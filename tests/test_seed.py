"""Testes do comando ``flask seed`` e do serviço de dados de demonstração."""

from datetime import UTC, datetime

import pytest
from flask import Flask
from sqlalchemy import func, select

from app import create_app
from app.config import ProductionConfig, TestingConfig
from app.extensions import db
from app.models import Appointment, AppointmentStatus, Customer, Service, User
from app.services import seed_service
from app.services.seed_service import DEMO_EMAIL, SeedError

PASSWORD = "senha-de-teste-123"


def _count(model: type) -> int:
    return db.session.scalar(select(func.count()).select_from(model))


def test_seed_creates_a_realistic_agenda(app: Flask) -> None:
    with app.app_context():
        counts = seed_service.seed_demo(PASSWORD)

        assert counts["customers"] == _count(Customer) == 8
        assert counts["services"] == _count(Service) == 8
        assert counts["appointments"] == _count(Appointment) > 20

        statuses = set(db.session.scalars(select(Appointment.status)))
        assert statuses == {s.value for s in AppointmentStatus}  # os três estados aparecem

        now = datetime.now(UTC)
        past = db.session.scalars(select(Appointment).where(Appointment.start_at < now)).all()
        future = db.session.scalars(select(Appointment).where(Appointment.start_at > now)).all()
        assert past
        assert future
        assert {a.status for a in past} <= {"completed", "canceled"}
        assert {a.status for a in future} <= {"scheduled", "canceled"}


def test_seed_agenda_has_no_overlapping_active_appointments(app: Flask) -> None:
    """A própria constraint do banco já impediria o insert; aqui conferimos explicitamente."""
    with app.app_context():
        seed_service.seed_demo(PASSWORD)
        active = db.session.scalars(
            select(Appointment)
            .where(Appointment.status == AppointmentStatus.SCHEDULED)
            .order_by(Appointment.start_at)
        ).all()
        for current, following in zip(active, active[1:], strict=False):
            assert current.end_at <= following.start_at


def test_seed_is_deterministic(app: Flask) -> None:
    now = datetime(2030, 6, 5, 15, 0, tzinfo=UTC)

    def snapshot() -> list[tuple]:
        rows = db.session.scalars(select(Appointment).order_by(Appointment.start_at))
        return [(a.start_at, a.status, a.customer.name, a.service.name, a.notes) for a in rows]

    with app.app_context():
        seed_service.seed_demo(PASSWORD, now=now)
        first = snapshot()
        seed_service.seed_demo(PASSWORD, reset=True, now=now)
        assert snapshot() == first


def test_seed_refuses_to_run_twice_without_reset(app: Flask) -> None:
    with app.app_context():
        seed_service.seed_demo(PASSWORD)
        with pytest.raises(SeedError, match="--reset"):
            seed_service.seed_demo(PASSWORD)
        assert _count(User) == 1


def test_seed_reset_recreates_data_without_leftovers(app: Flask) -> None:
    with app.app_context():
        seed_service.seed_demo(PASSWORD)
        seed_service.seed_demo(PASSWORD, reset=True)
        assert _count(User) == 1
        assert _count(Customer) == 8
        assert _count(Service) == 8


def test_demo_user_can_log_in_through_the_api(app: Flask) -> None:
    with app.app_context():
        seed_service.seed_demo(PASSWORD)
    client = app.test_client()
    response = client.post("/api/v1/auth/login", json={"email": DEMO_EMAIL, "password": PASSWORD})
    assert response.status_code == 200
    headers = {"Authorization": f"Bearer {response.get_json()['access_token']}"}
    assert client.get("/api/v1/appointments?per_page=100", headers=headers).get_json()["total"] > 20


def test_password_resolution_rules() -> None:
    assert seed_service.resolve_password("production", "da-env") == "da-env"
    assert seed_service.resolve_password("development", None) == seed_service.DEV_DEFAULT_PASSWORD
    for env_name in ("testing", "production"):
        with pytest.raises(SeedError, match="SEED_DEMO_PASSWORD"):
            seed_service.resolve_password(env_name, None)


# ---------- CLI ----------


def test_cli_seed_runs_and_reports(app: Flask, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEED_DEMO_PASSWORD", PASSWORD)
    result = app.test_cli_runner().invoke(args=["seed"])
    assert result.exit_code == 0, result.output
    assert "8 clientes" in result.output
    assert DEMO_EMAIL in result.output
    assert PASSWORD not in result.output  # a senha nunca é impressa

    again = app.test_cli_runner().invoke(args=["seed"])
    assert again.exit_code == 1
    assert "--reset" in again.output
    assert app.test_cli_runner().invoke(args=["seed", "--reset"]).exit_code == 0


def test_cli_seed_requires_password_outside_development(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SEED_DEMO_PASSWORD", raising=False)
    result = app.test_cli_runner().invoke(args=["seed"])
    assert result.exit_code == 1
    assert "SEED_DEMO_PASSWORD" in result.output
    with app.app_context():
        assert _count(User) == 0


def test_cli_seed_is_blocked_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    class Production(ProductionConfig):
        SQLALCHEMY_DATABASE_URI = TestingConfig.SQLALCHEMY_DATABASE_URI
        SECRET_KEY = "k1-" + "a" * 40  # noqa: S105
        JWT_SECRET_KEY = "k2-" + "b" * 40  # noqa: S105

    monkeypatch.setenv("SEED_DEMO_PASSWORD", PASSWORD)  # mesmo com senha definida, bloqueia
    result = create_app(Production).test_cli_runner().invoke(args=["seed"])
    assert result.exit_code == 1
    assert "produção" in result.output
    with create_app(TestingConfig).app_context():
        assert _count(User) == 0


def test_agenda_never_runs_past_the_end_of_the_business_day() -> None:
    """Serviços longos demais para caber no expediente não geram agendamento."""
    customers = [Customer(id=1, user_id=1, name="Cliente")]
    too_long = [
        Service(id=1, user_id=1, name="Maratona", duration_minutes=600, price=1, active=True)
    ]
    now = datetime(2030, 6, 5, 15, 0, tzinfo=UTC)

    assert seed_service._build_agenda(1, customers, too_long, now) == []

    fits = [Service(id=1, user_id=1, name="Rápido", duration_minutes=30, price=1, active=True)]
    agenda = seed_service._build_agenda(1, customers, fits, now)
    assert agenda
    assert all(a.end_at.hour < 21 or (a.end_at.hour == 21 and a.end_at.minute == 0) for a in agenda)
