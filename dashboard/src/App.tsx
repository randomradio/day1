import { useEffect, useState } from 'react';
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

const TAB_CONFIG: { id: Tab; label: string }[] = [
  { id: 'memory', label: 'Memory' },
  { id: 'conversations', label: 'Conversations' },
  { id: 'analytics', label: 'Analytics' },
];

function ConnectionBadge() {
  const [status, setStatus] = useState<'checking' | 'ok' | 'error'>('checking');

  useEffect(() => {
    fetch('/health')
      .then((r) => setStatus(r.ok ? 'ok' : 'error'))
      .catch(() => setStatus('error'));
  }, []);

  const colors = {
    checking: 'bg-yellow-500',
    ok: 'bg-green-500',
    error: 'bg-red-500',
  };

  return (
    <span className="flex items-center gap-1.5 text-xs text-gray-400" title={`API: ${status}`}>
      <span className={`w-2 h-2 rounded-full ${colors[status]}`} />
      {status === 'ok' ? 'Connected' : status === 'error' ? 'Disconnected' : '...'}
    </span>
  );
}

function EmptyState({ tab }: { tab: Tab }) {
  const messages: Record<Tab, { title: string; desc: string }> = {
    memory: {
      title: 'No memories yet',
      desc: 'Start using Day1 via MCP tools or the REST API to capture facts, observations, and relations.',
    },
    conversations: {
      title: 'No conversations recorded',
      desc: 'Use memory_log_message or Claude Code hooks to capture conversations. Fork, replay, and diff them here.',
    },
    analytics: {
      title: 'Waiting for data',
      desc: 'Analytics will populate automatically as you use Day1.',
    },
  };
  const m = messages[tab];
  return (
    <div className="flex flex-col items-center justify-center h-64 text-center">
      <h3 className="text-sm font-medium text-gray-400 mb-1">{m.title}</h3>
      <p className="text-xs text-gray-600 max-w-sm">{m.desc}</p>
    </div>
  );
}

export default function App() {
  const { activeBranch, branches, error, clearError, fetchBranches } = useBranchStore();
  const { tab, setTab } = useConversationStore();
  const [initialized, setInitialized] = useState(false);

  const activeTab = tab as Tab;

  useEffect(() => {
    fetchBranches().then(() => setInitialized(true));
  }, [fetchBranches]);

  const hasData = branches.length > 0;

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-gray-950/90 backdrop-blur border-b border-gray-800">
        <div className="max-w-[1600px] mx-auto px-4 py-2.5 flex items-center justify-between">
          <div className="flex items-center gap-5">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white text-xs font-bold">
                D1
              </div>
              <span className="text-sm font-semibold text-white tracking-tight">Day1</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-500 font-mono">v0.1</span>
            </div>

            <nav className="flex gap-0.5">
              {TAB_CONFIG.map(({ id, label }) => (
                <button
                  key={id}
                  onClick={() => setTab(id)}
                  className={`text-xs px-3 py-1.5 rounded-md transition-all ${
                    activeTab === id
                      ? 'bg-blue-600/20 text-blue-400 font-medium'
                      : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800/50'
                  }`}
                >
                  {label}
                </button>
              ))}
            </nav>
          </div>

          <div className="flex items-center gap-3">
            <ConnectionBadge />
            <span className="text-xs bg-gray-800 px-2.5 py-1 rounded-md text-blue-400 font-mono border border-gray-700">
              {activeBranch}
            </span>
          </div>
        </div>
      </header>

      {/* Error banner */}
      {error && (
        <div className="max-w-[1600px] mx-auto px-4 mt-2">
          <div className="bg-red-900/30 border border-red-800/50 text-red-300 text-xs px-4 py-2 rounded-lg flex items-center justify-between">
            <span>{error}</span>
            <button onClick={clearError} className="text-red-400 hover:text-red-200 ml-4">
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Main content */}
      <main className="max-w-[1600px] mx-auto px-4 py-4">
        {!initialized ? (
          <div className="flex items-center justify-center h-64">
            <div className="text-xs text-gray-600">Loading...</div>
          </div>
        ) : (
          <>
            {activeTab === 'memory' && (
              <>
                <div className="mb-4">
                  <SearchBar />
                </div>
                {!hasData ? (
                  <EmptyState tab="memory" />
                ) : (
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
                )}
              </>
            )}

            {activeTab === 'conversations' && (
              <div className="grid grid-cols-12 gap-4">
                <div className="col-span-3 h-[calc(100vh-6rem)]">
                  <ConversationList />
                </div>
                <div className="col-span-6 h-[calc(100vh-6rem)]">
                  <ConversationThread />
                </div>
                <div className="col-span-3 space-y-3 max-h-[calc(100vh-6rem)] overflow-y-auto">
                  <ReplayList />
                  <SemanticDiffView />
                </div>
              </div>
            )}

            {activeTab === 'analytics' && <AnalyticsDashboard />}
          </>
        )}
      </main>
    </div>
  );
}
