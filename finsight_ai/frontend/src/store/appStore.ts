/**
 * Global Zustand store — minimal global state only.
 */

import { create } from "zustand";
import type { ChatMessage } from "../types";

export interface IngestionJob {
  document_id: string;
  filename: string;
  status: "processing" | "parsed" | "failed";
  institution?: string;
  error?: string;
  started_at: number;
}

interface AppState {
  // Kept for backward compat with Sidebar component
  activePage: "home" | "chat";
  setActivePage: (page: "home" | "chat") => void;

  chatHistory: ChatMessage[];
  addChatMessage: (message: ChatMessage) => void;
  clearChat: () => void;

  ingestionJobs: IngestionJob[];
  addIngestionJob: (job: IngestionJob) => void;
  updateIngestionJob: (document_id: string, updates: Partial<IngestionJob>) => void;
  clearFinishedJobs: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  activePage: "chat",
  setActivePage: (page) => set({ activePage: page }),

  chatHistory: [],
  addChatMessage: (message) =>
    set((state) => ({ chatHistory: [...state.chatHistory, message] })),
  clearChat: () => set({ chatHistory: [] }),

  ingestionJobs: [],
  addIngestionJob: (job) =>
    set((state) => ({ ingestionJobs: [...state.ingestionJobs, job] })),
  updateIngestionJob: (document_id, updates) =>
    set((state) => ({
      ingestionJobs: state.ingestionJobs.map((j) =>
        j.document_id === document_id ? { ...j, ...updates } : j
      ),
    })),
  clearFinishedJobs: () =>
    set((state) => ({
      ingestionJobs: state.ingestionJobs.filter((j) => j.status === "processing"),
    })),
}));
