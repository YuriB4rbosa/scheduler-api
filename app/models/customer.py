from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TimestampMixin


class Customer(TimestampMixin, db.Model):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("user_id", "email", name="uq_customers_user_email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(255))

    user = relationship("User", back_populates="customers")
    appointments = relationship("Appointment", back_populates="customer")
