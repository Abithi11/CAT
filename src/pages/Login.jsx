import React, { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";
import { useAuth } from "@/context/AuthContext";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [tenant, setTenant] = useState("");
  const [role, setRole] = useState("dealer");
  const [operatorId, setOperatorId] = useState("");
  const [site, setSite] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  function handleSubmit(e) {
    e.preventDefault();
    if (!operatorId.trim() || !password.trim()) {
      setError("Enter your operator ID and password to continue.");
      return;
    }
    setError("");
    login({
      operatorId: operatorId.trim().toUpperCase(),
      site: site.trim() || "01",
      tenant: tenant.trim() || "default-dealer",
      role,
    });
    const redirectTo = location.state?.from || "/home";
    navigate(redirectTo, { replace: true });
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-rig-900 px-6">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-1.5 hazard-edge" />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-1.5 hazard-edge" />

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
        className="w-full max-w-sm"
      >
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-tag bg-signal text-rig-950 font-display text-xl font-bold">
            AR
          </div>
          <h1 className="font-display text-3xl font-bold uppercase tracking-wide text-rig-50">
            Argus
          </h1>
          <p className="mt-1 text-sm text-rig-400">
            Sign in to access the smart rental tracking console
          </p>
        </div>

        <Card>
          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-2">
              <Label>Workspace Access</Label>
              <div className="flex overflow-hidden rounded-tag border border-rig-600">
                {[
                  { value: "dealer", label: "Dealer" },
                  { value: "customer", label: "Customer" },
                ].map((opt) => (
                  <button
                    type="button"
                    key={opt.value}
                    onClick={() => setRole(opt.value)}
                    className={`flex-1 py-2 text-xs font-display font-semibold uppercase tracking-wide transition-colors ${
                      role === opt.value
                        ? "bg-signal text-rig-950"
                        : "text-rig-400 hover:text-rig-50"
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="tenant">Dealer / Workspace ID</Label>
              <Input
                id="tenant"
                placeholder="ridgeline-equipment"
                value={tenant}
                onChange={(e) => setTenant(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="operatorId">Operator ID</Label>
              <Input
                id="operatorId"
                placeholder="OP-4471"
                value={operatorId}
                onChange={(e) => setOperatorId(e.target.value)}
                autoComplete="username"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="site">Site Code (optional)</Label>
              <Input
                id="site"
                placeholder="04"
                value={site}
                onChange={(e) => setSite(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            </div>

            {error && (
              <p className="text-sm text-rust" role="alert">
                {error}
              </p>
            )}

            <Button type="submit" className="w-full" size="lg">
              Sign In
              <ArrowRight className="h-4 w-4" />
            </Button>

            <p className="text-center text-xs text-rig-500">
              Demo build — any operator ID and password will sign you in.
            </p>
          </form>
        </Card>
      </motion.div>
    </div>
  );
}
