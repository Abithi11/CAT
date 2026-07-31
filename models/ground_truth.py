import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Date, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from utils.database import Base


class GroundTruth(Base):
    """Planted truths from the synthetic generator, for validating detection accuracy.

    Never surfaced in the product UI — detection code must not read this table.
    """

    __tablename__ = "ground_truth"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    equipment_code = Column(String(50), nullable=False)
    truth_type = Column(String(30), nullable=False)  # degradation_onset, anomaly
    onset_date = Column(Date, nullable=True)  # set for degradation_onset only
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
