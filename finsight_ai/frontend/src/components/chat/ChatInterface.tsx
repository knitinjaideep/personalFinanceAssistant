/**
 * ChatInterface — extended chat screen with:
 * - Bucket scope selector (all / specific buckets)
 * - Streaming SSE responses with live agent trace
 * - Source citations per assistant message
 * - Pipeline state machine via usePipelineReducer (no duplicate terminal events)
 */

import React, { useState, useRef, useEffect, useCallback } from "react";
import { AlertTriangle, Bot, ChevronDown, ChevronRight, Loader2, Send, Trash2, User } from "lucide-react";
import { clsx } from "clsx";

import { useAppStore } from "../../store/appStore";
import { useBuckets } from "../../hooks/useBuckets";
import { useEventStream } from "../../hooks/useEventStream";
import {
  usePipelineReducer,
  isGenerationStalling,
  stageColor,
  stageLabelFor,
} from "../../hooks/usePipelineReducer";
import { chatApi } from "../../api/chat";
import { SourceCitations } from "./SourceCitations";
import { AnswerCard } from "../answers/AnswerCard";
import type { ChatMessage, ProcessingEvent, StructuredAnswer } from "../../types";
import type { SourceChunk } from "./SourceCitations";

// ── Clean stage progress bar ──────────────────────────────────────────────────
//
// Shows a single human-friendly status line + progress bar.
// Technical trace is hidden by default behind an expandable section.

interface StageProgressProps {
  pipelineState: ReturnType<typeof usePipelineReducer>["state"];
  isStreaming: boolean;
  events: ProcessingEvent[];
}

function StageProgressBar({ pipelineState, isStreaming, events }: StageProgressProps) {
  const [traceOpen, setTraceOpen] = useState(false);

  if (!isStreaming && pipelineState.stage === "idle") return null;

  const stalling = isGenerationStalling(pipelineState);
  const color = stageColor(pipelineState);
  const label = stageLabelFor(pipelineState, stalling);

  const barColor: Record<string, string> = {
    blue: "bg-blue-500",
    green: "bg-green-500",
    amber: "bg-amber-400",
    red: "bg-red-500",
  };

  const spinColor: Record<string, string> = {
    blue: "text-blue-500",
    green: "text-green-500",
    amber: "text-amber-500",
    red: "text-red-500",
  };

  const isDone = pipelineState.isTerminal;

  // Build clean step list for the progress display.
  // For no-data path, skip the "Generating answer" step entirely.
  const steps = pipelineState.isNoDataPath
    ? ["Searching your documents", "No matching records found", "Preparing response", "Answer ready"]
    : ["Searching your documents", "Reviewing matching records", "Generating answer", "Answer ready"];

  const currentStepIndex: Record<string, number> = {
    idle: -1,
    retrieving: 0,
    retrieval_complete: 1,
    preparing_response: 2,
    building_answer: 2,
    fallback_building: 2,
    done: 3,
    failed: 3,
  };
  const activeStep = currentStepIndex[pipelineState.stage] ?? -1;

  return (
    <div className="rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 space-y-2.5">
      {/* Progress bar */}
      <div className="flex items-center gap-3">
        {!isDone && (
          <Loader2
            size={13}
            className={clsx("shrink-0 animate-spin", spinColor[color])}
          />
        )}
        <div className="flex-1 bg-gray-200 rounded-full h-1.5 overflow-hidden">
          <div
            className={clsx(
              "h-full rounded-full transition-all duration-500",
              barColor[color]
            )}
            style={{
              width: `${Math.max(pipelineState.progress, pipelineState.stage === "idle" ? 5 : 0)}%`,
            }}
          />
        </div>
      </div>

      {/* Clean step list */}
      <div className="flex items-center gap-3 flex-wrap">
        {steps.map((step, i) => {
          const isActive = i === activeStep;
          const isPast = i < activeStep || isDone;
          const isFailed = pipelineState.stage === "failed" && i === activeStep;
          return (
            <React.Fragment key={step}>
              <span
                className={clsx(
                  "text-xs",
                  isFailed
                    ? "text-red-500 font-medium"
                    : isActive
                    ? clsx("font-medium", color === "amber" ? "text-amber-700" : "text-blue-600")
                    : isPast
                    ? "text-gray-400 line-through"
                    : "text-gray-300"
                )}
              >
                {step}
              </span>
              {i < steps.length - 1 && (
                <span className="text-gray-300 text-xs">›</span>
              )}
            </React.Fragment>
          );
        })}
      </div>

      {/* Stall or warning banner */}
      {(stalling || color === "amber") && !isDone && (
        <p className="text-xs text-amber-600 font-medium">
          <AlertTriangle size={11} className="inline mr-1 mb-0.5" />
          {label}
        </p>
      )}

      {/* Expandable technical trace */}
      {events.length > 0 && (
        <button
          onClick={() => setTraceOpen((v) => !v)}
          className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 transition-colors"
        >
          {traceOpen ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
          Technical trace
        </button>
      )}
      {traceOpen && events.length > 0 && (
        <div className="mt-1 space-y-0.5 max-h-32 overflow-y-auto border-t border-gray-200 pt-2">
          {events.map((e, i) => (
            <p key={i} className="text-[10px] font-mono text-gray-400 truncate">
              {e.event_type}: {e.message ?? ""}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

const EXAMPLE_QUESTIONS = [
  "How much did I pay in fees in the last 6 months?",
  "What recurring charges do I have across all accounts?",
  "Compare my account balances month-over-month.",
  "Which account had the highest fees this year?",
  "Summarize deposits and withdrawals for this month.",
  "What financial statements are missing for 2026?",
];

// ── Per-message type ───────────────────────────────────────────────────────────

interface RichMessage extends ChatMessage {
  sources?: SourceChunk[];
  structured_answer?: StructuredAnswer | null;
  answer_type?: string;
  /** From pipeline_meta.pipeline_stage: 'llm' | 'retrieval_only' | 'safe_error' */
  pipeline_stage?: string;
  warnings?: string[];
}

// ── Message bubble ─────────────────────────────────────────────────────────────

interface MessageBubbleProps {
  message: RichMessage;
  onFollowup?: (q: string) => void;
}

function MessageBubble({ message, onFollowup }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const isStructured =
    !isUser && message.structured_answer != null;

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

      <div className="flex flex-col gap-1 max-w-[85%] min-w-0">
        {isStructured && message.structured_answer ? (
          // Structured answer — AnswerCard handles fallback banner internally
          <div className="w-full">
            <AnswerCard
              structured={message.structured_answer}
              pipelineStage={message.pipeline_stage ?? "llm"}
              warnings={message.warnings ?? []}
              onFollowup={onFollowup}
            />
          </div>
        ) : (
          // Prose — render as styled bubble
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
        )}

        {!isUser && message.sources && message.sources.length > 0 && !isStructured && (
          <div className="ml-1">
            <SourceCitations sources={message.sources} />
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export function ChatInterface() {
  const { chatHistory, addChatMessage, clearChat, selectedBucket, setSelectedBucket } = useAppStore();
  const { buckets } = useBuckets();

  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [richHistory, setRichHistory] = useState<RichMessage[]>([]);

  // Derive bucket IDs from global selectedBucket context
  const selectedBucketIds = buckets
    .filter((b) => b.name.toLowerCase() === selectedBucket)
    .map((b) => b.id);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Pipeline state machine — replaces ad-hoc derivePipelineStage()
  const { state: pipelineState, pushEvent, reset: resetPipeline } = usePipelineReducer();

  const { events, isStreaming, clearEvents, streamChatQuery } = useEventStream({
    // Feed each SSE event into the reducer as it arrives.
    onEvent: pushEvent,
  });

  // Sync global chatHistory into rich history on mount
  useEffect(() => {
    setRichHistory(chatHistory.map((m) => ({ ...m })));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [richHistory, isLoading, isStreaming]);

  // Bucket toggle for the chat header
  const handleBucketToggle = useCallback(() => {
    setSelectedBucket(selectedBucket === "investments" ? "banking" : "investments");
  }, [selectedBucket, setSelectedBucket]);

  const handleSend = useCallback(async () => {
    const q = input.trim();
    if (!q || isLoading || isStreaming) return;

    setInput("");
    clearEvents();
    resetPipeline();

    const userMsg: RichMessage = {
      role: "user",
      content: q,
      timestamp: new Date().toISOString(),
    };
    setRichHistory((prev) => [...prev, userMsg]);
    addChatMessage(userMsg);
    setIsLoading(true);

    try {
      const result = await streamChatQuery({
        question: q,
        conversation_history: chatHistory,
        bucket_ids: selectedBucketIds.length > 0 ? selectedBucketIds : undefined,
        session_id: crypto.randomUUID(),
      });

      if (result) {
        // Extract pipeline_meta from the result (added in Phase 2.7 schema upgrade)
        const raw = result as unknown as Record<string, unknown>;
        const meta = raw.pipeline_meta as Record<string, unknown> | undefined;

        const assistantMsg: RichMessage = {
          role: "assistant",
          content: result.answer,
          timestamp: new Date().toISOString(),
          sources: result.sources as SourceChunk[],
          structured_answer: result.structured_answer as StructuredAnswer | null,
          answer_type: result.answer_type,
          pipeline_stage: (meta?.pipeline_stage as string | undefined) ?? "llm",
          warnings: (meta?.warnings as string[] | undefined) ?? [],
        };
        setRichHistory((prev) => [...prev, assistantMsg]);
        addChatMessage({ role: "assistant", content: result.answer });
      } else {
        // Fallback: non-streaming query endpoint
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
    resetPipeline,
    streamChatQuery,
    chatHistory,
    selectedBucketIds,
    addChatMessage,
    buckets,
    selectedBucket,
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
    resetPipeline();
  }, [clearChat, clearEvents, resetPipeline]);

  const handleExampleClick = useCallback((q: string) => {
    setInput(q);
    inputRef.current?.focus();
  }, []);

  const handleFollowup = useCallback((q: string) => {
    setInput(q);
    inputRef.current?.focus();
  }, []);

  // busy: true while a request is in flight.
  // We rely on pipelineState.isTerminal as an additional gate because
  // isStreaming (from the hook) may clear slightly before the terminal
  // response_complete event has been processed by the reducer.
  const busy = isLoading || (isStreaming && !pipelineState.isTerminal);

  // Show progress bar while streaming OR while pipeline hasn't reached terminal.
  // Once isTerminal is true, the bar disappears and the answer card is shown.
  const showProgress =
    isStreaming || (pipelineState.stage !== "idle" && !pipelineState.isTerminal);

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

      {/* Bucket context indicator */}
      <div className="px-6 py-2 border-b bg-gray-50 flex items-center gap-2">
        <span className="text-xs text-gray-500">Context:</span>
        <button
          onClick={handleBucketToggle}
          disabled={busy}
          className="text-xs font-medium px-2.5 py-1 rounded-md bg-white border border-gray-200 text-gray-700 hover:bg-gray-100 transition-colors capitalize disabled:opacity-50"
        >
          {selectedBucket}
        </button>
        <span className="text-xs text-gray-400">Click to switch</span>
      </div>

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
              <MessageBubble key={i} message={msg} onFollowup={handleFollowup} />
            ))}

            {/* Pipeline progress bar — shown while streaming or until terminal.
                Technical trace is nested inside and collapsed by default. */}
            {showProgress && (
              <div className="ml-10">
                <StageProgressBar
                  pipelineState={pipelineState}
                  isStreaming={isStreaming}
                  events={events}
                />
              </div>
            )}

            {/* Fallback spinner if no events yet */}
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
          <span className="ml-2 text-blue-500 capitalize">
            · Searching {selectedBucket}
          </span>
        </p>
      </div>
    </div>
  );
}
