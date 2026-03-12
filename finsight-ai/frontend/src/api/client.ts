/**
 * Base API client — thin wrapper over fetch with error handling.
 *
 * All API modules import from here rather than calling fetch directly,
 * keeping retry/error logic in one place.
 */

const BASE_URL = "/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string
  ) {
    super(`API ${status}: ${detail}`);
    this.name = "ApiError";
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      // ignore parse errors
    }
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<T>;
}

export const api = {
  async get<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
    const url = new URL(`${BASE_URL}${path}`, window.location.origin);
    if (params) {
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined) url.searchParams.set(k, String(v));
      });
    }
    const response = await fetch(url.toString(), { method: "GET" });
    return handleResponse<T>(response);
  },

  async post<T>(path: string, body: unknown): Promise<T> {
    const response = await fetch(`${BASE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return handleResponse<T>(response);
  },

  async upload<T>(path: string, file: File): Promise<T> {
    const form = new FormData();
    form.append("file", file);
    const response = await fetch(`${BASE_URL}${path}`, {
      method: "POST",
      body: form,
    });
    return handleResponse<T>(response);
  },

  async delete<T>(path: string): Promise<T> {
    const response = await fetch(`${BASE_URL}${path}`, { method: "DELETE" });
    return handleResponse<T>(response);
  },

  /** POST that returns a streaming Response for SSE. */
  stream(path: string, body: unknown): Promise<Response> {
    return fetch(`${BASE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(body),
    });
  },

  /** Open an SSE GET stream via EventSource. */
  eventSource(path: string, params: Record<string, string>): EventSource {
    const url = new URL(`${BASE_URL}${path}`, window.location.origin);
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
    return new EventSource(url.toString());
  },
};
