from flask_smorest import Api


def register_blueprints(api: Api) -> None:
    from app.routes import auth, health

    api.register_blueprint(health.blp)
    api.register_blueprint(auth.blp)
