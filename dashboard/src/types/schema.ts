export interface Branch {
  branch_name: string;
  parent_branch: string;
  status: string;
  description?: string;
  forked_at?: string;
}

export interface Fact {
  id: string;
  fact_text: string;
  category?: string;
  confidence: number;
  status: string;
  branch_name: string;
  session_id?: string;
  task_id?: string;
  agent_id?: string;
  score?: number;
  created_at?: string;
  metadata?: Record<string, unknown>;
}

export interface DiffRow {
  _table: string;
  [column: string]: unknown;
}

export interface Observation {
  id: string;
  type: string;
  observation_type: string;
  tool_name?: string;
  summary: string;
  session_id: string;
  created_at?: string;
}

export interface Snapshot {
  id: string;
  label?: string;
  branch_name: string;
  snapshot_data?: Record<string, unknown>;
  created_at?: string;
}

export interface SearchResult {
  results: Fact[];
  count: number;
}

export interface BranchListResponse {
  branches: Branch[];
}

export interface DiffResponse {
  diffs: DiffRow[];
  count: number;
}

export interface MergeResult {
  status?: string;
  merged_count?: number;
  rejected_count?: number;
  merge_id?: string;
  strategy?: string;
}

// === Conversation & Message History ===

export interface Conversation {
  id: string;
  session_id?: string;
  agent_id?: string;
  task_id?: string;
  branch_name: string;
  title?: string;
  parent_conversation_id?: string;
  fork_point_message_id?: string;
  status: string;
  message_count: number;
  total_tokens: number;
  model?: string;
  created_at?: string;
  updated_at?: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  session_id?: string;
  agent_id?: string;
  role: string;
  content?: string;
  thinking?: string;
  tool_calls?: Array<{ name: string; input?: string; output?: string }>;
  token_count: number;
  model?: string;
  sequence_num: number;
  branch_name: string;
  created_at?: string;
}

export interface MessageSearchResult {
  id: string;
  type: 'message';
  conversation_id: string;
  role: string;
  content: string;
  thinking?: string;
  tool_calls?: Array<{ name: string; input?: string; output?: string }>;
  session_id?: string;
  agent_id?: string;
  branch_name: string;
  sequence_num: number;
  score: number;
  created_at?: string;
}

export interface ConversationListResponse {
  conversations: Conversation[];
  count: number;
}

export interface MessageListResponse {
  messages: Message[];
  count: number;
}

export interface ConversationDiff {
  conversation_a: string;
  conversation_b: string;
  a_message_count: number;
  b_message_count: number;
  similarity: number;
  diff: Array<{
    op: string;
    a_messages?: Array<{ seq: number; role: string; content: string }>;
    b_messages?: Array<{ seq: number; role: string; content: string }>;
  }>;
}

// === Replay ===

export interface ReplayResult {
  replay_id: string;
  original_conversation_id: string;
  forked_conversation_id: string;
  fork_point_message_id: string;
  config: Record<string, unknown>;
  status: string;
  messages_copied: number;
  created_at?: string;
}

export interface ReplayListResponse {
  replays: Array<{
    replay_id: string;
    original_conversation_id?: string;
    status: string;
    message_count: number;
    total_tokens: number;
    model?: string;
    config: Record<string, unknown>;
    created_at?: string;
  }>;
  count: number;
}

// === Semantic Diff ===

export interface SemanticDiff {
  conversation_a: string;
  conversation_b: string;
  divergence_point: {
    shared_prefix_length: number;
    a_diverges_at_sequence?: number;
    b_diverges_at_sequence?: number;
    a_diverge_role?: string;
    b_diverge_role?: string;
    a_diverge_snippet?: string;
    b_diverge_snippet?: string;
    note?: string;
  };
  action_diff: {
    a_tool_count: number;
    b_tool_count: number;
    tools_only_in_a: string[];
    tools_only_in_b: string[];
    common_tools: string[];
    sequence_similarity: number;
    a_errors: number;
    b_errors: number;
    entries: Array<{
      op: string;
      tool?: string;
      a_tool?: string;
      b_tool?: string;
      a_sequence?: number;
      b_sequence?: number;
      a_args_snippet?: string;
      b_args_snippet?: string;
    }>;
  };
  reasoning_diff: {
    a_reasoning_steps: number;
    b_reasoning_steps: number;
    overall_similarity: number;
    pairs: Array<{
      position: number;
      a_sequence: number;
      b_sequence: number;
      similarity: number;
      a_snippet: string;
      b_snippet: string;
      diverged: boolean;
    }>;
  };
  outcome_diff: {
    a: { message_count: number; total_tokens: number; tool_call_count: number; error_count: number };
    b: { message_count: number; total_tokens: number; tool_call_count: number; error_count: number };
    delta: { messages: number; tokens: number; tool_calls: number; errors: number };
    efficiency: string;
  };
  summary: {
    verdict: string;
    description: string;
    action_match: number;
    reasoning_similarity: number;
    efficiency: string;
    shared_prefix: number;
    a_total_tokens: number;
    b_total_tokens: number;
  };
}

// === Analytics ===

export interface AnalyticsOverview {
  period_days: number;
  branch_name: string;
  counts: Record<string, number>;
  tokens: { total: number; avg_per_conversation: number };
  activity: { recent_conversations: Array<{ id: string; title?: string; status: string; message_count: number; created_at?: string }> };
  consolidation: { facts_created: number; facts_updated: number; facts_deduplicated: number; observations_processed: number; yield_rate: number };
}

export interface TrendData {
  period_days: number;
  granularity: string;
  branch_name: string;
  messages: Array<{ period: string; count: number }>;
  facts: Array<{ period: string; count: number }>;
  conversations: Array<{ period: string; count: number }>;
}

// === Scoring ===

export interface ScoreEntry {
  id: string;
  target_type: string;
  target_id: string;
  scorer: string;
  dimension: string;
  value: number;
  explanation?: string;
  created_at?: string;
}

export interface ScoreSummary {
  target_type: string;
  target_id: string;
  dimensions: Record<string, { avg: number; count: number; min: number; max: number }>;
}
