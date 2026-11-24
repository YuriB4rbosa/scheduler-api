"""Regras de negócio de agendamentos.

Regra central: um usuário não pode ter dois agendamentos ativos (``scheduled``) com horários
sobrepostos. A verificação acontece em duas camadas:

1. ``_ensure_slot_free`` consulta o banco e devolve um 409 explicativo (qual agendamento conflita);
2. a exclusion constraint ``ex_appointments_no_overlap`` garante a regra mesmo quando duas
   requisições simultâneas passam juntas pela etapa 1 (condição de corrida).
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.errors import ConflictError, UnprocessableError
from app.extensions import db
from app.models import Appointment, AppointmentStatus, Service
from app.services import catalog_service, customer_service
from app.services.common import Page, get_owned_or_404, order_by_clause, paginate

LABEL = "Appointment"
OVERLAP_CONSTRAINT = "ex_appointments_no_overlap"

_EAGER = (joinedload(Appointment.customer), joinedload(Appointment.service))

# Máquina de estados: só agendamentos ativos mudam de status, e nunca voltam a "scheduled".
_TRANSITIONS: dict[str, set[str]] = {
    AppointmentStatus.SCHEDULED: {AppointmentStatus.CANCELED, AppointmentStatus.COMPLETED},
    AppointmentStatus.COMPLETED: set(),
    AppointmentStatus.CANCELED: set(),
}


def _now() -> datetime:
    """Relógio isolado em uma função para os testes poderem controlá-lo."""
    return datetime.now(UTC)


def _to_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


def _iso(value: datetime) -> str:
    return _to_utc(value).isoformat()


# ---------- regras de validação ----------


def _ensure_not_in_the_past(start_at: datetime) -> None:
    if start_at < _now():
        raise UnprocessableError(
            "Appointments cannot be scheduled in the past.", code="START_IN_THE_PAST"
        )


def _ensure_service_active(service: Service) -> None:
    if not service.active:
        raise UnprocessableError(
            "This service is inactive and cannot be scheduled.", code="SERVICE_INACTIVE"
        )


def find_conflict(
    user_id: int, start_at: datetime, end_at: datetime, ignore_id: int | None = None
) -> Appointment | None:
    """Agendamento ativo do usuário que se sobrepõe a [start_at, end_at).

    Intervalos são semiabertos: terminar às 10:00 não conflita com começar às 10:00.
    """
    stmt = select(Appointment).where(
        Appointment.user_id == user_id,
        Appointment.status == AppointmentStatus.SCHEDULED,
        Appointment.start_at < end_at,
        Appointment.end_at > start_at,
    )
    if ignore_id is not None:
        stmt = stmt.where(Appointment.id != ignore_id)
    return db.session.scalars(stmt.order_by(Appointment.start_at).limit(1)).first()


def _ensure_slot_free(
    user_id: int, start_at: datetime, end_at: datetime, ignore_id: int | None = None
) -> None:
    conflict = find_conflict(user_id, start_at, end_at, ignore_id)
    if conflict is not None:
        raise ConflictError(
            "This time slot overlaps with another scheduled appointment.",
            code="APPOINTMENT_CONFLICT",
            details={
                "conflicting_appointment": {
                    "id": conflict.id,
                    "start_at": _iso(conflict.start_at),
                    "end_at": _iso(conflict.end_at),
                }
            },
        )


def _commit_or_conflict() -> None:
    """Confirma a transação; a constraint do banco vence a corrida entre requisições."""
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        diag = getattr(exc.orig, "diag", None)
        if getattr(diag, "constraint_name", None) == OVERLAP_CONSTRAINT:
            raise ConflictError(
                "This time slot overlaps with another scheduled appointment.",
                code="APPOINTMENT_CONFLICT",
            ) from None
        raise


# ---------- consultas ----------


def list_appointments(
    user_id: int,
    *,
    status: str | None = None,
    customer_id: int | None = None,
    service_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sort: str = "start_at",
    order: str = "asc",
    page: int = 1,
    per_page: int = 20,
) -> Page[Appointment]:
    stmt = select(Appointment).where(Appointment.user_id == user_id).options(*_EAGER)
    if status:
        stmt = stmt.where(Appointment.status == status)
    if customer_id is not None:
        stmt = stmt.where(Appointment.customer_id == customer_id)
    if service_id is not None:
        stmt = stmt.where(Appointment.service_id == service_id)
    if date_from is not None:
        stmt = stmt.where(Appointment.start_at >= _to_utc(date_from))
    if date_to is not None:
        stmt = stmt.where(Appointment.start_at < _to_utc(date_to))
    stmt = stmt.order_by(*order_by_clause(Appointment, sort, order))
    return paginate(stmt, page=page, per_page=per_page)


def get_appointment(user_id: int, appointment_id: int) -> Appointment:
    return get_owned_or_404(Appointment, appointment_id, user_id, LABEL, options=_EAGER)


# ---------- comandos ----------


def create_appointment(user_id: int, data: dict[str, Any]) -> Appointment:
    start_at = _to_utc(data["start_at"])
    _ensure_not_in_the_past(start_at)

    customer = customer_service.get_customer(user_id, data["customer_id"])
    service = catalog_service.get_service(user_id, data["service_id"])
    _ensure_service_active(service)

    end_at = start_at + timedelta(minutes=service.duration_minutes)
    _ensure_slot_free(user_id, start_at, end_at)

    appointment = Appointment(
        user_id=user_id,
        customer_id=customer.id,
        service_id=service.id,
        start_at=start_at,
        end_at=end_at,
        notes=data.get("notes"),
    )
    db.session.add(appointment)
    _commit_or_conflict()
    return appointment


def update_appointment(user_id: int, appointment_id: int, data: dict[str, Any]) -> Appointment:
    """Reagenda ou altera cliente/serviço/observações de um agendamento ativo."""
    appointment = get_appointment(user_id, appointment_id)
    if appointment.status != AppointmentStatus.SCHEDULED:
        raise ConflictError(
            f"Only scheduled appointments can be edited (current status: {appointment.status}).",
            code="APPOINTMENT_NOT_EDITABLE",
            details={"current_status": appointment.status},
        )

    start_at = appointment.start_at
    service = appointment.service
    if "start_at" in data:
        start_at = _to_utc(data["start_at"])
        _ensure_not_in_the_past(start_at)
    if "customer_id" in data:
        appointment.customer_id = customer_service.get_customer(user_id, data["customer_id"]).id
    if "service_id" in data and data["service_id"] != appointment.service_id:
        service = catalog_service.get_service(user_id, data["service_id"])
        _ensure_service_active(service)

    end_at = start_at + timedelta(minutes=service.duration_minutes)
    if (start_at, end_at) != (appointment.start_at, appointment.end_at):
        _ensure_slot_free(user_id, start_at, end_at, ignore_id=appointment.id)

    appointment.service_id = service.id
    appointment.start_at = start_at
    appointment.end_at = end_at
    if "notes" in data:
        appointment.notes = data["notes"]
    _commit_or_conflict()
    return appointment


def _ensure_transition_allowed(appointment: Appointment, new_status: AppointmentStatus) -> None:
    if new_status not in _TRANSITIONS[appointment.status]:
        raise ConflictError(
            f"Cannot change status from '{appointment.status}' to '{new_status}'.",
            code="INVALID_STATUS_TRANSITION",
            details={"current_status": appointment.status, "requested_status": str(new_status)},
        )


def cancel_appointment(user_id: int, appointment_id: int) -> Appointment:
    appointment = get_appointment(user_id, appointment_id)
    _ensure_transition_allowed(appointment, AppointmentStatus.CANCELED)
    appointment.status = AppointmentStatus.CANCELED.value
    db.session.commit()
    return appointment


def complete_appointment(user_id: int, appointment_id: int) -> Appointment:
    appointment = get_appointment(user_id, appointment_id)
    _ensure_transition_allowed(appointment, AppointmentStatus.COMPLETED)
    if appointment.start_at > _now():
        # Concluir um atendimento futuro liberaria o horário na constraint (só "scheduled"
        # ocupa a agenda) e permitiria dupla reserva. Concluído = já começou.
        raise ConflictError(
            "An appointment can only be completed after it has started.",
            code="APPOINTMENT_NOT_STARTED",
        )
    appointment.status = AppointmentStatus.COMPLETED.value
    db.session.commit()
    return appointment


def delete_appointment(user_id: int, appointment_id: int) -> None:
    appointment = get_appointment(user_id, appointment_id)
    if appointment.status == AppointmentStatus.COMPLETED:
        raise ConflictError(
            "Completed appointments are part of the history and cannot be deleted.",
            code="APPOINTMENT_COMPLETED",
        )
    db.session.delete(appointment)
    db.session.commit()
