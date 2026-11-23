"""Shared isolation-test helper, reused by every service's test_isolation.py
instead of each service re-implementing the same cross-database probe."""

import psycopg

ALL_SERVICES = ("iam", "screening", "content", "reporting", "files", "ai")


def other_services(service: str) -> tuple[str, ...]:
    if service not in ALL_SERVICES:
        raise ValueError(f"unknown service {service!r}; expected one of {ALL_SERVICES}")
    return tuple(name for name in ALL_SERVICES if name != service)


def can_connect(*, host: str, port: int, dbname: str, user: str, password: str) -> bool:
    """True if a connection succeeds; False if Postgres denies it (e.g. no CONNECT grant)."""
    try:
        with psycopg.connect(
            host=host, port=port, dbname=dbname, user=user, password=password, connect_timeout=3,
        ):
            return True
    except psycopg.OperationalError:
        return False
