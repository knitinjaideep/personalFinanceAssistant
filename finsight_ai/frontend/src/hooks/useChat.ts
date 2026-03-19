/**
 * Chat hook — manages chat state and API calls.
 */

import { useState, useCallback } from "react";
import { chatApi } from "../api/chat";
import type { ChatMessage, EmbeddingSource } from "../types";
import { useAppStore } from "../store/appStore";

export function useChat() {
  const { chatHistory, addChatMessage, clearChat } = useAppStore();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastSources, setLastSources] = useState<EmbeddingSource[]>([]);

  const sendMessage = useCallback(
    async (question: string) => {
      if (!question.trim()) return;

      const userMessage: ChatMessage = {
        role: "user",
        content: question,
        timestamp: new Date().toISOString(),
      };
      addChatMessage(userMessage);
      setIsLoading(true);
      setError(null);

      try {
        const response = await chatApi.query({
          question,
          conversation_history: chatHistory,
        });

        const assistantMessage: ChatMessage = {
          role: "assistant",
          content: response.answer,
          timestamp: new Date().toISOString(),
        };
        addChatMessage(assistantMessage);
        setLastSources(response.sources);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Failed to get response";
        setError(msg);
        addChatMessage({
          role: "assistant",
          content: `Error: ${msg}`,
          timestamp: new Date().toISOString(),
        });
      } finally {
        setIsLoading(false);
      }
    },
    [chatHistory, addChatMessage]
  );

  return { chatHistory, sendMessage, isLoading, error, lastSources, clearChat };
}
