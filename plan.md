# Smart Rental Tracking System — Build Plan & Architecture

Legend: `[x]` done · `[ ]` todo · **P0** = required outcome, must ship · **P1** = differentiator, ship to win · **P2** = stretch, cut first

---

## Phase 0 — Core foundation (day 1)

- [x] Live asset dashboard with real-time fleet status
- [x] Telemetry logging: runtime hours, idle hours, fuel usage, operator IDs
- [x] QR/RFID-simulated check-in / check-out
- [x] Usage logging across sites
- [x] Automated overdue return alerts
- [x] Rule-based anomaly & misuse detection (NumPy mathematical scoring engine)
- [x] Core data pipeline operational

---

## Phase 1 — Data & validation foundation (P0 — everything below depends on this)

- [x] Synthetic fleet generator: 12–24 months of history, multiple sites, equipment types
- [x] Seasonality per equipment type (e.g. excavators peak pre-monsoon)
- [x] Planted anomalies mirroring sample data (idle machines, NULL sites, unassigned usage)
- [x] **Hidden degradation onsets with ground-truth dates** — post-onset fuel/hour drift, efficiency decline (this is what makes the USP accuracy claim possible)
- [ ] Seed script wired into docker-compose bring-up (one command = running system with demo fleet)

## Phase 2 — Demand forecasting + rebalancing (P0 forecast, P1 recommendations)

- [ ] Feature pipeline: rentals per equipment type × site × month
- [ ] NGBoost model → probability distributions, not point estimates
- [ ] Forecast API endpoint + dashboard panel ("80% chance S003 needs 3+ excavators in June")
- [ ] Rebalancing recommendations: greedy assignment of forecasted demand to idle equipment
- [ ] Attach ₹ saved to every recommendation ("Move EQX1004 to S003 by June 1 — saves ₹48k/month idle cost")

## Phase 3 — Behavioral anomaly layer (P1)

- [ ] Per-machine usage baseline model (expected engine/idle hours per machine-day, NGBoost)
- [ ] Flag actuals outside 95% prediction interval, with quantified explanation
- [ ] Merge into existing anomaly feed (rules layer stays; this stacks on top)

## Phase 4 — Degradation tracing (P1 — THE USP)

- [ ] Health signal series per machine: fuel per engine-hour, efficiency, idle drift
- [ ] Change-point detection on the series (`ruptures` PELT or CUSUM)
- [ ] Onset attribution: map detected change-point → rental, site, operator in custody
- [ ] Per-machine health timeline view in dashboard (life across rentals, red onset marker)
- [ ] Early-intervention savings estimate per detection (₹ caught-early vs repair-at-failure)
- [ ] **Accuracy validation against ground truth** — "traced onset within ±N days on X% of fleet" (this number goes on the slide)

## Phase 5 — Reasoning layer (P1 agent, P2 NL query)

- [ ] LM Studio structured-output client (OpenAI-compatible endpoint via HTTPX, JSON schema enforced)
- [ ] LangGraph investigator agent: anomaly fires → bounded graph (fetch usage logs → operator history → contract/site context → synthesize case file with verdict + recommended action)
- [ ] Human approval queue for agent recommendations (approve/reject in dashboard)
- [ ] Cache one good agent run as demo fallback (local models flake; replays don't)
- [ ] NL querying: LLM → Pydantic-validated query spec (metric, filters, group-by, time range) → whitelisted SQLAlchemy — never raw SQL

## Phase 6 — Platform envelope (P0 unless marked)

- [x] Multi-tenant scoping: tenant_id on all tables + tenant claim in login/JWT
- [ ] Email delivery for alerts via smtplib (app-password SMTP; in-app alerts stay the demo path)
- [ ] Summary reports: total rented hours, per-site utilization, downtime, idle ratios
- [ ] Remote immobilization as simulated kill-switch (P1 — promised in day-1 summary): dealer toggles disabled flag → machine blocked from check-out, marked on dashboard
- [ ] Sustainability counter (P2, one line of code): idle hours → diesel litres → CO₂ on dashboard

## Phase 7 — Testing & delivery (P0 — promised in submission)

- [x] pytest smoke & functional suites (auth, registration, generator determinism, QR codes, rental lifecycle)
- [ ] docker-compose: single-command bring-up, seeded, no manual steps
- [ ] README: run instructions + architecture sketch (judges may open the repo)

## Phase 8 — Demo & pitch prep

- [ ] Demo script (2–3 min arc): problem number → live dashboard → QR check-out on phone → anomaly fires → click into investigator case file → degradation timeline with onset marker → forecast + rebalancing panel with ₹ saved
- [ ] One business number on the title slide (₹ lost per year to idle rented equipment)
- [ ] Accuracy slide: degradation onset detection % from Phase 4 validation
- [ ] Rehearse answers: "why not sensor telematics?" (works on data dealers already have, zero hardware, old + third-party machines) · "what did the ML learn a threshold wouldn't?" · "how is the LLM kept safe from the DB?" (validated query spec, never raw SQL)
- [ ] Pre-demo: reset seed data, cached agent replay ready, kill-switch demo machine chosen

---

# Mathematical Architecture & Algorithmic Formulation

## 1. NumPy Vectorized Anomaly & Misuse Scoring Engine

To quantify asset health and operational misuse, the backend calculates an **Anomaly & Misuse Score ($0 - 100$)** for every asset using vectorized NumPy operations over daily telemetry logs (engine hours $\mathbf{E}$, idle hours $\mathbf{I}$, fuel consumption $\mathbf{F}$, and assignment indicator $\mathbf{U}$).

### A. Underutilization / Excessive Idle Ratio ($S_{\text{idle}} \in [0, 1]$)
Measures the exact percentage of total runtime spent wasting fuel at idle:
$$\mathbf{R} = \frac{\mathbf{I}}{\mathbf{E} + \mathbf{I} + \epsilon} \implies S_{\text{idle}} = \text{mean}(\mathbf{R})$$
*(where $\epsilon = 1\times 10^{-6}$ prevents zero-division errors).*

### B. Unassigned / Ghost Asset Operations ($S_{\text{ghost}} \in [0, 1]$)
Identifies usage logged without valid operator accountability or site tracking:
$$\mathbf{U}_k = \mathbb{I}(\text{Site ID}_k = \text{NULL} \lor \text{Operator ID}_k = \text{NULL}) \implies S_{\text{ghost}} = \text{mean}(\mathbf{U})$$
*(High scores indicate severe risks of unauthorized usage, subleasing, or equipment misallocation).*

### C. Fuel Efficiency Deviation Z-Score ($S_{\text{fuel}} \in [0, 1]$)
Evaluates mechanical health and fuel theft risk by evaluating standard deviation ($\sigma$) against fleet-wide baseline means ($\mu$) per equipment class:
$$\text{Rate}_k = \frac{\mathbf{F}_k}{\mathbf{E}_k + \mathbf{I}_k + \epsilon}, \quad Z_k = \frac{\text{Rate}_k - \mu}{\sigma + \epsilon} \implies S_{\text{fuel}} = \min\left(1.0, \max\left(0, \frac{\text{mean}(\mathbf{Z})}{3.0}\right)\right)$$

### D. Composite Anomaly & Misuse Score ($0 - 100$)
Combined via industry risk weighting ($45\%$ Idle Waste, $40\%$ Ghost Operations, $15\%$ Efficiency Deviation):
$$\text{Score} = \min\left(100, \left\lfloor 45 \cdot S_{\text{idle}} + 40 \cdot S_{\text{ghost}} + 15 \cdot S_{\text{fuel}} \right\rceil\right)$$

#### Classification Thresholds:
* 🔴 **Critical Anomaly ($\text{Score} \ge 60$):** Severe misuse, ghost operations, or excessive fuel burning without active work.
* 🟡 **Warning ($35 \le \text{Score} < 60$):** Moderate underutilization or missing log metadata.
* 🟢 **Normal ($\text{Score} < 35$):** Healthy asset operation and accountability.

---

## 2. Overdue Return Alerts & Deadline Calculation

The automated return management loop monitors active rentals and categorizes deadlines:
1. **Overdue Action:** Where current date $> \text{expected\_return\_date}$, the system automatically updates rental status from `active` to `overdue` and logs an overdue alert with the exact day differential.
2. **Approaching Deadline Warning:** Where $0 \le (\text{expected\_return\_date} - \text{today}) \le 2 \text{ days}$, the system generates preventative warning notifications so managers can coordinate check-ins before penalties accrue.