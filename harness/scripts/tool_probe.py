#!/usr/bin/env python3
"""Invoke the harness toolbox directly as a teacher and report what each surface produces.

This is the same call path the agent loop uses (`toolbox.invoke(ctx, name, args)`), so a
result here is what the teacher would get, without the latency of a model turn deciding
which tool to call. The point is to answer, per surface: does the harness produce a real
artefact, and what is it?
"""
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / 'backend'
sys.path.insert(0, str(BACKEND))

from app.config import Settings            # noqa: E402
from app import courses, db as db_module   # noqa: E402
from app.harness import toolbox            # noqa: E402

CONCEPT = 'permutations_and_combinations'


class Principal:
    """The minimum a tool reads off the authenticated principal."""

    def __init__(self, role='teacher'):
        self.id = 'probe-teacher'
        self.role = role
        self.email = 'tengyi@luminfest.local'


def context(settings, concept=CONCEPT):
    graph = courses.graph_for_node(concept)
    spec = courses.course_for_node(concept)
    return toolbox.ToolContext(
        db=None, user=Principal(), settings=settings, graph=graph,
        subject_kind=getattr(spec, 'subject_kind', 'mathematics'),
        course_id=getattr(spec, 'id', 'integrated_math_1'))


def show(name, result, limit=700):
    ok = getattr(result, 'ok', None)
    print(f'--- {name}: ok={ok}')
    refused = getattr(result, 'refused', None)
    if refused:
        print('    REFUSED:', str(refused)[:400])
    data = getattr(result, 'data', None)
    if data is not None:
        text = json.dumps(data, default=str)
        print('    data:', text[:limit])
    notes = getattr(result, 'notes', None)
    if notes:
        print('    notes:', str(notes)[:300])
    print()


def main():
    settings = Settings.from_env()
    ctx = context(settings)
    which = sys.argv[1] if len(sys.argv) > 1 else 'all'

    calls = {
        'figure': ('build_figure', {'concept_id': CONCEPT}),
        'simulation': ('write_simulation', {
            'title': 'Permutations and combinations explorer',
            'description': ('Let a learner choose n and r, then show how many ordered '
                            'arrangements P(n,r) and unordered selections C(n,r) exist, '
                            'so they can see the two counts differ by r!.')}),
        'video': ('find_video', {'concept_id': CONCEPT}),
        'slides': ('build_presentation', {'concept_id': CONCEPT}),
        'deck': ('generate_slides', {'title': 'Permutations and combinations',
                                     'concept_id': CONCEPT}),
        'quiz': ('check_understanding', {'concept_id': CONCEPT}),
        'board': ('whiteboard_write', {'board_id': f'board-{CONCEPT}',
                                       'text': 'P(5,2) = 5 x 4 = 20 ordered pairs',
                                       'x': 60, 'y': 90}),
        'board_read': ('whiteboard_read', {'board_id': f'board-{CONCEPT}'}),
        'textbook': ('read_concept', {'concept_id': CONCEPT}),
        'browser': ('browser_snapshot', {'url': 'https://en.wikipedia.org/wiki/Permutation'}),
    }

    targets = list(calls) if which == 'all' else [which]
    for key in targets:
        name, args = calls[key]
        try:
            result = toolbox.invoke(ctx, name, args)
            show(f'{key} -> {name}', result)
        except Exception as exc:                       # a crash is a finding too
            print(f'--- {key} -> {name}: EXCEPTION {type(exc).__name__}: {str(exc)[:300]}')
            print()


if __name__ == '__main__':
    main()
