"""Testes de integração dos endpoints de autenticação."""

from datetime import timedelta
from typing import Any

import jwt as pyjwt
import pytest
from flask import Flask
from flask.testing import FlaskClient
from flask_jwt_extended import create_access_token, create_refresh_token

from app import create_app
from app.config import TestingConfig
from app.extensions import limiter

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
ME = "/api/v1/auth/me"
PAYLOAD = {"name": "Ana Souza", "email": "ana@salao.com", "password": "senha-segura-123"}


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _assert_error(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status
    error = response.get_json()["error"]
    assert error["code"] == code
    assert error["message"]
    assert isinstance(error["details"], dict)
    return error


def test_register_returns_201_without_password(client: FlaskClient) -> None:
    response = client.post(REGISTER, json=PAYLOAD)
    assert response.status_code == 201
    body = response.get_json()
    assert body["email"] == "ana@salao.com"
    assert body["id"] == 1
    assert "password" not in body
    assert "password_hash" not in body


def test_register_duplicate_email_returns_409(client: FlaskClient) -> None:
    client.post(REGISTER, json=PAYLOAD)
    _assert_error(client.post(REGISTER, json=PAYLOAD), 409, "EMAIL_ALREADY_REGISTERED")


def test_register_invalid_payload_returns_422_with_field_details(client: FlaskClient) -> None:
    response = client.post(REGISTER, json={"name": "", "email": "nao-e-email", "password": "123"})
    error = _assert_error(response, 422, "VALIDATION_ERROR")
    assert {"name", "email", "password"} <= set(error["details"]["json"])


def test_register_rejects_unknown_fields(client: FlaskClient) -> None:
    response = client.post(REGISTER, json={**PAYLOAD, "is_admin": True})
    error = _assert_error(response, 422, "VALIDATION_ERROR")
    assert "is_admin" in error["details"]["json"]


def test_login_returns_token_pair(client: FlaskClient) -> None:
    client.post(REGISTER, json=PAYLOAD)
    response = client.post(LOGIN, json={"email": "ana@salao.com", "password": "senha-segura-123"})
    assert response.status_code == 200
    body = response.get_json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "Bearer"


def test_login_wrong_password_returns_401(client: FlaskClient) -> None:
    client.post(REGISTER, json=PAYLOAD)
    response = client.post(LOGIN, json={"email": "ana@salao.com", "password": "errada-errada"})
    _assert_error(response, 401, "INVALID_CREDENTIALS")


def test_login_unknown_email_returns_401(client: FlaskClient) -> None:
    response = client.post(LOGIN, json={"email": "x@salao.com", "password": "senha-segura-123"})
    _assert_error(response, 401, "INVALID_CREDENTIALS")


def test_me_returns_authenticated_user(client: FlaskClient, make_user: Any) -> None:
    user, headers = make_user()
    response = client.get(ME, headers=headers)
    assert response.status_code == 200
    assert response.get_json()["id"] == user["id"]


def test_me_without_token_returns_401(client: FlaskClient) -> None:
    _assert_error(client.get(ME), 401, "MISSING_TOKEN")


def test_me_with_malformed_token_returns_401(client: FlaskClient) -> None:
    response = client.get(ME, headers=_bearer("isto.nao.e-um-jwt"))
    _assert_error(response, 401, "INVALID_TOKEN")


def test_me_with_token_signed_by_another_key_returns_401(client: FlaskClient) -> None:
    forged = pyjwt.encode(
        {"sub": "1", "type": "access", "fresh": False, "jti": "x", "iat": 0, "exp": 9999999999},
        "chave-falsa-chave-falsa-chave-falsa-chave-falsa",
        algorithm="HS256",
    )
    _assert_error(client.get(ME, headers=_bearer(forged)), 401, "INVALID_TOKEN")


def test_me_with_expired_token_returns_401(app: Flask, client: FlaskClient) -> None:
    with app.app_context():
        token = create_access_token(identity="1", expires_delta=timedelta(seconds=-1))
    _assert_error(client.get(ME, headers=_bearer(token)), 401, "TOKEN_EXPIRED")


def test_me_with_token_of_deleted_user_returns_401(app: Flask, client: FlaskClient) -> None:
    with app.app_context():
        token = create_access_token(identity="999")
    _assert_error(client.get(ME, headers=_bearer(token)), 401, "INVALID_TOKEN")


def test_refresh_token_cannot_access_protected_routes(app: Flask, client: FlaskClient) -> None:
    with app.app_context():
        token = create_refresh_token(identity="1")
    _assert_error(client.get(ME, headers=_bearer(token)), 401, "INVALID_TOKEN")


def test_refresh_issues_new_access_token(client: FlaskClient) -> None:
    client.post(REGISTER, json=PAYLOAD)
    tokens = client.post(
        LOGIN, json={"email": "ana@salao.com", "password": "senha-segura-123"}
    ).get_json()

    response = client.post(REFRESH, headers=_bearer(tokens["refresh_token"]))
    assert response.status_code == 200
    new_access = response.get_json()["access_token"]
    assert client.get(ME, headers=_bearer(new_access)).status_code == 200


def test_access_token_cannot_be_used_to_refresh(client: FlaskClient, make_user: Any) -> None:
    _, headers = make_user()
    _assert_error(client.post(REFRESH, headers=headers), 401, "INVALID_TOKEN")


def test_unknown_route_uses_standard_error_format(client: FlaskClient) -> None:
    _assert_error(client.get("/api/v1/nope"), 404, "NOT_FOUND")


def test_wrong_method_uses_standard_error_format(client: FlaskClient) -> None:
    _assert_error(client.get(REGISTER), 405, "METHOD_NOT_ALLOWED")


class _RateLimitedConfig(TestingConfig):
    RATELIMIT_ENABLED = True
    AUTH_RATE_LIMIT = "3 per minute"


def test_login_is_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    # O limiter é global: ao criar um app com ele ligado, garantimos o desligamento no teardown.
    monkeypatch.setattr(limiter, "enabled", False)
    client = create_app(_RateLimitedConfig).test_client()

    body = {"email": "x@salao.com", "password": "senha-segura-123"}
    statuses = [client.post(LOGIN, json=body).status_code for _ in range(4)]
    assert statuses == [401, 401, 401, 429]
    _assert_error(client.post(LOGIN, json=body), 429, "RATE_LIMITED")


def test_health_and_openapi_docs(client: FlaskClient) -> None:
    assert client.get("/health").get_json() == {"status": "ok", "database": "ok"}
    spec = client.get("/openapi.json").get_json()
    assert "/api/v1/auth/login" in spec["paths"]
    assert "bearerAuth" in spec["components"]["securitySchemes"]
    assert client.get("/docs").status_code == 200
