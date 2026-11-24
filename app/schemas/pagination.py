from marshmallow import RAISE, Schema, fields, validate


class PaginationQuerySchema(Schema):
    """Parâmetros comuns de listagem (parâmetros desconhecidos geram 422)."""

    class Meta:
        unknown = RAISE

    page = fields.Int(load_default=1, validate=validate.Range(min=1), metadata={"example": 1})
    per_page = fields.Int(
        load_default=20, validate=validate.Range(min=1, max=100), metadata={"example": 20}
    )
    order = fields.Str(load_default="asc", validate=validate.OneOf(["asc", "desc"]))


def make_page_schema(name: str, item_schema: type[Schema]) -> type[Schema]:
    """Envelope de listagem: {items, page, per_page, total, pages}."""
    return Schema.from_dict(
        {
            "items": fields.List(fields.Nested(item_schema)),
            "page": fields.Int(metadata={"example": 1}),
            "per_page": fields.Int(metadata={"example": 20}),
            "total": fields.Int(metadata={"example": 42}),
            "pages": fields.Int(metadata={"example": 3}),
        },
        name=name,
    )
