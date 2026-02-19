# Dashboard

Frontend dashboard for Day1 memory visualization. Read this when working on the UI.

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

UI for reviewing MO native diff results and executing merges.

**MO Native Diff**: Uses `DATA BRANCH DIFF source AGAINST target` to get row-level changes (INSERT/UPDATE/DELETE). The API endpoint is `GET /api/v1/branches/{name}/diff/native`.

**Merge Strategies**:
- **native**: Uses MO `DATA BRANCH MERGE` with conflict handling (SKIP = keep target, ACCEPT = use source)
- **auto**: Application-layer LLM-assisted merge with conflict resolution
- **cherry_pick**: Select specific items to merge
- **squash**: Merge all as a single summarized fact

```tsx
interface DiffRow {
  table: string;           // "facts" | "relations" | "observations"
  flag: string;            // "INSERT" | "UPDATE" | "DELETE" (from MO diff)
  [column: string]: any;   // Row data columns
}

const MergePanel: React.FC = () => {
  const { activeBranch, diffs, fetchDiff, mergeBranch } = useBranchStore();
  const [strategy, setStrategy] = useState('native');
  const [conflict, setConflict] = useState('skip');  // skip | accept
  const [targetBranch, setTargetBranch] = useState('main');

  // Fetch MO native diff
  useEffect(() => {
    if (activeBranch !== 'main') {
      fetchDiff(activeBranch, targetBranch);
    }
  }, [activeBranch, targetBranch]);

  const executeMerge = () => {
    mergeBranch(activeBranch, targetBranch, strategy, conflict);
  };

  return (
    <div className="bg-gray-800 rounded-lg p-4">
      <h3>Merge: {activeBranch} → {targetBranch}</h3>

      {/* Diff table: table | flag | columns */}
      <table>
        <thead>
          <tr><th>Table</th><th>Flag</th><th>ID</th><th>Details</th></tr>
        </thead>
        <tbody>
          {diffs.map((d, i) => (
            <tr key={i}>
              <td>{d.table}</td>
              <td className={d.flag === 'INSERT' ? 'text-green' : d.flag === 'DELETE' ? 'text-red' : 'text-yellow'}>
                {d.flag}
              </td>
              <td>{d.id}</td>
              <td>{d.fact_text || d.summary || ''}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Strategy selector */}
      <select value={strategy} onChange={e => setStrategy(e.target.value)}>
        <option value="native">Native (MO DATA BRANCH MERGE)</option>
        <option value="auto">Auto (LLM-assisted)</option>
        <option value="cherry_pick">Cherry Pick</option>
        <option value="squash">Squash</option>
      </select>

      {/* Conflict strategy (native only) */}
      {strategy === 'native' && (
        <select value={conflict} onChange={e => setConflict(e.target.value)}>
          <option value="skip">Skip Conflicts (keep target)</option>
          <option value="accept">Accept All (use source)</option>
        </select>
      )}

      <button onClick={executeMerge}>Execute Merge</button>
    </div>
  );
};
```

## API Integration

### REST Client (src/api/client.ts)

Uses relative paths (`/api/v1/...`) proxied via Vite dev server to `http://localhost:8000`.

```typescript
const API = '/api/v1';

export const api = {
  // Branches
  listBranches: () =>
    fetch(`${API}/branches`).then(r => r.json()),

  createBranch: (name: string, parent = 'main', description?: string) =>
    fetch(`${API}/branches`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ branch_name: name, parent_branch: parent, description }),
    }).then(r => r.json()),

  // MO Native Diff (DATA BRANCH DIFF)
  diffNative: (source: string, target = 'main') =>
    fetch(`${API}/branches/${source}/diff/native?target_branch=${target}`).then(r => r.json()),

  diffNativeCount: (source: string, target = 'main') =>
    fetch(`${API}/branches/${source}/diff/native/count?target_branch=${target}`).then(r => r.json()),

  // Merge (supports native/auto/cherry_pick/squash strategies)
  mergeBranch: (source: string, target: string, strategy: string, conflict?: string) =>
    fetch(`${API}/branches/${source}/merge`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_branch: target, strategy, conflict }),
    }).then(r => r.json()),

  // Facts
  searchFacts: (query: string, branch = 'main') =>
    fetch(`${API}/facts/search?query=${encodeURIComponent(query)}&branch=${branch}`).then(r => r.json()),

  // Time Travel (MO native: AS OF TIMESTAMP)
  timeTravel: (timestamp: string, branch = 'main') =>
    fetch(`${API}/snapshots/time-travel?timestamp=${encodeURIComponent(timestamp)}&branch=${branch}`).then(r => r.json()),

  // Archive branch (drops branch tables)
  archiveBranch: (name: string) =>
    fetch(`${API}/branches/${name}`, { method: 'DELETE' }).then(r => r.json()),
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
  diffs: DiffRow[];
  timeTravelFacts: Fact[];
  timeTravelTs: string | null;
  loading: boolean;
  error: string | null;

  setActiveBranch: (branch: string) => void;
  fetchBranches: () => Promise<void>;
  searchFacts: (query: string) => Promise<void>;
  fetchDiff: (source: string, target?: string) => Promise<void>;
  mergeBranch: (source: string, target: string, strategy: string, conflict?: string) => Promise<void>;
  timeTravel: (timestamp: string) => Promise<void>;
  clearError: () => void;
}
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
