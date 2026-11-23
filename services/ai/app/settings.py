from pydantic_settings import BaseSettings, SettingsConfigDict
from rheuma_db import DatabaseSettings


class Settings(BaseSettings):
    """Loaded purely from the process environment (no shared .env file - the
    database name/user/password differ per service and per invocation, see
    the root Makefile)."""

    model_config = SettingsConfigDict(env_nested_delimiter="__", extra="ignore")

    database: DatabaseSettings
