# Analysis Engines

> SemanticDiffEngine, ScoringEngine — understanding and evaluating agent behavior.

## Design Rationale

Analysis engines answer two questions:
1. **How did two approaches differ?** (SemanticDiffEngine)
2. **How good was the result?** (ScoringEngine)

These are the feedback mechanisms that enable learning: by understanding what worked and what didn't, the system (and its users) can improve templates, refine prompts, and select better strategies.

---

## SemanticDiffEngine

**Source**: `src/day1/core/semantic_diff.py`

### Purpose
Compare two agent conversations semantically across three layers. Unlike text diff (which compares character sequences), semantic diff decomposes conversations into meaningful layers.

### Three-Layer Comparison

```
┌──────────────────────────────────────────────────────────┐
│              THREE-LAYER SEMANTIC DIFF                     │
│                                                            │
│  Layer 1: Action Trace                                     │
│  ┌──────────────────────────────────────────────────┐     │
│  │ WHAT the agent did                                │     │
│  │ Tool call sequence, arguments, order              │     │
│  │ Comparison: bigram ordering similarity, tool sets │     │
│  └──────────────────────────────────────────────────┘     │
│                                                            │
│  Layer 2: Reasoning Trace                                  │
│  ┌──────────────────────────────────────────────────┐     │
│  │ WHY it chose that path                            │     │
│  │ Assistant messages, thinking traces               │     │
│  │ Comparison: embedding cosine similarity per step  │     │
│  └──────────────────────────────────────────────────┘     │
│                                                            │
│  Layer 3: Outcome Summary                                  │
│  ┌──────────────────────────────────────────────────┐     │
│  │ DID IT WORK                                       │     │
│  │ Token usage, error count, tool call count          │     │
│  │ Comparison: efficiency metrics, error delta        │     │
│  └──────────────────────────────────────────────────┘     │
│                                                            │
│  Divergence Point Detection                                │
│  ┌──────────────────────────────────────────────────┐     │
│  │ WHERE they first diverged                         │     │
│  │ Shared message prefix length                       │     │
│  │ First differing role and content                   │     │
│  └──────────────────────────────────────────────────┘     │
│                                                            │
│  Summary Verdict                                           │
│  ┌──────────────────────────────────────────────────┐     │
│  │ equivalent │ similar │ mixed │ divergent          │     │
│  │ Based on action_match × reasoning_similarity      │     │
│  └──────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────┘
```

### Verdict Criteria

| Verdict | Condition |
|---|---|
| **equivalent** | action_match > 0.8 AND reasoning_similarity > 0.8 |
| **similar** | action_match > 0.5 AND reasoning_similarity > 0.5 |
| **divergent** | action_match < 0.3 |
| **mixed** | everything else |

### Action Trace Analysis

Extracts tool call sequences and compares them:
- Tool set overlap (tools only in A, only in B, common)
- Sequence ordering similarity (bigram Jaccard)
- Argument differences for shared tools
- Error count comparison

### Reasoning Trace Analysis

Uses embedding similarity between aligned reasoning segments:
- Extract assistant messages as reasoning chunks
- Embed each chunk
- Align by position and compute pairwise cosine similarity
- Overall similarity = average across pairs
- Divergence threshold: similarity < 0.7

### Entry Points

| Surface | Method |
|---|---|
| **API** | `GET /conversations/{a}/semantic-diff/{b}` |
| **API** | `GET /replays/{id}/semantic-diff` |
| **Dashboard** | SemanticDiffView component |

---

## ScoringEngine

**Source**: `src/day1/core/scoring_engine.py`

### Purpose
LLM-as-judge for conversation quality. **This is one of only two engines that call LLM.** Evaluates conversations on configurable dimensions and persists scores for tracking quality over time.

### Default Dimensions

| Dimension | Definition |
|---|---|
| `helpfulness` | Did the agent solve the user's problem? |
| `correctness` | Are statements, code, and tool calls technically correct? |
| `coherence` | Is the conversation logical and well-structured? |
| `efficiency` | Did the agent solve without unnecessary steps? |
| `safety` | Did the agent avoid harmful or insecure outputs? |
| `instruction_following` | Did the agent follow instructions precisely? |
| `creativity` | Did the agent show novel problem-solving? |
| `completeness` | Did the agent address all parts of the request? |

### Scoring Flow

```
score_conversation(conversation_id, dimensions)
       │
       ├──→ Load all messages for conversation
       │
       ├──→ Format messages for LLM judge
       │       │
       │       └──→ [ROLE] content (truncated to 2000 chars per message)
       │            [Tool calls: tool_name_1, tool_name_2]
       │            (total max 30000 chars)
       │
       ├──→ LLM available?
       │       │
       │       ├──→ Yes: Call LLM with evaluation prompt
       │       │       └──→ structured JSON response with scores
       │       │
       │       └──→ No: Return neutral scores (0.5) with warning
       │
       ├──→ Persist scores in scores table
       │
       └──→ Return score results
```

### Score Sources

Scores can come from multiple sources:
- **LLM judge** (`scorer="llm_judge"`) — automated evaluation
- **Verification engine** (`scorer="verification_engine"`) — fact quality scores
- **Human annotation** (`scorer="human"`) — manual scoring via API

### Aggregate Summaries

`get_score_summary()` computes per-dimension aggregates:
- Average, min, max, count across all scores for a target
- Useful for dashboards and trend analysis

### Entry Points

| Surface | Method |
|---|---|
| **API** | `POST /conversations/{id}/evaluate` → LLM-as-judge scoring |
| **API** | `POST /scores` → manual/external score creation |
| **API** | `GET /scores` → list scores |
| **API** | `GET /scores/summary/{type}/{id}` → aggregate summary |

---

## Discussion

1. **Scoring bias**: Different LLMs score differently. How to normalize across models?
2. **Score reliability**: LLM scores can be noisy. Should we require multiple rounds?
3. **Automated scoring triggers**: Should every conversation be automatically scored on completion?
4. **Diff visualization**: The semantic diff produces rich data. How best to visualize it in the dashboard?
5. **Cost management**: LLM-based scoring and semantic diff (embedding) have API costs. Budget controls?
6. **Custom dimensions**: Allow users to define project-specific scoring dimensions?
