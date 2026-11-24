"""Testes unitários das regras de agendamento (camada de services)."""

from datetime import timedelta, timezone
from decimal import Decimal

import pytest
from flask import Flask

from app.errors import ConflictError, NotFoundError, UnprocessableError
from app.extensions import db
from app.models import Appointment, AppointmentStatus
from app.services import (
    appointment_service,
    auth_service,
    catalog_service,
    customer_service,
)
from tests.helpers import at


@pytest.fixture
def world(app: Flask) -> dict[str, int]:
    """Dois usuários, cada um com um cliente e um serviço de 45 min."""
    with app.app_context():
        ids: dict[str, int] = {}
        for tag in ("a", "b"):
            user = auth_service.register_user(tag, f"{tag}@x.com", "senha-segura-123")
            customer = customer_service.create_customer(user.id, {"name": f"Cliente {tag}"})
            service = catalog_service.create_service(
                user.id, {"name": "Corte", "duration_minutes": 45, "price": Decimal("50")}
            )
            ids.update({f"user_{tag}": user.id, f"customer_{tag}": customer.id})
            ids.update({f"service_{tag}": service.id})
        return ids


def _create(world: dict[str, int], start, tag: str = "a", **extra):
    data = {
        "customer_id": world[f"customer_{tag}"],
        "service_id": world[f"service_{tag}"],
        "start_at": start,
        **extra,
    }
    return appointment_service.create_appointment(world[f"user_{tag}"], data)


def test_end_is_start_plus_service_duration_in_utc(app: Flask, world: dict[str, int]) -> None:
    with app.app_context():
        start = at(10)
        # o mesmo instante, escrito em outro fuso, deve ser armazenado em UTC
        local = start.astimezone(timezone(timedelta(hours=-3)))
        appointment = _create(world, local)
        assert appointment.start_at == start
        assert appointment.end_at == start + timedelta(minutes=45)
        assert appointment.status == AppointmentStatus.SCHEDULED


@pytest.mark.parametrize("offset", [-44, -30, 0, 15, 44])
def test_overlapping_slots_are_rejected(app: Flask, world: dict[str, int], offset: int) -> None:
    with app.app_context():
        existing = _create(world, at(10))
        with pytest.raises(ConflictError) as exc:
            _create(world, at(10) + timedelta(minutes=offset))
        assert exc.value.code == "APPOINTMENT_CONFLICT"
        assert exc.value.details["conflicting_appointment"]["id"] == existing.id


@pytest.mark.parametrize("offset", [-45, 45, 120])
def test_adjacent_or_distant_slots_are_allowed(
    app: Flask, world: dict[str, int], offset: int
) -> None:
    with app.app_context():
        _create(world, at(10))
        _create(world, at(10) + timedelta(minutes=offset))


def test_long_appointment_covering_an_existing_one_conflicts(
    app: Flask, world: dict[str, int]
) -> None:
    with app.app_context():
        _create(world, at(10))
        long_service = catalog_service.create_service(
            world["user_a"], {"name": "Dia de noiva", "duration_minutes": 180, "price": Decimal(1)}
        )
        with pytest.raises(ConflictError):
            appointment_service.create_appointment(
                world["user_a"],
                {
                    "customer_id": world["customer_a"],
                    "service_id": long_service.id,
                    "start_at": at(9),
                },
            )


def test_canceled_appointment_frees_the_slot(app: Flask, world: dict[str, int]) -> None:
    with app.app_context():
        first = _create(world, at(10))
        appointment_service.cancel_appointment(world["user_a"], first.id)
        _create(world, at(10))  # não levanta


def test_same_slot_is_free_for_another_user(app: Flask, world: dict[str, int]) -> None:
    with app.app_context():
        _create(world, at(10), tag="a")
        _create(world, at(10), tag="b")


def test_cannot_book_in_the_past(app: Flask, world: dict[str, int]) -> None:
    with app.app_context():
        with pytest.raises(UnprocessableError) as exc:
            _create(world, at(10, days=-1))
        assert exc.value.code == "START_IN_THE_PAST"


def test_cannot_book_inactive_service(app: Flask, world: dict[str, int]) -> None:
    with app.app_context():
        catalog_service.update_service(world["user_a"], world["service_a"], {"active": False})
        with pytest.raises(UnprocessableError) as exc:
            _create(world, at(10))
        assert exc.value.code == "SERVICE_INACTIVE"


def test_cannot_use_customer_or_service_of_another_user(app: Flask, world: dict[str, int]) -> None:
    with app.app_context():
        with pytest.raises(NotFoundError) as exc:
            appointment_service.create_appointment(
                world["user_a"],
                {
                    "customer_id": world["customer_b"],
                    "service_id": world["service_a"],
                    "start_at": at(10),
                },
            )
        assert exc.value.code == "CUSTOMER_NOT_FOUND"
        with pytest.raises(NotFoundError) as exc:
            appointment_service.create_appointment(
                world["user_a"],
                {
                    "customer_id": world["customer_a"],
                    "service_id": world["service_b"],
                    "start_at": at(10),
                },
            )
        assert exc.value.code == "SERVICE_NOT_FOUND"


def test_database_constraint_catches_race_when_service_check_is_bypassed(
    app: Flask, world: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simula a corrida: a checagem do service não vê o conflito, mas o banco bloqueia."""
    with app.app_context():
        _create(world, at(10))
        monkeypatch.setattr(appointment_service, "find_conflict", lambda *a, **k: None)
        with pytest.raises(ConflictError) as exc:
            _create(world, at(10, 15))
        assert exc.value.code == "APPOINTMENT_CONFLICT"
        # a sessão continua utilizável depois do rollback
        assert db.session.query(Appointment).count() == 1


def test_update_can_shift_within_own_slot_but_not_into_another(
    app: Flask, world: dict[str, int]
) -> None:
    with app.app_context():
        first = _create(world, at(10))
        _create(world, at(11))
        moved = appointment_service.update_appointment(
            world["user_a"], first.id, {"start_at": at(10, 15)}
        )
        assert moved.end_at == at(10, 15) + timedelta(minutes=45)
        with pytest.raises(ConflictError):
            appointment_service.update_appointment(
                world["user_a"], first.id, {"start_at": at(10, 30)}
            )


def test_only_scheduled_appointments_are_editable(app: Flask, world: dict[str, int]) -> None:
    with app.app_context():
        appointment = _create(world, at(10))
        appointment_service.cancel_appointment(world["user_a"], appointment.id)
        with pytest.raises(ConflictError) as exc:
            appointment_service.update_appointment(world["user_a"], appointment.id, {"notes": "x"})
        assert exc.value.code == "APPOINTMENT_NOT_EDITABLE"


def test_status_transitions(
    app: Flask, world: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    with app.app_context():
        user = world["user_a"]
        done = _create(world, at(9))
        monkeypatch.setattr(appointment_service, "_now", lambda: at(9) + timedelta(minutes=5))
        assert appointment_service.complete_appointment(user, done.id).status == "completed"

        for action in (
            appointment_service.cancel_appointment,
            appointment_service.complete_appointment,
        ):
            with pytest.raises(ConflictError) as exc:
                action(user, done.id)
            assert exc.value.code == "INVALID_STATUS_TRANSITION"


def test_cannot_complete_before_start(app: Flask, world: dict[str, int]) -> None:
    with app.app_context():
        appointment = _create(world, at(10))
        with pytest.raises(ConflictError) as exc:
            appointment_service.complete_appointment(world["user_a"], appointment.id)
        assert exc.value.code == "APPOINTMENT_NOT_STARTED"
        db.session.refresh(appointment)
        assert appointment.status == AppointmentStatus.SCHEDULED  # nada foi alterado


def test_completed_appointment_cannot_be_deleted(
    app: Flask, world: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    with app.app_context():
        appointment = _create(world, at(9))
        monkeypatch.setattr(appointment_service, "_now", lambda: at(9) + timedelta(minutes=5))
        appointment_service.complete_appointment(world["user_a"], appointment.id)
        with pytest.raises(ConflictError) as exc:
            appointment_service.delete_appointment(world["user_a"], appointment.id)
        assert exc.value.code == "APPOINTMENT_COMPLETED"
