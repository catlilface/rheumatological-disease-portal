"""Local AI process: its projection database is ready, no inference or API yet."""
import signal
from threading import Event

from database import check_database

if __name__ == '__main__':
    stopped = Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopped.set())
    check_database('ai')
    stopped.wait()
