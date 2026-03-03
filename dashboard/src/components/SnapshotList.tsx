import { useState } from 'react';
import { useStore } from '../stores/store';

export default function SnapshotList() {
  const { snapshots, createSnapshot } = useStore();
  const [showCreate, setShowCreate] = useState(false);
  const [label, setLabel] = useState('');

  const handleCreate = async () => {
    await createSnapshot(label.trim() || undefined);
    setLabel('');
    setShowCreate(false);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-gray-700">Snapshots</h3>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="text-xs text-blue-600 hover:text-blue-800"
        >
          + New
        </button>
      </div>

      {showCreate && (
        <div className="mb-2 flex gap-1">
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
            placeholder="Label (optional)"
            className="flex-1 text-xs border border-gray-300 rounded px-2 py-1"
          />
          <button
            onClick={handleCreate}
            className="text-xs bg-blue-600 text-white px-2 py-1 rounded hover:bg-blue-700"
          >
            Save
          </button>
        </div>
      )}

      {snapshots.length === 0 ? (
        <p className="text-xs text-gray-400 italic">No snapshots</p>
      ) : (
        <ul className="space-y-0.5">
          {snapshots.map((s) => (
            <li
              key={s.id}
              className="text-xs text-gray-600 px-2 py-1 rounded hover:bg-gray-50"
              title={s.id}
            >
              <div className="truncate font-medium">
                {s.label || s.id.slice(0, 8)}
              </div>
              <div className="text-gray-400">
                {new Date(s.created_at).toLocaleString()}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
