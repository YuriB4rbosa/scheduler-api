from marshmallow import Schema, fields


class ErrorBodySchema(Schema):
    code = fields.Str(metadata={"example": "NOT_FOUND"})
    message = fields.Str(metadata={"example": "Customer not found."})
    details = fields.Dict(metadata={"example": {}})


class ErrorResponseSchema(Schema):
    """Formato de erro único de toda a API (usado na documentação OpenAPI)."""

    error = fields.Nested(ErrorBodySchema)
