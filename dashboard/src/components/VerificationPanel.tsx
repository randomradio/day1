import { useEffect, useState } from 'react';
import { useBranchStore } from '../stores/branchStore';
import { api } from '../api/client';
import type { VerificationSummary, MergeGateResult } from '../types/schema';

export default function VerificationPanel() {
  const { activeBranch } = useBranchStore();
  const [summary, setSummary] = useState<VerificationSummary | null>(null);
  const [mergeGate, setMergeGate] = useState<MergeGateResult | null>(null);
  const [batchResult, setBatchResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadSummary();
  }, [activeBranch]);

  const loadSummary = async () => {
    try {
      const data = await api.getVerificationSummary(activeBranch);
      setSummary(data);
    } catch {
      setSummary(null);
    }
  };

  const handleBatchVerify = async () => {
    setLoading(true);
    try {
      const result = await api.batchVerify(activeBranch);
      setBatchResult(
        `Processed ${result.total_processed}: ${result.verified} verified, ${result.invalidated} invalidated, ${result.unverified} unverified`
      );
      await loadSummary();
    } catch {
      setBatchResult('Failed to batch verify');
    }
    setLoading(false);
  };

  const handleCheckMergeGate = async () => {
    try {
      const result = await api.checkMergeGate(activeBranch);
      setMergeGate(result);
    } catch {
      setMergeGate(null);
    }
  };

  return (
    <div className="space-y-4">
      {/* Verification Summary */}
      {summary && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-2">
            Verification: {summary.branch_name}
          </h3>
          <div className="grid grid-cols-4 gap-2 text-sm mb-3">
            <div className="bg-blue-50 rounded p-2 text-center">
              <div className="text-lg font-bold text-blue-600">{summary.total_facts}</div>
              <div className="text-xs text-gray-500">Total</div>
            </div>
            <div className="bg-green-50 rounded p-2 text-center">
              <div className="text-lg font-bold text-green-600">{summary.by_status.verified || 0}</div>
              <div className="text-xs text-gray-500">Verified</div>
            </div>
            <div className="bg-yellow-50 rounded p-2 text-center">
              <div className="text-lg font-bold text-yellow-600">{summary.by_status.unverified || 0}</div>
              <div className="text-xs text-gray-500">Unverified</div>
            </div>
            <div className="bg-red-50 rounded p-2 text-center">
              <div className="text-lg font-bold text-red-600">{summary.by_status.invalidated || 0}</div>
              <div className="text-xs text-gray-500">Invalidated</div>
            </div>
          </div>
          {summary.total_facts > 0 && (
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div
                className="bg-green-500 h-2 rounded-full"
                style={{ width: `${summary.verification_rate * 100}%` }}
              />
            </div>
          )}
          <div className="text-xs text-gray-400 mt-1">
            {(summary.verification_rate * 100).toFixed(0)}% verified
          </div>
        </div>
      )}

      {/* Batch Verify */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold mb-2">Batch Verify</h3>
        <button
          className="bg-blue-500 text-white px-3 py-1 rounded text-sm hover:bg-blue-600 disabled:opacity-50"
          onClick={handleBatchVerify}
          disabled={loading}
        >
          {loading ? 'Verifying...' : `Verify All on ${activeBranch}`}
        </button>
        {batchResult && (
          <div className="mt-2 text-sm text-gray-600">{batchResult}</div>
        )}
      </div>

      {/* Merge Gate */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold mb-2">Merge Gate</h3>
        <button
          className="bg-gray-500 text-white px-3 py-1 rounded text-sm hover:bg-gray-600 mb-2"
          onClick={handleCheckMergeGate}
        >
          Check Merge Gate
        </button>
        {mergeGate && (
          <div className="mt-2">
            <div className={`text-sm font-semibold ${mergeGate.can_merge ? 'text-green-600' : 'text-red-600'}`}>
              {mergeGate.can_merge ? 'PASS — Ready to merge' : 'FAIL — Not ready'}
            </div>
            <div className="text-xs text-gray-500 mt-1">
              {mergeGate.verified} verified, {mergeGate.unverified} unverified, {mergeGate.invalidated} invalidated
            </div>
            {mergeGate.unverified_facts.length > 0 && (
              <ul className="mt-2 text-xs space-y-1">
                {mergeGate.unverified_facts.map((f) => (
                  <li key={f.id} className="text-yellow-600">
                    {f.fact_text} <span className="text-gray-400">({f.category})</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      {/* Per-category breakdown */}
      {summary && Object.keys(summary.by_category).length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-2">By Category</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-gray-500">
                <th className="pb-1">Category</th>
                <th className="pb-1 text-center">Verified</th>
                <th className="pb-1 text-center">Unverified</th>
                <th className="pb-1 text-center">Invalid</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(summary.by_category).map(([cat, counts]) => (
                <tr key={cat} className="border-t border-gray-100">
                  <td className="py-1">{cat}</td>
                  <td className="py-1 text-center text-green-600">{counts.verified || 0}</td>
                  <td className="py-1 text-center text-yellow-600">{counts.unverified || 0}</td>
                  <td className="py-1 text-center text-red-600">{counts.invalidated || 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
