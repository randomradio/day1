import { useBranchStore } from '../stores/branchStore';
import type { Fact } from '../types/schema';
import CrossReferencePanel from './CrossReferencePanel';

function FactCard({ fact }: { fact: Fact }) {
  return (
    <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
      <div className="flex items-start justify-between gap-2 mb-1">
        <span className="text-sm text-gray-800 leading-snug">
          {fact.fact_text}
        </span>
        {fact.score !== undefined && (
          <span className="text-xs text-blue-600 font-mono whitespace-nowrap">
            {fact.score.toFixed(3)}
          </span>
        )}
      </div>
      <div className="flex items-center gap-3 text-xs text-gray-500 mt-2">
        {fact.category && (
          <span className="bg-gray-200 px-2 py-0.5 rounded text-gray-700">{fact.category}</span>
        )}
        <span>confidence: {fact.confidence}</span>
        <span>{fact.status}</span>
        {fact.created_at && (
          <span>{new Date(fact.created_at).toLocaleString()}</span>
        )}
      </div>
      <div className="text-xs text-gray-400 mt-1 font-mono">
        {fact.id.slice(0, 8)}
        {fact.branch_name !== 'main' && ` · ${fact.branch_name}`}
      </div>
    </div>
  );
}

export default function FactDetail() {
  const { facts, timeTravelResults, timeTravelTs, activeBranch } = useBranchStore();

  const displayFacts = timeTravelTs ? timeTravelResults : facts;
  const title = timeTravelTs
    ? `Time Travel @ ${timeTravelTs}`
    : `${facts.length} results`;
  const focusFact = displayFacts[0];

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-lg p-4 border border-gray-200 shadow-sm">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-700">{title}</h3>
        </div>
        {displayFacts.length === 0 ? (
          <p className="text-sm text-gray-500">
            No facts found. Try searching or selecting a branch.
          </p>
        ) : (
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {displayFacts.map((f) => (
              <FactCard key={f.id} fact={f} />
            ))}
          </div>
        )}
      </div>
      <CrossReferencePanel factId={focusFact?.id} branch={activeBranch} />
    </div>
  );
}
