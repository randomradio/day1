import SearchBar from './components/SearchBar';
import BranchTree from './components/BranchTree';
import Timeline from './components/Timeline';
import MergePanel from './components/MergePanel';
import FactDetail from './components/FactDetail';
import { useBranchStore } from './stores/branchStore';

export default function App() {
  const { activeBranch, error, clearError } = useBranchStore();

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 p-4">
      {/* Header */}
      <header className="mb-4">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold text-white">
            BranchedMind
            <span className="text-sm font-normal text-gray-400 ml-2">
              Memory Dashboard
            </span>
          </h1>
          <span className="text-sm bg-gray-700 px-3 py-1 rounded-full text-blue-400">
            {activeBranch}
          </span>
        </div>
      </header>

      {/* Error banner */}
      {error && (
        <div className="bg-red-900/50 border border-red-700 text-red-300 text-sm px-4 py-2 rounded-lg mb-4 flex items-center justify-between">
          <span>{error}</span>
          <button onClick={clearError} className="text-red-400 hover:text-red-200">
            x
          </button>
        </div>
      )}

      {/* Search */}
      <div className="mb-4">
        <SearchBar />
      </div>

      {/* Main layout */}
      <div className="grid grid-cols-12 gap-4">
        {/* Left: Branch Tree */}
        <div className="col-span-4 h-[500px]">
          <BranchTree />
        </div>

        {/* Right: Timeline + Content */}
        <div className="col-span-8 space-y-4">
          <Timeline />
          <MergePanel />
          <FactDetail />
        </div>
      </div>
    </div>
  );
}
