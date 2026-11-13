from pydantic import BaseModel, Field, SecretStr
from sqlalchemy.engine import URL


class DatabaseSettings(BaseModel):
    """Database configuration populated through Settings.database."""

    host: str = Field(default="localhost", min_length=1)
    port: int = Field(default=5432, ge=1, le=65535)
    name: str = Field(default="rheumatology", min_length=1)
    user: str = Field(default="rheumatology", min_length=1)
    password: SecretStr = Field(default_factory=lambda: SecretStr(""))
    connect_timeout: int = Field(default=5, ge=1)

    def connection_url(self) -> URL:
        password = self.password.get_secret_value()
        if not password:
            raise ValueError("DATABASE__PASSWORD must be set before connecting to PostgreSQL")
        return URL.create(
            "postgresql+psycopg",
            username=self.user,
            password=password,
            host=self.host,
            port=self.port,
            database=self.name,
        )
