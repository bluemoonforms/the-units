import boto3
import datetime
import io
import json
import os
import uuid
from chalice import AuthResponse, Chalice, Response
from marshmallow import ValidationError

from chalicelib.bluemoon_api import BluemoonApi, BluemoonAuthorization
from chalicelib.database import DatabaseConnection
from chalicelib.exceptions import MissingLeaseFormsException
from chalicelib.models import Lease, LeaseEsignature, StatusEnum
from chalicelib.schemas import (
    ExecuteSchema,
    LeaseEsignatureSchema,
    LeaseSchema,
    LoginSchema,
    PaginatedLeaseSchema,
    UserSchema,
)
from chalicelib.utils import (
    ModelFilter,
    api_error_response,
    forms_mapper,
    get_token,
    gzip_response,
)


app = Chalice(app_name="the-units")
s3_client = boto3.client("s3")
BUCKET = os.getenv("AWS_BUCKET")


@app.authorizer()
def demo_auth(auth_request):
    auth_api = BluemoonAuthorization()
    token = auth_request.token
    if token.startswith("Bearer "):
        token = token.split("Bearer ")[1]
    authorized = auth_api.check_authorization(token)
    if authorized:
        return AuthResponse(routes=["*"], principal_id=authorized.id)
    else:
        return AuthResponse(routes=[], principal_id="id")


@app.route("/login", methods=["POST"], cors=True)
def login():
    request = app.current_request
    auth_api = BluemoonAuthorization()

    try:
        login_data = LoginSchema().load(request.json_body)
    except ValidationError as err:
        return {"success": False, "errors": err.messages}
    results = auth_api.authenticate(
        username=login_data["username"], password=login_data["password"]
    )
    if "success" not in results or not results["success"]:
        return results
    schema = UserSchema()

    return schema.dumps(auth_api.user)


@app.route("/", authorizer=demo_auth, methods=["GET"], cors=True)
def index():
    request = app.current_request
    token = get_token(request)
    api = BluemoonApi(token=token)
    return api.user_details()


@app.route("/leases", authorizer=demo_auth, methods=["GET", "POST"], cors=True)
def leases():
    """Filters and returns list of leases."""
    request = app.current_request
    user_id = request.context["authorizer"]["principalId"]
    db = DatabaseConnection()
    session = db.session()

    if request.method == "POST":
        try:
            lease_data = request.json_body
            new_lease = LeaseSchema().load(lease_data, session=session)
        except ValidationError as err:
            return {"success": False, "errors": err.messages}
        else:
            new_lease.user_id = user_id
            session.add(new_lease)
            session.commit()

    filters = {
        "fields": ["id", "bluemoon_id", "unit_number"],
        "default_page_size": 25,
        "default_order": "id",
        "default_dir": "desc",
    }
    filtering = ModelFilter(
        model=Lease, filters=filters, user_id=user_id, params=request.query_params
    )
    results = filtering.results()
    schema = PaginatedLeaseSchema()
    return gzip_response(data=schema.dump(results), status_code=200)


@app.route("/lease/{id}", authorizer=demo_auth, methods=["GET", "POST"], cors=True)
def lease(id):
    """Fetches lease and handles the callback."""
    request = app.current_request
    user_id = request.context["authorizer"]["principalId"]

    db = DatabaseConnection()
    session = db.session()
    query = session.query(Lease)
    lease = query.filter(Lease.id == id).filter(Lease.user_id == user_id).first()
    if not lease:
        return gzip_response(data={"message": "Not Found"}, status_code=404)

    if request.method == "POST" and "id" in request.json_body:
        lease.bluemoon_id = request.json_body["id"]
        session.add(lease)
        session.commit()

    return gzip_response(data=LeaseSchema().dump(lease), status_code=200)


@app.route("/lease/forms", authorizer=demo_auth, methods=["GET", "POST"], cors=True)
def lease_forms():
    bm_api = BluemoonApi(token=get_token(request=app.current_request))
    lease_forms = bm_api.lease_forms()
    if not lease_forms:
        return api_error_response()

    return gzip_response(data={"data": lease_forms}, status_code=200)


@app.route(
    "/lease/request/esign/{id}", authorizer=demo_auth, methods=["POST"], cors=True
)
def lease_request_esign(id):
    request = app.current_request
    user_id = request.context["authorizer"]["principalId"]

    db = DatabaseConnection()
    session = db.session()
    query = session.query(Lease)
    lease = query.filter(Lease.id == id).filter(Lease.user_id == user_id).first()
    if not lease:
        return gzip_response(data={"message": "Not Found"}, status_code=404)

    data = app.current_request.json_body
    token = get_token(request=app.current_request)
    selected_forms = data.get("forms")
    try:
        forms = forms_mapper(selected_forms=selected_forms, token=token)
    except MissingLeaseFormsException:
        return api_error_response()

    bm_api = BluemoonApi(token=token)
    post_data = {
        "lease_id": lease.bluemoon_id,
        "external_id": lease.id,
        "send_notifications": True,
        "notification_url": "{}/{}".format(os.getenv("UNITS_URL"), "notifications"),
        "data": forms,
    }
    response = bm_api.request_esignature(data=post_data)
    if not response.get("success"):
        return gzip_response(data=response, status_code=200)

    lease_esignature = LeaseEsignature(
        lease_id=lease.id,
        bluemoon_id=response["data"]["id"],
        data=response["data"]["data"],
    )
    session.add(lease_esignature)
    session.commit()
    return gzip_response(
        data=LeaseEsignatureSchema().dump(lease_esignature), status_code=201
    )


@app.route("/lease/print/{id}", authorizer=demo_auth, methods=["POST"], cors=True)
def lease_print(id):
    """Print requires the lease_id as it just uses that data, no esignature request."""
    user_id = app.current_request.context["authorizer"]["principalId"]

    db = DatabaseConnection()
    session = db.session()
    query = session.query(Lease)
    lease = query.filter(Lease.id == id).filter(Lease.user_id == user_id).first()
    if not lease:
        return gzip_response(data={"message": "Not Found"}, status_code=404)
    if not lease.bluemoon_id:
        return gzip_response(
            data={"message": "Bluemoon Lease not created."}, status_code=200
        )

    data = app.current_request.json_body
    token = get_token(request=app.current_request)
    selected_forms = data.get("forms")
    try:
        forms = forms_mapper(selected_forms=selected_forms, token=token)
    except MissingLeaseFormsException:
        return api_error_response()

    post_data = {"lease_id": lease.bluemoon_id, "data": forms}
    bm_api = BluemoonApi(token=token)

    response = bm_api.post_raw(path="lease/generate/pdf", data=post_data)
    content_type = response.headers.get("Content-Type")
    context = {}

    if content_type == "application/pdf":
        length = 0
        mem = io.BytesIO()
        for chunk in response.iter_content(chunk_size=128):
            length += len(chunk)
            mem.write(chunk)
        mem.seek(0)

        now = datetime.datetime.now()
        file_name = "{0:%d}/{0:%m}/{1}.pdf".format(now, uuid.uuid4().hex)
        s3_client.upload_fileobj(mem, BUCKET, file_name)
        signed_url = s3_client.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": BUCKET, "Key": file_name},
            ExpiresIn=3600,
        )
        context["success"] = True
        context["url"] = signed_url
    elif content_type == "application/json":
        context.update(response.json())

    return gzip_response(data=context, status_code=200)


@app.route("/lease/execute/{id}", authorizer=demo_auth, methods=["POST"], cors=True)
def lease_execute(id):
    """Execute using the lease_esignature_id as there could be more than one."""
    request = app.current_request
    user_id = request.context["authorizer"]["principalId"]

    try:
        execute_data = ExecuteSchema().load(request.json_body)
    except ValidationError as err:
        return gzip_response(
            data={"success": False, "errors": err.messages}, status_code=200
        )

    db = DatabaseConnection()
    session = db.session()
    query = session.query(LeaseEsignature).join("lease")
    lease_esignature = (
        query.filter(LeaseEsignature.id == id).filter(Lease.user_id == user_id).first()
    )
    if not lease_esignature:
        return gzip_response(data={"message": "Not Found"}, status_code=404)
    bm_api = BluemoonApi(token=get_token(request=request))

    # Update the status just in case we did not receive the latest data
    response = bm_api.esignature_details(bm_id=lease_esignature.bluemoon_id)
    if not response:
        return api_error_response()

    storage_data = response["data"]
    lease_esignature.data = storage_data
    try:
        signers_data = storage_data["esign"]["data"]["signers"]["data"]
        lease_esignature.transition_status(signers_data=signers_data)
    except KeyError:
        pass
    session.add(lease_esignature)
    session.commit()

    if lease_esignature.status != StatusEnum.signed:
        data = {
            "success": False,
            "errors": [{"status": "Lease has not been signed by all residents."}],
        }
        return gzip_response(data=data, status_code=404)

    response = bm_api.execute_lease(
        bm_id=lease_esignature.lease.bluemoon_id, data=execute_data
    )
    success = "executed" in response and response["executed"]

    return gzip_response(data={"success": success}, status_code=200)


@app.route("/configuration/{id}", authorizer=demo_auth, methods=["GET"], cors=True)
def configuration(id):
    """Fetch the configuration for Bluemoon integration."""
    user_id = app.current_request.context["authorizer"]["principalId"]

    db = DatabaseConnection()
    session = db.session()
    query = session.query(Lease)
    lease = query.filter(Lease.id == id).filter(Lease.user_id == user_id).first()

    token = get_token(request=app.current_request)
    bm_api = BluemoonApi(token=token)

    configuration = {
        "apiUrl": bm_api.url,
        "propertyNumber": bm_api.property_number(),
        "accessToken": token,
        "view": "create",
        "callBack": "{}/{}".format(os.getenv("UNITS_URL"), lease.id),
        "leaseData": {
            "standard": {"address": "123 Super Dr.", "unit_number": lease.unit_number}
        },
    }
    return gzip_response(data=configuration, status_code=200)


@app.route("/logout", authorizer=demo_auth, methods=["GET"], cors=True)
def logout():
    """Log the user out."""
    auth_api = BluemoonAuthorization()
    auth_api.logout(token=get_token(app.current_request))


@app.route("/notifications", methods=["POST"])
def notifications():
    data = app.current_request.json_body
    if "data" not in data:
        return gzip_response(data={"message": "Bad Request"}, status_code=405)

    db = DatabaseConnection()
    session = db.session()
    query = session.query(LeaseEsignature)
    lease_esignature = query.filter(
        LeaseEsignature.bluemoon_id == data["data"]["id"]
    ).first()

    lease_esignature.data = data["data"]
    try:
        signers_data = data["data"]["esign"]["data"]["signers"]["data"]
        lease_esignature.transition_status(signers_data=signers_data)
    except KeyError:
        pass
    session.add(lease_esignature)
    session.commit()
    return {"success": True}
