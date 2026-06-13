"use client";

import { useState, useRef, useEffect, useCallback, memo } from "react";
import {
  Send, Loader2, Sparkles, FileText, Lock,
  CheckCircle2, ChevronDown,
  Landmark, TrendingUp, CreditCard, FileSearch, ReceiptText,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { ApiError, NetworkError } from "@/lib/api-client";
import { useAppStore } from "@/store/appStore";
import type { ChatMessage, StructuredAnswer } from "@/types/index";
import { ChatBubble } from "./ChatBubble";
import { AnswerCard } from "./AnswerCard";
import CoralMascot from "@/components/coral/CoralMascot";
import DocumentsPageClient from "@/components/documents/DocumentsPageClient";

// ── Static content — declared once, never recreated per render ───────────────
const SUGGESTED_PROMPTS = [
  "What changed in my spending over the last 6 months?",
  "Summarize my latest investment statements.",
  "Which documents failed processing?",
  "What recurring transactions should I review?",
  "Compare my cash flow across accounts.",
  "What fees did Morgan Stanley charge me?",
] as const;

const CATEGORY_CHIPS = [
  { label: "Banking",     icon: <Landmark size={13} />,    prompt: "Give me a banking summary for the last 3 months." },
  { label: "Investments", icon: <TrendingUp size={13} />,  prompt: "How did my investments change recently?" },
  { label: "Spending",    icon: <CreditCard size={13} />,  prompt: "Show my top spending categories." },
  { label: "Documents",   icon: <FileSearch size={13} />,  prompt: "What documents have been processed?" },
  { label: "Recurring",   icon: <ReceiptText size={13} />, prompt: "List my recurring charges." },
  { label: "Taxes",       icon: <FileText size={13} />,    prompt: "Do I have any tax-related transactions?" },
] as const;

const SCROLL_THRESHOLD = 80;

// ── Typing indicator ─────────────────────────────────────────────────────────
const TypingIndicator = memo(function TypingIndicator() {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="flex items-center gap-2.5 pl-1"
    >
      <CoralMascot size="xs" animated={false} glow={false} />
      <div
        className="flex items-center gap-1.5 px-4 py-3 rounded-3xl rounded-bl-lg"
        style={{ background: "var(--glass-dark-bg)", border: "1px solid var(--border-accent)", boxShadow: "0 4px 16px var(--card-shadow)" }}
      >
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="w-1.5 h-1.5 rounded-full"
            style={{ background: "rgba(34,211,238,0.60)" }}
            animate={{ y: [0, -4, 0], opacity: [0.4, 1, 0.4] }}
            transition={{ duration: 0.8, repeat: Infinity, delay: i * 0.18, ease: "easeInOut" }}
          />
        ))}
      </div>
      <span className="small-text font-medium" style={{ color: "var(--text-muted)" }}>Coral is thinking…</span>
    </motion.div>
  );
});


// ── Empty state — centered intro that fills the chat column cleanly ──────────
const ChatIntro = memo(function ChatIntro({ onQuestion }: { onQuestion: (q: string) => void }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center text-center px-4 py-8">
      <div className="mb-6">
        <CoralMascot size="lg" animated />
      </div>

      <h2 className="page-title mb-2 leading-tight">Ask Coral</h2>
      <p className="body-text mb-2 font-medium" style={{ color: "rgba(34,211,238,0.78)" }}>
        Ask questions across your banking, investments, and documents.
      </p>
      <p className="small-text mb-8 max-w-md" style={{ color: "var(--text-secondary)" }}>
        Everything stays on your device. Ask what changed, what you spent, or what your statements say.
      </p>

      {/* Category chips */}
      <div className="flex flex-wrap justify-center gap-2 mb-8">
        {CATEGORY_CHIPS.map((chip) => (
          <button
            key={chip.label}
            onClick={() => onQuestion(chip.prompt)}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-full small-text font-semibold transition-transform duration-150 hover:-translate-y-0.5 active:scale-[0.98]"
            style={{
              background: "var(--glass-light-bg)",
              border: "1px solid var(--border-accent)",
              color: "var(--text-secondary)",
            }}
          >
            <span style={{ color: "rgba(34,211,238,0.70)" }}>{chip.icon}</span>
            {chip.label}
          </button>
        ))}
      </div>

      {/* Suggested prompts — 2-col on desktop, 1-col on mobile */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full max-w-3xl">
        {SUGGESTED_PROMPTS.map((q) => (
          <button
            key={q}
            onClick={() => onQuestion(q)}
            className="px-4 py-3.5 text-left small-text font-medium rounded-2xl transition-transform duration-150 hover:-translate-y-0.5 active:scale-[0.99]"
            style={{
              background: "var(--panel-bg)",
              border: "1px solid var(--panel-border-accent)",
              color: "var(--text-secondary)",
              boxShadow: "var(--panel-shadow)",
            }}
          >
            <Sparkles size={12} className="inline mb-0.5 mr-1.5" style={{ color: "rgba(255,122,90,0.80)" }} />
            {q}
          </button>
        ))}
      </div>
    </div>
  );
});

// ── Streaming status bubble ───────────────────────────────────────────────────
const StreamStatusBubble = memo(function StreamStatusBubble({ status }: { status: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -8 }}
      transition={{ duration: 0.18 }}
      className="flex items-center gap-2.5 pl-1"
    >
      <CoralMascot size="xs" animated={false} glow={false} />
      <div
        className="flex items-center gap-2 px-4 py-2.5 rounded-3xl rounded-bl-lg text-xs font-medium"
        style={{
          background: "var(--glass-dark-bg)",
          border: "1px solid var(--border-accent)",
          boxShadow: "0 4px 16px var(--card-shadow)",
          color: "rgba(34,211,238,0.70)",
        }}
      >
        <motion.span
          className="w-1.5 h-1.5 rounded-full shrink-0"
          style={{ background: "rgba(34,211,238,0.60)" }}
          animate={{ opacity: [0.3, 1, 0.3] }}
          transition={{ duration: 1.2, repeat: Infinity, ease: "easeInOut" }}
        />
        {status}
      </div>
    </motion.div>
  );
});

function MessageItem({ message, onFollowup }: { message: ChatMessage; onFollowup: (q: string) => void }) {
  if (message.role === "user") return <ChatBubble role="user" content={message.content} timestamp={message.timestamp} />;
  if (message.streamStatus) return <StreamStatusBubble status={message.streamStatus} />;
  if (message.answer)        return <AnswerCard answer={message.answer} onFollowup={onFollowup} timestamp={message.timestamp} />;
  return <ChatBubble role="assistant" content={message.content} timestamp={message.timestamp} errorRequestId={message.error_request_id} />;
}

function IngestionBadge() {
  const ingestionJobs = useAppStore((s) => s.ingestionJobs);
  const processing = ingestionJobs.filter((j) => j.status === "processing");
  const recentDone = ingestionJobs.filter((j) => j.status === "parsed" && Date.now() - j.started_at < 10_000);
  if (processing.length === 0 && recentDone.length === 0) return null;
  if (processing.length > 0) {
    return (
      <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-sm font-medium"
        style={{ background: "rgba(34,211,238,0.10)", border: "1px solid rgba(34,211,238,0.20)", color: "rgba(34,211,238,0.80)" }}>
        <Loader2 size={12} className="animate-spin" />
        {processing.length > 1 ? `${processing.length} ingesting…` : "Ingesting…"}
      </div>
    );
  }
  return (
    <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-sm font-medium"
      style={{ background: "rgba(76,175,147,0.10)", border: "1px solid rgba(76,175,147,0.22)", color: "rgba(76,175,147,0.85)" }}>
      <CheckCircle2 size={12} /> Ready for chat
    </div>
  );
}

function DocsModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "var(--modal-overlay)", backdropFilter: "blur(6px)" }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.97, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.97, y: 12 }}
        transition={{ duration: 0.22, ease: "easeOut" }}
        className="relative w-full max-w-2xl rounded-3xl overflow-hidden shadow-2xl max-h-[90vh] overflow-y-auto"
        style={{ background: "var(--modal-bg)", border: "1px solid var(--modal-border)", boxShadow: "var(--modal-shadow)" }}
      >
        <div
          className="flex items-center justify-between px-6 pt-6 pb-4 sticky top-0 z-10"
          style={{ background: "var(--modal-bg)", borderBottom: "1px solid var(--border-subtle)" }}
        >
          <h2 className="card-title-lg" style={{ color: "var(--text-primary)" }}>Documents</h2>
          <button onClick={onClose} className="p-1.5 rounded-full transition-colors" style={{ color: "var(--text-muted)" }} aria-label="Close">✕</button>
        </div>
        <div className="px-6 pb-6 pt-4">
          <DocumentsPageClient compact />
        </div>
      </motion.div>
    </div>
  );
}

// ── Composer — bottom-pinned, glass, grows up to a max height ─────────────────
function ChatComposer({
  input, setInput, onSend, loading,
}: {
  input: string;
  setInput: (v: string) => void;
  onSend: () => void;
  loading: boolean;
}) {
  const isLight = useAppStore((s) => s.theme === "light");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const canSend = input.trim().length > 0 && !loading;

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
  }, [input]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  return (
    <div className="shrink-0 px-3 sm:px-4 pt-3 pb-4">
      <div className="mx-auto w-full max-w-4xl">
        <div
          className="flex items-end gap-2.5 rounded-[26px] p-2 pl-4 transition-colors duration-200"
          style={{
            background: isLight ? "rgba(255,255,255,0.78)" : "rgba(5,22,40,0.72)",
            backdropFilter: "blur(20px)",
            WebkitBackdropFilter: "blur(20px)",
            border: `1px solid ${input.trim() ? "rgba(255,122,90,0.50)" : "var(--border-accent)"}`,
            boxShadow: input.trim()
              ? "0 0 0 3px rgba(255,122,90,0.10), 0 8px 30px var(--card-shadow)"
              : "0 8px 30px var(--card-shadow)",
          }}
        >
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your finances…"
            rows={1}
            className="flex-1 bg-transparent focus:outline-none resize-none leading-relaxed py-2.5"
            style={{
              minHeight: "40px",
              maxHeight: "140px",
              color: "var(--text-primary)",
              fontSize: "var(--font-body)",
            }}
            disabled={loading}
          />

          <motion.button
            whileTap={canSend ? { scale: 0.96 } : undefined}
            onClick={onSend}
            disabled={!canSend}
            aria-label="Send message"
            className="shrink-0 w-11 h-11 rounded-2xl flex items-center justify-center transition-[background,opacity] duration-150 disabled:opacity-35 disabled:cursor-not-allowed"
            style={{
              background: canSend ? "linear-gradient(135deg, #FF7A5A, #FFA38F)" : "var(--btn-glass-bg)",
              boxShadow: canSend ? "0 4px 16px rgba(255,122,90,0.40)" : "none",
            }}
          >
            {loading
              ? <Loader2 size={17} className="animate-spin text-white" />
              : <Send size={16} style={{ color: canSend ? "white" : "var(--text-muted)" }} />}
          </motion.button>
        </div>

        <div className="flex items-center justify-center gap-1.5 mt-2">
          <Lock size={10} style={{ color: "var(--text-dim)" }} />
          <p className="micro-text font-medium" style={{ color: "var(--text-dim)" }}>
            All data stays on your device · Enter to send · Shift+Enter for new line
          </p>
        </div>
      </div>
    </div>
  );
}

export default function ChatWindow() {
  const chatHistory = useAppStore((s) => s.chatHistory);
  const addChatMessage = useAppStore((s) => s.addChatMessage);
  const clearChat = useAppStore((s) => s.clearChat);
  const isLight = useAppStore((s) => s.theme === "light");

  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [docsOpen, setDocsOpen] = useState(false);
  const [showJumpBtn, setShowJumpBtn] = useState(false);

  const hasMessages = chatHistory.length > 0;

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  const isNearBottom = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return true;
    return el.scrollHeight - el.scrollTop - el.clientHeight < SCROLL_THRESHOLD;
  }, []);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    messagesEndRef.current?.scrollIntoView({ behavior });
  }, []);

  useEffect(() => {
    if (isNearBottom()) scrollToBottom();
  }, [chatHistory, loading, isNearBottom, scrollToBottom]);

  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const onScroll = () => setShowJumpBtn(!isNearBottom());
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [isNearBottom]);

  const send = useCallback(async (question?: string) => {
    const q = (question || input).trim();
    if (!q || loading) return;

    if (process.env.NODE_ENV === "development") console.time("chat-stream");

    setInput("");
    addChatMessage({ role: "user", content: q });
    setLoading(true);

    // Add a placeholder assistant message that we'll update as events arrive
    const placeholderIdx = useAppStore.getState().chatHistory.length;
    addChatMessage({ role: "assistant", content: "", streamStatus: "Understanding your question…" });

    try {
      const history = useAppStore.getState().chatHistory
        .slice(-8, -1)  // exclude the placeholder we just added
        .filter((m) => m.role === "user" || m.role === "assistant")
        .map((m) => ({ role: m.role, content: m.content }));

      const response = await fetch("/api/v1/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, history }),
        signal: AbortSignal.timeout(180_000),
      });

      if (!response.ok || !response.body) {
        throw new ApiError(response.status, "Stream request failed");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      const updateMessage = (patch: Partial<ChatMessage>) => {
        useAppStore.getState().updateLastAssistantMessage(patch);
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        let currentEvent = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));
              if (currentEvent === "status") {
                updateMessage({ streamStatus: data.message, content: "" });
              } else if (currentEvent === "intent") {
                // intent classified — update status
                updateMessage({ streamStatus: "Querying your data…" });
              } else if (currentEvent === "answer_token") {
                updateMessage({ content: data.text, streamStatus: undefined });
              } else if (currentEvent === "done") {
                const answer = data.answer as StructuredAnswer | undefined;
                updateMessage({
                  content: answer?.summary || data.text || "",
                  answer,
                  streamStatus: undefined,
                });
              } else if (currentEvent === "error") {
                updateMessage({
                  content: `Error: ${data.message}`,
                  streamStatus: undefined,
                });
              }
            } catch {
              // ignore malformed SSE data lines
            }
          }
        }
      }
    } catch (err: unknown) {
      let errorMsg: string;
      let reqId: string | undefined;

      if (err instanceof NetworkError) {
        errorMsg = err.message;
      } else if (err instanceof ApiError) {
        reqId = err.request_id;
        errorMsg = err.status === 500
          ? `The backend returned an error (500). Check FastAPI logs. Detail: ${err.detail}`
          : `Coral could not answer (${err.status}): ${err.detail}`;
      } else if (err instanceof Error && err.name === "TimeoutError") {
        errorMsg = "The request timed out. qwen3:8b inference can take up to 3 minutes.";
      } else {
        errorMsg = `Unexpected error: ${err instanceof Error ? err.message : String(err)}`;
      }

      useAppStore.getState().updateLastAssistantMessage({ content: errorMsg, streamStatus: undefined, error_request_id: reqId });
    } finally {
      setLoading(false);
      if (process.env.NODE_ENV === "development") console.timeEnd("chat-stream");
    }
  }, [input, loading, addChatMessage]);

  return (
    <div
      className="flex flex-col h-full"
      style={{ marginTop: "var(--nav-offset)", height: "calc(100% - var(--nav-offset))" }}
    >
      {/* ── Scroll area ─────────────────────────────────────────────────── */}
      <div className="relative flex-1 min-h-0 flex flex-col">
        <div
          ref={scrollContainerRef}
          className="flex-1 min-h-0 overflow-y-auto flex flex-col"
        >
          {hasMessages ? (
            <div className="mx-auto w-full max-w-3xl px-4 py-6 md:px-6 space-y-5">
              {chatHistory.map((msg, i) => (
                <MessageItem key={i} message={msg} onFollowup={send} />
              ))}
              {/* Only show typing indicator when there's no streaming placeholder */}
              <AnimatePresence>
                {loading && !chatHistory.some((m) => m.role === "assistant" && m.streamStatus) && (
                  <TypingIndicator />
                )}
              </AnimatePresence>
              <div ref={messagesEndRef} />
            </div>
          ) : (
            <div className="mx-auto w-full max-w-3xl flex flex-1 flex-col">
              <ChatIntro onQuestion={send} />
            </div>
          )}
        </div>

        {/* Jump to latest */}
        <AnimatePresence>
          {showJumpBtn && hasMessages && (
            <motion.button
              initial={{ opacity: 0, y: 8, scale: 0.92 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8, scale: 0.92 }}
              transition={{ duration: 0.18 }}
              onClick={() => scrollToBottom()}
              className="absolute bottom-3 left-1/2 -translate-x-1/2 flex items-center gap-1.5 px-3.5 py-2 rounded-full text-sm font-semibold text-white shadow-lg btn-coral"
            >
              <ChevronDown size={13} /> Jump to latest
            </motion.button>
          )}
        </AnimatePresence>
      </div>

      {/* ── Composer — fixed at footer ───────────────────────────────────── */}
      <div
        className="shrink-0"
        style={{
          borderTop: "1px solid var(--border-subtle)",
          background: isLight ? "rgba(240,247,252,0.40)" : "rgba(3,17,31,0.40)",
          backdropFilter: "blur(20px)",
          WebkitBackdropFilter: "blur(20px)",
        }}
      >
        <ChatComposer input={input} setInput={setInput} onSend={() => send()} loading={loading} />
      </div>

      {/* Documents modal */}
      <AnimatePresence>{docsOpen && <DocsModal open={docsOpen} onClose={() => setDocsOpen(false)} />}</AnimatePresence>
    </div>
  );
}
