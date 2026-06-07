"use client";

import { motion } from "framer-motion";
import { useAppStore } from "@/store/appStore";
import { formatTime } from "@/lib/utils";

interface ChatBubbleProps {
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
  errorRequestId?: string;
}

export function ChatBubble({ role, content, timestamp, errorRequestId }: ChatBubbleProps) {
  const theme = useAppStore((s) => s.theme);
  const isLight = theme === "light";

  if (role === "user") {
    return (
      <motion.div
        initial={{ opacity: 0, x: 12 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.22 }}
        className="flex flex-col items-end gap-1"
      >
        <div
          className="max-w-lg px-4 py-3 rounded-3xl rounded-br-lg text-white coral-card-body leading-relaxed"
          style={{
            background: "linear-gradient(135deg, #FF7A5A 0%, #FFA38F 100%)",
            boxShadow: "0 4px 20px rgba(255,122,90,0.25)",
          }}
        >
          {content}
        </div>
        {timestamp && (
          <span className="coral-badge-text mr-1" style={{ color: "var(--text-muted)" }}>
            {formatTime(timestamp)}
          </span>
        )}
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, x: -12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.22 }}
      className="flex items-start gap-2.5"
    >
      <div
        className="w-7 h-7 rounded-full shrink-0 mt-0.5 flex items-center justify-center text-sm font-bold"
        style={{
          background: "linear-gradient(135deg, #FF7A5A 0%, #FFA38F 100%)",
          color: "white",
        }}
      >
        C
      </div>
      <div className="flex flex-col items-start gap-1 min-w-0">
        <div
          className="max-w-2xl px-4 py-3 rounded-3xl rounded-bl-lg coral-card-body leading-relaxed"
          style={{
            background: isLight ? "rgba(255,255,255,0.82)" : "rgba(7,24,38,0.70)",
            backdropFilter: "blur(12px)",
            WebkitBackdropFilter: "blur(12px)",
            border: "1px solid var(--border-accent)",
            boxShadow: "0 4px 20px var(--card-shadow)",
            color: "var(--text-primary)",
          }}
        >
          {content}
        </div>
        {errorRequestId && (
          <div
            className="mt-1 px-3 py-2 rounded-xl text-[10px] font-mono"
            style={{
              background: "var(--glass-bg)",
              border: "1px solid var(--border-accent)",
              color: "rgba(34,211,238,0.55)",
            }}
          >
            <span className="font-semibold" style={{ color: "rgba(34,211,238,0.40)" }}>request_id</span>
            <span className="ml-2">{errorRequestId}</span>
          </div>
        )}
        {timestamp && (
          <span className="coral-badge-text ml-1" style={{ color: "var(--text-muted)" }}>
            {formatTime(timestamp)}
          </span>
        )}
      </div>
    </motion.div>
  );
}
