"""Fetch and store licence-cleared OpenStax textbook sections for the grounding map.

Real network tool for the operator, distinct from the test suite (which replays saved
fixtures). Usage, from the harness root:

    backend/bin-python? no -- run with any interpreter that has httpx:

    python3 backend/scripts/fetch_openstax.py --data-dir <HARNESS_DATA_DIR> [--concept linear_functions]

Every section passes the fail-close licence gate in app.ingest.policy before any text is
stored: the book must have an audited policy entry AND OpenStax's own API must still report
the licence that entry was audited against. NC books are recorded link-only with the refusal
reason and no text.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingest.sources import openstax  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--data-dir', required=True,
                        help='HARNESS_DATA_DIR-equivalent; sections land in <dir>/textbook/')
    parser.add_argument('--concept', action='append', default=[],
                        help='restrict to these concept ids (default: every mapped concept)')
    args = parser.parse_args()

    settings = type('Settings', (), {'data_dir': args.data_dir})()
    concepts = args.concept or list(openstax.SECTION_MAP)
    summary = []
    for concept_id in concepts:
        if concept_id not in openstax.SECTION_MAP:
            print(f'unknown concept {concept_id!r}; mapped: {sorted(openstax.SECTION_MAP)}',
                  file=sys.stderr)
            return 2
        book_slug, page_slug = openstax.SECTION_MAP[concept_id]
        record = openstax.ingest_section(settings, book_slug, page_slug)
        summary.append({'concept': concept_id, 'status': record.get('status'),
                        'book_slug': book_slug, 'page_slug': page_slug,
                        'source_url': record.get('source_url'),
                        'author': record.get('author'), 'licence': record.get('licence'),
                        'fetched_at': record.get('fetched_at'),
                        'chars': len(record.get('text') or ''),
                        'withheld_reason': record.get('withheld_reason', '')})
        print(f"[{record.get('status'):>11}] {concept_id}: {record.get('section_title', '')} "
              f"<{record.get('source_url', '')}>")
    print(json.dumps(summary, indent=1, ensure_ascii=False))
    return 0 if all(item['status'] == 'ready' for item in summary) else 1


if __name__ == '__main__':
    raise SystemExit(main())
