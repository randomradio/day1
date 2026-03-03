export interface Memory {
  id: string;
  text: string;
  context: string | null;
  file_context: string | null;
  session_id: string | null;
  branch_name: string;
  category: string | null;
  confidence: number;
  source_type: string | null;
  status: string;
  score: number | null;
  created_at: string;
}

export interface Branch {
  branch_name: string;
  parent_branch: string | null;
  status: string;
  description: string | null;
  created_at: string;
}

export interface Snapshot {
  id: string;
  label: string | null;
  branch_name: string;
  created_at: string;
}
