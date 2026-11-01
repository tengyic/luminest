"""Verify every PhET sim slug in simulations.json against the live PhET server.

Run:  python scripts/verify_sim_slugs.py

A slug whose HTML5 build returns non-200 is printed as FAIL; the operator should move
such a mapping back to `uncovered` with the HTTP code in the note. Optionally pass a
slug as argv to test one candidate before adding it as a mapping.
Exit code: number of failures (0 = all verified).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib import request

PACK = Path(__file__).resolve().parent.parent / 'app' / 'media_packs' / 'simulations.json'

UA = ('Luminfest/1.0 (educational slug verification; local single-learner instance)')


def check(slug: str) -> int:
    url = f'https://phet.colorado.edu/sims/html/{slug}/latest/{slug}_en.html'
    req = request.Request(url, headers={'User-Agent': UA})
    try:
        with request.urlopen(req, timeout=20) as resp:
            return resp.status
    except Exception as exc:  # noqa: BLE001  (report the code/reason, never widen)
        reason = getattr(exc, 'code', None) or str(exc)
        print(f'FAIL {slug} {reason}')
        return 0 if False else 1  # counted as failure below via return value


def main() -> int:
    data = json.loads(PACK.read_text(encoding='utf-8'))
    slugs = sorted({m['sim_slug_or_id'] for m in data['mappings'] if m['provider'] == 'phet'})
    if len(sys.argv) > 1:
        slugs = sys.argv[1:]
    failures = 0
    for slug in slugs:
        url = f'https://phet.colorado.edu/sims/html/{slug}/latest/{slug}_en.html'
        req = request.Request(url, headers={'User-Agent': UA})
        try:
            with request.urlopen(req, timeout=20) as resp:
                code = resp.status
        except Exception as exc:  # noqa: BLE001
            code = getattr(exc, 'code', None) or str(exc)
        if code == 200:
            print(f'OK   {slug}')
        else:
            print(f'FAIL {slug} {code}')
            failures += 1
    print(f'\n{len(slugs) - failures}/{len(slugs)} slugs verified live (HTTP 200)')
    return failures


if __name__ == '__main__':
    raise SystemExit(main())
