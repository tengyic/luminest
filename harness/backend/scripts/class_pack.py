"""Print the class the harness can actually deliver for a concept, and what it cannot.

This is the "prepare a class" check, run entirely server-side: it asks
:func:`app.procedure_service.assets_for` what exists, generates the figure with the
symbolic engine, searches for a video through the same verified path the teacher's tool
uses, and reviews every asset with :mod:`app.harness.teaching.assets`. Nothing here
invents content — a missing asset is printed as a missing asset with the harness's own
reason for it.

Run from ``backend/``::

    ../ui-tests/.venv/bin/python scripts/class_pack.py permutations_and_combinations
    ../ui-tests/.venv/bin/python scripts/class_pack.py --all-algebra   # every concept

``--all-algebra`` is the confidence check: it reports, per concept, whether the class has
a figure, a video and practice items, so a gap is a number rather than an impression.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import courses, figures, procedure_service                 # noqa: E402
from app.config import Settings                                    # noqa: E402
from app.harness import video_search                               # noqa: E402
from app.harness.teaching import assets                            # noqa: E402

COURSE = 'integrated_math_1'


def pack(concept_id: str, settings, *, course_id: str = COURSE, search_video: bool = True) -> dict:
    graph = courses.graph_for(course_id)
    if concept_id not in graph.nodes:
        raise SystemExit(f'{concept_id!r} is not a concept in {course_id}')
    node = graph.nodes[concept_id]
    concept = node.to_dict()

    try:
        delivered = procedure_service.assets_for(
            concept_id, course_id=course_id, graph=graph, settings=settings,
            subject_kind=courses.subject_kind_for(concept_id))
    except procedure_service.UnknownConcept:
        delivered = None

    figure = figures.figure_for(concept, graph, {},
                                subject_kind=courses.subject_kind_for(concept_id))

    video = None
    if search_video:
        import types
        ctx = types.SimpleNamespace(settings=settings, role='teacher')
        found = video_search.search_videos(ctx, concept.get('title', ''), limit=3)
        if found.get('ok'):
            video = next((card for card in found['videos'] if card.get('verified')),
                         (found['videos'] or [None])[0])

    review = assets.sweep(concept, {k: v for k, v in
                                    (('simulation', figure), ('video', video)) if v is not None})
    return {'concept': concept, 'delivered': delivered, 'figure': figure,
            'video': video, 'review': review,
            'plan': assets.plan_repair(review['reviews'],
                                       can_search_video=bool(settings.media_enabled))}


def _print_pack(result: dict) -> None:
    concept = result['concept']
    delivered = result['delivered']
    print(f"\n=== {concept.get('title')}  [{concept.get('id')}] ===")
    print(f"  figure      : {result['figure'].get('kind')} — {result['figure'].get('title')}")
    for item in result['figure'].get('readouts') or ():
        print(f"                {item['label']}: {item['value']}")
    if result['video']:
        video = result['video']
        print(f"  video       : {'embed' if video.get('verified') else 'link'} — "
              f"{video.get('title')} ({video.get('channel')})")
        print(f"                {video.get('embed_url') or video.get('watch_url')}")
    else:
        print('  video       : none found')
    if delivered:
        print(f"  deck        : {len(delivered.deck_sections)} section(s)")
        print(f"  practice    : {delivered.practice_count} authored item(s)")
        if delivered.worked_example:
            print(f"  worked ex.  : {str(delivered.worked_example.get('title'))[:60]}")
        for name, reason in (delivered.reasons or {}).items():
            print(f"  missing {name:12s}: {reason[:90]}")
    print(f"  review      : {assets.describe(result['review']['reviews']) or 'all assets ok'}")
    for entry in result['plan']:
        print(f"  repair      : show {entry['substitute']} now, then {entry['fix']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('concepts', nargs='*')
    parser.add_argument('--course', default=COURSE,
                        help='course id (default: %(default)s). Only algebra_2 has authored '
                             'lesson blocks for every concept; integrated_math_1 has 15 of 164.')
    parser.add_argument('--all-algebra', action='store_true')
    parser.add_argument('--no-video', action='store_true')
    args = parser.parse_args()
    course_id = args.course

    settings = Settings.from_env()
    print(f"environment: {settings.environment} · media: {settings.media_enabled} · "
          f"provider: {settings.provider}")

    if args.all_algebra:
        graph = courses.graph_for(course_id)
        tally = {'figure': 0, 'video': 0, 'practice': 0, 'deck': 0}
        gaps = []
        for concept_id in graph.nodes:
            result = pack(concept_id, settings, course_id=course_id, search_video=False)
            delivered = result['delivered']
            has = {'figure': result['figure'].get('kind') not in ('concept_map',),
                   'video': bool(result['video']),
                   'practice': bool(delivered and delivered.practice_count),
                   'deck': bool(delivered and delivered.deck_sections)}
            for key, present in has.items():
                tally[key] += bool(present)
            if not has['figure'] or not has['practice']:
                gaps.append((concept_id, has))
        total = len(graph.nodes)
        print(f'\n{total} concepts in {course_id}')
        for key, count in tally.items():
            print(f'  {key:9s} {count:4d}/{total} = {count / total:.0%}')
        if gaps:
            print(f'\n{len(gaps)} concept(s) without a figure or practice:')
            for concept_id, has in gaps[:40]:
                print(f'  {concept_id:48s} figure={has["figure"]} practice={has["practice"]}')
        return 0

    for concept_id in args.concepts:
        _print_pack(pack(concept_id, settings, course_id=course_id,
                         search_video=not args.no_video))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
