"""Dados de demonstração. Pensado para desenvolvimento e para quem avalia o projeto.

Gera um negócio fictício (salão) com clientes, serviços e uma agenda que mistura passado
(concluídos e cancelados) e futuro (agendados), sem sobreposições. A geração é determinística.
"""

import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.extensions import db
from app.models import Appointment, AppointmentStatus, Customer, Service, User
from app.services import auth_service

DEMO_EMAIL = "demo@scheduler.dev"
DEMO_NAME = "Salão Demo"
DEV_DEFAULT_PASSWORD = "demo12345"  # noqa: S105 - só usado quando ENV_NAME == "development"

_CUSTOMERS = [
    ("Maria Oliveira", "+55 11 98888-1111", "maria@example.com"),
    ("João Pereira", "+55 11 98888-2222", "joao@example.com"),
    ("Ana Costa", "+55 11 98888-3333", "ana.costa@example.com"),
    ("Carlos Souza", "+55 11 98888-4444", "carlos@example.com"),
    ("Beatriz Lima", "+55 11 98888-5555", "bia@example.com"),
    ("Rafael Alves", "+55 11 98888-6666", None),
    ("Fernanda Rocha", None, "fernanda@example.com"),
    ("Lucas Martins", "+55 11 98888-8888", "lucas@example.com"),
]

# (nome, duração em min, preço, ativo)
_SERVICES = [
    ("Corte feminino", 60, "90.00", True),
    ("Corte masculino", 30, "50.00", True),
    ("Barba", 20, "35.00", True),
    ("Coloração", 120, "220.00", True),
    ("Escova", 45, "70.00", True),
    ("Hidratação", 50, "110.00", True),
    ("Manicure", 40, "45.00", True),
    ("Pacote noiva (descontinuado)", 180, "600.00", False),
]


class SeedError(Exception):
    """Falha esperada do seed (mensagem pensada para o usuário da CLI)."""


def resolve_password(env_name: str, from_env: str | None) -> str:
    if from_env:
        return from_env
    if env_name == "development":
        return DEV_DEFAULT_PASSWORD
    raise SeedError("Defina SEED_DEMO_PASSWORD (a senha padrão só existe em development).")


def _build_agenda(
    user_id: int, customers: list[Customer], services: list[Service], now: datetime
) -> list[Appointment]:
    rng = random.Random(42)  # noqa: S311 - dados de demonstração, não é criptografia
    active_services = [s for s in services if s.active]
    appointments: list[Appointment] = []

    for day_offset in range(-10, 8):
        day = (now + timedelta(days=day_offset)).replace(hour=12, minute=0, second=0, microsecond=0)
        if (
            day_offset == 0 or day.weekday() >= 5
        ):  # sem hoje (evita "meio passado") e sem fim de semana
            continue
        cursor = day
        for _ in range(rng.randint(2, 4)):
            service = rng.choice(active_services)
            end = cursor + timedelta(minutes=service.duration_minutes)
            if end.hour >= 21:
                break
            canceled = rng.random() < 0.12
            if canceled:
                status = AppointmentStatus.CANCELED
            elif day_offset < 0:
                status = AppointmentStatus.COMPLETED
            else:
                status = AppointmentStatus.SCHEDULED
            appointments.append(
                Appointment(
                    user_id=user_id,
                    customer_id=rng.choice(customers).id,
                    service_id=service.id,
                    start_at=cursor,
                    end_at=end,
                    status=status.value,
                    notes=rng.choice([None, None, "Primeira visita", "Cliente fixo"]),
                )
            )
            cursor = end + timedelta(minutes=rng.choice([0, 15, 30, 60]))
    return appointments


def seed_demo(password: str, *, reset: bool = False, now: datetime | None = None) -> dict[str, int]:
    """Cria o usuário de demonstração e seus dados. Devolve a contagem do que foi criado."""
    now = now or datetime.now(UTC)
    existing = db.session.scalar(select(User).where(User.email == DEMO_EMAIL))
    if existing is not None:
        if not reset:
            raise SeedError(f"{DEMO_EMAIL} já existe. Use --reset para recriar os dados de demo.")
        db.session.delete(existing)  # cascata remove clientes, serviços e agendamentos
        db.session.commit()

    user = User(
        name=DEMO_NAME,
        email=DEMO_EMAIL,
        password_hash=auth_service.hash_password(password),
    )
    db.session.add(user)
    db.session.flush()

    customers = [Customer(user_id=user.id, name=n, phone=p, email=e) for n, p, e in _CUSTOMERS]
    services = [
        Service(user_id=user.id, name=n, duration_minutes=d, price=pr, active=a)
        for n, d, pr, a in _SERVICES
    ]
    db.session.add_all([*customers, *services])
    db.session.flush()

    appointments = _build_agenda(user.id, customers, services, now)
    db.session.add_all(appointments)
    db.session.commit()
    return {
        "customers": len(customers),
        "services": len(services),
        "appointments": len(appointments),
    }
