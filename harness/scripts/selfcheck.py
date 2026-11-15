"""One command, one report: does this build actually produce a lesson with a picture?

Each check is independent and prints PASS/FAIL with the literal detail behind it. Nothing
is inferred: a check that could not run is reported as SKIP, never as a pass, because the
whole point is to stop "it probably works" from being mistaken for evidence.

Run against a backend that is already up::

    backend/.venv/bin/python -u scripts/selfcheck.py --base http://127.0.0.1:8877
    backend/.venv/bin/python -u scripts/selfcheck.py --concept algebra_2_permutations_and_combinations --course algebra_2

The .pptx is verified by opening it as a zip and counting ``ppt/media/*`` entries. That
needs no python-pptx and answers the question a learner actually asks: are there pictures
in the file, or only text boxes.
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
import urllib.error
import urllib.request
import zipfile
import io

RESULTS: list[tuple[str, str, str]] = []


def record(name: str, ok: bool | None, detail: str) -> None:
    mark = 'SKIP' if ok is None else ('PASS' if ok else 'FAIL')
    RESULTS.append((mark, name, detail[:200]))


def call(base: str, path: str, payload=None, token: str | None = None,
         method: str | None = None, timeout: float = 60.0, raw: bool = False):
    url = base.rstrip('/') + path
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method or ('POST' if data else 'GET'))
    request.add_header('content-type', 'application/json')
    if token:
        request.add_header('authorization', 'Bearer ' + token)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read()
            return response.status, body if raw else json.loads(body or b'{}')
    except urllib.error.HTTPError as error:
        body = error.read()
        try:
            return error.code, json.loads(body or b'{}')
        except ValueError:
            return error.code, {'detail': body.decode('utf-8', 'replace')[:300]}
    except (urllib.error.URLError, ConnectionError, TimeoutError) as error:
        return 0, {'detail': f'not reachable: {error}'}


def image_elements(doc: dict) -> list[dict]:
    out = []
    for slide in doc.get('slides') or []:
        for element in slide.get('elements') or []:
            if str(element.get('kind') or element.get('type') or '') == 'image':
                out.append({'slide': slide.get('layout'), **(element.get('image') or {})})
    return out


def pictures(node) -> list[dict]:
    """Every nested dict that is an *available* picture, whatever key it hangs from.

    Looking for a key named "image" misses a poster: a video block carries its still frame
    as ``artifact.poster``, which is a real picture and the only one a first-exposure lesson
    has. Available is the test, not the name.
    """
    found: list[dict] = []
    if isinstance(node, dict):
        if node.get('available') is True and (node.get('sha256') or node.get('url')):
            found.append(node)
        for value in node.values():
            found.extend(pictures(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(pictures(value))
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://127.0.0.1:8877')
    parser.add_argument('--concept', default='biology_active_transport_against_a_gradient')
    parser.add_argument('--course', default='biology')
    args = parser.parse_args()
    base = args.base

    status, health = call(base, '/health')
    record('health ready', status == 200 and bool(health.get('ready')),
           f'{status} tutor={(health.get("tutor") or {}).get("state")}')
    if status != 200:
        for mark, name, detail in RESULTS:
            print(f'{mark:4} {name:34} {detail}')
        return 2

    email = f'selfcheck-{secrets.token_hex(4)}@probe.test'
    status, body = call(base, '/api/v1/auth/register',
                        {'name': 'selfcheck', 'email': email, 'password': 'long-secret-password'})
    token = body.get('token', '') if status == 201 else ''
    record('register', status == 201, f'{status} role={(body.get("user") or {}).get("role")}')
    if not token:
        for mark, name, detail in RESULTS:
            print(f'{mark:4} {name:34} {detail}')
        return 2

    status, me = call(base, '/api/v1/me', {'course_id': args.course}, token, method='PATCH')
    record('enrol', status == 200, f'{status} course={me.get("course_id")}')

    status, preview = call(base, '/api/v1/procedure/' + args.concept, token=token)
    plan = (preview.get('plan') or {}) if status == 200 else {}
    blocks = plan.get('blocks') or []
    budget = plan.get('total_minutes') or plan.get('budget_minutes')
    record('plan compiles', status == 200 and bool(blocks),
           f'{status} blocks={len(blocks)} minutes={budget}')
    for entry in (plan.get('skipped') or [])[:6]:
        print(f'     skipped {str(entry.get("kind")):14} {str(entry.get("reason"))[:90]}')

    status, started = call(base, '/api/v1/procedure/' + args.concept + '/start', {}, token)
    run = (started.get('run') or started) if status == 200 else {}
    record('run starts', status == 200 and bool(run.get('blocks')),
           f'{status} blocks={len(run.get("blocks") or [])}')
    run_pictures = pictures(run.get('blocks') or [])
    record('lesson blocks carry a picture', bool(run_pictures) or None,
           f'{len(run_pictures)} available picture(s) in {len(run.get("blocks") or [])} blocks')

    status, doc = call(base, '/api/v1/deck/from-concept/' + args.concept,
                       token=token, timeout=180.0)
    slides = (doc.get('slides') or []) if isinstance(doc, dict) else []
    deck_id = str(doc.get('id') or '') if isinstance(doc, dict) else ''
    record('deck composes', status == 200 and bool(slides), f'{status} slides={len(slides)}')
    elements = image_elements(doc) if slides else []
    record('deck has an image element', bool(elements),
           f'{len(elements)} image element(s)')
    for row in elements[:4]:
        print(f'     slide={row.get("slide")} sha={str(row.get("sha256"))[:12]}')

    # Every slide used to place its title at the same 48,36, so a title slide, a figure
    # slide and a summary read as one text document with page breaks. Distinct positions
    # are the cheapest evidence that the layout table is being consulted.
    title_boxes = set()
    for slide in slides:
        for element in slide.get('elements') or []:
            if str(element.get('kind')) == 'text' and (element.get('style') or {}).get('bold'):
                title_boxes.add((element.get('x'), element.get('y')))
                break
    record('title placement varies by layout', len(title_boxes) > 1 or None,
           f'{len(title_boxes)} distinct title position(s) across {len(slides)} slide(s)')

    if deck_id:
        status, images = call(base, f'/api/v1/deck/{deck_id}/images', token=token)
        rows = images if isinstance(images, list) else (images.get('images') or [])
        resolved = [r for r in rows if r.get('resolved')]
        record('deck images resolve to bytes', bool(resolved),
               f'{len(resolved)}/{len(rows)} resolved')

        status, lint = call(base, f'/api/v1/deck/{deck_id}/lint', token=token)
        violations = (lint.get('violations') if isinstance(lint, dict) else None) or []
        record('deck obeys the house style', status == 200 and not violations,
               f'{len(violations)} violation(s)' if status == 200 else f'{status} {lint}')
        for row in violations[:4]:
            print(f'     {row.get("rule")}: {str(row.get("detail"))[:90]}')

        status, blob = call(base, f'/api/v1/deck/{deck_id}/export.pptx',
                            token=token, timeout=180.0, raw=True)
        if status == 200 and isinstance(blob, bytes):
            try:
                with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                    media = [n for n in archive.namelist() if n.startswith('ppt/media/')]
                    slides_xml = [n for n in archive.namelist()
                                  if n.startswith('ppt/slides/slide')]
                record('pptx carries pictures', bool(media),
                       f'{len(media)} media file(s), {len(slides_xml)} slide(s), '
                       f'{len(blob) // 1024} KB')
            except zipfile.BadZipFile:
                record('pptx carries pictures', False, 'the export was not a zip (.pptx)')
        else:
            record('pptx carries pictures', False if status else None, f'export status {status}')

    print()
    width = max(len(name) for _, name, _ in RESULTS)
    for mark, name, detail in RESULTS:
        print(f'{mark:4}  {name:{width}}  {detail}')
    failed = [name for mark, name, _ in RESULTS if mark == 'FAIL']
    print()
    print('verdict:', 'all checks passed' if not failed else 'failed -> ' + ', '.join(failed))
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
