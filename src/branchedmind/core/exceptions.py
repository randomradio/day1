"""Custom exceptions for BranchedMind."""


class BranchedMindError(Exception):
    """Base exception for all BranchedMind errors."""


class DatabaseError(BranchedMindError):
    """Database operation failed."""


class BranchNotFoundError(BranchedMindError):
    """Requested branch does not exist."""


class BranchExistsError(BranchedMindError):
    """Branch with this name already exists."""


class FactNotFoundError(BranchedMindError):
    """Requested fact does not exist."""


class MergeConflictError(BranchedMindError):
    """Merge conflict that requires resolution."""


class EmbeddingError(BranchedMindError):
    """Embedding generation failed."""


class SnapshotError(BranchedMindError):
    """Snapshot operation failed."""


class TaskNotFoundError(BranchedMindError):
    """Requested task does not exist."""


class TaskAgentError(BranchedMindError):
    """Task agent operation failed."""


class ConsolidationError(BranchedMindError):
    """Memory consolidation failed."""


class ConversationNotFoundError(BranchedMindError):
    """Requested conversation does not exist."""


class MessageNotFoundError(BranchedMindError):
    """Requested message does not exist."""
