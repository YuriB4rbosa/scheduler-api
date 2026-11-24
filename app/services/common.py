"""Utilitários compartilhados pelos services: paginação e acesso restrito ao dono."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, select

from app.errors import NotFoundError
from app.extensions import db


@dataclass(frozen=True)
class Page[T]:
    items: list[T]
    page: int
    per_page: int
    total: int
    pages: int


def paginate[T](stmt: Select[Any], *, page: int, per_page: int) -> Page[T]:
    pagination = db.paginate(stmt, page=page, per_page=per_page, error_out=False, count=True)
    return Page(
        items=list(pagination.items),
        page=page,
        per_page=per_page,
        total=pagination.total or 0,
        pages=pagination.pages,
    )


def get_owned_or_404[M](
    model: type[M], obj_id: int, user_id: int, label: str, options: tuple[Any, ...] = ()
) -> M:
    """Busca um recurso do usuário.

    Recurso inexistente e recurso de outro usuário produzem a MESMA resposta (404), para não
    revelar a existência de IDs que não pertencem a quem está perguntando.
    """
    stmt = select(model).where(model.id == obj_id, model.user_id == user_id)  # type: ignore[attr-defined]
    obj = db.session.scalar(stmt.options(*options))
    if obj is None:
        raise NotFoundError(f"{label} not found.", code=f"{label.upper()}_NOT_FOUND")
    return obj


def order_by_clause(model: type[Any], sort: str, order: str) -> list[Any]:
    """ORDER BY com desempate por id, para a paginação ser estável."""
    column = getattr(model, sort)
    primary = column.desc() if order == "desc" else column.asc()
    return [primary, model.id.asc()]
