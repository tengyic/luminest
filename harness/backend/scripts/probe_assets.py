"""Measure what the generators actually produce, concept by concept.

The question this answers is the one that cannot be answered from a single example: when
the harness is pointed at *any* concept in the shipped courses, does it produce something
about that concept? It generates a figure for every concept, reviews it with
:mod:`app.harness.teaching.assets`, and prints the tally plus every failure with the
template that claimed it.

Run from ``backend/``::

    ../ui-tests/.venv/bin/python scripts/probe_assets.py                 # every pack
    ../ui-tests/.venv/bin/python scripts/probe_assets.py algebra_one_year
    ../ui-tests/.venv/bin/python scripts/probe_assets.py --failures-only

Exit status is 1 when any concept is ``off_topic`` or ``broken``, so this can be wired
into CI once the template table is good enough to hold that line.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import figures                                      # noqa: E402
from app.courses import COURSES                             # noqa: E402
from app.harness.teaching import assets                      # noqa: E402

PACKS = ROOT / 'app' / 'curriculum_packs'


class _IsolatedGraph:
    """The smallest graph ``concept_map`` accepts: no prerequisites, no dependants.

    Used only for non-mathematics packs, where the honest figure is a concept map and the
    review verdict is therefore the same whether or not the graph is populated.
    """

    def parents(self, node_id: str) -> list[str]:
        return []

    def children(self, node_id: str) -> list[str]:
        return []

    def siblings(self, node_id: str) -> list[str]:
        return []

    def in_unit(self, node_id: str) -> list[str]:
        return [node_id]

    def ancestors(self, node_id: str) -> list[str]:
        return []

    def descendants(self, node_id: str) -> list[str]:
        return []

    nodes: dict = {}


def subject_kind_of(pack: str) -> str:
    """The subject kind the app would give this pack, from the shipped course table."""
    for course in COURSES:
        if course.pack == pack:
            return course.subject_kind
    return 'unknown'


def pack_names() -> list[str]:
    return sorted(path.stem for path in PACKS.glob('*.json'))


def concepts_of(name: str) -> list[dict]:
    data = json.loads((PACKS / f'{name}.json').read_text(encoding='utf-8'))
    return list(data.get('concepts') or [])


def probe(name: str) -> tuple[Counter, list[tuple[str, dict, dict]]]:
    tally: Counter = Counter()
    failures: list[tuple[str, dict, dict]] = []
    kind = subject_kind_of(name)
    for concept in concepts_of(name):
        # Same dispatch the application uses: the symbolic engine only where it is valid.
        payload = figures.figure_for(concept, _IsolatedGraph(), {}, subject_kind=kind)
        review = assets.review_simulation(concept, payload)
        tally[review['verdict']] += 1
        tally[f"kind:{review.get('kind') or payload.get('kind')}"] += 1
        if not review['usable']:
            failures.append((name, concept, review))
    return tally, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('packs', nargs='*', help='pack names (default: all)')
    parser.add_argument('--failures-only', action='store_true')
    args = parser.parse_args()

    names = args.packs or pack_names()
    grand: Counter = Counter()
    all_failures: list[tuple[str, dict, dict]] = []
    for name in names:
        if not (PACKS / f'{name}.json').exists():
            print(f'skip {name}: no such pack')
            continue
        tally, failures = probe(name)
        grand.update(tally)
        all_failures.extend(failures)
        total = sum(count for verdict, count in tally.items() if not verdict.startswith('kind:'))
        if not args.failures_only:
            print(f'\n{name}: {total} concepts')
            for verdict in assets.VERDICTS:
                if tally.get(verdict):
                    print(f'  {verdict:10s} {tally[verdict]:4d}')

    print('\n=== totals ===')
    for verdict in assets.VERDICTS:
        if grand.get(verdict):
            print(f'  {verdict:10s} {grand[verdict]:4d}')
    judged = sum(grand[verdict] for verdict in ('ok', 'fallback', 'off_topic', 'broken'))
    if judged:
        ok = grand['ok']
        print(f'  on-topic share: {ok}/{judged} = {ok / judged:.1%}')

    if all_failures:
        print(f'\n=== {len(all_failures)} failure(s) ===')
        for pack, concept, review in all_failures:
            print(f"[{review['verdict']}] {pack}/{concept.get('id')} "
                  f"({concept.get('title')}) -> {review.get('kind')}")
            print(f"    {review['why'][:160]}")
    return 1 if any(review['verdict'] in ('off_topic', 'broken')
                    for _, _, review in all_failures) else 0


if __name__ == '__main__':
    raise SystemExit(main())
