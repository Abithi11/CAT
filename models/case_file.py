import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB

from utils.database import Base


class CaseFile(Base):
    """Investigator-agent output: one case per investigation, into a human
    approve/reject queue (status: pending -> approved | rejected)."""

    __tablename__ = "case_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    equipment_id = Column(UUID(as_uuid=True), ForeignKey("equipment.id"), nullable=False)
    equipment_code = Column(String(50), nullable=False)
    anomaly_score = Column(Float, nullable=False, default=0.0)
    verdict = Column(String(50), nullable=False)
    confidence = Column(Float, nullable=False, default=0.0)
    summary = Column(Text, nullable=False)
    recommended_action = Column(String(500), nullable=False)
    evidence = Column(JSONB, nullable=True)  # key_evidence list + gathered context
    llm_used = Column(Boolean, nullable=False, default=False)
    status = Column(String(20), nullable=False, default="pending")  # pending, approved, rejected
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    decided_at = Column(DateTime(timezone=True), nullable=True)
