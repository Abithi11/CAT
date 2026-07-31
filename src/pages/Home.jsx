import React from "react";
import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { QrCode, MessageSquare, Terminal, AlertTriangle, Gauge, Fuel, Clock, UserX, BellRing, HeartPulse, TrendingUp, BarChart3 } from "lucide-react";
import { ExcavatorArt } from "@/components/ExcavatorArt";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const FLEET_ROWS = [
  { id: "EQX-1002", type: "Excavator", site: "04", runtime: "118.4h", idle: "6.2h", fuel: "71%", operator: null, status: "anomaly" },
  { id: "EQX-0871", type: "Backhoe Loader", site: "02", runtime: "342.9h", idle: "12.1h", fuel: "54%", operator: "OP-4471", status: "active" },
  { id: "EQX-0654", type: "Skid Steer", site: "04", runtime: "22.0h", idle: "31.4h", fuel: "88%", operator: "OP-2209", status: "underutilized" },
  { id: "EQX-1140", type: "Wheel Loader", site: "01", runtime: "290.7h", idle: "4.0h", fuel: "23%", operator: "OP-1187", status: "overdue" },
];

const STATUS_MAP = {
  active: { label: "Active", variant: "ok" },
  anomaly: { label: "Unassigned", variant: "danger" },
  underutilized: { label: "Underutilized", variant: "warn" },
  overdue: { label: "Overdue Return", variant: "danger" },
};

export default function Home() {
  return (
    <div className="space-y-16">
      {/* HERO */}
      <section className="grid items-center gap-10 md:grid-cols-2">
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.5 }}
        >
          <span className="font-mono text-xs uppercase tracking-widest text-signal">
            Live Asset Dashboard
          </span>
          <h1 className="mt-3 font-display text-5xl font-bold uppercase leading-[1.05] tracking-wide text-rig-50 sm:text-6xl">
            Every machine,
            <br />
            accounted for.
          </h1>
          <p className="mt-5 max-w-md text-base leading-relaxed text-rig-400">
            Argus tracks runtime hours, idle time, fuel usage, and operator
            assignment across every rented unit in real time. QR and RFID
            check-in/check-out logs usage by site, flags overdue returns
            automatically, and surfaces anomalies — like equipment running
            with no assigned operator — before they become a problem.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/scan">
              <Button size="lg">
                <QrCode className="h-4 w-4" />
                Scan Equipment
              </Button>
            </Link>
            <Link to="/chat">
              <Button variant="secondary" size="lg">
                <MessageSquare className="h-4 w-4" />
                Ask the Assistant
              </Button>
            </Link>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.6, delay: 0.1 }}
          className="relative"
        >
          <ExcavatorArt className="w-full drop-shadow-[0_20px_40px_rgba(0,0,0,0.4)]" />
        </motion.div>
      </section>

      {/* STAT STRIP */}
      <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {[
          { icon: Gauge, label: "Units Tracked", value: "128" },
          { icon: Clock, label: "Avg Runtime / Wk", value: "61.3h" },
          { icon: Fuel, label: "Fleet Fuel Avg", value: "64%" },
          { icon: UserX, label: "Unassigned Flags", value: "3" },
        ].map(({ icon: Icon, label, value }) => (
          <Card key={label} className="p-5">
            <Icon className="mb-3 h-5 w-5 text-signal" />
            <div className="font-mono text-2xl font-semibold text-rig-50">{value}</div>
            <div className="mt-1 text-xs uppercase tracking-widest text-rig-500">{label}</div>
          </Card>
        ))}
      </section>

      {/* ANOMALY CALLOUT */}
      <section className="grid gap-4 md:grid-cols-2">
        <Link to="/alerts" className="tag-plate flex items-start gap-4 border-rust/40 bg-rust/5 p-5 transition-colors hover:border-rust/70">
          <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-rust" />
          <div>
            <p className="flex items-center gap-2 font-display font-semibold uppercase tracking-wide text-rig-50">
              Structural — EQX-1002
              <Badge variant="danger">Unassigned</Badge>
            </p>
            <p className="mt-1 text-sm text-rig-400">
              Unit is actively logging runtime at Site 04 with no operator ID
              attached to the session.
            </p>
          </div>
        </Link>
        <Link to="/alerts" className="tag-plate flex items-start gap-4 border-signal/40 bg-signal/5 p-5 transition-colors hover:border-signal/70">
          <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-signal" />
          <div>
            <p className="flex items-center gap-2 font-display font-semibold uppercase tracking-wide text-rig-50">
              Behavioral — EQX-0654
              <Badge variant="warn">Outlier</Badge>
            </p>
            <p className="mt-1 text-sm text-rig-400">
              Idle time is 31.4h this week — outside this unit's predicted
              4–14h baseline range.
            </p>
          </div>
        </Link>
      </section>

      {/* FLEET TABLE */}
      <section>
        <Card className="overflow-hidden p-0">
          <div className="flex items-center justify-between border-b border-rig-700 p-5">
            <div>
              <CardTitle>Fleet Telemetry</CardTitle>
              <CardDescription>Runtime, idle hours, fuel, and operator assignment by unit</CardDescription>
            </div>
            <Badge variant="ok">Live</Badge>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead>
                <tr className="border-b border-rig-700 text-xs uppercase tracking-widest text-rig-500">
                  <th className="px-5 py-3 font-display font-semibold">Unit</th>
                  <th className="px-5 py-3 font-display font-semibold">Site</th>
                  <th className="px-5 py-3 font-display font-semibold">Runtime</th>
                  <th className="px-5 py-3 font-display font-semibold">Idle</th>
                  <th className="px-5 py-3 font-display font-semibold">Fuel</th>
                  <th className="px-5 py-3 font-display font-semibold">Operator</th>
                  <th className="px-5 py-3 font-display font-semibold">Status</th>
                </tr>
              </thead>
              <tbody>
                {FLEET_ROWS.map((row) => (
                  <tr key={row.id} className="border-b border-rig-800 font-mono text-rig-200 last:border-0">
                    <td className="px-5 py-3">
                      <div className="font-semibold text-rig-50">{row.id}</div>
                      <div className="font-body text-xs text-rig-500">{row.type}</div>
                    </td>
                    <td className="px-5 py-3">{row.site}</td>
                    <td className="px-5 py-3">{row.runtime}</td>
                    <td className="px-5 py-3">{row.idle}</td>
                    <td className="px-5 py-3">{row.fuel}</td>
                    <td className="px-5 py-3">
                      {row.operator ?? <span className="text-rust">NULL</span>}
                    </td>
                    <td className="px-5 py-3">
                      <Badge variant={STATUS_MAP[row.status].variant}>
                        {STATUS_MAP[row.status].label}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </section>

      {/* QUICK LINKS */}
      <section className="grid gap-4 sm:grid-cols-2 md:grid-cols-4">
        <QuickLink to="/scan" icon={QrCode} title="Check-In / Check-Out" desc="Scan a unit's QR or RFID tag to log a site check-in or return." />
        <QuickLink to="/alerts" icon={BellRing} title="Alerts" desc="Overdue returns and anomaly case files from the investigator agent." />
        <QuickLink to="/health" icon={HeartPulse} title="Machine Health" desc="Degradation timelines with rental, site, and operator attribution." />
        <QuickLink to="/forecast" icon={TrendingUp} title="Forecast" desc="Probabilistic demand and rebalancing recommendations." />
        <QuickLink to="/reports" icon={BarChart3} title="Reports" desc="Per-site utilization, downtime, and rented-hour rollups." />
        <QuickLink to="/chat" icon={MessageSquare} title="Fleet Assistant" desc="Ask questions about utilization, alerts, or a specific unit." />
        <QuickLink to="/query" icon={Terminal} title="Query Builder" desc="Turn a plain-language request into a structured data query." />
      </section>
    </div>
  );
}

function QuickLink({ to, icon: Icon, title, desc }) {
  return (
    <Link to={to}>
      <Card className="group h-full transition-colors hover:border-signal/50">
        <Icon className="mb-3 h-5 w-5 text-signal" />
        <CardTitle className="text-base">{title}</CardTitle>
        <CardDescription className="mt-1">{desc}</CardDescription>
      </Card>
    </Link>
  );
}
