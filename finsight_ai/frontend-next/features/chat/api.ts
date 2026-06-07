import { api } from "@/lib/api-client";
import type { ChatRequest, ChatResponse } from "@/types/index";

export const chatApi = {
  query: (request: ChatRequest): Promise<ChatResponse> =>
    api.post<ChatResponse>("/chat/query", request),
};
