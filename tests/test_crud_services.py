"""Testes unitários das regras de clientes e catálogo (camada de services)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from flask import Flask

from app.errors import ConflictError, NotFoundError
from app.extensions import db
from app.models import Appointment, User
from app.services import auth_service, catalog_service, customer_service


@pytest.fixture
def users(app: Flask) -> tuple[int, int]:
    with app.app_context():
        a = auth_service.register_user("A", "a@x.com", "senha-segura-123")
        b = auth_service.register_user("B", "b@x.com", "senha-segura-123")
        return a.id, b.id


def _book(user_id: int, customer_id: int, service_id: int) -> None:
    start = datetime(2030, 1, 1, 10, 0, tzinfo=UTC)
    db.session.add(
        Appointment(
            user_id=user_id,
            customer_id=customer_id,
            service_id=service_id,
            start_at=start,
            end_at=start + timedelta(minutes=30),
        )
    )
    db.session.commit()


# ---------- clientes ----------


def test_customer_is_invisible_to_other_users(app: Flask, users: tuple[int, int]) -> None:
    owner, other = users
    with app.app_context():
        customer = customer_service.create_customer(owner, {"name": "Maria"})
        with pytest.raises(NotFoundError) as exc:
            customer_service.get_customer(other, customer.id)
        assert exc.value.code == "CUSTOMER_NOT_FOUND"
        assert customer_service.list_customers(other).total == 0


def test_customer_email_is_normalized_and_unique_per_user(
    app: Flask, users: tuple[int, int]
) -> None:
    owner, other = users
    with app.app_context():
        created = customer_service.create_customer(
            owner, {"name": "Maria", "email": " Maria@X.com "}
        )
        assert created.email == "maria@x.com"
        with pytest.raises(ConflictError) as exc:
            customer_service.create_customer(owner, {"name": "Outra", "email": "MARIA@x.com"})
        assert exc.value.code == "CUSTOMER_EMAIL_EXISTS"
        # o mesmo e-mail em outro usuário é permitido
        customer_service.create_customer(other, {"name": "Maria", "email": "maria@x.com"})


def test_customers_without_email_do_not_conflict(app: Flask, users: tuple[int, int]) -> None:
    owner, _ = users
    with app.app_context():
        customer_service.create_customer(owner, {"name": "A"})
        customer_service.create_customer(owner, {"name": "B"})
        assert customer_service.list_customers(owner).total == 2


def test_update_customer_can_keep_own_email_but_not_take_another(
    app: Flask, users: tuple[int, int]
) -> None:
    owner, _ = users
    with app.app_context():
        a = customer_service.create_customer(owner, {"name": "A", "email": "a@x.com"})
        customer_service.create_customer(owner, {"name": "B", "email": "b@x.com"})
        customer_service.update_customer(owner, a.id, {"email": "a@x.com", "name": "A2"})
        with pytest.raises(ConflictError):
            customer_service.update_customer(owner, a.id, {"email": "b@x.com"})


def test_search_treats_wildcards_literally(app: Flask, users: tuple[int, int]) -> None:
    owner, _ = users
    with app.app_context():
        customer_service.create_customer(owner, {"name": "100% Fiel"})
        customer_service.create_customer(owner, {"name": "Maria"})
        result = customer_service.list_customers(owner, q="%")
        assert [c.name for c in result.items] == ["100% Fiel"]


def test_pagination_metadata_and_stable_order(app: Flask, users: tuple[int, int]) -> None:
    owner, _ = users
    with app.app_context():
        for _ in range(25):
            customer_service.create_customer(owner, {"name": "Mesmo Nome"})
        seen: list[int] = []
        for page in (1, 2, 3):
            result = customer_service.list_customers(owner, page=page, per_page=10)
            assert (result.total, result.pages) == (25, 3)
            seen += [c.id for c in result.items]
        assert len(seen) == len(set(seen)) == 25  # sem repetição entre páginas
        assert customer_service.list_customers(owner, page=9, per_page=10).items == []


def test_cannot_delete_customer_with_appointments(app: Flask, users: tuple[int, int]) -> None:
    owner, _ = users
    with app.app_context():
        customer = customer_service.create_customer(owner, {"name": "Maria"})
        service = catalog_service.create_service(
            owner, {"name": "Corte", "duration_minutes": 30, "price": Decimal("50")}
        )
        _book(owner, customer.id, service.id)
        with pytest.raises(ConflictError) as exc:
            customer_service.delete_customer(owner, customer.id)
        assert exc.value.code == "CUSTOMER_HAS_APPOINTMENTS"


# ---------- serviços ----------


def test_service_is_invisible_to_other_users(app: Flask, users: tuple[int, int]) -> None:
    owner, other = users
    with app.app_context():
        service = catalog_service.create_service(
            owner, {"name": "Corte", "duration_minutes": 30, "price": Decimal("50")}
        )
        with pytest.raises(NotFoundError):
            catalog_service.get_service(other, service.id)
        with pytest.raises(NotFoundError):
            catalog_service.update_service(other, service.id, {"name": "Hack"})
        with pytest.raises(NotFoundError):
            catalog_service.delete_service(other, service.id)


def test_service_filters_by_price_range_and_active(app: Flask, users: tuple[int, int]) -> None:
    owner, _ = users
    with app.app_context():
        for name, price, active in [("A", "20", True), ("B", "50", True), ("C", "90", False)]:
            catalog_service.create_service(
                owner,
                {"name": name, "duration_minutes": 30, "price": Decimal(price), "active": active},
            )
        names = lambda **kw: [s.name for s in catalog_service.list_services(owner, **kw).items]  # noqa: E731
        assert names(min_price=Decimal(30)) == ["B", "C"]
        assert names(max_price=Decimal(50)) == ["A", "B"]
        assert names(active=False) == ["C"]
        assert names(sort="price", order="desc") == ["C", "B", "A"]


def test_cannot_delete_service_with_appointments(app: Flask, users: tuple[int, int]) -> None:
    owner, _ = users
    with app.app_context():
        customer = customer_service.create_customer(owner, {"name": "Maria"})
        service = catalog_service.create_service(
            owner, {"name": "Corte", "duration_minutes": 30, "price": Decimal("50")}
        )
        _book(owner, customer.id, service.id)
        with pytest.raises(ConflictError) as exc:
            catalog_service.delete_service(owner, service.id)
        assert exc.value.code == "SERVICE_HAS_APPOINTMENTS"
        assert db.session.get(User, owner) is not None
