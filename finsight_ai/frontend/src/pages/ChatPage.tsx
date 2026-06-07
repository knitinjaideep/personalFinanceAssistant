import { useState, useRef, useEffect, useCallback, memo } from "react";
import {
  Send, Trash2, Loader2, Upload,
  Lock, CheckCircle2, ChevronDown,
  Home, Landmark, TrendingUp, FileText, MessageSquare, Sun, Moon,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { api, ApiError } from "../api/client";
import { useAppStore, type ActivePage } from "../store/appStore";
import type { ChatMessage, ChatResponse } from "../types";
import { ChatBubble } from "../components/chat/ChatBubble";
import { AnswerCard } from "../components/chat/AnswerCard";
import { UploadModal } from "../components/upload/UploadModal";
import { BulkUploadModal } from "../components/upload/BulkUploadModal";
import { DocumentsModal } from "../components/documents/DocumentsModal";
import { fadeVariants } from "../design/motion";
import { CoralMascot } from "../components/CoralMascot";

const NAV_ITEMS: { id: ActivePage; label: string; icon: React.ReactNode }[] = [
  { id: "overview",    label: "Home",        icon: <Home size={15} /> },
  { id: "banking",     label: "Banking",     icon: <Landmark size={15} /> },
  { id: "investments", label: "Investments", icon: <TrendingUp size={15} /> },
  { id: "documents",   label: "Documents",   icon: <FileText size={15} /> },
  { id: "chat",        label: "Chat",        icon: <MessageSquare size={15} /> },
];

// ── Typing indicator ───────────────────────────────────────────────────────────

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
      <span className="font-medium" style={{ color: "var(--text-muted)" }}>Coral is thinking…</span>
    </motion.div>
  );
}

// ── Ingestion badge ────────────────────────────────────────────────────────────

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
        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-sm font-medium"
        style={{
          background: "rgba(34,211,238,0.10)",
          border: "1px solid rgba(34,211,238,0.20)",
          color: "rgba(34,211,238,0.80)",
        }}
      >
        <Loader2 size={12} className="animate-spin" />
        {processing.length > 1 ? `${processing.length} ingesting…` : "Ingesting…"}
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9 }}
      className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-sm font-medium"
      style={{
        background: "rgba(76,175,147,0.10)",
        border: "1px solid rgba(76,175,147,0.22)",
        color: "rgba(76,175,147,0.85)",
      }}
    >
      <CheckCircle2 size={12} />
      Ready for chat
    </motion.div>
  );
}

// ── Full-width transparent top nav ────────────────────────────────────────────
// Single header region. Transparent at rest, glass on hover/focus.
// No pill wrapper, no rounded container — the entire strip is the nav.

const ChatTopNav = memo(function ChatTopNav({
  onUpload,
  onDocs,
  onClearChat,
  hasMessages,
}: {
  onUpload: () => void;
  onDocs: () => void;
  onClearChat: () => void;
  hasMessages: boolean;
}) {
  const { activePage, setActivePage, theme, toggleTheme } = useAppStore();
  const isLight = theme === "light";

  return (
    <header className="chat-top-nav group absolute inset-x-0 top-0 z-40 h-20">
      {/* Glass surface — invisible at rest, fades in on hover/focus */}
      <div
        className="
          chat-nav-glass
          absolute inset-0
          border-b border-white/0
          bg-slate-950/0
          backdrop-blur-none
          transition-all duration-300 ease-out
          group-hover:border-cyan-200/10
          group-hover:bg-slate-950/55
          group-hover:backdrop-blur-xl
          group-focus-within:border-cyan-200/10
          group-focus-within:bg-slate-950/60
          group-focus-within:backdrop-blur-xl
        "
      />

      <nav className="relative mx-auto flex h-full max-w-7xl items-center justify-between px-6 lg:px-10">

        {/* Left: brand — click goes to home */}
        <button
          type="button"
          onClick={() => setActivePage("overview")}
          className="flex items-center gap-2.5 shrink-0 opacity-90 transition-opacity hover:opacity-100"
        >
          <CoralMascot variant="main" size="xs" animated={false} glow={false} className="shrink-0" />
          <span
            className="hidden font-bold text-base leading-none tracking-tight sm:block"
            style={{ color: "var(--text-primary)" }}
          >
            Coral
          </span>
        </button>

        {/* Center: nav links — no pill container wrapping them */}
        <div className="absolute left-1/2 -translate-x-1/2 flex items-center gap-0.5">
          {NAV_ITEMS.map((item) => {
            const isActive = activePage === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setActivePage(item.id)}
                className={
                  isActive
                    ? "flex items-center gap-1.5 rounded-full px-3.5 py-2 text-sm font-semibold text-white shadow-md transition-all duration-150"
                    : "flex items-center gap-1.5 rounded-full px-3 py-2 text-sm font-medium text-slate-200/55 transition-all duration-150 hover:bg-white/10 hover:text-white"
                }
                style={isActive ? {
                  background: "linear-gradient(135deg, rgba(255,122,90,0.90) 0%, rgba(255,163,143,0.82) 100%)",
                  boxShadow: "0 3px 14px rgba(255,122,90,0.32)",
                } : undefined}
              >
                <span className="shrink-0">{item.icon}</span>
                <span className="hidden md:block">{item.label}</span>
              </button>
            );
          })}
        </div>

        {/* Right: actions — Upload, Docs (icon only), theme, clear */}
        <div className="flex items-center gap-1.5 shrink-0">
          <AnimatePresence>
            <IngestionBadge />
          </AnimatePresence>

          {/* Docs — icon only, opens docs modal */}
          <button
            type="button"
            onClick={onDocs}
            className="flex items-center justify-center w-9 h-9 rounded-xl text-slate-200/55 transition-all duration-150 hover:bg-white/10 hover:text-white"
            title="Documents"
          >
            <FileText size={14} />
          </button>

          {/* Upload */}
          <button
            type="button"
            onClick={onUpload}
            className="flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-sm font-semibold text-white transition-all duration-150"
            style={{
              background: "linear-gradient(135deg, #FF7A5A, #FFA38F)",
              boxShadow: "0 3px 12px rgba(255,122,90,0.32)",
            }}
          >
            <Upload size={13} />
            <span className="hidden sm:block">Upload</span>
          </button>

          {/* Theme toggle */}
          <button
            type="button"
            onClick={toggleTheme}
            className="flex items-center justify-center w-9 h-9 rounded-xl text-slate-200/55 transition-all duration-150 hover:bg-white/10 hover:text-white"
          >
            {isLight
              ? <Sun size={14} style={{ color: "rgba(255,160,20,0.85)" }} />
              : <Moon size={14} style={{ color: "rgba(34,211,238,0.75)" }} />
            }
          </button>

          {/* Clear chat — only when messages exist */}
          <AnimatePresence>
            {hasMessages && (
              <motion.button
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9 }}
                type="button"
                onClick={onClearChat}
                className="flex items-center justify-center w-9 h-9 rounded-xl text-slate-200/45 transition-all duration-150 hover:bg-red-500/10 hover:text-red-400"
                title="Clear chat"
              >
                <Trash2 size={13} />
              </motion.button>
            )}
          </AnimatePresence>
        </div>
      </nav>
    </header>
  );
});


// ── Message item ───────────────────────────────────────────────────────────────

function MessageItem({ message, onFollowup }: { message: ChatMessage; onFollowup: (q: string) => void }) {
  if (message.role === "user") return <ChatBubble role="user" content={message.content} timestamp={message.timestamp} />;
  if (message.answer) return <AnswerCard answer={message.answer} onFollowup={onFollowup} timestamp={message.timestamp} />;
  return <ChatBubble role="assistant" content={message.content} timestamp={message.timestamp} errorRequestId={message.error_request_id} />;
}

// ── Composer dock ──────────────────────────────────────────────────────────────
// Absolute-positioned inside the fixed shell so it doesn't add page height.
// Gradient behind it is subtle — light ocean fade, not a heavy panel.

const ChatComposerDock = memo(function ChatComposerDock({
  input,
  loading,
  onInput,
  onKeyDown,
  onSend,
  textareaRef,
}: {
  input: string;
  loading: boolean;
  onInput: (v: string) => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
  onSend: () => void;
  textareaRef: React.RefObject<HTMLTextAreaElement>;
}) {
  const canSend = input.trim().length > 0 && !loading;

  return (
    <div
      className="absolute inset-x-0 bottom-0 z-30 px-6"
      style={{
        paddingBottom: "max(1.5rem, env(safe-area-inset-bottom))",
        paddingTop: "3rem",
        background: "linear-gradient(to top, rgba(0,19,31,0.88) 0%, rgba(0,19,31,0.45) 55%, transparent 100%)",
        pointerEvents: "none",
      }}
    >
      <div className="mx-auto w-full max-w-4xl" style={{ pointerEvents: "auto" }}>
        <form
          onSubmit={(e) => { e.preventDefault(); onSend(); }}
          className="flex min-h-[58px] items-end gap-3 rounded-[28px] border px-5 py-3"
          style={{
            borderColor: canSend ? "rgba(255,122,90,0.40)" : "rgba(34,211,238,0.22)",
            background: "rgba(3,17,31,0.58)",
            backdropFilter: "blur(24px)",
            WebkitBackdropFilter: "blur(24px)",
            boxShadow: canSend
              ? "0 18px 60px rgba(0,0,0,0.36), 0 0 0 3px rgba(255,122,90,0.08)"
              : "0 18px 60px rgba(0,0,0,0.30)",
            transition: "border-color 0.2s, box-shadow 0.2s",
          }}
        >
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => onInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Ask about your finances…"
            rows={1}
            className="chat-scrollbar flex-1 resize-none bg-transparent text-base leading-relaxed focus:outline-none"
            style={{
              minHeight: "32px",
              maxHeight: "128px",
              color: "var(--text-primary)",
              overflowY: "auto",
            }}
            disabled={loading}
          />

          <motion.button
            type="submit"
            whileHover={canSend ? { scale: 1.06, y: -1 } : undefined}
            whileTap={canSend ? { scale: 0.94 } : undefined}
            disabled={!canSend}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-30"
            style={{
              background: canSend
                ? "linear-gradient(135deg, #FF7A5A, #FFA38F)"
                : "var(--btn-glass-bg)",
              boxShadow: canSend ? "0 4px 16px rgba(255,122,90,0.38)" : "none",
            }}
          >
            {loading ? (
              <Loader2 size={15} className="animate-spin text-white" />
            ) : (
              <Send size={14} style={{ color: canSend ? "white" : "var(--text-muted)" }} />
            )}
          </motion.button>
        </form>

        <p className="mt-2 text-center text-xs" style={{ color: "rgba(160,190,205,0.40)" }}>
          <Lock size={9} className="mb-0.5 mr-1 inline" />
          All data stays on your device · Enter to send · Shift+Enter for new line
        </p>
      </div>
    </div>
  );
});

// ── Page ───────────────────────────────────────────────────────────────────────

const SCROLL_THRESHOLD = 80;

// Approximate composer dock height (gradient + form + hint) for padding math.
// Must match the visual bottom of the composer form.
const COMPOSER_OFFSET = "156px";
// Nav height
const NAV_HEIGHT = "80px";

export function ChatPage() {
  const { chatHistory, addChatMessage, clearChat } = useAppStore();
  const [input, setInput]           = useState("");
  const [loading, setLoading]       = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [bulkUploadOpen, setBulkUploadOpen] = useState(false);
  const [docsOpen, setDocsOpen]     = useState(false);
  const [showJumpBtn, setShowJumpBtn] = useState(false);
  const messagesEndRef   = useRef<HTMLDivElement>(null);
  const scrollRef        = useRef<HTMLDivElement>(null);
  const textareaRef      = useRef<HTMLTextAreaElement>(null) as React.RefObject<HTMLTextAreaElement>;

  const hasMessages = chatHistory.length > 0;

  const isNearBottom = useCallback(() => {
    const el = scrollRef.current;
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
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => setShowJumpBtn(!isNearBottom());
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [isNearBottom]);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 128)}px`;
  }, [input]);

  const send = useCallback(async (question?: string) => {
    const q = (question ?? input).trim();
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
  }, [input, loading, chatHistory, addChatMessage]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }, [send]);

  return (
    <>
      <style>{`
        /* Responsive: hide content before composer collides */
        @media (max-height: 820px) {
          .chat-suggestion-grid { display: none !important; }
        }
        @media (max-height: 720px) {
          .chat-category-chips { display: none !important; }
          .chat-subtitle-secondary { display: none !important; }
          .chat-mascot { width: 64px !important; height: 64px !important; }
        }
        @media (max-height: 640px) {
          .chat-mascot { display: none !important; }
          .chat-hero-title { font-size: clamp(1.75rem, 4vw, 2.5rem) !important; }
        }

        /* Light theme glass nav surface */
        [data-theme="light"] .chat-top-nav:hover .chat-nav-glass,
        [data-theme="light"] .chat-top-nav:focus-within .chat-nav-glass {
          background-color: rgba(240,247,252,0.88) !important;
          border-bottom-color: rgba(31,111,139,0.15) !important;
        }

        /* Subtle teal scrollbar — only in message list / textarea */
        .chat-scrollbar {
          scrollbar-width: thin;
          scrollbar-color: rgba(34,211,238,0.25) transparent;
        }
        .chat-scrollbar::-webkit-scrollbar { width: 6px; }
        .chat-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .chat-scrollbar::-webkit-scrollbar-thumb {
          background: rgba(34,211,238,0.20);
          border-radius: 999px;
        }
        .chat-scrollbar::-webkit-scrollbar-thumb:hover {
          background: rgba(34,211,238,0.35);
        }
      `}</style>

      {/*
        Fixed full-viewport shell — inset-0 so it covers the full screen.
        The Sidebar returns null when activePage === "chat", so there's no
        260px left column competing for space. This shell IS the viewport.
        overflow-hidden on this shell is what prevents any page-level scroll.
      */}
      <div className="fixed inset-0 overflow-hidden" style={{ zIndex: 20 }}>

        {/* Single top nav — transparent at rest, glass on hover */}
        <ChatTopNav
          onUpload={() => setUploadOpen(true)}
          onDocs={() => setDocsOpen(true)}
          onClearChat={clearChat}
          hasMessages={hasMessages}
        />

        {/* ── Active message state ─────────────────────────────────────────── */}
        {hasMessages && (
          <div
            className="flex h-full flex-col overflow-hidden"
            style={{
              paddingTop: NAV_HEIGHT,
              paddingBottom: COMPOSER_OFFSET,
            }}
          >
            {/* Message list — the ONLY scroll container on the entire page */}
            <div
              ref={scrollRef}
              className="chat-scrollbar min-h-0 flex-1 overflow-y-auto overscroll-contain px-6 py-6"
            >
              <div className="mx-auto max-w-2xl space-y-5">
                {chatHistory.map((msg, i) => (
                  <MessageItem key={i} message={msg} onFollowup={send} />
                ))}

                <AnimatePresence>
                  {loading && <TypingIndicator />}
                </AnimatePresence>

                <div ref={messagesEndRef} />
              </div>
            </div>

            {/* Jump to latest button */}
            <AnimatePresence>
              {showJumpBtn && (
                <motion.button
                  initial={{ opacity: 0, y: 8, scale: 0.92 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: 8, scale: 0.92 }}
                  transition={{ duration: 0.18 }}
                  onClick={() => scrollToBottom()}
                  className="absolute left-1/2 -translate-x-1/2 flex items-center gap-1.5 rounded-full px-3.5 py-2 text-sm font-semibold text-white"
                  style={{
                    bottom: "calc(" + COMPOSER_OFFSET + " + 1rem)",
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
        )}

        {/* Composer — absolute bottom of the fixed shell */}
        <ChatComposerDock
          input={input}
          loading={loading}
          onInput={setInput}
          onKeyDown={handleKeyDown}
          onSend={send}
          textareaRef={textareaRef}
        />
      </div>

      {/* Modals render outside the fixed shell so they aren't clipped */}
      <UploadModal open={uploadOpen} onClose={() => setUploadOpen(false)} onUploaded={() => {}} />
      <BulkUploadModal open={bulkUploadOpen} onClose={() => setBulkUploadOpen(false)} onUploaded={() => {}} />
      <DocumentsModal open={docsOpen} onClose={() => setDocsOpen(false)} />
    </>
  );
}
