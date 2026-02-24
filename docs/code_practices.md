# Code Practices

Python development standards for Day1. Follow these when writing or modifying code.

## Style Guide

- Follow [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
- **Linter**: `ruff` (fast, Google-style compatible)
- **Formatter**: `black` (line length 88)
- **Type checker**: `mypy` strict mode
- **Test runner**: `pytest` with `pytest-asyncio`

## Project Structure

```
branchedmind/
├── src/                    # Application code
│   ├── api/              # FastAPI endpoints
│   ├── core/             # Business logic
│   ├── db/               # Database layer
│   ├── mcp/              # MCP server
│   └── hooks/            # Claude Code hooks
├── tests/                 # All tests
├── docs/                  # This directory
├── pyproject.toml         # Project config
└── CLAUDE.md             # Onboarding (do NOT put code style here!)
```

## Naming Conventions

| Context | Convention | Example |
|----------|-------------|----------|
| Modules | `lowercase_with_underscores` | `memory_client.py` |
| Classes | `CapitalizedWords` | `MemoryClient` |
| Functions/Methods | `lowercase_with_underscores` | `write_fact()` |
| Constants | `UPPERCASE_WITH_UNDERSCORES` | `DEFAULT_BRANCH` |
| Private | `_leading_underscore` | `_embed_text()` |

## Docstrings (Google Style)

```python
def write_fact(fact_text: str, category: str | None = None) -> Fact:
    """Write a new fact to memory.

    Args:
        fact_text: The natural language description of fact.
        category: Optional category (bug_fix, architecture, preference, etc.)

    Returns:
        The created Fact object with generated ID and timestamp.

    Raises:
        DatabaseError: If the write operation fails.
    """
    pass
```

## Type Annotations

- **All functions** must have type hints
- Use `X | Y` syntax for unions (Python 3.10+)
- Use `typing.Protocol` for interfaces
- Avoid `Any` - use `object` or specific types

## Error Handling

- Define custom exceptions in `src/core/exceptions.py`
- Raise specific exceptions, never generic `Exception`
- Use context managers for resources
- Document exceptions in docstrings (Raises section)

## Testing

- Use `pytest` with `pytest-asyncio`
- Aim for 80%+ coverage on core logic
- Test behavior, not implementation
- Use fixtures for database, async client setup
