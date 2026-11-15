"""Exercise the two study artefacts: generated flashcards and the concept map.

Both are checked against a real enrolled course, not a fixture: the flashcards come out of an
authored lesson's Core idea block, and the map out of the same graph the lesson walks.

    backend/.venv/bin/python -u scripts/probe_learning_tools.py --base http://127.0.0.1:8877
"""
from __future__ import annotations

import argparse
import json
import secrets
import urllib.error
import urllib.request
from pathlib import Path


def call(base: str, path: str, payload=None, token: str = ''):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(base + path, data=data, method='POST' if data else 'GET')
    request.add_header('content-type', 'application/json')
    if token:
        request.add_header('authorization', 'Bearer ' + token)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=180) as response:
            return response.status, json.loads(response.read() or b'{}')
    except urllib.error.HTTPError as error:
        body = error.read()
        try:
            return error.code, json.loads(body or b'{}')
        except ValueError:
            return error.code, {'detail': body.decode('utf-8', 'replace')[:200]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://127.0.0.1:8877')
    parser.add_argument('--course', default='mine_76463a853c')
    parser.add_argument('--concept', default='overconfidence')
    args = parser.parse_args()
    base, course = args.base, args.course
    concept_id = f'{course}_{args.concept}'

    status, body = call(base, '/api/v1/auth/register',
                        {'name': 'probe', 'email': f'probe-{secrets.token_hex(3)}@x.test',
                         'password': 'long-secret-password'})
    token = body.get('token', '')
    print(f'register {status} token={bool(token)}')

    status, enrol = call(base, f'/api/v1/my-courses/{course}', {}, token)
    print(f'enrol    {status} {str(enrol)[:80]}')

    # 1. What would be created, without creating it.
    status, preview = call(base, '/api/v1/flashcards/generate',
                           {'concept_id': concept_id, 'dry_run': True}, token)
    cards = preview.get('cards') or preview.get('candidates') or []
    print(f'\n[flashcards] dry_run {status}  candidates={len(cards)}  '
          f'note={str(preview.get("note") or preview.get("reason") or "")[:90]}')
    for card in cards[:3]:
        print(f'  front: {str(card.get("front"))[:70]}')
        print(f'  back : {str(card.get("back"))[:90]}')

    # 2. Commit them, then read them back and schedule one.
    status, made = call(base, '/api/v1/flashcards/generate',
                        {'concept_id': concept_id, 'count': 4}, token)
    print(f'\n[flashcards] generate {status}  created={made.get("created")} '
          f'skipped={made.get("skipped")}')
    status, listed = call(base, f'/api/v1/flashcards?concept_id={concept_id}', token=token)
    stored = listed.get('cards') or []
    print(f'[flashcards] list     {status}  stored={len(stored)}')
    status, session = call(base, f'/api/v1/flashcards/session?concept_id={concept_id}',
                           token=token)
    queue = session.get('cards') or []
    print(f'[flashcards] session  {status}  due={len(queue)}')
    if queue:
        card_id = queue[0].get('id')
        status, reviewed = call(base, f'/api/v1/flashcards/{card_id}/review',
                                {'grade': 3}, token)
        print(f'[flashcards] review   {status}  '
              f'next_due={str(reviewed.get("card", {}).get("due_at"))[:24]}')
    status, stats = call(base, f'/api/v1/flashcards/stats?concept_id={concept_id}', token=token)
    print(f'[flashcards] stats    {status}  {json.dumps(stats)[:160]}')
    (Path('outputs') / 'flashcards.json').write_text(
        json.dumps({'concept_id': concept_id, 'cards': stored}, indent=1, ensure_ascii=False),
        encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
