from decimal import Decimal
from typing import Any

from marshmallow import Schema, ValidationError, fields, validate, validates_schema

from app.schemas.common import PartialUpdateMixin
from app.schemas.pagination import PaginationQuerySchema, make_page_schema

_NOT_BLANK = validate.Regexp(r".*\S.*", error="Must not be blank.")
_MAX_PRICE = Decimal("99999999.99")  # Numeric(10, 2)


def _price_field(**kwargs: Any) -> fields.Decimal:
    return fields.Decimal(
        places=2,
        as_string=True,
        validate=validate.Range(min=Decimal(0), max=_MAX_PRICE),
        **kwargs,
    )


class ServiceSchema(Schema):
    """Entrada (criação/PATCH parcial) e saída de serviços."""

    id = fields.Int(dump_only=True, metadata={"example": 1})
    name = fields.Str(
        required=True,
        validate=[validate.Length(min=1, max=120), _NOT_BLANK],
        metadata={"example": "Corte de cabelo"},
    )
    duration_minutes = fields.Int(
        required=True,
        validate=validate.Range(min=1, max=1440),
        metadata={"example": 45},
    )
    price = _price_field(required=True, metadata={"example": "60.00"})
    active = fields.Bool(load_default=True, metadata={"example": True})
    created_at = fields.AwareDateTime(dump_only=True)
    updated_at = fields.AwareDateTime(dump_only=True)

    @validates_schema
    def _require_some_field_on_patch(self, data: dict[str, Any], **kwargs: Any) -> None:
        if self.partial and not data:
            raise ValidationError("At least one field must be provided.")


class ServiceUpdateSchema(PartialUpdateMixin, ServiceSchema):
    pass


class ServiceListQuerySchema(PaginationQuerySchema):
    q = fields.Str(
        validate=validate.Length(max=100),
        metadata={"description": "Busca por nome.", "example": "corte"},
    )
    active = fields.Bool(metadata={"description": "Filtra por serviços ativos/inativos."})
    min_price = _price_field(metadata={"example": "30.00"})
    max_price = _price_field(metadata={"example": "100.00"})
    sort = fields.Str(
        load_default="name",
        validate=validate.OneOf(["name", "price", "duration_minutes", "created_at"]),
    )


ServicePageSchema = make_page_schema("ServicePage", ServiceSchema)
