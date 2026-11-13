from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={
        "ix": "%(table_name)s_%(column_0_N_name)s_idx",
        "uq": "%(table_name)s_%(column_0_N_name)s_key",
        "pk": "%(table_name)s_pkey",
        "fk": "%(table_name)s_%(column_0_N_name)s_fkey",
        "ck": "%(table_name)s_%(constraint_name)s_check",
    })
