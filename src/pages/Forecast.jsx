import React, { useState } from "react";
import { BandChart } from "@/components/charts";
import { Card, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TrendingUp, ArrowRight } from "lucide-react";

// Point this at your backend's forecast endpoint: GET /api/forecast?equipmentType=&site=
const EQUIPMENT_TYPES = ["Excavator", "Backhoe Loader", "Skid Steer", "Wheel Loader"];
const SITES = ["Site 01", "Site 02", "Site 03", "Site 04"];

const FORECAST_POINTS = [
  { label: "Aug", low: 8, median: 14, high: 21 },
  { label: "Sep", low: 11, median: 19, high: 27 },
  { label: "Oct", low: 15, median: 24, high: 34 },
  { label: "Nov", low: 9, median: 16, high: 23 },
];

const REBALANCE_RECS = [
  { unit: "EQX-1002", from: "Site 03", to: "Site 01", confidence: 82, reason: "Forecasted excavator demand at Site 01 exceeds available units in October" },
  { unit: "EQX-0654", from: "Site 04", to: "Site 02", confidence: 68, reason: "Skid steer utilization trending low at Site 04, rising demand at Site 02" },
];

export default function Forecast() {
  const [equipmentType, setEquipmentType] = useState(EQUIPMENT_TYPES[0]);
  const [site, setSite] = useState(SITES[0]);

  return (
    <div className="space-y-8">
      <div>
        <span className="font-mono text-xs uppercase tracking-widest text-signal">
          Probabilistic Demand Forecast
        </span>
        <h1 className="mt-2 font-display text-3xl font-bold uppercase tracking-wide text-rig-50">
          Demand &amp; Rebalancing
        </h1>
        <p className="mt-2 max-w-xl text-sm text-rig-400">
          Forecasted as a range with stated confidence, not a single guess —
          so you know how much to trust the number before pre-positioning
          equipment.
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <Select label="Equipment Type" value={equipmentType} options={EQUIPMENT_TYPES} onChange={setEquipmentType} />
        <Select label="Site" value={site} options={SITES} onChange={setSite} />
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div>
            <CardTitle>{equipmentType} Demand — {site}</CardTitle>
            <CardDescription>Shaded band = 80% confidence interval, line = median forecast</CardDescription>
          </div>
          <Badge variant="warn">
            <TrendingUp className="h-3 w-3" />
            Trending up
          </Badge>
        </CardHeader>
        <BandChart points={FORECAST_POINTS} />
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Rebalancing Recommendations</CardTitle>
          <CardDescription>Suggested pre-positioning based on forecasted demand gaps</CardDescription>
        </CardHeader>
        <div className="space-y-3">
          {REBALANCE_RECS.map((rec) => (
            <div
              key={rec.unit}
              className="flex flex-col gap-3 rounded-tag border border-rig-700 bg-rig-800/50 p-4 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="flex items-center gap-3">
                <span className="font-mono text-sm font-semibold text-rig-50">{rec.unit}</span>
                <span className="flex items-center gap-1.5 font-mono text-xs text-rig-400">
                  {rec.from}
                  <ArrowRight className="h-3 w-3" />
                  {rec.to}
                </span>
              </div>
              <p className="max-w-md text-xs text-rig-500">{rec.reason}</p>
              <Badge variant={rec.confidence >= 75 ? "ok" : "warn"}>{rec.confidence}% confidence</Badge>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function Select({ label, value, options, onChange }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-display font-semibold uppercase tracking-widest text-rig-400">
        {label}
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-10 rounded-tag border border-rig-600 bg-rig-900 px-3 text-sm text-rig-50 focus-visible:outline-none focus-visible:border-signal"
      >
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    </label>
  );
}
