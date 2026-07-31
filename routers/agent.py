import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.investigator import run_investigation
from auth.dependencies import get_current_user
from models.case_file import CaseFile
from models.equipment import Equipment
from models.user import User
from utils.database import get_db

agent_router = APIRouter(prefix="/agent", tags=["agent"])

_CACHED_RUN = Path(__file__).resolve().parent.parent / "agent" / "cached_run.json"


class InvestigateRequest(BaseModel):
    equipment_id: UUID


def _serialize_case(c: CaseFile) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "equipment_id": str(c.equipment_id),
        "equipment_code": c.equipment_code,
        "anomaly_score": c.anomaly_score,
        "verdict": c.verdict,
        "confidence": c.confidence,
        "summary": c.summary,
        "recommended_action": c.recommended_action,
        "evidence": c.evidence,
        "llm_used": c.llm_used,
        "status": c.status,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "decided_at": c.decided_at.isoformat() if c.decided_at else None,
    }


@agent_router.post("/investigate", status_code=201)
async def investigate(
    body: InvestigateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Run the bounded LangGraph investigation for one machine; the resulting
    case file lands in the pending approval queue."""
    eq = (await db.execute(
        select(Equipment).where(Equipment.id == body.equipment_id,
                                Equipment.tenant_id == user.tenant_id)
    )).scalar_one_or_none()
    if not eq:
        raise HTTPException(status_code=404, detail="Equipment not found")
    case = await run_investigation(db, user.tenant_id, eq)
    await db.commit()
    return _serialize_case(case)


@agent_router.get("/cases", status_code=200)
async def list_cases(
    status_filter: str | None = Query(None, alias="status", description="pending | approved | rejected"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    stmt = select(CaseFile).where(CaseFile.tenant_id == user.tenant_id)
    if status_filter:
        stmt = stmt.where(CaseFile.status == status_filter)
    stmt = stmt.order_by(CaseFile.created_at.desc())
    return [_serialize_case(c) for c in (await db.execute(stmt)).scalars().all()]


@agent_router.get("/demo-replay", status_code=200)
async def demo_replay(user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Cached investigator run — the demo fallback when the local LLM flakes."""
    return json.loads(_CACHED_RUN.read_text())


async def _decide(case_id: UUID, decision: str, user: User, db: AsyncSession) -> dict[str, Any]:
    case = (await db.execute(
        select(CaseFile).where(CaseFile.id == case_id, CaseFile.tenant_id == user.tenant_id)
    )).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if case.status != "pending":
        raise HTTPException(status_code=409, detail=f"Case already {case.status}")
    case.status = decision
    case.decided_at = datetime.now(timezone.utc)
    await db.commit()
    return _serialize_case(case)


@agent_router.post("/cases/{case_id}/approve", status_code=200)
async def approve_case(
    case_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _decide(case_id, "approved", user, db)


@agent_router.post("/cases/{case_id}/reject", status_code=200)
async def reject_case(
    case_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _decide(case_id, "rejected", user, db)
