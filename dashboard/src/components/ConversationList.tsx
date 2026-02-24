import { useEffect } from 'react';
import { useConversationStore } from '../stores/conversationStore';
import { useVisiblePolling } from '../hooks/usePolling';

const STATUS_COLORS: Record<string, string> = {
  active: '#22c55e',
  completed: '#3b82f6',
  replaying: '#f59e0b',
  archived: '#9ca3af',
};

export default function ConversationList() {
  const {
    conversations,
    selectedConversation,
    loading,
    fetchConversations,
    refreshConversations,
    selectConversation,
    fetchReplays,
    refreshReplays,
    pollingEnabled,
  } = useConversationStore();

  // Initial fetch
  useEffect(() => {
    fetchConversations({ limit: 50 });
  }, [fetchConversations]);

  // Poll conversations every 5 seconds
  useVisiblePolling(refreshConversations, 5000, pollingEnabled);

  // Poll replays for selected conversation every 5 seconds
  useVisiblePolling(refreshReplays, 5000, pollingEnabled && selectedConversation !== null);

  return (
    <div className="bg-white rounded-lg p-3 h-full overflow-hidden flex flex-col border border-gray-200 shadow-sm">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-gray-700 font-medium">Conversations</span>
        <span className="text-xs text-gray-500">{conversations.length} total</span>
      </div>

      <div className="flex-1 overflow-y-auto space-y-1">
        {loading && conversations.length === 0 && (
          <p className="text-xs text-gray-500 p-2">Loading...</p>
        )}

        {conversations.map((conv) => {
          const isSelected = selectedConversation?.id === conv.id;
          return (
            <button
              key={conv.id}
              onClick={() => {
                selectConversation(conv.id);
                fetchReplays(conv.id);
              }}
              className={`w-full text-left p-2 rounded text-xs transition-colors ${
                isSelected
                  ? 'bg-blue-100 border border-blue-300'
                  : 'bg-gray-50 hover:bg-gray-100 border border-transparent'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-gray-800 truncate font-medium">
                  {conv.title || conv.id.slice(0, 12)}
                </span>
                <span
                  className="inline-block w-2 h-2 rounded-full ml-2 flex-shrink-0"
                  style={{ backgroundColor: STATUS_COLORS[conv.status] || '#9ca3af' }}
                  title={conv.status}
                />
              </div>
              <div className="flex items-center gap-2 mt-1 text-gray-500">
                <span>{conv.message_count} msgs</span>
                <span>{conv.total_tokens.toLocaleString()} tok</span>
                {conv.parent_conversation_id && (
                  <span className="text-amber-600">fork</span>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
