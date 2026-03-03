import { useState } from 'react';
import { useStore } from '../stores/store';

const CATEGORIES = ['', 'pattern', 'decision', 'bug_fix', 'session', 'conversation', 'architecture'];

export default function SearchBar() {
  const { search, clearSearch, searchQuery, loading } = useStore();
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('');

  const handleSearch = () => {
    const q = query.trim();
    if (!q) {
      clearSearch();
      return;
    }
    search(q, category || undefined);
  };

  return (
    <div className="flex gap-2">
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
        placeholder="Search memories..."
        className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
      />
      <select
        value={category}
        onChange={(e) => setCategory(e.target.value)}
        className="border border-gray-300 rounded-lg px-2 py-2 text-sm bg-white"
      >
        <option value="">All categories</option>
        {CATEGORIES.filter(Boolean).map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>
      <button
        onClick={handleSearch}
        disabled={loading}
        className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50"
      >
        Search
      </button>
      {searchQuery && (
        <button
          onClick={() => {
            setQuery('');
            clearSearch();
          }}
          className="text-sm text-gray-500 hover:text-gray-700 px-2"
        >
          Clear
        </button>
      )}
    </div>
  );
}
