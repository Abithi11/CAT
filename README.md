# Smart Rental Tracking System

Multi-tenant equipment-rental tracking for construction & mining dealers — live fleet
visibility, QR-simulated custody events, probabilistic demand forecasting, layered
anomaly detection, an LLM investigator agent, and **degradation tracing**: pinpointing
*when* a machine started degrading and *who had custody* at that moment.

Built for the Caterpillar hackathon. No hardware, no telematics box — everything runs
on the rental records and usage logs dealers already collect.

---

## Quick start

```bash
docker compose up --build
```

That's it. The stack builds, waits for TimescaleDB, creates the schema, converts
`usage_logs` into a hypertable, seeds an 18-month synthetic fleet (20 machines,
6 sites, 12 operators — with planted anomalies and hidden degradation onsets),
and starts the API on **http://localhost:8000** (Swagger UI at `/docs`).

**Demo login** — tenant `demo`, email `demo@cat.com`, password `demo1234`.

```bash
curl -s localhost:8000/auth/login -H 'Content-Type: application/json' \
  -d '{"tenant_slug":"demo","email":"demo@cat.com","password":"demo1234"}'
```

Every endpoint below (except `/health`) takes `Authorization: Bearer <access_token>`.

### Optional configuration

Copy `.env.example` to `.env` to override defaults. Two integrations are optional:

| Setting | Effect if unset |
|---|---|
| `LLM_BASE_URL` (default `http://trinity.local:1234/v1`) | Agent falls back to a deterministic rule-based verdict; `/agent/demo-replay` always works |
| `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `ALERT_EMAIL_TO` | Email delivery skipped; in-app alerts still land in the `alerts` table and dashboard |

The chat model is auto-detected from LM Studio's `/v1/models` (embedding and
reranker models are skipped) unless `LLM_MODEL` is set.

> **Pointing the container at LM Studio.** mDNS `.local` hostnames do **not**
> resolve inside Docker containers. Use the machine's IP, or
> `http://host.docker.internal:1234/v1` when LM Studio runs on the Docker host:
>
> ```bash
> LLM_BASE_URL=http://192.168.1.42:1234/v1 docker compose up
> ```
>
> The API logs LM Studio reachability at startup — check that line before demoing:
> `LM Studio reachable at ... (model: ...)`.

**Structured output on local models.** LM Studio's `json_schema` mode returns an
empty `content` on reasoning models — the schema constrains the reasoning stream
and the JSON ends up in `reasoning_content`
([lmstudio-bug-tracker #1773](https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/1773),
[#1698](https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/1698)).
`services/llm.py` handles this: it recovers the reply from `reasoning_content`,
and if that fails, falls back to injecting the schema into the prompt and parsing
defensively (fences, `<think>` blocks, prose). The working strategy is cached per
process, so a mixed fleet of local models works without configuration.

---

## Architecture

```
                    ┌──────────────────────────────────────────┐
   QR scan  ─────►  │  routers/   FastAPI + JWT (tenant claim) │
   Usage POST ────► └────────────────────┬─────────────────────┘
                                         │
                    ┌────────────────────▼─────────────────────┐
                    │  services/   business logic layer        │
                    │                                          │
                    │  __init__  checkout / checkin / usage    │
                    │  analytics rules + NumPy anomaly scores  │
                    │  degradation  ruptures change-points ★   │
                    │  forecasting  NGBoost distributions      │
                    │  alerts    scan → alerts table → SMTP    │
                    │  reports   utilization / downtime        │
                    │  llm       LM Studio via HTTPX           │
                    └────────────────────┬─────────────────────┘
                                         │
     agent/investigator.py               │        generators/
     LangGraph bounded graph ────────────┤        synthetic fleet
     (4 nodes, ≤5 tool calls)            │        + ground truth
                                         │
                    ┌────────────────────▼─────────────────────┐
                    │  SQLAlchemy 2.0 async ORM                │
                    │  PostgreSQL + TimescaleDB hypertable     │
                    └──────────────────────────────────────────┘
```

**Key design decisions**

- **The LLM never touches the database.** The agent's graph nodes gather context via
  SQLAlchemy, hand the LLM plain JSON text, and require a Pydantic-validated response
  (`AgentVerdict`). No LLM-generated SQL anywhere.
- **Anomaly detection is layered.** Structural rules (NULL site/operator, usage while
  unassigned) first; per-class statistical baselines (fuel z-score vs equipment type)
  stack on top.
- **Ground truth is separated from detection.** The generator plants degradation onsets
  into a `ground_truth` table that the detection code never reads — that's what makes
  the accuracy number meaningful rather than circular.
- **Everything degrades gracefully.** LLM offline → heuristic verdict. TimescaleDB
  missing → plain Postgres table. SMTP unset → in-app alerts only. Too little history
  → seasonal baseline instead of NGBoost.
- **Multi-tenancy** is a `tenant_id` column on every table plus a tenant claim in the JWT.

---

## API surface

| Area | Endpoint | Notes |
|---|---|---|
| Health | `GET /health` | DB connectivity check |
| Auth | `POST /auth/register` · `/auth/login` · `/auth/refresh` · `GET /auth/me` | JWT, per-tenant |
| Custody | `POST /rentals/checkout` · `/rentals/checkin` | QR-simulated check-in/out |
| | `GET /equipment/{id}/qrcode` | PNG QR encoding the equipment code |
| Telemetry | `POST /usage` | Ingests runtime/idle/fuel per machine-day |
| Dashboard | `GET /dashboard/summary` · `/dashboard/live-assets` | Live status, KPIs, risk feed |
| Reports | `GET /reports/summary` | Rented hours, per-site utilization, downtime |
| Alerts | `GET /alerts` · `POST /alerts/scan` · `POST /alerts/{id}/acknowledge` | APScheduler runs the same scan every 15 min |
| Anomalies | `GET /analytics/anomalies` · `POST /rentals/detect-overdue` | Scores 0–100 with explanations |
| Forecasting | `GET /forecast` · `GET /forecast/rebalancing` | NGBoost distributions; ₹ saved per move |
| **Degradation** | `GET /equipment/{id}/degradation` | Health timeline + onset + custody at onset |
| | `GET /degradation/fleet` · `POST /degradation/validate` | Fleet view; **accuracy vs ground truth** |
| Agent | `POST /agent/investigate` · `GET /agent/cases` | LangGraph investigator → approval queue |
| | `POST /agent/cases/{id}/approve` · `/reject` · `GET /agent/demo-replay` | Human-in-the-loop; cached replay |
| Kill-switch | `POST /equipment/{id}/immobilize` · `/release` | Simulated remote immobilization |
| Seeding | `POST /seed` | Generate a synthetic fleet for your tenant |

---

## How degradation tracing works

1. **Health signal** — for each machine, daily *fuel litres per engine-hour*, restricted
   to days with ≥1 engine-hour (near-idle days are noise), smoothed with a centered
   7-day rolling median.
2. **Change-point detection** — `ruptures` PELT (RBF cost) proposes candidate breaks;
   the earliest whose post-segment mean exceeds baseline × 1.08 wins. A one-sided CUSUM
   is the fallback. The winner is then backtracked to where the signal first left
   baseline, since degradation ramps rather than steps.
3. **Custody attribution** — the rental covering the onset date supplies the site and
   operator who had the machine when it started degrading.
4. **Validation** — `POST /degradation/validate` compares detected onsets against the
   generator's planted ones and reports accuracy within ±N days, mean absolute error,
   and false positives.

```bash
# the number for the slide
curl -s -X POST 'localhost:8000/degradation/validate?tolerance_days=30' \
  -H "Authorization: Bearer $TOKEN" | jq '.headline, .accuracy_pct, .mean_abs_error_days'
```

---

## Tests

```bash
pip install -r requirements-dev.txt
```

```bash
docker compose up -d db && python -m pytest
```

Tests need Postgres on `localhost:5432` (override with `TEST_PG_SERVER`); they create
and drop a `cat_test` database per run. No test requires LM Studio or SMTP — both are
mocked.

| Suite | Covers |
|---|---|
| `test_smoke.py` | Health, every route registered, auth roundtrip, all read endpoints on an empty tenant |
| `test_e2e_lifecycle.py` | **The full arc**: checkout → 150 days of usage → overdue alert → anomaly flag → degradation trace with custody, onset verified within ±30 days of the planted one |
| `test_degradation.py` | Change-point detection unit tests (flat/ramp/step), ground-truth validation API |
| `test_forecast.py` | Distribution sanity (p10 ≤ mean ≤ p90, probabilities in [0,1]), ₹ savings, empty-tenant behavior |
| `test_alerts.py` | Scan → dedup → acknowledge, smtplib delivery mocked, scheduler entry point |
| `test_llm.py` | LM Studio client against a stub server: model selection, strategy negotiation, `reasoning_content` recovery, JSON extraction, retry |
| `test_agent.py` | Heuristic fallback, LLM path, **LLM-gets-no-DB-handle assertion**, approval queue, replay |
| `test_reports.py` | Utilization/downtime math, window filtering, kill-switch blocks checkout |
| `test_rentals.py`, `test_analytics.py`, `test_dashboard.py`, `test_generator.py`, `test_auth.py`, `test_register.py` | Phase 0 foundation + regressions |

---

## Tech stack

Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2.0 (async) · PostgreSQL + TimescaleDB ·
NGBoost · ruptures · pandas/NumPy/SciPy · LangGraph · LM Studio via HTTPX · APScheduler ·
smtplib · qrcode · pytest · Docker Compose
