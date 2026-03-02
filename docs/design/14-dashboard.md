# Dashboard

> React + Vite frontend for visualizing and managing Day1 memory.

## Architecture

**Tech Stack**: React + Vite + Tailwind CSS + Zustand + React Flow + D3.js

```
┌────────────────────────────────────────────────────────┐
│                    DASHBOARD                            │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Zustand Stores (State Management)                │  │
│  │  ├── branchStore: active branch, branch list      │  │
│  │  ├── searchStore: query, results, filters         │  │
│  │  ├── conversationStore: active conversation       │  │
│  │  └── analyticsStore: metrics, trends              │  │
│  └──────────────────────────┬───────────────────────┘  │
│                              │                          │
│  ┌──────────────────────────▼───────────────────────┐  │
│  │  Components                                       │  │
│  │                                                    │  │
│  │  ┌────────────┐  ┌──────────────┐  ┌──────────┐  │  │
│  │  │ BranchTree │  │ Conversation │  │ Timeline │  │  │
│  │  │ (React Flow)│  │ Thread       │  │ (D3.js)  │  │  │
│  │  └────────────┘  └──────────────┘  └──────────┘  │  │
│  │                                                    │  │
│  │  ┌────────────┐  ┌──────────────┐  ┌──────────┐  │  │
│  │  │ MergePanel │  │  SearchBar   │  │FactDetail│  │  │
│  │  └────────────┘  └──────────────┘  └──────────┘  │  │
│  │                                                    │  │
│  │  ┌────────────┐  ┌──────────────┐  ┌──────────┐  │  │
│  │  │ Analytics  │  │ ReplayList   │  │ Semantic │  │  │
│  │  │ Dashboard  │  │              │  │ DiffView │  │  │
│  │  └────────────┘  └──────────────┘  └──────────┘  │  │
│  │                                                    │  │
│  │  ┌────────────┐  ┌──────────────┐  ┌──────────┐  │  │
│  │  │ Template   │  │ Verification │  │ Handoff  │  │  │
│  │  │ List       │  │ Panel        │  │ Panel    │  │  │
│  │  └────────────┘  └──────────────┘  └──────────┘  │  │
│  └──────────────────────────────────────────────────┘  │
│                              │                          │
│  ┌──────────────────────────▼───────────────────────┐  │
│  │  REST API Client (fetch → /api/v1/*)              │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

## Component → API Mapping

| Component | API Endpoint | Purpose |
|---|---|---|
| BranchTree | `GET /branches/topology` | Hierarchical branch visualization |
| ConversationList | `GET /conversations` | List conversations on active branch |
| ConversationThread | `GET /conversations/{id}/messages` | Message history display |
| MergePanel | `POST /branches/{name}/merge` | Merge interface with strategy selection |
| Timeline | `GET /observations/timeline` | Chronological observation view |
| SearchBar | `GET /facts/search` | Hybrid search with results display |
| FactDetail | `GET /facts/{id}`, `GET /facts/{id}/verification` | Fact details and verification status |
| ReplayList | `GET /replays` | List of conversation replays |
| SemanticDiffView | `GET /conversations/{a}/semantic-diff/{b}` | Three-layer diff visualization |
| AnalyticsDashboard | `GET /analytics/overview`, `GET /analytics/trends` | Metrics and charts |
| TemplateList | `GET /templates` | Template registry |
| VerificationPanel | `GET /verification/summary/{branch}` | Branch verification status |
| HandoffPanel | `GET /handoffs` | Handoff records |
| BundlePanel | `GET /bundles` | Knowledge bundles |

## Visualization

### Branch Tree (React Flow)
Interactive tree visualization showing branch hierarchy, status (active/merged/archived), and relationship lines. Supports zoom, pan, and click-to-select.

### Timeline (D3.js)
Chronological view of facts and observations on a branch. Time axis with markers for key events (session start/end, task milestones).

### Analytics Charts
Time-series charts for messages, facts, conversations over time. Consolidation yield rate tracking.

## Discussion

1. **Real-time updates**: Currently polling-based. WebSocket/SSE for live dashboard updates?
2. **Mobile support**: Currently desktop-optimized. Responsive design needed?
3. **Dark mode**: Tailwind CSS supports it natively. Priority?
4. **Export**: Dashboard data export (CSV, JSON) for external analysis?
