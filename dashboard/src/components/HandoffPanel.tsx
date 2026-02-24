import { useEffect, useState } from 'react';
import { useBranchStore } from '../stores/branchStore';
import { api } from '../api/client';
import type { HandoffRecord } from '../types/schema';

export default function HandoffPanel() {
  const { activeBranch, branches } = useBranchStore();
  const [handoffs, setHandoffs] = useState<HandoffRecord[]>([]);
  const [targetBranch, setTargetBranch] = useState('');
  const [handoffType, setHandoffType] = useState('task_continuation');
  const [includeUnverified, setIncludeUnverified] = useState(false);
  const [contextSummary, setContextSummary] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  useEffect(() => {
    loadHandoffs();
  }, [activeBranch]);

  const loadHandoffs = async () => {
    try {
      const data = await api.listHandoffs({ source_branch: activeBranch });
      setHandoffs(data.handoffs);
    } catch {
      setHandoffs([]);
    }
  };

  const handleCreate = async () => {
    if (!targetBranch) return;
    setLoading(true);
    try {
      const data = await api.createHandoff({
        source_branch: activeBranch,
        target_branch: targetBranch,
        handoff_type: handoffType,
        include_unverified: includeUnverified,
        context_summary: contextSummary || undefined,
      });
      setResult(
        `Handoff created: ${data.fact_count} facts, ${data.conversation_count} conversations`
      );
      setTargetBranch('');
      setContextSummary('');
      await loadHandoffs();
    } catch {
      setResult('Failed to create handoff');
    }
    setLoading(false);
  };

  return (
    <div className="space-y-4">
      {/* Create Handoff */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold mb-2">
          Create Handoff from: {activeBranch}
        </h3>
        <div className="space-y-2">
          <select
            className="w-full border rounded px-2 py-1 text-sm"
            value={targetBranch}
            onChange={(e) => setTargetBranch(e.target.value)}
          >
            <option value="">Select target branch...</option>
            {branches
              .filter((b) => b.branch_name !== activeBranch)
              .map((b) => (
                <option key={b.branch_name} value={b.branch_name}>
                  {b.branch_name}
                </option>
              ))}
          </select>
          <select
            className="w-full border rounded px-2 py-1 text-sm"
            value={handoffType}
            onChange={(e) => setHandoffType(e.target.value)}
          >
            <option value="task_continuation">Task Continuation</option>
            <option value="agent_switch">Agent Switch</option>
            <option value="session_handoff">Session Handoff</option>
            <option value="escalation">Escalation</option>
          </select>
          <textarea
            className="w-full border rounded px-2 py-1 text-sm"
            placeholder="Context summary (optional)"
            rows={2}
            value={contextSummary}
            onChange={(e) => setContextSummary(e.target.value)}
          />
          <label className="flex items-center gap-1 text-sm">
            <input
              type="checkbox"
              checked={includeUnverified}
              onChange={(e) => setIncludeUnverified(e.target.checked)}
            />
            Include unverified facts
          </label>
          <button
            className="bg-indigo-500 text-white px-3 py-1 rounded text-sm hover:bg-indigo-600 disabled:opacity-50"
            onClick={handleCreate}
            disabled={loading || !targetBranch}
          >
            Create Handoff
          </button>
          {result && (
            <div className="text-sm text-gray-600">{result}</div>
          )}
        </div>
      </div>

      {/* Handoff History */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold mb-2">Handoff History</h3>
        {handoffs.length > 0 ? (
          <ul className="text-sm space-y-2">
            {handoffs.map((h) => (
              <li key={h.id} className="border-b border-gray-100 pb-2">
                <div className="flex justify-between">
                  <span className="font-medium">
                    {h.source_branch} → {h.target_branch}
                  </span>
                  <span className={`text-xs px-2 py-0.5 rounded ${
                    h.verification_status === 'verified'
                      ? 'bg-green-100 text-green-700'
                      : 'bg-yellow-100 text-yellow-700'
                  }`}>
                    {h.verification_status}
                  </span>
                </div>
                <div className="text-xs text-gray-400 mt-0.5">
                  {h.handoff_type} · {h.fact_count} facts, {h.conversation_count} convs
                  {h.created_at && ` · ${new Date(h.created_at).toLocaleString()}`}
                </div>
                {h.context_summary && (
                  <div className="text-xs text-gray-500 mt-1 truncate">
                    {h.context_summary}
                  </div>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-sm text-gray-400">No handoffs from this branch</div>
        )}
      </div>
    </div>
  );
}
