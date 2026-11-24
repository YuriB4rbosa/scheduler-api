from collections.abc import Callable
from typing import Any

from flask_jwt_extended import jwt_required
from flask_smorest import Blueprint

from app.schemas.common import ErrorResponseSchema

BEARER = [{"bearerAuth": []}]


def protected(blp: Blueprint) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Exige JWT e documenta o esquema de segurança e o 401 no OpenAPI."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        func = blp.alt_response(
            401, schema=ErrorResponseSchema, description="Token ausente, inválido ou expirado."
        )(func)
        func = blp.doc(security=BEARER)(func)
        return jwt_required()(func)

    return decorator
