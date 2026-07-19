"""Application configuration loaded from environment variables."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEV = "dev"
    TEST = "test"
    EVAL = "eval"
    PROD = "prod"


class AnalysisMode(StrEnum):
    STANDARD = "standard"
    FIXTURE = "fixture"  # deterministic fake-LLM mode used in tests


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    upgradepilot_env: Environment = Environment.DEV
    upgradepilot_version: str = "0.1.0"
    upgradepilot_git_sha: str = "unknown"

    # LangSmith
    langsmith_tracing: bool = True
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "upgradepilot-dev"
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_hide_inputs: bool = False
    langsmith_hide_outputs: bool = False

    # LLM provider
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-4-6"
    llm_api_key: SecretStr | None = None
    llm_max_tokens: int = 4096
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 2

    # GitHub
    github_token: SecretStr | None = None
    github_api_timeout_seconds: int = 30
    github_max_retries: int = 3

    # PostgreSQL — SecretStr prevents the password embedded in the URL from
    # appearing in repr() / logs. Call .get_secret_value() when passing to psycopg.
    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://upgradepilot:upgradepilot@localhost:5432/upgradepilot"
    )

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_timeout_seconds: int = 5

    # FastAPI
    api_host: str = "0.0.0.0"  # noqa: S104
    api_port: int = 8000
    api_workers: int = 1

    # Streamlit
    ui_port: int = 8501

    # Safety limits (configurable, applied during archive extraction)
    max_archive_compressed_bytes: Annotated[int, Field(gt=0)] = 100 * 1024 * 1024  # 100 MB
    max_archive_extracted_bytes: Annotated[int, Field(gt=0)] = 500 * 1024 * 1024  # 500 MB
    max_archive_file_count: Annotated[int, Field(gt=0)] = 10_000
    max_path_depth: Annotated[int, Field(gt=0)] = 20
    max_single_file_bytes: Annotated[int, Field(gt=0)] = 5 * 1024 * 1024  # 5 MB
    analysis_timeout_seconds: Annotated[int, Field(gt=0)] = 120

    # Workspace retention
    workspace_retention_hours: Annotated[int, Field(gt=0)] = 24

    @property
    def langsmith_project_name(self) -> str:
        return f"upgradepilot-{self.upgradepilot_env}"

    @property
    def tracing_enabled(self) -> bool:
        return self.langsmith_tracing and self.langsmith_api_key is not None


def get_settings() -> Settings:
    return Settings()
