"""Tests for TemplateEngine."""

from __future__ import annotations

import pytest
import pytest_asyncio

from day1.core.branch_manager import BranchManager
from day1.core.exceptions import (
    BranchNotFoundError,
    TemplateError,
    TemplateNotFoundError,
)
from day1.core.fact_engine import FactEngine
from day1.core.template_engine import TemplateEngine


@pytest.mark.asyncio
async def test_create_template_from_branch(db_session, mock_embedder):
    """Create a template from an existing branch."""
    # Write some facts to main
    fact_engine = FactEngine(db_session, mock_embedder)
    await fact_engine.write_fact(fact_text="Best practice: use async", branch_name="main")
    await fact_engine.write_fact(fact_text="Pattern: retry with backoff", branch_name="main")

    engine = TemplateEngine(db_session)
    template = await engine.create_template(
        name="Python Best Practices",
        source_branch="main",
        description="Common Python patterns and practices",
        applicable_task_types=["bug_fix", "feature"],
        tags=["python", "patterns"],
        created_by="curator-1",
    )

    assert template.name == "Python Best Practices"
    assert template.version == 1
    assert template.branch_name == "template/python-best-practices/v1"
    assert template.source_branch == "main"
    assert template.status == "active"
    assert template.applicable_task_types == ["bug_fix", "feature"]
    assert template.tags == ["python", "patterns"]
    assert template.created_by == "curator-1"
    assert template.fact_count == 2


@pytest.mark.asyncio
async def test_create_template_invalid_source(db_session):
    """Creating template from nonexistent branch raises error."""
    engine = TemplateEngine(db_session)
    with pytest.raises(BranchNotFoundError):
        await engine.create_template(
            name="Bad Template",
            source_branch="nonexistent-branch",
        )


@pytest.mark.asyncio
async def test_create_template_duplicate_name(db_session):
    """Creating template with existing name raises error."""
    engine = TemplateEngine(db_session)
    await engine.create_template(name="Unique Template", source_branch="main")

    with pytest.raises(TemplateError, match="already exists"):
        await engine.create_template(name="Unique Template", source_branch="main")


@pytest.mark.asyncio
async def test_instantiate_template(db_session, mock_embedder):
    """Instantiating template creates a working branch with inherited data."""
    fact_engine = FactEngine(db_session, mock_embedder)
    await fact_engine.write_fact(fact_text="Inherited knowledge", branch_name="main")

    engine = TemplateEngine(db_session)
    template = await engine.create_template(
        name="Starter Kit",
        source_branch="main",
    )

    result = await engine.instantiate_template(
        template_name="Starter Kit",
        target_branch_name="task/new-work",
        task_id="task-123",
    )

    assert result["branch_name"] == "task/new-work"
    assert result["template_name"] == "Starter Kit"
    assert result["template_version"] == 1
    assert result["facts_inherited"] == template.fact_count
    assert result["task_id"] == "task-123"


@pytest.mark.asyncio
async def test_instantiate_nonexistent_template(db_session):
    """Instantiating nonexistent template raises error."""
    engine = TemplateEngine(db_session)
    with pytest.raises(TemplateNotFoundError):
        await engine.instantiate_template(
            template_name="Ghost Template",
            target_branch_name="task/whatever",
        )


@pytest.mark.asyncio
async def test_update_template_bumps_version(db_session, mock_embedder):
    """Updating template creates new version and deprecates old."""
    fact_engine = FactEngine(db_session, mock_embedder)
    await fact_engine.write_fact(fact_text="Original fact", branch_name="main")

    engine = TemplateEngine(db_session)
    v1 = await engine.create_template(
        name="Evolving Template",
        source_branch="main",
        applicable_task_types=["feature"],
    )
    assert v1.version == 1

    # Add more facts and update
    await fact_engine.write_fact(fact_text="New discovery", branch_name="main")

    v2 = await engine.update_template(
        template_name="Evolving Template",
        source_branch="main",
        reason="Added new discoveries",
    )

    assert v2.version == 2
    assert v2.branch_name == "template/evolving-template/v2"
    assert v2.status == "active"
    assert v2.applicable_task_types == ["feature"]  # Inherited from v1
    assert v2.metadata_json["previous_version"] == 1
    assert v2.metadata_json["update_reason"] == "Added new discoveries"


@pytest.mark.asyncio
async def test_update_deprecates_old_version(db_session):
    """Old version is deprecated after update."""
    engine = TemplateEngine(db_session)
    v1 = await engine.create_template(
        name="Versioned Template",
        source_branch="main",
    )

    await engine.update_template(
        template_name="Versioned Template",
        source_branch="main",
    )

    # v1 should now be deprecated — get_template returns v2
    template = await engine.get_template("Versioned Template")
    assert template.version == 2


@pytest.mark.asyncio
async def test_list_templates_filter_by_task_type(db_session):
    """List templates filtered by applicable task type."""
    engine = TemplateEngine(db_session)
    await engine.create_template(
        name="Bug Fix Patterns",
        source_branch="main",
        applicable_task_types=["bug_fix"],
    )
    await engine.create_template(
        name="Feature Guide",
        source_branch="main",
        applicable_task_types=["feature"],
    )

    bug_templates = await engine.list_templates(task_type="bug_fix")
    assert len(bug_templates) == 1
    assert bug_templates[0].name == "Bug Fix Patterns"


@pytest.mark.asyncio
async def test_list_templates_filter_by_tags(db_session):
    """List templates filtered by tags."""
    engine = TemplateEngine(db_session)
    await engine.create_template(
        name="Auth Patterns",
        source_branch="main",
        tags=["auth", "security"],
    )
    await engine.create_template(
        name="DB Patterns",
        source_branch="main",
        tags=["database", "sql"],
    )

    auth_templates = await engine.list_templates(tags=["auth"])
    assert len(auth_templates) == 1
    assert auth_templates[0].name == "Auth Patterns"


@pytest.mark.asyncio
async def test_find_applicable_template_exact_match(db_session):
    """Find template by exact task type match."""
    engine = TemplateEngine(db_session)
    await engine.create_template(
        name="Incident Response",
        source_branch="main",
        applicable_task_types=["incident", "hotfix"],
    )

    found = await engine.find_applicable_template(task_type="incident")
    assert found is not None
    assert found.name == "Incident Response"


@pytest.mark.asyncio
async def test_find_applicable_template_no_match(db_session):
    """Find template returns None when no match."""
    engine = TemplateEngine(db_session)
    await engine.create_template(
        name="Only For Bugs",
        source_branch="main",
        applicable_task_types=["bug_fix"],
    )

    found = await engine.find_applicable_template(task_type="research")
    assert found is None


@pytest.mark.asyncio
async def test_deprecate_template(db_session):
    """Deprecating template marks all active versions as deprecated."""
    engine = TemplateEngine(db_session)
    await engine.create_template(
        name="Deprecated Template",
        source_branch="main",
    )

    deprecated = await engine.deprecate_template("Deprecated Template")
    assert deprecated.status == "deprecated"

    # Should not be findable anymore
    with pytest.raises(TemplateNotFoundError):
        await engine.get_template("Deprecated Template")


@pytest.mark.asyncio
async def test_get_template(db_session):
    """Get template returns latest active version."""
    engine = TemplateEngine(db_session)
    await engine.create_template(
        name="My Template",
        source_branch="main",
        description="A test template",
    )

    template = await engine.get_template("My Template")
    assert template.name == "My Template"
    assert template.description == "A test template"
    assert template.version == 1
    assert template.status == "active"


@pytest.mark.asyncio
async def test_get_template_not_found(db_session):
    """Get nonexistent template raises error."""
    engine = TemplateEngine(db_session)
    with pytest.raises(TemplateNotFoundError):
        await engine.get_template("nonexistent")
