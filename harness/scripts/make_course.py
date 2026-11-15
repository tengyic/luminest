"""Turn a document into a course you can actually study.

The shipped AP Psychology pack is structure only -- concept titles and unit order, no
lessons, no items -- because reproducing a publisher's text is not ours to do. So the honest
path is the learner-uploaded one: give the builder the text you legitimately hold, and it
builds the graph, the questions and the lessons from that.

This does the whole loop over HTTP and starts no server:

    register -> upload the document -> enrol -> compile one lesson

    backend/.venv/bin/python -u scripts/make_course.py --file ~/Downloads/book.pdf \
        --title "AP Psychology" --subject psychology
    backend/.venv/bin/python -u scripts/make_course.py --file unit1.txt --text

``--text`` sends a plain-text file; otherwise the bytes go up as a document and the server
decides. Every refusal is printed with its reason -- a course that did not build is not a
course with zero concepts.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import secrets
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote


def call(base: str, path: str, payload=None, token: str | None = None,
         method: str | None = None, timeout: float = 180.0):
    url = base.rstrip('/') + path
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
            return error.code, {'detail': body.decode('utf-8', 'replace')[:500]}
    except (urllib.error.URLError, ConnectionError, TimeoutError) as error:
        return 0, {'detail': f'not reachable: {error}'}


def upload(base: str, token: str, path: Path, title: str, subject: str,
           level: str, as_text: bool):
    """Raw bytes with a declared content type, filename in the query string."""
    declared = 'text/plain' if as_text else (mimetypes.guess_type(path.name)[0]
                                             or 'application/octet-stream')
    query = (f'?filename={quote(path.name)}'
             f'&title={quote(title)}'
             f'&subject={quote(subject)}'
             f'&level={quote(level)}'
             # Without save=1 this route is a *preview*: it returns a course that looks
             # built and stores nothing, and the next call to enrol then answers 404 "no
             # such course on this account". enrol=1 also makes it the active course, which
             # is what makes the plan routes resolve.
             f'&save=1&enrol=1')
    request = urllib.request.Request(base.rstrip('/') + '/api/v1/create/upload' + query,
                                     data=path.read_bytes(), method='POST')
    request.add_header('content-type', declared)
    request.add_header('authorization', 'Bearer ' + token)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=600) as response:
            return response.status, json.loads(response.read() or b'{}')
    except urllib.error.HTTPError as error:
        body = error.read()
        try:
            return error.code, json.loads(body or b'{}')
        except ValueError:
            return error.code, {'detail': body.decode('utf-8', 'replace')[:500]}
    except (urllib.error.URLError, ConnectionError, TimeoutError) as error:
        return 0, {'detail': f'not reachable: {error}'}


def first_concept_id(body: dict) -> str:
    """Some concept id from whatever the builder returned, so a plan can be compiled."""
    for key in ('concepts', 'concept_ids', 'graph'):
        value = body.get(key)
        if isinstance(value, list) and value and isinstance(value[0], str):
            return value[0]
        if isinstance(value, list) and value and isinstance(value[0], dict):
            found = value[0].get('id')
            if found:
                return str(found)
    course = body.get('course') or {}
    if isinstance(course, dict):
        stats = course.get('stats') or {}
        if isinstance(stats, dict) and stats.get('first_concept'):
            return str(stats['first_concept'])
    return ''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://127.0.0.1:8877')
    parser.add_argument('--file', required=True)
    parser.add_argument('--title', default='')
    parser.add_argument('--subject', default='')
    parser.add_argument('--level', default='')
    parser.add_argument('--text', action='store_true',
                        help='send the file as text/plain instead of guessing its type')
    parser.add_argument('--no-enrol', action='store_true')
    args = parser.parse_args()

    path = Path(args.file).expanduser()
    if not path.is_file():
        print(f'no such file: {path}')
        return 2
    size_mb = path.stat().st_size / (1024 * 1024)
    title = args.title or path.stem

    status, health = call(args.base, '/health')
    if status != 200:
        print(f'the backend is not answering on {args.base}: {health}')
        return 2

    email = f'creator-{secrets.token_hex(4)}@course.test'
    status, body = call(args.base, '/api/v1/auth/register',
                        {'name': 'creator', 'email': email, 'password': 'long-secret-password'})
    if status != 201:
        print(f'registration failed: {status} {body}')
        return 2
    token = body['token']
    print(f'account: {(body.get("user") or {}).get("role")}')
    # Printed so the next step - diagnose.py --token, or opening the app - uses the same
    # account instead of a fresh empty one, which would report "no attempts yet" forever.
    print(f'token: {token}')

    print(f'uploading {path.name} ({size_mb:.1f} MB) as {title!r} ...')
    status, built = upload(args.base, token, path, title, args.subject, args.level, args.text)
    print(f'[upload] {status}')
    # /create/upload answers 200 with the course itself; /create/course answers 201 with a
    # wrapper. Accepting only one of the two is how a script reports "nothing to enrol in"
    # about a course that was built successfully.
    if status not in (200, 201):
        print(json.dumps(built, ensure_ascii=False, indent=2)[:1200])
        return 2

    course = built.get('course') or built
    course_id = str(course.get('id') or course.get('course_id') or '')
    print(f'  course    : {course_id or "(unnamed)"}  {course.get("title") or title}')

    def count(value):
        return len(value) if isinstance(value, (list, dict)) else value

    print(f'  concepts  : {count(built.get("concepts"))}')
    print(f'  questions : {count(built.get("questions"))}')
    # The titles are the quality signal: a curated text yields phrases, a badly extracted
    # one yields fragments like "Answering them". Printing them makes that visible before
    # anyone tries to study from it.
    titles = [str(entry.get('title') or '') for entry in (built.get('concepts') or [])
              if isinstance(entry, dict)][:8]
    if titles:
        print(f'  first     : {" | ".join(titles)}')
    stats = built.get('graph_stats') or {}
    if stats:
        print(f'  graph     : {json.dumps(stats, ensure_ascii=False)[:200]}')
    if built.get('rights_note'):
        print(f'  rights    : {str(built["rights_note"])[:160]}')

    if not course_id:
        print('the builder returned no course id; nothing to enrol in')
        return 2

    if not args.no_enrol:
        status, me = call(args.base, '/api/v1/my-courses/' + course_id + '/enrol', {},
                          token)
        print(f'[enrol] {status} active={me.get("course_id") or me.get("active") or ""}')

    concept_id = first_concept_id(built)
    if concept_id:
        status, preview = call(args.base, '/api/v1/procedure/' + concept_id, token=token)
        if status == 200:
            plan = preview.get('plan') or {}
            print(f'[plan] {len(plan.get("blocks") or [])} block(s) for {concept_id}, '
                  f'{plan.get("total_minutes")} min')
            for block in (plan.get('blocks') or []):
                print(f'   - {block.get("kind")}: {str(block.get("title"))[:60]}')
            for entry in (plan.get('skipped') or [])[:4]:
                print(f'   (skipped {entry.get("kind")}: {str(entry.get("reason"))[:80]})')
        else:
            print(f'[plan] {status} {json.dumps(preview, ensure_ascii=False)[:200]}')
    else:
        print('no concept id came back, so no lesson could be compiled -- the course is '
              'built but its graph is not reachable from this response')
    return 0


if __name__ == '__main__':
    sys.exit(main())
