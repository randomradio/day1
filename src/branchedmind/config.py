"""Application configuration via environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """BranchedMind configuration."""

    # Database (MatrixOne via aiomysql)
    database_url: str = "mysql+aiomysql://user:pass@localhost:6001/branchedmind"

    # Embedding
    embedding_provider: str = "openai"  # "openai" | "mock"
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # LLM (for fact extraction, conflict resolution)
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-4-5-20250929"

    # Server
    host: str = "127.0.0.1"
    port: int = 8000

    # Branch defaults
    default_branch: str = "main"

    model_config = {"env_prefix": "BM_", "env_file": ".env"}


settings = Settings()
