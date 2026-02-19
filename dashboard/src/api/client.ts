import type {
  BranchListResponse,
  Conversation,
  ConversationDiff,
  ConversationListResponse,
  DiffResponse,
  Fact,
  MergeResult,
  Message,
  MessageListResponse,
  MessageSearchResult,
  SearchResult,
  Snapshot,
} from '../types/schema';

const API = '/api/v1';

async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, init);
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`${resp.status}: ${body}`);
  }
  return resp.json();
}

export const api = {
  // Branches
  listBranches: () =>
    fetchJSON<BranchListResponse>(`${API}/branches`),

  createBranch: (name: string, parent = 'main', description?: string) =>
    fetchJSON(`${API}/branches`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        branch_name: name,
        parent_branch: parent,
        description,
      }),
    }),

  archiveBranch: (name: string) =>
    fetchJSON(`${API}/branches/${name}`, { method: 'DELETE' }),

  // Diff
  diffNative: (source: string, target = 'main') =>
    fetchJSON<DiffResponse>(
      `${API}/branches/${source}/diff/native?target_branch=${target}`
    ),

  diffNativeCount: (source: string, target = 'main') =>
    fetchJSON<{ counts: Record<string, number> }>(
      `${API}/branches/${source}/diff/native/count?target_branch=${target}`
    ),

  // Merge
  mergeBranch: (
    source: string,
    target: string,
    strategy: string,
    conflict = 'skip'
  ) =>
    fetchJSON<MergeResult>(`${API}/branches/${source}/merge`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        target_branch: target,
        strategy,
        conflict,
      }),
    }),

  // Facts / Search
  searchFacts: (query: string, branch = 'main', searchType = 'hybrid') =>
    fetchJSON<SearchResult>(
      `${API}/facts/search?query=${encodeURIComponent(query)}&branch=${branch}&search_type=${searchType}`
    ),

  getFact: (id: string) => fetchJSON<Fact>(`${API}/facts/${id}`),

  // Observations
  searchObservations: (query: string, branch = 'main') =>
    fetchJSON<{ results: unknown[]; count: number }>(
      `${API}/observations/search?query=${encodeURIComponent(query)}&branch=${branch}`
    ),

  // Snapshots
  listSnapshots: (branch?: string) =>
    fetchJSON<{ snapshots: Snapshot[] }>(
      `${API}/snapshots${branch ? `?branch=${branch}` : ''}`
    ),

  createSnapshot: (label?: string, branch = 'main', native = false) =>
    fetchJSON(`${API}/snapshots`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ label, branch, native }),
    }),

  // Time travel
  timeTravel: (timestamp: string, branch = 'main', category?: string) =>
    fetchJSON<{ timestamp: string; results: Fact[] }>(
      `${API}/time-travel?timestamp=${encodeURIComponent(timestamp)}&branch=${branch}${category ? `&category=${category}` : ''}`
    ),

  // Conversations
  listConversations: (params?: {
    session_id?: string;
    agent_id?: string;
    task_id?: string;
    status?: string;
    limit?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.session_id) qs.set('session_id', params.session_id);
    if (params?.agent_id) qs.set('agent_id', params.agent_id);
    if (params?.task_id) qs.set('task_id', params.task_id);
    if (params?.status) qs.set('status', params.status);
    if (params?.limit) qs.set('limit', String(params.limit));
    const q = qs.toString();
    return fetchJSON<ConversationListResponse>(
      `${API}/conversations${q ? `?${q}` : ''}`
    );
  },

  getConversation: (id: string) =>
    fetchJSON<Conversation>(`${API}/conversations/${id}`),

  createConversation: (data: {
    session_id?: string;
    title?: string;
    branch?: string;
  }) =>
    fetchJSON<Conversation>(`${API}/conversations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),

  forkConversation: (id: string, messageId: string, title?: string, branch?: string) =>
    fetchJSON<Conversation>(`${API}/conversations/${id}/fork`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message_id: messageId, title, branch }),
    }),

  diffConversations: (a: string, b: string) =>
    fetchJSON<ConversationDiff>(`${API}/conversations/${a}/diff/${b}`),

  // Messages
  listMessages: (conversationId: string, limit = 100, offset = 0) =>
    fetchJSON<MessageListResponse>(
      `${API}/conversations/${conversationId}/messages?limit=${limit}&offset=${offset}`
    ),

  addMessage: (conversationId: string, data: {
    role: string;
    content?: string;
    thinking?: string;
    tool_calls?: Array<{ name: string; input?: string; output?: string }>;
    session_id?: string;
    branch?: string;
  }) =>
    fetchJSON<Message>(`${API}/conversations/${conversationId}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...data, conversation_id: conversationId }),
    }),

  searchMessages: (query: string, branch = 'main', conversationId?: string) =>
    fetchJSON<{ results: MessageSearchResult[]; count: number }>(
      `${API}/messages/search?query=${encodeURIComponent(query)}&branch=${branch}${conversationId ? `&conversation_id=${conversationId}` : ''}`
    ),
};
