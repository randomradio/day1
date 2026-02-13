import { create } from 'zustand';
import type { Branch, DiffRow, Fact } from '../types/schema';
import { api } from '../api/client';

interface BranchStore {
  // State
  branches: Branch[];
  activeBranch: string;
  facts: Fact[];
  diffs: DiffRow[];
  loading: boolean;
  error: string | null;
  searchQuery: string;
  timeTravelTs: string;
  timeTravelResults: Fact[];

  // Actions
  setActiveBranch: (branch: string) => void;
  setSearchQuery: (query: string) => void;
  fetchBranches: () => Promise<void>;
  searchFacts: (query: string) => Promise<void>;
  fetchDiff: (source: string, target?: string) => Promise<void>;
  mergeBranch: (source: string, target: string, strategy: string, conflict?: string) => Promise<void>;
  timeTravel: (timestamp: string) => Promise<void>;
  clearError: () => void;
}

export const useBranchStore = create<BranchStore>((set, get) => ({
  branches: [],
  activeBranch: 'main',
  facts: [],
  diffs: [],
  loading: false,
  error: null,
  searchQuery: '',
  timeTravelTs: '',
  timeTravelResults: [],

  setActiveBranch: (branch) => set({ activeBranch: branch }),

  setSearchQuery: (query) => set({ searchQuery: query }),

  clearError: () => set({ error: null }),

  fetchBranches: async () => {
    set({ loading: true, error: null });
    try {
      const data = await api.listBranches();
      set({ branches: data.branches, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  searchFacts: async (query) => {
    set({ loading: true, error: null });
    try {
      const data = await api.searchFacts(query, get().activeBranch);
      set({ facts: data.results, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  fetchDiff: async (source, target = 'main') => {
    set({ loading: true, error: null });
    try {
      const data = await api.diffNative(source, target);
      set({ diffs: data.diffs, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  mergeBranch: async (source, target, strategy, conflict = 'skip') => {
    set({ loading: true, error: null });
    try {
      await api.mergeBranch(source, target, strategy, conflict);
      await get().fetchBranches();
      set({ loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  timeTravel: async (timestamp) => {
    set({ loading: true, error: null, timeTravelTs: timestamp });
    try {
      const data = await api.timeTravel(timestamp, get().activeBranch);
      set({ timeTravelResults: data.results, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },
}));
