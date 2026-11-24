"""Application factory."""

from flask import Flask

from app.config import Config, get_config
from app.extensions import db, jwt, migrate


def create_app(config: type[Config] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config or get_config())

    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        raise RuntimeError("Variável de banco não definida. Veja o .env.example.")
    for key in ("SECRET_KEY", "JWT_SECRET_KEY"):
        if not app.config.get(key):
            raise RuntimeError(f"{key} não definida. Veja o .env.example.")

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    from app import models  # noqa: F401  (registra as tabelas para o Alembic)

    return app
