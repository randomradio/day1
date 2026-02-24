import { create } from 'zustand';
import type {
  AnalyticsOverview,
  Conversation,
  Message,
  ScoreEntry,
  ScoreSummary,
  SemanticDiff,
  TrendData,
} from '../types/schema';
import { api } from '../api/client';

type Tab = 'memory' | 'conversations' | 'analytics';

// Sync URL hash with tab state
const updateHash = (tab: Tab) => {
  if (window.location.hash !== `#${tab}`) {
    window.location.hash = tab;
  }
};

const getTabFromHash = (): Tab => {
  const hash = window.location.hash.slice(1);
  if (hash === 'memory' || hash === 'conversations' || hash === 'analytics') {
    return hash;
  }
  return 'memory';
};

// Listen for hash changes (browser back/forward buttons)
if (typeof window !== 'undefined') {
  window.addEventListener('hashchange', () => {
    const tab = getTabFromHash();
    useConversationStore.getState().setTab(tab, false);
  });
}

interface ConversationStore {
  // State
  tab: Tab;
  conversations: Conversation[];
  selectedConversation: Conversation | null;
  messages: Message[];
  selectedMessage: Message | null;
  replays: Array<{ replay_id: string; original_conversation_id?: string; status: string; message_count: number; created_at?: string }>;
  semanticDiff: SemanticDiff | null;
  scores: ScoreEntry[];
  scoreSummary: ScoreSummary | null;
  analytics: AnalyticsOverview | null;
  trends: TrendData | null;
  loading: boolean;
  error: string | null;

  // Actions
  setTab: (tab: Tab, updateUrl?: boolean) => void;
  setSelectedMessage: (message: Message | null) => void;
  fetchConversations: (params?: { session_id?: string; status?: string; limit?: number }) => Promise<void>;
  selectConversation: (id: string) => Promise<void>;
  fetchMessages: (conversationId: string) => Promise<void>;
  fetchReplays: (conversationId?: string) => Promise<void>;
  fetchSemanticDiff: (a: string, b: string) => Promise<void>;
  evaluateConversation: (conversationId: string) => Promise<void>;
  fetchScoreSummary: (conversationId: string) => Promise<void>;
  fetchAnalytics: (branch?: string, days?: number) => Promise<void>;
  fetchTrends: (days?: number, granularity?: string, branch?: string) => Promise<void>;
  clearError: () => void;
}

export const useConversationStore = create<ConversationStore>((set, get) => ({
  tab: getTabFromHash(), // Initialize from URL hash
  conversations: [],
  selectedConversation: null,
  messages: [],
  selectedMessage: null,
  replays: [],
  semanticDiff: null,
  scores: [],
  scoreSummary: null,
  analytics: null,
  trends: null,
  loading: false,
  error: null,

  setTab: (tab, updateUrl = true) => {
    set({ tab });
    if (updateUrl) {
      updateHash(tab);
    }
  },

  setSelectedMessage: (message) => set({ selectedMessage: message }),

  clearError: () => set({ error: null }),

  fetchConversations: async (params) => {
    set({ loading: true, error: null });
    try {
      const data = await api.listConversations(params);
      set({ conversations: data.conversations, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  selectConversation: async (id) => {
    set({ loading: true, error: null });
    try {
      const conv = await api.getConversation(id);
      set({ selectedConversation: conv });
      await get().fetchMessages(id);
      set({ loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  fetchMessages: async (conversationId) => {
    try {
      const data = await api.listMessages(conversationId);
      set({ messages: data.messages });
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  fetchReplays: async (conversationId) => {
    set({ loading: true, error: null });
    try {
      const data = await api.listReplays(conversationId);
      set({ replays: data.replays, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  fetchSemanticDiff: async (a, b) => {
    set({ loading: true, error: null, semanticDiff: null });
    try {
      const diff = await api.semanticDiff(a, b);
      set({ semanticDiff: diff, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  evaluateConversation: async (conversationId) => {
    set({ loading: true, error: null });
    try {
      const data = await api.evaluateConversation(conversationId);
      set({ scores: data.scores, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  fetchScoreSummary: async (conversationId) => {
    try {
      const summary = await api.scoreSummary('conversation', conversationId);
      set({ scoreSummary: summary });
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  fetchAnalytics: async (branch, days = 30) => {
    set({ loading: true, error: null });
    try {
      const data = await api.analyticsOverview(branch, days);
      set({ analytics: data, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  fetchTrends: async (days = 30, granularity = 'day', branch) => {
    set({ loading: true, error: null });
    try {
      const data = await api.analyticsTrends(days, granularity, branch);
      set({ trends: data, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },
}));
