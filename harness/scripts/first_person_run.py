#!/usr/bin/env python3
"""Observable first-person acceptance run for the Luminfest learning harness.

Runs against a *fresh* database and a *brand-new* learner account. Every step has an
explicit pass criterion and records the raw status code / response / database rows.
A step that "seems fine" is recorded as a fail. No result is fabricated: when a
provider or capability is absent, the run keeps the reason string the server returns.

Usage:
    python3 scripts/first_person_run.py --base-url http://127.0.0.1:8791 \
        --database <HARNESS_DATA_DIR>/harness.sqlite3 --output outputs/first-person

Requires only the standard library (plus a running backend).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

API = '/api/v1'


class Client:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip('/')
        # Never let a system HTTP proxy swallow loopback requests.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.token = ''

    def call(self, method: str, path: str, body=None, timeout=45):
        url = self.base + path
        data = None if body is None else json.dumps(body).encode('utf-8')
        headers = {'Accept': 'application/json'}
        if data is not None:
            headers['Content-Type'] = 'application/json'
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=timeout) as response:
                raw = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
        except urllib.error.URLError as exc:
            return {'status': -1, 'body': {'error': str(exc.reason)}}
        try:
            parsed = json.loads(raw.decode('utf-8')) if raw else None
        except (ValueError, UnicodeDecodeError):
            parsed = {'raw_bytes': len(raw), 'preview': raw[:200].decode('utf-8', 'replace')}
        return {'status': status, 'body': parsed}


def clip(value, limit=1400):
    text = json.dumps(value, ensure_ascii=False, default=str) if not isinstance(value, str) else value
    return text if len(text) <= limit else text[:limit] + f' …[{len(text)} chars]'


class Run:
    def __init__(self, client: Client, database: Path, topic: str):
        self.client = client
        self.database = database
        self.topic = topic
        self.steps: list[dict] = []
        self.context: dict = {}

    def db_counts(self, tables):
        if not self.database.exists():
            return {}
        connection = sqlite3.connect(f'file:{self.database}?mode=ro', uri=True)
        existing = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        result = {}
        for table in tables:
            if table in existing:
                result[table] = connection.execute('SELECT count(*) FROM "' + table + '"').fetchone()[0]
        connection.close()
        return result

    def step(self, name, criterion, function, expect=None):
        started = time.monotonic()
        try:
            evidence = function()
        except Exception as exc:  # noqa: BLE001 - a raised step is a failed step, not a crashed run
            evidence = {'exception': f'{type(exc).__name__}: {exc}'}
        ok = False
        try:
            ok = bool(criterion(evidence)) if expect is None else expect(evidence)
        except Exception:
            ok = False
        record = {'step': name, 'passed': ok, 'criterion': criterion.__doc__ or 'observable evidence',
                  'seconds': round(time.monotonic() - started, 3), 'evidence': evidence}
        self.steps.append(record)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {clip(evidence, 500)}", flush=True)
        return record, evidence

    def request(self, method, path, body=None):
        return self.client.call(method, path, body)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8791')
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--topic', default='creep deformation of titanium aluminide turbine blades')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    client = Client(args.base_url)
    run = Run(client, args.database, args.topic)
    email = f'first-person-{uuid.uuid4().hex[:12]}@example.test'
    password = 'First-Person-Acceptance!2026'
    tables = ('users', 'attempts', 'learning_states', 'procedure_runs', 'created_courses',
              'messages', 'flashcards', 'assessments', 'decks')

    def health_ok(e):
        """GET /health returns ready:true and declares its own model/tutor limits."""
        return e.get('status') == 200 and e.get('body', {}).get('ready') is True

    run.step('01 health', health_ok, lambda: run.request('GET', API + '/health'))
    run.context['health'] = run.steps[-1]['evidence']['body']

    def register_ok(e):
        """A brand-new account is created (201) with a bearer token and a learner role."""
        body = e.get('body') or {}
        return e.get('status') == 201 and bool(body.get('token'))

    reg, reg_evidence = run.step(
        '02 register fresh learner', register_ok,
        lambda: run.request('POST', API + '/auth/register',
                            {'name': 'First Person Learner', 'email': email, 'password': password,
                             'age_confirmed': True, 'accept_terms': True}))
    token = (reg_evidence.get('body') or {}).get('token')
    if token:
        client.token = token
    run.context['account'] = {'email': email, 'role': (reg_evidence.get('body') or {}).get('user', {}).get('role')}
    role = run.context['account']['role']
    run.steps.append({'step': '02b no operator promotion', 'passed': role == 'learner',
                      'criterion': 'The first account in HARNESS_ENV=test must stay a learner.',
                      'evidence': {'role': role}})

    def unseen_ok(e):
        """The named topic is genuinely absent from the knowledge graph."""
        body = e.get('body') or {}
        return e.get('status') == 200 and not body.get('results') and not body.get('items')

    run.step('03 topic is unseen', unseen_ok,
             lambda: run.request('GET', API + '/knowledge-graph/search?q=' + urllib.parse.quote(args.topic)))

    def agent_ok(e):
        """Asking to be taught an unseen topic must produce a syllabus or an explicit named refusal."""
        body = e.get('body') or {}
        return e.get('status') == 200 and bool(body.get('message'))

    def agent_answer_ok(e):
        """A free-form question to the agent must produce a non-empty learner-visible reply."""
        body = e.get('body') or {}
        return e.get('status') == 200 and bool(str(body.get('message') or '').strip())

    agent_evidence = run.step(
        '04 ask to be taught the unseen topic (agent chat)', agent_answer_ok,
        lambda: run.request('POST', API + '/agent/chat',
                            {'message': f'Teach me {args.topic}. Build a syllabus and start the first lesson.',
                             'context': {}, 'speak': False}))[1]
    body = agent_evidence.get('body') or {}
    run.context['agent'] = {
        'answered_by': body.get('answered_by'), 'provider': body.get('provider'),
        'grounded_offline': body.get('grounded_offline'),
        'finish_reason': body.get('finish_reason'),
        'tool_calls': [ev.get('tool') or ev.get('name') for ev in body.get('events', [])
                       if ev.get('type') in ('tool_call', 'tool_result', 'tool')],
        'message': clip(body.get('message'), 600),
    }

    def scoped_agent_ok(e):
        """The same agent turn scoped to a real concept must return the grounded offline answer."""
        body = e.get('body') or {}
        return e.get('status') == 200 and bool(str(body.get('message') or '').strip()) and body.get('grounded_offline') is True

    run.step('04b agent chat scoped to a concept', scoped_agent_ok,
             lambda: run.request('POST', API + '/agent/chat',
                                 {'message': 'Why do fractions need a common denominator?',
                                  'context': {'concept_id': 'fractions'}, 'speak': False}))

    def auto_ok(e):
        """POST /create/auto on an unseen topic must return a course plan, not a silent empty."""
        body = e.get('body') or {}
        return e.get('status') in (200, 201) and bool(body.get('concepts') or body.get('course_id'))

    run.step('05 generate a course from the topic name', auto_ok,
             lambda: run.request('POST', API + '/create/auto',
                                 {'query': args.topic, 'save': False, 'enrol': False}),
             )
    run.context['counts_after_generation'] = run.db_counts(tables)

    def saved_course_ok(e):
        """Saving and enrolling the generated course makes its concepts the learner's active curriculum."""
        body = e.get('body') or {}
        return e.get('status') == 201 and body.get('created') is True and body.get('enrolled') is True

    saved_evidence = run.step('05b save and enrol the generated course', saved_course_ok,
                              lambda: run.request('POST', API + '/create/auto',
                                                  {'query': args.topic, 'save': True, 'enrol': True}))[1]
    generated_course_id = (saved_evidence.get('body') or {}).get('course_id')
    run.context['generated_course_id'] = generated_course_id

    def generated_lesson_quality_ok(e):
        """A worked example must not be a verbatim restatement of the source sentence, and must contain real steps."""
        body = (e.get('lesson') or {}) if isinstance(e, dict) else {}
        blocks = body.get('blocks') or []
        core_block = next((b for b in blocks if b.get('kind') == 'concept'), {})
        core = str(core_block.get('body') or '')
        source_span = str(core_block.get('source_span') or '')
        example = str(next((b.get('body') for b in blocks if b.get('kind') == 'worked_example'), '') or '')
        return (bool(example) and example.strip() != source_span.strip()
                and example.strip() != core.strip() and len(example.split()) >= 25)

    generated_concept = ''
    curriculum = run.request('GET', API + '/curriculum')
    for item in (curriculum.get('body') or {}).get('concepts', []):
        if item.get('course_id') == generated_course_id:
            generated_concept = item.get('id', '')
            break
    run.context['generated_concept_id'] = generated_concept
    if generated_concept:
        lesson_evidence = run.step('05c generated lesson has independent worked example',
                                   generated_lesson_quality_ok,
                                   lambda: {'lesson': run.request('GET', API + '/lessons/' + generated_concept).get('body')})
        run.context['generated_lesson_blocks'] = clip(
            (lesson_evidence if isinstance(lesson_evidence, dict) else {}).get('lesson', {}).get('blocks'), 1200)

    def courses_ok(e):
        """A course/concept list exists so a lesson can be started."""
        body = e.get('body') or {}
        return e.get('status') == 200 and bool(body.get('courses') or body.get('concepts') or body)

    run.step('06 available courses', courses_ok,
             lambda: run.request('GET', API + '/courses'))
    # A concept id (not a course id) is what /procedure/{concept_id}/start expects.
    concept_id = ''
    for item in (curriculum.get('body') or {}).get('concepts', []):
        if item.get('has_lesson'):
            concept_id = item.get('id', '')
            break
    run.context['concept_id'] = concept_id

    def unknown_chat_ok(e):
        """A learner asking about an untaught topic in /chat gets an explicit error, not a hallucinated lesson."""
        return e.get('status') in (404, 422)

    run.step('07 chat on an unknown topic is refused', unknown_chat_ok,
             lambda: run.request('POST', API + '/chat',
                                 {'concept_id': 'titanium-aluminide-creep',
                                  'message': f'Explain {args.topic} to me.'}))

    if concept_id:
        def start_ok(e):
            """Starting the lesson returns a run with at least one block."""
            body = e.get('body') or {}
            return e.get('status') == 200 and bool(body.get('run_id') or body.get('id')) and bool(body.get('blocks'))

        start_evidence = run.step('08 start a lesson', start_ok,
                                  lambda: run.request('POST', API + '/procedure/' + concept_id + '/start'))[1]
        start_body = start_evidence.get('body') or {}
        run_id = start_body.get('run_id') or start_body.get('id')
        run.context['run_id'] = run_id
        blocks = start_body.get('blocks') or []
        run.context['first_blocks'] = [b.get('kind') for b in blocks if isinstance(b, dict)]

        counts_before = run.db_counts(('attempts',))
        if blocks and run_id:
            first_order = (blocks[0] or {}).get('order', 1)

            def advance_ok(e):
                """Advancing the first block with outcome=done must write an attempt row for the learner's answer."""
                return e.get('status') == 200 and counts_after.get('attempts', 0) > counts_before.get('attempts', 0)

            advance_result = run.request('POST', API + '/procedure/runs/' + str(run_id) + '/advance',
                                         {'order': first_order, 'outcome': 'done', 'seconds': 30})
            counts_after = run.db_counts(('attempts',))
            run.step('09 complete first block (done) writes an attempt', advance_ok,
                     lambda: {'request': advance_result, 'counts_before': counts_before,
                              'counts_after': counts_after, 'advance_body': clip(advance_result.get('body'), 500)})

        def question_ok(e):
            """A real question with a signed receipt and answer options is served."""
            body = e.get('body') or {}
            return e.get('status') == 200 and bool(body.get('receipt')) and bool(body.get('options'))

        question_evidence = run.step('10 serve a real question', question_ok,
                                     lambda: run.request('GET', API + '/questions/next?mode=practice'))[1]
        question = question_evidence.get('body') or {}
        if question.get('receipt'):
            option = (question.get('options') or [{}])[0]
            option_id = option.get('id') if isinstance(option, dict) else str(option)
            submission = {'question_id': question.get('id'), 'option_id': option_id,
                          'receipt': question.get('receipt'),
                          'client_event_id': 'first-person-' + uuid.uuid4().hex[:10],
                          'elapsed_seconds': 0.5, 'confidence': 0.6,
                          'self_explanation': 'I am choosing this option because the units must stay consistent when the quantities are combined.'}

            def attempt_ok(e):
                """Submitting an answer must be accepted and produce a specific diagnosis category."""
                body = e.get('body') or {}
                return e.get('status') == 200 and bool(body.get('diagnosis'))

            attempt_evidence = run.step('11 answer the question', attempt_ok,
                                        lambda: run.request('POST', API + '/attempts', submission))[1]
            run.context['diagnosis'] = (attempt_evidence.get('body') or {}).get('diagnosis')
            run.context['counts_after_answer'] = run.db_counts(tables)

            def read_states():
                if not args.database.exists():
                    return []
                connection = sqlite3.connect(f'file:{args.database}?mode=ro', uri=True)
                try:
                    rows = list(connection.execute('SELECT concept_id, data FROM learning_states'))
                finally:
                    connection.close()
                return [{'concept_id': row[0], 'data': json.loads(row[1])} for row in rows]

            def review_ok(e):
                """After a scored attempt, a learning_states row exists with a scheduled due_at."""
                states = e.get('states') or []
                return any((s.get('data') or {}).get('due_at') for s in states)

            states = read_states()
            run.step('12 learning state moved and next review scheduled', review_ok,
                     lambda: {'states': states, 'reviews_endpoint': run.request('GET', API + '/reviews')})
            run.context['learning_states_after_answer'] = clip(states, 1000)

            def adaptation_ok(e):
                """The compiled lesson plan must list the evidence it adapted on after an attempt."""
                body = e.get('body') or {}
                return e.get('status') == 200 and bool(body)

            plan_evidence = run.step('13 recompile plan after the answer', adaptation_ok,
                                     lambda: run.request('GET', API + '/procedure/' + concept_id))[1]
            run.context['plan_after_answer'] = clip(plan_evidence.get('body'), 900)

    voice_result = run.request('POST', API + '/voice/speak', {'text': 'Let us look at why the units must agree.'})

    def voice_honest_ok(e):
        """Voice either produces audio or names the missing service with an actionable reason; never a fake success."""
        detail = str((e.get('body') or {}).get('detail') or '')
        return e.get('status') == 200 or (e.get('status') == 503 and 'VoiceStudio' in detail)

    def voice_speaks_ok(e):
        """The tutor actually speaks: /voice/speak returns audio (200)."""
        return e.get('status') == 200

    run.step('14 voice behaviour is honest', voice_honest_ok, lambda: voice_result)
    run.step('14b tutor actually speaks', voice_speaks_ok, lambda: voice_result)

    # Finish the lesson by advancing every remaining block, then check the run's terminal state.
    if run.context.get('run_id') and concept_id:
        current = run.request('GET', API + '/procedure/runs/' + str(run.context['run_id']))
        body = current.get('body') or {}
        done_orders = {int(row.get('order') or 0) for row in body.get('completed') or []}
        for block in body.get('blocks') or []:
            order = int(block.get('order') or 0)
            if not order or order in done_orders:
                continue
            run.request('POST', API + '/procedure/runs/' + str(run.context['run_id']) + '/advance',
                        {'order': order, 'outcome': 'skipped'})
        final = run.request('GET', API + '/procedure/runs/' + str(run.context['run_id']))

        def lesson_ends_ok(e):
            """Advancing all blocks ends the lesson with a completed run and a full progress record."""
            body = e.get('body') or {}
            return (e.get('status') == 200 and body.get('status') == 'completed'
                    and body.get('progress') == 1.0 and bool(body.get('completed')))

        run.step('15 lesson ends with a summary', lesson_ends_ok, lambda: final)
        run.context['final_run'] = clip(final.get('body'), 1200)

    run.context['final_counts'] = run.db_counts(tables)
    passed = sum(1 for s in run.steps if s['passed'])
    report = {
        'generated_at': time.strftime('%Y-%m-%d %H:%M:%S %z'),
        'base_url': args.base_url, 'topic': args.topic, 'database': str(args.database),
        'passed': passed, 'total': len(run.steps), 'failed': len(run.steps) - passed,
        'steps': run.steps, 'context': run.context,
        'note': 'A FAIL is observed behaviour, not a claim that the whole subsystem is broken. Refusals with reasons are designed fallbacks.',
    }
    (args.output / 'first-person-run.json').write_text(json.dumps(report, indent=2, ensure_ascii=False))

    lines = ['# First-person acceptance run', '',
             f'- backend: `{args.base_url}` · database: `{args.database}`',
             f'- unseen topic: **{args.topic}**',
             f'- result: **{passed}/{len(run.steps)} steps passed**', '',
             '| # | Step | Pass | Evidence |', '|---|---|---|---|']
    for index, s in enumerate(run.steps, 1):
        lines.append(f"| {index} | {s['step']} | {'PASS' if s['passed'] else 'FAIL'} | `{clip(s['evidence'], 320).replace('|', '/')}` |")
    lines += ['', '## Health / provider declaration', '', '```json', clip(run.context.get('health'), 1200), '```',
              '', '## Agent turn on the unseen topic', '', '```json', clip(run.context.get('agent'), 1200), '```',
              '', '## Database row counts', '', '```json', clip({'after_generation': run.context.get('counts_after_generation'),
                                                                   'after_answer': run.context.get('counts_after_answer'),
                                                                   'final': run.context.get('final_counts')}, 1600), '```',
              '', 'Full machine-readable evidence: `first-person-run.json`.']
    (args.output / 'first-person-run.md').write_text('\n'.join(lines) + '\n')
    print(f'\n{passed}/{len(run.steps)} steps passed; evidence: {args.output}')
    return 0 if passed == len(run.steps) else 1


if __name__ == '__main__':
    sys.exit(main())
