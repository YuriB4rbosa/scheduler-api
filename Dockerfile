# syntax=docker/dockerfile:1

# ---- Estágio 1: instala as dependências em um venv isolado ----
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
COPY requirements.txt .
RUN /opt/venv/bin/pip install -r requirements.txt


# ---- Estágio 2: imagem final, enxuta e sem privilégios de root ----
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    FLASK_APP=wsgi:app \
    APP_ENV=production \
    PORT=8000

RUN useradd --system --create-home --uid 10001 app
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app app ./app
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app wsgi.py ./
COPY --chown=app:app docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER app
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT', '8000'), timeout=3)"

ENTRYPOINT ["/entrypoint.sh"]
