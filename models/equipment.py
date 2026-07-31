import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from utils.database import Base


class Equipment(Base):
    __tablename__ = "equipment"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    equipment_code = Column(String(50), nullable=False)
    equipment_type = Column(String(50), nullable=False)  # Excavator, Crane, Bulldozer, Grader, Loader, Compactor
    status = Column(String(20), default="available")  # available, rented, maintenance, retired
    disabled = Column(Boolean, default=False, nullable=False)  # remote kill-switch: blocks checkout
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    tenant = relationship("Tenant", backref="equipment")
    rentals = relationship("Rental", back_populates="equipment")
    usage_logs = relationship("UsageLog", back_populates="equipment")
