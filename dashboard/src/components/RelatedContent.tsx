import type { Fact } from '../types/schema';

export default function RelatedContent({ facts }: { facts: Fact[] }) {
  if (facts.length === 0) {
    return (
      <div className="text-xs text-gray-500">
        No related facts found yet.
      </div>
    );
  }

  return (
    <div className="space-y-2 max-h-56 overflow-y-auto">
      {facts.map((fact) => (
        <div key={fact.id} className="rounded-md border border-gray-200 bg-gray-50 p-2">
          <div className="text-xs text-gray-800">{fact.fact_text}</div>
          <div className="mt-1 text-[11px] text-gray-500 font-mono">
            {fact.id.slice(0, 8)} · {fact.branch_name}
          </div>
        </div>
      ))}
    </div>
  );
}

