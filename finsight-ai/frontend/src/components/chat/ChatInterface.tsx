/**
 * ChatInterface — extended chat screen with:
 * - Bucket scope selector (all / specific buckets)
 * - Streaming SSE responses with live agent trace
 * - Source citations per assistant message
 * - Fallback to non-streaming for compatibility
 */

import React, { useState, useRef, useEffect, useCallback } from "react";
import { Send, Trash2, Loader2, Bot, User } from "lucide-react";
import { clsx } from "clsx";

import { useAppStore } from "../../store/appStore";
import { useBuckets } from "../../hooks/useBuckets";
import { useEventStream } from "../../hooks/useEventStream";
import { chatApi } from "../../api/chat";
import { BucketPicker } from "./BucketPicker";
import { AgentTrace } from "./AgentTrace";
import { SourceCitations } from "./SourceCitations";
import type { ChatMessage } from "../../types";
import type { SourceChunk } from "./SourceCitations";

const EXAMPLE_QUESTIONS = [
  "How much did I pay in fees in the last 6 months?",
  "What recurring charges do I have across all accounts?",
  "Compare my account balances month-over-month.",
  "Which account had the highest fees this year?",
  "Summarize deposits and withdrawals for this month.",
  "What financial statements are missing for 2026?",
];

// ── Per-message type (extended with sources) ──────────────────────────────────

interface RichMessage extends ChatMessage {
  sources?: SourceChunk[];
}

// ── Message bubble ────────────────────────────────────────────────────────────

function MessageBubble({ message }: { message: RichMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={clsx("flex gap-3", isUser ? "flex-row-reverse" : "flex-row")}>
      <div
        className={clsx(
          "w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-0.5",
          isUser ? "bg-blue-600" : "bg-gray-200"
        )}
      >
        {isUser ? (
          <User size={14} className="text-white" />
        ) : (
          <Bot size={14} className="text-gray-600" />
        )}
      </div>
      <div className="flex flex-col gap-1 max-w-[80%]">
        <div
          className={clsx(
            "px-4 py-2.5 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap",
            isUser
              ? "bg-blue-600 text-white rounded-tr-sm"
              : "bg-gray-100 text-gray-800 rounded-tl-sm"
          )}
        >
          {message.content}
        </div>
        {!isUser && message.sources && message.sources.length > 0 && (
          <div className="ml-1">
            <SourceCitations sources={message.sources} />
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function ChatInterface() {
  const { chatHistory, addChatMessage, clearChat } = useAppStore();
  const { buckets } = useBuckets();

  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [selectedBucketIds, setSelectedBucketIds] = useState<string[]>([]);
  // Local rich history (not stored in global store to keep store simple)
  const [richHistory, setRichHistory] = useState<RichMessage[]>([]);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const { events, isStreaming, clearEvents, streamChatQuery } = useEventStream();

  // Sync global chatHistory into rich history on mount / external changes
  useEffect(() => {
    setRichHistory(chatHistory.map((m) => ({ ...m })));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [richHistory, isLoading, isStreaming]);

  const handleToggleBucket = useCallback((id: string) => {
    setSelectedBucketIds((prev) =>
      prev.includes(id) ? prev.filter((b) => b !== id) : [...prev, id]
    );
  }, []);

  const handleSelectAll = useCallback(() => {
    setSelectedBucketIds([]);
  }, []);

  const handleSend = useCallback(async () => {
    const q = input.trim();
    if (!q || isLoading || isStreaming) return;

    setInput("");
    clearEvents();

    const userMsg: RichMessage = {
      role: "user",
      content: q,
      timestamp: new Date().toISOString(),
    };
    setRichHistory((prev) => [...prev, userMsg]);
    addChatMessage(userMsg);
    setIsLoading(true);

    try {
      // Use streaming endpoint
      const result = await streamChatQuery({
        question: q,
        conversation_history: chatHistory,
        bucket_ids: selectedBucketIds.length > 0 ? selectedBucketIds : undefined,
        session_id: crypto.randomUUID(),
      });

      if (result) {
        const assistantMsg: RichMessage = {
          role: "assistant",
          content: result.answer,
          timestamp: new Date().toISOString(),
          sources: result.sources as SourceChunk[],
        };
        setRichHistory((prev) => [...prev, assistantMsg]);
        addChatMessage({ role: "assistant", content: result.answer });
      } else {
        // Fallback: non-streaming
        const response = await chatApi.query({
          question: q,
          conversation_history: chatHistory,
        });
        const assistantMsg: RichMessage = {
          role: "assistant",
          content: response.answer,
          timestamp: new Date().toISOString(),
          sources: response.sources as unknown as SourceChunk[],
        };
        setRichHistory((prev) => [...prev, assistantMsg]);
        addChatMessage({ role: "assistant", content: response.answer });
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to get response";
      const errorMsg: RichMessage = {
        role: "assistant",
        content: `Error: ${msg}`,
        timestamp: new Date().toISOString(),
      };
      setRichHistory((prev) => [...prev, errorMsg]);
      addChatMessage(errorMsg);
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  }, [
    input,
    isLoading,
    isStreaming,
    clearEvents,
    streamChatQuery,
    chatHistory,
    selectedBucketIds,
    addChatMessage,
  ]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleClear = useCallback(() => {
    clearChat();
    setRichHistory([]);
    clearEvents();
  }, [clearChat, clearEvents]);

  const handleExampleClick = useCallback(
    (q: string) => {
      setInput(q);
      inputRef.current?.focus();
    },
    []
  );

  const busy = isLoading || isStreaming;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b">
        <div>
          <h1 className="text-lg font-semibold text-gray-900">Financial Chat</h1>
          <p className="text-xs text-gray-500">Powered by local Ollama — fully private</p>
        </div>
        {richHistory.length > 0 && (
          <button
            onClick={handleClear}
            className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-red-500 transition-colors"
          >
            <Trash2 size={13} />
            Clear
          </button>
        )}
      </div>

      {/* Bucket scope picker */}
      {buckets.length > 0 && (
        <div className="px-6 py-2.5 border-b bg-gray-50">
          <BucketPicker
            buckets={buckets}
            selectedIds={selectedBucketIds}
            onToggle={handleToggleBucket}
            onSelectAll={handleSelectAll}
            disabled={busy}
          />
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {richHistory.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center gap-4">
            <Bot size={40} className="text-gray-300" />
            <div>
              <p className="text-sm font-medium text-gray-600">Ask about your finances</p>
              <p className="text-xs text-gray-400 mt-1">
                Upload statements first, then ask questions
              </p>
            </div>
            <div className="grid grid-cols-1 gap-2 w-full max-w-md">
              {EXAMPLE_QUESTIONS.map((q) => (
                <button
                  key={q}
                  onClick={() => handleExampleClick(q)}
                  className="text-left text-xs px-3 py-2 rounded-lg border border-gray-200 text-gray-600 hover:bg-blue-50 hover:border-blue-300 hover:text-blue-700 transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {richHistory.map((msg, i) => (
              <MessageBubble key={i} message={msg} />
            ))}

            {/* Live agent trace — shown while streaming */}
            {(events.length > 0 || isStreaming) && (
              <div className="ml-10">
                <AgentTrace events={events} isStreaming={isStreaming} />
              </div>
            )}

            {/* Loading indicator */}
            {busy && events.length === 0 && (
              <div className="flex gap-3">
                <div className="w-7 h-7 rounded-full bg-gray-200 flex items-center justify-center">
                  <Bot size={14} className="text-gray-600" />
                </div>
                <div className="bg-gray-100 rounded-2xl rounded-tl-sm px-4 py-2.5">
                  <Loader2 size={16} className="text-gray-400 animate-spin" />
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* Input */}
      <div className="border-t px-6 py-4">
        <div className="flex gap-2 items-end">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question about your financial statements…"
            rows={1}
            disabled={busy}
            className="flex-1 resize-none rounded-xl border border-gray-300 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-60"
            style={{ maxHeight: "120px" }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || busy}
            className="p-2.5 rounded-xl bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shrink-0"
          >
            {busy ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
          </button>
        </div>
        <p className="text-xs text-gray-400 mt-2">
          Enter to send · Shift+Enter for newline
          {selectedBucketIds.length > 0 && (
            <span className="ml-2 text-blue-500">
              · Querying {selectedBucketIds.length} bucket{selectedBucketIds.length > 1 ? "s" : ""}
            </span>
          )}
        </p>
      </div>
    </div>
  );
}
