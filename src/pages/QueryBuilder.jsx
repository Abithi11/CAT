import React, { useState } from "react";
import { motion } from "framer-motion";
import { Terminal, Wand2, Copy, Check, Loader2 } from "lucide-react";
import { Card, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

// Point this at your backend's NL-to-query endpoint. It should accept
// { text } and return { intent, filters, structuredQuery }.
const QUERY_ENDPOINT = "/api/query/parse";

const EXAMPLES = [
  "Show every excavator idle for more than 5 hours at site 04",
  "List units with no operator assigned in the last 24 hours",
  "Which rentals are overdue for return this week?",
  "Fuel usage for EQX-1002 over the past 7 days",
];

export default function QueryBuilder() {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!text.trim() || loading) return;
    setLoading(true);
    setError("");
    setResult(null);

    try {
      const res = await fetch(QUERY_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text.trim() }),
      });
      if (!res.ok) throw new Error("Request failed");
      const data = await res.json();
      setResult(data);
    } catch {
      setError("Couldn't reach the query backend. Confirm /api/query/parse is wired up.");
    } finally {
      setLoading(false);
    }
  }

  function handleCopy() {
    if (!result) return;
    navigator.clipboard.writeText(JSON.stringify(result, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="space-y-8">
      <div>
        <span className="font-mono text-xs uppercase tracking-widest text-signal">
          Natural Language Query
        </span>
        <h1 className="mt-2 font-display text-3xl font-bold uppercase tracking-wide text-rig-50">
          Query Builder
        </h1>
        <p className="mt-2 max-w-xl text-sm text-rig-400">
          Describe what you want to know in plain language. It's converted
          into a structured query the backend and LLM can process directly
          against fleet telemetry.
        </p>
      </div>

      <Card>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="relative">
            <Terminal className="pointer-events-none absolute left-3.5 top-3.5 h-4 w-4 text-rig-500" />
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={3}
              placeholder="e.g. Show every unit idle for more than 5 hours at site 04"
              className="w-full resize-none rounded-tag border border-rig-600 bg-rig-900 py-3 pl-10 pr-3 text-sm text-rig-50 placeholder:text-rig-500 focus-visible:outline-none focus-visible:border-signal"
            />
          </div>

          <div className="flex flex-wrap gap-2">
            {EXAMPLES.map((ex) => (
              <button
                type="button"
                key={ex}
                onClick={() => setText(ex)}
                className="rounded-tag border border-rig-600 px-3 py-1.5 text-xs text-rig-300 transition-colors hover:border-signal/60 hover:text-signal"
              >
                {ex}
              </button>
            ))}
          </div>

          <Button type="submit" disabled={loading || !text.trim()}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
            Build Query
          </Button>

          {error && <p className="text-sm text-rust">{error}</p>}
        </form>
      </Card>

      {result && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <div>
                <CardTitle>Structured Query</CardTitle>
                <CardDescription>Ready to send to the LLM or query engine</CardDescription>
              </div>
              <div className="flex items-center gap-2">
                {result.intent && <Badge variant="warn">{result.intent}</Badge>}
                <Button variant="ghost" size="icon" onClick={handleCopy} type="button">
                  {copied ? <Check className="h-4 w-4 text-ok" /> : <Copy className="h-4 w-4" />}
                </Button>
              </div>
            </CardHeader>
            <pre className="overflow-x-auto rounded-tag border border-rig-700 bg-rig-950 p-4 font-mono text-xs leading-relaxed text-rig-200">
{JSON.stringify(result, null, 2)}
            </pre>
          </Card>
        </motion.div>
      )}
    </div>
  );
}
