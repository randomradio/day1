import { useEffect, useState } from 'react';
import { useBranchStore } from '../stores/branchStore';

export default function MergePanel() {
  const { branches, activeBranch, diffs, fetchDiff, mergeBranch, loading } =
    useBranchStore();
  const [target, setTarget] = useState('main');
  const [strategy, setStrategy] = useState('native');
  const [conflict, setConflict] = useState('skip');

  const canDiff = activeBranch !== 'main' && activeBranch !== target;

  useEffect(() => {
    if (canDiff) {
      fetchDiff(activeBranch, target);
    }
  }, [activeBranch, target, canDiff, fetchDiff]);

  const handleMerge = async () => {
    await mergeBranch(activeBranch, target, strategy, conflict);
  };

  if (!canDiff) {
    return (
      <div className="bg-gray-800 rounded-lg p-4 text-gray-500 text-sm">
        Select a non-main branch to see diff/merge options.
      </div>
    );
  }

  return (
    <div className="bg-gray-800 rounded-lg p-4">
      <h3 className="text-sm font-semibold text-gray-200 mb-3">
        Merge: {activeBranch} → {target}
      </h3>

      {/* Diff summary */}
      <div className="mb-3">
        <span className="text-xs text-gray-400">
          {diffs.length} changes detected
        </span>
        {diffs.length > 0 && (
          <div className="mt-2 max-h-48 overflow-y-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-500 border-b border-gray-700">
                  <th className="text-left py-1 px-2">Table</th>
                  <th className="text-left py-1 px-2">ID</th>
                  <th className="text-left py-1 px-2">Flag</th>
                </tr>
              </thead>
              <tbody>
                {diffs.slice(0, 50).map((d, i) => (
                  <tr key={i} className="border-b border-gray-700/50">
                    <td className="py-1 px-2 text-gray-400">{d._table}</td>
                    <td className="py-1 px-2 text-gray-300 font-mono">
                      {String(d.id || '').slice(0, 8)}
                    </td>
                    <td className="py-1 px-2">
                      <span
                        className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                          String(d.__mo_diff_flag || '').includes('INSERT')
                            ? 'bg-green-900 text-green-300'
                            : String(d.__mo_diff_flag || '').includes('DELETE')
                            ? 'bg-red-900 text-red-300'
                            : 'bg-yellow-900 text-yellow-300'
                        }`}
                      >
                        {String(d.__mo_diff_flag || 'CHANGE')}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Merge controls */}
      <div className="flex items-center gap-2 mb-3">
        <label className="text-xs text-gray-400">Target:</label>
        <select
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          className="bg-gray-700 text-gray-200 text-xs px-2 py-1 rounded border border-gray-600"
        >
          {branches
            .filter((b) => b.branch_name !== activeBranch)
            .map((b) => (
              <option key={b.branch_name} value={b.branch_name}>
                {b.branch_name}
              </option>
            ))}
        </select>

        <label className="text-xs text-gray-400">Strategy:</label>
        <select
          value={strategy}
          onChange={(e) => setStrategy(e.target.value)}
          className="bg-gray-700 text-gray-200 text-xs px-2 py-1 rounded border border-gray-600"
        >
          <option value="native">Native (MO)</option>
          <option value="auto">Auto</option>
          <option value="squash">Squash</option>
        </select>

        {strategy === 'native' && (
          <>
            <label className="text-xs text-gray-400">Conflict:</label>
            <select
              value={conflict}
              onChange={(e) => setConflict(e.target.value)}
              className="bg-gray-700 text-gray-200 text-xs px-2 py-1 rounded border border-gray-600"
            >
              <option value="skip">Skip (keep target)</option>
              <option value="accept">Accept (use source)</option>
            </select>
          </>
        )}
      </div>

      <button
        onClick={handleMerge}
        disabled={loading}
        className="bg-green-600 text-white text-sm px-4 py-1.5 rounded hover:bg-green-500 disabled:opacity-50"
      >
        {loading ? 'Merging...' : 'Merge'}
      </button>
    </div>
  );
}
