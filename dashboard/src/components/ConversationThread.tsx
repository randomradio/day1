import { useConversationStore } from '../stores/conversationStore';
import { useVisiblePolling } from '../hooks/usePolling';

const ROLE_STYLES: Record<string, { bg: string; label: string; text: string }> = {
  user: { bg: 'bg-blue-50', label: 'User', text: 'text-blue-700' },
  assistant: { bg: 'bg-green-50', label: 'Assistant', text: 'text-green-700' },
  system: { bg: 'bg-gray-100', label: 'System', text: 'text-gray-600' },
  tool_call: { bg: 'bg-amber-50', label: 'Tool Call', text: 'text-amber-700' },
  tool_result: { bg: 'bg-cyan-50', label: 'Tool Result', text: 'text-cyan-700' },
};

function getRoleStyle(role: string) {
  return ROLE_STYLES[role] || { bg: 'bg-gray-100', label: role, text: 'text-gray-600' };
}

export default function ConversationThread() {
  const { selectedConversation, messages, selectedMessage, scores, evaluateConversation, loading, setSelectedMessage, refreshMessages, pollingEnabled } =
    useConversationStore();

  // Poll messages for selected conversation every 5 seconds
  useVisiblePolling(refreshMessages, 5000, pollingEnabled && selectedConversation !== null);

  if (!selectedConversation) {
    return (
      <div className="bg-white rounded-lg p-4 flex items-center justify-center h-full border border-gray-200 shadow-sm">
        <p className="text-gray-500 text-sm">Select a conversation to view its thread</p>
      </div>
    );
  }

  const conv = selectedConversation;

  return (
    <div className="bg-white rounded-lg p-3 flex flex-col h-full overflow-hidden border border-gray-200 shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between mb-3 pb-2 border-b border-gray-200">
        <div>
          <h3 className="text-sm font-medium text-gray-800">
            {conv.title || 'Untitled'}
          </h3>
          <div className="flex gap-3 text-xs text-gray-500 mt-0.5">
            <span>{conv.message_count} messages</span>
            <span>{conv.total_tokens.toLocaleString()} tokens</span>
            {conv.model && <span>{conv.model}</span>}
            <span className="text-gray-400">{conv.id.slice(0, 8)}</span>
          </div>
        </div>
        <button
          onClick={() => evaluateConversation(conv.id)}
          disabled={loading}
          className="bg-purple-600 text-white text-xs px-3 py-1 rounded hover:bg-purple-700 disabled:opacity-50 shadow-sm"
        >
          Evaluate
        </button>
      </div>

      {/* Scores bar */}
      {scores.length > 0 && (
        <div className="flex gap-2 mb-2 flex-wrap">
          {scores.map((s) => (
            <span
              key={s.id}
              className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-700"
              title={s.explanation || ''}
            >
              {s.dimension}: <span className="font-mono">{s.value.toFixed(2)}</span>
            </span>
          ))}
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-2">
        {messages.map((msg) => {
          const style = getRoleStyle(msg.role);
          const isSelected = selectedMessage?.id === msg.id;
          return (
            <div
              key={msg.id}
              onClick={() => setSelectedMessage(msg)}
              className={`${style.bg} rounded p-2 border transition-all cursor-pointer hover:shadow-sm ${
                isSelected ? 'ring-2 ring-blue-400 border-blue-300' : 'border-gray-100'
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                <span className={`text-xs font-medium ${style.text}`}>
                  {style.label}
                </span>
                <span className="text-xs text-gray-500">#{msg.sequence_num}</span>
                {msg.token_count > 0 && (
                  <span className="text-xs text-gray-500">{msg.token_count} tok</span>
                )}
                {isSelected && (
                  <span className="ml-auto text-xs text-blue-500">→ Details</span>
                )}
              </div>
              {msg.content && (
                <pre className="text-xs text-gray-700 whitespace-pre-wrap break-words font-mono leading-relaxed">
                  {msg.content.length > 2000
                    ? msg.content.slice(0, 2000) + '...'
                    : msg.content}
                </pre>
              )}
              {msg.thinking && (
                <details className="mt-1">
                  <summary className="text-xs text-gray-500 cursor-pointer">Thinking</summary>
                  <pre className="text-xs text-gray-600 whitespace-pre-wrap mt-1 pl-2 border-l border-gray-300">
                    {msg.thinking.slice(0, 1000)}
                  </pre>
                </details>
              )}
              {msg.tool_calls && msg.tool_calls.length > 0 && (
                <div className="mt-1 space-y-1">
                  {msg.tool_calls.map((tc, i) => (
                    <div key={i} className="text-xs bg-white/50 rounded px-2 py-1">
                      <span className="text-amber-700">{tc.name}</span>
                      {tc.input && (
                        <span className="text-gray-600 ml-2">
                          {tc.input.slice(0, 100)}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
