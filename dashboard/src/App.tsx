import { useEffect } from 'react';
import ConnectionBadge from './components/ConnectionBadge';
import BranchList from './components/BranchList';
import SnapshotList from './components/SnapshotList';
import SearchBar from './components/SearchBar';
import MemoryList from './components/MemoryList';
import { useStore } from './stores/store';

export default function App() {
  const {
    activeBranch,
    branches,
    count,
    error,
    setError,
    setActiveBranch,
    fetchBranches,
    fetchTimeline,
    fetchCount,
    fetchSnapshots,
  } = useStore();

  useEffect(() => {
    fetchBranches();
    fetchTimeline();
    fetchCount();
    fetchSnapshots();
  }, []);

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-white/90 backdrop-blur border-b border-gray-200 shadow-sm">
        <div className="max-w-[1400px] mx-auto px-4 py-2.5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white text-xs font-bold">
              D1
            </div>
            <span className="text-sm font-semibold tracking-tight">Day1</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-500 font-mono border border-gray-200">
              v2
            </span>
          </div>

          <div className="flex items-center gap-4">
            <ConnectionBadge />
            <select
              value={activeBranch}
              onChange={(e) => setActiveBranch(e.target.value)}
              className="text-xs bg-blue-50 px-2 py-1 rounded-md text-blue-700 font-mono border border-blue-200 cursor-pointer"
            >
              {branches.map((b) => (
                <option key={b.branch_name} value={b.branch_name}>
                  {b.branch_name}
                </option>
              ))}
              {branches.length === 0 && <option value="main">main</option>}
            </select>
            <span className="text-xs text-gray-500">
              {count} {count === 1 ? 'memory' : 'memories'}
            </span>
          </div>
        </div>
      </header>

      {/* Error banner */}
      {error && (
        <div className="max-w-[1400px] mx-auto px-4 mt-2">
          <div className="bg-red-50 border border-red-200 text-red-700 text-xs px-4 py-2 rounded-lg flex items-center justify-between">
            <span>{error}</span>
            <button onClick={() => setError(null)} className="text-red-600 hover:text-red-800 ml-4">
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Main layout */}
      <div className="max-w-[1400px] mx-auto px-4 py-4 grid grid-cols-12 gap-4">
        {/* Sidebar */}
        <aside className="col-span-3 space-y-6">
          <BranchList />
          <SnapshotList />
        </aside>

        {/* Main area */}
        <main className="col-span-9 space-y-4">
          <SearchBar />
          <MemoryList />
        </main>
      </div>
    </div>
  );
}
