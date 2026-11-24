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


_API_DESCRIPTION = """API REST de agendamento para pequenos negócios (salões, clínicas, oficinas).

**Como testar aqui no Swagger**
1. `POST /api/v1/auth/register` para criar sua conta (ou use o usuário de demonstração do `flask seed`).
2. `POST /api/v1/auth/login` e copie o `access_token`.
3. Clique em **Authorize** e cole o token (sem a palavra `Bearer`).

**Convenções**
- Datas em ISO 8601. Na entrada o fuso é obrigatório (`2030-01-10T09:00:00-03:00`); na saída tudo vem em UTC.
- Erros seguem sempre o formato `{"error": {"code", "message", "details"}}`.
- Recursos de outro usuário respondem `404`, como se não existissem.
"""  # noqa: E501


class Config:
    ENV_NAME = "development"

    SQLALCHEMY_DATABASE_URI = _database_url("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Quantos proxies reversos confiáveis existem na frente da app (0 = nenhum). Define se
    # X-Forwarded-For/Proto/Host são respeitados; sem isso o rate limit veria o IP do proxy.
    TRUSTED_PROXY_COUNT = int(os.environ.get("TRUSTED_PROXY_COUNT", 0))

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
    API_SPEC_OPTIONS = {
        "info": {"description": _API_DESCRIPTION},
        "servers": [{"url": "/", "description": "Servidor atual"}],
    }


class DevelopmentConfig(Config):
    # Sem DEBUG=True de propósito: sob o gunicorn ele ligaria o modo debug do Flask.
    # Para depurar localmente use `flask run --debug`.
    ENV_NAME = "development"


class TestingConfig(Config):
    ENV_NAME = "testing"
    TESTING = True
    RATELIMIT_ENABLED = False
    SQLALCHEMY_DATABASE_URI = _database_url("TEST_DATABASE_URL")
    SECRET_KEY = "test-secret-key"  # noqa: S105 - apenas para testes
    JWT_SECRET_KEY = "test-jwt-secret-key-with-at-least-32-bytes"  # noqa: S105


class ProductionConfig(Config):
    ENV_NAME = "production"
    DEBUG = False
    # Render/Railway colocam exatamente um proxy na frente da aplicação.
    TRUSTED_PROXY_COUNT = int(os.environ.get("TRUSTED_PROXY_COUNT", 1))


CONFIGS: dict[str, type[Config]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None) -> type[Config]:
    return CONFIGS[name or os.environ.get("APP_ENV", "development")]
