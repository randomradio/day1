import type {
  BranchListResponse,
  DiffResponse,
  Fact,
  MergeResult,
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
};
