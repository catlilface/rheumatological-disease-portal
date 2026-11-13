from pathlib import Path
from typing import Self

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class CorsSettings(BaseModel):
    """CORS configuration populated by the parent Settings model."""

    allow_origins: list[str] = Field(default_factory=list)
    allow_methods: list[str] = Field(default_factory=lambda: ["GET"])
    allow_headers: list[str] = Field(default_factory=list)
    allow_credentials: bool = False
    expose_headers: list[str] = Field(default_factory=list)
    max_age: int = Field(default=600, ge=0)

    @model_validator(mode="after")
    def validate_credentialed_cors(self) -> Self:
        if self.allow_credentials and any(
            "*" in values for values in (
                self.allow_origins, self.allow_methods, self.allow_headers,
            )
        ):
            raise ValueError("CORS with credentials requires explicit lists without wildcard '*'")
        return self


class Settings(BaseSettings):
    """Application settings from the environment and the repository's .env."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    app_name: str = "Rheumatological Disease Portal"
    debug: bool = False
    allowed_hosts: list[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1"], min_length=1)
    cors: CorsSettings = Field(default_factory=CorsSettings)
