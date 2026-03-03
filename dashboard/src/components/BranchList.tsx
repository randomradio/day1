import { useState } from 'react';
import { useStore } from '../stores/store';

export default function BranchList() {
  const { branches, activeBranch, setActiveBranch, createBranch, mergeBranch } = useStore();
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [mergeSource, setMergeSource] = useState<string | null>(null);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    await createBranch(newName.trim());
    setNewName('');
    setShowCreate(false);
  };

  const handleMerge = async (source: string) => {
    await mergeBranch(source, 'main');
    setMergeSource(null);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-gray-700">Branches</h3>
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
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
            placeholder="branch-name"
            className="flex-1 text-xs border border-gray-300 rounded px-2 py-1"
          />
          <button
            onClick={handleCreate}
            className="text-xs bg-blue-600 text-white px-2 py-1 rounded hover:bg-blue-700"
          >
            Create
          </button>
        </div>
      )}

      <ul className="space-y-0.5">
        {branches.map((b) => (
          <li key={b.branch_name} className="group">
            <button
              onClick={() => setActiveBranch(b.branch_name)}
              className={`w-full text-left text-sm px-2 py-1 rounded flex items-center justify-between ${
                b.branch_name === activeBranch
                  ? 'bg-blue-100 text-blue-800 font-medium'
                  : 'text-gray-700 hover:bg-gray-100'
              }`}
            >
              <span className="truncate">{b.branch_name}</span>
              <span className="text-xs text-gray-400">
                {b.status === 'archived' ? 'arc' : ''}
              </span>
            </button>
            {b.branch_name !== 'main' && b.branch_name === activeBranch && (
              <div className="pl-2 mt-0.5">
                {mergeSource === b.branch_name ? (
                  <div className="flex gap-1 text-xs">
                    <button
                      onClick={() => handleMerge(b.branch_name)}
                      className="text-green-600 hover:text-green-800"
                    >
                      Confirm merge to main
                    </button>
                    <button
                      onClick={() => setMergeSource(null)}
                      className="text-gray-400 hover:text-gray-600"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setMergeSource(b.branch_name)}
                    className="text-xs text-gray-500 hover:text-blue-600"
                  >
                    Merge to main
                  </button>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
