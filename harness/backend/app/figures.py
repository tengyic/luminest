"""Subject-aware figures.

The symbolic engine in :mod:`app.mathkit` builds a figure by matching a concept
against mathematics templates and falling back to a generic quadratic. For a
mathematics course that is exactly right. For any other subject it is actively
misleading: handed "Newton's second law" it returns a parabola and labels it with
the concept's name, so a learner sees a meaningless curve presented as physics.

So figures are dispatched by subject kind.

* ``mathematics`` courses use the symbolic engine, unchanged.
* every other subject gets a **concept map**: the idea in the centre, what it
  rests on to the left, what it unlocks to the right, and the learner's own
  mastery on each. That is real, derived content - it comes from the graph's own
  edges and the learner's own recorded evidence - rather than a decorative
  substitute.
"""

from __future__ import annotations

from typing import Any, Mapping

from .mathkit import build as build_simulation
from .mathkit.templates import template_for

#: Figure kinds this module can emit.
MATHEMATICAL = 'mathematical'
CONCEPT_MAP = 'concept_map'

#: The symbolic engine's last-resort template. It draws a quadratic probe, which is only
#: honest when the concept really is "a quantity as a function of one variable" — so it
#: is never served as a learner-facing figure.
GENERIC_PROBE_KIND = 'function_probe'

#: How many neighbours to draw before the map stops being readable.
MAX_NEIGHBOURS = 5


def _label(graph, node_id: str) -> str:
    node = graph.nodes.get(node_id)
    return node.title if node is not None else node_id


def _mastery(states: Mapping[str, Any], node_id: str) -> float:
    return float((states.get(node_id) or {}).get('mastery', 0.0))


def _neighbour(graph, node_id: str, states: Mapping[str, Any]) -> dict[str, Any]:
    node = graph.nodes.get(node_id)
    return {
        'id': node_id,
        'label': _label(graph, node_id),
        'tier': getattr(node, 'tier', '') or '',
        'difficulty': int(getattr(node, 'difficulty', 3) or 3),
        'mastery': round(_mastery(states, node_id), 4),
    }


def concept_map(node: Mapping[str, Any], graph, states: Mapping[str, Any] | None = None,
                limit: int = MAX_NEIGHBOURS) -> dict[str, Any]:
    """A concept-relationship figure for any subject.

    Every field is derived: the neighbours come from the graph's own prerequisite
    and teaching-order edges, and the mastery values come from the learner's
    recorded evidence. Nothing here is decorative.
    """
    states = states or {}
    node_id = str(node.get('id') or '')
    title = str(node.get('title') or node_id)
    summary = str(node.get('summary') or '')

    prerequisites = [n for n in graph.parents(node_id) if n in graph.nodes][:limit]
    dependants = [n for n in graph.children(node_id) if n in graph.nodes][:limit]
    siblings = [n for n in graph.in_unit(node_id) if n != node_id][:limit]
    deeper = [n for n in graph.ancestors(node_id) if n in graph.nodes]

    mastery = _mastery(states, node_id)
    weak = [n for n in prerequisites if _mastery(states, n) < 0.6]
    ready = [n for n in dependants if _mastery(states, n) >= 0.6]

    steps: list[str] = []
    if prerequisites:
        steps.append(
            f'This idea rests on {len(prerequisites)} earlier one(s): '
            + ', '.join(_label(graph, n) for n in prerequisites)
            + '. Reading them first is what makes this one land.'
        )
    else:
        steps.append('This is a starting point in the course - it has no prerequisite '
                     'inside this course, so it can be met at any time.')
    if weak:
        steps.append(
            f'{len(weak)} of those prerequisites measure below 0.60 for you right now: '
            + ', '.join(_label(graph, n) for n in weak)
            + '. A weak prerequisite is the most common reason a later idea feels hard.'
        )
    if dependants:
        steps.append(
            f'Understanding this unlocks {len(dependants)} later idea(s): '
            + ', '.join(_label(graph, n) for n in dependants)
            + '.'
        )
    if deeper:
        steps.append(
            f'Counting indirect dependencies, {len(deeper)} concept(s) in this course sit '
            f'underneath this one in the prerequisite order.'
        )
    if node.get('unit'):
        steps.append(f'It sits in the unit "{node["unit"]}"'
                     + (f', topic "{node["topic"]}".' if node.get('topic') else '.'))

    readouts = [
        {'label': 'Your mastery here', 'value': round(mastery, 2), 'kind': 'mastery'},
        {'label': 'Direct prerequisites', 'value': len(prerequisites), 'kind': 'count'},
        {'label': 'Prerequisites below 0.60', 'value': len(weak), 'kind': 'gap'},
        {'label': 'Ideas this unlocks', 'value': len(dependants), 'kind': 'count'},
        {'label': 'Concepts depending on this', 'value': len(deeper), 'kind': 'count'},
    ]

    notes = [
        'This is a concept map derived from the course graph, not a simulation. '
        'No physical or mathematical model is being claimed here.',
    ]
    if not graph.parents(node_id) and not graph.children(node_id):
        notes.append('This concept is currently isolated in the graph: it has neither '
                     'prerequisites nor dependants, so the map shows the idea alone.')

    return {
        'figure': 'map',
        'kind': CONCEPT_MAP,
        'title': title,
        'objective': summary,
        'variable': '',
        'discrete': False,
        'domain': None,
        'focus': {'id': node_id, 'label': title, 'tier': str(node.get('tier') or ''),
                  'difficulty': int(node.get('difficulty') or 3), 'mastery': round(mastery, 4)},
        'prerequisites': [_neighbour(graph, n, states) for n in prerequisites],
        'dependants': [_neighbour(graph, n, states) for n in dependants],
        'siblings': [_neighbour(graph, n, states) for n in siblings],
        'marks': [],
        'parameters': [],
        'parts': [],
        'series': [],
        'secondary': None,
        'features': [],
        'table': None,
        'probe': None,
        'steps': steps,
        'readouts': readouts,
        'notes': notes,
        'engine': 'concept-map',
    }


def figure_for(node: Mapping[str, Any], graph, states: Mapping[str, Any] | None = None,
               subject_kind: str = MATHEMATICAL) -> dict[str, Any]:
    """Dispatch to the right figure builder for the subject.

    ``subject_kind`` is ``'mathematics'`` only for courses where the symbolic engine
    is actually valid. Anything else gets a concept map.

    A mathematics concept that matches no template is *also* given a concept map rather
    than the engine's generic probe. The probe is a quadratic, so serving it would put a
    parabola on screen labelled with whatever concept was asked for — the exact failure
    this module exists to prevent, just reached through the mathematics branch instead of
    the science one. The concept map is derived from the graph's own edges, so it is
    always true even when no figure has been written yet.
    """
    if subject_kind == 'mathematics':
        spec = template_for(node)
        if spec.kind != GENERIC_PROBE_KIND:
            payload = build_simulation(spec)
            payload['engine'] = 'symbolic'
            return payload
    return concept_map(node, graph, states)


__all__ = ['MATHEMATICAL', 'CONCEPT_MAP', 'GENERIC_PROBE_KIND', 'concept_map', 'figure_for',
           'MAX_NEIGHBOURS']
