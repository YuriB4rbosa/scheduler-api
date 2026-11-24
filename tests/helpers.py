"""Helpers compartilhados pelos testes de agendamento."""

from datetime import UTC, datetime, timedelta
from typing import Any

from flask.testing import FlaskClient

APPOINTMENTS = "/api/v1/appointments"


def at(hour: int, minute: int = 0, days: int = 7) -> datetime:
    """Instante futuro (UTC) estável: ``days`` dias à frente, no horário pedido."""
    base = datetime.now(UTC) + timedelta(days=days)
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)


def iso(value: datetime) -> str:
    return value.isoformat()


def make_customer(client: FlaskClient, headers: dict[str, str], **extra: Any) -> dict[str, Any]:
    response = client.post(
        "/api/v1/customers", json={"name": "Maria Oliveira", **extra}, headers=headers
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def make_service(client: FlaskClient, headers: dict[str, str], **extra: Any) -> dict[str, Any]:
    payload = {"name": "Corte", "duration_minutes": 45, "price": "60.00", **extra}
    response = client.post("/api/v1/services", json=payload, headers=headers)
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def book(
    client: FlaskClient,
    headers: dict[str, str],
    customer: dict[str, Any],
    service: dict[str, Any],
    start: datetime,
    **extra: Any,
) -> Any:
    """POST /appointments e devolve a resposta crua (o teste decide o que esperar)."""
    payload = {
        "customer_id": customer["id"],
        "service_id": service["id"],
        "start_at": iso(start),
        **extra,
    }
    return client.post(APPOINTMENTS, json=payload, headers=headers)


def assert_error(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.get_json()
    error = response.get_json()["error"]
    assert error["code"] == code
    return error
