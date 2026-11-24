from typing import Any

from flask.views import MethodView
from flask_smorest import Blueprint
from marshmallow import RAISE

from app.auth import current_user_id
from app.routes._common import protected
from app.schemas.common import ErrorResponseSchema
from app.schemas.customer import (
    CustomerListQuerySchema,
    CustomerPageSchema,
    CustomerSchema,
    CustomerUpdateSchema,
)
from app.services import customer_service

blp = Blueprint(
    "customers",
    __name__,
    url_prefix="/api/v1/customers",
    description="Clientes do negócio. Cada usuário enxerga somente os próprios clientes.",
)

_NOT_FOUND = "Cliente não encontrado (ou pertencente a outro usuário)."


@blp.route("")
class CustomerList(MethodView):
    @protected(blp)
    @blp.arguments(CustomerListQuerySchema, location="query", unknown=RAISE)
    @blp.response(200, CustomerPageSchema)
    def get(self, args: dict[str, Any]) -> Any:
        """Lista clientes com busca, ordenação e paginação."""
        return customer_service.list_customers(current_user_id(), **args)

    @protected(blp)
    @blp.arguments(CustomerSchema)
    @blp.response(201, CustomerSchema)
    @blp.alt_response(
        409, schema=ErrorResponseSchema, description="E-mail já usado por outro cliente."
    )
    def post(self, data: dict[str, Any]) -> Any:
        """Cadastra um cliente."""
        return customer_service.create_customer(current_user_id(), data)


@blp.route("/<int:customer_id>")
class CustomerDetail(MethodView):
    @protected(blp)
    @blp.response(200, CustomerSchema)
    @blp.alt_response(404, schema=ErrorResponseSchema, description=_NOT_FOUND)
    def get(self, customer_id: int) -> Any:
        """Detalha um cliente."""
        return customer_service.get_customer(current_user_id(), customer_id)

    @protected(blp)
    @blp.arguments(CustomerUpdateSchema)
    @blp.response(200, CustomerSchema)
    @blp.alt_response(404, schema=ErrorResponseSchema, description=_NOT_FOUND)
    @blp.alt_response(
        409, schema=ErrorResponseSchema, description="E-mail já usado por outro cliente."
    )
    def patch(self, data: dict[str, Any], customer_id: int) -> Any:
        """Atualiza parcialmente um cliente (envie só os campos a alterar)."""
        return customer_service.update_customer(current_user_id(), customer_id, data)

    @protected(blp)
    @blp.response(204)
    @blp.alt_response(404, schema=ErrorResponseSchema, description=_NOT_FOUND)
    @blp.alt_response(409, schema=ErrorResponseSchema, description="Cliente possui agendamentos.")
    def delete(self, customer_id: int) -> None:
        """Remove um cliente que não tenha agendamentos."""
        customer_service.delete_customer(current_user_id(), customer_id)
