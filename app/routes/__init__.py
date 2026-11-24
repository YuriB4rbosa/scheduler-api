from flask_smorest import Api


def register_blueprints(api: Api) -> None:
    from app.routes import appointments, auth, customers, health, services

    api.register_blueprint(health.blp)
    api.register_blueprint(auth.blp)
    api.register_blueprint(customers.blp)
    api.register_blueprint(services.blp)
    api.register_blueprint(appointments.blp)
