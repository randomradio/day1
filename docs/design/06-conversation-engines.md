# Conversation Engines

> ConversationEngine, CherryPick, ReplayEngine — managing episodic memory (what happened when).

## Design Rationale

Conversations are the **episodic memory** of the system — complete records of what happened, in what order, with full context. Unlike facts (which are distilled knowledge), conversations preserve the original reasoning chain, tool call sequence, and decision process.

This is valuable for:
- **Replay**: Re-running a conversation with different parameters to compare approaches
- **Semantic diff**: Understanding how two approaches differ at the action, reasoning, and outcome levels
- **Handoff**: Giving a new agent full context of what the previous agent did
- **Audit**: Understanding why a particular decision was made

```
┌──────────────────────────────────────────────────────┐
│                CONVERSATION LIFECYCLE                  │
│                                                        │
│  SessionStart Hook                                     │
│       │                                                │
│       ▼                                                │
│  create_conversation()                                 │
│       │                                                │
│       ├──→ UserPrompt Hook ──→ write_message(user)    │
│       │                                                │
│       ├──→ AssistantResponse ──→ write_message(asst)  │
│       │                                                │
│       ├──→ PostToolUse ──→ write_message(tool_result)  │
│       │                                                │
│       ├──→ [Fork] ──→ fork_conversation() ──→ new conv │
│       │                                                │
│       └──→ SessionEnd ──→ close_conversation()         │
│                                                        │
│  Later:                                                │
│       ├──→ replay() ──→ fork + re-execute              │
│       ├──→ cherry_pick() ──→ extract to another branch│
│       └──→ semantic_diff() ──→ compare two runs        │
└──────────────────────────────────────────────────────┘
```

---

## ConversationEngine

**Source**: `src/day1/core/conversation_engine.py`

### Purpose
Thread-level management of chat history. Each session typically has one conversation, but forks create additional conversations.

### Core Operations

| Method | Purpose |
|---|---|
| `create_conversation()` | Start new conversation thread |
| `get_conversation()` | Retrieve conversation metadata |
| `get_conversation_by_session()` | Find conversation for a session |
| `list_conversations()` | List with filters (session, agent, task, branch, status) |
| `fork_conversation()` | Create fork at specific message (for replay or branching) |
| `close_conversation()` | Mark completed with final stats |

### Fork Model

Forking creates a new conversation that shares the message prefix up to the fork point:

```
Original:  msg1 → msg2 → msg3 → msg4 → msg5
                           │
Fork at msg3:              └──→ new_msg4 → new_msg5 → new_msg6
```

The fork records `parent_conversation_id` and `fork_point_message_id` for traceability.

### Entry Points

| Surface | Trigger | Method |
|---|---|---|
| **Hook** | SessionStart | `create_conversation()` |
| **Hook** | SessionEnd | `close_conversation()` |
| **API** | `POST /conversations` | `create_conversation()` |
| **API** | `POST /conversations/{id}/fork` | `fork_conversation()` |
| **API** | `POST /conversations/{id}/complete` | `close_conversation()` |

---

## CherryPick (ConversationCherryPick)

**Source**: `src/day1/core/conversation_cherry_pick.py`

### Purpose
Selectively extract messages from one conversation/branch and copy them to another. Useful for taking specific insights from an experimental branch without merging everything.

### Operation

```
Source conversation (branch: experiment/approach-a):
    msg1: "Let me try approach A..."
    msg2: "Found that X works because..."   ← cherry-pick this
    msg3: "Error: Y doesn't work..."
    msg4: "Fixed by doing Z..."              ← cherry-pick this

Target conversation (branch: main):
    ... existing messages ...
    msg_new: "Found that X works because..."  (cherry-picked)
    msg_new: "Fixed by doing Z..."            (cherry-picked)
```

### Entry Points

| Surface | Method |
|---|---|
| **API** | `POST /conversations/{id}/cherry-pick` |
| **CLI** | Conversation cherry-pick command |

---

## ReplayEngine

**Source**: `src/day1/core/replay_engine.py`

### Purpose
Fork a conversation at any message point and prepare it for re-execution with different parameters. This enables systematic comparison of different approaches to the same task.

### Replay Flow

```
┌────────────────────────────────────────────────────┐
│                    REPLAY FLOW                      │
│                                                      │
│  1. Select conversation + fork point                │
│       │                                              │
│       ▼                                              │
│  2. Fork conversation at message N                  │
│       │                                              │
│       ▼                                              │
│  3. Configure replay parameters:                    │
│     ├── Different model (e.g., GPT-4 vs Claude)    │
│     ├── Different temperature                       │
│     ├── Tool filters (allow/deny specific tools)   │
│     └── Extra context injection                     │
│       │                                              │
│       ▼                                              │
│  4. Prepare context (messages up to fork point)     │
│       │                                              │
│       ▼                                              │
│  5. Agent re-executes from fork point              │
│       │                                              │
│       ▼                                              │
│  6. Compare: semantic_diff(original, replay)        │
│       │                                              │
│       ▼                                              │
│  7. Score: ScoringEngine.score_conversation()       │
└────────────────────────────────────────────────────┘
```

### Core Operations

| Method | Purpose |
|---|---|
| `create_replay()` | Fork conversation and configure replay parameters |
| `get_replay_context()` | Get message history up to fork point (for LLM input) |
| `complete_replay()` | Mark replay finished |
| `diff_replay()` | Row-level diff between original and replay |

### Entry Points

| Surface | Method |
|---|---|
| **API** | `POST /conversations/{id}/replay` |
| **API** | `GET /replays/{id}/context` |
| **API** | `GET /replays/{id}/semantic-diff` |
| **API** | `POST /replays/{id}/complete` |

---

## Discussion

1. **Conversation compaction**: Long conversations (1000+ messages) are expensive to store and retrieve. Should we auto-compact old conversations?
2. **Cross-conversation search**: Searching across all conversations on a branch requires scanning all messages. Index optimization?
3. **Replay automation**: Currently replay requires manual re-execution. Can we automate the replay-compare-score pipeline?
4. **Fork explosion**: Each replay creates a new conversation. Should we limit fork depth?
5. **Privacy**: Conversation content may contain sensitive information. How to handle data sanitization for exports?
