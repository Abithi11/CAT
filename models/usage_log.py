import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Float, Date, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from utils.database import Base


class UsageLog(Base):
    __tablename__ = "usage_logs"

    # Composite PK includes log_date so TimescaleDB can partition this table
    # into a hypertable on the time dimension (see utils.database.apply_timescale).
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    rental_id = Column(UUID(as_uuid=True), ForeignKey("rentals.id"), nullable=False)
    equipment_id = Column(UUID(as_uuid=True), ForeignKey("equipment.id"), nullable=False)
    site_id = Column(UUID(as_uuid=True), ForeignKey("sites.id"), nullable=True)
    operator_id = Column(UUID(as_uuid=True), ForeignKey("operators.id"), nullable=True)
    log_date = Column(Date, primary_key=True, nullable=False)
    engine_hours = Column(Float, default=0.0)
    idle_hours = Column(Float, default=0.0)
    fuel_litres = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    tenant = relationship("Tenant", backref="usage_logs")
    rental = relationship("Rental", back_populates="usage_logs")
    equipment = relationship("Equipment", back_populates="usage_logs")
    site = relationship("Site", back_populates="usage_logs")
    operator = relationship("Operator", back_populates="usage_logs")
