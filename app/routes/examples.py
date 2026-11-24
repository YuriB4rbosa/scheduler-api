"""Exemplos de requisição/resposta exibidos no Swagger (``/docs``)."""

from typing import Any


def error(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


# ---------- autenticação ----------

REGISTER_REQUEST = {"name": "Ana Souza", "email": "ana@salao.com", "password": "senha-segura-123"}
REGISTER_RESPONSE = {
    "id": 1,
    "name": "Ana Souza",
    "email": "ana@salao.com",
    "created_at": "2030-01-02T12:00:00+00:00",
}
EMAIL_TAKEN = error("EMAIL_ALREADY_REGISTERED", "Email already registered.")

LOGIN_REQUEST = {"email": "ana@salao.com", "password": "senha-segura-123"}
LOGIN_RESPONSE = {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.assinatura",
    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwidHlwZSI6InJl.assinatura",
    "token_type": "Bearer",
}
INVALID_CREDENTIALS = error("INVALID_CREDENTIALS", "Invalid email or password.")

# ---------- agendamentos ----------

APPOINTMENT_REQUEST = {
    "customer_id": 1,
    "service_id": 2,
    "start_at": "2030-01-10T09:00:00-03:00",
    "notes": "Cliente prefere atendimento com a Ana.",
}
APPOINTMENT_RESPONSE = {
    "id": 17,
    "customer_id": 1,
    "service_id": 2,
    "customer": {"id": 1, "name": "Maria Oliveira"},
    "service": {"id": 2, "name": "Corte masculino", "duration_minutes": 30, "price": "50.00"},
    "start_at": "2030-01-10T12:00:00+00:00",
    "end_at": "2030-01-10T12:30:00+00:00",
    "status": "scheduled",
    "notes": "Cliente prefere atendimento com a Ana.",
    "created_at": "2030-01-02T12:00:00+00:00",
    "updated_at": "2030-01-02T12:00:00+00:00",
}
APPOINTMENT_CONFLICT = error(
    "APPOINTMENT_CONFLICT",
    "This time slot overlaps with another scheduled appointment.",
    {
        "conflicting_appointment": {
            "id": 12,
            "start_at": "2030-01-10T12:15:00+00:00",
            "end_at": "2030-01-10T13:00:00+00:00",
        }
    },
)
APPOINTMENT_PAST = error("START_IN_THE_PAST", "Appointments cannot be scheduled in the past.")
INVALID_TRANSITION = error(
    "INVALID_STATUS_TRANSITION",
    "Cannot change status from 'canceled' to 'completed'.",
    {"current_status": "canceled", "requested_status": "completed"},
)

# ---------- erros comuns ----------

VALIDATION_ERROR = error(
    "VALIDATION_ERROR",
    "Validation failed. Check 'details' for the invalid fields.",
    {"json": {"start_at": ["Not a valid aware datetime."], "service_id": ["Missing data."]}},
)
NOT_FOUND = error("APPOINTMENT_NOT_FOUND", "Appointment not found.")
UNAUTHORIZED = error("MISSING_TOKEN", "Authentication token is missing.")
