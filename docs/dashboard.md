# Dashboard

Frontend dashboard for BranchedMind memory visualization. Read this when working on the UI.

## Tech Stack

| Component | Technology | Purpose |
|-----------|------------|----------|
| Framework | React + Vite | Fast dev server, HMR, TypeScript support |
| Node Graph | React Flow | Git-like branch tree visualization |
| Timeline | D3.js v7 | Chronological memory view, brush/zoom filters |
| State | Zustand | Lightweight state management, great TS support |
| Styling | Tailwind CSS | Fast iteration, dark mode built-in |
| Real-time | Polling (2s) | Simple, works everywhere (no SSE complexity) |

## Project Structure

```
/day1/
├── dashboard/                    # Frontend (root level, separate from Python)
│   ├── src/
│   │   ├── components/
│   │   │   ├── BranchTree.tsx       # React Flow node graph
│   │   │   ├── Timeline.tsx         # D3.js timeline view
│   │   │   ├── MergePanel.tsx       # Conflict resolution UI
│   │   │   ├── FactDetail.tsx       # Single fact viewer
│   │   │   └── SearchBar.tsx        # Fact search input
│   │   ├── hooks/
│   │   │   ├── useBranches.ts       # Branch data fetching
│   │   │   ├── useMemory.ts        # Fact/search queries
│   │   │   └── usePolling.ts       # Poll-based real-time updates
│   │   ├── stores/
│   │   │   └── branchStore.ts      # Zustand global state
│   │   ├── api/
│   │   │   └── client.ts           # REST API client
│   │   ├── types/
│   │   │   └── schema.ts          # TypeScript types (match backend OpenAPI)
│   │   ├── utils/
│   │   │   └── time.ts            # Date formatting utilities
│   │   └── App.tsx
│   ├── index.html
│   ├── package.json
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   └── vite.config.ts
├── src/                        # Python backend (separate repo)
└── docs/
```

## Key Components

### 1. BranchTree.tsx (React Flow)

Git-like branch visualization with nodes and edges.

```tsx
import ReactFlow, { Node, Edge, BackgroundVariant } from 'reactflow';
import 'reactflow/dist/style.css';

interface BranchNode extends Node {
  branchName: string;
  factCount: number;
  status: 'active' | 'merged' | 'archived';
  lastUpdate: string;
}

const BranchTree: React.FC = () => {
  const { branches, activeBranch, setActiveBranch } = useBranchStore();
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);

  // Transform branches into React Flow nodes
  useEffect(() => {
    const flowNodes: Node[] = branches.map((b, i) => ({
      id: b.branchName,
      position: { x: i * 200, y: 0 },
      data: { label: b.branchName, ...b }
    }));

    // Create edges based on parent relationships
    const flowEdges: Edge[] = branches
      .filter(b => b.parentBranch)
      .map(b => ({
        id: `${b.parentBranch}-${b.branchName}`,
        source: b.parentBranch!,
        target: b.branchName,
        type: 'smoothstep'
      }));

    setNodes(flowNodes);
    setEdges(flowEdges);
  }, [branches]);

  return (
    <div className="h-screen bg-gray-50 dark:bg-gray-900">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodeClick={(_, node) => setActiveBranch(node.id)}
        fitView
      >
        <BackgroundVariant color="#gray-100 dark:#gray-800" />
      </ReactFlow>
    </div>
  );
};
```

**Features:**
- Click node → filter timeline to that branch
- Double-click → set as active branch
- Color coding: main (blue), active (green), merged (gray)
- Zoom/pan built-in via React Flow

### 2. Timeline.tsx (D3.js)

Chronological view of facts, observations, and relations.

```tsx
import { scaleTime } from 'd3-time-scale';
import { brushX } from 'd3-brush';
import { select, axisBottom } from 'd3';

const Timeline: React.FC = () => {
  const svgRef = useRef<SVGSVGElement>(null);
  const { facts } = useMemoryStore();
  const [brushRange, setBrushRange] = useState<[Date, Date] | null>(null);

  useEffect(() => {
    const svg = select(svgRef.current);
    const width = 800;
    const height = 200;

    // Time scale (earliest to latest fact)
    const xScale = scaleTime()
      .domain([minDate, maxDate])
      .range([0, width]);

    // X-axis
    svg.append('g')
      .attr('transform', `translate(0,${height})`)
      .call(axisBottom(xScale));

    // Brush for filtering
    const brush = brushX()
      .extent([[0, width]])
      .on('end', (event) => {
        if (event.selection) setBrushRange(event.selection.map(xScale.invert));
      });

    svg.append('g')
      .call(brush);

    // Fact circles
    svg.selectAll('.fact')
      .data(facts)
      .join('circle')
      .attr('cx', d => xScale(new Date(d.created_at)))
      .attr('cy', 50)
      .attr('r', 6)
      .attr('fill', d => getCategoryColor(d.category));

  }, [facts]);

  return <svg ref={svgRef} className="w-full h-48" />;
};
```

**Features:**
- Brush filter → show only facts within time range
- Color code: fact (blue), observation (green), relation (purple)
- Hover → show fact detail tooltip
- Click → open FactDetail modal

### 3. MergePanel.tsx

UI for reviewing and resolving branch merge conflicts.

```tsx
interface Conflict {
  factId: string;
  sourceFact: string;      // Source branch fact
  targetFact: string;      // Target branch fact
  similarity: number;        // 0-1, how similar they are
}

const MergePanel: React.FC = () => {
  const { sourceBranch, targetBranch } = useBranchStore();
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [resolutions, setResolutions] = useState<Record<string, 'source' | 'target' | 'both'>>({});

  // Fetch diff when branches selected
  useEffect(() => {
    if (sourceBranch && targetBranch) {
      api.diffBranches(sourceBranch, targetBranch)
        .then(setConflicts);
    }
  }, [sourceBranch, targetBranch]);

  const handleResolve = (factId: string, choice: 'source' | 'target' | 'both') => {
    setResolutions({ ...resolutions, [factId]: choice });
  };

  const executeMerge = () => {
    const toKeep = Object.entries(resolutions)
      .filter(([_, choice]) => choice !== 'target')
      .map(([id]) => id);

    api.mergeBranches(sourceBranch, targetBranch, 'cherry_pick', toKeep);
  };

  return (
    <div className="p-6">
      <h2 className="text-xl font-bold">Merge: {sourceBranch} → {targetBranch}</h2>

      {conflicts.map(c => (
        <div key={c.factId} className="border rounded p-4 mb-4">
          <div className="flex justify-between">
            <div>
              <span className="text-red-600">Source:</span>
              <p>{c.sourceFact}</p>
            </div>
            <div>
              <span className="text-blue-600">Target:</span>
              <p>{c.targetFact}</p>
            </div>
          </div>

          <div className="flex gap-2 mt-2">
            <button
              onClick={() => handleResolve(c.factId, 'source')}
              className={resolutions[c.factId] === 'source' ? 'bg-green-500' : 'bg-gray-200'}
            >
              Keep Source
            </button>
            <button
              onClick={() => handleResolve(c.factId, 'target')}
              className={resolutions[c.factId] === 'target' ? 'bg-green-500' : 'bg-gray-200'}
            >
              Keep Target
            </button>
            <button
              onClick={() => handleResolve(c.factId, 'both')}
              className={resolutions[c.factId] === 'both' ? 'bg-green-500' : 'bg-gray-200'}
            >
              Keep Both
            </button>
          </div>
        </div>
      ))}

      <button
        onClick={executeMerge}
        className="w-full bg-blue-500 text-white py-2 rounded mt-4"
      >
        Execute Merge ({Object.values(resolutions).filter(r => r !== 'target').length} changes)
      </button>
    </div>
  );
};
```

## API Integration

### REST Client (src/api/client.ts)

```typescript
const API_BASE = 'http://localhost:8000/api/v1';

export const api = {
  // Branches
  listBranches: () =>
    fetch(`${API_BASE}/branches`).then(r => r.json()),

  diffBranches: (source: string, target: string) =>
    fetch(`${API_BASE}/branches/${source}/diff/${target}`).then(r => r.json()),

  // Facts
  searchFacts: (query: string, branch?: string) =>
    fetch(`${API_BASE}/facts/search?q=${encodeURIComponent(query)}&branch=${branch || 'main'}`)
      .then(r => r.json()),

  // Merge
  mergeBranches: (source: string, target: string, strategy: string, items: string[]) =>
    fetch(`${API_BASE}/branches/${source}/merge`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_branch: target, strategy, items })
    }).then(r => r.json()),
};
```

## State Management (Zustand)

```typescript
// src/stores/branchStore.ts
import { create } from 'zustand';

interface BranchStore {
  branches: Branch[];
  activeBranch: string;
  facts: Fact[];
  setActiveBranch: (branch: string) => void;
  setFacts: (facts: Fact[]) => void;
}

export const useBranchStore = create<BranchStore>((set) => ({
  branches: [],
  activeBranch: 'main',
  facts: [],

  setActiveBranch: (branch) => {
    set({ activeBranch: branch });
    // Fetch facts for new branch
    api.searchFacts('', branch).then(set);
  },

  setFacts: (facts) => set({ facts }),
}));
```

## Real-time Polling

```typescript
// src/hooks/usePolling.ts
import { useEffect } from 'react';
import { useBranchStore } from '../stores/branchStore';

export const usePolling = (interval: number = 2000) => {
  const { activeBranch, setFacts } = useBranchStore();
  const lastUpdate = useRef<Date>(new Date());

  useEffect(() => {
    const timer = setInterval(async () => {
      const response = await fetch(
        `/api/v1/updates?branch=${activeBranch}&since=${lastUpdate.current.toISOString()}`
      );
      const updates = await response.json();

      if (updates.length > 0) {
        setFacts(updates);  // Or merge with existing facts
        lastUpdate.current = new Date(updates[updates.length - 1].created_at);
      }
    }, interval);

    return () => clearInterval(timer);
  }, [activeBranch]);
};
```

## Build & Run

```bash
# Install dependencies
npm install

# Development server (HMR on :5173)
npm run dev

# Type checking
npm run type-check

# Linting
npm run lint

# Production build
npm run build
npm run preview
```

## Implementation Order

1. **Setup** (1h): Vite + React + TypeScript + Tailwind
2. **API Client** (1h): REST client with error handling
3. **BranchStore** (1h): Zustand store for branches/facts
4. **BranchTree** (2h): React Flow integration
5. **Timeline** (1h): D3.js basic timeline
6. **MergePanel** (1h): Conflict resolution UI

**Total: ~7 hours**
