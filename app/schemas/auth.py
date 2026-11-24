from marshmallow import Schema, fields, validate

_NOT_BLANK = validate.Regexp(r".*\S.*", error="Must not be blank.")


class RegisterSchema(Schema):
    name = fields.Str(
        required=True,
        validate=[validate.Length(min=1, max=120), _NOT_BLANK],
        metadata={"example": "Ana Souza"},
    )
    email = fields.Email(required=True, metadata={"example": "ana@salao.com"})
    password = fields.Str(
        required=True,
        load_only=True,
        validate=validate.Length(min=8, max=128),
        metadata={"example": "senha-segura-123"},
    )


class LoginSchema(Schema):
    email = fields.Email(required=True, metadata={"example": "ana@salao.com"})
    password = fields.Str(required=True, load_only=True, metadata={"example": "senha-segura-123"})


class UserSchema(Schema):
    id = fields.Int(dump_only=True, metadata={"example": 1})
    name = fields.Str(dump_only=True, metadata={"example": "Ana Souza"})
    email = fields.Email(dump_only=True, metadata={"example": "ana@salao.com"})
    created_at = fields.AwareDateTime(dump_only=True)


class TokenPairSchema(Schema):
    access_token = fields.Str(metadata={"example": "eyJhbGciOiJIUzI1NiIs..."})
    refresh_token = fields.Str(metadata={"example": "eyJhbGciOiJIUzI1NiIs..."})
    token_type = fields.Str(metadata={"example": "Bearer"})


class AccessTokenSchema(Schema):
    access_token = fields.Str(metadata={"example": "eyJhbGciOiJIUzI1NiIs..."})
    token_type = fields.Str(metadata={"example": "Bearer"})
