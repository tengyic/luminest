#!/usr/bin/env python
"""Refresh the bundled OpenStax textbook catalogue from the publisher's own CMS API.

The catalogue is **data, not code**: a licence withdrawal is a deletion, and a new
book is an addition the publisher made, not a decision this project made. This
script is the only sanctioned way the bundled snapshot changes, so every change to
it is reproducible from the publisher's own API rather than hand-edited.

What it fetches
---------------
``https://openstax.org/apps/cms/api/v2/pages/?type=books.Book`` with the licence
fields requested explicitly. The licence a book reports here is the same field the
runtime fetcher (``app.ingest.sources.openstax.fetch_book_meta``) re-reads at fetch
time, so the snapshot and the live gate can never drift apart silently.

What it writes
--------------
``app/ingest/sources/openstax_catalogue.json`` -- raw publisher fields per book,
plus provenance (source URL, retrieval timestamp, API shape) and a summary block.
**No rights decision is baked into the data**: the per-book rights position is
derived at import time by ``app.ingest.policy`` from the publisher strings through
the same fail-close classifier every other source uses, so editing the JSON cannot
upgrade a book's rights -- only re-fetching it from the publisher can.

Usage
-----
    python scripts/refresh_openstax_catalogue.py                # live fetch + write
    python scripts/refresh_openstax_catalogue.py --check        # fetch, report, no write
    python scripts/refresh_openstax_catalogue.py --out PATH     # custom destination

Exit status is 0 when the catalogue was refreshed (or checked) successfully, 1 on a
network/API failure. A *changed* rights picture is not a failure: it is exactly the
change this script exists to surface.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
import time
from pathlib import Path

import httpx

DEFAULT_OUT = Path(__file__).resolve().parent.parent / 'app' / 'ingest' / 'sources' / \
    'openstax_catalogue.json'

LISTING_URL = 'https://openstax.org/apps/cms/api/v2/pages/'
LISTING_PARAMS = {'type': 'books.Book', 'format': 'json', 'limit': 200,
                  'fields': 'title,license_name,license_version,license_url,book_state,book_uuid'}
SCHEMA = 'openstax_catalogue/1'
USER_AGENT = ('LuminfestLearningHarness/1.0 (catalogue refresh; reads publisher licence '
              'fields only, stores no book text)')

#: The evidence entry these snapshots update. Kept here so the JSON and the evidence
#: registry cannot name different audits.
EVIDENCE_ID = 'openstax_full_catalogue_2026_11_10'


def fetch_listing() -> dict:
    """The publisher's own book listing, licence fields included."""
    with httpx.Client(timeout=40.0, follow_redirects=True, trust_env=False,
                      headers={'User-Agent': USER_AGENT}) as client:
        response = client.get(LISTING_URL, params=LISTING_PARAMS)
        response.raise_for_status()
        return response.json()


def build_snapshot(raw: dict) -> dict:
    """The bundled snapshot: raw publisher fields plus provenance, nothing derived."""
    items = raw.get('items') or []
    if raw.get('meta', {}).get('total_count') != len(items):
        raise ValueError(
            f'listing reported {raw.get("meta", {}).get("total_count")} books but served '
            f'{len(items)}; raise the limit parameter and re-run rather than store a partial '
            f'catalogue')
    books = []
    for item in items:
        meta = item.get('meta') or {}
        slug = str(meta.get('slug') or '')
        if not slug:
            raise ValueError(f'book {item.get("id")!r} has no slug; refusing to store it')
        books.append({
            'id': item.get('id'),
            'slug': slug,
            'title': str(item.get('title') or ''),
            'locale': str(meta.get('locale') or ''),
            'book_uuid': str(item.get('book_uuid') or ''),
            'book_state': str(item.get('book_state') or ''),
            'license_name': item.get('license_name'),
            'license_version': item.get('license_version'),
            'license_url': item.get('license_url'),
            'detail_url': str(meta.get('html_url') or ''),
            'first_published_at': str(meta.get('first_published_at') or ''),
        })
    books.sort(key=lambda book: book['slug'])
    slugs = [book['slug'] for book in books]
    duplicates = sorted(slug for slug, count in collections.Counter(slugs).items() if count > 1)
    if duplicates:
        raise ValueError(f'duplicate slugs in listing: {duplicates}')
    licences = collections.Counter(
        (book['license_name'], book['license_version']) for book in books)
    states = collections.Counter(book['book_state'] for book in books)
    return {
        'schema': SCHEMA,
        'evidence_id': EVIDENCE_ID,
        'source': LISTING_URL + '?' + '&'.join(
            f'{key}={value}' for key, value in LISTING_PARAMS.items()),
        'retrieved_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'method': "OpenStax Wagtail CMS v2 pages API, type=books.Book, publisher-reported "
                  "licence fields. Raw fields only: the per-book rights position is derived "
                  "at import time by app.ingest.policy through the fail-close licence "
                  "classifier, so this file cannot widen a book's rights.",
        'total_count': len(books),
        'summary': {
            'by_licence': [{'license_name': name, 'license_version': version, 'count': count}
                           for (name, version), count in licences.most_common()],
            'by_state': dict(states),
            'unlicensed_slugs': sorted(book['slug'] for book in books
                                       if not book['license_name']),
        },
        'books': books,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT,
                        help=f'destination (default: {DEFAULT_OUT})')
    parser.add_argument('--check', action='store_true',
                        help='fetch and report, but do not write')
    args = parser.parse_args(argv)

    try:
        raw = fetch_listing()
    except httpx.HTTPError as exc:
        print(f'fetch failed: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 1
    try:
        snapshot = build_snapshot(raw)
    except ValueError as exc:
        print(f'refusing to store: {exc}', file=sys.stderr)
        return 1

    print(f"retrieved {snapshot['total_count']} books at {snapshot['retrieved_at']}")
    for row in snapshot['summary']['by_licence']:
        label = f"{row['license_name']} {row['license_version']}" if row['license_name'] \
            else '(no licence declared)'
        print(f"  {row['count']:4}  {label}")
    print(f"  states: {snapshot['summary']['by_state']}")

    if args.check:
        print('--check: not written.')
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(snapshot, indent=1, ensure_ascii=False,
                                   sort_keys=False) + '\n', encoding='utf-8')
    print(f"written: {args.out}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
