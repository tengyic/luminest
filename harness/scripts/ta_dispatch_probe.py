#!/usr/bin/env python3
"""Does the TA actually work when the teacher asks it something mid-lesson?

``/ta/sweep`` is the silent interval check: deterministic, no model, no job. This probes the
other half — ``POST /ta/dispatch``, which runs a real agent turn in the background so the
teacher can keep talking while an asset is researched or built. It starts one server,
registers a teacher, dispatches a job, polls ``/ta/status`` to completion and prints what the
TA produced.

The point is the division of labour: the teacher's turn must not block on this, and the
result must arrive in a feed the teacher pulls rather than on the learner's screen.
"""

from __future__ import annotations

import json
import secrets
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from probe_class import HARNESS, PYTHON, call, free_port, wait_ready   # noqa: E402

CONCEPT = 'algebra_2_permutations_and_combinations'
MESSAGE = ('The learner just asked whether order matters in a locker combination. Build me '
           'a quick interactive that shows one selection counted both ways, and a video '
           'that explains it. Report back, do not present anything on screen.')


def main() -> int:
    port = free_port()
    state = HARNESS / '.tmp' / f'ta-probe-{int(time.time())}-{port}'
    state.mkdir(parents=True, exist_ok=True)
    import os
    env = dict(os.environ)
    env.update({'HARNESS_ENV': 'development', 'HARNESS_DATA_DIR': str(state),
                'HARNESS_DATABASE_URL': 'sqlite:///' + str(state / 'h.sqlite3'),
                'HARNESS_AUTO_CREATE': '1', 'HARNESS_PORT': str(port),
                'HARNESS_SECRET': secrets.token_urlsafe(48),
                'HARNESS_TUTOR_PROVIDER': 'openai',
                'HARNESS_MEDIA_ENABLED': '1',
                'HARNESS_TUTOR_TIMEOUT_SECONDS': '240'})
    for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy'):
        env.pop(key, None)
    log = (state / 'server.log').open('w')
    server = subprocess.Popen([str(PYTHON), 'scripts/run.py'], cwd=str(HARNESS / 'backend'),
                              env=env, stdout=log, stderr=subprocess.STDOUT)
    base = f'http://127.0.0.1:{port}'
    try:
        wait_ready(base)
        status, body = call(base + '/api/v1/auth/register',
                            {'name': 'teacher', 'email': 'ta@class.test',
                             'password': 'long-secret-password'})
        token = body['token']
        call(base + '/api/v1/me', {'course_id': 'algebra_2'}, token, method='PATCH')
        print(f'teacher ready on {base}')

        started = time.time()
        status, job = call(base + '/api/v1/ta/dispatch',
                           {'message': MESSAGE, 'concept_id': CONCEPT}, token)
        print(f'\n[dispatch] POST /ta/dispatch -> {status} in {time.time() - started:.1f}s')
        print(f'  {json.dumps(job)[:400]}')
        if status not in (200, 202):
            return 1

        # The teacher's own turn must not wait on this. Report how long dispatch took to
        # return versus how long the job takes to finish: those are different numbers, and
        # the gap is the whole reason the job exists.
        deadline = time.time() + 300
        last = ''
        while time.time() < deadline:
            status, body = call(base + '/api/v1/ta/status', token=token)
            rows = body.get('jobs') or []
            snapshot = [(r.get('id'), r.get('status')) for r in rows]
            if snapshot != last:
                print(f'  status: {snapshot}  ({time.time() - started:.0f}s)')
                last = snapshot
            if rows and all(r.get('status') in ('done', 'failed') for r in rows):
                break
            time.sleep(3)

        status, body = call(base + '/api/v1/ta/results?since=0', token=token)
        print(f'\n[results] GET /ta/results -> {status}')
        print(json.dumps(body.get('results') or body, indent=2)[:2500])
        return 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == '__main__':
    sys.exit(main())
