from typing import Any

from flask.views import MethodView
from flask_smorest import Blueprint
from marshmallow import RAISE

from app.auth import current_user_id
from app.routes._common import protected
from app.schemas.appointment import (
    AppointmentCreateSchema,
    AppointmentListQuerySchema,
    AppointmentPageSchema,
    AppointmentSchema,
    AppointmentUpdateSchema,
)
from app.schemas.common import ErrorResponseSchema
from app.services import appointment_service

blp = Blueprint(
    "appointments",
    __name__,
    url_prefix="/api/v1/appointments",
    description=(
        "Agendamentos. Não é possível ter dois agendamentos ativos sobrepostos no mesmo "
        "horário (409 `APPOINTMENT_CONFLICT`)."
    ),
)

_NOT_FOUND = "Agendamento não encontrado (ou pertencente a outro usuário)."
_CONFLICT = "Horário sobreposto a outro agendamento ativo."


@blp.route("")
class AppointmentList(MethodView):
    @protected(blp)
    @blp.arguments(AppointmentListQuerySchema, location="query", unknown=RAISE)
    @blp.response(200, AppointmentPageSchema)
    def get(self, args: dict[str, Any]) -> Any:
        """Lista agendamentos filtrando por status, cliente, serviço e período."""
        return appointment_service.list_appointments(current_user_id(), **args)

    @protected(blp)
    @blp.arguments(AppointmentCreateSchema)
    @blp.response(201, AppointmentSchema)
    @blp.alt_response(
        404, schema=ErrorResponseSchema, description="Cliente ou serviço não encontrado."
    )
    @blp.alt_response(409, schema=ErrorResponseSchema, description=_CONFLICT)
    @blp.alt_response(
        422,
        schema=ErrorResponseSchema,
        description="Horário no passado, serviço inativo ou dados inválidos.",
    )
    def post(self, data: dict[str, Any]) -> Any:
        """Cria um agendamento. O término é calculado pela duração do serviço."""
        return appointment_service.create_appointment(current_user_id(), data)


@blp.route("/<int:appointment_id>")
class AppointmentDetail(MethodView):
    @protected(blp)
    @blp.response(200, AppointmentSchema)
    @blp.alt_response(404, schema=ErrorResponseSchema, description=_NOT_FOUND)
    def get(self, appointment_id: int) -> Any:
        """Detalha um agendamento."""
        return appointment_service.get_appointment(current_user_id(), appointment_id)

    @protected(blp)
    @blp.arguments(AppointmentUpdateSchema)
    @blp.response(200, AppointmentSchema)
    @blp.alt_response(404, schema=ErrorResponseSchema, description=_NOT_FOUND)
    @blp.alt_response(
        409, schema=ErrorResponseSchema, description=f"{_CONFLICT} Ou agendamento não editável."
    )
    def patch(self, data: dict[str, Any], appointment_id: int) -> Any:
        """Reagenda ou altera um agendamento ativo (status muda só via /cancel e /complete)."""
        return appointment_service.update_appointment(current_user_id(), appointment_id, data)

    @protected(blp)
    @blp.response(204)
    @blp.alt_response(404, schema=ErrorResponseSchema, description=_NOT_FOUND)
    @blp.alt_response(
        409, schema=ErrorResponseSchema, description="Agendamento concluído (histórico)."
    )
    def delete(self, appointment_id: int) -> None:
        """Remove um agendamento. Concluídos são histórico e não podem ser removidos."""
        appointment_service.delete_appointment(current_user_id(), appointment_id)


@blp.route("/<int:appointment_id>/cancel")
class AppointmentCancel(MethodView):
    @protected(blp)
    @blp.response(200, AppointmentSchema)
    @blp.alt_response(404, schema=ErrorResponseSchema, description=_NOT_FOUND)
    @blp.alt_response(409, schema=ErrorResponseSchema, description="Transição de status inválida.")
    def post(self, appointment_id: int) -> Any:
        """Cancela um agendamento ativo e libera o horário."""
        return appointment_service.cancel_appointment(current_user_id(), appointment_id)


@blp.route("/<int:appointment_id>/complete")
class AppointmentComplete(MethodView):
    @protected(blp)
    @blp.response(200, AppointmentSchema)
    @blp.alt_response(404, schema=ErrorResponseSchema, description=_NOT_FOUND)
    @blp.alt_response(
        409,
        schema=ErrorResponseSchema,
        description="Transição inválida ou atendimento ainda não começou.",
    )
    def post(self, appointment_id: int) -> Any:
        """Marca como concluído um agendamento ativo cujo horário já começou."""
        return appointment_service.complete_appointment(current_user_id(), appointment_id)
