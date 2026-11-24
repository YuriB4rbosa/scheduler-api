"""Testes das constraints do banco (a última linha de defesa das regras de negócio)."""

from datetime import UTC, datetime, timedelta

import pytest
from flask import Flask
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Appointment, AppointmentStatus, Customer, Service, User

T0 = datetime(2030, 1, 10, 9, 0, tzinfo=UTC)


def _seed(user_email: str = "owner@example.com") -> tuple[User, Customer, Service]:
    user = User(name="Owner", email=user_email, password_hash="x")
    customer = Customer(user=user, name="Maria", email="maria@example.com")
    service = Service(user=user, name="Corte", duration_minutes=30, price=50)
    db.session.add_all([user, customer, service])
    db.session.commit()
    return user, customer, service


def _appt(user, customer, service, start, minutes=30, status="scheduled") -> Appointment:
    return Appointment(
        user_id=user.id,
        customer_id=customer.id,
        service_id=service.id,
        start_at=start,
        end_at=start + timedelta(minutes=minutes),
        status=status,
    )


def test_defaults_and_relationships(app: Flask) -> None:
    with app.app_context():
        user, customer, service = _seed()
        appt = _appt(user, customer, service, T0)
        db.session.add(appt)
        db.session.commit()

        assert appt.status == AppointmentStatus.SCHEDULED
        assert appt.created_at is not None
        assert appt.customer.name == "Maria"
        assert service.active is True
        assert user.appointments == [appt]


def test_overlapping_appointments_are_rejected_by_database(app: Flask) -> None:
    with app.app_context():
        user, customer, service = _seed()
        db.session.add(_appt(user, customer, service, T0))
        db.session.commit()

        db.session.add(_appt(user, customer, service, T0 + timedelta(minutes=15)))
        with pytest.raises(IntegrityError, match="ex_appointments_no_overlap"):
            db.session.commit()


def test_adjacent_appointments_are_allowed(app: Flask) -> None:
    with app.app_context():
        user, customer, service = _seed()
        db.session.add(_appt(user, customer, service, T0))
        db.session.add(_appt(user, customer, service, T0 + timedelta(minutes=30)))
        db.session.commit()


def test_canceled_appointment_frees_the_slot(app: Flask) -> None:
    with app.app_context():
        user, customer, service = _seed()
        db.session.add(_appt(user, customer, service, T0, status="canceled"))
        db.session.add(_appt(user, customer, service, T0))
        db.session.commit()


def test_same_slot_for_different_users_is_allowed(app: Flask) -> None:
    with app.app_context():
        u1, c1, s1 = _seed("a@example.com")
        u2, c2, s2 = _seed("b@example.com")
        db.session.add(_appt(u1, c1, s1, T0))
        db.session.add(_appt(u2, c2, s2, T0))
        db.session.commit()


def test_customer_email_is_unique_per_user(app: Flask) -> None:
    with app.app_context():
        user, _, _ = _seed()
        db.session.add(Customer(user_id=user.id, name="Outra", email="maria@example.com"))
        with pytest.raises(IntegrityError, match="uq_customers_user_email"):
            db.session.commit()


def test_service_duration_must_be_positive(app: Flask) -> None:
    with app.app_context():
        user, _, _ = _seed()
        db.session.add(Service(user_id=user.id, name="Ruim", duration_minutes=0, price=10))
        with pytest.raises(IntegrityError, match="ck_services_duration_positive"):
            db.session.commit()
