"""Tests for BranchManager transactional behavior."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from day1.core.branch_manager import BranchManager
from day1.core.exceptions import BranchCreationError
from day1.db.models import BranchRegistry


@pytest.mark.asyncio
async def test_create_branch_rolls_back_on_commit_error(db_session, monkeypatch):
    """Branch creation should roll back if commit fails."""
    mgr = BranchManager(db_session)

    orig_rollback = db_session.rollback
    rollback_called = {"value": False}

    async def failing_commit(*args, **kwargs):
        raise RuntimeError("commit failed")

    async def tracking_rollback(*args, **kwargs):
        rollback_called["value"] = True
        await orig_rollback()

    monkeypatch.setattr(db_session, "commit", failing_commit)
    monkeypatch.setattr(db_session, "rollback", tracking_rollback)

    with pytest.raises(BranchCreationError):
        await mgr.create_branch("task/rollback-test", tables=[])

    assert rollback_called["value"] is True

    result = await db_session.execute(
        select(BranchRegistry).where(
            BranchRegistry.branch_name == "task/rollback-test"
        )
    )
    assert result.scalar_one_or_none() is None
