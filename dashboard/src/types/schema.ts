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
