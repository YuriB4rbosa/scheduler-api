import enum
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TimestampMixin


class AppointmentStatus(enum.StrEnum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELED = "canceled"


class Appointment(TimestampMixin, db.Model):
    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint("end_at > start_at", name="ck_appointments_end_after_start"),
        CheckConstraint(
            "status IN ('scheduled', 'completed', 'canceled')", name="ck_appointments_status"
        ),
        # Garantia no banco contra sobreposição (imune a condições de corrida).
        # Intervalo semiaberto [start, end): um agendamento pode começar quando outro termina.
        # Só agendamentos ativos ("scheduled") ocupam o horário.
        ExcludeConstraint(
            ("user_id", "="),
            (text("tstzrange(start_at, end_at)"), "&&"),
            name="ex_appointments_no_overlap",
            using="gist",
            where=text("status = 'scheduled'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # user_id é denormalizado de propósito: simplifica a checagem de dono e a de conflito.
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), index=True
    )
    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="RESTRICT"), index=True
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(20),
        default=AppointmentStatus.SCHEDULED.value,
        server_default=AppointmentStatus.SCHEDULED.value,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text)

    user = relationship("User", back_populates="appointments")
    customer = relationship("Customer", back_populates="appointments")
    service = relationship("Service", back_populates="appointments")
