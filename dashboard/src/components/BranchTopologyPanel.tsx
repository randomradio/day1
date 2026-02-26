import { useEffect, useState } from 'react';
import { useBranchStore } from '../stores/branchStore';
import { api } from '../api/client';

export default function BranchTopologyPanel() {
  const {
    activeBranch,
    branchStats,
    fetchTopology,
    fetchBranchStats,
    enrichBranch,
    autoArchive,
    loading,
    error,
  } = useBranchStore();

  const [archiveDays, setArchiveDays] = useState(30);
  const [dryRun, setDryRun] = useState(true);
  const [archiveResult, setArchiveResult] = useState<string | null>(null);
  const [expired, setExpired] = useState<Array<{ branch_name: string; ttl_days: number; expired_at: string }>>([]);

  // Enrich form
  const [purpose, setPurpose] = useState('');
  const [owner, setOwner] = useState('');
  const [ttlDays, setTtlDays] = useState('');
  const [tags, setTags] = useState('');

  useEffect(() => {
    fetchTopology();
  }, [fetchTopology]);

  useEffect(() => {
    if (activeBranch) {
      fetchBranchStats(activeBranch);
    }
  }, [activeBranch, fetchBranchStats]);

  const handleAutoArchive = async () => {
    try {
      const result = await autoArchive(archiveDays, true, dryRun);
      setArchiveResult(
        dryRun
          ? `${result.candidates.length} candidate(s) found (dry run)`
          : `${result.archived} branch(es) archived`
      );
    } catch {
      setArchiveResult('Failed to run auto-archive');
    }
  };

  const handleCheckExpired = async () => {
    try {
      const data = await api.getExpiredBranches();
      setExpired(data.expired);
    } catch {
      setExpired([]);
    }
  };

  const handleEnrich = async () => {
    const data: Record<string, unknown> = {};
    if (purpose) data.purpose = purpose;
    if (owner) data.owner = owner;
    if (ttlDays) data.ttl_days = parseInt(ttlDays, 10);
    if (tags) data.tags = tags.split(',').map((t) => t.trim());

    await enrichBranch(activeBranch, data as { purpose?: string; owner?: string; ttl_days?: number; tags?: string[] });
    setPurpose('');
    setOwner('');
    setTtlDays('');
    setTags('');
  };

  return (
    <div className="space-y-4">
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-3 py-2 rounded text-sm">
          {error}
        </div>
      )}

      {/* Branch Stats */}
      {branchStats && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-2">
            Stats: {branchStats.branch_name}
          </h3>
          <div className="grid grid-cols-3 gap-2 text-sm">
            <div className="bg-blue-50 rounded p-2 text-center">
              <div className="text-lg font-bold text-blue-600">{branchStats.fact_count}</div>
              <div className="text-xs text-gray-500">Facts</div>
            </div>
            <div className="bg-green-50 rounded p-2 text-center">
              <div className="text-lg font-bold text-green-600">{branchStats.conversation_count}</div>
              <div className="text-xs text-gray-500">Conversations</div>
            </div>
            <div className="bg-purple-50 rounded p-2 text-center">
              <div className="text-lg font-bold text-purple-600">{branchStats.observation_count}</div>
              <div className="text-xs text-gray-500">Observations</div>
            </div>
          </div>
          {branchStats.last_activity && (
            <div className="text-xs text-gray-400 mt-2">
              Last activity: {new Date(branchStats.last_activity).toLocaleString()}
            </div>
          )}
        </div>
      )}

      {/* Enrich Metadata */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold mb-2">
          Enrich: {activeBranch}
        </h3>
        <div className="space-y-2">
          <input
            className="w-full border rounded px-2 py-1 text-sm"
            placeholder="Purpose"
            value={purpose}
            onChange={(e) => setPurpose(e.target.value)}
          />
          <input
            className="w-full border rounded px-2 py-1 text-sm"
            placeholder="Owner"
            value={owner}
            onChange={(e) => setOwner(e.target.value)}
          />
          <div className="flex gap-2">
            <input
              className="w-1/2 border rounded px-2 py-1 text-sm"
              placeholder="TTL (days)"
              type="number"
              value={ttlDays}
              onChange={(e) => setTtlDays(e.target.value)}
            />
            <input
              className="w-1/2 border rounded px-2 py-1 text-sm"
              placeholder="Tags (comma-separated)"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
            />
          </div>
          <button
            className="bg-blue-500 text-white px-3 py-1 rounded text-sm hover:bg-blue-600 disabled:opacity-50"
            onClick={handleEnrich}
            disabled={loading}
          >
            Enrich
          </button>
        </div>
      </div>

      {/* Auto-Archive */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold mb-2">Auto-Archive</h3>
        <div className="flex items-center gap-2 mb-2">
          <label className="text-sm">Inactive days:</label>
          <input
            type="range"
            min={7}
            max={90}
            value={archiveDays}
            onChange={(e) => setArchiveDays(Number(e.target.value))}
            className="flex-1"
          />
          <span className="text-sm font-mono w-8">{archiveDays}</span>
        </div>
        <div className="flex items-center gap-2 mb-2">
          <label className="flex items-center gap-1 text-sm">
            <input
              type="checkbox"
              checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
            />
            Dry run
          </label>
        </div>
        <button
          className="bg-orange-500 text-white px-3 py-1 rounded text-sm hover:bg-orange-600 disabled:opacity-50"
          onClick={handleAutoArchive}
          disabled={loading}
        >
          {dryRun ? 'Preview Archive' : 'Archive Now'}
        </button>
        {archiveResult && (
          <div className="mt-2 text-sm text-gray-600">{archiveResult}</div>
        )}
      </div>

      {/* TTL Expiry */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold mb-2">TTL Expiry</h3>
        <button
          className="bg-gray-500 text-white px-3 py-1 rounded text-sm hover:bg-gray-600 mb-2"
          onClick={handleCheckExpired}
        >
          Check Expired
        </button>
        {expired.length > 0 ? (
          <ul className="text-sm space-y-1">
            {expired.map((e) => (
              <li key={e.branch_name} className="flex justify-between text-red-600">
                <span>{e.branch_name}</span>
                <span className="text-xs">TTL: {e.ttl_days}d</span>
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-sm text-gray-400">No expired branches</div>
        )}
      </div>
    </div>
  );
}
