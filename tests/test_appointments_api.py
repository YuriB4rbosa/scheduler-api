"""Testes de integração de /api/v1/appointments."""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app.extensions import db
from app.models import Appointment
from app.services import appointment_service
from tests.helpers import APPOINTMENTS, assert_error, at, book, iso, make_customer, make_service


@pytest.fixture
def setup(client: FlaskClient, make_user: Any) -> dict[str, Any]:
    """Usuário com um cliente e um serviço de 45 minutos."""
    user, headers = make_user()
    return {
        "user": user,
        "headers": headers,
        "customer": make_customer(client, headers),
        "service": make_service(client, headers),
    }


def _book(client: FlaskClient, s: dict[str, Any], start: datetime, **extra: Any) -> Any:
    return book(client, s["headers"], s["customer"], s["service"], start, **extra)


def _frozen_at(monkeypatch: pytest.MonkeyPatch, moment: datetime) -> None:
    monkeypatch.setattr(appointment_service, "_now", lambda: moment)


# ---------- criação ----------


def test_create_returns_201_with_computed_end_and_summaries(
    client: FlaskClient, setup: dict[str, Any]
) -> None:
    start = at(10)
    response = _book(client, setup, start, notes="Prefere a Ana")
    assert response.status_code == 201, response.get_json()
    body = response.get_json()
    assert body["status"] == "scheduled"
    assert datetime.fromisoformat(body["start_at"]) == start
    assert datetime.fromisoformat(body["end_at"]) == start + timedelta(minutes=45)
    assert body["customer"] == {"id": setup["customer"]["id"], "name": "Maria Oliveira"}
    assert body["service"]["duration_minutes"] == 45
    assert body["notes"] == "Prefere a Ana"
    assert "user_id" not in body


def test_create_accepts_other_timezones_and_returns_utc(
    client: FlaskClient, setup: dict[str, Any]
) -> None:
    start = at(10)
    local = start.astimezone(timezone(timedelta(hours=-3)))
    assert "-03:00" in iso(local)
    body = _book(client, setup, local).get_json()
    assert body["start_at"].endswith("+00:00")
    assert datetime.fromisoformat(body["start_at"]) == start


def test_create_rejects_datetime_without_timezone(
    client: FlaskClient, setup: dict[str, Any]
) -> None:
    naive = at(10).replace(tzinfo=None)
    response = client.post(
        APPOINTMENTS,
        json={
            "customer_id": setup["customer"]["id"],
            "service_id": setup["service"]["id"],
            "start_at": naive.isoformat(),
        },
        headers=setup["headers"],
    )
    error = assert_error(response, 422, "VALIDATION_ERROR")
    assert "start_at" in error["details"]["json"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"customer_id": "x", "service_id": 1, "start_at": "2030-01-01T10:00:00Z"},
        {"customer_id": 1, "service_id": 1, "start_at": "amanha"},
        {"customer_id": 1, "service_id": 1, "start_at": "2030-01-01T10:00:00Z", "notes": "x" * 501},
        {
            "customer_id": 1,
            "service_id": 1,
            "start_at": "2030-01-01T10:00:00Z",
            "status": "completed",
        },
        {"customer_id": 1, "service_id": 1, "start_at": "2030-01-01T10:00:00Z", "end_at": "x"},
    ],
)
def test_create_validation_errors(
    client: FlaskClient, setup: dict[str, Any], payload: dict
) -> None:
    response = client.post(APPOINTMENTS, json=payload, headers=setup["headers"])
    assert_error(response, 422, "VALIDATION_ERROR")


def test_create_in_the_past_returns_422(client: FlaskClient, setup: dict[str, Any]) -> None:
    assert_error(_book(client, setup, at(10, days=-1)), 422, "START_IN_THE_PAST")


def test_create_with_inactive_service_returns_422(
    client: FlaskClient, setup: dict[str, Any]
) -> None:
    service_url = f"/api/v1/services/{setup['service']['id']}"
    client.patch(service_url, json={"active": False}, headers=setup["headers"])
    assert_error(_book(client, setup, at(10)), 422, "SERVICE_INACTIVE")


def test_create_with_unknown_customer_or_service_returns_404(
    client: FlaskClient, setup: dict[str, Any]
) -> None:
    headers = setup["headers"]
    ok = {"start_at": iso(at(10))}
    r = client.post(APPOINTMENTS, json={**ok, "customer_id": 999, "service_id": 1}, headers=headers)
    assert_error(r, 404, "CUSTOMER_NOT_FOUND")
    r = client.post(
        APPOINTMENTS,
        json={**ok, "customer_id": setup["customer"]["id"], "service_id": 999},
        headers=headers,
    )
    assert_error(r, 404, "SERVICE_NOT_FOUND")


def test_cannot_book_with_customer_or_service_of_another_user(
    client: FlaskClient, setup: dict[str, Any], make_user: Any
) -> None:
    _, other_headers = make_user("outra@x.com")
    foreign_customer = make_customer(client, other_headers)
    foreign_service = make_service(client, other_headers)
    mine = {"customer": setup["customer"], "service": setup["service"], "headers": setup["headers"]}

    r = book(client, mine["headers"], foreign_customer, mine["service"], at(10))
    assert_error(r, 404, "CUSTOMER_NOT_FOUND")
    r = book(client, mine["headers"], mine["customer"], foreign_service, at(10))
    assert_error(r, 404, "SERVICE_NOT_FOUND")


# ---------- conflito de horário ----------


@pytest.mark.parametrize("offset", [-44, -20, 0, 15, 44])
def test_overlapping_booking_returns_409_with_conflict_details(
    client: FlaskClient, setup: dict[str, Any], offset: int
) -> None:
    existing = _book(client, setup, at(10)).get_json()
    response = _book(client, setup, at(10) + timedelta(minutes=offset))
    error = assert_error(response, 409, "APPOINTMENT_CONFLICT")
    assert error["details"]["conflicting_appointment"]["id"] == existing["id"]
    assert error["details"]["conflicting_appointment"]["start_at"] == existing["start_at"]


@pytest.mark.parametrize("offset", [-45, 45])
def test_back_to_back_bookings_are_allowed(
    client: FlaskClient, setup: dict[str, Any], offset: int
) -> None:
    assert _book(client, setup, at(10)).status_code == 201
    assert _book(client, setup, at(10) + timedelta(minutes=offset)).status_code == 201


def test_canceled_slot_can_be_rebooked(client: FlaskClient, setup: dict[str, Any]) -> None:
    first = _book(client, setup, at(10)).get_json()
    client.post(f"{APPOINTMENTS}/{first['id']}/cancel", headers=setup["headers"])
    assert _book(client, setup, at(10)).status_code == 201


def test_same_slot_is_allowed_for_different_users(
    client: FlaskClient, setup: dict[str, Any], make_user: Any
) -> None:
    _, other_headers = make_user("outra@x.com")
    other = {
        "headers": other_headers,
        "customer": make_customer(client, other_headers),
        "service": make_service(client, other_headers),
    }
    assert _book(client, setup, at(10)).status_code == 201
    assert _book(client, other, at(10)).status_code == 201


def test_concurrent_requests_cannot_double_book(app: Flask, setup: dict[str, Any]) -> None:
    barrier = threading.Barrier(2)
    start = at(10)

    def attempt(_: int) -> int:
        client = app.test_client()
        barrier.wait()
        return _book(client, setup, start).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(attempt, range(2)))

    assert statuses == [201, 409]
    with app.app_context():
        assert db.session.query(Appointment).count() == 1


# ---------- listagem ----------


def _seed_agenda(client: FlaskClient, setup: dict[str, Any]) -> dict[str, Any]:
    other_customer = make_customer(client, setup["headers"], name="João")
    other_service = make_service(client, setup["headers"], name="Barba", duration_minutes=20)
    ids = {
        "a": _book(client, setup, at(9)).get_json()["id"],
        "b": _book(client, setup, at(11)).get_json()["id"],
        "c": book(client, setup["headers"], other_customer, setup["service"], at(13)).get_json()[
            "id"
        ],
        "d": book(client, setup["headers"], setup["customer"], other_service, at(15)).get_json()[
            "id"
        ],
        "other_customer": other_customer["id"],
        "other_service": other_service["id"],
    }
    client.post(f"{APPOINTMENTS}/{ids['b']}/cancel", headers=setup["headers"])
    return ids


def _ids(client: FlaskClient, setup: dict[str, Any], query: str = "") -> list[int]:
    response = client.get(f"{APPOINTMENTS}?{query}", headers=setup["headers"])
    assert response.status_code == 200, response.get_json()
    return [a["id"] for a in response.get_json()["items"]]


def test_list_defaults_to_chronological_order(client: FlaskClient, setup: dict[str, Any]) -> None:
    ids = _seed_agenda(client, setup)
    assert _ids(client, setup) == [ids["a"], ids["b"], ids["c"], ids["d"]]
    assert _ids(client, setup, "order=desc") == [ids["d"], ids["c"], ids["b"], ids["a"]]


def test_list_filters(client: FlaskClient, setup: dict[str, Any]) -> None:
    ids = _seed_agenda(client, setup)
    assert _ids(client, setup, "status=canceled") == [ids["b"]]
    assert _ids(client, setup, "status=scheduled") == [ids["a"], ids["c"], ids["d"]]
    assert _ids(client, setup, f"customer_id={ids['other_customer']}") == [ids["c"]]
    assert _ids(client, setup, f"service_id={ids['other_service']}") == [ids["d"]]


def test_list_date_range_is_half_open(client: FlaskClient, setup: dict[str, Any]) -> None:
    ids = _seed_agenda(client, setup)
    window = (
        f"date_from={iso(at(11)).replace('+', '%2B')}&date_to={iso(at(15)).replace('+', '%2B')}"
    )
    # inclui o início exato de 11h, exclui o início exato de 15h
    assert _ids(client, setup, window) == [ids["b"], ids["c"]]


def test_list_paginates(client: FlaskClient, setup: dict[str, Any]) -> None:
    _seed_agenda(client, setup)
    body = client.get(f"{APPOINTMENTS}?per_page=3&page=2", headers=setup["headers"]).get_json()
    assert (body["page"], body["per_page"], body["total"], body["pages"]) == (2, 3, 4, 2)
    assert len(body["items"]) == 1


@pytest.mark.parametrize(
    "query",
    [
        "status=pendente",
        "sort=user_id",
        "customer_id=abc",
        "date_from=ontem",
        "date_from=2030-01-02T00:00:00Z&date_to=2030-01-01T00:00:00Z",
        "date_from=2030-01-01T00:00:00",  # sem fuso
        "foo=bar",
    ],
)
def test_list_rejects_invalid_params(
    client: FlaskClient, setup: dict[str, Any], query: str
) -> None:
    response = client.get(f"{APPOINTMENTS}?{query}", headers=setup["headers"])
    assert_error(response, 422, "VALIDATION_ERROR")


def test_list_uses_constant_number_of_queries(
    app: Flask, client: FlaskClient, setup: dict[str, Any]
) -> None:
    """Cliente e serviço vêm por JOIN: o custo não cresce com o tamanho da página (sem N+1)."""
    from sqlalchemy import event

    for hour in range(8, 18):
        assert _book(client, setup, at(hour, days=hour)).status_code == 201

    statements: list[str] = []

    def count(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        statements.append(statement)

    with app.app_context():
        event.listen(db.engine, "before_cursor_execute", count)
        try:
            response = client.get(f"{APPOINTMENTS}?per_page=10", headers=setup["headers"])
        finally:
            event.remove(db.engine, "before_cursor_execute", count)

    assert len(response.get_json()["items"]) == 10
    assert len(statements) <= 3  # contagem + página (+ eventual verificação de usuário)


# ---------- detalhe, edição e remoção ----------


def test_get_returns_the_appointment(client: FlaskClient, setup: dict[str, Any]) -> None:
    created = _book(client, setup, at(10)).get_json()
    body = client.get(f"{APPOINTMENTS}/{created['id']}", headers=setup["headers"]).get_json()
    assert body == created


def test_get_missing_returns_404(client: FlaskClient, setup: dict[str, Any]) -> None:
    response = client.get(f"{APPOINTMENTS}/999", headers=setup["headers"])
    assert_error(response, 404, "APPOINTMENT_NOT_FOUND")


def test_patch_reschedules_and_recomputes_end(client: FlaskClient, setup: dict[str, Any]) -> None:
    created = _book(client, setup, at(10)).get_json()
    url = f"{APPOINTMENTS}/{created['id']}"
    body = client.patch(url, json={"start_at": iso(at(14))}, headers=setup["headers"]).get_json()
    assert datetime.fromisoformat(body["start_at"]) == at(14)
    assert datetime.fromisoformat(body["end_at"]) == at(14) + timedelta(minutes=45)
    assert body["notes"] is None


def test_patch_changing_service_recomputes_end(client: FlaskClient, setup: dict[str, Any]) -> None:
    created = _book(client, setup, at(10)).get_json()
    short = make_service(client, setup["headers"], name="Barba", duration_minutes=15)
    body = client.patch(
        f"{APPOINTMENTS}/{created['id']}",
        json={"service_id": short["id"]},
        headers=setup["headers"],
    ).get_json()
    assert datetime.fromisoformat(body["end_at"]) == at(10) + timedelta(minutes=15)
    assert body["service"]["name"] == "Barba"


def test_patch_into_conflict_returns_409_and_keeps_original(
    client: FlaskClient, setup: dict[str, Any]
) -> None:
    first = _book(client, setup, at(10)).get_json()
    _book(client, setup, at(11))
    url = f"{APPOINTMENTS}/{first['id']}"
    response = client.patch(url, json={"start_at": iso(at(11, 20))}, headers=setup["headers"])
    assert_error(response, 409, "APPOINTMENT_CONFLICT")
    assert client.get(url, headers=setup["headers"]).get_json()["start_at"] == first["start_at"]


def test_patch_longer_service_that_would_collide_returns_409(
    client: FlaskClient, setup: dict[str, Any]
) -> None:
    first = _book(client, setup, at(10)).get_json()
    _book(client, setup, at(11))  # começa 1h depois
    long = make_service(client, setup["headers"], name="Coloração", duration_minutes=120)
    response = client.patch(
        f"{APPOINTMENTS}/{first['id']}", json={"service_id": long["id"]}, headers=setup["headers"]
    )
    assert_error(response, 409, "APPOINTMENT_CONFLICT")


def test_patch_validation_rules(client: FlaskClient, setup: dict[str, Any]) -> None:
    created = _book(client, setup, at(10)).get_json()
    url = f"{APPOINTMENTS}/{created['id']}"
    h = setup["headers"]
    assert_error(client.patch(url, json={}, headers=h), 422, "VALIDATION_ERROR")
    assert_error(
        client.patch(url, json={"status": "completed"}, headers=h), 422, "VALIDATION_ERROR"
    )
    assert_error(
        client.patch(url, json={"start_at": iso(at(10, days=-2))}, headers=h),
        422,
        "START_IN_THE_PAST",
    )
    assert_error(client.patch(url, json={"customer_id": 999}, headers=h), 404, "CUSTOMER_NOT_FOUND")


def test_patch_canceled_appointment_returns_409(client: FlaskClient, setup: dict[str, Any]) -> None:
    created = _book(client, setup, at(10)).get_json()
    url = f"{APPOINTMENTS}/{created['id']}"
    client.post(f"{url}/cancel", headers=setup["headers"])
    response = client.patch(url, json={"notes": "x"}, headers=setup["headers"])
    assert_error(response, 409, "APPOINTMENT_NOT_EDITABLE")


def test_delete_scheduled_and_canceled(client: FlaskClient, setup: dict[str, Any]) -> None:
    a = _book(client, setup, at(10)).get_json()["id"]
    b = _book(client, setup, at(12)).get_json()["id"]
    client.post(f"{APPOINTMENTS}/{b}/cancel", headers=setup["headers"])
    for appointment_id in (a, b):
        url = f"{APPOINTMENTS}/{appointment_id}"
        assert client.delete(url, headers=setup["headers"]).status_code == 204
        assert_error(client.get(url, headers=setup["headers"]), 404, "APPOINTMENT_NOT_FOUND")


def test_customer_and_service_with_appointments_cannot_be_deleted(
    client: FlaskClient, setup: dict[str, Any]
) -> None:
    _book(client, setup, at(10))
    h = setup["headers"]
    r = client.delete(f"/api/v1/customers/{setup['customer']['id']}", headers=h)
    assert_error(r, 409, "CUSTOMER_HAS_APPOINTMENTS")
    r = client.delete(f"/api/v1/services/{setup['service']['id']}", headers=h)
    assert_error(r, 409, "SERVICE_HAS_APPOINTMENTS")


# ---------- status ----------


def test_cancel_then_cancel_again_returns_409(client: FlaskClient, setup: dict[str, Any]) -> None:
    created = _book(client, setup, at(10)).get_json()
    url = f"{APPOINTMENTS}/{created['id']}/cancel"
    assert client.post(url, headers=setup["headers"]).get_json()["status"] == "canceled"
    error = assert_error(
        client.post(url, headers=setup["headers"]), 409, "INVALID_STATUS_TRANSITION"
    )
    assert error["details"] == {"current_status": "canceled", "requested_status": "canceled"}


def test_complete_before_start_returns_409(client: FlaskClient, setup: dict[str, Any]) -> None:
    created = _book(client, setup, at(10)).get_json()
    response = client.post(f"{APPOINTMENTS}/{created['id']}/complete", headers=setup["headers"])
    assert_error(response, 409, "APPOINTMENT_NOT_STARTED")


def test_complete_after_start_then_it_is_immutable(
    client: FlaskClient, setup: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _book(client, setup, at(10)).get_json()
    url = f"{APPOINTMENTS}/{created['id']}"
    h = setup["headers"]
    _frozen_at(monkeypatch, at(10) + timedelta(minutes=50))

    assert client.post(f"{url}/complete", headers=h).get_json()["status"] == "completed"
    assert_error(client.post(f"{url}/cancel", headers=h), 409, "INVALID_STATUS_TRANSITION")
    assert_error(client.post(f"{url}/complete", headers=h), 409, "INVALID_STATUS_TRANSITION")
    assert_error(client.patch(url, json={"notes": "x"}, headers=h), 409, "APPOINTMENT_NOT_EDITABLE")
    assert_error(client.delete(url, headers=h), 409, "APPOINTMENT_COMPLETED")


def test_complete_canceled_appointment_returns_409(
    client: FlaskClient, setup: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _book(client, setup, at(10)).get_json()
    url = f"{APPOINTMENTS}/{created['id']}"
    client.post(f"{url}/cancel", headers=setup["headers"])
    _frozen_at(monkeypatch, datetime.now(UTC) + timedelta(days=30))
    assert_error(
        client.post(f"{url}/complete", headers=setup["headers"]), 409, "INVALID_STATUS_TRANSITION"
    )


# ---------- isolamento e autenticação ----------


def test_other_users_appointment_is_404_for_every_operation(
    client: FlaskClient, setup: dict[str, Any], make_user: Any
) -> None:
    _, intruder = make_user("intruso@x.com")
    created = _book(client, setup, at(10)).get_json()
    url = f"{APPOINTMENTS}/{created['id']}"

    code = "APPOINTMENT_NOT_FOUND"
    assert_error(client.get(url, headers=intruder), 404, code)
    assert_error(client.patch(url, json={"notes": "x"}, headers=intruder), 404, code)
    assert_error(client.delete(url, headers=intruder), 404, code)
    assert_error(client.post(f"{url}/cancel", headers=intruder), 404, code)
    assert_error(client.post(f"{url}/complete", headers=intruder), 404, code)
    assert client.get(APPOINTMENTS, headers=intruder).get_json()["total"] == 0
    # nada foi alterado para o dono
    assert client.get(url, headers=setup["headers"]).get_json()["status"] == "scheduled"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", ""),
        ("post", ""),
        ("get", "/1"),
        ("patch", "/1"),
        ("delete", "/1"),
        ("post", "/1/cancel"),
        ("post", "/1/complete"),
    ],
)
def test_every_route_requires_authentication(client: FlaskClient, method: str, path: str) -> None:
    assert_error(getattr(client, method)(APPOINTMENTS + path), 401, "MISSING_TOKEN")
    response = getattr(client, method)(
        APPOINTMENTS + path, headers={"Authorization": "Bearer token.invalido.aqui"}
    )
    assert_error(response, 401, "INVALID_TOKEN")


def test_openapi_documents_appointment_endpoints(client: FlaskClient) -> None:
    spec = client.get("/openapi.json").get_json()
    assert "/api/v1/appointments/{appointment_id}/cancel" in spec["paths"]
    create = spec["paths"]["/api/v1/appointments"]["post"]
    assert {"201", "401", "404", "409", "422"} <= set(create["responses"])
    assert create["security"] == [{"bearerAuth": []}]
