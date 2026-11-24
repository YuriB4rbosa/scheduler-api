"""Testes de integração de /api/v1/customers."""

from typing import Any

import pytest
from flask.testing import FlaskClient

URL = "/api/v1/customers"
MARIA = {"name": "Maria Oliveira", "phone": "+55 11 98888-7777", "email": "maria@email.com"}


def _create(client: FlaskClient, headers: dict[str, str], **data: Any) -> dict[str, Any]:
    response = client.post(URL, json={**MARIA, **data}, headers=headers)
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def _error(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.get_json()
    error = response.get_json()["error"]
    assert error["code"] == code
    return error


def test_create_returns_201_and_hides_owner(client: FlaskClient, make_user: Any) -> None:
    _, headers = make_user()
    body = _create(client, headers)
    assert body["id"] == 1
    assert body["name"] == "Maria Oliveira"
    assert body["created_at"]
    assert "user_id" not in body


def test_create_ignores_no_client_supplied_owner(client: FlaskClient, make_user: Any) -> None:
    _, headers = make_user()
    response = client.post(URL, json={**MARIA, "user_id": 99}, headers=headers)
    assert _error(response, 422, "VALIDATION_ERROR")["details"]["json"]["user_id"]


def test_create_validation_errors(client: FlaskClient, make_user: Any) -> None:
    _, headers = make_user()
    response = client.post(
        URL, json={"name": "  ", "email": "ruim", "phone": "abc"}, headers=headers
    )
    fields = _error(response, 422, "VALIDATION_ERROR")["details"]["json"]
    assert {"name", "email", "phone"} <= set(fields)


def test_duplicate_email_returns_409_but_other_user_may_reuse(
    client: FlaskClient, make_user: Any
) -> None:
    _, headers = make_user()
    _, other_headers = make_user("bia@salao.com")
    _create(client, headers)
    _error(client.post(URL, json=MARIA, headers=headers), 409, "CUSTOMER_EMAIL_EXISTS")
    assert client.post(URL, json=MARIA, headers=other_headers).status_code == 201


def test_list_paginates_with_envelope(client: FlaskClient, make_user: Any) -> None:
    _, headers = make_user()
    for i in range(25):
        _create(client, headers, name=f"Cliente {i:02d}", email=f"c{i}@x.com")

    body = client.get(f"{URL}?per_page=10&page=3", headers=headers).get_json()
    assert (body["page"], body["per_page"], body["total"], body["pages"]) == (3, 10, 25, 3)
    assert [c["name"] for c in body["items"]][0] == "Cliente 20"
    assert len(body["items"]) == 5


def test_list_search_and_sort(client: FlaskClient, make_user: Any) -> None:
    _, headers = make_user()
    for name in ("Bruno", "Ana Maria", "Carla Maria"):
        _create(client, headers, name=name, email=f"{name[:3].lower()}@x.com")

    found = client.get(f"{URL}?q=maria&sort=name&order=desc", headers=headers).get_json()
    assert [c["name"] for c in found["items"]] == ["Carla Maria", "Ana Maria"]
    by_email = client.get(f"{URL}?q=BRU@", headers=headers).get_json()
    assert by_email["total"] == 1


@pytest.mark.parametrize(
    "query",
    ["page=0", "per_page=101", "per_page=0", "sort=password", "order=sideways", "foo=bar"],
)
def test_list_rejects_invalid_query_params(client: FlaskClient, make_user: Any, query: str) -> None:
    _, headers = make_user()
    _error(client.get(f"{URL}?{query}", headers=headers), 422, "VALIDATION_ERROR")


def test_get_and_patch_and_delete_flow(client: FlaskClient, make_user: Any) -> None:
    _, headers = make_user()
    created = _create(client, headers)
    url = f"{URL}/{created['id']}"

    assert client.get(url, headers=headers).get_json()["email"] == "maria@email.com"

    patched = client.patch(url, json={"phone": None}, headers=headers).get_json()
    assert patched["phone"] is None
    assert patched["name"] == "Maria Oliveira"  # campos não enviados ficam intactos

    assert client.delete(url, headers=headers).status_code == 204
    _error(client.get(url, headers=headers), 404, "CUSTOMER_NOT_FOUND")


def test_patch_rejects_empty_body_and_duplicate_email(client: FlaskClient, make_user: Any) -> None:
    _, headers = make_user()
    first = _create(client, headers)
    _create(client, headers, name="Outro", email="outro@x.com")
    url = f"{URL}/{first['id']}"
    _error(client.patch(url, json={}, headers=headers), 422, "VALIDATION_ERROR")
    _error(
        client.patch(url, json={"email": "outro@x.com"}, headers=headers),
        409,
        "CUSTOMER_EMAIL_EXISTS",
    )


def test_missing_customer_returns_404(client: FlaskClient, make_user: Any) -> None:
    _, headers = make_user()
    _error(client.get(f"{URL}/999", headers=headers), 404, "CUSTOMER_NOT_FOUND")


def test_other_users_customer_is_404_for_every_operation(
    client: FlaskClient, make_user: Any
) -> None:
    _, owner = make_user()
    _, intruder = make_user("intruso@x.com")
    url = f"{URL}/{_create(client, owner)['id']}"

    _error(client.get(url, headers=intruder), 404, "CUSTOMER_NOT_FOUND")
    _error(client.patch(url, json={"name": "Hack"}, headers=intruder), 404, "CUSTOMER_NOT_FOUND")
    _error(client.delete(url, headers=intruder), 404, "CUSTOMER_NOT_FOUND")
    assert client.get(URL, headers=intruder).get_json()["total"] == 0
    # e o dono segue com o dado intacto
    assert client.get(url, headers=owner).get_json()["name"] == "Maria Oliveira"


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", ""), ("post", ""), ("get", "/1"), ("patch", "/1"), ("delete", "/1")],
)
def test_every_route_requires_authentication(client: FlaskClient, method: str, path: str) -> None:
    _error(getattr(client, method)(URL + path), 401, "MISSING_TOKEN")
    response = getattr(client, method)(URL + path, headers={"Authorization": "Bearer lixo"})
    _error(response, 401, "INVALID_TOKEN")


def test_cannot_delete_customer_with_appointments(
    client: FlaskClient, make_user: Any, app: Any
) -> None:
    from datetime import UTC, datetime, timedelta

    from app.extensions import db
    from app.models import Appointment, Service

    user, headers = make_user()
    customer = _create(client, headers)
    with app.app_context():
        service = Service(user_id=user["id"], name="Corte", duration_minutes=30, price=50)
        db.session.add(service)
        db.session.flush()
        start = datetime(2030, 1, 1, 9, tzinfo=UTC)
        db.session.add(
            Appointment(
                user_id=user["id"],
                customer_id=customer["id"],
                service_id=service.id,
                start_at=start,
                end_at=start + timedelta(minutes=30),
            )
        )
        db.session.commit()

    _error(
        client.delete(f"{URL}/{customer['id']}", headers=headers), 409, "CUSTOMER_HAS_APPOINTMENTS"
    )
