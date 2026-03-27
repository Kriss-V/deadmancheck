import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Monitor(Base):
    __tablename__ = "monitors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=True)  # friendly name for ping URL
    tags: Mapped[str] = mapped_column(String(500), default="")  # comma-separated

    # Schedule: either cron expression or period_seconds
    schedule_type: Mapped[str] = mapped_column(String(20), default="period")  # period | cron
    period_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)   # e.g. 3600 = every hour
    cron_expression: Mapped[str | None] = mapped_column(String(100), nullable=True)  # e.g. "0 3 * * *"
    grace_seconds: Mapped[int] = mapped_column(Integer, default=300)  # how long to wait after due before alerting

    # Duration monitoring (the differentiator)
    expect_duration_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    expect_duration_max_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)  # hard max
    duration_alert_pct: Mapped[int] = mapped_column(Integer, default=200)  # alert if > X% of rolling avg
    avg_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)  # rolling avg

    # State
    status: Mapped[str] = mapped_column(String(20), default="new")  # new | up | late | paused
    last_ping_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    next_expected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    alert_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Alert config
    alert_email: Mapped[str | None] = mapped_column(String(255), nullable=True)  # defaults to user email
    alert_webhook_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    alert_on_recovery: Mapped[bool] = mapped_column(Boolean, default=True)

    is_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="monitors")
    pings: Mapped[list["Ping"]] = relationship("Ping", back_populates="monitor", cascade="all, delete-orphan")
