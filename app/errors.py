"""Exceções de domínio.

Os services levantam estas exceções (sem conhecer HTTP); a camada web as traduz para o
formato de erro padronizado em ``app/error_handlers.py``.
"""

from typing import Any


class AppError(Exception):
    status_code = 500
    default_code = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
        self.details = details or {}


class BadRequestError(AppError):
    status_code = 400
    default_code = "BAD_REQUEST"


class UnauthorizedError(AppError):
    status_code = 401
    default_code = "UNAUTHORIZED"


class ForbiddenError(AppError):
    status_code = 403
    default_code = "FORBIDDEN"


class NotFoundError(AppError):
    status_code = 404
    default_code = "NOT_FOUND"


class UnprocessableError(AppError):
    """Entrada sintaticamente válida, mas que viola uma regra de negócio."""

    status_code = 422
    default_code = "UNPROCESSABLE"


class ConflictError(AppError):
    status_code = 409
    default_code = "CONFLICT"
