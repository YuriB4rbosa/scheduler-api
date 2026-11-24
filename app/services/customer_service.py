"""Regras de negócio de clientes. Todas as operações são escopadas pelo ``user_id``."""

from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError

from app.errors import ConflictError
from app.extensions import db
from app.models import Appointment, Customer
from app.services.common import Page, get_owned_or_404, order_by_clause, paginate

LABEL = "Customer"


def _normalize(data: dict[str, Any]) -> dict[str, Any]:
    data = dict(data)
    if data.get("name") is not None:
        data["name"] = data["name"].strip()
    if data.get("email") is not None:
        data["email"] = data["email"].strip().lower()
    return data


def _ensure_email_available(user_id: int, email: str | None, ignore_id: int | None = None) -> None:
    if not email:
        return
    stmt = select(Customer.id).where(Customer.user_id == user_id, Customer.email == email)
    if ignore_id is not None:
        stmt = stmt.where(Customer.id != ignore_id)
    if db.session.scalar(stmt) is not None:
        raise ConflictError(
            "A customer with this email already exists.", code="CUSTOMER_EMAIL_EXISTS"
        )


def _commit_or_conflict() -> None:
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ConflictError(
            "A customer with this email already exists.", code="CUSTOMER_EMAIL_EXISTS"
        ) from None


def list_customers(
    user_id: int,
    *,
    q: str | None = None,
    sort: str = "name",
    order: str = "asc",
    page: int = 1,
    per_page: int = 20,
) -> Page[Customer]:
    stmt = select(Customer).where(Customer.user_id == user_id)
    if q:
        stmt = stmt.where(
            Customer.name.icontains(q, autoescape=True)
            | Customer.email.icontains(q, autoescape=True)
            | Customer.phone.icontains(q, autoescape=True)
        )
    stmt = stmt.order_by(*order_by_clause(Customer, sort, order))
    return paginate(stmt, page=page, per_page=per_page)


def get_customer(user_id: int, customer_id: int) -> Customer:
    return get_owned_or_404(Customer, customer_id, user_id, LABEL)


def create_customer(user_id: int, data: dict[str, Any]) -> Customer:
    data = _normalize(data)
    _ensure_email_available(user_id, data.get("email"))
    customer = Customer(user_id=user_id, **data)
    db.session.add(customer)
    _commit_or_conflict()
    return customer


def update_customer(user_id: int, customer_id: int, data: dict[str, Any]) -> Customer:
    customer = get_customer(user_id, customer_id)
    data = _normalize(data)
    if "email" in data:
        _ensure_email_available(user_id, data["email"], ignore_id=customer.id)
    for field, value in data.items():
        setattr(customer, field, value)
    _commit_or_conflict()
    return customer


def delete_customer(user_id: int, customer_id: int) -> None:
    customer = get_customer(user_id, customer_id)
    has_appointments = db.session.scalar(
        select(exists().where(Appointment.customer_id == customer.id))
    )
    if has_appointments:
        raise ConflictError(
            "Customer has appointments and cannot be deleted. Cancel or remove them first.",
            code="CUSTOMER_HAS_APPOINTMENTS",
        )
    db.session.delete(customer)
    db.session.commit()
