import React, { useState } from "react";
import { motion } from "framer-motion";
import { AlertOctagon, ShieldCheck, User, MapPin, Calendar } from "lucide-react";
import { DegradationChart } from "@/components/charts";
import { Card, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

// Point this at your backend's degradation-tracing endpoint:
// GET /api/machines/:id/health — expects { series, baselineLow, baselineHigh,
// changePointIndex, attribution: { rentalId, site, operatorId, onsetDate } }
const MACHINES = [
  {
    id: "EQX-1002",
    type: "Excavator",
    metric: "Fuel per engine-hour (L/hr)",
    healthy: true,
    baselineLow: 8,
    baselineHigh: 11,
    changePointIndex: null,
    series: Array.from({ length: 20 }, (_, i) => ({ value: 9 + Math.sin(i / 3) * 1.1 })),
  },
  {
    id: "EQX-0871",
    type: "Backhoe Loader",
    metric: "Fuel per engine-hour (L/hr)",
    healthy: false,
    baselineLow: 6,
    baselineHigh: 8.5,
    changePointIndex: 13,
    series: [
      ...Array.from({ length: 13 }, (_, i) => ({ value: 7.2 + Math.sin(i / 2) * 0.6 })),
      ...Array.from({ length: 8 }, (_, i) => ({ value: 10.5 + i * 0.4 })),
    ],
    attribution: {
      rentalId: "RNT-58213",
      site: "Site 02",
      operatorId: "OP-4471",
      onsetDate: "2026-07-18",
    },
    savingsEstimate: "$2,150",
  },
];

export default function Health() {
  const [selectedId, setSelectedId] = useState(MACHINES[1].id);
  const machine = MACHINES.find((m) => m.id === selectedId);

  return (
    <div className="space-y-8">
      <div>
        <span className="font-mono text-xs uppercase tracking-widest text-signal">
          Degradation Tracing
        </span>
        <h1 className="mt-2 font-display text-3xl font-bold uppercase tracking-wide text-rig-50">
          Machine Health Timeline
        </h1>
        <p className="mt-2 max-w-xl text-sm text-rig-400">
          Change-point detection across each machine's full usage history —
          pinpointing when degradation began and which rental, site, and
          operator held custody at the time.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {MACHINES.map((m) => (
          <button
            key={m.id}
            onClick={() => setSelectedId(m.id)}
            className={`flex items-center gap-2 rounded-tag border px-3 py-2 text-xs font-display font-semibold uppercase tracking-wide transition-colors ${
              selectedId === m.id
                ? "border-signal bg-rig-800 text-signal"
                : "border-rig-600 text-rig-400 hover:text-rig-50"
            }`}
          >
            {m.healthy ? (
              <ShieldCheck className="h-3.5 w-3.5 text-ok" />
            ) : (
              <AlertOctagon className="h-3.5 w-3.5 text-rust" />
            )}
            {m.id}
          </button>
        ))}
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div>
            <CardTitle>{machine.id} — {machine.type}</CardTitle>
            <CardDescription>{machine.metric}, healthy baseline shaded green</CardDescription>
          </div>
          <Badge variant={machine.healthy ? "ok" : "danger"}>
            {machine.healthy ? "Within baseline" : "Degradation onset detected"}
          </Badge>
        </CardHeader>
        <DegradationChart
          series={machine.series}
          baselineLow={machine.baselineLow}
          baselineHigh={machine.baselineHigh}
          changePointIndex={machine.changePointIndex}
        />
      </Card>

      {!machine.healthy && machine.attribution && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
          <Card className="border-rust/40 bg-rust/5">
            <CardHeader>
              <CardTitle className="text-rust">Custody Attribution</CardTitle>
              <CardDescription>
                Evidence for maintenance timing and damage-dispute resolution
              </CardDescription>
            </CardHeader>
            <div className="grid gap-4 sm:grid-cols-2">
              <AttributionRow icon={Calendar} label="Onset Date" value={machine.attribution.onsetDate} />
              <AttributionRow icon={MapPin} label="Site" value={machine.attribution.site} />
              <AttributionRow icon={User} label="Operator" value={machine.attribution.operatorId} />
              <AttributionRow icon={AlertOctagon} label="Rental" value={machine.attribution.rentalId} />
            </div>
            <div className="mt-4 rounded-tag border border-rig-700 bg-rig-900/60 p-4 text-sm text-rig-300">
              Early intervention at onset vs. repair-at-failure estimated to
              save <span className="font-mono font-semibold text-signal">{machine.savingsEstimate}</span> on this unit.
            </div>
          </Card>
        </motion.div>
      )}
    </div>
  );
}

function AttributionRow({ icon: Icon, label, value }) {
  return (
    <div className="flex items-center gap-3 rounded-tag border border-rig-700 bg-rig-800/50 px-4 py-3">
      <Icon className="h-4 w-4 text-rust" />
      <div>
        <div className="text-xs uppercase tracking-widest text-rig-500">{label}</div>
        <div className="font-mono text-sm text-rig-50">{value}</div>
      </div>
    </div>
  );
}
