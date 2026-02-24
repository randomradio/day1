import { useEffect, useState } from 'react';
import { useTemplateStore } from '../stores/templateStore';
import type { TemplateBranch } from '../types/schema';

export default function TemplateList() {
  const { templates, loading, error, fetchTemplates, instantiateTemplate, selectTemplate } =
    useTemplateStore();
  const [instantiateTarget, setInstantiateTarget] = useState('');
  const [instantiating, setInstantiating] = useState<string | null>(null);

  useEffect(() => {
    fetchTemplates();
  }, [fetchTemplates]);

  const handleInstantiate = async (template: TemplateBranch) => {
    if (!instantiateTarget.trim()) return;
    setInstantiating(template.name);
    try {
      await instantiateTemplate(template.name, instantiateTarget.trim());
      setInstantiateTarget('');
      setInstantiating(null);
    } catch {
      setInstantiating(null);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Templates</h2>
        <button
          className="text-sm text-blue-500 hover:text-blue-700"
          onClick={() => fetchTemplates()}
        >
          Refresh
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-3 py-2 rounded text-sm">
          {error}
        </div>
      )}

      {loading && <div className="text-sm text-gray-400">Loading...</div>}

      {templates.length === 0 && !loading && (
        <div className="text-sm text-gray-400 text-center py-4">
          No templates yet. Create one from a curated branch.
        </div>
      )}

      <div className="space-y-2">
        {templates.map((t) => (
          <div
            key={t.id}
            className="bg-white border border-gray-200 rounded-lg p-3 hover:border-blue-300 cursor-pointer"
            onClick={() => selectTemplate(t)}
          >
            <div className="flex items-center justify-between">
              <div>
                <span className="font-medium text-sm">{t.name}</span>
                <span className="ml-2 text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">
                  v{t.version}
                </span>
              </div>
              <span
                className={`text-xs px-1.5 py-0.5 rounded ${
                  t.status === 'active'
                    ? 'bg-green-100 text-green-700'
                    : 'bg-gray-100 text-gray-500'
                }`}
              >
                {t.status}
              </span>
            </div>

            {t.description && (
              <p className="text-xs text-gray-500 mt-1">{t.description}</p>
            )}

            <div className="flex items-center gap-3 mt-2 text-xs text-gray-400">
              <span>{t.fact_count} facts</span>
              <span>{t.conversation_count} convs</span>
              {t.applicable_task_types && (
                <span>
                  {t.applicable_task_types.join(', ')}
                </span>
              )}
            </div>

            {t.tags && t.tags.length > 0 && (
              <div className="flex gap-1 mt-1">
                {t.tags.map((tag) => (
                  <span
                    key={tag}
                    className="text-xs bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            )}

            {/* Instantiate inline */}
            <div className="flex items-center gap-2 mt-2" onClick={(e) => e.stopPropagation()}>
              <input
                className="flex-1 border rounded px-2 py-1 text-xs"
                placeholder="target branch name..."
                value={instantiating === t.name ? instantiateTarget : ''}
                onFocus={() => setInstantiating(t.name)}
                onChange={(e) => {
                  setInstantiating(t.name);
                  setInstantiateTarget(e.target.value);
                }}
              />
              <button
                className="bg-green-500 text-white px-2 py-1 rounded text-xs hover:bg-green-600 disabled:opacity-50"
                onClick={() => handleInstantiate(t)}
                disabled={instantiating !== t.name || !instantiateTarget.trim()}
              >
                Instantiate
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
