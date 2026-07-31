import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import {
  LogOut,
  Gauge,
  QrCode,
  MessageSquare,
  Terminal,
  BarChart3,
  TrendingUp,
  HeartPulse,
  BellRing,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { to: "/home", label: "Overview", icon: Gauge },
  { to: "/scan", label: "Scan", icon: QrCode },
  { to: "/alerts", label: "Alerts", icon: BellRing },
  { to: "/health", label: "Health", icon: HeartPulse },
  { to: "/forecast", label: "Forecast", icon: TrendingUp },
  { to: "/reports", label: "Reports", icon: BarChart3 },
  { to: "/chat", label: "Assistant", icon: MessageSquare },
  { to: "/query", label: "Query Builder", icon: Terminal },
];

export function Layout({ children }) {
  const { operator, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="min-h-screen bg-rig-900">
      <header className="sticky top-0 z-40 border-b border-rig-700 bg-rig-900/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-tag bg-signal text-rig-950 font-display font-bold">
              AR
            </div>
            <div className="flex flex-col leading-none">
              <span className="font-display text-lg font-semibold uppercase tracking-widest text-rig-50">
                Argus
              </span>
              {operator?.tenant && (
                <span className="font-mono text-[10px] text-rig-500">{operator.tenant}</span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-3">
            {operator && (
              <span className="hidden items-center gap-2 font-mono text-xs text-rig-500 sm:flex">
                {operator.operatorId} · SITE {operator.site}
                <span className="rounded-tag border border-rig-600 px-1.5 py-0.5 text-[10px] uppercase tracking-widest text-rig-400">
                  {operator.role}
                </span>
              </span>
            )}
            <button
              onClick={handleLogout}
              className="flex items-center gap-2 rounded-tag border border-rig-600 px-3 py-2 text-xs font-display font-semibold uppercase tracking-wide text-rig-300 transition-colors hover:border-rust/60 hover:text-rust"
            >
              <LogOut className="h-3.5 w-3.5" />
              Logout
            </button>
          </div>
        </div>

        <nav className="flex items-center gap-1 overflow-x-auto border-t border-rig-800 px-4 py-2">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-1.5 whitespace-nowrap rounded-tag px-3 py-1.5 text-xs font-display font-semibold uppercase tracking-wide transition-colors",
                  isActive ? "bg-rig-800 text-signal" : "text-rig-400 hover:text-rig-50"
                )
              }
            >
              <Icon className="h-3.5 w-3.5" />
              {label}
            </NavLink>
          ))}
        </nav>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-10">{children}</main>
    </div>
  );
}
