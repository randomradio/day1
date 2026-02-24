import type {
  AnalyticsOverview,
  BranchListResponse,
  CherryPickRequest,
  CherryPickResult,
  Conversation,
  ConversationDiff,
  ConversationListResponse,
  CuratedBranchRequest,
  CuratedBranchResult,
  DiffResponse,
  Fact,
  MergeResult,
  Message,
  MessageListResponse,
  MessageSearchResult,
  ReplayListResponse,
  ReplayResult,
  ScoreEntry,
  ScoreSummary,
  SearchResult,
  SemanticDiff,
  Snapshot,
  TrendData,
} from '../types/schema';

const API = '/api/v1';

// Read API key from query param ?key= or localStorage
function getApiKey(): string | null {
  const params = new URLSearchParams(window.location.search);
  const key = params.get('key') || localStorage.getItem('day1_api_key');
  if (key) localStorage.setItem('day1_api_key', key);
  return key;
}

async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const apiKey = getApiKey();
  if (apiKey) headers.set('Authorization', `Bearer ${apiKey}`);

  const resp = await fetch(url, { ...init, headers });
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
    branch?: string;
    status?: string;
    limit?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.session_id) qs.set('session_id', params.session_id);
    if (params?.agent_id) qs.set('agent_id', params.agent_id);
    if (params?.task_id) qs.set('task_id', params.task_id);
    if (params?.branch) qs.set('branch', params.branch);
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

  cherryPickConversation: (id: string, data: CherryPickRequest) =>
    fetchJSON<CherryPickResult>(`${API}/conversations/${id}/cherry-pick`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),

  createCuratedBranch: (data: CuratedBranchRequest) =>
    fetchJSON<CuratedBranchResult>(`${API}/branches/curated`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
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

  // Semantic Diff
  semanticDiff: (a: string, b: string) =>
    fetchJSON<SemanticDiff>(`${API}/conversations/${a}/semantic-diff/${b}`),

  // Replays
  startReplay: (conversationId: string, data: {
    from_message_id: string;
    system_prompt?: string;
    model?: string;
    temperature?: number;
    max_tokens?: number;
    tool_filter?: string[];
    extra_context?: string;
    branch?: string;
    title?: string;
  }) =>
    fetchJSON<ReplayResult>(`${API}/conversations/${conversationId}/replay`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),

  getReplayContext: (replayId: string) =>
    fetchJSON<{ conversation_id: string; messages: Array<{ role: string; content: string }>; model?: string }>(
      `${API}/replays/${replayId}/context`
    ),

  replayDiff: (replayId: string) =>
    fetchJSON<ConversationDiff>(`${API}/replays/${replayId}/diff`),

  replaySemanticDiff: (replayId: string) =>
    fetchJSON<SemanticDiff>(`${API}/replays/${replayId}/semantic-diff`),

  completeReplay: (replayId: string) =>
    fetchJSON(`${API}/replays/${replayId}/complete`, { method: 'POST' }),

  listReplays: (conversationId?: string, limit = 20) => {
    const qs = new URLSearchParams();
    if (conversationId) qs.set('conversation_id', conversationId);
    qs.set('limit', String(limit));
    return fetchJSON<ReplayListResponse>(`${API}/replays?${qs}`);
  },

  // Analytics
  analyticsOverview: (branch?: string, days = 30) => {
    const qs = new URLSearchParams();
    if (branch) qs.set('branch', branch);
    qs.set('days', String(days));
    return fetchJSON<AnalyticsOverview>(`${API}/analytics/overview?${qs}`);
  },

  analyticsSession: (sessionId: string) =>
    fetchJSON<Record<string, unknown>>(`${API}/analytics/sessions/${sessionId}`),

  analyticsAgent: (agentId: string, days = 30) =>
    fetchJSON<Record<string, unknown>>(`${API}/analytics/agents/${agentId}?days=${days}`),

  analyticsTrends: (days = 30, granularity = 'day', branch?: string) => {
    const qs = new URLSearchParams({ days: String(days), granularity });
    if (branch) qs.set('branch', branch);
    return fetchJSON<TrendData>(`${API}/analytics/trends?${qs}`);
  },

  analyticsConversation: (conversationId: string) =>
    fetchJSON<Record<string, unknown>>(`${API}/analytics/conversations/${conversationId}`),

  // Scores
  evaluateConversation: (conversationId: string, dimensions?: string[]) =>
    fetchJSON<{ scores: ScoreEntry[] }>(`${API}/conversations/${conversationId}/evaluate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dimensions }),
    }),

  listScores: (params?: { target_type?: string; target_id?: string; dimension?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.target_type) qs.set('target_type', params.target_type);
    if (params?.target_id) qs.set('target_id', params.target_id);
    if (params?.dimension) qs.set('dimension', params.dimension);
    if (params?.limit) qs.set('limit', String(params.limit));
    return fetchJSON<{ scores: ScoreEntry[] }>(`${API}/scores?${qs}`);
  },

  scoreSummary: (targetType: string, targetId: string) =>
    fetchJSON<ScoreSummary>(`${API}/scores/summary/${targetType}/${targetId}`),
};
