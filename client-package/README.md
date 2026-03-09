# Day1 Client — Memory + Skill Evolution

## Server Info

| Item | Value |
|------|-------|
| **API Endpoint** | `http://localhost:9821` (or `http://<DAY1_SERVER>:9821`) |
| **Health Check** | `GET /health` |
| **MCP Endpoint** | `http://localhost:9821/mcp` (streamable HTTP) |
| **MCP Tools** | 28 tools (21 memory/graph + 7 skill evolution) |

## Quick Start (5 minutes)

### 1. Copy this directory to your machine

```bash
scp -r momo@<DAY1_SERVER>:~/src/day1/client-package ./day1-client
cd day1-client
```

### 2. Install dependencies

```bash
# Option A: pip
pip install -r requirements.txt

# Option B: uv (faster)
uv pip install -r requirements.txt

# Option C: Minimal (only Day1 tracer, no agent framework)
pip install httpx
```

### 3. Verify connection

```bash
curl http://localhost:9821/health
# {"status":"ok","version":"2.0.0"}
```

### 4. Run examples

```bash
# LiteLLM ReAct agent (default: DeepSeek V3 via magikcloud)
python litellm_react_agent.py --day1-url http://localhost:9821

# LangChain ReAct agent
python langchain_react_agent.py --day1-url http://localhost:9821
```

---

## Python SDK Usage

### Memory Operations

```python
from day1_tracer import Day1Tracer

client = Day1Tracer("http://localhost:9821")

# Write a memory
result = client.memory_write(
    text="Discovered auth bug in login.py",
    context="Missing null check on user object causes 500",
    category="bug_fix",
)
memory_id = result["result"]["id"]

# Search memories
results = client.memory_search("auth bug", limit=5)
for mem in results["result"]["results"]:
    print(f"  {mem['text']} (score: {mem['score']:.2f})")

# Create relations (knowledge graph)
client.memory_relate(memory_id_1, memory_id_2, "related_to", "Same auth module")

# Graph traversal
graph = client.memory_graph(memory_id_1, depth=2)
print(f"Nodes: {len(graph['nodes'])}, Edges: {len(graph['edges'])}")
```

### Trace Capture

```python
client = Day1Tracer("http://localhost:9821")

# Record a trace from your own agent
client.start("Solve a coding problem")
client.add_user_message("Fix the bug in auth.py")
client.add_tool_use("read_file", {"path": "auth.py"}, "def login(): ...")
client.add_assistant_message("Fixed!")
trace = client.finish()
```

### Compare two runs

```python
comparison = client.compare(trace_a_id, trace_b_id)
print(f"Verdict: {comparison['verdict']}")
```

### Full evolution loop

```python
# 1. Register a skill
skill = client.register_skill("my-skill", "# my-skill\n\n## Instructions\n...")

# 2. Run your agent, store traces, compare them

# 3. Evolve the skill
evo = client.evolve_skill("my-skill", comparison_ids=[comp_id])

# 4. Promote the winner
client.promote_skill(evo["winner_id"])

# 5. View history
history = client.get_evolution_history("my-skill")
```

---

## REST API Reference

### Memory CRUD

```bash
SERVER=http://localhost:9821

# Write memory
curl -X POST $SERVER/api/v1/ingest/mcp \
  -H 'Content-Type: application/json' \
  -d '{"tool": "memory_write", "arguments": {"text": "Important finding", "category": "pattern"}}'

# Search memories
curl -X POST $SERVER/api/v1/ingest/mcp \
  -H 'Content-Type: application/json' \
  -d '{"tool": "memory_search", "arguments": {"query": "auth bug"}}'

# Get memory by ID
curl $SERVER/api/v1/memories/{memory_id}

# Update memory
curl -X PATCH $SERVER/api/v1/memories/{memory_id} \
  -H 'Content-Type: application/json' \
  -d '{"text": "Updated finding", "category": "decision"}'

# Archive (soft-delete) memory
curl -X DELETE $SERVER/api/v1/memories/{memory_id}

# Batch write
curl -X POST $SERVER/api/v1/memories/batch \
  -H 'Content-Type: application/json' \
  -d '{"items": [{"text": "mem1"}, {"text": "mem2"}], "branch": "main"}'

# Batch archive
curl -X DELETE $SERVER/api/v1/memories/batch \
  -H 'Content-Type: application/json' \
  -d '{"memory_ids": ["id1", "id2"]}'
```

### Knowledge Graph

```bash
# Create relation
curl -X POST $SERVER/api/v1/memories/{memory_id}/relations \
  -H 'Content-Type: application/json' \
  -d '{"target_id": "other-id", "relation_type": "related_to"}'

# List relations
curl $SERVER/api/v1/memories/{memory_id}/relations

# Graph traversal
curl "$SERVER/api/v1/memories/{memory_id}/graph?depth=2&limit=50"

# Delete relation
curl -X DELETE $SERVER/api/v1/relations/{relation_id}
```

### Traces & Skills

```bash
# Store a trace
curl -X POST $SERVER/api/v1/traces \
  -H 'Content-Type: application/json' \
  -d '{"steps": [...], "trace_type": "external", "session_id": "my-agent"}'

# Compare traces
curl -X POST $SERVER/api/v1/traces/{a}/compare/{b}

# Register skill
curl -X POST $SERVER/api/v1/skills \
  -H 'Content-Type: application/json' \
  -d '{"skill_name": "my-skill", "content": "# Instructions..."}'

# Evolve skill
curl -X POST $SERVER/api/v1/skills/my-skill/evolve \
  -d '{"strategy": "single_mutation"}'
```

---

## MCP Client Config (Claude Code)

Add to your Claude Code MCP settings:

```json
{
  "mcpServers": {
    "day1": {
      "type": "http",
      "url": "http://localhost:9821/mcp"
    }
  }
}
```

28 MCP tools available:

**Memory (11):** `memory_write`, `memory_search`, `memory_get`, `memory_update`, `memory_archive`, `memory_write_batch`, `memory_archive_batch`, `memory_timeline`, `memory_merge`, `memory_count`, `memory_restore`

**Branch (5):** `memory_branch_create`, `memory_branch_switch`, `memory_branch_list`, `memory_branch_archive`, `memory_branch_delete`

**Snapshot (2):** `memory_snapshot`, `memory_snapshot_list`

**Graph (3):** `memory_relate`, `memory_relations`, `memory_graph`

**Skill (7):** `skill_trace_extract`, `skill_trace_store`, `skill_compare`, `skill_register`, `skill_list`, `skill_evolve`, `skill_evolution_history`
