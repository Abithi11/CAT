import React, { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Send, Bot, User, Loader2 } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

// Point this at your backend's chat/completion endpoint.
const CHAT_ENDPOINT = "/api/chat";

const SUGGESTIONS = [
  "Which units are currently overdue for return?",
  "Show me anything flagged with no operator assigned.",
  "What's the idle time on EQX-1002 this week?",
  "Which sites have the most underutilized equipment?",
];

const WELCOME = {
  id: "welcome",
  role: "assistant",
  content:
    "I'm the Argus assistant. Ask me about equipment status, utilization, overdue returns, or anomalies across your rental fleet.",
};

export default function Chat() {
  const [messages, setMessages] = useState([WELCOME]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  async function sendMessage(text) {
    const trimmed = text.trim();
    if (!trimmed || loading) return;

    const userMsg = { id: crypto.randomUUID(), role: "user", content: trimmed };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch(CHAT_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: trimmed,
          history: messages.map(({ role, content }) => ({ role, content })),
        }),
      });

      if (!res.ok) throw new Error("Request failed");
      const data = await res.json();
      const replyText = data.reply ?? "The assistant didn't return a response.";
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "assistant", content: replyText },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content:
            "Couldn't reach the assistant backend just now. Confirm /api/chat is wired up and try again.",
          isError: true,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(e) {
    e.preventDefault();
    sendMessage(input);
  }

  return (
    <div className="mx-auto flex h-[calc(100vh-9rem)] max-w-3xl flex-col">
      <div className="mb-4">
        <span className="font-mono text-xs uppercase tracking-widest text-signal">
          Fleet Assistant
        </span>
        <h1 className="mt-2 font-display text-3xl font-bold uppercase tracking-wide text-rig-50">
          Ask Argus
        </h1>
      </div>

      <Card className="flex flex-1 flex-col overflow-hidden p-0">
        <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto p-5">
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
          {loading && (
            <div className="flex items-center gap-2 text-sm text-rig-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              Thinking…
            </div>
          )}
        </div>

        {messages.length <= 1 && (
          <div className="flex flex-wrap gap-2 border-t border-rig-700 p-4">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => sendMessage(s)}
                className="rounded-tag border border-rig-600 px-3 py-1.5 text-xs text-rig-300 transition-colors hover:border-signal/60 hover:text-signal"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        <form onSubmit={handleSubmit} className="flex items-center gap-2 border-t border-rig-700 p-4">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about a unit, site, or alert…"
            className="h-11 flex-1 rounded-tag border border-rig-600 bg-rig-900 px-3.5 text-sm text-rig-50 placeholder:text-rig-500 focus-visible:outline-none focus-visible:border-signal"
          />
          <Button type="submit" size="icon" disabled={loading || !input.trim()}>
            <Send className="h-4 w-4" />
          </Button>
        </form>
      </Card>
    </div>
  );
}

function MessageBubble({ message }) {
  const isUser = message.role === "user";
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={`flex items-start gap-3 ${isUser ? "flex-row-reverse" : ""}`}
    >
      <div
        className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-tag ${
          isUser ? "bg-rig-700 text-rig-200" : "bg-signal text-rig-950"
        }`}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>
      <div
        className={`max-w-[80%] rounded-tag px-4 py-2.5 text-sm leading-relaxed ${
          isUser
            ? "bg-rig-700 text-rig-50"
            : message.isError
            ? "border border-rust/40 bg-rust/10 text-rig-200"
            : "border border-rig-700 bg-rig-800 text-rig-200"
        }`}
      >
        {message.content}
      </div>
    </motion.div>
  );
}
