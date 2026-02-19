import SearchBar from './components/SearchBar';
import BranchTree from './components/BranchTree';
import Timeline from './components/Timeline';
import MergePanel from './components/MergePanel';
import FactDetail from './components/FactDetail';
import ConversationList from './components/ConversationList';
import ConversationThread from './components/ConversationThread';
import ReplayList from './components/ReplayList';
import SemanticDiffView from './components/SemanticDiffView';
import AnalyticsDashboard from './components/AnalyticsDashboard';
import { useBranchStore } from './stores/branchStore';
import { useConversationStore } from './stores/conversationStore';

type Tab = 'memory' | 'conversations' | 'analytics';

export default function App() {
  const { activeBranch, error, clearError } = useBranchStore();
  const { tab, setTab } = useConversationStore();

  const activeTab = tab as Tab;

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 p-4">
      {/* Header */}
      <header className="mb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <h1 className="text-xl font-bold text-white">
              Day1
            </h1>
            {/* Tab nav */}
            <nav className="flex gap-1">
              {(['memory', 'conversations', 'analytics'] as Tab[]).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`text-xs px-3 py-1 rounded-full transition-colors ${
                    activeTab === t
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-700 text-gray-400 hover:text-gray-200'
                  }`}
                >
                  {t.charAt(0).toUpperCase() + t.slice(1)}
                </button>
              ))}
            </nav>
          </div>
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

      {/* Memory tab (original) */}
      {activeTab === 'memory' && (
        <>
          <div className="mb-4">
            <SearchBar />
          </div>
          <div className="grid grid-cols-12 gap-4">
            <div className="col-span-4 h-[500px]">
              <BranchTree />
            </div>
            <div className="col-span-8 space-y-4">
              <Timeline />
              <MergePanel />
              <FactDetail />
            </div>
          </div>
        </>
      )}

      {/* Conversations tab */}
      {activeTab === 'conversations' && (
        <div className="grid grid-cols-12 gap-4">
          <div className="col-span-3 h-[calc(100vh-8rem)]">
            <ConversationList />
          </div>
          <div className="col-span-6 h-[calc(100vh-8rem)]">
            <ConversationThread />
          </div>
          <div className="col-span-3 space-y-3 max-h-[calc(100vh-8rem)] overflow-y-auto">
            <ReplayList />
            <SemanticDiffView />
          </div>
        </div>
      )}

      {/* Analytics tab */}
      {activeTab === 'analytics' && (
        <AnalyticsDashboard />
      )}
    </div>
  );
}
