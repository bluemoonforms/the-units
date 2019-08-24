from marshmallow_sqlalchemy import ModelSchema
from marshmallow import Schema, fields, validate

from chalicelib.models import Lease, LeaseEsignature, StatusEnum, User


class SmartNested(fields.Nested):
    def serialize(self, attr, obj, accessor=None):
        if attr not in obj.__dict__:
            return {"id": int(getattr(obj, attr.rstrip("s") + "_id"))}
        return super(SmartNested, self).serialize(attr, obj, accessor)


class LeaseSchema(ModelSchema):
    esignatures = fields.Nested("LeaseEsignatureSchema", many=True, exclude=("lease",))

    class Meta:
        model = Lease
        exclude = ("user_id",)


class LeaseEsignatureSchema(ModelSchema):
    status = fields.Method("get_status", deserialize="load_status")

    def get_status(self, obj):
        return obj.status.name

    def load_status(self, value):
        try:
            return getattr(StatusEnum, value)
        except AttributeError:
            return

    class Meta:
        model = LeaseEsignature


class UserSchema(ModelSchema):
    class Meta:
        model = User
        excluede = ("leases",)


class PaginatedLeaseSchema(Schema):
    items = fields.Nested(LeaseSchema, many=True)
    previous_page = fields.Integer()
    next_page = fields.Integer()
    has_previous = fields.Boolean()
    has_next = fields.Boolean()
    total = fields.Integer()
    pages = fields.Integer()


class LoginSchema(Schema):
    username = fields.Str(
        required=True, error_messages={"required": "Username is required."}
    )
    password = fields.Str(
        required=True, error_messages={"required": "Password is required."}
    )


class ExecuteSchema(Schema):
    name = fields.Str(required=True, error_messages={"required": "Name is required."})
    initials = fields.Str(
        required=True,
        validate=validate.Length(max=3),
        error_messages={"required": "Initials are required."},
    )
    title = fields.Str()


class PrintPdfSchema(Schema):
    forms = fields.List(fields.Str())
