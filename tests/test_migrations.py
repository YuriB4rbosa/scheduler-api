"""As migrations precisam gerar o mesmo schema que os models descrevem.

Os demais testes montam o banco com ``create_all``; sem este teste, uma migration esquecida,
incompleta ou errada só seria descoberta em produção.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask import Flask
from flask_migrate import downgrade, upgrade
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app import create_app
from app.config import TestingConfig
from app.extensions import db

SCRATCH_DB = "scheduler_migrations_check"
MIGRATIONS_DIR = str(Path(__file__).resolve().parent.parent / "migrations")


@pytest.fixture
def migrated_app() -> Iterator[Flask]:
    """App apontando para um banco descartável, criado e removido só para este teste."""
    base = make_url(TestingConfig.SQLALCHEMY_DATABASE_URI)
    scratch = base.set(database=SCRATCH_DB)

    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{SCRATCH_DB}"'))

    config = type(
        "ScratchConfig",
        (TestingConfig,),
        {"SQLALCHEMY_DATABASE_URI": scratch.render_as_string(hide_password=False)},
    )
    app = create_app(config)
    try:
        yield app
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        admin.dispose()


def test_migrations_match_models_and_are_reversible(migrated_app: Flask) -> None:
    with migrated_app.app_context():
        upgrade(directory=MIGRATIONS_DIR)

        with db.engine.connect() as conn:
            diffs = compare_metadata(MigrationContext.configure(conn), db.metadata)
        assert diffs == [], f"Models e migrations divergem: {diffs}"

        # a regra de sobreposição precisa existir no banco migrado (autogenerate não a compara)
        with db.engine.connect() as conn:
            constraint = conn.execute(
                text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = :n"),
                {"n": "ex_appointments_no_overlap"},
            ).scalar_one()
        assert "EXCLUDE USING gist" in constraint
        assert "tstzrange" in constraint
        assert "scheduled" in constraint

        downgrade(directory=MIGRATIONS_DIR, revision="base")
        remaining = set(inspect(db.engine).get_table_names()) - {"alembic_version"}
        assert remaining == set()

        upgrade(directory=MIGRATIONS_DIR)  # e volta a subir sem erro
        assert "appointments" in inspect(db.engine).get_table_names()
