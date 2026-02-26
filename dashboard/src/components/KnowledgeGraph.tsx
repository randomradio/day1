import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { useBranchStore } from '../stores/branchStore';
import type { KnowledgeGraphResponse } from '../types/schema';

export default function KnowledgeGraph() {
  const { activeBranch } = useBranchStore();
  const [data, setData] = useState<KnowledgeGraphResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    api.getKnowledgeGraph({ branch: activeBranch, limit: 120 })
      .then((resp) => {
        if (!cancelled) setData(resp);
      })
      .catch((e) => {
        if (!cancelled) setError((e as Error).message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [activeBranch]);

  return (
    <div className="bg-white rounded-lg p-4 border border-gray-200 shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-700">Knowledge Graph</h3>
        <span className="text-[11px] text-gray-400 font-mono">{activeBranch}</span>
      </div>

      {loading && <div className="text-xs text-gray-500">Loading graph…</div>}
      {error && <div className="text-xs text-red-600">{error}</div>}

      {!loading && !error && data && (
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-2 text-xs">
            <div className="rounded border border-gray-200 p-2 bg-gray-50">
              <div className="text-gray-500">nodes</div>
              <div className="text-gray-900 font-semibold">{data.nodes.length}</div>
            </div>
            <div className="rounded border border-gray-200 p-2 bg-gray-50">
              <div className="text-gray-500">edges</div>
              <div className="text-gray-900 font-semibold">{data.edges.length}</div>
            </div>
            <div className="rounded border border-gray-200 p-2 bg-gray-50">
              <div className="text-gray-500">mode</div>
              <div className="text-gray-900 font-semibold">{data.mode}</div>
            </div>
          </div>

          <div className="rounded-lg border border-dashed border-gray-300 bg-gradient-to-br from-gray-50 to-white p-3">
            <div className="text-xs text-gray-600 mb-2">
              React Flow integration point (placeholder): currently rendering a compact edge list.
            </div>
            <div className="max-h-48 overflow-y-auto space-y-1">
              {data.edges.slice(0, 20).map((edge) => (
                <div key={edge.id} className="text-xs text-gray-700 flex items-center gap-2">
                  <span className="font-medium">{edge.source}</span>
                  <span className="text-gray-400">[{edge.label}]</span>
                  <span className="font-medium">{edge.target}</span>
                </div>
              ))}
              {data.edges.length === 0 && (
                <div className="text-xs text-gray-500">No graph edges yet.</div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

