import { useStore } from '../stores/store';

const CATEGORY_COLORS: Record<string, string> = {
  pattern: 'bg-purple-100 text-purple-700',
  decision: 'bg-blue-100 text-blue-700',
  bug_fix: 'bg-red-100 text-red-700',
  session: 'bg-gray-100 text-gray-700',
  conversation: 'bg-green-100 text-green-700',
  architecture: 'bg-amber-100 text-amber-700',
};

export default function MemoryList() {
  const { memories, loading, searchQuery } = useStore();

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 text-gray-400">
        Loading...
      </div>
    );
  }

  if (memories.length === 0) {
    return (
      <div className="flex items-center justify-center py-12 text-gray-400">
        {searchQuery ? 'No results found' : 'No memories yet'}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {searchQuery && (
        <p className="text-xs text-gray-500">
          {memories.length} result{memories.length !== 1 ? 's' : ''} for "{searchQuery}"
        </p>
      )}
      {memories.map((m) => (
        <div
          key={m.id}
          className="border border-gray-200 rounded-lg p-3 hover:border-gray-300 transition-colors"
        >
          <div className="flex items-start justify-between gap-2">
            <p className="text-sm text-gray-900 flex-1">{m.text}</p>
            <div className="flex items-center gap-1.5 shrink-0">
              {m.category && (
                <span
                  className={`text-xs px-1.5 py-0.5 rounded ${
                    CATEGORY_COLORS[m.category] || 'bg-gray-100 text-gray-600'
                  }`}
                >
                  {m.category}
                </span>
              )}
              <span className="text-xs text-gray-400">
                {(m.confidence * 100).toFixed(0)}%
              </span>
            </div>
          </div>
          {m.context && (
            <p className="text-xs text-gray-500 mt-1">{m.context}</p>
          )}
          <div className="flex items-center gap-3 mt-2 text-xs text-gray-400">
            <span>{new Date(m.created_at).toLocaleString()}</span>
            {m.source_type && <span>{m.source_type}</span>}
            {m.file_context && (
              <span className="font-mono truncate max-w-48" title={m.file_context}>
                {m.file_context}
              </span>
            )}
            {m.score != null && m.score > 0 && (
              <span>score: {m.score.toFixed(2)}</span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
