import { useConversationStore } from '../stores/conversationStore';

const VERDICT_COLORS: Record<string, string> = {
  equivalent: 'text-green-400',
  similar: 'text-blue-400',
  divergent: 'text-red-400',
  mixed: 'text-amber-400',
};

function Bar({ value, max = 1, color }: { value: number; max?: number; color: string }) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div className="w-full bg-gray-700 rounded-full h-1.5">
      <div className="h-1.5 rounded-full" style={{ width: `${pct}%`, backgroundColor: color }} />
    </div>
  );
}

export default function SemanticDiffView() {
  const { semanticDiff } = useConversationStore();

  if (!semanticDiff) return null;

  const { summary, action_diff, outcome_diff, divergence_point } = semanticDiff;

  return (
    <div className="bg-gray-800 rounded-lg p-3 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm text-gray-400 font-medium">Semantic Diff</span>
        <span className={`text-sm font-bold ${VERDICT_COLORS[summary.verdict] || 'text-gray-400'}`}>
          {summary.verdict.toUpperCase()}
        </span>
      </div>

      <p className="text-xs text-gray-500">{summary.description}</p>

      {/* Summary metrics */}
      <div className="grid grid-cols-3 gap-3">
        <div>
          <div className="text-xs text-gray-500 mb-1">Action Match</div>
          <div className="text-sm font-mono text-gray-200">{(summary.action_match * 100).toFixed(0)}%</div>
          <Bar value={summary.action_match} color="#f59e0b" />
        </div>
        <div>
          <div className="text-xs text-gray-500 mb-1">Reasoning Similarity</div>
          <div className="text-sm font-mono text-gray-200">{(summary.reasoning_similarity * 100).toFixed(0)}%</div>
          <Bar value={summary.reasoning_similarity} color="#3b82f6" />
        </div>
        <div>
          <div className="text-xs text-gray-500 mb-1">Efficiency</div>
          <div className="text-sm font-mono text-gray-200">{summary.efficiency}</div>
        </div>
      </div>

      {/* Divergence point */}
      {divergence_point.shared_prefix_length > 0 && (
        <div className="bg-gray-700/30 rounded p-2 text-xs">
          <span className="text-gray-500">Diverges after </span>
          <span className="text-gray-300 font-mono">{divergence_point.shared_prefix_length}</span>
          <span className="text-gray-500"> shared messages</span>
          {divergence_point.note && (
            <span className="text-gray-600 ml-2">({divergence_point.note})</span>
          )}
        </div>
      )}

      {/* Action diff details */}
      <details>
        <summary className="text-xs text-gray-500 cursor-pointer">
          Actions: {action_diff.a_tool_count} vs {action_diff.b_tool_count} tool calls
          ({(action_diff.sequence_similarity * 100).toFixed(0)}% sequence match)
        </summary>
        <div className="mt-1 space-y-1">
          {action_diff.entries.slice(0, 20).map((e, i) => (
            <div key={i} className="text-xs flex items-center gap-2 px-2">
              <span className={
                e.op === 'equal' ? 'text-gray-500' :
                e.op === 'insert' ? 'text-green-500' :
                e.op === 'delete' ? 'text-red-500' :
                'text-amber-500'
              }>
                {e.op === 'equal' ? '=' : e.op === 'insert' ? '+' : e.op === 'delete' ? '-' : '~'}
              </span>
              <span className="text-gray-400 font-mono">
                {e.tool || e.a_tool || e.b_tool}
              </span>
            </div>
          ))}
        </div>
      </details>

      {/* Outcome diff */}
      <details>
        <summary className="text-xs text-gray-500 cursor-pointer">
          Outcome: {outcome_diff.delta.messages > 0 ? '+' : ''}{outcome_diff.delta.messages} msgs,{' '}
          {outcome_diff.delta.tokens > 0 ? '+' : ''}{outcome_diff.delta.tokens} tokens
        </summary>
        <div className="mt-1 grid grid-cols-2 gap-2 text-xs">
          <div className="bg-gray-700/30 rounded p-2">
            <div className="text-gray-500 mb-1">Conversation A</div>
            <div className="text-gray-300">{outcome_diff.a.message_count} msgs, {outcome_diff.a.total_tokens} tok, {outcome_diff.a.error_count} errors</div>
          </div>
          <div className="bg-gray-700/30 rounded p-2">
            <div className="text-gray-500 mb-1">Conversation B</div>
            <div className="text-gray-300">{outcome_diff.b.message_count} msgs, {outcome_diff.b.total_tokens} tok, {outcome_diff.b.error_count} errors</div>
          </div>
        </div>
      </details>
    </div>
  );
}
