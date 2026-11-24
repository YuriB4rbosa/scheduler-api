from collections.abc import Iterator

import pytest
from flask import Flask
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
