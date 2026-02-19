import { useConversationStore } from '../stores/conversationStore';

export default function ReplayList() {
  const { replays, selectedConversation, fetchSemanticDiff } =
    useConversationStore();

  if (!selectedConversation || replays.length === 0) {
    return null;
  }

  return (
    <div className="bg-gray-800 rounded-lg p-3">
      <span className="text-sm text-gray-400 font-medium">
        Replays ({replays.length})
      </span>
      <div className="mt-2 space-y-1">
        {replays.map((r) => (
          <div
            key={r.replay_id}
            className="flex items-center justify-between text-xs bg-gray-700/30 rounded px-2 py-1.5"
          >
            <div className="flex items-center gap-2">
              <span
                className={`inline-block w-2 h-2 rounded-full ${
                  r.status === 'completed' ? 'bg-green-500' : 'bg-amber-500'
                }`}
              />
              <span className="text-gray-300 font-mono">
                {r.replay_id.slice(0, 8)}
              </span>
              <span className="text-gray-500">{r.message_count} msgs</span>
            </div>
            <button
              onClick={() => {
                if (r.original_conversation_id) {
                  fetchSemanticDiff(r.original_conversation_id, r.replay_id);
                }
              }}
              className="text-cyan-500 hover:text-cyan-400"
            >
              Diff
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
