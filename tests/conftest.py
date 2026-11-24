from collections.abc import Callable, Iterator
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import text

from app import create_app
from app.config import TestingConfig
from app.extensions import db


@pytest.fixture(scope="session")
def app() -> Iterator[Flask]:
    """App de teste apontando para o banco separado (TEST_DATABASE_URL)."""
    app = create_app(TestingConfig)
    with app.app_context():
        db.session.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
        db.session.commit()
        db.drop_all()
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture(autouse=True)
def _clean_db(app: Flask) -> Iterator[None]:
    """Isola os testes: limpa todas as tabelas depois de cada um."""
    yield
    with app.app_context():
        db.session.remove()
        tables = ", ".join(f'"{t.name}"' for t in db.metadata.sorted_tables)
        db.session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        db.session.commit()


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


@pytest.fixture
def make_user(client: FlaskClient) -> Callable[..., tuple[dict[str, Any], dict[str, str]]]:
    """Cadastra um usuário e devolve (user_json, headers com o access token)."""

    def _make(
        email: str = "ana@salao.com", password: str = "senha-segura-123", name: str = "Ana"
    ) -> tuple[dict[str, Any], dict[str, str]]:
        user = client.post(
            "/api/v1/auth/register", json={"name": name, "email": email, "password": password}
        ).get_json()
        tokens = client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        ).get_json()
        return user, {"Authorization": f"Bearer {tokens['access_token']}"}

    return _make
