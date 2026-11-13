from alembic import context

from app.database.base import Base
from app.database.connection import create_database_engine
import app.database.models  # Register all models for autogenerate/check.
from app.settings import Settings

config = context.config
target_metadata = Base.metadata


def configure_and_run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    supplied_connection = config.attributes.get("connection")
    if supplied_connection is not None:
        configure_and_run(supplied_connection)
        return
    database = config.attributes.get("database_settings") or Settings().database
    engine = create_database_engine(database)
    try:
        with engine.connect() as connection:
            configure_and_run(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    context.configure(dialect_name="postgresql", target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    run_migrations_online()
