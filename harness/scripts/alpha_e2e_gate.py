"""Closed-Alpha end-to-end gate: one real course, over real HTTP.

This is deliberately not a pytest module. It drives a *running* backend with a
real database, a real model, the real VoiceStudio speech service, and the same
bearer tokens a client uses. Every check records its own evidence; a failure is
recorded as a failure and the gate keeps going, because an operator needs the
whole shape of a broken build, not just the first red line.

    cd harness
    python3 scripts/alpha_e2e_gate.py --base http://127.0.0.1:8791

Outputs: ``outputs/alpha_e2e_evidence.json`` (machine readable) and a short
human summary on stdout. Nothing here changes application state outside the
isolated backend it is pointed at.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs' / 'alpha_e2e_evidence.json'
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class Gate:
    def __init__(self, base: str, course: str, timeout: float):
        self.base, self.course, self.timeout = base.rstrip('/'), course, timeout
        self.steps: list[dict] = []
        self.token = ''
        self.learner_token = ''
        self.concept = ''
        self.deck_id = ''
        self.created_course = ''

    def req(self, method: str, path: str, body=None, *, token: str | None = None,
            raw: bytes | None = None, content_type: str = 'application/json',
            timeout: float | None = None):
        url = self.base + path
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        headers = {'Content-Type': content_type}
        bearer = self.token if token is None else token
        if bearer:
            headers['Authorization'] = 'Bearer ' + bearer
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with OPENER.open(request, timeout=timeout or self.timeout) as response:
                payload = response.read()
                status = response.status
                ctype = response.headers.get('Content-Type', '')
        except urllib.error.HTTPError as exc:
            payload, status, ctype = exc.read(), exc.code, 'application/json'
        except Exception as exc:                       # noqa: BLE001
            return -1, {'error': f'{type(exc).__name__}: {exc}'}, ''
        if 'json' in ctype or not ctype:
            try:
                return status, json.loads(payload or b'{}'), ctype
            except ValueError:
                pass
        return status, {'bytes': len(payload), 'preview': payload[:80].decode('utf-8', 'replace')}, ctype

    def check(self, name: str, method: str, path: str, body=None, *,
              expect=(200, 201, 204), token=None, raw=None, content_type='application/json',
              extract=None, timeout=None):
        started = time.monotonic()
        status, doc, ctype = self.req(method, path, body, token=token, raw=raw,
                                      content_type=content_type, timeout=timeout)
        ms = round((time.monotonic() - started) * 1000)
        ok = status in expect
        step = {'name': name, 'method': method, 'path': path, 'status': status,
                'ok': ok, 'ms': ms, 'excerpt': json.dumps(doc, ensure_ascii=False)[:420]}
        self.steps.append(step)
        print(f"[{'PASS' if ok else 'FAIL'}] {name:44s} {status:>4}  {ms:>7} ms")
        if not ok:
            print('       ' + step['excerpt'][:300])
        if callable(extract):
            try:
                extract(doc)
            except Exception as exc:                   # noqa: BLE001
                step['extract_error'] = f'{type(exc).__name__}: {exc}'
        return doc if ok else None


def brief(doc, keys=()):
    """A compact, non-secret digest of one response."""
    if not isinstance(doc, dict):
        return doc
    return {k: doc.get(k) for k in keys if k in doc}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default=os.getenv('ALPHA_BASE', 'http://127.0.0.1:8791'))
    ap.add_argument('--course', default=os.getenv('ALPHA_COURSE', 'ap_psychology'))
    ap.add_argument('--timeout', type=float, default=300.0)
    ap.add_argument('--wav', default='', help='optional WAV file for the live ASR check')
    args = ap.parse_args()
    g = Gate(args.base, args.course, args.timeout)

    print(f'Closed-Alpha E2E gate · {args.base} · course={args.course}')
    print('=' * 78)

    # ------------------------------------------------------------------ boot
    g.check('health', 'GET', '/api/v1/health', token='')
    stamp = str(int(time.time()))
    reg = g.check('register teacher (first account)', 'POST', '/api/v1/auth/register',
                  {'name': 'Alpha Teacher', 'email': f'alpha.teacher.{stamp}@e2e.test',
                   'password': 'long-secret-password', 'age_confirmed': True,
                   'accept_terms': True}, expect=(201,), token='')
    if reg:
        g.token = reg['token']
    learner = g.check('register second learner', 'POST', '/api/v1/auth/register',
                      {'name': 'Alpha Learner', 'email': f'alpha.learner.{stamp}@e2e.test',
                       'password': 'another-long-secret', 'age_confirmed': True,
                       'accept_terms': True}, expect=(201,), token='')
    if learner:
        g.learner_token = learner['token']

    courses = g.check('catalogue of courses', 'GET', '/api/v1/courses')
    found = False
    if isinstance(courses, dict):
        ids = [c.get('id') for c in courses.get('courses', [])]
        found = args.course in ids
        g.steps[-1]['course_count'] = len(ids)
        g.steps[-1]['target_present'] = found
    print(f'       courses listed: {g.steps[-1].get("course_count")} | '
          f'{args.course} present: {found}')

    g.check('enrol in AP Psychology', 'PATCH', '/api/v1/me', {'course_id': args.course})
    cur = g.check('curriculum (concepts + lessons)', 'GET', '/api/v1/curriculum')
    if isinstance(cur, dict):
        concepts = cur.get('concepts', [])
        with_lesson = [c for c in concepts if c.get('has_lesson')]
        g.concept = (with_lesson or concepts or [{}])[0].get('id', '')
        g.steps[-1]['concepts'] = len(concepts)
        g.steps[-1]['with_lesson'] = len(with_lesson)
        print(f'       concepts: {len(concepts)} | with lesson: {len(with_lesson)} | '
              f'chosen: {g.concept}')

    # ------------------------------------------------- planning + assessment
    g.check('course planning', 'GET', '/api/v1/plan')
    g.check('diagnostic gaps', 'GET', '/api/v1/diagnostic/gaps')
    question = g.check('next question (signed receipt)', 'GET',
                       '/api/v1/questions/next?mode=practice')
    if question:
        qid = question.get('question', {}).get('id') or question.get('id')
        receipt = question.get('receipt') or question.get('question', {}).get('receipt')
        options = question.get('question', {}).get('options') or question.get('options') or []
        option = options[0].get('id') if options and isinstance(options[0], dict) else (options[0] if options else 'A')
        if qid and receipt:
            g.check('submit attempt + grade it', 'POST', '/api/v1/attempts',
                    {'question_id': qid, 'option_id': str(option),
                     'receipt': receipt, 'client_event_id': 'alpha-' + stamp,
                     # The server measures the interval itself; claiming more time
                     # than elapsed is a 422, not a lenient rounding.
                     'elapsed_seconds': 0.0}, expect=(200, 201))
        else:
            print('       (no signed receipt in response; attempt skipped)')
    g.check('gradebook', 'GET', '/api/v1/gradebook')
    g.check('learner dashboard', 'GET', '/api/v1/dashboard')
    g.check('learner analytics', 'GET', '/api/v1/analytics')

    # ------------------------------------------------------- teaching materials
    if g.concept:
        g.check('TA prepares the class', 'POST', '/api/v1/ta/prepare',
                {'concept_id': g.concept, 'curate_video': False})
        g.check('compiled lesson plan', 'GET', f'/api/v1/procedure/{g.concept}')
        g.check('start the lesson (materialise the deck)', 'POST',
                f'/api/v1/procedure/{g.concept}/start', {})
        g.check('live course catalog', 'GET', '/api/v1/live/catalog')
        g.check('live turn state', 'GET', f'/api/v1/live/{g.concept}/state')
        g.check('mind map for the course', 'GET', '/api/v1/mindmap/course')
        g.check('mind map interactive page', 'GET', f'/api/v1/mindmap/{g.concept}/html')
        g.check('flashcards generated', 'POST', '/api/v1/flashcards/generate',
                {'concept_id': g.concept, 'count': 3})
        g.check('flashcard review session', 'GET',
                f'/api/v1/flashcards/session?concept_id={g.concept}')
        deck = g.check('editable deck from the concept', 'GET',
                       f'/api/v1/deck/from-concept/{g.concept}')
        if isinstance(deck, dict):
            g.deck_id = deck.get('deck_id') or deck.get('id') or ''
        if g.deck_id:
            g.check('real .pptx export', 'GET',
                    f'/api/v1/deck/{g.deck_id}/export.pptx', expect=(200,))
        g.check('whiteboard drawing agent', 'POST', '/api/v1/whiteboard-agent/draw',
                {'id': 'alpha_draw_1', 'region': 'scratch',
                 'content': {'type': 'tex', 'mode': 'spec',
                             'title': 'Behaviour = f(consequences)',
                             'spec': {'latex': r'P(R) = f(S^{R})', 'display': True}}})
        images = g.check('image search for the lesson', 'POST', '/api/v1/images/for-lesson',
                         {'concept_id': g.concept}, expect=(200,))
        if isinstance(images, dict):
            g.steps[-1]['outcome'] = images.get('outcome')
            g.steps[-1]['images_found'] = len(images.get('images') or [])

    # ------------------------------------------------------- the live teacher
    if g.concept:
        turn = g.check('MODEL TEACHER TURN (tools + voice)', 'POST', '/api/v1/agent/chat',
                       {'message': 'I keep confusing classical and operant conditioning. '
                                   'Ask me one question that would tell you which part I am missing.',
                        'speak': True, 'context': {'concept_id': g.concept,
                                                   'board_id': 'board-' + g.concept}},
                       timeout=max(args.timeout, 300), expect=(200,))
        if isinstance(turn, dict):
            tools = [e.get('name') for e in turn.get('events', []) if e.get('type') == 'tool_call']
            answered_by = str(turn.get('answered_by') or '')
            g.steps[-1]['answered_by'] = turn.get('answered_by')
            g.steps[-1]['tools'] = tools
            g.steps[-1]['speech'] = brief(turn.get('speech') or {}, ('kind', 'delivery', 'clips'))
            g.steps[-1]['reply_chars'] = len(turn.get('message') or '')
            # An HTTP 200 is not proof of a live teacher: a grounded fallback also
            # returns 200. Fail the gate if the model did not actually answer.
            model_backed = bool(answered_by) and 'fallback' not in answered_by.lower() \
                and g.steps[-1]['reply_chars'] > 0
            g.steps[-1]['model_backed'] = model_backed
            if not model_backed:
                g.steps[-1]['ok'] = False
                print('       [FAIL] prose fallback passed itself off as a model teacher turn')
            print('       answered_by:', turn.get('answered_by'), '| tools:', tools or 'none',
                  '| speech:', (turn.get('speech') or {}).get('kind'),
                  '| reply:', (turn.get('message') or '')[:120].replace('\n', ' '))

        # VoiceStudio renders clips asynchronously; "pending" is a valid immediate
        # state but not a deliverable one. Poll until one is actually playable.
        clips = ((turn.get('speech') or {}).get('clips') or []) if isinstance(turn, dict) else []
        if clips:
            url = clips[0].get('url') or ''
            deadline = time.monotonic() + 30.0
            clip, ctype, status, ready = None, '', 0, False
            while time.monotonic() < deadline and url:
                status, clip, ctype = g.req('GET', url)
                # The audio endpoint serves the rendered bytes directly. A JSON
                # state envelope is not its contract: an ID3/MPEG header in the
                # body *is* the proof that synthesis completed.
                body_bytes = clip.get('bytes', 0) if isinstance(clip, dict) else 0
                preview = str(clip.get('preview', '')) if isinstance(clip, dict) else ''
                ready = (status == 200 and body_bytes > 1024
                         and (preview.startswith('ID3') or 'audio' in ctype))
                if ready:
                    break
                time.sleep(1.0)
            g.steps.append({'name': 'TTS clip renders to a playable asset', 'method': 'GET',
                            'path': url, 'status': status, 'ok': ready,
                            'ms': 0, 'bytes': body_bytes,
                            'excerpt': json.dumps(clip, ensure_ascii=False)[:300]})
            print(f"[{'PASS' if ready else 'FAIL'}] TTS clip renders to a playable asset"
                  f"      {body_bytes} bytes, {ctype}")

        # A second turn asks for a concrete artifact. This is the "teacher in
        # control of what and when" claim: the model must choose and dispatch a
        # tool from the registry, not merely write prose about doing it.
        tool_turn = g.check('TEACHER ORCHESTRATES A TOOL', 'POST', '/api/v1/agent/chat',
                            {'message': ('We need to draw on the board. First call '
                                         "stage_surface with surface='whiteboard' and a short "
                                         "reason, then call whiteboard_write to write the word "
                                         "'reinforcement' on the lesson board. Do both steps "
                                         'in order, then tell me what you drew.'),
                             'speak': False,
                             'context': {'concept_id': g.concept,
                                         'board_id': 'board-' + g.concept}},
                            timeout=max(args.timeout, 300), expect=(200,))
        if isinstance(tool_turn, dict):
            names = [e.get('name') for e in tool_turn.get('events', [])
                     if e.get('type') == 'tool_call']
            results = [e.get('ok') for e in tool_turn.get('events', [])
                       if e.get('type') == 'tool_result']
            g.steps[-1]['tools'] = names
            g.steps[-1]['tool_results'] = results
            # Both steps have to land: a surface switch alone is a decision, not a
            # lesson artifact. Require the whiteboard write itself to succeed.
            dispatched = False
            if ('stage_surface' in names and 'whiteboard_write' in names
                    and len(results) == len(names)):
                dispatched = (bool(results[names.index('whiteboard_write')])
                              and bool(results[names.index('stage_surface')]))
            g.steps[-1]['dispatched'] = dispatched
            if not dispatched:
                g.steps[-1]['ok'] = False
                print('       [FAIL] the teacher did not switch surface AND write to the board')
            print('       tools called:', names or 'none', '| results:', results or 'none')

    # -------------------------------------------------------------- live voice
    wav = Path(args.wav) if args.wav else None
    if not (wav and wav.is_file()):
        wav = ROOT.parent / 'ddsa-slice' / '.workbuddy' / 'probe' / 'probe.wav'
    if g.concept and wav.is_file():
        asr = g.check('LIVE ASR (barge-in audio -> transcript)', 'POST',
                      f'/api/v1/live/{g.concept}/asr', raw=wav.read_bytes(),
                      content_type='audio/wav', timeout=max(args.timeout, 240))
        if isinstance(asr, dict):
            g.steps[-1]['transport'] = asr.get('transport')
            g.steps[-1]['server_latency_ms'] = asr.get('latency_ms')
            g.steps[-1]['transcript'] = asr.get('text')
            # "Live" is a transport claim, not a 200: a 20-second batch HTTP
            # transcription is correct but is not a live turn. Require the
            # streaming socket path and a non-empty transcript.
            live = asr.get('transport') == 'stream' and bool(asr.get('text'))
            g.steps[-1]['live'] = live
            if not live:
                g.steps[-1]['ok'] = False
                print('       [FAIL] ASR fell back to batch or produced no transcript')
            print('       transport:', asr.get('transport'),
                  '| server latency:', asr.get('latency_ms'), 'ms',
                  '| text:', asr.get('text'))
    else:
        print('       [SKIP] no WAV fixture for live ASR')

    # -------------------------------------------------- authoring, media, data
    g.check('textbook catalogue', 'GET', '/api/v1/textbooks/catalogue')
    g.check('licensed image library', 'GET', '/api/v1/images/library')
    g.check('capability matrix', 'GET', '/api/v1/capabilities')
    g.check('model configuration surface', 'GET', '/api/v1/settings/model-config')
    # A real source, not a stub: the builder refuses anything under 400 chars /
    # 80 words / 2 paragraphs, and needs >= 4 extractable concepts. Markdown
    # headings are how a textbook declares its concepts, so the fixture is shaped
    # like one instead of a single wall of prose.
    source = (
        '# Classical Conditioning\n\n'
        'Classical conditioning begins with an unconditioned stimulus that already '
        'produces an unconditioned response. A neutral stimulus is paired with it '
        'repeatedly until the neutral stimulus alone elicits a conditioned response. '
        'Acquisition is the stage during which that association strengthens. '
        'Extinction follows when the conditioned stimulus is presented repeatedly '
        'without the unconditioned stimulus, and the conditioned response weakens. '
        'Spontaneous recovery is the reappearance of the conditioned response after '
        'a rest period, which shows that extinction suppresses rather than erases '
        'the original learning.\n\n'
        '# Generalisation and Discrimination\n\n'
        'Stimulus generalisation occurs when a similar stimulus also produces the '
        'response, while discrimination is the learned ability to tell the two '
        'apart. Generalisation broadens the class of cues that trigger a response '
        'and discrimination narrows it again, so the two processes together '
        'determine how precisely a learner responds to a cue in a new situation.\n\n'
        '# Operant Conditioning\n\n'
        'Operant conditioning differs: behaviour is shaped by its consequences. '
        'Reinforcement increases the likelihood of a response and punishment '
        'decreases it. Positive and negative describe whether a stimulus is added '
        'or removed, not whether the outcome is good or bad. A learner who can '
        'predict which consequence produces a steady, persistent response '
        'understands the difference between the two forms of conditioning rather '
        'than merely naming them.\n\n'
        '# Reinforcement Schedules\n\n'
        'Fixed ratio, variable ratio, fixed interval and variable interval schedules '
        'determine both the rate of responding and resistance to extinction. A '
        'variable ratio schedule produces a steady, persistent response because '
        'the next reinforcement cannot be predicted from the last one.')
    g.check('course creation preview from textbook-length source', 'POST',
            '/api/v1/create/preview', {'text': source}, expect=(200, 201))
    created = g.check('course creation: build and store', 'POST',
                      '/api/v1/create/course',
                      {'text': source, 'title': 'Alpha Conditioning Course',
                       'subject': 'Psychology', 'level': 'intro'}, expect=(201,))
    if isinstance(created, dict):
        g.created_course = (created.get('course') or {}).get('id', '')
        g.steps[-1]['concepts'] = created.get('concepts')
        g.steps[-1]['questions'] = created.get('questions')

    def blueprint_concept(title: str) -> dict:
        return {'title': title,
                'summary': ('This concept explains how a learner comes to predict an '
                            'outcome from a cue and how that prediction changes with '
                            'new evidence over repeated practice trials.'),
                'definition': ('A measurable change in behaviour or expectation that '
                               'follows a reliably observed relationship between events.'),
                'example': ['Identify the cue and the outcome in one concrete case.',
                            'Predict what happens when the outcome stops following the cue.'],
                'misconception': 'The learner assumes the first pairing erases the old response.',
                'correction': ('Extinction suppresses the old response; a rest period can '
                               'reveal that the association is still available.'),
                'application': ('Given a short scenario, classify the schedule and justify '
                                'the predicted response rate in two sentences.'),
                'objective': 'Distinguish acquisition from extinction in a novel example.',
                'keywords': ['learning', 'conditioning'], 'difficulty': 2}

    blueprint = {
        'schema': 1,
        'course': {'id': 'alpha_skill_probe', 'title': 'Alpha Skill Probe',
                   'subject': 'Psychology', 'level': 'intro',
                   'description': ('A short authored course used by the Closed-Alpha gate '
                                   'to prove that a blueprint can be read, audited and '
                                   'materialised without inventing content.')},
        'units': [
            {'title': f'Learning unit {i + 1}',
             'strand': 'Learning',
             'objective': ('Explain how observed pairings and consequences change a '
                           'measured response across repeated trials and rest periods.'),
             'concepts': [blueprint_concept(f'Concept {i + 1}.{j + 1}')
                          for j in range(3)]}
            for i in range(3)],
    }
    authored = g.check('course authoring blueprint (dry run)', 'POST',
                       '/api/v1/author/courses',
                       {'blueprint': blueprint, 'save': False, 'illustrate': False},
                       expect=(200, 201))
    if isinstance(authored, dict):
        g.steps[-1]['audit_ok'] = (authored.get('audit') or {}).get('ok')

    # ------------------------------------------------- study-benchmark telemetry
    g.check('measurement contract', 'GET', '/api/v1/measurement')
    g.check('learning-efficiency report', 'GET', '/api/v1/measurement/report')
    g.check('cold probe budget', 'GET', '/api/v1/measurement/probe/next')
    g.check('estimator benchmark (study benchmarks)', 'GET',
            '/api/v1/measurement/bench', timeout=max(args.timeout, 240))

    # ------------------------------------------------------- multiuser isolation
    me = g.check('second learner profile', 'GET', '/api/v1/me', token=g.learner_token)
    if isinstance(me, dict):
        g.steps[-1]['learner_course'] = me.get('course_id')
    g.check('second learner dashboard', 'GET', '/api/v1/dashboard', token=g.learner_token)
    if g.deck_id:
        cross = g.check('cross-account deck is refused', 'GET',
                        f'/api/v1/deck/{g.deck_id}', token=g.learner_token,
                        expect=(403, 404))
        g.steps[-1]['isolated'] = cross is not None or g.steps[-1]['status'] in (403, 404)
    g.check('own courses (learner)', 'GET', '/api/v1/my-courses', token=g.learner_token)
    # A concept with a curated photograph in the bundle must be illustrated with no
    # network at all. The pack is keyed by short slugs, so this is the regression that
    # used to return no_images while a licence-cleared picture sat on disk.
    g.check('second learner enrols in physics', 'PATCH', '/api/v1/me',
            {'course_id': 'physics'}, token=g.learner_token)
    shipped = g.check('shipped textbook photograph attaches offline', 'POST',
                      '/api/v1/images/for-lesson',
                      {'concept_id': 'physics_acceleration_as_the_rate_of_change_of_velocity'},
                      token=g.learner_token, expect=(200,))
    if isinstance(shipped, dict):
        first = (shipped.get('images') or [{}])[0]
        asset = first.get('asset') or {}
        credit = str(asset.get('credit') or '')
        g.steps[-1]['outcome'] = shipped.get('outcome')
        g.steps[-1]['licence'] = asset.get('licence')
        g.steps[-1]['credit'] = credit[:90]
        verified = (shipped.get('outcome') == 'ok'
                    and first.get('outcome') == 'shipped'
                    and bool(asset.get('sha256')) and bool(credit))
        g.steps[-1]['verified'] = verified
        if not verified:
            g.steps[-1]['ok'] = False
            print('       [FAIL] expected a shipped, attributed photograph in the lesson')
        print('       outcome:', shipped.get('outcome'), '| licence:', asset.get('licence'),
              '| credit:', credit[:70])

    # ------------------------------------------------------------------ report
    passed = sum(1 for s in g.steps if s['ok'])
    summary = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'base': args.base, 'course': args.course, 'concept': g.concept,
        'model': 'configured at runtime by the operator',
        'checks': len(g.steps), 'passed': passed, 'failed': len(g.steps) - passed,
        'failures': [{'name': s['name'], 'status': s['status'], 'excerpt': s['excerpt']}
                     for s in g.steps if not s['ok']],
        'steps': g.steps,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
    print('=' * 78)
    print(f'{passed}/{len(g.steps)} checks passed · evidence: {OUT}')
    return 0 if passed == len(g.steps) else 1


if __name__ == '__main__':
    sys.exit(main())
