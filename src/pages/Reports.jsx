import React, { useState } from "react";
import { motion } from "framer-motion";
import { BarChart } from "@/components/charts";
import { Card, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Clock, TrendingDown, Activity, ArrowUpRight } from "lucide-react";

// Point this at your backend's rollup endpoint: GET /api/reports/utilization
const SITE_ROLLUPS = [
  { site: "Site 01", rentedHours: 412, downtimeHours: 18, utilization: 91 },
  { site: "Site 02", rentedHours: 356, downtimeHours: 44, utilization: 78 },
  { site: "Site 03", rentedHours: 190, downtimeHours: 61, utilization: 52 },
  { site: "Site 04", rentedHours: 288, downtimeHours: 22, utilization: 84 },
];

const fadeUp = {
  hidden: { opacity: 0, y: 16 },
  show: (i = 0) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.5, delay: i * 0.06, ease: [0.16, 1, 0.3, 1] },
  }),
};

export default function Reports() {
  const [range, setRange] = useState("30d");
  const totalRented = SITE_ROLLUPS.reduce((sum, s) => sum + s.rentedHours, 0);
  const totalDowntime = SITE_ROLLUPS.reduce((sum, s) => sum + s.downtimeHours, 0);
  const avgUtilization = Math.round(
    SITE_ROLLUPS.reduce((sum, s) => sum + s.utilization, 0) / SITE_ROLLUPS.length
  );

  const kpis = [
    { icon: Clock, value: `${totalRented}h`, label: "Total Rented Hours", tint: "text-signal bg-signal/10" },
    { icon: TrendingDown, value: `${totalDowntime}h`, label: "Total Downtime", tint: "text-rust bg-rust/10" },
    { icon: Activity, value: `${avgUtilization}%`, label: "Avg Utilization", tint: "text-ok bg-ok/10" },
  ];

  return (
    <div className="space-y-8">
      {/* Hero block */}
      <motion.div
        initial="hidden"
        animate="show"
        variants={fadeUp}
        className="relative overflow-hidden rounded-tag border border-rig-700 bg-rig-800"
      >
        <div className="pointer-events-none absolute inset-y-0 right-0 w-24 hazard-edge opacity-60 sm:w-32" />
        <div className="relative flex flex-wrap items-end justify-between gap-6 p-6 sm:p-8">
          <div>
            <span className="font-mono text-xs uppercase tracking-widest text-signal">
              Roll-Up Reporting
            </span>
            <h1 className="mt-2 font-display text-4xl font-bold uppercase leading-none tracking-wide text-rig-50 sm:text-5xl">
              Utilization &amp; Downtime
            </h1>
            <p className="mt-3 max-w-xl text-sm text-rig-400">
              Rented hours, downtime, and utilization rolled up per site across
              the selected window.
            </p>
          </div>
          <div className="relative flex overflow-hidden rounded-tag border border-rig-600 bg-rig-900">
            {["7d", "30d", "90d"].map((r) => (
              <button
                key={r}
                onClick={() => setRange(r)}
                className={`px-4 py-2 text-xs font-display font-semibold uppercase tracking-wide transition-colors ${
                  range === r ? "bg-signal text-rig-950" : "text-rig-400 hover:text-rig-50"
                }`}
              >
                {r}
              </button>
            ))}
          </div>
        </div>
      </motion.div>

      {/* KPI row */}
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {kpis.map(({ icon: Icon, value, label, tint }, i) => (
          <motion.div key={label} custom={i + 1} initial="hidden" animate="show" variants={fadeUp}>
            <Card className="p-6">
              <div className={`mb-4 flex h-10 w-10 items-center justify-center rounded-tag ${tint}`}>
                <Icon className="h-5 w-5" />
              </div>
              <div className="font-mono text-3xl font-bold text-rig-50">{value}</div>
              <div className="mt-1.5 text-xs uppercase tracking-widest text-rig-500">{label}</div>
            </Card>
          </motion.div>
        ))}
      </section>

      {/* Chart card -- now sized to actually use the space it's given */}
      <motion.div custom={4} initial="hidden" animate="show" variants={fadeUp}>
        <Card>
          <CardHeader className="flex-row items-start justify-between">
            <div>
              <CardTitle>Utilization by Site</CardTitle>
              <CardDescription>Percent of available machine-hours actually rented</CardDescription>
            </div>
            <div className="hidden gap-4 font-mono text-[11px] uppercase tracking-widest text-rig-500 sm:flex">
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-ok" />
                75%+
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-signal" />
                55-74%
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-rust" />
                &lt;55%
              </span>
            </div>
          </CardHeader>
          <div className="h-[340px] sm:h-[420px]">
            <BarChart
              data={SITE_ROLLUPS}
              valueKey="utilization"
              labelKey="site"
              unit="%"
              height={420}
              colorByStatus
              goodMin={75}
              warnMin={55}
            />
          </div>
        </Card>
      </motion.div>

      {/* Site breakdown table */}
      <motion.div custom={5} initial="hidden" animate="show" variants={fadeUp}>
        <Card className="overflow-hidden p-0">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-rig-700 p-5">
            <div>
              <CardTitle>Site Breakdown</CardTitle>
              <CardDescription>Rented hours vs downtime, {range}</CardDescription>
            </div>
          </div>
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-rig-700 text-xs uppercase tracking-widest text-rig-500">
                <th className="px-5 py-3 font-display font-semibold">Site</th>
                <th className="px-5 py-3 font-display font-semibold">Rented Hours</th>
                <th className="px-5 py-3 font-display font-semibold">Downtime</th>
                <th className="px-5 py-3 font-display font-semibold">Utilization</th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody>
              {SITE_ROLLUPS.map((row) => (
                <tr
                  key={row.site}
                  className="group border-b border-rig-800 font-mono text-rig-200 transition-colors last:border-0 hover:bg-rig-800/60"
                >
                  <td className="px-5 py-4 font-body font-semibold text-rig-50">{row.site}</td>
                  <td className="px-5 py-4">{row.rentedHours}h</td>
                  <td className="px-5 py-4">{row.downtimeHours}h</td>
                  <td className="px-5 py-4">
                    <Badge variant={row.utilization >= 75 ? "ok" : row.utilization >= 55 ? "warn" : "danger"}>
                      {row.utilization}%
                    </Badge>
                  </td>
                  <td className="px-5 py-4 text-right">
                    <ArrowUpRight className="ml-auto h-4 w-4 text-rig-600 opacity-0 transition-opacity group-hover:opacity-100" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </motion.div>
    </div>
  );
}
