"""Live end-to-end class: prepare the materials, then teach one turn.

This is the integration check that the unit tests cannot be: it starts the real server,
registers a teacher, asks the procedure service to prepare a class, then sends one tutor
turn with ``speak`` on so the reply is also rendered through the local VoiceStudio
backend. It prints the tutor's actual words, the tools it chose, and what came back.

The tutor is model-backed for this run (``HARNESS_TUTOR_PROVIDER=openai``), because an
offline instance has no one to ask a question of — the grounded fallback answers, which
is a different product. That switch is the operator decision the docs describe; this
script sets it for the lifetime of one subprocess and nothing else.

From source that is enough: ``config.load_dotenv`` finds ``backend/.env``. A frozen
backend has no ``.env`` beside it — the bundle ships code, not operator secrets — so the
provider URL and key can only arrive through the environment. ``--backend-exe`` therefore
also reads the same ``tutor.env`` ``BackendLauncher`` reads, and applies the same rules,
which makes this probe a test of the packaged app's real configuration path rather than a
test of a configuration nobody ships.

Run from ``harness/``::

    ui-tests/.venv/bin/python scripts/probe_class.py
    ui-tests/.venv/bin/python scripts/probe_class.py --concept algebra_2_permutations_and_combinations
    ui-tests/.venv/bin/python scripts/probe_class.py --message "why is it divided by r!?"
    ui-tests/.venv/bin/python scripts/probe_class.py --backend-exe ../outputs/Luminest.app/Contents/Resources/backend/LuminfestBackend/LuminfestBackend
"""

from __future__ import annotations

import argparse
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

DEFAULT_CONCEPT = 'algebra_2_permutations_and_combinations'
DEFAULT_MESSAGE = (
    'Teach me permutations and combinations. I want to understand why the two formulas '
    'differ, and I want to see something I can move. Then give me one question to try.')


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def call(url, payload=None, token=None, method=None, timeout=180):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method or ('POST' if data else 'GET'))
    request.add_header('content-type', 'application/json')
    if token:
        request.add_header('authorization', 'Bearer ' + token)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b'{}')
    except urllib.error.HTTPError as error:
        body = error.read()
        try:
            return error.code, json.loads(body or b'{}')
        except ValueError:
            return error.code, {'detail': body.decode('utf-8', 'replace')[:400]}


def fetch_bytes(url: str, token: str | None = None, timeout: float = 20.0):
    """``(status, bytes, content-type)`` — for the audio route, which returns an mp3."""
    request = urllib.request.Request(url)
    if token:
        request.add_header('authorization', 'Bearer ' + token)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            payload = response.read()
            return response.status, len(payload), response.headers.get('content-type', '')
    except urllib.error.HTTPError as error:
        return error.code, 0, error.headers.get('content-type', '') if error.headers else ''
    except (urllib.error.URLError, ConnectionError, TimeoutError):
        return 0, 0, ''


TUTOR_ENV_KEYS = ('HARNESS_TUTOR_PROVIDER', 'HARNESS_TUTOR_URL', 'HARNESS_TUTOR_MODEL',
                  'HARNESS_TUTOR_KEY', 'HARNESS_TUTOR_TIMEOUT_SECONDS')
TUTOR_ENV_ALIASES = (('DEEPSEEK_API_KEY', 'HARNESS_TUTOR_KEY'),
                     ('DEEPSEEK_BASE_URL', 'HARNESS_TUTOR_URL'))


def read_tutor_env(path: Path) -> dict[str, str]:
    """The operator's ``tutor.env``, filtered the way ``BackendLauncher`` filters it.

    Kept deliberately identical to the Swift reader: only ``HARNESS_TUTOR_*`` survives (a
    line that could repoint storage or network policy must not be honoured), and the
    ``DEEPSEEK_*`` aliases are resolved here because ``config.load_dotenv`` only aliases
    them while reading its own file.
    """
    try:
        text = path.read_text(encoding='utf-8')
    except OSError:
        return {}
    loaded: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or '=' not in stripped:
            continue
        key, _, value = stripped.partition('=')
        loaded[key.strip()] = value.strip().strip('"').strip("'")
    resolved = {k: v for k, v in loaded.items() if k in TUTOR_ENV_KEYS and v}
    for source, target in TUTOR_ENV_ALIASES:
        if loaded.get(source) and not resolved.get(target):
            resolved[target] = loaded[source]
    # A legacy tutor.env can still name the removed offline provider. BackendLauncher
    # treats that as unconfigured; so must this probe, or the backend refuses to boot
    # before any question is asked.
    if resolved.get('HARNESS_TUTOR_PROVIDER') == 'offline':
        resolved.pop('HARNESS_TUTOR_PROVIDER', None)
    return resolved


def wait_ready(base: str, timeout: float = 90.0) -> None:
    """Wait until the server answers *anything* on the health route.

    ``/api/v1/health`` is authenticated, so a live server answers 401 — which is a
    perfectly good sign of life. Only a refused connection means "not up yet".

    The deadline is computed from now, not passed as a timestamp: an earlier version took
    ``deadline=60.0``, compared it against ``time.time()``, and therefore gave up on the
    first iteration. Startup from source is roughly eight seconds (imports), so the
    budget has to be generous.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            status, _ = call(base + '/api/v1/health', timeout=2)
            if status < 500:
                return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(0.4)
    raise SystemExit('the backend did not come up')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--concept', default=DEFAULT_CONCEPT)
    parser.add_argument('--course', default='algebra_2')
    parser.add_argument('--advance-to', default='',
                        help='walk the plan until the current block is this kind (for '
                             'example "simulation"), the way a client advances after a '
                             'learner finishes each block')
    parser.add_argument('--message', action='append', default=None,
                        help='a learner turn; repeat the flag for a multi-turn lesson, and '
                             'the turns share one server and one conversation')
    parser.add_argument('--no-speak', action='store_true')
    parser.add_argument('--keep', action='store_true', help='leave the server running')
    parser.add_argument('--backend-exe', default='',
                        help='drive this frozen backend instead of scripts/run.py, so the '
                             'shipped bundle is what gets tested rather than the source tree')
    parser.add_argument('--tutor-env', default='',
                        help='operator tutor settings file; defaults to the one the packaged '
                             'app reads, and only applies with --backend-exe')
    parser.add_argument('--state-dir', default='',
                        help='where the server keeps its database and media; defaults to '
                             'harness/.tmp, and pointing it somewhere unrelated to this '
                             'checkout is what makes a portability run honest')
    args = parser.parse_args()

    port = free_port()
    # Not tempfile.mkdtemp(): that resolves to /var/folders, which the test sandbox
    # blocks, and the server then dies at startup with no visible error.
    state = (Path(args.state_dir).expanduser() if args.state_dir
             else HARNESS / '.tmp' / f'class-probe-{int(time.time())}-{port}')
    state.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update({
        'HARNESS_ENV': 'development',          # first account becomes the teacher
        'HARNESS_DATA_DIR': str(state),
        'HARNESS_DATABASE_URL': 'sqlite:///' + str(state / 'h.sqlite3'),
        'HARNESS_AUTO_CREATE': '1',
        'HARNESS_PORT': str(port),
        'HARNESS_SECRET': secrets.token_urlsafe(48),
        'HARNESS_TUTOR_PROVIDER': 'openai',    # this run only; see the module docstring
        'HARNESS_MEDIA_ENABLED': '1',
        'HARNESS_TUTOR_TIMEOUT_SECONDS': '240',
    })
    for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy'):
        env.pop(key, None)

    if args.backend_exe:
        # A frozen backend has no .env beside it, so a provider with no URL or key makes
        # ``Settings`` refuse to start at all. Feed it what the app feeds it.
        path = Path(args.tutor_env).expanduser() if args.tutor_env else (
            Path.home() / 'Library' / 'Application Support'
            / 'Luminfest Learning Harness' / 'tutor.env')
        supplied = read_tutor_env(path)
        if not supplied:
            raise SystemExit(f'no tutor settings at {path}; the frozen backend has no .env '
                             'of its own and would refuse to start with a provider set')
        for key, value in supplied.items():
            env.setdefault(key, value)
        missing = [k for k in ('HARNESS_TUTOR_URL', 'HARNESS_TUTOR_MODEL', 'HARNESS_TUTOR_KEY')
                   if not env.get(k)]
        if missing:
            raise SystemExit(f'{path} does not set {", ".join(missing)}')
        print(f'tutor settings: {path} (model {env["HARNESS_TUTOR_MODEL"]})')

    log = (state / 'server.log').open('w')
    if args.backend_exe:
        # The frozen binary takes ``--port`` (that is what BackendLauncher passes) and finds
        # its data files relative to the bundle, not the working directory, so running it
        # from the state dir is both realistic and harmless.
        command, cwd = [args.backend_exe, '--port', str(port)], str(state)
        print(f'backend: frozen bundle {args.backend_exe}')
    else:
        command, cwd = [str(PYTHON), 'scripts/run.py'], str(HARNESS / 'backend')
        print('backend: source tree (scripts/run.py)')
    server = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
    base = f'http://127.0.0.1:{port}'
    try:
        try:
            wait_ready(base)
        except SystemExit:
            log.flush()
            tail = (state / 'server.log').read_text(errors='replace')[-2000:]
            raise SystemExit(f'the backend did not come up on {port}. Server log:\n{tail}')
        status, body = call(base + '/api/v1/auth/register',
                            {'name': 'teacher', 'email': 'teacher@class.test',
                             'password': 'long-secret-password'})
        if status != 201:
            raise SystemExit(f'registration failed: {status} {body}')
        token = body['token']
        print(f"teacher registered: role={body['user']['role']}")

        # Enrol in the course the concept belongs to. Without this the procedure routes
        # answer 404 "Unknown concept for this course", because they resolve against the
        # learner's enrolment rather than the global graph.
        status, me = call(base + '/api/v1/me', {'course_id': args.course}, token,
                          method='PATCH')
        print(f"[enrol] PATCH /me course_id={args.course} -> {status} "
              f"(enrolled: {me.get('course_id')})")

        # 1. What the harness can prepare for this concept, before anyone speaks.
        # The TA prepares first: a concept with no curated video has none in its lesson,
        # so curating is what turns "no video" into "video".
        status, ready = call(f'{base}/api/v1/ta/prepare',
                             {'concept_id': args.concept}, token)
        print(f"\n[TA] POST /ta/prepare -> {status}")
        if status == 200:
            video = ready.get('video') or {}
            print(f"  figure : {ready['figure']['kind']} — {ready['figure']['title'][:60]}")
            print(f"  video  : {'curated: ' + video.get('title', '') if video.get('curated') else 'none — ' + str(video.get('reason') or '')}")
            print(f"  ready  : {ready['ready']}")

        status, preview = call(f'{base}/api/v1/procedure/{args.concept}', token=token)
        print(f"\n[prepare] GET /procedure/{args.concept} -> {status}")
        if status == 200:
            plan = preview.get('plan') or {}
            print(f"  plan: {len(plan.get('blocks') or [])} block(s), "
                  f"~{plan.get('minutes') or '?'} min")
            for block in plan.get('blocks') or []:
                print(f"    - {block.get('kind') or block.get('activity')}: "
                      f"{str(block.get('title') or '')[:60]}")
            for entry in plan.get('skipped') or []:
                print(f"    (skipped {entry.get('kind')}: {str(entry.get('reason'))[:70]})")

        status, prepared = call(f'{base}/api/v1/procedure/{args.concept}/start', {}, token)
        print(f"\n[start] POST /procedure/{args.concept}/start -> {status}")
        run = {}
        if status == 200:
            run = prepared.get('run') or prepared
            print(f"  run: {run.get('run_id') or '(unnamed)'} · "
                  f"blocks: {len(run.get('blocks') or [])}")
            for block in run.get('blocks') or []:
                detail = block.get('image_unavailable') or block.get('image') or ''
                print(f"    - {block.get('kind') or block.get('activity')}: "
                      f"{str(block.get('title') or '')[:55]} {str(detail)[:40]}")
        else:
            print(f"  {json.dumps(prepared)[:300]}")

        # 2b. Walk the plan the way a client does after a learner finishes a block. Without
        # this the tutor is pinned to block 1 for the whole conversation: the diagnostic
        # asks for evidence, the learner answers in prose, and nothing records it, so the
        # run never advances and every later request is answered with the same question.
        if args.advance_to and run.get('run_id'):
            for _ in range(8):
                current = run.get('current') or {}
                if str(current.get('kind') or current.get('activity') or '') == args.advance_to:
                    break
                order = int(current.get('order') or 0)
                if not order:
                    break
                status, run = call(f"{base}/api/v1/procedure/runs/{run['run_id']}/advance",
                                   {'order': order, 'outcome': 'done', 'seconds': 90}, token)
                moved = (run.get('current') or {})
                print(f"  [advance] block {order} done -> {status} · now "
                      f"{moved.get('kind') or moved.get('activity') or '(finished)'}")
                if status != 200:
                    print(f"    {json.dumps(run)[:300]}")
                    break
            current = run.get('current') or {}
            print(f"  [block] teaching inside: "
                  f"{current.get('kind') or current.get('activity') or '(none)'} — "
                  f"{str(current.get('title') or '')[:60]}")

        # 2. The TA's asset check, which is what decides whether the class is ready.
        status, sweep = call(f'{base}/api/v1/ta/sweep',
                             {'concept_id': args.concept,
                              'signals': {'active_seconds': 120, 'window_seconds': 300}}, token)
        print(f"\n[sweep] POST /ta/sweep -> {status}")
        if status == 200:
            print(f"  figure : {sweep['figure']['kind']} — {sweep['figure']['title']}")
            print(f"  ready  : {sweep['ready']} | {sweep['report'] or 'no problems'}")
            for entry in sweep.get('plan') or []:
                print(f"  repair : {entry['substitute']} now, then {entry['fix']}")

        # 3. The lesson: one turn per learner message, in one conversation.
        messages = args.message or [DEFAULT_MESSAGE]
        for number, message in enumerate(messages, start=1):
            print(f'\n[teach {number}/{len(messages)}] you: {message}\n')
            started = time.time()
            status, turn = call(base + '/api/v1/agent/chat',
                                {'message': message, 'speak': not args.no_speak,
                                 'context': {'concept_id': args.concept,
                                             'course_id': args.course}},
                                token)
            elapsed = time.time() - started
            print(f'[teach {number}] POST /agent/chat -> {status} in {elapsed:.1f}s')
            if status != 200:
                print(json.dumps(turn)[:600])
                return 1

            tools = [event.get('label') or event.get('name')
                     for event in turn.get('events') or ()
                     if event.get('type') in ('tool_call', 'tool_result')]
            print(f"  answered_by: {turn.get('answered_by')} | finish: {turn.get('finish_reason')}")
            print(f"  tools      : {tools or 'none'}")
            speech = turn.get('speech') or {}
            clips = speech.get('clips') or ([speech] if speech.get('digest') else [])
            print(f"  speech     : kind={speech.get('kind')} delivery={speech.get('delivery')} "
                  f"clips={len(clips)} first={speech.get('state')}")
            # A reply is spoken as a series of clips, because one utterance of a paragraph
            # is a silence the length of the lesson. Poll them in order and report each:
            # this is the same loop the app runs while it plays.
            ready = 0
            for index, clip in enumerate(clips):
                if not clip.get('digest'):
                    continue
                status, info = call(f"{base}/api/v1/media/audio/{clip['digest']}/state",
                                    token=token)
                for _ in range(240):
                    if info.get('state') in ('ready', 'failed'):
                        break
                    time.sleep(1.0)
                    status, info = call(f"{base}/api/v1/media/audio/{clip['digest']}/state",
                                        token=token)
                if info.get('state') == 'ready':
                    ready += 1
                print(f"    clip {index + 1}/{len(clips)}: {info.get('state')} · "
                      f"{info.get('bytes') or 0} bytes"
                      + (f" · {info.get('reason')}" if info.get('reason') else ''))
            print(f"  audio      : {ready}/{len(clips)} clip(s) rendered")
            print('\n--- tutor ---')
            print(turn.get('message') or '(empty)')
            print('--- end ---')
        return 0
    finally:
        if not args.keep:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
        else:
            print(f'\nserver left running on {base} (data dir {state})')


if __name__ == '__main__':
    sys.exit(main())
