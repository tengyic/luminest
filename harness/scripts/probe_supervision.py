"""Live check: the supervision route against a real server, from source."""
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
PYTHON = HARNESS / 'ui-tests' / '.venv' / 'bin' / 'python'


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def call(url, payload=None, token=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method or ('POST' if data else 'GET'))
    request.add_header('content-type', 'application/json')
    if token:
        request.add_header('authorization', 'Bearer ' + token)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=20) as response:
            return response.status, json.loads(response.read() or b'{}')
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b'{}')


def main():
    port = free_port()
    state = Path(tempfile.mkdtemp(prefix='supervision-probe-'))
    env = dict(os.environ)
    env.update({'HARNESS_ENV': 'test', 'HARNESS_DATA_DIR': str(state),
                'HARNESS_DATABASE_URL': 'sqlite:///' + str(state / 'h.sqlite3'),
                'HARNESS_AUTO_CREATE': '1', 'HARNESS_PORT': str(port),
                'HARNESS_SECRET': secrets.token_urlsafe(48),
                'HARNESS_ALLOWED_HOSTS': '127.0.0.1,localhost'})
    server = subprocess.Popen(
        [str(PYTHON), '-m', 'uvicorn', 'app.main:create_app', '--factory',
         '--host', '127.0.0.1', '--port', str(port), '--log-level', 'warning'],
        cwd=HARNESS / 'backend', env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    base = f'http://127.0.0.1:{port}/api/v1'
    try:
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            try:
                if call(base + '/health')[1].get('ready'):
                    break
            except (OSError, ValueError):
                time.sleep(0.2)
        else:
            raise SystemExit('server never became ready')

        status, body = call(base + '/auth/register',
                            {'name': 'Probe', 'email': 'probe@example.com',
                             'password': 'probe-password'})
        assert status == 201, (status, body)
        token = body['token']
        print('register:', status, body['user']['role'])

        status, body = call(base + '/supervision', token=token)
        print('GET /supervision:', status, sorted(body))
        print('  posture:', body['posture'])

        for label, payload in [
            ('present', {'idle_seconds': 5, 'active_seconds': 240, 'scroll_events': 6}),
            ('drifting', {'idle_seconds': 120}),
            ('away', {'idle_seconds': 400, 'rest_quota_total': 2}),
            ('away, no breaks left', {'idle_seconds': 400, 'rest_quota_total': 2,
                                      'rest_quota_used': 2}),
            ('resting', {'idle_seconds': 900, 'resting': True}),
            ('variant failed', {'variant_result': 'wrong'}),
            ('during a test', {'variant_result': 'wrong', 'item_context': 'test'}),
        ]:
            status, body = call(base + '/supervision/assess', payload, token=token)
            print(f'POST assess [{label}]:', status, body['state'], '->', body['move']['kind'])

        # A client that tries to state its own mastery must be refused, not trusted.
        status, body = call(base + '/supervision/assess', {'mastery': 0.99}, token=token)
        print('POST assess [client claims mastery]:', status, str(body.get('detail'))[:90])

        status, body = call(base + '/supervision/assess', {}, token=None)
        print('POST assess [no token]:', status, str(body.get('detail'))[:60])
    finally:
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()
        for line in (server.stderr.read() or b'').decode(errors='replace').splitlines()[-3:]:
            print('server:', line)


if __name__ == '__main__':
    sys.exit(main())
