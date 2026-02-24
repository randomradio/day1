import { useState } from 'react';
import { useBranchStore } from '../stores/branchStore';
import { useVisiblePolling } from '../hooks/usePolling';

export default function SearchBar() {
  const { searchFacts, searchQuery, refreshFacts, setSearchQuery, activeBranch, loading, pollingEnabled } =
    useBranchStore();
  const [input, setInput] = useState(searchQuery);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setSearchQuery(input);
    searchFacts(input);
  };

  // Poll search results every 10 seconds (slower than conversations since searches are more expensive)
  useVisiblePolling(refreshFacts, 10000, pollingEnabled && searchQuery !== '');

  return (
    <form onSubmit={handleSearch} className="flex items-center gap-2">
      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder={`Search facts on ${activeBranch}...`}
        className="flex-1 bg-white text-gray-900 px-3 py-2 rounded-lg border border-gray-300 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none text-sm shadow-sm"
      />
      <button
        type="submit"
        disabled={loading}
        className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 text-sm disabled:opacity-50 shadow-sm"
      >
        {loading ? '...' : 'Search'}
      </button>
    </form>
  );
}
