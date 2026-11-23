from pydantic import BaseModel, Field, SecretStr
from sqlalchemy.engine import URL


class DatabaseSettings(BaseModel):
    """Connection settings for one service's own database.

    `name`/`user` have no default here: each service must be explicit about
    which database and least-privilege role it connects as.
    """

    host: str = Field(default="localhost", min_length=1)
    port: int = Field(default=5432, ge=1, le=65535)
    name: str = Field(min_length=1)
    user: str = Field(min_length=1)
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
