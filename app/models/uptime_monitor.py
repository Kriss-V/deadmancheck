import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UptimeMonitor(Base):
    __tablename__ = "uptime_monitors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, default=300)   # check every N seconds
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=10)
    expected_status_code: Mapped[int] = mapped_column(Integer, default=200)

    # State
    status: Mapped[str] = mapped_column(String(20), default="new")  # new | up | down
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_response_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    alert_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Alert config
    alert_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    alert_webhook_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    slack_webhook_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    discord_webhook_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram_bot_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pagerduty_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    alert_on_recovery: Mapped[bool] = mapped_column(Boolean, default=True)

    is_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="uptime_monitors")
    checks: Mapped[list["UptimeCheck"]] = relationship("UptimeCheck", back_populates="monitor", cascade="all, delete-orphan")


class UptimeCheck(Base):
    __tablename__ = "uptime_checks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    monitor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("uptime_monitors.id"), nullable=False, index=True)

    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    is_up: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    monitor: Mapped["UptimeMonitor"] = relationship("UptimeMonitor", back_populates="checks")
