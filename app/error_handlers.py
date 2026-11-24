"""Formato de erro padronizado para toda a API.

{"error": {"code": "NOT_FOUND", "message": "...", "details": {...}}}
"""

from typing import Any

from flask import Flask, Response, jsonify
from werkzeug.exceptions import HTTPException

from app.errors import AppError
from app.extensions import jwt

_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
}


def error_response(
    status: int, code: str, message: str, details: dict[str, Any] | None = None
) -> tuple[Response, int]:
    body = {"error": {"code": code, "message": message, "details": details or {}}}
    return jsonify(body), status


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(AppError)
    def handle_app_error(exc: AppError) -> tuple[Response, int]:
        return error_response(exc.status_code, exc.code, exc.message, exc.details)

    # Registrado depois do flask-smorest, então substitui o handler padrão dele.
    @app.errorhandler(HTTPException)
    def handle_http_exception(exc: HTTPException) -> tuple[Response, int]:
        status = exc.code or 500
        code = _CODES.get(status, "HTTP_ERROR")
        details: dict[str, Any] = {}
        message = exc.description or exc.name
        if status == 422:
            # webargs/smorest anexa {"messages": {"json": {"campo": ["erro"]}}}
            data = getattr(exc, "data", None) or {}
            details = data.get("messages", {})
            message = "Validation failed. Check 'details' for the invalid fields."
        return error_response(status, code, message, details)

    @app.errorhandler(Exception)
    def handle_unexpected(exc: Exception) -> tuple[Response, int]:
        app.logger.exception("Unhandled exception", exc_info=exc)
        return error_response(500, "INTERNAL_ERROR", "Internal server error.")

    # Erros do JWT precisam do mesmo formato (por padrão a extensão devolve outro).
    @jwt.unauthorized_loader
    def missing_token(reason: str) -> tuple[Response, int]:
        return error_response(401, "MISSING_TOKEN", "Authentication token is missing.")

    @jwt.invalid_token_loader
    def invalid_token(reason: str) -> tuple[Response, int]:
        return error_response(401, "INVALID_TOKEN", "Authentication token is invalid.")

    @jwt.expired_token_loader
    def expired_token(header: dict, payload: dict) -> tuple[Response, int]:
        return error_response(401, "TOKEN_EXPIRED", "Authentication token has expired.")
