/**
 * Global Zustand store.
 *
 * Keeps only truly global state here:
 * - Active page/navigation
 * - Chat conversation history (persists across page switches)
 * - Upload queue status
 *
 * Per-page data fetching is handled by custom hooks with local state.
 */

import { create } from "zustand";
import type { Bucket, ChatMessage, StatementDocument } from "../types";

interface AppState {
  // Navigation — simplified to 2 tabs
  activePage: "home" | "chat";
  setActivePage: (page: AppState["activePage"]) => void;

  // Selected bucket context — shared between Home and Chat
  selectedBucket: "investments" | "banking";
  setSelectedBucket: (bucket: AppState["selectedBucket"]) => void;

  // Chat history persists across navigation
  chatHistory: ChatMessage[];
  addChatMessage: (message: ChatMessage) => void;
  clearChat: () => void;

  // Recently uploaded docs (for status polling)
  recentUploads: StatementDocument[];
  addRecentUpload: (doc: StatementDocument) => void;
  updateUploadStatus: (id: string, status: string) => void;
  removeFromUploads: (id: string) => void;

  // Buckets — cached list shared across upload + chat screens
  buckets: Bucket[];
  setBuckets: (buckets: Bucket[]) => void;
  addBucket: (bucket: Bucket) => void;
  removeBucket: (id: string) => void;
  updateBucketCount: (id: string, delta: number) => void;
}

export const useAppStore = create<AppState>((set) => ({
  activePage: "home",
  setActivePage: (page) => set({ activePage: page }),

  selectedBucket: "investments",
  setSelectedBucket: (bucket) => set({ selectedBucket: bucket }),

  chatHistory: [],
  addChatMessage: (message) =>
    set((state) => ({ chatHistory: [...state.chatHistory, message] })),
  clearChat: () => set({ chatHistory: [] }),

  recentUploads: [],
  addRecentUpload: (doc) =>
    set((state) => ({
      recentUploads: [doc, ...state.recentUploads.slice(0, 19)],
    })),
  updateUploadStatus: (id, status) =>
    set((state) => ({
      recentUploads: state.recentUploads.map((doc) =>
        doc.id === id ? { ...doc, document_status: status as any } : doc
      ),
    })),
  removeFromUploads: (id) =>
    set((state) => ({
      recentUploads: state.recentUploads.filter((doc) => doc.id !== id),
    })),

  buckets: [],
  setBuckets: (buckets) => set({ buckets }),
  addBucket: (bucket) =>
    set((state) => ({ buckets: [...state.buckets, bucket] })),
  removeBucket: (id) =>
    set((state) => ({ buckets: state.buckets.filter((b) => b.id !== id) })),
  updateBucketCount: (id, delta) =>
    set((state) => ({
      buckets: state.buckets.map((b) =>
        b.id === id
          ? { ...b, document_count: Math.max(0, b.document_count + delta) }
          : b
      ),
    })),
}));
