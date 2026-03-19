import { useState, useRef, useEffect } from "react";
import { Send, Trash2, Loader2, Sparkles } from "lucide-react";
import { api } from "../api/client";
import { useAppStore } from "../store/appStore";
import type { ChatMessage, ChatResponse } from "../types";
import { ChatBubble } from "../components/chat/ChatBubble";
import { AnswerCard } from "../components/chat/AnswerCard";

const EXAMPLE_QUESTIONS = [
  "What fees have I been charged?",
  "Show me my account balances",
  "List my recent transactions",
  "What's my portfolio worth?",
  "Which institutions do I have data from?",
  "Explain the fee section of my statement",
];

export function ChatPage() {
  const { chatHistory, addChatMessage, clearChat } = useAppStore();
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatHistory]);

  const send = async (question?: string) => {
    const q = (question || input).trim();
    if (!q || loading) return;
    setInput("");

    addChatMessage({ role: "user", content: q });
    setLoading(true);

    try {
      const history = chatHistory.slice(-6).map((m) => ({
        role: m.role,
        content: m.content,
      }));
      const resp = await api.post<ChatResponse>("/chat/query", {
        question: q,
        history,
      });
      addChatMessage({
        role: "assistant",
        content: resp.raw_text || resp.answer.summary,
        answer: resp.answer,
      });
    } catch (err: any) {
      addChatMessage({
        role: "assistant",
        content: `Sorry, something went wrong: ${err.detail || err.message}`,
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

  return (
    <div className="flex flex-col h-full bg-pearl">
      {/* Header */}
      <div className="px-6 py-4 bg-white border-b border-ocean-50 flex items-center justify-between shrink-0">
        <div>
          <h1 className="text-base font-semibold text-slate">
            Ask Coral
          </h1>
          <p className="text-xs text-ocean-DEFAULT/50">
            Ask anything about your financial statements
          </p>
        </div>
        {chatHistory.length > 0 && (
          <button
            onClick={clearChat}
            className="flex items-center gap-1.5 text-xs text-ocean-DEFAULT/40 hover:text-negative transition-colors"
          >
            <Trash2 size={12} />
            Clear chat
          </button>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-5">
        {chatHistory.length === 0 ? (
          <ChatEmptyState onQuestion={send} />
        ) : (
          chatHistory.map((msg, i) => (
            <MessageItem key={i} message={msg} onFollowup={send} />
          ))
        )}

        {loading && (
          <div className="flex items-center gap-2.5 text-sm text-ocean-DEFAULT/50 pl-1">
            <Loader2 size={14} className="animate-spin text-coral" />
            Analyzing your data...
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input bar */}
      <div className="px-6 py-4 bg-white border-t border-ocean-50 shrink-0">
        <div className="flex gap-3 max-w-3xl mx-auto">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your finances..."
            className="flex-1 px-4 py-3 rounded-xl border border-ocean-100 text-sm text-slate bg-pearl placeholder:text-ocean-DEFAULT/30 focus:outline-none focus:ring-2 focus:ring-coral/30 focus:border-coral/50 transition-all"
            disabled={loading}
          />
          <button
            onClick={() => send()}
            disabled={loading || !input.trim()}
            className="px-4 py-3 rounded-xl text-white font-medium text-sm transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed"
            style={{
              background: input.trim()
                ? "linear-gradient(135deg, #FF7A5A, #FFA38F)"
                : undefined,
              backgroundColor: !input.trim() ? "#CDEDF6" : undefined,
            }}
          >
            <Send size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}

function ChatEmptyState({ onQuestion }: { onQuestion: (q: string) => void }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
      <img
        src="/mascot.png"
        alt="Coral mascot"
        className="w-20 h-20 object-contain mb-5 opacity-90 drop-shadow"
      />
      <h2 className="text-lg font-semibold text-slate mb-2">
        Ask me anything about your finances
      </h2>
      <p className="text-sm text-ocean-DEFAULT/50 mb-8 max-w-sm leading-relaxed">
        Ask anything about your statements — fees, balances, spending, portfolio.
        Everything stays on your device.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full max-w-lg">
        {EXAMPLE_QUESTIONS.map((q) => (
          <button
            key={q}
            onClick={() => onQuestion(q)}
            className="px-4 py-2.5 text-left text-sm text-slate/70 bg-white border border-ocean-100 rounded-xl hover:border-coral/40 hover:bg-coral-50/30 hover:text-coral transition-all duration-150 shadow-soft"
          >
            <span className="text-coral mr-1.5">
              <Sparkles size={11} className="inline mb-0.5" />
            </span>
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}

function MessageItem({
  message,
  onFollowup,
}: {
  message: ChatMessage;
  onFollowup: (q: string) => void;
}) {
  if (message.role === "user") {
    return <ChatBubble role="user" content={message.content} />;
  }
  if (message.answer) {
    return <AnswerCard answer={message.answer} onFollowup={onFollowup} />;
  }
  return <ChatBubble role="assistant" content={message.content} />;
}
