/**
 * Tests for usePipelineReducer state machine.
 *
 * Run with: npx vitest (after adding vitest to package.json)
 *
 * Covers:
 * - Empty retrieval (chat_no_data) → terminal done without building_answer stage
 * - Duplicate response_complete events are ignored (terminal guard)
 * - stream_closed_without_terminal synthesizes failed terminal state
 * - No stuck loading: terminal state stops progress updates
 * - Partial data path renders correctly
 * - Standard LLM path still works
 */

import { describe, it, expect } from "vitest";
import { pipelineReducer, INITIAL_STATE } from "../usePipelineReducer";
import type { PipelineState } from "../usePipelineReducer";
import type { ProcessingEvent } from "../../types";

// ── Helpers ───────────────────────────────────────────────────────────────────

const ts = () => new Date().toISOString();

function makeEvent(
  event_type: string,
  overrides: Partial<ProcessingEvent & { progress?: number; payload?: Record<string, unknown> }> = {}
): ProcessingEvent {
  return {
    id: "evt-1",
    session_id: "test-session",
    event_type,
    step_name: "test",
    stage: "test",
    agent_name: "chat_pipeline",
    status: "complete",
    message: `Event: ${event_type}`,
    timestamp: ts(),
    ...overrides,
  } as unknown as ProcessingEvent;
}

function pushEvent(state: PipelineState, event_type: string, overrides = {}): PipelineState {
  return pipelineReducer(state, { type: "EVENT", event: makeEvent(event_type, overrides) });
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("pipelineReducer — no-data path", () => {
  it("transitions idle → retrieving → retrieval_complete → preparing_response", () => {
    let state = INITIAL_STATE;
    state = pushEvent(state, "chat_retrieve_started");
    expect(state.stage).toBe("retrieving");

    state = pushEvent(state, "chat_retrieve_done", { payload: { chunks_found: 0, sql_rows: 0 } });
    expect(state.stage).toBe("retrieval_complete");

    state = pushEvent(state, "chat_no_data", { progress: 0.9 });
    expect(state.stage).toBe("preparing_response");
    expect(state.isNoDataPath).toBe(true);
    // Must NOT have entered building_answer stage
    expect(state.stage).not.toBe("building_answer");
  });

  it("reaches done terminal on response_complete after no-data path", () => {
    let state = INITIAL_STATE;
    state = pushEvent(state, "chat_retrieve_started");
    state = pushEvent(state, "chat_retrieve_done");
    state = pushEvent(state, "chat_no_data");

    state = pushEvent(state, "response_complete", {
      payload: {
        answer: "Nothing found.",
        pipeline_meta: { pipeline_stage: "no_data", fallback_triggered: false, warnings: [] },
      },
    });

    expect(state.stage).toBe("done");
    expect(state.isTerminal).toBe(true);
    expect(state.progress).toBe(100);
    expect(state.isNoDataPath).toBe(true);
  });
});

describe("pipelineReducer — terminal guard", () => {
  it("ignores all events after response_complete (duplicate terminal guard)", () => {
    let state = INITIAL_STATE;
    state = pushEvent(state, "chat_retrieve_started");
    state = pushEvent(state, "response_complete", {
      payload: {
        answer: "First answer.",
        pipeline_meta: { pipeline_stage: "llm", fallback_triggered: false, warnings: [] },
      },
    });

    expect(state.isTerminal).toBe(true);
    const terminalState = state;

    // Second response_complete — must be ignored entirely
    state = pushEvent(state, "response_complete", {
      payload: {
        answer: "Second answer.",
        pipeline_meta: { pipeline_stage: "llm", fallback_triggered: false, warnings: [] },
      },
    });

    expect(state).toBe(terminalState); // reference equality — no new state object
  });

  it("ignores events after error terminal state", () => {
    let state = INITIAL_STATE;
    state = pushEvent(state, "error");
    expect(state.isTerminal).toBe(true);
    const terminalState = state;

    state = pushEvent(state, "chat_retrieve_started");
    expect(state).toBe(terminalState);
  });
});

describe("pipelineReducer — stream_closed_without_terminal", () => {
  it("synthesized stream close event produces failed terminal state", () => {
    let state = INITIAL_STATE;
    state = pushEvent(state, "chat_retrieve_started");
    state = pushEvent(state, "chat_generate_started");

    // Simulate stream close without terminal
    state = pushEvent(state, "stream_closed_without_terminal");

    expect(state.stage).toBe("failed");
    expect(state.isTerminal).toBe(true);
    expect(state.message).toContain("Connection ended");
  });

  it("does not change state after stream close terminal", () => {
    let state = INITIAL_STATE;
    state = pushEvent(state, "stream_closed_without_terminal");
    const terminalState = state;

    // Further events should be no-ops
    state = pushEvent(state, "chat_generate_done");
    expect(state).toBe(terminalState);
  });
});

describe("pipelineReducer — LLM path", () => {
  it("transitions through full LLM path to done", () => {
    let state = INITIAL_STATE;
    state = pushEvent(state, "chat_retrieve_started");
    expect(state.stage).toBe("retrieving");

    state = pushEvent(state, "chat_retrieve_done", {
      payload: { chunks_found: 5, sql_rows: 0 },
    });
    expect(state.stage).toBe("retrieval_complete");

    state = pushEvent(state, "chat_generate_started");
    expect(state.stage).toBe("building_answer");
    expect(state.isNoDataPath).toBe(false);

    state = pushEvent(state, "chat_generate_done");
    expect(state.stage).toBe("building_answer"); // no stage change on done

    state = pushEvent(state, "response_complete", {
      payload: {
        answer: "Answer text.",
        pipeline_meta: { pipeline_stage: "llm", fallback_triggered: false, warnings: [] },
      },
    });
    expect(state.stage).toBe("done");
    expect(state.isTerminal).toBe(true);
  });

  it("progress never decreases", () => {
    let state = INITIAL_STATE;
    state = pushEvent(state, "chat_retrieve_started", { progress: 0.05 });
    const p1 = state.progress;
    state = pushEvent(state, "chat_retrieve_done", { progress: 0.20 });
    const p2 = state.progress;
    expect(p2).toBeGreaterThan(p1);

    // Sending a lower progress should not decrease it
    state = pushEvent(state, "chat_generate_progress", { progress: 0.10 });
    expect(state.progress).toBeGreaterThanOrEqual(p2);
  });
});

describe("pipelineReducer — partial data path", () => {
  it("transitions via chat_partial_data to preparing_response with isNoDataPath", () => {
    let state = INITIAL_STATE;
    state = pushEvent(state, "chat_retrieve_started");
    state = pushEvent(state, "chat_retrieve_done", { payload: { chunks_found: 2, sql_rows: 0 } });
    state = pushEvent(state, "chat_partial_data", { progress: 0.9 });

    expect(state.stage).toBe("preparing_response");
    expect(state.isNoDataPath).toBe(true);
  });
});

describe("pipelineReducer — reset", () => {
  it("resets to initial state", () => {
    let state = INITIAL_STATE;
    state = pushEvent(state, "chat_retrieve_started");
    state = pipelineReducer(state, { type: "RESET" });
    expect(state).toEqual(INITIAL_STATE);
  });
});
