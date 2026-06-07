/**
 * Base API client — thin wrapper over fetch with error handling.
 * All calls go through the Next.js rewrite proxy (/api/v1 → localhost:8000/api/v1).
 * Chat uses a 120s AbortController timeout to survive slow LLM inference.
 */

const BASE_URL = "/api/v1";

// Default timeout for regular API calls
const DEFAULT_TIMEOUT_MS = 15_000;
// Extended timeout for LLM-backed chat (qwen3:8b can take 60-120s)
const CHAT_TIMEOUT_MS = 120_000;

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
    public request_id?: string
  ) {
    super(`API ${status}: ${detail}`);
    this.name = "ApiError";
  }
}

export class NetworkError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "NetworkError";
  }
}

function withAbortTimeout(timeoutMs: number): { signal: AbortSignal; clear: () => void } {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  return { signal: controller.signal, clear: () => clearTimeout(timer) };
}

function classifyFetchError(e: unknown): never {
  if (e instanceof ApiError) throw e;
  if (e instanceof Error) {
    if (e.name === "AbortError") {
      throw new NetworkError(
        "The request timed out. The Coral backend may be busy — qwen3:8b inference can take up to 2 minutes."
      );
    }
    const msg = e.message.toLowerCase();
    if (msg.includes("failed to fetch") || msg.includes("networkerror") || msg.includes("network")) {
      throw new NetworkError(
        "Coral backend is not reachable. Make sure FastAPI is running on http://localhost:8000."
      );
    }
    if (msg.includes("econnreset") || msg.includes("socket hang up") || msg.includes("connection reset")) {
      throw new NetworkError(
        "The backend closed the connection while processing the request. Check FastAPI logs for errors."
      );
    }
  }
  throw new NetworkError(
    `Unexpected error: ${e instanceof Error ? e.message : String(e)}`
  );
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = response.statusText;
    let request_id: string | undefined;
    try {
      const body = await response.json();
      if (typeof body.detail === "object" && body.detail !== null) {
        detail = body.detail.detail || JSON.stringify(body.detail);
        request_id = body.detail.request_id;
      } else {
        detail = body.detail || JSON.stringify(body);
        request_id = body.request_id;
      }
    } catch {
      // ignore parse errors
    }
    throw new ApiError(response.status, detail, request_id);
  }
  return response.json() as Promise<T>;
}

export const api = {
  async get<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
    const url = new URL(`${BASE_URL}${path}`, typeof window !== "undefined" ? window.location.origin : "http://localhost:3001");
    if (params) {
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined) url.searchParams.set(k, String(v));
      });
    }
    const { signal, clear } = withAbortTimeout(DEFAULT_TIMEOUT_MS);
    try {
      const response = await fetch(url.toString(), { method: "GET", signal });
      clear();
      return handleResponse<T>(response);
    } catch (e) {
      clear();
      classifyFetchError(e);
    }
  },

  async post<T>(path: string, body: unknown, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
    const { signal, clear } = withAbortTimeout(timeoutMs);
    try {
      const response = await fetch(`${BASE_URL}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal,
      });
      clear();
      return handleResponse<T>(response);
    } catch (e) {
      clear();
      classifyFetchError(e);
    }
  },

  async postChat<T>(path: string, body: unknown): Promise<T> {
    return this.post<T>(path, body, CHAT_TIMEOUT_MS);
  },

  async upload<T>(path: string, file: File): Promise<T> {
    const form = new FormData();
    form.append("file", file);
    const { signal, clear } = withAbortTimeout(30_000);
    try {
      const response = await fetch(`${BASE_URL}${path}`, { method: "POST", body: form, signal });
      clear();
      return handleResponse<T>(response);
    } catch (e) {
      clear();
      classifyFetchError(e);
    }
  },

  async uploadForm<T>(path: string, form: FormData): Promise<T> {
    const { signal, clear } = withAbortTimeout(30_000);
    try {
      const response = await fetch(`${BASE_URL}${path}`, { method: "POST", body: form, signal });
      clear();
      return handleResponse<T>(response);
    } catch (e) {
      clear();
      classifyFetchError(e);
    }
  },

  async delete<T>(path: string): Promise<T> {
    const { signal, clear } = withAbortTimeout(DEFAULT_TIMEOUT_MS);
    try {
      const response = await fetch(`${BASE_URL}${path}`, { method: "DELETE", signal });
      clear();
      return handleResponse<T>(response);
    } catch (e) {
      clear();
      classifyFetchError(e);
    }
  },
};
