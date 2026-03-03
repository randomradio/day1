import { create } from 'zustand';
import type { Memory, Branch, Snapshot } from '../types/schema';
import * as api from '../api/client';

interface Store {
  // State
  branches: Branch[];
  activeBranch: string;
  memories: Memory[];
  snapshots: Snapshot[];
  count: number;
  searchQuery: string;
  loading: boolean;
  error: string | null;

  // Actions
  fetchBranches: () => Promise<void>;
  fetchTimeline: () => Promise<void>;
  fetchCount: () => Promise<void>;
  fetchSnapshots: () => Promise<void>;
  search: (query: string, category?: string) => Promise<void>;
  setActiveBranch: (branch: string) => Promise<void>;
  createBranch: (name: string, description?: string) => Promise<void>;
  mergeBranch: (source: string, target?: string) => Promise<void>;
  createSnapshot: (label?: string) => Promise<void>;
  writeMemory: (text: string, context?: string, category?: string) => Promise<void>;
  clearSearch: () => void;
  setError: (error: string | null) => void;
}

export const useStore = create<Store>((set, get) => ({
  branches: [],
  activeBranch: 'main',
  memories: [],
  snapshots: [],
  count: 0,
  searchQuery: '',
  loading: false,
  error: null,

  fetchBranches: async () => {
    try {
      const { branches } = await api.listBranches();
      set({ branches });
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  fetchTimeline: async () => {
    set({ loading: true, error: null });
    try {
      const { timeline } = await api.getTimeline(get().activeBranch);
      set({ memories: timeline, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  fetchCount: async () => {
    try {
      const { count } = await api.getCount(get().activeBranch);
      set({ count });
    } catch {
      // silent
    }
  },

  fetchSnapshots: async () => {
    try {
      const { snapshots } = await api.listSnapshots(get().activeBranch);
      set({ snapshots });
    } catch {
      // silent
    }
  },

  search: async (query, category) => {
    set({ loading: true, error: null, searchQuery: query });
    try {
      const { results } = await api.searchMemories(query, get().activeBranch, 20, category);
      set({ memories: results, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  setActiveBranch: async (branch) => {
    set({ activeBranch: branch });
    const { fetchTimeline, fetchCount, fetchSnapshots } = get();
    await Promise.all([fetchTimeline(), fetchCount(), fetchSnapshots()]);
  },

  createBranch: async (name, description) => {
    try {
      await api.createBranch(name, get().activeBranch, description);
      await get().fetchBranches();
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  mergeBranch: async (source, target) => {
    try {
      await api.mergeBranch(source, target || 'main');
      await Promise.all([get().fetchBranches(), get().fetchTimeline()]);
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  createSnapshot: async (label) => {
    try {
      await api.createSnapshot(get().activeBranch, label);
      await get().fetchSnapshots();
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  writeMemory: async (text, context, category) => {
    try {
      await api.writeMemory(text, context, get().activeBranch, category);
      await Promise.all([get().fetchTimeline(), get().fetchCount()]);
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  clearSearch: () => {
    set({ searchQuery: '' });
    get().fetchTimeline();
  },

  setError: (error) => set({ error }),
}));
