"""PreCompact hook: extract facts and relations before context compression.

Invoked when Claude Code is about to compress the conversation context.
Extracts structured facts and relations to prevent information loss.
"""

from __future__ import annotations

import asyncio

from day1.core.embedding import get_embedding_provider
from day1.core.fact_engine import FactEngine
from day1.core.relation_engine import RelationEngine
from day1.core.search_engine import SearchEngine
from day1.hooks.base import (
    get_db_session,
    get_session_id,
    read_hook_input,
    write_hook_output,
)


async def handler(input_data: dict) -> dict:
    """Extract facts and relations from context before compression."""
    session = await get_db_session()
    if session is None:
        return {}

    embedder = get_embedding_provider()
    fact_engine = FactEngine(session, embedder)
    search_engine = SearchEngine(session, embedder)
    relation_engine = RelationEngine(session)

    # Get transcript content if available
    transcript = input_data.get("transcript", "")
    if not transcript:
        await session.close()
        return {}

    # For MVP: extract simple facts from transcript using heuristics
    # Production version would use LLM (Claude) for intelligent extraction
    facts_extracted = _extract_facts_heuristic(transcript)
    relations_extracted = _extract_relations_heuristic(transcript)

    facts_written = 0
    for fact_data in facts_extracted:
        # Dedup check: search for similar existing facts
        existing = await search_engine.search(
            query=fact_data["text"],
            search_type="vector",
            limit=3,
        )
        if existing and existing[0]["score"] > 0.92:
            # Highly similar fact exists, update confidence
            await fact_engine.update_fact(
                existing[0]["id"],
                confidence=max(existing[0]["confidence"], 0.9),
            )
        else:
            await fact_engine.write_fact(
                fact_text=fact_data["text"],
                category=fact_data.get("category"),
                source_type="extraction",
                session_id=get_session_id(),
            )
            facts_written += 1

    rels_written = 0
    for rel_data in relations_extracted:
        await relation_engine.write_relation(
            source_entity=rel_data["source"],
            target_entity=rel_data["target"],
            relation_type=rel_data["type"],
            session_id=get_session_id(),
        )
        rels_written += 1

    await session.close()

    return {
        "systemMessage": (
            f"[Day1] Extracted {facts_written} facts and "
            f"{rels_written} relations from context before compression."
        )
    }


def _extract_facts_heuristic(transcript: str) -> list[dict]:
    """Simple heuristic fact extraction from transcript.

    For MVP: extracts sentences that look like factual statements.
    Production would use Claude API for structured extraction.
    """
    facts = []
    lines = transcript.split("\n")
    for line in lines:
        line = line.strip()
        if not line or len(line) < 20:
            continue
        # Look for declarative patterns
        indicators = [
            "uses ",
            "requires ",
            "depends on ",
            "is configured",
            "was fixed",
            "caused by",
            "the project",
            "the system",
            "architecture",
            "pattern",
            "bug",
            "error",
            "solution",
        ]
        if any(ind in line.lower() for ind in indicators):
            category = "general"
            if any(w in line.lower() for w in ("bug", "error", "fix")):
                category = "bug_fix"
            elif any(w in line.lower() for w in ("architecture", "design", "pattern")):
                category = "architecture"
            elif any(w in line.lower() for w in ("prefer", "convention", "style")):
                category = "preference"
            facts.append({"text": line[:500], "category": category})
    return facts[:20]  # Cap at 20 facts per extraction


def _extract_relations_heuristic(transcript: str) -> list[dict]:
    """Simple heuristic relation extraction.

    For MVP: basic pattern matching.
    Production would use LLM for accurate extraction.
    """
    relations = []
    patterns = [
        ("depends on", "depends_on"),
        ("implements", "implements"),
        ("fixes", "fixes"),
        ("causes", "causes"),
        ("uses", "uses"),
    ]
    lines = transcript.split("\n")
    for line in lines:
        for pattern, rel_type in patterns:
            if pattern in line.lower():
                parts = line.lower().split(pattern)
                if len(parts) == 2:
                    source = parts[0].strip().split()[-1] if parts[0].strip() else ""
                    target = parts[1].strip().split()[0] if parts[1].strip() else ""
                    if source and target and len(source) > 2 and len(target) > 2:
                        relations.append(
                            {
                                "source": source.title(),
                                "target": target.title(),
                                "type": rel_type,
                            }
                        )
    return relations[:10]


def main() -> None:
    input_data = read_hook_input()
    result = asyncio.run(handler(input_data))
    write_hook_output(result)


if __name__ == "__main__":
    main()
