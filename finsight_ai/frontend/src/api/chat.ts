import { api } from "./client";
import type { ChatRequest, ChatResponse } from "../types";

export const chatApi = {
  query: (request: ChatRequest): Promise<ChatResponse> =>
    api.post<ChatResponse>("/chat/query", request),
};
