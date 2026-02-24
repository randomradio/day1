"""Knowledge bundle engine: portable, serialized knowledge packages.

Unlike Templates (which are live branch forks), Bundles are portable
serialized packages that can be exported and imported across projects.

Bundles can be imported into templates, and templates can be exported
as bundles.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from day1.core.exceptions import KnowledgeBundleError
from day1.db.models import (
    Conversation,
    Fact,
    KnowledgeBundle,
    Message,
    Relation,
)

logger = logging.getLogger(__name__)


class KnowledgeBundleEngine:
    """Create, export, and import portable knowledge bundles."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_bundle(
        self,
        name: str,
        source_branch: str,
        description: str | None = None,
        source_task_id: str | None = None,
        tags: list[str] | None = None,
        created_by: str | None = None,
        only_verified: bool = True,
        fact_ids: list[str] | None = None,
        conversation_ids: list[str] | None = None,
    ) -> dict:
        """Create a knowledge bundle from a branch.

        Serializes facts, conversations (with messages), and relations
        into a portable package.

        Args:
            name: Bundle name.
            source_branch: Branch to export from.
            description: Bundle description.
            source_task_id: Associated task ID.
            tags: Discovery tags.
            created_by: Creator identifier.
            only_verified: Only include verified facts (default True).
            fact_ids: Specific fact IDs (overrides auto-selection).
            conversation_ids: Specific conversation IDs.

        Returns:
            Dict with bundle metadata.
        """
        # Collect facts
        if fact_ids:
            fact_result = await self._session.execute(
                select(Fact).where(Fact.id.in_(fact_ids))
            )
            facts = list(fact_result.scalars().all())
        else:
            fact_result = await self._session.execute(
                select(Fact).where(
                    Fact.branch_name == source_branch,
                    Fact.status == "active",
                )
            )
            facts = list(fact_result.scalars().all())
            if only_verified:
                facts = [
                    f for f in facts
                    if (f.metadata_json or {}).get("verification_status") == "verified"
                ]

        # Collect conversations
        if conversation_ids:
            conv_result = await self._session.execute(
                select(Conversation).where(Conversation.id.in_(conversation_ids))
            )
        else:
            conv_result = await self._session.execute(
                select(Conversation).where(
                    Conversation.branch_name == source_branch,
                    Conversation.status.in_(["active", "completed"]),
                )
            )
        conversations = list(conv_result.scalars().all())

        # Collect relations on branch
        rel_result = await self._session.execute(
            select(Relation).where(Relation.branch_name == source_branch)
        )
        relations = list(rel_result.scalars().all())

        # Serialize facts
        serialized_facts = [
            {
                "fact_text": f.fact_text,
                "category": f.category,
                "confidence": f.confidence,
                "source_type": f.source_type,
                "metadata": f.metadata_json,
            }
            for f in facts
        ]

        # Serialize conversations with messages
        serialized_conversations = []
        for conv in conversations:
            msg_result = await self._session.execute(
                select(Message)
                .where(Message.conversation_id == conv.id)
                .order_by(Message.sequence_num.asc())
            )
            messages = msg_result.scalars().all()

            serialized_conversations.append({
                "title": conv.title,
                "status": conv.status,
                "model": conv.model,
                "messages": [
                    {
                        "role": m.role,
                        "content": m.content,
                        "thinking": m.thinking,
                        "sequence_num": m.sequence_num,
                        "token_count": m.token_count,
                    }
                    for m in messages
                ],
            })

        # Serialize relations
        serialized_relations = [
            {
                "source_entity": r.source_entity,
                "target_entity": r.target_entity,
                "relation_type": r.relation_type,
                "properties": r.properties,
                "confidence": r.confidence,
            }
            for r in relations
        ]

        bundle_data = {
            "facts": serialized_facts,
            "conversations": serialized_conversations,
            "relations": serialized_relations,
        }

        # Create bundle record
        bundle = KnowledgeBundle(
            name=name,
            description=description,
            source_branch=source_branch,
            source_task_id=source_task_id,
            fact_count=len(serialized_facts),
            conversation_count=len(serialized_conversations),
            relation_count=len(serialized_relations),
            bundle_data=bundle_data,
            tags=tags,
            created_by=created_by,
        )
        self._session.add(bundle)
        await self._session.commit()
        await self._session.refresh(bundle)

        return {
            "id": bundle.id,
            "name": bundle.name,
            "description": bundle.description,
            "version": bundle.version,
            "source_branch": bundle.source_branch,
            "fact_count": bundle.fact_count,
            "conversation_count": bundle.conversation_count,
            "relation_count": bundle.relation_count,
            "tags": bundle.tags,
            "created_at": bundle.created_at.isoformat() if bundle.created_at else None,
        }

    async def import_bundle(
        self,
        bundle_id: str,
        target_branch: str,
        import_facts: bool = True,
        import_conversations: bool = True,
        import_relations: bool = True,
    ) -> dict:
        """Import a knowledge bundle into a target branch.

        Creates new facts, conversations, messages, and relations on the
        target branch from the bundle's serialized data.

        Args:
            bundle_id: Bundle to import.
            target_branch: Branch to import into.
            import_facts: Whether to import facts.
            import_conversations: Whether to import conversations.
            import_relations: Whether to import relations.

        Returns:
            Dict with counts of imported items.
        """
        result = await self._session.execute(
            select(KnowledgeBundle).where(KnowledgeBundle.id == bundle_id)
        )
        bundle = result.scalar_one_or_none()
        if bundle is None:
            raise KnowledgeBundleError(f"Bundle {bundle_id} not found")

        data = bundle.bundle_data or {}
        facts_imported = 0
        conversations_imported = 0
        messages_imported = 0
        relations_imported = 0

        # Import facts
        if import_facts:
            for fd in data.get("facts", []):
                fact = Fact(
                    fact_text=fd["fact_text"],
                    category=fd.get("category"),
                    confidence=fd.get("confidence", 0.7),
                    source_type="bundle_import",
                    source_id=bundle.id,
                    branch_name=target_branch,
                    metadata_json=fd.get("metadata"),
                )
                self._session.add(fact)
                facts_imported += 1

        # Import conversations with messages
        if import_conversations:
            for cd in data.get("conversations", []):
                conv = Conversation(
                    branch_name=target_branch,
                    title=cd.get("title"),
                    status="active",
                    model=cd.get("model"),
                    message_count=len(cd.get("messages", [])),
                    metadata_json={"imported_from_bundle": bundle.id},
                )
                self._session.add(conv)
                await self._session.flush()

                for md in cd.get("messages", []):
                    msg = Message(
                        conversation_id=conv.id,
                        role=md["role"],
                        content=md.get("content"),
                        thinking=md.get("thinking"),
                        sequence_num=md.get("sequence_num", 0),
                        token_count=md.get("token_count", 0),
                        branch_name=target_branch,
                    )
                    self._session.add(msg)
                    messages_imported += 1

                conversations_imported += 1

        # Import relations
        if import_relations:
            for rd in data.get("relations", []):
                rel = Relation(
                    source_entity=rd["source_entity"],
                    target_entity=rd["target_entity"],
                    relation_type=rd["relation_type"],
                    properties=rd.get("properties"),
                    confidence=rd.get("confidence", 1.0),
                    branch_name=target_branch,
                )
                self._session.add(rel)
                relations_imported += 1

        await self._session.commit()

        return {
            "bundle_id": bundle.id,
            "bundle_name": bundle.name,
            "target_branch": target_branch,
            "facts_imported": facts_imported,
            "conversations_imported": conversations_imported,
            "messages_imported": messages_imported,
            "relations_imported": relations_imported,
        }

    async def get_bundle(self, bundle_id: str) -> dict:
        """Get bundle details without the full bundle_data."""
        result = await self._session.execute(
            select(KnowledgeBundle).where(KnowledgeBundle.id == bundle_id)
        )
        bundle = result.scalar_one_or_none()
        if bundle is None:
            raise KnowledgeBundleError(f"Bundle {bundle_id} not found")

        return {
            "id": bundle.id,
            "name": bundle.name,
            "description": bundle.description,
            "version": bundle.version,
            "source_branch": bundle.source_branch,
            "source_task_id": bundle.source_task_id,
            "fact_count": bundle.fact_count,
            "conversation_count": bundle.conversation_count,
            "relation_count": bundle.relation_count,
            "tags": bundle.tags,
            "status": bundle.status,
            "created_by": bundle.created_by,
            "created_at": bundle.created_at.isoformat() if bundle.created_at else None,
        }

    async def export_bundle(self, bundle_id: str) -> dict:
        """Export the full bundle data (for transfer/download).

        Returns the complete bundle including serialized data.
        """
        result = await self._session.execute(
            select(KnowledgeBundle).where(KnowledgeBundle.id == bundle_id)
        )
        bundle = result.scalar_one_or_none()
        if bundle is None:
            raise KnowledgeBundleError(f"Bundle {bundle_id} not found")

        return {
            "id": bundle.id,
            "name": bundle.name,
            "description": bundle.description,
            "version": bundle.version,
            "source_branch": bundle.source_branch,
            "fact_count": bundle.fact_count,
            "conversation_count": bundle.conversation_count,
            "relation_count": bundle.relation_count,
            "tags": bundle.tags,
            "status": bundle.status,
            "created_by": bundle.created_by,
            "bundle_data": bundle.bundle_data,
            "created_at": bundle.created_at.isoformat() if bundle.created_at else None,
        }

    async def list_bundles(
        self,
        status: str = "active",
        tags: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """List knowledge bundles with optional filters."""
        stmt = (
            select(KnowledgeBundle)
            .where(KnowledgeBundle.status == status)
            .order_by(KnowledgeBundle.created_at.desc())
            .limit(limit)
        )

        result = await self._session.execute(stmt)
        bundles = list(result.scalars().all())

        # Filter by tags in Python (JSON column)
        if tags:
            tag_set = set(tags)
            bundles = [
                b for b in bundles
                if b.tags and tag_set.intersection(set(b.tags))
            ]

        return [
            {
                "id": b.id,
                "name": b.name,
                "description": b.description,
                "version": b.version,
                "source_branch": b.source_branch,
                "fact_count": b.fact_count,
                "conversation_count": b.conversation_count,
                "relation_count": b.relation_count,
                "tags": b.tags,
                "status": b.status,
                "created_by": b.created_by,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
            for b in bundles
        ]
