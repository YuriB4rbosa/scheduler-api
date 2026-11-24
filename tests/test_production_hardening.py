"""Endurecimento para produção: segredos fortes e IP real atrás de proxy."""

import pytest
from flask import request

from app import create_app
from app.config import ProductionConfig, TestingConfig
from app.extensions import limiter

STRONG_A = "a" * 20 + "B" * 20 + "1234"
STRONG_B = "z" * 20 + "Y" * 20 + "9876"


def _production(**overrides: object) -> type[ProductionConfig]:
    attrs = {
        "SQLALCHEMY_DATABASE_URI": TestingConfig.SQLALCHEMY_DATABASE_URI,
        "SECRET_KEY": STRONG_A,
        "JWT_SECRET_KEY": STRONG_B,
        **overrides,
    }
    return type("Prod", (ProductionConfig,), attrs)


def test_production_starts_with_strong_distinct_secrets() -> None:
    assert create_app(_production()).config["ENV_NAME"] == "production"


@pytest.mark.parametrize(
    "overrides",
    [
        {"SECRET_KEY": "change-me"},
        {"JWT_SECRET_KEY": "change-me-too"},
        {"SECRET_KEY": "dev-only-secret-key-not-for-production-0123456789"},
        {"SECRET_KEY": "curta"},
        {"JWT_SECRET_KEY": STRONG_A},  # igual à SECRET_KEY
    ],
)
def test_production_rejects_weak_or_example_secrets(overrides: dict[str, str]) -> None:
    with pytest.raises(RuntimeError, match="SECRET_KEY|diferentes") as exc:
        create_app(_production(**overrides))
    # a mensagem orienta, mas nunca revela o valor configurado
    for value in overrides.values():
        assert value not in str(exc.value)


def test_weak_secrets_are_still_fine_outside_production() -> None:
    class Dev(TestingConfig):
        SECRET_KEY = "change-me"  # noqa: S105
        JWT_SECRET_KEY = "change-me-too"  # noqa: S105

    create_app(Dev)  # não levanta


def _remote_addr_app(proxies: int):
    config = type("Proxied", (TestingConfig,), {"TRUSTED_PROXY_COUNT": proxies})
    app = create_app(config)

    @app.get("/whoami")
    def whoami() -> dict[str, str]:
        return {"ip": request.remote_addr, "scheme": request.scheme}

    return app.test_client()


def test_forwarded_headers_are_ignored_without_a_trusted_proxy() -> None:
    client = _remote_addr_app(0)
    body = client.get("/whoami", headers={"X-Forwarded-For": "9.9.9.9"}).get_json()
    assert body["ip"] == "127.0.0.1"  # não dá para forjar o IP


def test_forwarded_headers_are_used_behind_one_trusted_proxy() -> None:
    client = _remote_addr_app(1)
    headers = {"X-Forwarded-For": "9.9.9.9", "X-Forwarded-Proto": "https"}
    body = client.get("/whoami", headers=headers).get_json()
    assert body == {"ip": "9.9.9.9", "scheme": "https"}


def test_only_the_last_proxy_hop_is_trusted() -> None:
    """Um cliente que injeta o próprio X-Forwarded-For não escolhe o IP que vale."""
    client = _remote_addr_app(1)
    body = client.get("/whoami", headers={"X-Forwarded-For": "1.2.3.4, 9.9.9.9"}).get_json()
    assert body["ip"] == "9.9.9.9"


def test_production_defaults_to_one_trusted_proxy() -> None:
    assert ProductionConfig.TRUSTED_PROXY_COUNT == 1
    assert TestingConfig.TRUSTED_PROXY_COUNT == 0


def test_rate_limit_is_per_real_client_ip_behind_a_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    class Limited(TestingConfig):
        RATELIMIT_ENABLED = True
        AUTH_RATE_LIMIT = "2 per minute"
        TRUSTED_PROXY_COUNT = 1

    monkeypatch.setattr(limiter, "enabled", False)  # o limiter é global: restaura no teardown
    client = create_app(Limited).test_client()
    body = {"email": "x@salao.com", "password": "senha-segura-123"}

    def login(ip: str) -> int:
        return client.post(
            "/api/v1/auth/login", json=body, headers={"X-Forwarded-For": ip}
        ).status_code

    assert [login("10.0.0.1"), login("10.0.0.1"), login("10.0.0.1")] == [401, 401, 429]
    assert login("10.0.0.2") == 401  # outro cliente real não é afetado


def test_no_environment_enables_flask_debug_through_config() -> None:
    """DEBUG=True na config valeria também sob o gunicorn (depure com `flask run --debug`)."""
    from app.config import CONFIGS

    assert [name for name, cfg in CONFIGS.items() if getattr(cfg, "DEBUG", False)] == []
