"""List an OpenStax book's real table of contents, or check that sections exist.

    python scripts/probe_sections.py --book elementary-algebra
    python scripts/probe_sections.py --book elementary-algebra --check 2-5-... 2-6-...

The table of contents is read from the publisher's own webview (``data-page-slug``
attributes), and ``--check`` fetches each slug and reports its HTTP status. This is the
only sanctioned way to obtain a section slug for an outline: guessing a slug produces a
citation that 404s on the learner's screen.

Both published editions of every book are in the audited catalogue, and only the CC BY
first editions may become text anchors; ``scripts/course_pipeline.py verify`` refuses an
anchor whose book is not CC BY and ingestible.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import httpx  # noqa: E402

from app.ingest.sources import openstax  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--book', required=True)
    ap.add_argument('--check', nargs='*', default=[])
    args = ap.parse_args()

    toc = openstax.fetch_toc(args.book)
    print(f'{args.book}: {len(toc)} sections in the published table of contents')
    for entry in sorted(toc, key=lambda s: s['page_slug']):
        print('  ' + entry['page_slug'])

    if args.check:
        client = httpx.Client(timeout=20.0, follow_redirects=True, trust_env=False,
                              headers={'User-Agent': openstax.USER_AGENT})
        base = f'https://openstax.org/books/{args.book}/pages/'
        missing = 0
        print(f'\nchecking {len(args.check)} slug(s):')
        for slug in args.check:
            response = client.get(base + slug)
            ok = response.status_code == 200
            missing += 0 if ok else 1
            print(f"  {'OK ' if ok else response.status_code}  {slug}")
        return 1 if missing else 0
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
