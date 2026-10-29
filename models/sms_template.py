"""SMS template — swappable per card type and recipient type."""

from __future__ import annotations

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


class SmsTemplate(Base, TimestampMixin):
    __tablename__ = "sms_templates"
    __table_args__ = (
        UniqueConstraint("card_type", "recipient_type", name="uq_template_card_recipient"),
    )

    # e.g. "SAFE", "ASSIST", "DANGER"
    card_type: Mapped[str] = mapped_column(String(16), nullable=False)

    # e.g. "PARENT", "POLICE"
    recipient_type: Mapped[str] = mapped_column(String(16), nullable=False)

    template_text: Mapped[str] = mapped_column(Text, nullable=False)

    def __repr__(self) -> str:
        return f"<SmsTemplate {self.card_type}/{self.recipient_type}>"