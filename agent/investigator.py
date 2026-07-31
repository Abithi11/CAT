"""LangGraph investigator agent.

Bounded linear graph (4 analysis nodes, <=5 tool calls total):

    anomaly_context -> operator_history -> contract_context -> synthesize

Every node reads the DB through SQLAlchemy and writes plain dicts into state.
The LLM only ever sees that gathered context as JSON text and must answer in a
Pydantic-validated schema (services.llm.structured_completion) — it never
touches the database. If LM Studio is unreachable the synthesize node falls
back to a deterministic heuristic verdict, so the demo cannot dead-end.
"""

import json
import logging
from datetime import date, timedelta
from typing import Any, Literal, TypedDict
from uuid import UUID

from langgraph.graph import StateGraph, START, END
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.case_file import CaseFile
from models.equipment import Equipment
from models.operator import Operator
from models.rental import Rental
from models.site import Site
from models.usage_log import UsageLog
from services.analytics import calculate_fleet_anomalies
from services.llm import LLMUnavailable, structured_completion

logger = logging.getLogger(__name__)

VERDICTS = ("misuse", "underutilization", "unassigned_usage",
            "possible_mechanical_issue", "normal")

RECOMMENDED_ACTIONS = {
    "misuse": "Contact the site supervisor; review operator assignment and consider re-training or contract penalty clauses.",
    "underutilization": "Recall or rebalance the machine to a higher-demand site; review rental terms.",
    "unassigned_usage": "Require check-out records to include site and operator; audit custody events for this machine.",
    "possible_mechanical_issue": "Schedule an early service inspection; degraded efficiency compounds daily.",
    "normal": "No action required; keep monitoring.",
}


class AgentVerdict(BaseModel):
    verdict: Literal["misuse", "underutilization", "unassigned_usage",
                     "possible_mechanical_issue", "normal"]
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    key_evidence: list[str]
    recommended_action: str


class InvestigationState(TypedDict, total=False):
    anomaly: dict[str, Any]
    usage_stats: dict[str, Any]
    operator_history: dict[str, Any]
    contract_context: dict[str, Any]
    verdict: dict[str, Any]
    llm_used: bool


async def run_investigation(db: AsyncSession, tenant_id: UUID, equipment: Equipment) -> CaseFile:
    """Build + run the bounded graph, persist the case file (status=pending)."""

    async def anomaly_context(state: InvestigationState) -> dict:
        anomalies = await calculate_fleet_anomalies(db, tenant_id, window_days=30)
        anomaly = next(
            (a for a in anomalies if a["equipment_id"] == str(equipment.id)),
            {"anomaly_score": 0, "severity": "Normal", "metrics": {}, "explanation": "No data"},
        )
        cutoff = date.today() - timedelta(days=30)
        eng, idle, fuel, days, ghost_days = (await db.execute(
            select(
                func.coalesce(func.sum(UsageLog.engine_hours), 0.0),
                func.coalesce(func.sum(UsageLog.idle_hours), 0.0),
                func.coalesce(func.sum(UsageLog.fuel_litres), 0.0),
                func.count(UsageLog.id),
                func.count(UsageLog.id).filter(
                    (UsageLog.site_id.is_(None)) | (UsageLog.operator_id.is_(None))),
            ).where(UsageLog.tenant_id == tenant_id,
                    UsageLog.equipment_id == equipment.id,
                    UsageLog.log_date >= cutoff)
        )).one()
        return {
            "anomaly": {k: anomaly[k] for k in ("anomaly_score", "severity", "metrics", "explanation")},
            "usage_stats": {
                "window_days": 30, "days_logged": int(days),
                "engine_hours": round(float(eng), 1), "idle_hours": round(float(idle), 1),
                "fuel_litres": round(float(fuel), 1), "ghost_days": int(ghost_days),
            },
        }

    async def operator_history(state: InvestigationState) -> dict:
        rental = (await db.execute(
            select(Rental).where(
                Rental.equipment_id == equipment.id,
                Rental.actual_return_date.is_(None),
            ).order_by(Rental.check_out_date.desc()).limit(1)
        )).scalar_one_or_none()
        if rental is None or rental.operator_id is None:
            return {"operator_history": {
                "operator_assigned": False,
                "note": "No operator on record for the current rental — custody chain incomplete.",
            }}
        op = (await db.execute(
            select(Operator).where(Operator.id == rental.operator_id)
        )).scalar_one()
        total_rentals = (await db.execute(
            select(func.count(Rental.id)).where(
                Rental.tenant_id == tenant_id, Rental.operator_id == op.id)
        )).scalar_one()
        op_eng, op_idle = (await db.execute(
            select(
                func.coalesce(func.sum(UsageLog.engine_hours), 0.0),
                func.coalesce(func.sum(UsageLog.idle_hours), 0.0),
            ).where(UsageLog.tenant_id == tenant_id, UsageLog.operator_id == op.id)
        )).one()
        op_eng, op_idle = float(op_eng), float(op_idle)
        return {"operator_history": {
            "operator_assigned": True,
            "operator_code": op.operator_code, "operator_name": op.name,
            "total_rentals_operated": int(total_rentals),
            "career_idle_ratio_pct": round(op_idle / (op_eng + op_idle + 1e-6) * 100, 1),
        }}

    async def contract_context(state: InvestigationState) -> dict:
        row = (await db.execute(
            select(Rental, Site.site_code, Site.name)
            .outerjoin(Site, Rental.site_id == Site.id)
            .where(Rental.equipment_id == equipment.id)
            .order_by(Rental.check_out_date.desc())
            .limit(1)
        )).first()
        if not row:
            return {"contract_context": {"has_rental_history": False}}
        rental, site_code, site_name = row
        overdue_days = 0
        if rental.actual_return_date is None and rental.expected_return_date < date.today():
            overdue_days = (date.today() - rental.expected_return_date).days
        return {"contract_context": {
            "has_rental_history": True,
            "rental_status": rental.status,
            "check_out_date": str(rental.check_out_date),
            "expected_return_date": str(rental.expected_return_date),
            "days_overdue": overdue_days,
            "site_code": site_code, "site_name": site_name or "Unassigned",
            "equipment_status": equipment.status,
            "kill_switch_active": bool(equipment.disabled),
        }}

    async def synthesize(state: InvestigationState) -> dict:
        context = {
            "equipment": {"code": equipment.equipment_code, "type": equipment.equipment_type},
            "anomaly": state.get("anomaly", {}),
            "usage_stats": state.get("usage_stats", {}),
            "operator_history": state.get("operator_history", {}),
            "contract_context": state.get("contract_context", {}),
        }
        try:
            verdict = await structured_completion(
                system=(
                    "You are the investigation officer for an equipment-rental dealer. "
                    "You are given telemetry statistics, anomaly-detector output, operator "
                    "history and contract context for one machine, all pre-fetched for you. "
                    "Decide what is going on and reply ONLY with JSON matching the schema. "
                    "Base every claim strictly on the provided numbers — do not invent data."
                ),
                user=json.dumps(context, default=str),
                schema=AgentVerdict,
            )
            return {"verdict": verdict.model_dump(), "llm_used": True}
        except LLMUnavailable as e:
            logger.warning("LLM unavailable, using heuristic verdict: %s", e)
            return {"verdict": _heuristic_verdict(state), "llm_used": False}

    graph = StateGraph(InvestigationState)
    graph.add_node("anomaly_context", anomaly_context)
    graph.add_node("operator_history", operator_history)
    graph.add_node("contract_context", contract_context)
    graph.add_node("synthesize", synthesize)
    graph.add_edge(START, "anomaly_context")
    graph.add_edge("anomaly_context", "operator_history")
    graph.add_edge("operator_history", "contract_context")
    graph.add_edge("contract_context", "synthesize")
    graph.add_edge("synthesize", END)

    final: InvestigationState = await graph.compile().ainvoke({})

    v = final["verdict"]
    case = CaseFile(
        tenant_id=tenant_id,
        equipment_id=equipment.id,
        equipment_code=equipment.equipment_code,
        anomaly_score=float(final.get("anomaly", {}).get("anomaly_score", 0)),
        verdict=v["verdict"],
        confidence=float(v["confidence"]),
        summary=v["summary"],
        recommended_action=v["recommended_action"][:500],
        evidence={
            "key_evidence": v.get("key_evidence", []),
            "anomaly": final.get("anomaly", {}),
            "usage_stats": final.get("usage_stats", {}),
            "operator_history": final.get("operator_history", {}),
            "contract_context": final.get("contract_context", {}),
        },
        llm_used=bool(final.get("llm_used", False)),
        status="pending",
    )
    db.add(case)
    await db.flush()
    return case


def _heuristic_verdict(state: InvestigationState) -> dict[str, Any]:
    """Deterministic fallback mirroring the anomaly layers — keeps the demo alive."""
    anomaly = state.get("anomaly", {})
    metrics = anomaly.get("metrics", {})
    stats = state.get("usage_stats", {})
    score = anomaly.get("anomaly_score", 0)
    idle_ratio = metrics.get("idle_ratio", 0.0)
    ghost_ratio = metrics.get("ghost_ratio", 0.0)
    fuel_z = metrics.get("fuel_z_score", 0.0)

    evidence = []
    if ghost_ratio > 0.3:
        verdict = "unassigned_usage"
        evidence.append(f"{ghost_ratio * 100:.0f}% of usage days logged with no site or operator")
    elif fuel_z > 1.0:
        verdict = "possible_mechanical_issue"
        evidence.append(f"Fuel consumption {fuel_z:.1f} standard deviations above class baseline")
    elif idle_ratio > 0.5:
        verdict = "underutilization" if score < 60 else "misuse"
        evidence.append(f"Machine idle {idle_ratio * 100:.0f}% of powered-on time")
    elif score >= 60:
        verdict = "misuse"
        evidence.append(f"Composite anomaly score {score}")
    else:
        verdict = "normal"
        evidence.append(f"Anomaly score {score} within normal range")
    if stats.get("ghost_days"):
        evidence.append(f"{stats['ghost_days']} untraceable usage day(s) in the last 30 days")

    return {
        "verdict": verdict,
        "confidence": 0.6 if verdict != "normal" else 0.8,
        "summary": f"Rule-based assessment (LLM offline): {anomaly.get('explanation', 'no anomaly data')}",
        "key_evidence": evidence,
        "recommended_action": RECOMMENDED_ACTIONS[verdict],
    }
