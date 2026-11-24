"""Each Compose service receives only its own password. No SQL access in the legacy k8s stack."""
import os
import sys
from contextlib import closing
from pathlib import Path

from pg8000.dbapi import connect


def check_database(service):
    db = f'mis_{service}'
    with closing(connect(host=os.environ['PGHOST'], port=5432, database=db,
                         user=f'{db}_app', timeout=4,
                         password=Path('/run/secrets/db-password').read_text().strip())) as conn:
        # Also verifies that owner migrations ran; pg_isready alone cannot do that.
        conn.cursor().execute('SELECT message_id FROM public.inbox_messages LIMIT 0')


if __name__ == '__main__':
    check_database(sys.argv[1])
