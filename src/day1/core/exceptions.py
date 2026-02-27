"""Custom exceptions for Day1."""


class Day1Error(Exception):
    """Base exception for all Day1 errors."""


class DatabaseError(Day1Error):
    """Database operation failed."""


class BranchNotFoundError(Day1Error):
    """Requested branch does not exist."""


class BranchExistsError(Day1Error):
    """Branch with this name already exists."""


class BranchCreationError(Day1Error, RuntimeError):
    """Branch creation failed after validation (write/commit/native op failure)."""


class FactNotFoundError(Day1Error):
    """Requested fact does not exist."""


class MergeConflictError(Day1Error):
    """Merge conflict that requires resolution."""


class EmbeddingError(Day1Error):
    """Embedding generation failed."""


class SnapshotError(Day1Error):
    """Snapshot operation failed."""


class TaskNotFoundError(Day1Error):
    """Requested task does not exist."""


class TaskAgentError(Day1Error):
    """Task agent operation failed."""


class ConsolidationError(Day1Error):
    """Memory consolidation failed."""


class ConversationNotFoundError(Day1Error):
    """Requested conversation does not exist."""


class MessageNotFoundError(Day1Error):
    """Requested message does not exist."""


class ReplayError(Day1Error):
    """Replay operation failed."""


class AnalyticsError(Day1Error):
    """Analytics computation failed."""


class BranchTopologyError(Day1Error):
    """Branch topology operation failed."""


class TemplateNotFoundError(Day1Error):
    """Requested template does not exist."""


class TemplateError(Day1Error):
    """Template operation failed."""


class VerificationError(Day1Error):
    """Fact or conversation verification failed."""


class HandoffError(Day1Error):
    """Task handoff operation failed."""


class KnowledgeBundleError(Day1Error):
    """Knowledge bundle operation failed."""
