/// <reference types="vite/client" />
import { motion } from "framer-motion";
import { userBubbleVariants, assistantBubbleVariants } from "../../design/motion";
import { CoralMascot } from "../CoralMascot";

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
  if (role === "user") {
    return (
      <motion.div
        variants={userBubbleVariants}
        initial="hidden"
        animate="visible"
        className="flex flex-col items-end gap-1"
      >
        <div
          className="max-w-lg px-4 py-3 rounded-3xl rounded-br-lg text-white text-sm leading-relaxed"
          style={{
            background: "linear-gradient(135deg, #FF7A5A 0%, #FFA38F 100%)",
            boxShadow: "0 4px 20px rgba(255,122,90,0.25)",
          }}
        >
          {content}
        </div>
        {timestamp && (
          <span className="text-[10px] text-ocean/25 mr-1">{formatTime(timestamp)}</span>
        )}
      </motion.div>
    );
  }

  return (
    <motion.div
      variants={assistantBubbleVariants}
      initial="hidden"
      animate="visible"
      className="flex items-start gap-2.5"
    >
      <CoralMascot variant="main" size="xs" animated={false} className="mt-0.5 shrink-0" />
      <div className="flex flex-col items-start gap-1 min-w-0">
      <div
        className="max-w-2xl px-4 py-3 rounded-3xl rounded-bl-lg text-sm text-ocean-deep leading-relaxed"
        style={{
          background: "rgba(255,255,255,0.88)",
          backdropFilter: "blur(12px)",
          WebkitBackdropFilter: "blur(12px)",
          border: "1px solid rgba(205,237,246,0.8)",
          boxShadow: "0 4px 20px rgba(11,60,93,0.10)",
        }}
      >
        {content}
      </div>
      {VITE_DEBUG && errorRequestId && (
        <div
          className="mt-1 px-3 py-2 rounded-xl text-[10px] font-mono text-ocean/60"
          style={{
            background: "rgba(240,249,252,0.70)",
            border: "1px solid rgba(205,237,246,0.65)",
          }}
        >
          <span className="font-semibold text-ocean/40">request_id</span>
          <span className="ml-2 text-ocean/55">{errorRequestId}</span>
        </div>
      )}
      {timestamp && (
        <span className="text-[10px] text-ocean/25 ml-1">{formatTime(timestamp)}</span>
      )}
      </div>
    </motion.div>
  );
}
