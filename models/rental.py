import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from utils.database import Base


class Rental(Base):
    __tablename__ = "rentals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    equipment_id = Column(UUID(as_uuid=True), ForeignKey("equipment.id"), nullable=False)
    site_id = Column(UUID(as_uuid=True), ForeignKey("sites.id"), nullable=True)
    operator_id = Column(UUID(as_uuid=True), ForeignKey("operators.id"), nullable=True)
    check_out_date = Column(Date, nullable=False)
    expected_return_date = Column(Date, nullable=False)
    actual_return_date = Column(Date, nullable=True)
    status = Column(String(20), default="active")  # active, returned, overdue
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    tenant = relationship("Tenant", backref="rentals")
    equipment = relationship("Equipment", back_populates="rentals")
    site = relationship("Site", back_populates="rentals")
    operator = relationship("Operator", back_populates="rentals")
    usage_logs = relationship("UsageLog", back_populates="rental")
