import { useState } from 'react';
import { useTemplateStore } from '../stores/templateStore';
import { useBranchStore } from '../stores/branchStore';

interface Props {
  onCreated?: () => void;
}

export default function TemplateCreateWizard({ onCreated }: Props) {
  const { branches } = useBranchStore();
  const { createTemplate, loading, error } = useTemplateStore();

  const [name, setName] = useState('');
  const [sourceBranch, setSourceBranch] = useState('main');
  const [description, setDescription] = useState('');
  const [taskTypes, setTaskTypes] = useState('');
  const [tags, setTags] = useState('');
  const [success, setSuccess] = useState<string | null>(null);

  const handleCreate = async () => {
    if (!name.trim() || !sourceBranch) return;
    setSuccess(null);
    try {
      const template = await createTemplate({
        name: name.trim(),
        source_branch: sourceBranch,
        description: description || undefined,
        applicable_task_types: taskTypes
          ? taskTypes.split(',').map((t) => t.trim())
          : undefined,
        tags: tags ? tags.split(',').map((t) => t.trim()) : undefined,
      });
      setSuccess(`Created template "${template.name}" v${template.version}`);
      setName('');
      setDescription('');
      setTaskTypes('');
      setTags('');
      onCreated?.();
    } catch {
      // Error is handled by store
    }
  };

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4">
      <h3 className="text-sm font-semibold mb-3">Create Template</h3>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-3 py-2 rounded text-sm mb-2">
          {error}
        </div>
      )}
      {success && (
        <div className="bg-green-50 border border-green-200 text-green-700 px-3 py-2 rounded text-sm mb-2">
          {success}
        </div>
      )}

      <div className="space-y-2">
        <div>
          <label className="text-xs text-gray-500 block mb-0.5">Template Name *</label>
          <input
            className="w-full border rounded px-2 py-1 text-sm"
            placeholder="e.g. Python Best Practices"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>

        <div>
          <label className="text-xs text-gray-500 block mb-0.5">Source Branch *</label>
          <select
            className="w-full border rounded px-2 py-1 text-sm bg-white"
            value={sourceBranch}
            onChange={(e) => setSourceBranch(e.target.value)}
          >
            {branches
              .filter((b) => b.status === 'active')
              .map((b) => (
                <option key={b.branch_name} value={b.branch_name}>
                  {b.branch_name}
                </option>
              ))}
          </select>
        </div>

        <div>
          <label className="text-xs text-gray-500 block mb-0.5">Description</label>
          <textarea
            className="w-full border rounded px-2 py-1 text-sm"
            rows={2}
            placeholder="What this template contains..."
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>

        <div>
          <label className="text-xs text-gray-500 block mb-0.5">
            Applicable Task Types (comma-separated)
          </label>
          <input
            className="w-full border rounded px-2 py-1 text-sm"
            placeholder="bug_fix, feature, research"
            value={taskTypes}
            onChange={(e) => setTaskTypes(e.target.value)}
          />
        </div>

        <div>
          <label className="text-xs text-gray-500 block mb-0.5">
            Tags (comma-separated)
          </label>
          <input
            className="w-full border rounded px-2 py-1 text-sm"
            placeholder="python, patterns, auth"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
          />
        </div>

        <button
          className="w-full bg-blue-500 text-white px-3 py-2 rounded text-sm hover:bg-blue-600 disabled:opacity-50"
          onClick={handleCreate}
          disabled={loading || !name.trim()}
        >
          {loading ? 'Creating...' : 'Create Template'}
        </button>
      </div>
    </div>
  );
}
