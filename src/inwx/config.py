"""Client configuration (explicit args, env vars, or env file)."""

from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_API_URL = "https://api.domrobot.com/jsonrpc/"
OTE_API_URL = "https://api.ote.domrobot.com/jsonrpc/"


class Config(BaseModel):
    """INWX DomRobot client configuration with validation."""

    username: str = Field(description="INWX account username (account.login user)")
    password: str = Field(description="INWX account password (account.login pass)")
    api_url: str = Field(
        default=DEFAULT_API_URL,
        description="DomRobot JSON-RPC endpoint (prod default, OTE sandbox override)",
    )
    timeout: float = Field(default=30.0, description="Request timeout in seconds")
    log_level: str = Field(default="INFO", description="Logging level")
    language: str = Field(default="en", description="API message language (en/de)")

    model_config = ConfigDict(str_strip_whitespace=True, validate_default=True)

    @field_validator("username", "password")
    @classmethod
    def validate_required(cls, v: str) -> str:
        if not v:
            raise ValueError("must not be empty")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid}")
        return v.upper()

    @property
    def sandbox(self) -> bool:
        """True when pointed at the OTE test system."""
        return "ote.domrobot" in (self.api_url or "")

    @classmethod
    def from_env(
        cls,
        username: str | None = None,
        password: str | None = None,
        api_url: str | None = None,
        timeout: float | None = None,
        log_level: str | None = None,
        language: str | None = None,
    ) -> Config:
        """Build config from explicit args with ``INWX_*`` env fallback."""
        return cls(
            username=username or os.environ.get("INWX_USERNAME", ""),
            password=password or os.environ.get("INWX_API_PASSWORD", "") or os.environ.get("INWX_PASSWORD", ""),
            api_url=api_url or os.environ.get("INWX_API_URL", "") or DEFAULT_API_URL,
            timeout=timeout if timeout is not None else float(os.environ.get("INWX_TIMEOUT", "30.0")),
            log_level=log_level or os.environ.get("INWX_LOG_LEVEL", "INFO"),
            language=language or os.environ.get("INWX_LANGUAGE", "en"),
        )
