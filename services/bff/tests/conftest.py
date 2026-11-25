"""Black-box checks: build the Go executable once; isolate state per test over real TLS."""
import os
from pathlib import Path
import re
import ssl
import subprocess

import httpx
import pytest

SERVICE = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='session')
def executable(tmp_path_factory):
    tmp = tmp_path_factory.mktemp('go-bff')
    (tmp / 'contracts').symlink_to(SERVICE.parents[1] / 'contracts', target_is_directory=True)
    subprocess.run(['go', 'build', '-o', str(tmp / 'bff'), './cmd/bff'], cwd=SERVICE, check=True)
    (tmp / 'ssl.cnf').write_text('[req]\nprompt=no\ndistinguished_name=name\nx509_extensions=ext\n'
                                 '[name]\nCN=localhost\n[ext]\nsubjectAltName=DNS:localhost\nbasicConstraints=CA:TRUE\n')
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                    '-config', 'ssl.cnf', '-keyout', 'key.pem', '-out', 'cert.pem'], cwd=tmp, check=True, capture_output=True)
    return tmp


@pytest.fixture
def server(executable):
    env = {'PATH': os.environ['PATH'], 'MOCK_MODERATOR_PASSWORD': 'demo-moderator'}
    with subprocess.Popen(['./bff', '-addr', '127.0.0.1:0', '-tls-cert', 'cert.pem', '-tls-key', 'key.pem'],
                          cwd=executable, env=env, stderr=subprocess.PIPE, text=True) as proc:
        try:
            line = proc.stderr.readline()
            port = re.search(r'address=127\.0\.0\.1:(\d+)', line)
            assert port, line
            # Drain logs to avoid blocking the server during longer workflows.
            from threading import Thread
            reader = Thread(target=lambda: list(proc.stderr), daemon=True)
            reader.start()
            yield 'https://localhost:' + port[1], ssl.create_default_context(cafile=str(executable / 'cert.pem'))
        finally:
            proc.terminate()
            proc.wait(timeout=15)


@pytest.fixture
async def client(server):
    url, context = server
    async with httpx.AsyncClient(base_url=url, verify=context, trust_env=False) as client:
        yield client


@pytest.fixture
def anyio_backend():
    return 'asyncio'
