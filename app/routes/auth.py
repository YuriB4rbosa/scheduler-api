from typing import Any

from flask import current_app
from flask.views import MethodView
from flask_jwt_extended import jwt_required
from flask_smorest import Blueprint

from app.auth import current_user, current_user_id
from app.extensions import limiter
from app.schemas.auth import (
    AccessTokenSchema,
    LoginSchema,
    RegisterSchema,
    TokenPairSchema,
    UserSchema,
)
from app.schemas.common import ErrorResponseSchema
from app.services import auth_service

blp = Blueprint(
    "auth",
    __name__,
    url_prefix="/api/v1/auth",
    description="Cadastro, login e renovação de token.",
)

_BEARER = [{"bearerAuth": []}]


def _auth_rate_limit() -> str:
    return current_app.config["AUTH_RATE_LIMIT"]


@blp.route("/register")
class Register(MethodView):
    @limiter.limit(_auth_rate_limit)
    @blp.arguments(RegisterSchema)
    @blp.response(201, UserSchema)
    @blp.alt_response(409, schema=ErrorResponseSchema, description="E-mail já cadastrado.")
    def post(self, data: dict[str, Any]) -> Any:
        """Cadastra um novo usuário (dono de negócio)."""
        return auth_service.register_user(**data)


@blp.route("/login")
class Login(MethodView):
    @limiter.limit(_auth_rate_limit)
    @blp.arguments(LoginSchema)
    @blp.response(200, TokenPairSchema)
    @blp.alt_response(401, schema=ErrorResponseSchema, description="Credenciais inválidas.")
    def post(self, data: dict[str, Any]) -> Any:
        """Autentica e devolve um access token (curto) e um refresh token."""
        user = auth_service.authenticate(**data)
        return auth_service.issue_tokens(user)


@blp.route("/refresh")
class Refresh(MethodView):
    @jwt_required(refresh=True)
    @blp.doc(security=_BEARER)
    @blp.response(200, AccessTokenSchema)
    @blp.alt_response(
        401, schema=ErrorResponseSchema, description="Refresh token ausente ou inválido."
    )
    def post(self) -> Any:
        """Troca um refresh token válido por um novo access token."""
        return auth_service.issue_access_token(current_user_id())


@blp.route("/me")
class Me(MethodView):
    @jwt_required()
    @blp.doc(security=_BEARER)
    @blp.response(200, UserSchema)
    @blp.alt_response(401, schema=ErrorResponseSchema, description="Token ausente ou inválido.")
    def get(self) -> Any:
        """Devolve o usuário autenticado."""
        return current_user()
