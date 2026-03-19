/**
 * Global Zustand store — minimal global state only.
 */

import { create } from "zustand";
import type { ChatMessage } from "../types";

interface AppState {
  activePage: "home" | "chat";
  setActivePage: (page: AppState["activePage"]) => void;

  chatHistory: ChatMessage[];
  addChatMessage: (message: ChatMessage) => void;
  clearChat: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  activePage: "home",
  setActivePage: (page) => set({ activePage: page }),

  chatHistory: [],
  addChatMessage: (message) =>
    set((state) => ({ chatHistory: [...state.chatHistory, message] })),
  clearChat: () => set({ chatHistory: [] }),
}));
