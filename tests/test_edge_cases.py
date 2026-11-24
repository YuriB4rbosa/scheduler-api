"""Caminhos de erro e de corrida que os testes de fluxo normal não alcançam."""

from datetime import timedelta
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.config import ProductionConfig, TestingConfig, _database_url, get_config
from app.errors import ConflictError
from app.extensions import db
from app.models import Appointment
from app.services import auth_service, catalog_service, customer_service
from tests.helpers import APPOINTMENTS, at, book, make_customer, make_service

# ---------- configuração ----------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("postgres://u:p@h/db", "postgresql+psycopg://u:p@h/db"),  # Render/Heroku
        ("postgresql://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
    ],
)
def test_database_url_is_normalized_for_psycopg3(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: str
) -> None:
    monkeypatch.setenv("SOME_DB_URL", raw)
    assert _database_url("SOME_DB_URL") == expected


def test_get_config_selects_by_name_or_app_env(monkeypatch: pytest.MonkeyPatch) -> None:
    assert get_config("testing") is TestingConfig
    monkeypatch.setenv("APP_ENV", "production")
    assert get_config() is ProductionConfig
    assert ProductionConfig.DEBUG is False


def test_database_url_missing_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOME_DB_URL", raising=False)
    assert _database_url("SOME_DB_URL") is None


def test_app_refuses_to_start_without_database_url() -> None:
    class NoDatabase(TestingConfig):
        SQLALCHEMY_DATABASE_URI = None

    with pytest.raises(RuntimeError, match="banco"):
        create_app(NoDatabase)


@pytest.mark.parametrize("key", ["SECRET_KEY", "JWT_SECRET_KEY"])
def test_app_refuses_to_start_without_secrets(key: str) -> None:
    config = type("NoSecret", (TestingConfig,), {key: None})
    with pytest.raises(RuntimeError, match=key):
        create_app(config)


def test_unexpected_errors_return_standard_500_without_leaking_details() -> None:
    app = create_app(TestingConfig)

    @app.get("/boom")
    def boom() -> None:
        raise ValueError("segredo interno: senha=hunter2")

    response = app.test_client().get("/boom")
    assert response.status_code == 500
    error = response.get_json()["error"]
    assert error["code"] == "INTERNAL_ERROR"
    assert "hunter2" not in response.get_data(as_text=True)


# ---------- corridas: a constraint do banco decide quando a checagem prévia falha ----------


def test_register_race_on_same_email_returns_409(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    with app.app_context():
        auth_service.register_user("Ana", "ana@x.com", "senha-segura-123")
        monkeypatch.setattr(auth_service, "get_user_by_email", lambda email: None)
        with pytest.raises(ConflictError) as exc:
            auth_service.register_user("Ana 2", "ana@x.com", "senha-segura-123")
        assert exc.value.code == "EMAIL_ALREADY_REGISTERED"


def test_customer_race_on_same_email_returns_409(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    with app.app_context():
        user = auth_service.register_user("Ana", "ana@x.com", "senha-segura-123")
        customer_service.create_customer(user.id, {"name": "Maria", "email": "m@x.com"})
        monkeypatch.setattr(customer_service, "_ensure_email_available", lambda *a, **k: None)
        with pytest.raises(ConflictError) as exc:
            customer_service.create_customer(user.id, {"name": "Maria 2", "email": "m@x.com"})
        assert exc.value.code == "CUSTOMER_EMAIL_EXISTS"
        # a sessão segue utilizável depois do rollback
        assert customer_service.list_customers(user.id).total == 1


def test_unrelated_integrity_errors_are_not_disguised_as_conflicts(app: Flask) -> None:
    """Só a violação da constraint de sobreposição vira 409; o resto precisa aparecer."""
    from app.services.appointment_service import _commit_or_conflict

    with app.app_context():
        user = auth_service.register_user("Ana", "ana@x.com", "senha-segura-123")
        start = at(10)
        db.session.add(
            Appointment(
                user_id=user.id,
                customer_id=9999,  # FK inexistente
                service_id=9999,
                start_at=start,
                end_at=start + timedelta(minutes=30),
            )
        )
        with pytest.raises(IntegrityError):
            _commit_or_conflict()


# ---------- lacunas de fluxo ----------


def test_service_name_is_trimmed_on_update(app: Flask) -> None:
    with app.app_context():
        user = auth_service.register_user("Ana", "ana@x.com", "senha-segura-123")
        service = catalog_service.create_service(
            user.id, {"name": "Corte", "duration_minutes": 30, "price": 10}
        )
        updated = catalog_service.update_service(user.id, service.id, {"name": "  Escova  "})
        assert updated.name == "Escova"


def test_patch_notes_on_active_appointment(client: FlaskClient, make_user: Any) -> None:
    _, headers = make_user()
    customer, service = make_customer(client, headers), make_service(client, headers)
    created = book(client, headers, customer, service, at(10)).get_json()
    url = f"{APPOINTMENTS}/{created['id']}"

    body = client.patch(
        url, json={"notes": "Trazer foto de referência"}, headers=headers
    ).get_json()
    assert body["notes"] == "Trazer foto de referência"
    assert body["start_at"] == created["start_at"]  # horário intacto

    cleared = client.patch(url, json={"notes": None}, headers=headers).get_json()
    assert cleared["notes"] is None


def test_patch_with_same_values_is_idempotent_and_not_a_self_conflict(
    client: FlaskClient, make_user: Any
) -> None:
    _, headers = make_user()
    customer, service = make_customer(client, headers), make_service(client, headers)
    created = book(client, headers, customer, service, at(10)).get_json()
    payload = {"start_at": created["start_at"], "service_id": service["id"]}
    response = client.patch(f"{APPOINTMENTS}/{created['id']}", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.get_json()["end_at"] == created["end_at"]
