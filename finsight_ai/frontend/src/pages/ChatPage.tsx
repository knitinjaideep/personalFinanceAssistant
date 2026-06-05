import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Trash2, Loader2, Sparkles, Upload, FileText, Lock, CheckCircle2, Layers, ChevronDown } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { api, ApiError } from "../api/client";
import { useAppStore } from "../store/appStore";
import type { ChatMessage, ChatResponse } from "../types";
import { ChatBubble } from "../components/chat/ChatBubble";
import { AnswerCard } from "../components/chat/AnswerCard";
import { UploadModal } from "../components/upload/UploadModal";
import { BulkUploadModal } from "../components/upload/BulkUploadModal";
import { DocumentsModal } from "../components/documents/DocumentsModal";
import {
  contentPageVariants, staggerContainer, staggerChild, fadeVariants,
} from "../design/motion";
import { CoralMascot } from "../components/CoralMascot";
import { CoralBubbleMascot } from "../components/CoralBubbleMascot";

const EXAMPLE_QUESTIONS = [
  "How much did I spend on dining last month?",
  "Show my top spending categories",
  "Do I have any subscriptions?",
  "How is my cash flow looking this month?",
  "What fees did Morgan Stanley charge me?",
  "Summarize my latest statement",
];

// ── Typing indicator ──────────────────────────────────────────────────────────

function TypingIndicator() {
  return (
    <motion.div
      variants={fadeVariants}
      initial="hidden"
      animate="visible"
      exit="exit"
      className="flex items-center gap-2.5 pl-1"
    >
      <CoralMascot variant="main" size="xs" className="shrink-0" />
      <div
        className="flex items-center gap-1.5 px-4 py-3 rounded-3xl rounded-bl-lg"
        style={{
          background: "var(--glass-dark-bg)",
          backdropFilter: "blur(12px)",
          border: "1px solid var(--border-accent)",
          boxShadow: "0 4px 16px var(--card-shadow)",
        }}
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
      <span className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>Coral is thinking…</span>
    </motion.div>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────

function ChatEmptyState({ onQuestion }: { onQuestion: (q: string) => void }) {
  return (
    <motion.div
      variants={contentPageVariants}
      initial="hidden"
      animate="visible"
      className="flex flex-col items-center justify-center min-h-[55vh] text-center px-4"
    >
      <motion.div variants={staggerChild} className="mb-6">
        <CoralBubbleMascot
          variant="main"
          size="lg"
          animated
          glow
          speech="I'm here to help you understand your money in plain English."
        />
      </motion.div>

      <motion.h2
        variants={staggerChild}
        className="text-[22px] font-bold mb-2 leading-tight"
        style={{ color: "var(--text-primary)" }}
      >
        Chat with Coral
      </motion.h2>

      <motion.p
        variants={staggerChild}
        className="text-[14px] mb-2 font-medium"
        style={{ color: "rgba(34,211,238,0.70)" }}
      >
        Ask anything about your finances
      </motion.p>

      <motion.p
        variants={staggerChild}
        className="text-sm mb-9 max-w-sm leading-relaxed"
        style={{ color: "var(--text-secondary)" }}
      >
        Everything stays on your device. Ask me what changed, what you spent, or what your statements say.
      </motion.p>

      <motion.div
        variants={staggerContainer}
        initial="hidden"
        animate="visible"
        className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full max-w-lg"
      >
        {EXAMPLE_QUESTIONS.map((q) => (
          <motion.button
            key={q}
            variants={staggerChild}
            whileHover={{ y: -2, scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
            onClick={() => onQuestion(q)}
            className="px-4 py-3 text-left text-sm font-medium rounded-2xl transition-all duration-150"
            style={{
              background: "var(--panel-bg)",
              backdropFilter: "blur(12px)",
              border: "1px solid var(--panel-border-accent)",
              color: "var(--text-secondary)",
              boxShadow: "var(--panel-shadow)",
            }}
          >
            <Sparkles size={11} className="inline mb-0.5 mr-1.5" style={{ color: "rgba(255,122,90,0.80)" }} />
            {q}
          </motion.button>
        ))}
      </motion.div>
    </motion.div>
  );
}

// ── Message item ──────────────────────────────────────────────────────────────

function MessageItem({ message, onFollowup }: { message: ChatMessage; onFollowup: (q: string) => void }) {
  if (message.role === "user") return <ChatBubble role="user" content={message.content} timestamp={message.timestamp} />;
  if (message.answer) return <AnswerCard answer={message.answer} onFollowup={onFollowup} timestamp={message.timestamp} />;
  return <ChatBubble role="assistant" content={message.content} timestamp={message.timestamp} errorRequestId={message.error_request_id} />;
}

// ── Ingestion status badge ────────────────────────────────────────────────────

function IngestionBadge() {
  const { ingestionJobs } = useAppStore();
  const processing = ingestionJobs.filter((j) => j.status === "processing");
  const recentDone = ingestionJobs.filter(
    (j) => j.status === "parsed" && Date.now() - j.started_at < 10_000
  );

  if (processing.length === 0 && recentDone.length === 0) return null;

  if (processing.length > 0) {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.9 }}
        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-[11px] font-medium"
        style={{
          background: "rgba(34,211,238,0.10)",
          border: "1px solid rgba(34,211,238,0.20)",
          color: "rgba(34,211,238,0.80)",
        }}
      >
        <Loader2 size={11} className="animate-spin" />
        {processing.length > 1 ? `${processing.length} ingesting…` : "Ingesting…"}
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9 }}
      className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-[11px] font-medium"
      style={{
        background: "rgba(76,175,147,0.10)",
        border: "1px solid rgba(76,175,147,0.22)",
        color: "rgba(76,175,147,0.85)",
      }}
    >
      <CheckCircle2 size={11} />
      Ready for chat
    </motion.div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

const SCROLL_THRESHOLD = 80;

export function ChatPage() {
  const { chatHistory, addChatMessage, clearChat, theme } = useAppStore();
  const isLight = theme === "light";
  const [input, setInput]               = useState("");
  const [loading, setLoading]           = useState(false);
  const [uploadOpen, setUploadOpen]     = useState(false);
  const [bulkUploadOpen, setBulkUploadOpen] = useState(false);
  const [docsOpen, setDocsOpen]         = useState(false);
  const [showJumpBtn, setShowJumpBtn]   = useState(false);
  const messagesEndRef                  = useRef<HTMLDivElement>(null);
  const scrollContainerRef             = useRef<HTMLDivElement>(null);
  const textareaRef                    = useRef<HTMLTextAreaElement>(null);

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

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 120)}px`;
    }
  }, [input]);

  const send = async (question?: string) => {
    const q = (question || input).trim();
    if (!q || loading) return;
    setInput("");
    addChatMessage({ role: "user", content: q });
    setLoading(true);

    try {
      const history = chatHistory.slice(-6).map((m) => ({ role: m.role, content: m.content }));
      const resp = await api.post<ChatResponse>("/chat/query", { question: q, history });
      addChatMessage({
        role: "assistant",
        content: resp.raw_text || resp.answer.summary,
        answer: resp.answer,
      });
    } catch (err: unknown) {
      const apiErr = err instanceof ApiError ? err : null;
      addChatMessage({
        role: "assistant",
        content: `Coral could not find matching data yet. Try widening the date range or reprocessing your statements. (${apiErr?.detail ?? (err instanceof Error ? err.message : "Unknown error")})`,
        error_request_id: apiErr?.request_id,
      });
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const canSend = input.trim().length > 0 && !loading;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: -6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className="shrink-0 px-6 pt-8 pb-4 flex items-center justify-between"
        style={{
          borderBottom: `1px solid var(--border-subtle)`,
          background: isLight ? "rgba(240,247,252,0.60)" : "rgba(3,17,31,0.45)",
          backdropFilter: "blur(20px)",
          WebkitBackdropFilter: "blur(20px)",
        }}
      >
        {/* Brand */}
        <div className="flex items-center gap-3">
          <CoralMascot size="sm" animated={false} className="shrink-0" />
          <div>
            <h1 className="text-[16px] font-bold leading-tight tracking-tight" style={{ color: "var(--text-primary)" }}>
              Chat with Coral
            </h1>
            <p className="text-[11px] font-medium" style={{ color: "rgba(34,211,238,0.60)" }}>
              Ask anything about your finances
            </p>
          </div>
        </div>

        {/* Right actions */}
        <div className="flex items-center gap-2">
          <AnimatePresence>
            <IngestionBadge />
          </AnimatePresence>

          <button
            onClick={() => setDocsOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-all"
            style={{
              background: "var(--btn-glass-bg)",
              border: "1px solid var(--btn-glass-border)",
              color: "var(--text-secondary)",
            }}
          >
            <FileText size={12} />
            Docs
          </button>

          <button
            onClick={() => setBulkUploadOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-all"
            style={{
              background: "var(--btn-glass-bg)",
              border: "1px solid var(--btn-glass-border)",
              color: "var(--text-secondary)",
            }}
          >
            <Layers size={12} />
            Bulk
          </button>

          <button
            onClick={() => setUploadOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold text-white transition-all"
            style={{
              background: "linear-gradient(135deg, #FF7A5A, #FFA38F)",
              boxShadow: "0 4px 12px rgba(255,122,90,0.35)",
            }}
          >
            <Upload size={12} />
            Upload
          </button>

          <AnimatePresence>
            {chatHistory.length > 0 && (
              <motion.button
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9 }}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={clearChat}
                className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-xl transition-colors"
                style={{
                  background: "var(--btn-glass-bg)",
                  border: "1px solid var(--btn-glass-border)",
                  color: "var(--text-muted)",
                }}
              >
                <Trash2 size={11} />
              </motion.button>
            )}
          </AnimatePresence>
        </div>
      </motion.div>

      {/* ── Messages ───────────────────────────────────────────────────────── */}
      <div className="relative flex-1 min-h-0">
        <div
          ref={scrollContainerRef}
          className="h-full overflow-y-auto px-6 py-6"
        >
          <div className="max-w-2xl mx-auto space-y-5">
            {chatHistory.length === 0 ? (
              <ChatEmptyState onQuestion={send} />
            ) : (
              chatHistory.map((msg, i) => (
                <MessageItem key={i} message={msg} onFollowup={send} />
              ))
            )}

            <AnimatePresence>
              {loading && <TypingIndicator />}
            </AnimatePresence>

            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Jump to latest */}
        <AnimatePresence>
          {showJumpBtn && (
            <motion.button
              initial={{ opacity: 0, y: 8, scale: 0.92 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8, scale: 0.92 }}
              transition={{ duration: 0.18 }}
              onClick={() => scrollToBottom()}
              className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-1.5 px-3.5 py-2 rounded-full text-xs font-semibold text-white shadow-lg"
              style={{
                background: "linear-gradient(135deg, #FF7A5A, #FFA38F)",
                boxShadow: "0 4px 16px rgba(255,122,90,0.45)",
              }}
            >
              <ChevronDown size={13} />
              Jump to latest
            </motion.button>
          )}
        </AnimatePresence>
      </div>

      {/* ── Input bar ──────────────────────────────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2, duration: 0.35 }}
        className="shrink-0 px-6 py-4"
        style={{
          borderTop: `1px solid var(--border-subtle)`,
          background: isLight ? "rgba(240,247,252,0.60)" : "rgba(3,17,31,0.45)",
          backdropFilter: "blur(20px)",
          WebkitBackdropFilter: "blur(20px)",
        }}
      >
        <div className="flex gap-3 max-w-2xl mx-auto items-end">
          <div
            className="flex-1 flex items-end rounded-2xl overflow-hidden transition-all duration-200"
            style={{
              background: isLight ? "rgba(255,255,255,0.88)" : "rgba(3,17,31,0.80)",
              border: `1px solid ${input.trim() ? "rgba(255,122,90,0.50)" : "var(--border-accent)"}`,
              boxShadow: input.trim()
                ? "0 0 0 3px rgba(255,122,90,0.10)"
                : `0 2px 8px var(--card-shadow)`,
            }}
          >
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about your finances…"
              rows={1}
              className="flex-1 px-4 py-3 text-sm bg-transparent focus:outline-none resize-none leading-relaxed"
              style={{
                minHeight: "44px",
                maxHeight: "120px",
                color: "var(--text-primary)",
              }}
              disabled={loading}
            />
          </div>

          <motion.button
            whileHover={canSend ? { scale: 1.06, y: -1 } : undefined}
            whileTap={canSend ? { scale: 0.94 } : undefined}
            onClick={() => send()}
            disabled={!canSend}
            className="shrink-0 w-11 h-11 rounded-2xl flex items-center justify-center font-medium transition-all duration-200 disabled:opacity-30 disabled:cursor-not-allowed"
            style={{
              background: canSend
                ? "linear-gradient(135deg, #FF7A5A, #FFA38F)"
                : "var(--btn-glass-bg)",
              boxShadow: canSend ? "0 4px 16px rgba(255,122,90,0.40)" : "none",
            }}
          >
            {loading ? (
              <Loader2 size={16} className="animate-spin text-white" />
            ) : (
              <Send size={15} style={{ color: canSend ? "white" : "var(--text-muted)" }} />
            )}
          </motion.button>
        </div>

        {/* Privacy footer */}
        <div className="flex items-center justify-center gap-1.5 mt-2.5">
          <Lock size={9} style={{ color: "var(--text-dim)" }} />
          <p className="text-[10px] font-medium" style={{ color: "var(--text-dim)" }}>
            All data stays on your device · Enter to send · Shift+Enter for new line
          </p>
        </div>
      </motion.div>

      {/* ── Modals ─────────────────────────────────────────────────────────── */}
      <UploadModal
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onUploaded={() => {}}
      />
      <BulkUploadModal
        open={bulkUploadOpen}
        onClose={() => setBulkUploadOpen(false)}
        onUploaded={() => {}}
      />
      <DocumentsModal
        open={docsOpen}
        onClose={() => setDocsOpen(false)}
      />
    </div>
  );
}
