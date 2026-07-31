"""LangGraph investigator agent: bounded graph, LLM safety, approval queue, replay."""

from datetime import date, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent.investigator import AgentVerdict, _heuristic_verdict
from models.equipment import Equipment
from models.rental import Rental
from models.tenant import Tenant
from models.usage_log import UsageLog
from services.llm import LLMUnavailable


class TestHeuristicFallback:
    """Pure unit tests for the deterministic verdict — no DB, no network."""

    def test_ghost_usage_verdict(self):
        v = _heuristic_verdict({
            "anomaly": {"anomaly_score": 80, "metrics": {"ghost_ratio": 0.9, "idle_ratio": 0.4,
                                                         "fuel_z_score": 0.1}, "explanation": "x"},
            "usage_stats": {"ghost_days": 9},
        })
        assert v["verdict"] == "unassigned_usage"
        assert v["key_evidence"]
        assert AgentVerdict.model_validate(v)

    def test_fuel_drift_verdict(self):
        v = _heuristic_verdict({
            "anomaly": {"anomaly_score": 55, "metrics": {"ghost_ratio": 0.0, "idle_ratio": 0.2,
                                                         "fuel_z_score": 2.1}, "explanation": "x"},
            "usage_stats": {},
        })
        assert v["verdict"] == "possible_mechanical_issue"

    def test_normal_verdict(self):
        v = _heuristic_verdict({
            "anomaly": {"anomaly_score": 5, "metrics": {"ghost_ratio": 0.0, "idle_ratio": 0.1,
                                                        "fuel_z_score": 0.0}, "explanation": "fine"},
            "usage_stats": {},
        })
        assert v["verdict"] == "normal"
        assert v["confidence"] > 0.5


class TestInvestigator:
    @pytest.fixture
    async def setup(self, client, engine):
        reg = await client.post("/auth/register", json={
            "tenant_name": "AgentCo", "tenant_slug": "agentco",
            "email": "ops@agentco.com", "password": "agent123",
        })
        headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            tenant = (await db.execute(select(Tenant).where(Tenant.slug == "agentco"))).scalar_one()
            eq = Equipment(id=uuid4(), tenant_id=tenant.id, equipment_code="AG-CR-1",
                           equipment_type="Crane", status="rented")
            rental = Rental(
                id=uuid4(), tenant_id=tenant.id, equipment_id=eq.id,
                check_out_date=date.today() - timedelta(days=15),
                expected_return_date=date.today() + timedelta(days=10),
                status="active",
            )
            db.add_all([eq, rental])
            await db.flush()
            for i in range(8):
                db.add(UsageLog(
                    id=uuid4(), tenant_id=tenant.id, rental_id=rental.id, equipment_id=eq.id,
                    log_date=date.today() - timedelta(days=i + 1),
                    engine_hours=0.4, idle_hours=11.5, fuel_litres=5.0,
                    site_id=None, operator_id=None,
                ))
            await db.commit()
            return {"headers": headers, "eq_id": str(eq.id)}

    async def test_investigation_falls_back_when_llm_offline(self, client, setup):
        """LM Studio unreachable must still yield a usable case file."""
        with patch("agent.investigator.structured_completion",
                   side_effect=LLMUnavailable("LM Studio unreachable")):
            resp = await client.post("/agent/investigate",
                                     json={"equipment_id": setup["eq_id"]}, headers=setup["headers"])
        assert resp.status_code == 201, resp.text
        case = resp.json()
        assert case["llm_used"] is False
        assert case["verdict"] == "unassigned_usage"
        assert case["status"] == "pending"
        assert case["evidence"]["key_evidence"]
        # every graph node contributed context
        for key in ("anomaly", "usage_stats", "operator_history", "contract_context"):
            assert key in case["evidence"]

    async def test_investigation_uses_llm_verdict_when_available(self, client, setup):
        fake = AgentVerdict(
            verdict="misuse", confidence=0.91,
            summary="Machine held without operator assignment for 8 days.",
            key_evidence=["100% ghost usage days", "11.5 idle hours/day"],
            recommended_action="Contact the site supervisor and audit custody records.",
        )
        with patch("agent.investigator.structured_completion", return_value=fake) as mock_llm:
            resp = await client.post("/agent/investigate",
                                     json={"equipment_id": setup["eq_id"]}, headers=setup["headers"])
        assert resp.status_code == 201, resp.text
        case = resp.json()
        assert case["llm_used"] is True
        assert case["verdict"] == "misuse"
        assert case["confidence"] == pytest.approx(0.91)

        # LLM safety: it receives text context only — no DB session, no SQL
        kwargs = mock_llm.call_args.kwargs
        assert set(kwargs) == {"system", "user", "schema"}
        assert isinstance(kwargs["user"], str)
        assert kwargs["schema"] is AgentVerdict

    async def test_approval_queue_flow(self, client, setup):
        with patch("agent.investigator.structured_completion",
                   side_effect=LLMUnavailable("offline")):
            case = (await client.post("/agent/investigate",
                                      json={"equipment_id": setup["eq_id"]},
                                      headers=setup["headers"])).json()

        pending = (await client.get("/agent/cases?status=pending", headers=setup["headers"])).json()
        assert [c["id"] for c in pending] == [case["id"]]

        approved = await client.post(f"/agent/cases/{case['id']}/approve", headers=setup["headers"])
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"
        assert approved.json()["decided_at"] is not None

        again = await client.post(f"/agent/cases/{case['id']}/reject", headers=setup["headers"])
        assert again.status_code == 409, "a decided case cannot be re-decided"

        assert (await client.get("/agent/cases?status=pending", headers=setup["headers"])).json() == []

    async def test_investigate_unknown_equipment_404(self, client, setup):
        resp = await client.post("/agent/investigate", json={"equipment_id": str(uuid4())},
                                 headers=setup["headers"])
        assert resp.status_code == 404

    async def test_demo_replay_available_without_llm(self, client, setup):
        resp = await client.get("/agent/demo-replay", headers=setup["headers"])
        assert resp.status_code == 200
        replay = resp.json()
        assert replay["verdict"] in ("misuse", "underutilization", "unassigned_usage",
                                     "possible_mechanical_issue", "normal")
        assert replay["evidence"]["key_evidence"]
        assert replay["equipment_code"]
