"""Regras de negócio do catálogo de serviços (corte, consulta, revisão...)."""

from decimal import Decimal
from typing import Any

from sqlalchemy import exists, select

from app.errors import ConflictError
from app.extensions import db
from app.models import Appointment, Service
from app.services.common import Page, get_owned_or_404, order_by_clause, paginate

LABEL = "Service"


def list_services(
    user_id: int,
    *,
    q: str | None = None,
    active: bool | None = None,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    sort: str = "name",
    order: str = "asc",
    page: int = 1,
    per_page: int = 20,
) -> Page[Service]:
    stmt = select(Service).where(Service.user_id == user_id)
    if q:
        stmt = stmt.where(Service.name.icontains(q, autoescape=True))
    if active is not None:
        stmt = stmt.where(Service.active.is_(active))
    if min_price is not None:
        stmt = stmt.where(Service.price >= min_price)
    if max_price is not None:
        stmt = stmt.where(Service.price <= max_price)
    stmt = stmt.order_by(*order_by_clause(Service, sort, order))
    return paginate(stmt, page=page, per_page=per_page)


def get_service(user_id: int, service_id: int) -> Service:
    return get_owned_or_404(Service, service_id, user_id, LABEL)


def create_service(user_id: int, data: dict[str, Any]) -> Service:
    data = {**data, "name": data["name"].strip()}
    service = Service(user_id=user_id, **data)
    db.session.add(service)
    db.session.commit()
    return service


def update_service(user_id: int, service_id: int, data: dict[str, Any]) -> Service:
    service = get_service(user_id, service_id)
    if "name" in data:
        data = {**data, "name": data["name"].strip()}
    for field, value in data.items():
        setattr(service, field, value)
    db.session.commit()
    return service


def delete_service(user_id: int, service_id: int) -> None:
    service = get_service(user_id, service_id)
    has_appointments = db.session.scalar(
        select(exists().where(Appointment.service_id == service.id))
    )
    if has_appointments:
        raise ConflictError(
            "Service has appointments and cannot be deleted. Deactivate it instead "
            "(PATCH active=false).",
            code="SERVICE_HAS_APPOINTMENTS",
        )
    db.session.delete(service)
    db.session.commit()
