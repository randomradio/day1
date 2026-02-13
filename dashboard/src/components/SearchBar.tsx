import { useState } from 'react';
import { useBranchStore } from '../stores/branchStore';

export default function SearchBar() {
  const { searchFacts, searchQuery, setSearchQuery, activeBranch, loading } =
    useBranchStore();
  const [input, setInput] = useState(searchQuery);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setSearchQuery(input);
    searchFacts(input);
  };

  return (
    <form onSubmit={handleSearch} className="flex items-center gap-2">
      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder={`Search facts on ${activeBranch}...`}
        className="flex-1 bg-gray-700 text-gray-200 px-3 py-2 rounded-lg border border-gray-600 focus:border-blue-500 focus:outline-none text-sm"
      />
      <button
        type="submit"
        disabled={loading}
        className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-500 text-sm disabled:opacity-50"
      >
        {loading ? '...' : 'Search'}
      </button>
    </form>
  );
}
