from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "%(table_name)s_%(column_0_N_name)s_idx",
    "uq": "%(table_name)s_%(column_0_N_name)s_key",
    "pk": "%(table_name)s_pkey",
    "fk": "%(table_name)s_%(column_0_N_name)s_fkey",
    "ck": "%(table_name)s_%(constraint_name)s_check",
}


class Base(DeclarativeBase):
    """Shared declarative base.

    Each service runs in its own process and virtualenv, so importing this
    one `Base` per service never mixes tables across services in the same
    `MetaData` — there is no single process that imports two services' models.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
