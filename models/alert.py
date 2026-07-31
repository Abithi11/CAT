import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB

from utils.database import Base


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    alert_type = Column(String(30), nullable=False)  # overdue, approaching_deadline, anomaly
    severity = Column(String(20), nullable=False, default="info")  # info, warning, critical
    equipment_id = Column(UUID(as_uuid=True), ForeignKey("equipment.id"), nullable=True)
    rental_id = Column(UUID(as_uuid=True), nullable=True)
    message = Column(String(500), nullable=False)
    details = Column(JSONB, nullable=True)
    status = Column(String(20), nullable=False, default="open")  # open, acknowledged
    email_sent = Column(String(20), nullable=False, default="skipped")  # skipped, sent, failed
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
