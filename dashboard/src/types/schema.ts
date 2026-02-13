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
