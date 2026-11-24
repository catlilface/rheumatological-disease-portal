"""Run inside each service image: real app login, grants and synthetic SQL invariants."""
import os
from contextlib import closing
from pathlib import Path
import sys

from pg8000.dbapi import DatabaseError, connect

owner, = sys.argv[1:]
password = Path('/run/secrets/db-password').read_text().strip()
owners = ('iam', 'screening', 'content', 'reporting', 'files', 'ai')


def connection(target):
    return connect(host=os.environ['PGHOST'], database=f'mis_{target}', user=f'mis_{owner}_app', password=password, timeout=5)


with closing(connection(owner)) as conn:
    cursor = conn.cursor()
    cursor.execute('SELECT current_database(), current_user')
    assert cursor.fetchone() == [f'mis_{owner}', f'mis_{owner}_app']
    cursor.execute('SELECT message_id FROM public.inbox_messages LIMIT 0')
    cursor.execute('SELECT event_id FROM public.outbox_events LIMIT 0')
    for forbidden in ('CREATE TABLE public.no_ddl(i int)', 'CREATE TEMP TABLE no_temp(i int)', 'DELETE FROM migration.schema_migrations WHERE false'):
        try:
            cursor.execute(forbidden)
        except DatabaseError as exc:
            assert exc.args[0]['C'] == '42501', exc.args[0]['C']
        else:
            raise AssertionError(f'{owner}: forbidden SQL succeeded')
        finally:
            conn.rollback()  # Even an unexpectedly successful DDL probe must leave no trace.
    try:
        cursor.execute(sys.stdin.read())
    finally:
        conn.rollback()

for target in owners:
    if target == owner:
        continue
    try:
        with closing(connection(target)):
            raise AssertionError(f'Unexpected CONNECT {owner} -> {target}')
    except DatabaseError as exc:
        assert exc.args[0]['C'] == '42501', exc.args[0]['C']
print(f'OK: {owner}, own DB, denied DDL/history, five denied foreign DBs, domain invariants')
