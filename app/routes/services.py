from typing import Any

from flask.views import MethodView
from flask_smorest import Blueprint
from marshmallow import RAISE

from app.auth import current_user_id
from app.routes._common import protected
from app.schemas.common import ErrorResponseSchema
from app.schemas.service import (
    ServiceListQuerySchema,
    ServicePageSchema,
    ServiceSchema,
    ServiceUpdateSchema,
)
from app.services import catalog_service

blp = Blueprint(
    "services",
    __name__,
    url_prefix="/api/v1/services",
    description="Serviços oferecidos (nome, duração e preço). Cada usuário vê só os seus.",
)

_NOT_FOUND = "Serviço não encontrado (ou pertencente a outro usuário)."


@blp.route("")
class ServiceList(MethodView):
    @protected(blp)
    @blp.arguments(ServiceListQuerySchema, location="query", unknown=RAISE)
    @blp.response(200, ServicePageSchema)
    def get(self, args: dict[str, Any]) -> Any:
        """Lista serviços com busca, filtros de preço/status, ordenação e paginação."""
        return catalog_service.list_services(current_user_id(), **args)

    @protected(blp)
    @blp.arguments(ServiceSchema)
    @blp.response(201, ServiceSchema)
    def post(self, data: dict[str, Any]) -> Any:
        """Cadastra um serviço."""
        return catalog_service.create_service(current_user_id(), data)


@blp.route("/<int:service_id>")
class ServiceDetail(MethodView):
    @protected(blp)
    @blp.response(200, ServiceSchema)
    @blp.alt_response(404, schema=ErrorResponseSchema, description=_NOT_FOUND)
    def get(self, service_id: int) -> Any:
        """Detalha um serviço."""
        return catalog_service.get_service(current_user_id(), service_id)

    @protected(blp)
    @blp.arguments(ServiceUpdateSchema)
    @blp.response(200, ServiceSchema)
    @blp.alt_response(404, schema=ErrorResponseSchema, description=_NOT_FOUND)
    def patch(self, data: dict[str, Any], service_id: int) -> Any:
        """Atualiza parcialmente um serviço (envie só os campos a alterar)."""
        return catalog_service.update_service(current_user_id(), service_id, data)

    @protected(blp)
    @blp.response(204)
    @blp.alt_response(404, schema=ErrorResponseSchema, description=_NOT_FOUND)
    @blp.alt_response(409, schema=ErrorResponseSchema, description="Serviço possui agendamentos.")
    def delete(self, service_id: int) -> None:
        """Remove um serviço que não tenha agendamentos (senão, desative-o)."""
        catalog_service.delete_service(current_user_id(), service_id)
