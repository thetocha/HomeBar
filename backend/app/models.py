from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

ORDER_STATUSES = ("pending", "accepted", "ready", "done")
NEXT_STATUS = {
    "pending": "accepted",
    "accepted": "ready",
    "ready": "done",
}


class Cocktail(Base):
    __tablename__ = "cocktails"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    photo_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    orders: Mapped[list["Order"]] = relationship(back_populates="cocktail")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cocktail_id: Mapped[int | None] = mapped_column(
        ForeignKey("cocktails.id", ondelete="SET NULL"), nullable=True
    )
    cocktail_name: Mapped[str] = mapped_column(String(120), nullable=False)
    guest_telegram_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    guest_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    cocktail: Mapped[Cocktail | None] = relationship(back_populates="orders")
