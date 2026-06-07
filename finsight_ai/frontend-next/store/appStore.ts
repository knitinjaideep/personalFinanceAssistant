/**
 * Global Zustand store — minimal global state only.
 * Must be used only in "use client" components.
 */

import { create } from "zustand";
import type { ChatMessage } from "@/types/index";

export type Theme = "dark" | "light";

export interface IngestionJob {
  document_id: string;
  filename: string;
  status: "processing" | "parsed" | "failed";
  institution?: string;
  error?: string;
  started_at: number;
}

export type ActivePage =
  | "overview"
  | "banking"
  | "investments"
  | "documents"
  | "chat";

function applyTheme(theme: Theme) {
  if (typeof document === "undefined") return;
  document.documentElement.setAttribute("data-theme", theme);
  try { localStorage.setItem("coral-theme", theme); } catch {}
}

interface AppState {
  activePage: ActivePage;
  setActivePage: (page: ActivePage) => void;

  theme: Theme;
  initTheme: () => void;
  toggleTheme: () => void;

  chatHistory: ChatMessage[];
  addChatMessage: (message: ChatMessage) => void;
  clearChat: () => void;

  ingestionJobs: IngestionJob[];
  addIngestionJob: (job: IngestionJob) => void;
  updateIngestionJob: (document_id: string, updates: Partial<IngestionJob>) => void;
  clearFinishedJobs: () => void;

  uploadModalOpen: boolean;
  openUploadModal: () => void;
  closeUploadModal: () => void;
}

export const useAppStore = create<AppState>((set, get) => ({
  activePage: "overview",
  setActivePage: (page) => set({ activePage: page }),

  // Always start as "dark" on both server and client to avoid hydration mismatch.
  // initTheme() reads localStorage client-side and corrects the value after mount.
  theme: "dark",
  initTheme: () => {
    try {
      const stored = localStorage.getItem("coral-theme");
      if (stored === "light" || stored === "dark") {
        applyTheme(stored);
        set({ theme: stored });
        return;
      }
    } catch {}
    applyTheme("dark");
  },
  toggleTheme: () => {
    const next: Theme = get().theme === "dark" ? "light" : "dark";
    applyTheme(next);
    set({ theme: next });
  },

  uploadModalOpen: false,
  openUploadModal: () => set({ uploadModalOpen: true }),
  closeUploadModal: () => set({ uploadModalOpen: false }),

  chatHistory: [],
  addChatMessage: (message) =>
    set((state) => ({
      chatHistory: [
        ...state.chatHistory,
        { timestamp: new Date().toISOString(), ...message },
      ],
    })),
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
