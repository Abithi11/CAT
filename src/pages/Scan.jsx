import React, { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { QrCode, Camera, CameraOff, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { Html5Qrcode } from "html5-qrcode";
import { Card, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/context/AuthContext";

// Point this at your backend's check-in/check-out endpoint.
const CHECKIN_ENDPOINT = "/api/checkins";
const SCANNER_ELEMENT_ID = "argus-qr-reader";

export default function Scan() {
  const { operator } = useAuth();
  const [mode, setMode] = useState("check-in");
  const [scanning, setScanning] = useState(false);
  const [manualCode, setManualCode] = useState("");
  const [log, setLog] = useState([]);
  const [cameraError, setCameraError] = useState("");
  const scannerRef = useRef(null);

  useEffect(() => {
    return () => {
      stopScanner();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function startScanner() {
    setCameraError("");
    try {
      const scanner = new Html5Qrcode(SCANNER_ELEMENT_ID);
      scannerRef.current = scanner;
      await scanner.start(
        { facingMode: "environment" },
        { fps: 10, qrbox: { width: 240, height: 240 } },
        (decodedText) => {
          handleDecoded(decodedText);
        },
        () => {
          // per-frame decode failures are expected while framing the code; ignore
        }
      );
      setScanning(true);
    } catch (err) {
      setCameraError(
        "Couldn't access the camera. Check browser permissions or use manual entry below."
      );
      setScanning(false);
    }
  }

  async function stopScanner() {
    const scanner = scannerRef.current;
    if (scanner) {
      try {
        await scanner.stop();
        await scanner.clear();
      } catch {
        // scanner already stopped
      }
      scannerRef.current = null;
    }
    setScanning(false);
  }

  async function handleDecoded(rawValue) {
    await stopScanner();
    submitEvent(rawValue);
  }

  function handleManualSubmit(e) {
    e.preventDefault();
    if (!manualCode.trim()) return;
    submitEvent(manualCode.trim());
    setManualCode("");
  }

  async function submitEvent(assetCode) {
    const entry = {
      id: crypto.randomUUID(),
      assetCode,
      mode,
      operatorId: operator?.operatorId ?? "UNKNOWN",
      site: operator?.site ?? "—",
      timestamp: new Date().toISOString(),
      status: "pending",
    };
    setLog((prev) => [entry, ...prev]);

    try {
      const res = await fetch(CHECKIN_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          assetCode,
          eventType: mode,
          operatorId: entry.operatorId,
          site: entry.site,
          timestamp: entry.timestamp,
        }),
      });
      updateEntry(entry.id, res.ok ? "success" : "failed");
    } catch {
      updateEntry(entry.id, "failed");
    }
  }

  function updateEntry(id, status) {
    setLog((prev) => prev.map((e) => (e.id === id ? { ...e, status } : e)));
  }

  return (
    <div className="space-y-8">
      <div>
        <span className="font-mono text-xs uppercase tracking-widest text-signal">
          Check-In / Check-Out
        </span>
        <h1 className="mt-2 font-display text-3xl font-bold uppercase tracking-wide text-rig-50">
          Scan Equipment
        </h1>
        <p className="mt-2 max-w-xl text-sm text-rig-400">
          Scan a unit's QR or RFID tag to log a check-in or check-out event.
          Each scan is sent to the backend with your operator ID, site, and a
          timestamp for the audit trail.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader className="flex-row items-center justify-between">
            <div>
              <CardTitle>Scanner</CardTitle>
              <CardDescription>Point the camera at the unit's tag</CardDescription>
            </div>
            <div className="flex overflow-hidden rounded-tag border border-rig-600">
              {["check-in", "check-out"].map((m) => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  className={`px-3 py-1.5 text-xs font-display font-semibold uppercase tracking-wide transition-colors ${
                    mode === m ? "bg-signal text-rig-950" : "text-rig-400 hover:text-rig-50"
                  }`}
                >
                  {m}
                </button>
              ))}
            </div>
          </CardHeader>

          <div className="relative flex aspect-square w-full items-center justify-center overflow-hidden rounded-tag border border-rig-700 bg-rig-950">
            <div id={SCANNER_ELEMENT_ID} className="h-full w-full [&_video]:h-full [&_video]:w-full [&_video]:object-cover" />
            {!scanning && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-rig-950/90 p-6 text-center">
                <QrCode className="h-10 w-10 text-rig-600" />
                <p className="text-sm text-rig-500">
                  Camera is off. Start scanning to detect a tag automatically.
                </p>
              </div>
            )}
          </div>

          {cameraError && (
            <p className="mt-3 text-sm text-rust">{cameraError}</p>
          )}

          <div className="mt-4 flex gap-3">
            {!scanning ? (
              <Button onClick={startScanner} className="flex-1">
                <Camera className="h-4 w-4" />
                Start Scanning
              </Button>
            ) : (
              <Button onClick={stopScanner} variant="secondary" className="flex-1">
                <CameraOff className="h-4 w-4" />
                Stop Scanning
              </Button>
            )}
          </div>

          <form onSubmit={handleManualSubmit} className="mt-6 space-y-2 border-t border-rig-700 pt-5">
            <Label htmlFor="manual">Manual Entry</Label>
            <div className="flex gap-2">
              <Input
                id="manual"
                placeholder="EQX-1002"
                value={manualCode}
                onChange={(e) => setManualCode(e.target.value)}
              />
              <Button type="submit" variant="secondary">
                Log
              </Button>
            </div>
          </form>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Scan Log</CardTitle>
            <CardDescription>Most recent events this session</CardDescription>
          </CardHeader>

          <div className="space-y-3">
            <AnimatePresence initial={false}>
              {log.length === 0 && (
                <p className="text-sm text-rig-500">No scans logged yet.</p>
              )}
              {log.map((entry) => (
                <motion.div
                  key={entry.id}
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="flex items-center justify-between rounded-tag border border-rig-700 bg-rig-800/50 px-3 py-2.5"
                >
                  <div>
                    <div className="font-mono text-sm text-rig-50">{entry.assetCode}</div>
                    <div className="text-xs text-rig-500">
                      {entry.mode} · {entry.operatorId} · site {entry.site}
                    </div>
                  </div>
                  <StatusIcon status={entry.status} />
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </Card>
      </div>
    </div>
  );
}

function StatusIcon({ status }) {
  if (status === "pending") return <Loader2 className="h-4 w-4 animate-spin text-rig-500" />;
  if (status === "success") return <Badge variant="ok"><CheckCircle2 className="h-3 w-3" />Sent</Badge>;
  return <Badge variant="danger"><XCircle className="h-3 w-3" />Failed</Badge>;
}
