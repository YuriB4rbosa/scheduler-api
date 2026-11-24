from typing import Any

from marshmallow import Schema, ValidationError, fields, validate, validates_schema

from app.schemas.common import PartialUpdateMixin
from app.schemas.pagination import PaginationQuerySchema, make_page_schema

_NOT_BLANK = validate.Regexp(r".*\S.*", error="Must not be blank.")
_PHONE = validate.Regexp(r"^\+?[0-9()\-\s]{8,30}$", error="Invalid phone number.")


class CustomerSchema(Schema):
    """Entrada (criação/PATCH parcial) e saída de clientes."""

    id = fields.Int(dump_only=True, metadata={"example": 1})
    name = fields.Str(
        required=True,
        validate=[validate.Length(min=1, max=120), _NOT_BLANK],
        metadata={"example": "Maria Oliveira"},
    )
    phone = fields.Str(allow_none=True, validate=_PHONE, metadata={"example": "+55 11 98888-7777"})
    email = fields.Email(allow_none=True, metadata={"example": "maria@email.com"})
    created_at = fields.AwareDateTime(dump_only=True)
    updated_at = fields.AwareDateTime(dump_only=True)

    @validates_schema
    def _require_some_field_on_patch(self, data: dict[str, Any], **kwargs: Any) -> None:
        if self.partial and not data:
            raise ValidationError("At least one field must be provided.")


class CustomerUpdateSchema(PartialUpdateMixin, CustomerSchema):
    pass


class CustomerListQuerySchema(PaginationQuerySchema):
    q = fields.Str(
        validate=validate.Length(max=100),
        metadata={"description": "Busca por nome, e-mail ou telefone.", "example": "maria"},
    )
    sort = fields.Str(load_default="name", validate=validate.OneOf(["name", "email", "created_at"]))


CustomerPageSchema = make_page_schema("CustomerPage", CustomerSchema)
