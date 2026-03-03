import type { Memory, Branch, Snapshot } from '../types/schema';

const BASE = '/api/v1';

async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

async function callTool<T = unknown>(name: string, args: Record<string, unknown> = {}): Promise<T> {
  const body = { tool: name, arguments: args };
  const res = await fetchJSON<{ result: T }>(`${BASE}/ingest/mcp`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
  return res.result;
}

export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch('/health');
    return res.ok;
  } catch {
    return false;
  }
}

export async function getTimeline(
  branch = 'main',
  limit = 50,
  category?: string,
  source_type?: string,
): Promise<{ timeline: Memory[]; count: number }> {
  const params = new URLSearchParams({ branch, limit: String(limit) });
  if (category) params.set('category', category);
  if (source_type) params.set('source_type', source_type);
  return fetchJSON(`${BASE}/memories/timeline?${params}`);
}

export async function getCount(branch = 'main'): Promise<{ branch: string; count: number }> {
  return fetchJSON(`${BASE}/memories/count?branch=${encodeURIComponent(branch)}`);
}

export async function searchMemories(
  query: string,
  branch = 'main',
  limit = 20,
  category?: string,
): Promise<{ results: Memory[]; count: number }> {
  const args: Record<string, unknown> = { query, branch, limit };
  if (category) args.category = category;
  return callTool('memory_search', args);
}

export async function writeMemory(
  text: string,
  context?: string,
  branch = 'main',
  category?: string,
  confidence = 0.7,
  source_type?: string,
): Promise<{ id: string; created_at: string }> {
  const args: Record<string, unknown> = { text, branch, confidence };
  if (context) args.context = context;
  if (category) args.category = category;
  if (source_type) args.source_type = source_type;
  return callTool('memory_write', args);
}

export async function listBranches(): Promise<{ branches: Branch[] }> {
  return callTool('memory_branch_list', {});
}

export async function createBranch(
  branch_name: string,
  parent = 'main',
  description?: string,
): Promise<Branch> {
  const args: Record<string, unknown> = { branch_name, parent };
  if (description) args.description = description;
  return callTool('memory_branch_create', args);
}

export async function mergeBranch(
  source_branch: string,
  target_branch = 'main',
): Promise<{ source_branch: string; target_branch: string; merged: number; skipped_duplicates: number }> {
  return callTool('memory_merge', { source_branch, target_branch });
}

export async function listSnapshots(
  branch?: string,
): Promise<{ snapshots: Snapshot[] }> {
  const args: Record<string, unknown> = {};
  if (branch) args.branch = branch;
  return callTool('memory_snapshot_list', args);
}

export async function createSnapshot(
  branch = 'main',
  label?: string,
): Promise<{ snapshot_id: string; label: string; created_at: string }> {
  const args: Record<string, unknown> = { branch };
  if (label) args.label = label;
  return callTool('memory_snapshot', args);
}
