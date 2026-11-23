from sqlalchemy import Engine, create_engine

from rheuma_db.settings import DatabaseSettings


def create_database_engine(settings: DatabaseSettings) -> Engine:
    """Create an engine without opening a connection or changing the schema."""
    return create_engine(
        settings.connection_url(),
        pool_pre_ping=True,
        connect_args={"connect_timeout": settings.connect_timeout},
    )
