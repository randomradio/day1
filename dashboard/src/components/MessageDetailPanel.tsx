import { useConversationStore } from '../stores/conversationStore';

const ROLE_BADGES: Record<string, { bg: string; text: string; label: string }> = {
  user: { bg: 'bg-blue-100', text: 'text-blue-700', label: 'User' },
  assistant: { bg: 'bg-green-100', text: 'text-green-700', label: 'Assistant' },
  system: { bg: 'bg-gray-100', text: 'text-gray-700', label: 'System' },
  tool_call: { bg: 'bg-amber-100', text: 'text-amber-700', label: 'Tool Call' },
  tool_result: { bg: 'bg-cyan-100', text: 'text-cyan-700', label: 'Tool Result' },
};

function getRoleBadge(role: string) {
  return ROLE_BADGES[role] || { bg: 'bg-gray-100', text: 'text-gray-700', label: role };
}

function MetadataRow({ label, value }: { label: string; value: string | number | undefined }) {
  if (value === undefined || value === null || value === '') return null;
  return (
    <div className="flex justify-between py-1 border-b border-gray-100 last:border-0">
      <span className="text-xs text-gray-500">{label}</span>
      <span className="text-xs text-gray-800 font-mono text-right">{String(value)}</span>
    </div>
  );
}

export default function MessageDetailPanel() {
  const { selectedMessage } = useConversationStore();

  if (!selectedMessage) {
    return (
      <div className="bg-white rounded-lg p-4 h-full border border-gray-200 shadow-sm flex items-center justify-center">
        <p className="text-sm text-gray-500">Select a message to view details</p>
      </div>
    );
  }

  const badge = getRoleBadge(selectedMessage.role);

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200 bg-gray-50">
        <span className={`text-xs px-2 py-0.5 rounded font-medium ${badge.bg} ${badge.text}`}>
          {badge.label}
        </span>
        <span className="text-xs text-gray-400 font-mono">#{selectedMessage.sequence_num}</span>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {/* Content */}
        {selectedMessage.content && (
          <div>
            <h4 className="text-xs font-semibold text-gray-600 mb-2">Content</h4>
            <pre className="text-xs text-gray-800 whitespace-pre-wrap break-words font-mono leading-relaxed bg-gray-50 rounded p-2 border border-gray-100">
              {selectedMessage.content}
            </pre>
          </div>
        )}

        {/* Thinking */}
        {selectedMessage.thinking && (
          <details className="group">
            <summary className="text-xs font-semibold text-gray-600 cursor-pointer hover:text-gray-800 flex items-center gap-1">
              <span className="transform group-open:rotate-90 transition-transform">▶</span>
              Thinking
            </summary>
            <pre className="text-xs text-gray-700 whitespace-pre-wrap mt-2 p-2 bg-gray-50 rounded border border-gray-100 font-mono leading-relaxed">
              {selectedMessage.thinking}
            </pre>
          </details>
        )}

        {/* Tool Calls */}
        {selectedMessage.tool_calls && selectedMessage.tool_calls.length > 0 && (
          <div>
            <h4 className="text-xs font-semibold text-gray-600 mb-2">Tool Calls</h4>
            <div className="space-y-2">
              {selectedMessage.tool_calls.map((tc, i) => (
                <div key={i} className="bg-gray-50 rounded border border-gray-100 overflow-hidden">
                  <div className="px-2 py-1 bg-amber-50 border-b border-amber-100">
                    <span className="text-xs font-medium text-amber-800 font-mono">{tc.name}</span>
                  </div>
                  <div className="p-2 space-y-1">
                    {tc.input && (
                      <div>
                        <span className="text-xs text-gray-500 block mb-1">Input:</span>
                        <pre className="text-xs text-gray-700 whitespace-pre-wrap break-words font-mono bg-white rounded p-1.5 border border-gray-200">
                          {typeof tc.input === 'string' ? tc.input : JSON.stringify(tc.input, null, 2)}
                        </pre>
                      </div>
                    )}
                    {tc.output && (
                      <div>
                        <span className="text-xs text-gray-500 block mb-1">Output:</span>
                        <pre className="text-xs text-gray-700 whitespace-pre-wrap break-words font-mono bg-white rounded p-1.5 border border-gray-200">
                          {typeof tc.output === 'string' ? tc.output : JSON.stringify(tc.output, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Metadata */}
        <div>
          <h4 className="text-xs font-semibold text-gray-600 mb-2">Metadata</h4>
          <div className="bg-gray-50 rounded border border-gray-100 p-2">
            <MetadataRow label="Message ID" value={selectedMessage.id.slice(0, 12)} />
            <MetadataRow label="Sequence" value={selectedMessage.sequence_num} />
            <MetadataRow label="Tokens" value={selectedMessage.token_count} />
            <MetadataRow label="Model" value={selectedMessage.model} />
            <MetadataRow label="Session ID" value={selectedMessage.session_id?.slice(0, 8)} />
            <MetadataRow label="Agent ID" value={selectedMessage.agent_id?.slice(0, 8)} />
            <MetadataRow label="Branch" value={selectedMessage.branch_name} />
            <MetadataRow
              label="Created"
              value={selectedMessage.created_at ? new Date(selectedMessage.created_at).toLocaleString() : undefined}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
