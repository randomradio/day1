#!/usr/bin/env python3
"""LiteLLM ReAct Agent + Day1 Skill Evolution — Full Loop Demo.

A manual ReAct loop using LiteLLM (supports 100+ LLM providers).
Demonstrates Day1 as a provider-agnostic skill evolution substrate.

Requirements:
  pip install litellm
  Day1 server running at http://10.112.1.28:8321

Usage:
  # Default (magikcloud deepseek-v3)
  python examples/litellm_react_agent.py

  # OpenAI
  python examples/litellm_react_agent.py --model gpt-4o-mini --api-key sk-...

  # Any OpenAI-compatible endpoint
  python examples/litellm_react_agent.py --model openai/your-model --api-base http://localhost:11434/v1
"""

from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any

import litellm

from day1_tracer import Day1Tracer

DAY1_URL = os.getenv("DAY1_URL", "http://10.112.1.28:8321")

# Default LLM config — magikcloud DeepSeek V3
DEFAULT_API_BASE = "https://api.magikcloud.cn/v1"
DEFAULT_API_KEY = "magik-2ab00f8ae98f4bab8f9d1876b71c42d6"
DEFAULT_MODEL = "openai/ep-deepseek-v3-2-104138"


# ── Tool definitions (OpenAI function calling format) ────────────────────

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web for information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Evaluate a math expression.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "Math expression"},
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "Directory path"},
                },
                "required": ["directory"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file's contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                },
                "required": ["path"],
            },
        },
    },
]


def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    """Execute a tool and return the result (simulated sandbox)."""
    if name == "search_web":
        query = arguments.get("query", "").lower()
        results = {
            "python asyncio": "asyncio provides async/await syntax. Key APIs: asyncio.run(), asyncio.gather(), asyncio.create_task().",
            "fastapi": "FastAPI is a high-performance Python web framework built on Starlette and Pydantic.",
            "react pattern": "ReAct = Reasoning + Acting. The agent reasons about what to do, takes an action, observes the result, and repeats.",
        }
        for key, value in results.items():
            if key in query:
                return value
        return f"No specific results for '{arguments.get('query')}'"

    elif name == "calculate":
        expr = arguments.get("expression", "")
        try:
            allowed = set("0123456789+-*/.() ")
            if all(c in allowed for c in expr):
                return str(eval(expr))  # noqa: S307
        except Exception as e:
            return f"Error: {e}"
        return "Error: invalid expression"

    elif name == "list_files":
        directory = arguments.get("directory", ".")
        if directory in (".", "/project", "/project/src"):
            return "main.py\nconfig.py\nutils.py\ntest_main.py"
        return f"Directory not found: {directory}"

    elif name == "read_file":
        path = arguments.get("path", "")
        files = {
            "main.py": "from fastapi import FastAPI\napp = FastAPI()\n\n@app.get('/health')\ndef health():\n    return {'status': 'ok'}",
            "config.py": "import os\nDB_URL = os.getenv('DATABASE_URL', 'sqlite:///app.db')\nDEBUG = True",
            "utils.py": "import hashlib\n\ndef hash_text(text: str) -> str:\n    return hashlib.sha256(text.encode()).hexdigest()",
        }
        return files.get(path.split("/")[-1], f"File not found: {path}")

    return f"Unknown tool: {name}"


# ── ReAct loop ───────────────────────────────────────────────────────────

def run_react_agent(
    task: str,
    tracer: Day1Tracer,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.0,
    max_steps: int = 10,
    trace_type: str = "original",
    parent_trace_id: str | None = None,
    api_base: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Run a ReAct loop with LiteLLM and capture trace in Day1."""
    tracer.start(task, model=model, temperature=temperature, framework="litellm")
    tracer.add_user_message(task)

    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant. Use the provided tools to complete the task. "
                "Think step by step. When you have enough information, provide a final answer."
            ),
        },
        {"role": "user", "content": task},
    ]

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "tools": TOOL_SCHEMAS,
        "temperature": temperature,
    }
    if api_base:
        kwargs["api_base"] = api_base
    if api_key:
        kwargs["api_key"] = api_key

    final_answer = ""

    for step in range(max_steps):
        t0 = time.time()
        response = litellm.completion(**kwargs)
        duration_ms = int((time.time() - t0) * 1000)
        msg = response.choices[0].message

        # Track token usage
        usage = response.usage
        token_count = (usage.total_tokens if usage else None)

        if msg.tool_calls:
            # Agent wants to call tools
            messages.append(msg.model_dump())

            for tc in msg.tool_calls:
                func_name = tc.function.name
                func_args = json.loads(tc.function.arguments)

                # Record the assistant's reasoning + tool call
                reasoning = msg.content or ""
                if reasoning:
                    tracer.add_assistant_message(reasoning, token_count=token_count)

                # Execute tool
                t1 = time.time()
                result = execute_tool(func_name, func_args)
                tool_duration = int((time.time() - t1) * 1000)

                tracer.add_tool_use(
                    tool_name=func_name,
                    tool_input=func_args,
                    tool_output=result,
                    duration_ms=tool_duration,
                )

                # Add tool result to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

            # Continue the loop with tool results
            kwargs["messages"] = messages

        else:
            # Final answer (no tool calls)
            final_answer = msg.content or ""
            tracer.add_assistant_message(final_answer, token_count=token_count)
            break

    # Store trace
    trace = tracer.finish(trace_type=trace_type, parent_trace_id=parent_trace_id)
    print(f"  Agent answer: {final_answer[:200]}")
    return trace


# ── Main ─────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="LiteLLM ReAct Agent + Day1")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="LiteLLM model name")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="API base URL")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="API key")
    parser.add_argument("--day1-url", default=DAY1_URL, help="Day1 server URL")
    args = parser.parse_args()

    print("=" * 60)
    print("LiteLLM ReAct Agent + Day1 Skill Evolution Demo")
    print(f"  Model: {args.model}")
    print(f"  Day1:  {args.day1_url}")
    print("=" * 60)

    tracer = Day1Tracer(args.day1_url, session_id=f"litellm-demo-{int(time.time())}")

    # Health check
    try:
        health = tracer.health()
        print(f"\n[ok] Day1 server: {health}")
    except Exception as e:
        print(f"\n[err] Day1 not reachable at {args.day1_url}: {e}")
        print("  Start Day1: PYTHONPATH=src .venv/bin/uvicorn day1.api.app:app --port 8321")
        return

    task = (
        "I need to understand a project: first list the files in /project, "
        "then read main.py and config.py, and finally search for what the ReAct pattern is. "
        "Give me a summary of everything."
    )

    # ── Step 1: Run agent (original) ─────────────────────────────────────
    print(f"\n--- Step 1: Run agent (original, temp=0.0) ---")
    print(f"  Task: {task[:80]}...")
    trace_a = run_react_agent(
        task, tracer,
        model=args.model,
        temperature=0.0,
        trace_type="original",
        api_base=args.api_base,
        api_key=args.api_key,
    )
    trace_a_id = trace_a["id"]
    print(f"  Trace A: {trace_a_id}")
    print(f"  Summary: {trace_a.get('summary', {})}")

    # ── Step 2: Re-run (variant with temp=0.8) ───────────────────────────
    print(f"\n--- Step 2: Re-run agent (variant, temp=0.8) ---")
    tracer2 = Day1Tracer(args.day1_url, session_id=f"litellm-variant-{int(time.time())}")
    trace_b = run_react_agent(
        task, tracer2,
        model=args.model,
        temperature=0.8,
        trace_type="variant",
        parent_trace_id=trace_a_id,
        api_base=args.api_base,
        api_key=args.api_key,
    )
    trace_b_id = trace_b["id"]
    print(f"  Trace B: {trace_b_id}")
    print(f"  Summary: {trace_b.get('summary', {})}")

    # ── Step 3: Compare ──────────────────────────────────────────────────
    print(f"\n--- Step 3: Compare traces (9 dimensions) ---")
    comparison = tracer.compare(trace_a_id, trace_b_id)
    print(f"  Verdict: {comparison.get('verdict')}")
    print(f"  Dimension scores:")
    for dim, score in sorted(comparison.get("dimension_scores", {}).items()):
        bar = "█" * int(score * 20) + "░" * (20 - int(score * 20))
        label = "B better" if score > 0.6 else "A better" if score < 0.4 else "equal"
        print(f"    {dim:25s} {bar} {score:.2f} {label}")
    insights = comparison.get("insights", [])
    if insights:
        print(f"  Insights:")
        for i in insights[:5]:
            print(f"    - {i}")

    # ── Step 4: Register skill ───────────────────────────────────────────
    print(f"\n--- Step 4: Register SKILL.md ---")
    run_id = int(time.time())
    skill_name = f"project-explorer-{run_id}"
    skill_md = f"""# {skill_name}

## Description
A skill for exploring and understanding codebases.

## Instructions
1. List directory contents to understand project structure
2. Read key files (main entry point, configuration)
3. Search for relevant concepts/patterns
4. Synthesize a clear summary

## Best Practices
- Read files in dependency order (config -> main -> utils)
- Note important patterns and frameworks used
- Report findings organized by category

## Model
Tested with: {args.model}
"""
    skill = tracer.register_skill(skill_name, skill_md)
    print(f"  Registered: {skill.get('skill_name')} v{skill.get('version')}")

    # ── Step 5: Evolve ───────────────────────────────────────────────────
    print(f"\n--- Step 5: Evolve skill from comparison insights ---")
    comp_id = comparison.get("id")
    try:
        evo = tracer.evolve_skill(
            skill_name,
            strategy="single_mutation",
            comparison_ids=[comp_id] if comp_id else None,
        )
        print(f"  Status: {evo.get('status')}")
        print(f"  Winner: {evo.get('winner_id')}")

        # Promote
        winner_id = evo.get("winner_id")
        if winner_id:
            print(f"\n--- Step 6: Promote evolved skill ---")
            promoted = tracer.promote_skill(winner_id)
            print(f"  {promoted.get('skill_name')} v{promoted.get('version')} -> {promoted.get('status')}")
    except Exception as e:
        print(f"  Evolution result: {e}")

    # ── History ──────────────────────────────────────────────────────────
    print(f"\n--- Step 7: Evolution history ---")
    history = tracer.get_evolution_history(skill_name)
    for v in history.get("fitness_trajectory", []):
        status_icon = "[active]" if v["status"] == "active" else "[      ]"
        print(f"  {status_icon} v{v['version']}: fitness={v['fitness']} ({v['status']})")

    print(f"\n{'=' * 60}")
    print("Demo complete! Full loop: trace -> compare -> evolve -> promote")
    print(f"{'=' * 60}")

    tracer.close()
    tracer2.close()


if __name__ == "__main__":
    main()
