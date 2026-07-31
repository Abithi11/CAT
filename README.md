# Argus — Smart Rental Tracking Frontend

React + Vite + Tailwind CSS + Framer Motion + shadcn/ui-style components.

## Setup

```bash
npm install
npm run dev
```

## Pages

- `/login` — operator sign-in with dealer/customer workspace scoping (demo
  auth, stored in localStorage — swap in your real auth call inside
  `src/context/AuthContext.jsx`)
- `/home` — hero + live fleet telemetry dashboard (runtime, idle, fuel,
  operator assignment, structural + behavioral anomaly flags)
- `/scan` — camera-based QR/RFID scanner (via `html5-qrcode`) with manual
  entry fallback; posts check-in/check-out events to the backend
- `/alerts` — overdue-return and anomaly feed, with an investigator-agent
  case file view (evidence steps + verdict) per alert
- `/health` — degradation tracing: per-machine usage history against its
  healthy baseline, change-point marker, and custody attribution
  (rental/site/operator at onset)
- `/forecast` — probabilistic demand forecast (confidence band, not a point
  estimate) per equipment type/site/month, plus rebalancing recommendations
- `/reports` — per-site utilization, downtime, and rented-hours rollups
- `/chat` — LLM assistant chat interface for fleet questions
- `/query` — converts a plain-language request into a structured query
  payload for the LLM/query engine

## Wiring up your backend

Three fetch calls are stubbed with relative paths — point these at your
actual API (or add a Vite proxy in `vite.config.js`):

| File | Endpoint | Purpose |
|---|---|---|
| `src/pages/Scan.jsx` | `POST /api/checkins` | logs a check-in/check-out event |
| `src/pages/Chat.jsx` | `POST /api/chat` | sends `{ message, history }`, expects `{ reply }` |
| `src/pages/QueryBuilder.jsx` | `POST /api/query/parse` | sends `{ text }`, expects `{ intent, filters, structuredQuery }` |
| `src/pages/Alerts.jsx` | `GET /api/alerts`, `POST /api/alerts/:id/investigate` | alert feed; agent case file `{ steps, verdict }` |
| `src/pages/Health.jsx` | `GET /api/machines/:id/health` | usage series, baseline band, change-point index, attribution |
| `src/pages/Forecast.jsx` | `GET /api/forecast?equipmentType=&site=` | probability band per month, rebalancing recs |
| `src/pages/Reports.jsx` | `GET /api/reports/utilization` | per-site rented hours, downtime, utilization |

All four currently render with mocked sample data inline in each file —
swap the constant at the top of each page (e.g. `SITE_ROLLUPS`, `MACHINES`,
`ALERTS`) for a `fetch`/`useEffect` call once the corresponding endpoint is
live.

The fleet table on `/home` is currently populated with sample rows —
replace `FLEET_ROWS` in `src/pages/Home.jsx` with a fetch to your live
telemetry endpoint once it's ready.
