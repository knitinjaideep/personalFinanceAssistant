/**
 * usePipelineReducer — typed reducer for the chat pipeline state machine.
 *
 * Replaces the ad-hoc ``derivePipelineStage()`` function in ChatInterface with
 * a proper reducer so that:
 *   1. Stage transitions are explicit and exhaustive.
 *   2. Once a terminal stage is reached, all further events are ignored.
 *   3. Duplicate "response_complete" events are deduped.
 *   4. Stall detection is driven by timestamps attached to each event.
 *   5. SSE stream close without terminal → synthesize "failed" terminal state.
 *
 * Pipeline stage model (strictly forward — no backwards transitions):
 *
 *   idle
 *    └─ chat_retrieve_started      → retrieving
 *        └─ chat_retrieve_done     → retrieval_complete
 *            ├─ chat_no_data           → preparing_response   (LLM skipped)
 *            ├─ chat_partial_data      → preparing_response   (LLM skipped)
 *            └─ chat_generate_started  → building_answer
 *                ├─ chat_generate_progress  (no stage change, updates progress + ts)
 *                ├─ chat_fallback_triggered → fallback_building
 *                └─ chat_generate_done      → building_answer (progress bump)
 *            └─ response_complete  → done  (TERMINAL — all paths)
 *    └─ error                      → failed (TERMINAL)
 *    └─ stream_closed_without_terminal → failed (TERMINAL — synthesized by frontend)
 *
 * Terminal stages: done | failed
 * Once terminal, the reducer returns state unchanged for every event.
 */

import { useReducer, useCallback } from "react";
import type { ProcessingEvent } from "../types";

// ── Stage types ───────────────────────────────────────────────────────────────

export type PipelineStage =
  | "idle"
  | "retrieving"
  | "retrieval_complete"
  | "preparing_response"  // no-data / partial-data deterministic path (LLM skipped)
  | "building_answer"
  | "fallback_building"
  | "done"
  | "failed";

/**
 * Human-friendly labels for the clean progress indicator.
 * These hide internal pipeline detail from the default view.
 */
const STAGE_DISPLAY_LABELS: Record<PipelineStage, string> = {
  idle: "Waiting…",
  retrieving: "Searching your documents…",
  retrieval_complete: "Reviewing matching records…",
  preparing_response: "Preparing response…",
  building_answer: "Generating answer…",
  fallback_building: "Preparing retrieved answer…",
  done: "Answer ready",
  failed: "Something went wrong",
};

// ── State ─────────────────────────────────────────────────────────────────────

export interface PipelineState {
  /** Current stage of the pipeline. */
  stage: PipelineStage;
  /** Progress percentage 0–100. Never decreases. */
  progress: number;
  /** ISO timestamp of the last received event (for stall detection). */
  lastEventAt: string | null;
  /** ISO timestamp of the last chat_generate_progress or chat_generate_started event. */
  lastGenerateEventAt: string | null;
  /** Human-readable status label derived from stage (used in clean progress view). */
  message: string;
  /** Whether a fallback answer was used (set from response_complete payload). */
  fallbackTriggered: boolean;
  /** Reason string from chat_fallback_triggered event. */
  fallbackReason: string | null;
  /** Warning messages collected across all events. */
  warnings: string[];
  /** Whether the pipeline has reached a terminal stage. */
  isTerminal: boolean;
  /**
   * True when the pipeline took the deterministic no-data path.
   * The frontend can use this to skip showing a fake "Generating answer" step.
   */
  isNoDataPath: boolean;
}

export const INITIAL_STATE: PipelineState = {
  stage: "idle",
  progress: 0,
  lastEventAt: null,
  lastGenerateEventAt: null,
  message: "Waiting…",
  fallbackTriggered: false,
  fallbackReason: null,
  warnings: [],
  isTerminal: false,
  isNoDataPath: false,
};

// ── Actions ───────────────────────────────────────────────────────────────────

export interface PipelineEventAction {
  type: "EVENT";
  event: ProcessingEvent;
}

export interface PipelineResetAction {
  type: "RESET";
}

export type PipelineAction = PipelineEventAction | PipelineResetAction;

// ── Reducer ───────────────────────────────────────────────────────────────────

function clampProgress(current: number, next: number): number {
  // Progress only ever increases.
  return Math.max(current, Math.min(100, Math.round(next)));
}

function extractProgress(event: ProcessingEvent): number {
  const raw = (event as unknown as Record<string, unknown>).progress;
  return typeof raw === "number" ? raw * 100 : 0;
}

function extractPayload(event: ProcessingEvent): Record<string, unknown> {
  return (
    ((event as unknown as Record<string, unknown>).payload as Record<string, unknown>) ?? {}
  );
}

export function pipelineReducer(
  state: PipelineState,
  action: PipelineAction
): PipelineState {
  if (action.type === "RESET") return INITIAL_STATE;

  const { event } = action;

  // ── Terminal guard — once done/failed, ignore everything. ─────────────────
  if (state.isTerminal) return state;

  const ts = event.timestamp ?? new Date().toISOString();
  const progress = extractProgress(event);
  const payload = extractPayload(event);

  switch (event.event_type) {
    case "chat_retrieve_started":
      return {
        ...state,
        stage: "retrieving",
        progress: clampProgress(state.progress, progress || 5),
        message: "Searching documents…",
        lastEventAt: ts,
      };

    case "chat_retrieve_done": {
      const chunks = payload.chunks_found as number | undefined;
      const msg =
        chunks != null
          ? `Found ${chunks} document chunk${chunks !== 1 ? "s" : ""}${
              payload.has_sql ? " + SQL data" : ""
            }`
          : "Documents searched";
      return {
        ...state,
        stage: "retrieval_complete",
        progress: clampProgress(state.progress, progress || 20),
        message: msg,
        lastEventAt: ts,
        warnings:
          (event as unknown as { status?: string }).status === "warning"
            ? [...state.warnings, "Retrieval timed out — proceeding without full context"]
            : state.warnings,
      };
    }

    case "chat_no_data":
      // Deterministic no-data path — LLM was skipped entirely.
      return {
        ...state,
        stage: "preparing_response",
        progress: clampProgress(state.progress, progress || 90),
        message: STAGE_DISPLAY_LABELS["preparing_response"],
        lastEventAt: ts,
        isNoDataPath: true,
      };

    case "chat_partial_data":
      // Deterministic partial-data path — LLM was skipped.
      return {
        ...state,
        stage: "preparing_response",
        progress: clampProgress(state.progress, progress || 90),
        message: STAGE_DISPLAY_LABELS["preparing_response"],
        lastEventAt: ts,
        isNoDataPath: true,
      };

    case "chat_generate_started":
      return {
        ...state,
        stage: "building_answer",
        progress: clampProgress(state.progress, progress || 30),
        message: STAGE_DISPLAY_LABELS["building_answer"],
        lastEventAt: ts,
        lastGenerateEventAt: ts,
      };

    case "chat_generate_progress":
      // No stage change — just update progress and heartbeat timestamp.
      return {
        ...state,
        progress: clampProgress(state.progress, progress || state.progress),
        lastEventAt: ts,
        lastGenerateEventAt: ts,
        // Keep the clean label; don't expose elapsed seconds by default
        message: STAGE_DISPLAY_LABELS["building_answer"],
      };

    case "chat_generate_done":
      return {
        ...state,
        progress: clampProgress(state.progress, progress || 75),
        lastEventAt: ts,
        lastGenerateEventAt: ts,
        message: STAGE_DISPLAY_LABELS["building_answer"],
      };

    case "chat_fallback_triggered": {
      const reason = (payload.reason as string | undefined) ?? "unknown";
      return {
        ...state,
        stage: "fallback_building",
        progress: clampProgress(state.progress, 75),
        message: STAGE_DISPLAY_LABELS["fallback_building"],
        fallbackTriggered: true,
        fallbackReason: reason,
        lastEventAt: ts,
        warnings: payload.error
          ? [...state.warnings, String(payload.error)]
          : state.warnings,
      };
    }

    case "response_complete": {
      // ── SOLE TERMINAL EVENT ──────────────────────────────────────────
      // All pipeline paths (LLM, no-data, partial-data, fallback) converge here.
      // Once this fires, isTerminal = true and all subsequent events are ignored.
      const meta = payload.pipeline_meta as Record<string, unknown> | undefined;
      const metaWarnings = (meta?.warnings as string[] | undefined) ?? [];
      const metaFallback = (meta?.fallback_triggered as boolean | undefined) ?? false;
      const metaReason = (meta?.fallback_reason as string | undefined) ?? null;
      const pipelineStage = (meta?.pipeline_stage as string | undefined) ?? "llm";
      const isNoData = pipelineStage === "no_data" || pipelineStage === "partial_data";

      return {
        ...state,
        stage: "done",
        progress: 100,
        message: STAGE_DISPLAY_LABELS["done"],
        fallbackTriggered: metaFallback || state.fallbackTriggered,
        fallbackReason: metaReason || state.fallbackReason,
        warnings: [...new Set([...state.warnings, ...metaWarnings])],
        lastEventAt: ts,
        isTerminal: true,
        isNoDataPath: isNoData || state.isNoDataPath,
      };
    }

    case "error": {
      return {
        ...state,
        stage: "failed",
        progress: state.progress,
        message: STAGE_DISPLAY_LABELS["failed"],
        lastEventAt: ts,
        isTerminal: true,
      };
    }

    case "stream_closed_without_terminal": {
      // Synthesized by the frontend when the SSE stream closes before
      // a response_complete event arrives (network drop, server error, etc.).
      // This is a terminal state — stops the loading indicator immediately.
      return {
        ...state,
        stage: "failed",
        progress: state.progress,
        message: "Connection ended before answer arrived. Please try again.",
        lastEventAt: ts,
        isTerminal: true,
      };
    }

    default:
      // Unknown event — update last-seen timestamp, no stage change.
      return { ...state, lastEventAt: ts };
  }
}

// ── Stall detection ───────────────────────────────────────────────────────────

/** Returns true if we're in building_answer and the last generate heartbeat is >12s old. */
export function isGenerationStalling(state: PipelineState): boolean {
  if (state.stage !== "building_answer") return false;
  if (!state.lastGenerateEventAt) return false;
  const age = Date.now() - new Date(state.lastGenerateEventAt).getTime();
  return age > 12_000;
}

// ── Stage display helpers ─────────────────────────────────────────────────────

export function stageLabelFor(state: PipelineState, stalling: boolean): string {
  if (stalling) return "Still generating — this may take a moment…";
  // Return the canonical stage label (not raw message) for clean display.
  return STAGE_DISPLAY_LABELS[state.stage] ?? state.message;
}

export type StageColor = "blue" | "amber" | "green" | "red";

export function stageColor(state: PipelineState): StageColor {
  if (state.stage === "failed") return "red";
  if (state.stage === "done" && state.fallbackTriggered) return "amber";
  if (state.stage === "done") return "green";
  if (state.stage === "fallback_building") return "amber";
  return "blue";
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function usePipelineReducer() {
  const [state, dispatch] = useReducer(pipelineReducer, INITIAL_STATE);

  const pushEvent = useCallback(
    (event: ProcessingEvent) => dispatch({ type: "EVENT", event }),
    []
  );

  const reset = useCallback(() => dispatch({ type: "RESET" }), []);

  return { state, pushEvent, reset };
}
