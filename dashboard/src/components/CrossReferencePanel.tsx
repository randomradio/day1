import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { FactRelatedResponse } from '../types/schema';
import RelatedContent from './RelatedContent';

export default function CrossReferencePanel({
  factId,
  branch,
}: {
  factId?: string;
  branch?: string;
}) {
  const [data, setData] = useState<FactRelatedResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!factId) {
      setData(null);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    api.getFactRelated(factId, branch, 12)
      .then((resp) => {
        if (!cancelled) setData(resp);
      })
      .catch((e) => {
        if (!cancelled) setError((e as Error).message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [factId, branch]);

  return (
    <div className="bg-white rounded-lg p-4 border border-gray-200 shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-700">Cross References</h3>
        {factId && <span className="text-[11px] text-gray-400 font-mono">{factId.slice(0, 8)}</span>}
      </div>

      {!factId && (
        <div className="text-xs text-gray-500">Search or time-travel results will show related graph edges here.</div>
      )}

      {factId && loading && <div className="text-xs text-gray-500">Loading related content…</div>}
      {factId && error && <div className="text-xs text-red-600">{error}</div>}

      {factId && !loading && !error && data && (
        <div className="space-y-3">
          <div className="text-xs text-gray-600">
            {data.count} relations · {data.entities.length} entities
          </div>
          <div className="flex flex-wrap gap-1">
            {data.entities.slice(0, 8).map((entity) => (
              <span key={entity} className="px-2 py-0.5 rounded-full bg-blue-50 border border-blue-200 text-[11px] text-blue-700">
                {entity}
              </span>
            ))}
          </div>
          <RelatedContent facts={data.related_facts} />
        </div>
      )}
    </div>
  );
}

