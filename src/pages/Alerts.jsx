import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, Clock, Mail, UserX, Activity, ChevronRight, FileSearch, Check } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

// Point this at your backend's alerts feed: GET /api/alerts
// The investigator case file is produced by the LangGraph agent when an
// alert fires: POST /api/alerts/:id/investigate — expects a { steps, verdict }
// evidence trail like the mocked one below.
const ALERTS = [
  {
    id: "a1",
    type: "overdue",
    unit: "EQX-1140",
    site: "Site 01",
    detail: "Return was due 2 days ago — no check-in logged",
    emailSent: true,
  },
  {
    id: "a2",
    type: "structural",
    unit: "EQX-1002",
    site: "Site 04",
    detail: "Unit actively logging runtime with no operator ID assigned",
    emailSent: true,
  },
  {
    id: "a3",
    type: "behavioral",
    unit: "EQX-0654",
    site: "Site 04",
    detail: "Idle time 31.4h/wk falls outside this unit's predicted range (4–14h)",
    emailSent: false,
  },
];

const TYPE_META = {
  overdue: { icon: Clock, label: "Overdue Return", variant: "danger" },
  structural: { icon: UserX, label: "Unassigned Usage", variant: "danger" },
  behavioral: { icon: Activity, label: "Behavioral Outlier", variant: "warn" },
};

const CASE_FILES = {
  a2: {
    steps: [
      "Pulled usage log for EQX-1002 — active session, runtime accruing at Site 04.",
      "Checked operator assignment table — no operator ID bound to this session.",
      "Reviewed contract terms for the active rental — operator sign-off was not completed at check-out.",
      "Cross-referenced site check-in log — QR check-out scanned, RFID operator badge scan missing.",
    ],
    verdict: "Structural anomaly confirmed: equipment in active use without a bound operator. Recommend flagging the check-out for manual review before further runtime accrues.",
  },
  a3: {
    steps: [
      "Pulled EQX-0654's predicted idle-time range from its usage baseline model (4–14h/week).",
      "Compared against this week's logged idle time: 31.4h.",
      "Checked site-level context — Site 04 utilization has been trending down for 3 weeks.",
      "Checked for maintenance holds — none recorded, unit is marked available.",
    ],
    verdict: "Behavioral outlier confirmed, not explained by a maintenance hold. Likely underutilization — a rebalancing candidate rather than a fault.",
  },
};

export default function Alerts() {
  const [openId, setOpenId] = useState(null);
  const [investigated, setInvestigated] = useState({});

  function investigate(id) {
    setInvestigated((prev) => ({ ...prev, [id]: "loading" }));
    setTimeout(() => {
      setInvestigated((prev) => ({ ...prev, [id]: "done" }));
    }, 900);
  }

  return (
    <div className="space-y-8">
      <div>
        <span className="font-mono text-xs uppercase tracking-widest text-signal">
          Alerts &amp; Anomalies
        </span>
        <h1 className="mt-2 font-display text-3xl font-bold uppercase tracking-wide text-rig-50">
          Alert Feed
        </h1>
        <p className="mt-2 max-w-xl text-sm text-rig-400">
          Overdue returns and structural or behavioral anomalies. Open a case
          file to see the investigator agent's evidence trail before acting.
        </p>
      </div>

      <div className="space-y-3">
        {ALERTS.map((alert) => {
          const meta = TYPE_META[alert.type];
          const Icon = meta.icon;
          const isOpen = openId === alert.id;
          const caseFile = CASE_FILES[alert.id];
          const status = investigated[alert.id];

          return (
            <Card key={alert.id} className="p-0">
              <button
                onClick={() => setOpenId(isOpen ? null : alert.id)}
                className="flex w-full items-center justify-between gap-4 p-5 text-left"
              >
                <div className="flex items-center gap-4">
                  <div className={`flex h-10 w-10 items-center justify-center rounded-tag ${meta.variant === "danger" ? "bg-rust/15" : "bg-signal/15"}`}>
                    <Icon className={`h-5 w-5 ${meta.variant === "danger" ? "text-rust" : "text-signal"}`} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-semibold text-rig-50">{alert.unit}</span>
                      <Badge variant={meta.variant}>{meta.label}</Badge>
                    </div>
                    <p className="mt-1 text-sm text-rig-400">{alert.detail}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  {alert.emailSent && (
                    <span className="hidden items-center gap-1 text-xs text-rig-500 sm:flex">
                      <Mail className="h-3.5 w-3.5" />
                      Emailed
                    </span>
                  )}
                  <ChevronRight className={`h-4 w-4 text-rig-500 transition-transform ${isOpen ? "rotate-90" : ""}`} />
                </div>
              </button>

              <AnimatePresence>
                {isOpen && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="overflow-hidden border-t border-rig-700"
                  >
                    <div className="p-5">
                      {!caseFile ? (
                        <p className="text-sm text-rig-500">No investigator case file available for this alert type.</p>
                      ) : !status ? (
                        <Button size="sm" variant="secondary" onClick={() => investigate(alert.id)}>
                          <FileSearch className="h-3.5 w-3.5" />
                          Run Investigator Agent
                        </Button>
                      ) : status === "loading" ? (
                        <p className="flex items-center gap-2 text-sm text-rig-400">
                          <span className="h-2 w-2 animate-pulse rounded-full bg-signal" />
                          Agent walking usage logs, operator history, and contract terms…
                        </p>
                      ) : (
                        <div className="space-y-4">
                          <ol className="space-y-2">
                            {caseFile.steps.map((step, i) => (
                              <li key={i} className="flex items-start gap-2 text-sm text-rig-300">
                                <span className="mt-0.5 font-mono text-xs text-rig-600">{String(i + 1).padStart(2, "0")}</span>
                                {step}
                              </li>
                            ))}
                          </ol>
                          <div className="flex items-start gap-2 rounded-tag border border-signal/30 bg-signal/10 p-3">
                            <Check className="mt-0.5 h-4 w-4 flex-shrink-0 text-signal" />
                            <p className="text-sm text-rig-100">{caseFile.verdict}</p>
                          </div>
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
