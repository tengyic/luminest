"""Image chain: does a prepared lesson actually carry a photograph, and if not, why?

This asks no model and starts no server. It talks to an already-running backend, registers
a throwaway learner, and walks the three routes that decide whether a lesson has a picture:

    POST /api/v1/ta/prepare            what the harness says it can prepare
    GET  /api/v1/procedure/{concept}   the compiled plan, including what it skipped
    POST /api/v1/procedure/{concept}/start   the run the learner actually receives

Every image outcome is printed with the literal reason the backend gave, so "no image" can
never be mistaken for "nobody asked". That distinction is the whole point: five different
failures look identical from the outside.

Run it against a server that is already up::

    backend/.venv/bin/python scripts/probe_images.py
    backend/.venv/bin/python scripts/probe_images.py --concept algebra_2_permutations_and_combinations
    backend/.venv/bin/python scripts/probe_images.py --base http://127.0.0.1:8877 --course physics
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
import urllib.error
import urllib.request


def call(base: str, path: str, payload=None, token: str | None = None, method: str | None = None,
         timeout: float = 30.0):
    """``(status, body)``. A refused connection is reported, never raised."""
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
            return error.code, {'detail': body.decode('utf-8', 'replace')[:300]}
    except (urllib.error.URLError, ConnectionError, TimeoutError) as error:
        return 0, {'detail': f'not reachable: {error}'}


def image_fields(block: dict) -> dict:
    """Every key on a block that could carry or refuse a picture."""
    out = {}
    for key, value in block.items():
        lowered = key.lower()
        if any(word in lowered for word in ('image', 'photo', 'figure', 'poster')):
            if isinstance(value, (dict, list)):
                out[key] = value
            else:
                out[key] = str(value)[:200]
    return out


def course_for(base: str, concept: str, token: str, explicit: str) -> str:
    """The course this concept belongs to, so the enrolment route does not 404."""
    if explicit:
        return explicit
    status, body = call(base, '/api/v1/courses', token=token)
    items = body if isinstance(body, list) else (body.get('courses') if isinstance(body, dict) else None)
    if status == 200 and isinstance(items, list):
        for item in items:
            blob = json.dumps(item)[:20000]
            if concept in blob and item.get('id'):
                return str(item['id'])
    for guess in ('biology', 'physics', 'life_science', 'psychology', 'ap_psychology'):
        status, _ = call(base, '/api/v1/procedure/' + concept, token=token)
        if status == 200:
            return guess
        status, _ = call(base, '/api/v1/me', {'course_id': guess}, token, method='PATCH')
        status, _ = call(base, '/api/v1/procedure/' + concept, token=token)
        if status == 200:
            return guess
    return ''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://127.0.0.1:8877')
    parser.add_argument('--concept', default='active_transport')
    parser.add_argument('--course', default='')
    args = parser.parse_args()
    base = args.base

    status, health = call(base, '/health')
    print(f'[health] {status} ready={health.get("ready")} '
          f'tutor={(health.get("tutor") or {}).get("state")}')
    if status != 200:
        print(f'  the backend is not answering on {base}: {health}')
        return 2

    email = f'probe-{secrets.token_hex(4)}@images.test'
    status, body = call(base, '/api/v1/auth/register',
                        {'name': 'probe', 'email': email, 'password': 'long-secret-password'})
    if status != 201:
        print(f'[register] {status} {body}')
        return 2
    token = body['token']
    print(f'[register] 201 role={(body.get("user") or {}).get("role")}')

    course = course_for(base, args.concept, token, args.course)
    if course:
        status, me = call(base, '/api/v1/me', {'course_id': course}, token, method='PATCH')
        print(f'[enrol] {status} course={me.get("course_id") or course}')
    else:
        print('[enrol] no course resolved; the procedure routes will 404 if this concept '
              'is not enrolled')

    status, ready = call(base, '/api/v1/ta/prepare', {'concept_id': args.concept}, token)
    print(f'\n[ta/prepare] {status}')
    if status == 200:
        figure = ready.get('figure') or {}
        video = ready.get('video') or {}
        print(f'  figure: {figure.get("kind")} — {str(figure.get("title") or "")[:60]}')
        print(f'  figure keys: {sorted(figure.keys())}')
        print(f'  video: {"curated: " + str(video.get("title")) if video.get("curated") else "none — " + str(video.get("reason") or "")}')
        print(f'  ready: {ready.get("ready")}')
        print(f'  image-ish keys: {json.dumps(image_fields(ready), ensure_ascii=False)[:600]}')
    else:
        print(f'  {json.dumps(ready, ensure_ascii=False)[:400]}')

    status, preview = call(base, '/api/v1/procedure/' + args.concept, token=token)
    print(f'\n[plan] {status}')
    if status == 200:
        plan = preview.get('plan') or {}
        blocks = plan.get('blocks') or []
        budget = plan.get('total_minutes') or plan.get('budget_minutes') or '?'
        print(f'  {len(blocks)} block(s), {budget} min')
        for block in blocks:
            print(f'  - {block.get("kind") or block.get("activity")}: '
                  f'{str(block.get("title") or "")[:60]}')
        for entry in plan.get('skipped') or []:
            print(f'  (skipped {entry.get("kind")}: {str(entry.get("reason"))[:90]})')
    else:
        print(f'  {json.dumps(preview, ensure_ascii=False)[:400]}')

    status, prepared = call(base, '/api/v1/procedure/' + args.concept + '/start', {}, token)
    print(f'\n[start] {status}')
    if status == 200:
        run = prepared.get('run') or prepared
        blocks = run.get('blocks') or []
        print(f'  run={run.get("run_id")} blocks={len(blocks)}')
        for block in blocks:
            detail = image_fields(block)
            print(f'  - {block.get("kind") or block.get("activity")}: '
                  f'{str(block.get("title") or "")[:50]}')
            print(f'      image: {json.dumps(detail, ensure_ascii=False)[:400] if detail else "(no image key at all)"}')
    else:
        print(f'  {json.dumps(prepared, ensure_ascii=False)[:400]}')

    # Composing a deck reads the curriculum and may ask the model for narration, so this
    # call is measured in tens of seconds, not in the three-second budget of a read route.
    # The route returns the document itself (not a wrapper), and answers 422 rather than an
    # empty document, so a 200 with no slides would be a contradiction worth printing.
    status, doc = call(base, '/api/v1/deck/from-concept/' + args.concept, token=token,
                       timeout=180.0)
    print(f'\n[deck] {status}')
    if status == 200 and isinstance(doc, dict):
        deck_id = str(doc.get('id') or '')
        slides = doc.get('slides') or []
        print(f'  deck_id={deck_id or "(none)"} slides={len(slides)}')
        for slide in slides[:4]:
            elements = slide.get('elements') or []
            kinds = [str(item.get('type') or item.get('kind') or '') for item in elements]
            boxes = [(item.get('x'), item.get('y'), item.get('w')) for item in elements]
            print(f'   - {str(slide.get("layout") or "?"):12} elements={kinds}')
            print(f'     boxes={boxes}')
        if deck_id:
            status, images = call(base, f'/api/v1/deck/{deck_id}/images', token=token)
            rows = images if isinstance(images, list) else (images.get('images') or [])
            print(f'  [images] {status} count={len(rows or [])}')
            for item in (rows or [])[:6]:
                print(f'   - resolved={item.get("resolved")} '
                      f'sha={str(item.get("sha256") or "")[:12]} '
                      f'{str(item.get("title") or "")[:50]}')
    else:
        print(f'  {json.dumps(doc, ensure_ascii=False)[:300]}')

    print('\nverdict: compare the [plan] block kinds against the [start] image keys. '
          'A block whose kind is "figure" but whose image keys are empty was refused, '
          'not skipped; the reason belongs in the same response and is missing.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
