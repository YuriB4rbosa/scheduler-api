from typing import Any

from marshmallow import Schema, ValidationError, fields, validate, validates_schema

from app.models import AppointmentStatus
from app.schemas.common import PartialUpdateMixin
from app.schemas.pagination import PaginationQuerySchema, make_page_schema

_START_EXAMPLE = "2030-01-10T09:00:00-03:00"


class AppointmentCreateSchema(Schema):
    """Entrada de criação (e base do PATCH). ``start_at`` exige fuso horário explícito."""

    customer_id = fields.Int(required=True, metadata={"example": 1})
    service_id = fields.Int(required=True, metadata={"example": 1})
    start_at = fields.AwareDateTime(
        required=True,
        format="iso",
        metadata={
            "description": "Início, em ISO 8601 COM fuso (ex.: -03:00 ou Z). Sem fuso é rejeitado.",
            "example": _START_EXAMPLE,
        },
    )
    notes = fields.Str(
        allow_none=True,
        validate=validate.Length(max=500),
        metadata={"example": "Cliente prefere atendimento com a Ana."},
    )

    @validates_schema
    def _require_some_field_on_patch(self, data: dict[str, Any], **kwargs: Any) -> None:
        if self.partial and not data:
            raise ValidationError("At least one field must be provided.")


class AppointmentUpdateSchema(PartialUpdateMixin, AppointmentCreateSchema):
    pass


class CustomerSummarySchema(Schema):
    id = fields.Int(metadata={"example": 1})
    name = fields.Str(metadata={"example": "Maria Oliveira"})


class ServiceSummarySchema(Schema):
    id = fields.Int(metadata={"example": 1})
    name = fields.Str(metadata={"example": "Corte de cabelo"})
    duration_minutes = fields.Int(metadata={"example": 45})
    price = fields.Decimal(places=2, as_string=True, metadata={"example": "60.00"})


class AppointmentSchema(Schema):
    """Saída. Datas em UTC; ``end_at`` é calculado (início + duração do serviço)."""

    id = fields.Int(metadata={"example": 1})
    customer_id = fields.Int(metadata={"example": 1})
    service_id = fields.Int(metadata={"example": 1})
    customer = fields.Nested(CustomerSummarySchema)
    service = fields.Nested(ServiceSummarySchema)
    start_at = fields.AwareDateTime(metadata={"example": "2030-01-10T12:00:00+00:00"})
    end_at = fields.AwareDateTime(metadata={"example": "2030-01-10T12:45:00+00:00"})
    status = fields.Str(
        validate=validate.OneOf([s.value for s in AppointmentStatus]),
        metadata={"example": "scheduled"},
    )
    notes = fields.Str(allow_none=True)
    created_at = fields.AwareDateTime()
    updated_at = fields.AwareDateTime()


class AppointmentListQuerySchema(PaginationQuerySchema):
    status = fields.Str(validate=validate.OneOf([s.value for s in AppointmentStatus]))
    customer_id = fields.Int(validate=validate.Range(min=1))
    service_id = fields.Int(validate=validate.Range(min=1))
    date_from = fields.AwareDateTime(
        format="iso",
        metadata={
            "description": "Início >= este instante (ISO 8601 com fuso).",
            "example": _START_EXAMPLE,
        },
    )
    date_to = fields.AwareDateTime(
        format="iso",
        metadata={
            "description": "Início < este instante (ISO 8601 com fuso).",
            "example": "2030-01-11T00:00:00-03:00",
        },
    )
    sort = fields.Str(
        load_default="start_at", validate=validate.OneOf(["start_at", "created_at", "status"])
    )

    @validates_schema
    def _validate_range(self, data: dict[str, Any], **kwargs: Any) -> None:
        start, end = data.get("date_from"), data.get("date_to")
        if start and end and start >= end:
            raise ValidationError("date_from must be earlier than date_to.", "date_to")


AppointmentPageSchema = make_page_schema("AppointmentPage", AppointmentSchema)
