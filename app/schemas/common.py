from typing import Any

from marshmallow import Schema, fields


class ErrorBodySchema(Schema):
    code = fields.Str(metadata={"example": "NOT_FOUND"})
    message = fields.Str(metadata={"example": "Customer not found."})
    details = fields.Dict(metadata={"example": {}})


class ErrorResponseSchema(Schema):
    """Formato de erro único de toda a API (usado na documentação OpenAPI)."""

    error = fields.Nested(ErrorBodySchema)


class PartialUpdateMixin:
    """Para schemas de PATCH: nenhum campo é obrigatório (nem na validação, nem no OpenAPI)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs["partial"] = True
        super().__init__(*args, **kwargs)
        for field in self.fields.values():  # type: ignore[attr-defined]
            field.required = False
