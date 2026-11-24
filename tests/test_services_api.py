"""Testes de integração de /api/v1/services."""

from typing import Any

import pytest
from flask.testing import FlaskClient

URL = "/api/v1/services"
CORTE = {"name": "Corte de cabelo", "duration_minutes": 45, "price": "60.00"}


def _create(client: FlaskClient, headers: dict[str, str], **data: Any) -> dict[str, Any]:
    response = client.post(URL, json={**CORTE, **data}, headers=headers)
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def _error(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.get_json()
    error = response.get_json()["error"]
    assert error["code"] == code
    return error


def test_create_returns_201_with_decimal_price_as_string(
    client: FlaskClient, make_user: Any
) -> None:
    _, headers = make_user()
    body = _create(client, headers, price=59.9)
    assert body["price"] == "59.90"
    assert body["active"] is True
    assert body["duration_minutes"] == 45
    assert "user_id" not in body


@pytest.mark.parametrize(
    ("payload", "bad_fields"),
    [
        ({"name": "", "duration_minutes": 30, "price": "10"}, {"name"}),
        ({"name": "X", "duration_minutes": 0, "price": "10"}, {"duration_minutes"}),
        ({"name": "X", "duration_minutes": 1441, "price": "10"}, {"duration_minutes"}),
        ({"name": "X", "duration_minutes": 30, "price": "-1"}, {"price"}),
        ({"name": "X", "duration_minutes": 30, "price": "abc"}, {"price"}),
        ({"name": "X", "duration_minutes": 30, "price": "999999999"}, {"price"}),
        ({}, {"name", "duration_minutes", "price"}),
    ],
)
def test_create_validation_errors(
    client: FlaskClient, make_user: Any, payload: dict[str, Any], bad_fields: set[str]
) -> None:
    _, headers = make_user()
    response = client.post(URL, json=payload, headers=headers)
    fields = _error(response, 422, "VALIDATION_ERROR")["details"]["json"]
    assert bad_fields <= set(fields)


def test_list_filters_and_sorting(client: FlaskClient, make_user: Any) -> None:
    _, headers = make_user()
    _create(client, headers, name="Corte", price="40.00", duration_minutes=30)
    _create(client, headers, name="Coloração", price="150.00", duration_minutes=120)
    _create(client, headers, name="Barba", price="25.00", duration_minutes=20, active=False)

    def names(query: str) -> list[str]:
        items = client.get(f"{URL}?{query}", headers=headers).get_json()["items"]
        return [s["name"] for s in items]

    assert names("sort=price&order=desc") == ["Coloração", "Corte", "Barba"]
    assert names("sort=duration_minutes") == ["Barba", "Corte", "Coloração"]
    assert names("active=true&sort=name") == ["Coloração", "Corte"]
    assert names("active=false") == ["Barba"]
    assert names("min_price=30&max_price=100") == ["Corte"]
    assert names("q=co&sort=name") == ["Coloração", "Corte"]


@pytest.mark.parametrize(
    "query", ["min_price=abc", "sort=user_id", "active=talvez", "per_page=500", "x=1"]
)
def test_list_rejects_invalid_query_params(client: FlaskClient, make_user: Any, query: str) -> None:
    _, headers = make_user()
    _error(client.get(f"{URL}?{query}", headers=headers), 422, "VALIDATION_ERROR")


def test_patch_updates_only_sent_fields(client: FlaskClient, make_user: Any) -> None:
    _, headers = make_user()
    created = _create(client, headers, active=False)
    url = f"{URL}/{created['id']}"

    body = client.patch(url, json={"price": "70.50"}, headers=headers).get_json()
    assert body["price"] == "70.50"
    assert body["name"] == "Corte de cabelo"
    assert body["active"] is False  # o default (True) não pode sobrescrever num PATCH

    _error(client.patch(url, json={}, headers=headers), 422, "VALIDATION_ERROR")


def test_delete_flow(client: FlaskClient, make_user: Any) -> None:
    _, headers = make_user()
    url = f"{URL}/{_create(client, headers)['id']}"
    assert client.delete(url, headers=headers).status_code == 204
    _error(client.get(url, headers=headers), 404, "SERVICE_NOT_FOUND")


def test_other_users_service_is_404_for_every_operation(
    client: FlaskClient, make_user: Any
) -> None:
    _, owner = make_user()
    _, intruder = make_user("intruso@x.com")
    url = f"{URL}/{_create(client, owner)['id']}"

    _error(client.get(url, headers=intruder), 404, "SERVICE_NOT_FOUND")
    _error(client.patch(url, json={"price": "1"}, headers=intruder), 404, "SERVICE_NOT_FOUND")
    _error(client.delete(url, headers=intruder), 404, "SERVICE_NOT_FOUND")
    assert client.get(URL, headers=intruder).get_json()["total"] == 0
    assert client.get(url, headers=owner).get_json()["price"] == "60.00"


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", ""), ("post", ""), ("get", "/1"), ("patch", "/1"), ("delete", "/1")],
)
def test_every_route_requires_authentication(client: FlaskClient, method: str, path: str) -> None:
    _error(getattr(client, method)(URL + path), 401, "MISSING_TOKEN")


def test_openapi_documents_security_and_pagination(client: FlaskClient) -> None:
    spec = client.get("/openapi.json").get_json()
    get_op = spec["paths"]["/api/v1/services"]["get"]
    assert get_op["security"] == [{"bearerAuth": []}]
    params = {p["name"] for p in get_op["parameters"]}
    assert {"page", "per_page", "sort", "order", "q", "active", "min_price", "max_price"} <= params
    assert "401" in get_op["responses"]
    assert "204" in spec["paths"]["/api/v1/services/{service_id}"]["delete"]["responses"]
    assert spec["paths"]["/api/v1/auth/me"]["get"]["security"] == [{"bearerAuth": []}]
