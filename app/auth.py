"""Helpers de autenticação usados pelas rotas."""

from flask_jwt_extended import get_jwt_identity

from app.errors import UnauthorizedError
from app.extensions import db
from app.models import User


def current_user_id() -> int:
    """ID do usuário autenticado (a rota precisa estar sob ``@jwt_required``)."""
    return int(get_jwt_identity())


def current_user() -> User:
    user = db.session.get(User, current_user_id())
    if user is None:
        # Token válido, mas o usuário foi removido depois da emissão.
        raise UnauthorizedError("User no longer exists.", code="INVALID_TOKEN")
    return user
