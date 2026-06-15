/// <reference types="vite/client" />
import { motion } from "framer-motion";
import { userBubbleVariants, assistantBubbleVariants } from "../../design/motion";
import { CoralMascot } from "../CoralMascot";
import { useAppStore } from "../../store/appStore";

const VITE_DEBUG = import.meta.env.VITE_DEBUG === "true";

interface ChatBubbleProps {
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
  errorRequestId?: string;
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function ChatBubble({ role, content, timestamp, errorRequestId }: ChatBubbleProps) {
  const theme = useAppStore((s) => s.theme);
  const isLight = theme === "light";

  if (role === "user") {
    return (
      <motion.div
        variants={userBubbleVariants}
        initial="hidden"
        animate="visible"
        className="flex flex-col items-end gap-1.5"
      >
        <div
          className="max-w-lg px-5 py-3.5 rounded-[22px] rounded-br-[6px] text-white leading-relaxed text-[0.93rem]"
          style={{
            background: "var(--chat-user-bg)",
            boxShadow: "var(--chat-user-shadow)",
            fontWeight: 450,
          }}
        >
          {content}
        </div>
        {timestamp && (
          <span className="coral-badge-text mr-1 opacity-50" style={{ color: "var(--text-muted)" }}>
            {formatTime(timestamp)}
          </span>
        )}
      </motion.div>
    );
  }

  return (
    <motion.div
      variants={assistantBubbleVariants}
      initial="hidden"
      animate="visible"
      className="flex items-start gap-3"
    >
      <CoralMascot variant="main" size="xs" animated={false} className="mt-1 shrink-0" />
      <div className="flex flex-col items-start gap-1.5 min-w-0">
        <div
          className="max-w-2xl px-5 py-3.5 rounded-[22px] rounded-bl-[6px] leading-relaxed text-[0.93rem]"
          style={{
            background: isLight ? "rgba(255,255,255,0.84)" : "rgba(6,22,40,0.72)",
            backdropFilter: "blur(16px)",
            WebkitBackdropFilter: "blur(16px)",
            border: `1px solid var(--chat-card-border)`,
            boxShadow: "var(--chat-card-shadow)",
            color: "var(--text-primary)",
          }}
        >
          {content}
        </div>
        {VITE_DEBUG && errorRequestId && (
          <div
            className="mt-1 px-3 py-2 rounded-xl text-[10px] font-mono"
            style={{
              background: "var(--glass-bg)",
              border: `1px solid var(--chat-card-border)`,
              color: "rgba(34,211,238,0.55)",
            }}
          >
            <span className="font-semibold" style={{ color: "rgba(34,211,238,0.40)" }}>request_id</span>
            <span className="ml-2" style={{ color: "rgba(34,211,238,0.55)" }}>{errorRequestId}</span>
          </div>
        )}
        {timestamp && (
          <span className="coral-badge-text ml-1 opacity-50" style={{ color: "var(--text-muted)" }}>
            {formatTime(timestamp)}
          </span>
        )}
      </div>
    </motion.div>
  );
}
