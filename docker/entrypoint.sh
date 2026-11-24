#!/bin/sh
# Aplica as migrations e inicia o servidor. Roda a cada start do container.
set -e

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    echo "Aplicando migrations..."
    flask db upgrade
fi

echo "Iniciando a API na porta ${PORT:-8000}..."
exec gunicorn wsgi:app \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-2}" \
    --timeout 30 \
    --access-logfile -
