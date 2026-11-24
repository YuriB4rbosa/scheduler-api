"""Application factory."""

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from app.cli import register_cli
from app.config import Config, get_config
from app.error_handlers import register_error_handlers
from app.extensions import api, db, jwt, limiter, migrate
from app.routes import register_blueprints
from app.schemas.common import ErrorResponseSchema

_PLACEHOLDER_PREFIXES = ("change-me", "changeme", "dev-only", "local-demo")
MIN_SECRET_LENGTH = 32


def _reject_weak_secrets(app: Flask) -> None:
    """Em produção, recusa chaves de exemplo ou curtas (o valor nunca é exibido)."""
    for key in ("SECRET_KEY", "JWT_SECRET_KEY"):
        value = app.config[key]
        if len(value) < MIN_SECRET_LENGTH or value.lower().startswith(_PLACEHOLDER_PREFIXES):
            raise RuntimeError(
                f"{key} é fraca ou é um valor de exemplo. Em produção use um segredo aleatório "
                f"com pelo menos {MIN_SECRET_LENGTH} caracteres "
                '(python -c "import secrets; print(secrets.token_hex(32))").'
            )
    if app.config["SECRET_KEY"] == app.config["JWT_SECRET_KEY"]:
        raise RuntimeError("SECRET_KEY e JWT_SECRET_KEY devem ser valores diferentes em produção.")


def create_app(config: type[Config] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config or get_config())

    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        raise RuntimeError("Variável de banco não definida. Veja o .env.example.")
    for key in ("SECRET_KEY", "JWT_SECRET_KEY"):
        if not app.config.get(key):
            raise RuntimeError(f"{key} não definida. Veja o .env.example.")

    if app.config["ENV_NAME"] == "production":
        _reject_weak_secrets(app)

    proxies = app.config["TRUSTED_PROXY_COUNT"]
    if proxies > 0:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxies, x_proto=proxies, x_host=proxies)  # type: ignore[method-assign]

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    limiter.init_app(app)

    api.ERROR_SCHEMA = ErrorResponseSchema
    api.init_app(app)
    api.spec.components.security_scheme(
        "bearerAuth", {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
    )
    register_blueprints(api)
    register_cli(app)
    register_error_handlers(app)  # depois do smorest: substitui o handler de erros dele

    from app import models  # noqa: F401  (registra as tabelas para o Alembic)

    return app
