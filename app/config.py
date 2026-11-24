"""Configuração da aplicação. Todos os segredos vêm de variáveis de ambiente."""

import os
from datetime import timedelta

from dotenv import load_dotenv

# Precisa rodar antes de as classes abaixo lerem os.environ.
load_dotenv()


def _database_url(name: str) -> str | None:
    """Lê a URL do banco e normaliza o prefixo (Render/Railway usam ``postgres://``)."""
    url = os.environ.get(name)
    if url is None:
        return None
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


class Config:
    SQLALCHEMY_DATABASE_URI = _database_url("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SECRET_KEY = os.environ.get("SECRET_KEY")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        minutes=int(os.environ.get("JWT_ACCESS_TOKEN_MINUTES", 15))
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=int(os.environ.get("JWT_REFRESH_TOKEN_DAYS", 7)))

    # Limite de tentativas em login/cadastro (mitiga força bruta). O armazenamento em memória
    # é por processo; com vários workers use Redis (ex.: redis://...).
    AUTH_RATE_LIMIT = os.environ.get("AUTH_RATE_LIMIT", "10 per minute")
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")

    # flask-smorest / OpenAPI
    API_TITLE = "Scheduler API"
    API_VERSION = "v1"
    OPENAPI_VERSION = "3.0.3"
    OPENAPI_URL_PREFIX = "/"
    OPENAPI_SWAGGER_UI_PATH = "/docs"
    OPENAPI_SWAGGER_UI_URL = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    RATELIMIT_ENABLED = False
    SQLALCHEMY_DATABASE_URI = _database_url("TEST_DATABASE_URL")
    SECRET_KEY = "test-secret-key"  # noqa: S105 - apenas para testes
    JWT_SECRET_KEY = "test-jwt-secret-key-with-at-least-32-bytes"  # noqa: S105


class ProductionConfig(Config):
    DEBUG = False


CONFIGS: dict[str, type[Config]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None) -> type[Config]:
    return CONFIGS[name or os.environ.get("APP_ENV", "development")]
