"""Custom exceptions for Day1."""


class Day1Error(Exception):
    """Base exception for all Day1 errors."""


class DatabaseError(Day1Error):
    """Database operation failed."""


class BranchNotFoundError(Day1Error):
    """Requested branch does not exist."""


class BranchExistsError(Day1Error):
    """Branch with this name already exists."""


class EmbeddingError(Day1Error):
    """Embedding generation failed."""
