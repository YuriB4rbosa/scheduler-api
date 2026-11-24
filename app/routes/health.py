from typing import Any

from flask.views import MethodView
from flask_smorest import Blueprint
from marshmallow import Schema, fields
from sqlalchemy import text

from app.extensions import db

blp = Blueprint("health", __name__, description="Verificação de saúde do serviço.")


class HealthSchema(Schema):
    status = fields.Str(metadata={"example": "ok"})
    database = fields.Str(metadata={"example": "ok"})


@blp.route("/health")
class Health(MethodView):
    @blp.response(200, HealthSchema)
    def get(self) -> Any:
        """Confirma que a API e o banco de dados estão respondendo."""
        db.session.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
