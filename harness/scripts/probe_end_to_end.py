"""End-to-end: one learner walks the whole product, against the frozen backend.

``probe_class.py`` answers "does a class teach?". This answers a bigger question: can a
person actually use the shipped thing from the first screen to a spoken answer, with every
surface the app reaches for alive? The two are different failures. A build can teach
perfectly and still 404 the gallery, serve an empty knowledge graph, or refuse the
registration the launch gate now demands.

It runs the frozen binary in ``desktop`` mode - the environment the app sets - so the
launch gate is live and media defaults are the shipped ones. That matters: in
``development`` the gate is off, so a regression there is invisible to every other check.

Everything is asserted; a failed step prints what came back and the script exits non-zero.
Nothing here is written to the operator's real database: the state directory is fresh.

Run from ``harness/``::

    ui-tests/.venv/bin/python scripts/probe_end_to_end.py \
        --backend-exe ../outputs/Luminfest.app/Contents/Resources/backend/LuminfestBackend/LuminfestBackend

Add ``--skip-chat`` to skip the one model-backed turn (the slowest step, and the only one
that needs a reachable provider).
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from probe_class import (HARNESS, PYTHON, call, free_port, read_tutor_env,  # noqa: E402
                         wait_ready)

CONCEPT = 'algebra_2_permutations_and_combinations'
COURSE = 'algebra_2'
PASSWORD = 'long-secret-password'

#: Feature routers, each proved by a status that is not 404. Copied deliberately rather
#: than imported: this script must be runnable against a *frozen* backend, which has no
#: ``scripts/package.py`` next to it.
FEATURE_ROUTES = ('/deck', '/flashcards', '/my-courses', '/author/methodology',
                  '/images/library', '/create/search', '/playground', '/capabilities',
                  '/procedure', '/stream/status')

failures: list[str] = []


def raw_status(url: str, timeout: float = 10.0) -> int:
    """Status only, for routes that answer HTML.

    ``probe_class.call`` parses every response as JSON, which is right for the API and
    wrong for ``/`` - the page is served as text/html, so decoding it raised
    ``JSONDecodeError`` and the whole journey died at the first static page. A status is
    all this probe needs from a page anyway.
    """
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(urllib.request.Request(url), timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except (urllib.error.URLError, ConnectionError, TimeoutError):
        return 0


def recorded_consent(database: Path, email: str) -> dict:
    """What the row actually says about consent, read from the probe's own database.

    The API deliberately does not return these columns, so asserting on the response
    proved nothing - ``terms_accepted_at`` was simply absent from the schema. Consent is
    a compliance claim, so it is checked where it is stored. The probe owns this database
    (``HARNESS_DATABASE_URL`` points into the state directory), which is why reading it
    directly is safe here and would not be in a general-purpose test.
    """
    import sqlite3
    if not database.is_file():
        return {}
    with sqlite3.connect(database) as db:
        db.row_factory = sqlite3.Row
        row = db.execute('select age_confirmed_at, terms_accepted_at, terms_version '
                         'from users where email = ?', (email,)).fetchone()
    return dict(row) if row else {}


def check(label: str, ok: bool, detail: str = '') -> bool:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  [{detail}]" if detail else ''))
    if not ok:
        failures.append(label + (f' ({detail})' if detail else ''))
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--backend-exe', default='')
    parser.add_argument('--tutor-env', default='')
    parser.add_argument('--skip-chat', action='store_true')
    parser.add_argument('--media', action='store_true',
                        help='also allow outbound media (search/curation); off is what '
                             'the shipped desktop build does')
    args = parser.parse_args()

    port = free_port()
    state = HARNESS / '.tmp' / f'e2e-{int(time.time())}-{port}'
    state.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update({
        'HARNESS_ENV': 'desktop',          # what the app sets; gate on, media off
        'HARNESS_DATA_DIR': str(state),
        'HARNESS_DATABASE_URL': 'sqlite:///' + str(state / 'h.sqlite3'),
        'HARNESS_AUTO_CREATE': '1',
        'HARNESS_PORT': str(port),
        'HARNESS_SECRET': secrets.token_urlsafe(48),
        'HARNESS_ALLOWED_HOSTS': 'localhost,127.0.0.1',
    })
    if args.media:
        env['HARNESS_MEDIA_ENABLED'] = '1'
    for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy'):
        env.pop(key, None)

    if args.backend_exe:
        path = Path(args.tutor_env).expanduser() if args.tutor_env else (
            Path.home() / 'Library' / 'Application Support'
            / 'Luminfest Learning Harness' / 'tutor.env')
        supplied = read_tutor_env(path)
        if not supplied:
            raise SystemExit(f'no tutor settings at {path}')
        for key, value in supplied.items():
            env.setdefault(key, value)
        env['HARNESS_TUTOR_PROVIDER'] = 'openai'
        command = [args.backend_exe, '--port', str(port)]
        print(f'backend: frozen bundle, desktop mode, state {state}')
    else:
        env['HARNESS_TUTOR_PROVIDER'] = 'openai'
        command = [str(PYTHON), 'scripts/run.py']
        print(f'backend: source tree, desktop mode, state {state}')

    log = (state / 'server.log').open('w')
    server = subprocess.Popen(command, cwd=str(state) if args.backend_exe else str(HARNESS / 'backend'),
                              env=env, stdout=log, stderr=subprocess.STDOUT)
    base = f'http://127.0.0.1:{port}'
    api = base + '/api/v1'
    try:
        wait_ready(base)
        print('\n[1] the server answers')

        status, health = call(api + '/health', timeout=10)
        check('health ready', status == 200 and health.get('ready') is True, f'{status}')
        check('schema version present', bool(health.get('schema_version')),
              str(health.get('schema_version')))

        print('\n[2] the launch gate (this is what desktop mode changes)')
        status, body = call(api + '/auth/register',
                            {'name': 'no gate', 'email': 'n@x.test', 'password': PASSWORD})
        check('registration without attestation is refused', status == 422, f'{status}')
        check('and says why', '13 or older' in json.dumps(body), str(body.get('detail'))[:60])

        email = f'e2e-{secrets.token_hex(6)}@example.invalid'
        status, body = call(api + '/auth/register',
                            {'name': 'E2E learner', 'email': email, 'password': PASSWORD,
                             'age_confirmed': True, 'accept_terms': True})
        ok = check('registration with attestation succeeds', status == 201, f'{status}')
        user = body.get('user') or {}
        if ok:
            check('first account is the teacher', user.get('role') == 'teacher',
                  str(user.get('role')))
            check('telemetry consent defaults off', user.get('telemetry_consent') is False,
                  str(user.get('telemetry_consent')))
            consent = recorded_consent(state / 'h.sqlite3', email)
            check('age attestation is stored', bool(consent.get('age_confirmed_at')),
                  str(consent.get('age_confirmed_at')))
            check('terms acceptance is stored', bool(consent.get('terms_accepted_at')),
                  str(consent.get('terms_version')))

        print('\n[3] sign in and enrol')
        status, body = call(api + '/auth/login', {'email': email, 'password': PASSWORD})
        token = body.get('token') if status == 200 else None
        check('login returns a token', bool(token), f'{status}')
        if not token:
            raise SystemExit('cannot continue without a token')
        check('login is the same account', (body.get('user') or {}).get('id') == user.get('id'))

        status, me = call(api + '/me', {'course_id': COURSE}, token, method='PATCH')
        check('enrolment', status == 200 and me.get('course_id') == COURSE,
              f'{status} {me.get("course_id")}')

        print('\n[4] the data packs a learner actually reads')
        status, graph = call(api + '/knowledge-graph', token=token)
        nodes = (graph.get('nodes') or [])
        edges = (graph.get('edges') or [])
        check('knowledge graph populated', status == 200 and len(nodes) >= 50 and edges,
              f'{len(nodes)} nodes, {len(edges)} edges')
        status, sources = call(api + '/media/sources', token=token)
        check('media sources', status == 200 and bool(sources.get('sources')),
              str(len(sources.get('sources') or [])))
        status, sims = call(api + '/simulations', token=token)
        units = sims.get('units') or []
        mapped = sims.get('mapped')
        check('simulation map answers', status == 200 and isinstance(mapped, int),
              f'{status} mapped={mapped}')
        # ``algebra_2`` has no PhET mappings at all - only six of the twelve courses do
        # (biology 10, chemistry 15, computer_science 3, earth_space_science 12,
        # integrated_math_1 17, physics 17). An empty gallery for this course is a content
        # gap, not a broken route, and the lesson still gets its simulation block from the
        # local figure engine. Reported, deliberately not failed: a probe that fails on
        # known content coverage stops being run.
        print(f'        (simulation gallery: {len(units)} unit(s) for {COURSE} - '
              f'content coverage, not a route failure)')
        status, legal = call(api + '/legal')
        check('legal documents served', status == 200 and bool(legal.get('documents')),
              str(len(legal.get('documents') or [])))

        print('\n[5] the static pages (app root, not /api/v1)')
        for page in ('/', '/playground'):
            check(f'{page} serves a page', raw_status(base + page) == 200)

        print('\n[6] every feature router is mounted')
        for route in FEATURE_ROUTES:
            status, _ = call(api + route, token=token)
            check(f'{route} is not 404', status != 404, f'{status}')

        print('\n[7] one practice question, answered')
        status, question = call(api + '/questions/next?mode=practice', token=token)
        options = (question.get('options') or [])
        check('a question was served', status == 200 and bool(question.get('id')),
              f'{status} {len(options)} options')
        if options:
            status, answer = call(api + '/attempts',
                                  {'question_id': question['id'],
                                   'option_id': options[0]['id'],
                                   'receipt': question.get('receipt'),
                                   'client_event_id': secrets.token_hex(16),
                                   'elapsed_seconds': 0, 'confidence': 0.5}, token)
            check('the answer is scored', status in (200, 201)
                  and isinstance(answer.get('correct'), bool),
                  f'{status} correct={answer.get("correct")}')
            status, dashboard = call(api + '/dashboard', token=token)
            attempts = ((dashboard.get('stats') or {}).get('attempts') or 0)
            check('the attempt persisted', attempts >= 1, str(attempts))

        print('\n[8] the TA prepares a class, and the plan opens with the video')
        status, ready = call(api + '/ta/prepare', {'concept_id': CONCEPT}, token)
        figure = (ready.get('figure') or {})
        video = (ready.get('video') or {})
        check('TA prepare', status == 200, f'{status}')
        check('a figure exists', bool(figure.get('kind')), str(figure.get('kind')))
        check('a curated video exists', bool(video.get('curated')),
              str(video.get('title') or video.get('reason'))[:60])

        status, preview = call(f'{api}/procedure/{CONCEPT}', token=token)
        plan = (preview.get('plan') or {})
        kinds = [block.get('kind') or block.get('activity') for block in plan.get('blocks') or []]
        check('the plan has blocks', status == 200 and len(kinds) >= 3, str(kinds))
        check('the plan includes the video', 'video' in kinds, str(kinds))
        check('the deck is skipped, with a reason', any(
            entry.get('kind') == 'deck' for entry in plan.get('skipped') or []),
            str([e.get('kind') for e in plan.get('skipped') or []]))

        status, started = call(f'{api}/procedure/{CONCEPT}/start', {}, token)
        run = started.get('run') or started
        check('the run starts', status == 200 and bool(run.get('blocks')),
              f'{status} {len(run.get("blocks") or [])} blocks')

        print('\n[9] supervision and rewards')
        # Flat fields, not a nested ``signals`` object: ``AssessInput`` sets
        # ``extra='forbid'``, so the nested form is a 422 that reads like a broken route.
        status, reading = call(api + '/supervision/assess',
                               {'concept_id': CONCEPT, 'idle_seconds': 40,
                                'active_seconds': 120, 'window_seconds': 300},
                               token)
        check('supervision answers', status == 200 and bool(reading.get('state')),
              f'{status} {reading.get("state")}')
        check('with a move', bool(reading.get('move')), str(reading.get('move')))
        status, events = call(api + '/rewards/events', token=token)
        check('rewards events readable', status == 200, f'{status}')

        if not args.skip_chat:
            print('\n[10] one teaching turn, spoken')
            status, turn = call(api + '/agent/chat',
                                {'message': 'Explain why the two formulas differ, then give me '
                                            'one question to try.',
                                 'speak': True,
                                 'context': {'concept_id': CONCEPT, 'course_id': COURSE}},
                                token, timeout=300)
            message = (turn.get('message') or '')
            check('the tutor replies', status == 200 and len(message) > 40,
                  f'{status} {len(message)} chars')
            check('a model answered', bool(turn.get('answered_by')),
                  str(turn.get('answered_by')))
            speech = turn.get('speech') or {}
            clips = speech.get('clips') or ([speech] if speech.get('digest') else [])
            check('the reply is queued for speech', bool(clips), str(len(clips)))
            ready_clips = 0
            for clip in clips:
                if not clip.get('digest'):
                    continue
                for _ in range(240):
                    _, info = call(f"{api}/media/audio/{clip['digest']}/state", token=token)
                    if info.get('state') in ('ready', 'failed'):
                        break
                    time.sleep(1.0)
                if info.get('state') == 'ready':
                    ready_clips += 1
            check('the audio rendered', ready_clips == len([c for c in clips if c.get('digest')]),
                  f'{ready_clips}/{len([c for c in clips if c.get("digest")])} clips')
            print('\n--- tutor ---')
            print(message[:600])
            print('--- end ---')

        print()
        if failures:
            print(f'END TO END: {len(failures)} FAILURE(S)')
            for item in failures:
                print(f'  - {item}')
            return 1
        print('END TO END: every check passed')
        return 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        log.close()


if __name__ == '__main__':
    sys.exit(main())
