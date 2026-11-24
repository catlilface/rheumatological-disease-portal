"""Run Screening tests against a disposable PostgreSQL with the MIS-27 roles."""

import os
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from secrets import token_hex
from tempfile import TemporaryDirectory
from time import monotonic, sleep

from pg8000.dbapi import DatabaseError, InterfaceError, connect


ROOT = Path(__file__).resolve().parents[3]
SCREENING = ROOT / "services/screening"
RUNTIME = ROOT / "packages/service-runtime"
APP = "mis_screening_app"
MIGRATOR = "mis_screening_migrator"


def docker(*args, env=None):
    return subprocess.check_output(["docker", *args], text=True, env=env).strip()


def prepare_database(port, admin_password, app_password):
    def open_db(user, password, database="mis_screening"):
        return connect(host="127.0.0.1", port=port, user=user, password=password,
                       database=database, timeout=5)

    deadline = monotonic() + 45
    while True:
        try:
            admin = open_db("postgres", admin_password, "postgres")
            break
        except (DatabaseError, InterfaceError, OSError):
            if monotonic() >= deadline:
                raise
            sleep(1)

    migrator_password = token_hex(16)
    with closing(admin) as connection, closing(connection.cursor()) as cursor:
        connection.autocommit = True
        cursor.execute(f"CREATE ROLE {MIGRATOR} LOGIN PASSWORD '{migrator_password}'")
        cursor.execute(f"CREATE ROLE {APP} LOGIN PASSWORD '{app_password}'")
        cursor.execute(f"CREATE DATABASE mis_screening OWNER {MIGRATOR}")
        cursor.execute("REVOKE ALL ON DATABASE mis_screening FROM PUBLIC")
        cursor.execute(f"GRANT CONNECT ON DATABASE mis_screening TO {APP}")

    with closing(open_db("postgres", admin_password)) as connection, closing(connection.cursor()) as cursor:
        cursor.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
        cursor.execute(f"GRANT USAGE ON SCHEMA public TO {APP}")
        cursor.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {MIGRATOR} IN SCHEMA public "
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP}",
        )
        connection.commit()

    migrations = [ROOT / "infra/db/common/001_messaging.sql", *sorted((SCREENING / "migrations").glob("*.sql"))]
    with closing(open_db(MIGRATOR, migrator_password)) as connection, closing(connection.cursor()) as cursor:
        for migration in migrations:
            cursor.execute(migration.read_text(encoding="utf-8").split("-- migrate:down", 1)[0])
            connection.commit()

    with closing(open_db(APP, app_password)) as connection, closing(connection.cursor()) as cursor:
        cursor.execute((ROOT / "infra/db/tests/screening.sql").read_text(encoding="utf-8"))
        connection.rollback()


def main():
    admin_password, app_password = token_hex(16), token_hex(16)
    with TemporaryDirectory() as proto_dir:
        contracts = sorted(path.relative_to(ROOT).as_posix() for path in (ROOT / "contracts").glob("*/v1/*.proto"))
        subprocess.run(
            [sys.executable, "-m", "grpc_tools.protoc", "-I.", f"--python_out={proto_dir}",
             f"--grpc_python_out={proto_dir}", *contracts],
            cwd=ROOT, check=True,
        )
        container = docker(
            "run", "--detach", "--rm", "--tmpfs", "/var/lib/postgresql",
            "--env", "POSTGRES_PASSWORD", "--publish", "127.0.0.1::5432", "postgres:18.7-alpine3.23",
            env={**os.environ, "POSTGRES_PASSWORD": admin_password},
        )
        try:
            port = int(docker("port", container, "5432/tcp").rsplit(":", 1)[-1])
            prepare_database(port, admin_password, app_password)
            python_paths = [proto_dir, str(RUNTIME), os.environ.get("PYTHONPATH", "")]
            subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "services/screening/tests", "-v"],
                cwd=ROOT, check=True,
                env={
                    **os.environ, "PYTHONPATH": os.pathsep.join(filter(None, python_paths)),
                    "SCREENING_TEST_POSTGRES_PORT": str(port),
                    "SCREENING_TEST_POSTGRES_PASSWORD": app_password,
                    "PYTHONUTF8": "1",
                },
            )
        finally:
            docker("stop", container)


if __name__ == "__main__":
    main()
