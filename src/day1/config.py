"""Application configuration via environment variables."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Load .env from project root (works regardless of CWD)
_project_root = Path(__file__).resolve().parents[2]
load_dotenv(_project_root / ".env")


class Settings(BaseSettings):
    """Day1 configuration."""

    # Database (MatrixOne via aiomysql)
    database_url: str = "mysql+aiomysql://user:pass@localhost:6001/day1"

    # Embedding
    embedding_provider: str = "openai"  # "openai" | "doubao" | "mock"
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Doubao (Volces/ByteDance) Embedding
    doubao_api_key: str = ""
    doubao_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    doubao_embedding_model: str = "doubao-embedding-vision-251215"
    doubao_llm_model: str = "doubao-seed-1-6-251015"

    # LLM (OpenAI-compatible API)
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""
    llm_provider: str = "openai"  # "openai" | "anthropic" | "custom"

    # Anthropic (legacy, for backward compatibility)
    anthropic_api_key: str = ""

    # Server
    host: str = "127.0.0.1"
    port: int = 8000

    # Security
    api_key: str = ""  # Empty = open access (dev mode)
    cors_origins: list[str] = ["*"]  # Restrict in production
    rate_limit: int = 0  # Requests per minute per IP (0 = disabled)

    # Logging
    log_level: str = "DEBUG"  # DEBUG | INFO | WARNING | ERROR
    log_format: str = "text"  # "text" | "json"

    # Branch defaults
    default_branch: str = "main"

    # Hooks debug logging
    hooks_debug: bool = False

    model_config = {"env_prefix": "BM_", "env_file": ".env"}


settings = Settings()
