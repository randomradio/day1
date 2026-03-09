#!/usr/bin/env python3
"""LangChain ReAct Agent + Day1 Skill Evolution — Full Loop Demo.

Demonstrates:
  1. LangChain ReAct agent runs a task -> trace captured in Day1
  2. Same task re-run with different temperature -> second trace
  3. Day1 compares both traces (9 dimensions)
  4. Register a SKILL.md -> evolve it from comparison insights

Requirements:
  pip install langchain langchain-openai langgraph
  Day1 server running at http://10.112.1.28:8321

Usage:
  # Default (magikcloud deepseek-v3)
  python examples/langchain_react_agent.py

  # Custom model
  python examples/langchain_react_agent.py --model gpt-4o-mini --api-key sk-...
"""

from __future__ import annotations

import argparse
import json
import os
import time

# LangChain imports
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

# Day1 tracer (no day1 package dependency — pure HTTP)
from day1_tracer import Day1Tracer

DAY1_URL = os.getenv("DAY1_URL", "http://10.112.1.28:8321")

# Default LLM config — magikcloud DeepSeek V3
DEFAULT_API_BASE = "https://api.magikcloud.cn/v1"
DEFAULT_API_KEY = "magik-2ab00f8ae98f4bab8f9d1876b71c42d6"
DEFAULT_MODEL = "ep-deepseek-v3-2-104138"


# ── Tools for the agent ──────────────────────────────────────────────────

@tool
def search_web(query: str) -> str:
    """Search the web for information (simulated)."""
    fake_results = {
        "python asyncio": "asyncio is Python's built-in library for async/await. Use asyncio.run() to start.",
        "fastapi tutorial": "FastAPI is a modern web framework. Define routes with @app.get() decorators.",
        "sqlalchemy async": "Use create_async_engine() and AsyncSession for async SQLAlchemy 2.0.",
    }
    for key, value in fake_results.items():
        if key in query.lower():
            return value
    return f"Search results for '{query}': No specific results found. Try a more specific query."


@tool
def calculate(expression: str) -> str:
    """Evaluate a math expression safely."""
    try:
        allowed = set("0123456789+-*/.() ")
        if all(c in allowed for c in expression):
            return str(eval(expression))  # noqa: S307 — demo only
        return "Error: only numeric expressions allowed"
    except Exception as e:
        return f"Error: {e}"


@tool
def read_file(path: str) -> str:
    """Read a file's contents (simulated)."""
    files = {
        "config.py": "DATABASE_URL = 'sqlite:///app.db'\nDEBUG = True\nSECRET_KEY = 'change-me'",
        "main.py": "from fastapi import FastAPI\napp = FastAPI()\n\n@app.get('/')\ndef root():\n    return {'hello': 'world'}",
    }
    return files.get(path, f"File not found: {path}")


TOOLS = [search_web, calculate, read_file]


# ── Traced agent runner ──────────────────────────────────────────────────

def run_agent_with_trace(
    task: str,
    tracer: Day1Tracer,
    model_name: str = DEFAULT_MODEL,
    temperature: float = 0.0,
    trace_type: str = "original",
    parent_trace_id: str | None = None,
    api_base: str = DEFAULT_API_BASE,
    api_key: str = DEFAULT_API_KEY,
) -> dict:
    """Run a LangChain ReAct agent and capture the full trace in Day1."""
    llm = ChatOpenAI(
        model=model_name,
        temperature=temperature,
        base_url=api_base,
        api_key=api_key,
    )
    agent = create_react_agent(llm, TOOLS)

    tracer.start(task, model=model_name, temperature=temperature, framework="langchain")
    tracer.add_user_message(task)

    # Run the agent
    result = agent.invoke({"messages": [HumanMessage(content=task)]})

    # Extract trace from LangGraph messages
    for msg in result["messages"]:
        msg_type = type(msg).__name__

        if msg_type == "AIMessage":
            # Tool calls
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tracer.add_assistant_message(
                        f"Calling tool: {tc['name']}({json.dumps(tc['args'])})"
                    )
            elif msg.content:
                tracer.add_assistant_message(str(msg.content))

        elif msg_type == "ToolMessage":
            tracer.add_tool_use(
                tool_name=msg.name,
                tool_input=msg.tool_call_id,
                tool_output=str(msg.content)[:2000],
            )

    # Store trace in Day1
    trace = tracer.finish(
        trace_type=trace_type,
        parent_trace_id=parent_trace_id,
    )

    final_msg = result["messages"][-1].content if result["messages"] else ""
    print(f"  Agent answer: {str(final_msg)[:200]}")
    return trace


# ── Main demo ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="LangChain ReAct Agent + Day1")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model name")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="API base URL")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="API key")
    parser.add_argument("--day1-url", default=DAY1_URL, help="Day1 server URL")
    args = parser.parse_args()

    print("=" * 60)
    print("LangChain ReAct Agent + Day1 Skill Evolution Demo")
    print(f"  Model: {args.model}")
    print(f"  Day1:  {args.day1_url}")
    print("=" * 60)

    tracer = Day1Tracer(args.day1_url, session_id=f"langchain-demo-{int(time.time())}")

    # Verify Day1 is running
    try:
        health = tracer.health()
        print(f"\n[ok] Day1 server: {health}")
    except Exception as e:
        print(f"\n[err] Day1 server not reachable at {args.day1_url}: {e}")
        print("  Start Day1: PYTHONPATH=src .venv/bin/uvicorn day1.api.app:app --port 8321")
        return

    task = "Look up how Python asyncio works, then calculate 365 * 24 to find hours in a year, and finally read config.py to check the database settings."

    # ── Step 1: Run agent (original trace) ───────────────────────────────
    print(f"\n--- Step 1: Run agent (original) ---")
    print(f"  Task: {task[:80]}...")
    trace_a = run_agent_with_trace(
        task, tracer,
        model_name=args.model,
        temperature=0.0,
        trace_type="original",
        api_base=args.api_base,
        api_key=args.api_key,
    )
    trace_a_id = trace_a["id"]
    print(f"  Trace A stored: {trace_a_id}")
    print(f"  Summary: {trace_a.get('summary', {})}")

    # ── Step 2: Re-run with different temperature (replay) ───────────────
    print(f"\n--- Step 2: Re-run agent (variant, temp=0.7) ---")
    tracer2 = Day1Tracer(args.day1_url, session_id=f"langchain-replay-{int(time.time())}")
    trace_b = run_agent_with_trace(
        task,
        tracer2,
        model_name=args.model,
        temperature=0.7,
        trace_type="variant",
        parent_trace_id=trace_a_id,
        api_base=args.api_base,
        api_key=args.api_key,
    )
    trace_b_id = trace_b["id"]
    print(f"  Trace B stored: {trace_b_id}")
    print(f"  Summary: {trace_b.get('summary', {})}")

    # ── Step 3: Compare traces ───────────────────────────────────────────
    print(f"\n--- Step 3: Compare traces (9 dimensions) ---")
    comparison = tracer.compare(trace_a_id, trace_b_id)
    print(f"  Verdict: {comparison.get('verdict')}")
    print(f"  Scores:")
    for dim, score in sorted(comparison.get("dimension_scores", {}).items()):
        bar = "█" * int(score * 20) + "░" * (20 - int(score * 20))
        label = "B better" if score > 0.6 else "A better" if score < 0.4 else "equal"
        print(f"    {dim:25s} {bar} {score:.2f}  ({label})")
    print(f"  Insights: {comparison.get('insights', [])}")

    # ── Step 4: Register a skill ─────────────────────────────────────────
    print(f"\n--- Step 4: Register SKILL.md ---")
    run_id = int(time.time())
    skill_name = f"research-and-compute-{run_id}"
    skill_content = f"""# {skill_name}

## Description
A skill for agents that need to research information, perform calculations, and inspect files.

## Instructions
1. Search for relevant information first
2. Perform any needed calculations
3. Read configuration or source files as needed
4. Synthesize findings into a clear answer

## Constraints
- Always verify search results before using them
- Show calculation steps
- Report any missing files gracefully
"""
    skill = tracer.register_skill(skill_name, skill_content)
    print(f"  Skill registered: {skill.get('skill_name')} v{skill.get('version')} ({skill.get('status')})")

    # ── Step 5: Evolve skill from comparison insights ────────────────────
    print(f"\n--- Step 5: Evolve skill ---")
    comparison_id = comparison.get("id")
    try:
        evo_run = tracer.evolve_skill(
            skill_name,
            strategy="single_mutation",
            comparison_ids=[comparison_id] if comparison_id else None,
        )
        print(f"  Evolution run: {evo_run.get('status')}")
        print(f"  Candidates: {evo_run.get('candidate_ids', [])}")
        print(f"  Winner: {evo_run.get('winner_id')}")

        # ── Step 6: Promote winner ───────────────────────────────────────
        winner_id = evo_run.get("winner_id")
        if winner_id:
            print(f"\n--- Step 6: Promote winner ---")
            promoted = tracer.promote_skill(winner_id)
            print(f"  Promoted: {promoted.get('skill_name')} v{promoted.get('version')} -> {promoted.get('status')}")
    except Exception as e:
        print(f"  Evolution: {e}")

    # ── Step 7: View history ─────────────────────────────────────────────
    print(f"\n--- Step 7: Evolution history ---")
    history = tracer.get_evolution_history(skill_name)
    print(f"  Versions: {len(history.get('versions', []))}")
    for v in history.get("fitness_trajectory", []):
        status_icon = "[active]" if v["status"] == "active" else "[      ]"
        print(f"    {status_icon} v{v['version']}: fitness={v['fitness']} ({v['status']})")

    print(f"\n{'=' * 60}")
    print("Demo complete! Full loop: trace -> compare -> evolve -> promote")
    print(f"{'=' * 60}")

    tracer.close()
    tracer2.close()


if __name__ == "__main__":
    main()
