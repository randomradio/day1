import { useEffect, useState } from 'react';
import { useBranchStore } from '../stores/branchStore';
import { api } from '../api/client';
import type { KnowledgeBundle } from '../types/schema';

export default function BundlePanel() {
  const { activeBranch } = useBranchStore();
  const [bundles, setBundles] = useState<KnowledgeBundle[]>([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  // Create form
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [tags, setTags] = useState('');
  const [onlyVerified, setOnlyVerified] = useState(true);

  // Import
  const [importBranch, setImportBranch] = useState('');

  useEffect(() => {
    loadBundles();
  }, []);

  const loadBundles = async () => {
    try {
      const data = await api.listBundles();
      setBundles(data.bundles);
    } catch {
      setBundles([]);
    }
  };

  const handleCreate = async () => {
    if (!name) return;
    setLoading(true);
    try {
      const bundle = await api.createBundle({
        name,
        source_branch: activeBranch,
        description: description || undefined,
        tags: tags ? tags.split(',').map((t) => t.trim()) : undefined,
        only_verified: onlyVerified,
      });
      setResult(
        `Bundle "${bundle.name}" created: ${bundle.fact_count} facts, ${bundle.conversation_count} conversations`
      );
      setName('');
      setDescription('');
      setTags('');
      await loadBundles();
    } catch {
      setResult('Failed to create bundle');
    }
    setLoading(false);
  };

  const handleImport = async (bundleId: string) => {
    if (!importBranch) return;
    setLoading(true);
    try {
      const result = await api.importBundle(bundleId, importBranch);
      setResult(
        `Imported: ${result.facts_imported} facts, ${result.conversations_imported} conversations, ${result.relations_imported} relations`
      );
    } catch {
      setResult('Failed to import bundle');
    }
    setLoading(false);
  };

  return (
    <div className="space-y-4">
      {/* Create Bundle */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold mb-2">
          Create Bundle from: {activeBranch}
        </h3>
        <div className="space-y-2">
          <input
            className="w-full border rounded px-2 py-1 text-sm"
            placeholder="Bundle name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            className="w-full border rounded px-2 py-1 text-sm"
            placeholder="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <input
            className="w-full border rounded px-2 py-1 text-sm"
            placeholder="Tags (comma-separated)"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
          />
          <label className="flex items-center gap-1 text-sm">
            <input
              type="checkbox"
              checked={onlyVerified}
              onChange={(e) => setOnlyVerified(e.target.checked)}
            />
            Only include verified facts
          </label>
          <button
            className="bg-purple-500 text-white px-3 py-1 rounded text-sm hover:bg-purple-600 disabled:opacity-50"
            onClick={handleCreate}
            disabled={loading || !name}
          >
            Create Bundle
          </button>
        </div>
      </div>

      {result && (
        <div className="bg-blue-50 border border-blue-200 text-blue-700 px-3 py-2 rounded text-sm">
          {result}
        </div>
      )}

      {/* Bundle List */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold mb-2">Knowledge Bundles</h3>
        <div className="mb-2">
          <input
            className="w-full border rounded px-2 py-1 text-sm"
            placeholder="Target branch for import"
            value={importBranch}
            onChange={(e) => setImportBranch(e.target.value)}
          />
        </div>
        {bundles.length > 0 ? (
          <ul className="text-sm space-y-2">
            {bundles.map((b) => (
              <li key={b.id} className="border border-gray-100 rounded p-2">
                <div className="flex justify-between items-start">
                  <div>
                    <div className="font-medium">{b.name}</div>
                    {b.description && (
                      <div className="text-xs text-gray-500">{b.description}</div>
                    )}
                  </div>
                  <button
                    className="bg-green-500 text-white px-2 py-0.5 rounded text-xs hover:bg-green-600 disabled:opacity-50"
                    onClick={() => handleImport(b.id)}
                    disabled={!importBranch || loading}
                  >
                    Import
                  </button>
                </div>
                <div className="flex gap-2 mt-1 text-xs text-gray-400">
                  <span>{b.fact_count} facts</span>
                  <span>{b.conversation_count} convs</span>
                  <span>{b.relation_count} rels</span>
                  {b.source_branch && <span>from: {b.source_branch}</span>}
                </div>
                {b.tags && b.tags.length > 0 && (
                  <div className="flex gap-1 mt-1">
                    {b.tags.map((t) => (
                      <span
                        key={t}
                        className="bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded text-xs"
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-sm text-gray-400">No bundles yet</div>
        )}
      </div>
    </div>
  );
}
