#!/usr/bin/env python3
"""Pre-warm the curated video allowlist using the same Chromium curation gates.

``find_video`` curates a concept on demand the first time a lesson opens, which
costs ~25-30 s. This script pays that cost up front for a whole course (or a
named handful of concepts), writing to the *same* allowlist through the *same*
``video_search.curate_for_concept`` path, so no second set of rules exists.

    python3 scripts/populate_video_allowlist.py fractions ratios
    python3 scripts/populate_video_allowlist.py --all
    python3 scripts/populate_video_allowlist.py --all --force --limit 4

Every candidate still passes title relevance, neighbouring-lesson exclusion,
trusted-source preference and the keyless oEmbed embeddability probe. A concept
that qualifies for nothing is reported with the reason; nothing is invented.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app import courses, curriculum  # noqa: E402
from app.config import Settings  # noqa: E402
from app.harness import chromium_search, video, video_search  # noqa: E402


def concept_rows(course_id: str) -> list[dict]:
    """The lesson titles/keywords a curator would search for, in a stable order."""
    try:
        table = curriculum.course_concepts(course_id)
    except Exception:  # noqa: BLE001 - fall back to the authored lesson table
        table = {}
    if not table:
        table = curriculum.CONCEPTS
    rows = []
    for concept_id, entry in table.items():
        if not isinstance(entry, dict):
            continue
        rows.append({
            'id': str(concept_id),
            'title': str(entry.get('title') or concept_id),
            'keywords': [str(word) for word in (entry.get('keywords') or [])],
        })
    return sorted(rows, key=lambda row: row['id'])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('concepts', nargs='*', help='concept ids; omit with --all')
    parser.add_argument('--all', action='store_true', help='every concept in the course')
    parser.add_argument('--force', action='store_true',
                        help='re-curate concepts that already have an allowlist row')
    parser.add_argument('--limit', type=int, default=6,
                        help='candidates per search (1-10)')
    parser.add_argument('--pause', type=float, default=1.0,
                        help='seconds between concepts, to be polite to the provider')
    parser.add_argument('--course', default='',
                        help='course id (default: the shipped default course)')
    parser.add_argument('--json', action='store_true', help='one JSON object as output')
    args = parser.parse_args(argv)

    if not args.all and not args.concepts:
        parser.error('give concept ids or use --all')

    settings = Settings.from_env()
    if not getattr(settings, 'media_enabled', False):
        print('HARNESS_MEDIA_ENABLED is off; curation cannot search.', file=sys.stderr)
        return 2
    ready, why = chromium_search.available()
    if not ready:
        print(f'Chromium is unavailable: {why}', file=sys.stderr)
        return 2

    course_id = args.course or courses.DEFAULT_COURSE_ID
    rows = concept_rows(course_id)
    by_id = {row['id']: row for row in rows}
    wanted = rows if args.all else [by_id.get(cid) or {'id': cid, 'title': cid,
                                                       'keywords': []}
                                    for cid in args.concepts]
    table = video.load_allowlist(settings)
    existing = {str(row.get('concept_id')) for row in table.get(course_id, [])}

    started = time.monotonic()
    outcomes = []
    for concept in wanted:
        cid = concept['id']
        if cid in existing and not args.force:
            outcomes.append({'concept_id': cid, 'skipped': 'already curated'})
            if not args.json:
                print(f'  = {cid}: already curated')
            continue
        try:
            out = video_search.curate_for_concept(
                settings, concept, course_id, limit=max(1, min(args.limit, 10)))
        except Exception as exc:  # noqa: BLE001 - one bad concept must not stop a course
            out = {'curated': False, 'reason': f'{type(exc).__name__}: {exc}'}
        already_present = (out.get('reason') == 'already curated'
                           and bool((out.get('video') or {}).get('video_id')))
        record = {
            'concept_id': cid,
            'curated': bool(out.get('curated')),
            'already_present': already_present,
            'video_id': (out.get('video') or {}).get('video_id', ''),
            'reason': out.get('reason', ''),
            'path': out.get('path', ''),
        }
        outcomes.append(record)
        # ``--force`` re-runs the search, and a different winner is a legitimate
        # outcome. video.curate() is append-only and keyed by (concept_id,
        # video_id), so a second winner would leave TWO rows for the concept and
        # video.resolve() would hand the lesson both. Re-curating must *replace*,
        # not accumulate: prune the older rows only after a new winner has been
        # written, so a failed re-curation can never delete a working card.
        if args.force and record['curated'] and cid in existing:
            fresh = video.load_allowlist(settings)
            rows = fresh.get(course_id, [])
            kept = [row for row in rows
                    if not (str(row.get('concept_id')) == cid
                            and str(row.get('video_id')) != record['video_id'])]
            if len(kept) != len(rows):
                fresh[course_id] = kept
                video.save_allowlist(settings, fresh)
                record['replaced'] = len(rows) - len(kept)
        if not args.json:
            mark = '+' if record['curated'] else ('=' if already_present else '-')
            print(f'  {mark} {cid}: {record["video_id"] or record["reason"][:90]}')
        if args.pause:
            time.sleep(args.pause)

    summary = {
        'course_id': course_id,
        'chromium': chromium_search.available()[1],
        'considered': len(wanted),
        'curated': sum(1 for row in outcomes if row.get('curated')),
        'skipped': sum(1 for row in outcomes if row.get('skipped')),
        'already_present': sum(1 for row in outcomes if row.get('already_present')),
        'replaced': sum(int(row.get('replaced') or 0) for row in outcomes),
        'elapsed_seconds': round(time.monotonic() - started, 1),
        'outcomes': outcomes,
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f'\n{summary["curated"]} curated / {summary["considered"]} considered '
              f'({summary["skipped"]} already present, {summary["replaced"]} older rows '
              f'replaced) in {summary["elapsed_seconds"]}s -> '
              f'{video.allowlist_path(settings)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
