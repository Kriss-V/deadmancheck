import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Ping(Base):
    __tablename__ = "pings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    monitor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("monitors.id"), nullable=False, index=True)

    # ping type: success (heartbeat), start (job began), fail (job failed)
    kind: Mapped[str] = mapped_column(String(20), default="success")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Duration: populated when kind=success and a matching start ping exists
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_anomaly: Mapped[bool] = mapped_column(Integer, default=0)  # 1 if flagged

    # Optional metadata sent by the job
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)  # last 10k chars of job output
    source_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    # Assertion results: JSON array of {field, op, value, actual, passed}
    assertion_results: Mapped[str | None] = mapped_column(Text, nullable=True)

    monitor: Mapped["Monitor"] = relationship("Monitor", back_populates="pings")
