import json
import gzip
import math
from chalice import Response

from chalicelib.database import DatabaseConnection
from chalicelib.bluemoon_api import BluemoonApi
from chalicelib.exceptions import MissingLeaseFormsException


def get_token(request):
    try:
        return request.headers["Authorization"].split("Bearer ")[1]
    except (KeyError, TypeError, IndexError):
        pass


def gzip_response(data, status_code, headers={}):
    blob = json.dumps(data).encode("utf-8")
    payload = gzip.compress(blob)
    headers["Content-Type"] = "application/json"
    headers["Content-Encoding"] = "gzip"

    return Response(body=payload, status_code=status_code, headers=headers)


def api_error_response():
    return gzip_response(
        data={"message": "Unable to retrieve api data."}, status_code=500
    )


def forms_mapper(selected_forms, token):
    bm_api = BluemoonApi(token=token)
    lease_forms = bm_api.lease_forms()
    if not lease_forms:
        raise MissingLeaseFormsException()

    standard_selections = [
        lease_form["name"]
        for lease_form in lease_forms
        if lease_form["type"] == "standard"
    ]
    custom_selections = [
        lease_form["name"]
        for lease_form in lease_forms
        if lease_form["type"] == "custom"
    ]
    standard_forms = [
        form_name for form_name in selected_forms if form_name in standard_selections
    ]
    custom_forms = [
        form_name for form_name in selected_forms if form_name in custom_selections
    ]
    return {'standard_forms': standard_forms, 'custom_forms': custom_forms}


class Page(object):
    def __init__(self, items, page, page_size, total):
        self.items = items
        self.previous_page = None
        self.next_page = None
        self.has_previous = page > 1
        if self.has_previous:
            self.previous_page = page - 1
        previous_items = (page - 1) * page_size
        self.has_next = previous_items + len(items) < total
        if self.has_next:
            self.next_page = page + 1
        self.total = total
        self.pages = int(math.ceil(total / float(page_size)))


class ModelFilter(object):
    sort_directions = ["asc", "desc"]

    def __init__(self, filters, model, user_id, params=None):
        self.filters = filters
        self.params = params
        self.user_id = user_id
        if not params:
            self.params = {}
        self.model = model
        self.query = None

    def paginate(self):
        """Paginate the query data."""
        try:
            page_size = int(
                self.params.get("page_size", self.filters["default_page_size"])
            )
        except ValueError:
            page_size = self.filters["default_page_size"]

        try:
            page = int(self.params.get("page", 1))
        except ValueError:
            page = 1
        items = self.query.limit(page_size).offset((page - 1) * page_size).all()
        total = self.query.order_by(None).count()
        return Page(items, page, page_size, total)

    def ordering(self):
        """Process the query ordering."""
        sort_dir = self.params.get("order_dir", self.filters["default_dir"])
        if sort_dir not in self.sort_directions:
            sort_dir = self.filters["default_dir"]

        sort_field = self.params.get("order_by", self.filters["default_order"])
        if sort_field not in self.filters["fields"]:
            sort_field = self.filters["default_order"]

        try:
            sort_attr = getattr(self.model, sort_field)
        except AttributeError:
            pass
        else:
            if sort_dir == "desc":
                sort_attr = sort_attr.desc()
            self.query = self.query.order_by(sort_attr)

    def filtering(self):
        """Filter the model."""
        query = self.query
        # TODO: this needs a subquery as well for children of
        # objects that have the authorized user. maybe pass in
        # query object that has join or auth already filtered
        if hasattr(self.model, "user_id"):
            query = query.filter(self.model.user_id == self.user_id)

        for field, filter_value in self.params.items():
            if field not in self.filters["fields"]:
                continue

            try:
                value, filter_type = filter_value.split(":")
            except ValueError:
                continue

            attr = getattr(self.model, field)
            if filter_type == "contains":
                query = query.filter(attr.like("%{}%".format(value)))
                continue

            if filter_type == "starts":
                query = query.filter(attr.like("{}%".format(value)))
                continue

            if filter_type == "ends":
                query = query.filter(attr.like("%{}".format(value)))
                continue

            if filter_type == "eq":
                query = query.filter(attr == value)
                continue

            if filter_type == "ne":
                query = query.filter(attr != value)
                continue

            if filter_type == "ge":
                query = query.filter(attr >= int(value))
                continue

            if filter_type == "gt":
                query = query.filter(attr > int(value))
                continue

            if filter_type == "le":
                query = query.filter(attr <= int(value))
                continue

            if filter_type == "ls":
                query = query.filter(attr < int(value))
                continue

            if filter_type == "in":
                value = value.split("|")
                query = query.filter(attr.in_(value))
                continue

            if filter_type == "is_null":
                query = query.filter(attr == None)  # noqa
                continue
        self.query = query

    def results(self):
        db = DatabaseConnection()
        session = db.session()
        self.query = session.query(self.model)
        self.filtering()
        self.ordering()
        return self.paginate()
