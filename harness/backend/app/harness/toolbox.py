"""The harness toolbox: the complete set of actions the agentic loop may take.

A harness is not an app of predefined content. It is a *system* that decides, from
evidence about one learner, what to do next - and then does it by calling a tool. The
toolbox is therefore the honest boundary of the system: if an action is not here, the
loop cannot take it, and everything the loop does is inspectable after the fact.

Three rules shape this module.

1. **One gate for material.** Anything that reads outside material goes through
   :mod:`app.ingest.policy`. Sources that are not cleared for reuse are returned as
   link-only references: the harness records that they exist and never copies their
   text. There is no override, because a single gate is auditable and a scattered set
   of checks is not.

2. **Tools return evidence, not verdicts.** ``read_learner_evidence`` reports counts and
   categories with their sampling limits attached. A tool never says "the learner does
   not understand X"; it says "3 of the last 4 attempts on X selected the option whose
   error process is adding denominators".

3. **Tools are cheap and deterministic where they can be.** Figures, case studies,
   flashcards and MCQs are composed from real curriculum structure and the symbolic
   maths engine, so the offline harness still produces genuine content rather than a
   placeholder that pretends a model ran.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from ..curriculum import (CONCEPTS, GRAPH_TO_LESSON, KNOWLEDGE_GRAPH, LESSON_TARGETS,
                          QUESTIONS)
from ..ingest import policy
from ..mathkit import MathSyntaxError, build as build_simulation

#: Postures a tool can have, from most to least trusted.
#: ``internal``  reads this project's own graph and curriculum;
#: ``personal``  reads one learner's own records;
#: ``ingestible`` may read outside text because the licence clears it;
#: ``embed_only`` may hand back a provider-hosted player or a licence-cleared media file,
#:                and must never hold a copy of anything the licence does not clear;
#: ``link_only``  may name an outside source but must never return its text;
#: ``sandboxed`` executes learner-supplied code inside a restricted workspace.
POSTURES = ('internal', 'personal', 'ingestible', 'embed_only', 'link_only', 'sandboxed')


@dataclass(frozen=True)
class ToolSpec:
    """The declaration the loop and the system prompt both read.

    ``requires`` names the importable modules a tool needs beyond the standard library
    and the harness's own code. It is empty for every tool whose dependencies are part of
    the declared runtime requirements, which is almost all of them. It exists for the few
    that sit on an *optional* package, because a tool that is listed to the model but can
    only ever refuse is worse than one that is not listed at all: the model spends a turn
    discovering it cannot work, and the failure looks like a bug rather than a build
    decision. ``available`` below turns that into a fact the catalogue reports.
    """

    name: str
    summary: str
    arguments: str
    posture: str
    returns: str
    requires: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {'name': self.name, 'summary': self.summary, 'arguments': self.arguments,
                'posture': self.posture, 'returns': self.returns,
                'requires': list(self.requires), 'available': available(self)}

    def signature(self) -> str:
        return f'{self.name}({self.arguments}) -> {self.returns} [{self.posture}]'


@dataclass
class ToolResult:
    """What a tool hands back.

    ``citations`` is not decoration. Every claim the harness later makes to a learner
    has to be traceable to one of these entries, which is why the field is on the
    result rather than assembled later by the caller.
    """

    tool: str
    ok: bool
    data: Any = None
    citations: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    refused: str = ''
    error: str = ''
    #: Images this tool produced, as validated ``data:`` URLs. They are *not* part of the
    #: text payload: OpenAI's ``role: 'tool'`` message cannot carry an image, so
    #: ``agent_loop`` re-injects them as a user message with image parts before the next
    #: step. That is the mechanism that makes the loop see-act-see instead of
    #: see-act-blindly.
    images: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        # The count, not the bytes: an event trace or a tool message holding four 2 MB
        # data URLs is unusable, and the model gets the images through the dedicated
        # message the loop appends.
        return {'tool': self.tool, 'ok': self.ok, 'data': self.data,
                'citations': self.citations, 'notes': self.notes,
                'refused': self.refused, 'error': self.error,
                'images': len(self.images)}


class ToolRefused(RuntimeError):
    """Raised inside a tool when policy forbids the action."""


@dataclass
class ToolContext:
    """Everything a tool is allowed to know about the call."""

    db: Any = None
    user: Any = None
    settings: Any = None
    now: float = 0.0
    workspace: Any = None
    #: The knowledge graph this call is scoped to. A learner is enrolled in one course,
    #: and resolving against a different course's graph would hand them an empty
    #: neighbourhood - a tool that looks like it works and returns nothing.
    graph: Any = None
    #: ``mathematics`` routes through the symbolic engine; anything else does not.
    #: The default matches the default course, so a context built without an explicit
    #: course behaves exactly as before the multi-subject layer existed.
    subject_kind: str = 'mathematics'
    #: The learner's course id. Media curation is keyed by course, so a tool that resolved
    #: a simulation or a curated video without this would silently return nothing.
    course_id: str = ''

    @property
    def user_id(self) -> str:
        return getattr(self.user, 'id', '') or ''


def graph_for(ctx) -> Any:
    """The graph this call is scoped to, falling back to the mathematics course.

    This is the single place that decides which graph a tool reads. Without it, every
    tool would reach for the module-level mathematics graph and a physics learner would
    get correct-looking empty answers.
    """
    return getattr(ctx, 'graph', None) or KNOWLEDGE_GRAPH


# --------------------------------------------------------------------- helpers

def _node_or_lesson(ctx, concept_id: str) -> dict[str, Any] | None:
    """Resolve a graph node id *or* an authored lesson id, within this call's graph.

    Two namespaces name the same idea (``fractions`` is a lesson, ``fraction_equivalence``
    is a node), and a caller may hold either. Resolution is against the graph the context
    carries, so a concept from any course resolves to its own course's node.
    """
    graph = graph_for(ctx)
    node = graph.nodes.get(concept_id)
    if node is None:
        target = LESSON_TARGETS.get(concept_id) or ''
        node = graph.nodes.get(target) if target else None
    return node.to_dict() if node is not None else None


def _lesson_for(concept_id: str) -> dict | None:
    """The authored lesson whose questions and blocks belong to this id."""
    if concept_id in CONCEPTS:
        return CONCEPTS[concept_id]
    lesson_id = GRAPH_TO_LESSON.get(concept_id)
    return CONCEPTS.get(lesson_id) if lesson_id else None


def _node_citation(node: Mapping[str, Any]) -> dict[str, Any]:
    provenance = dict(node.get('provenance') or {})
    return {'kind': 'concept_node', 'id': node.get('id', ''), 'title': node.get('title', ''),
            'source': provenance.get('source', 'internal curriculum graph'),
            'url': provenance.get('url', ''), 'licence': provenance.get('licence', 'project-authored'),
            'licence_class': provenance.get('licence_class', 'internal')}


def _lesson_citation(lesson: Mapping[str, Any]) -> dict[str, Any]:
    return {'kind': 'authored_lesson', 'id': lesson.get('id', ''), 'title': lesson.get('title', ''),
            'source': 'Project-authored curriculum', 'url': '', 'licence': 'project-authored',
            'licence_class': 'internal'}


def _matches(query: str, *fields: str) -> bool:
    needle = query.strip().casefold()
    if not needle:
        return False
    return any(needle in (value or '').casefold() for value in fields)


def _policy_for(name: str) -> policy.SourcePolicy | None:
    for entry in (policy.WIKIDATA, policy.OPERATOR_SCOPE_SEQUENCE, *policy.RESTRICTED):
        if entry.name.casefold() == name.strip().casefold():
            return entry
    return None


def _learner_state(db, user_id: str, concept_id: str) -> dict:
    from ..db import State
    from sqlalchemy import select
    if not db or not user_id:
        return {}
    row = db.scalar(select(State).where(State.user_id == user_id, State.concept_id == concept_id))
    return dict(row.data) if row else {}


def learner_states(ctx) -> dict[str, dict]:
    """This learner's recorded state, projected onto graph node ids.

    Attempts are written against whatever id the question carried - an authored lesson
    id for the mathematics course, a graph node id for a generated course. A figure
    reads node ids, so both keys are offered and a lookup cannot silently miss.
    """
    from ..db import State
    from sqlalchemy import select
    if ctx is None or not getattr(ctx, 'db', None) or not getattr(ctx, 'user_id', ''):
        return {}
    projected: dict[str, dict] = {}
    for row in ctx.db.scalars(select(State).where(State.user_id == ctx.user_id)):
        data = dict(row.data or {})
        projected.setdefault(row.concept_id, data)
        projected.setdefault(LESSON_TARGETS.get(row.concept_id, row.concept_id), data)
    return projected


def _attempt_rows(db, user_id: str, concept_id: str, limit: int = 12) -> list:
    """Attempts for one concept, resolving either namespace.

    A question is written against an authored lesson (``fractions``); the graph node
    (``fraction_equivalence``) is a different id for the same thing. The loop already
    resolves both, so a tool that did not would silently return an empty sample when
    handed a node id - the failure mode being a tool that looks like it works.
    """
    from ..db import Attempt
    from sqlalchemy import select
    if not db or not user_id:
        return []
    lesson = concept_id if concept_id in CONCEPTS else (GRAPH_TO_LESSON.get(concept_id) or concept_id)
    statement = (select(Attempt).where(Attempt.user_id == user_id, Attempt.concept_id == lesson)
                 .order_by(Attempt.created_at.desc()).limit(limit))
    return list(db.scalars(statement))


# ------------------------------------------------------------------- the tools

def search_concepts(ctx: ToolContext, query: str, limit: int = 8) -> ToolResult:
    """Search the course graph. The entry point when the loop is unsure what to teach."""
    graph = graph_for(ctx)
    hits = graph.search(query, limit=max(1, min(25, int(limit))))
    return ToolResult('search_concepts', True, {'query': query, 'hits': hits},
                      citations=[{'kind': 'concept_graph', 'source': 'internal curriculum graph',
                                  'licence_class': 'internal'}],
                      notes=[f'{len(graph.nodes)} concepts are indexed; relevance is '
                             'deterministic term overlap, not a semantic embedding.'])


def read_concept(ctx: ToolContext, concept_id: str, include_lesson: bool = True) -> ToolResult:
    """Read one concept: graph classification, neighbourhood and authored lesson."""
    graph = graph_for(ctx)
    node = _node_or_lesson(ctx, concept_id)
    if node is None:
        return ToolResult('read_concept', False, error=f'Unknown concept {concept_id!r}')
    node_id = node['id']
    payload: dict[str, Any] = {
        'node': node,
        'prerequisites': graph.all_parents(node_id),
        'direct_prerequisites': graph.parents(node_id),
        'sequence_predecessors': [p for p, c in graph.sequence_edges if c == node_id],
        'dependants': graph.children(node_id),
        'ancestors': graph.ancestors(node_id),
        'classification': graph.classify(graph.nodes[node_id]),
    }
    citations = [_node_citation(node)]
    if include_lesson:
        lesson = _lesson_for(concept_id) or _lesson_for(node_id)
        if lesson:
            payload['lesson'] = {'id': lesson['id'], 'title': lesson['title'], 'unit': lesson['unit'],
                                 'summary': lesson['summary'], 'hint': lesson['hint'],
                                 'blocks': lesson['blocks'], 'project': lesson['project'],
                                 'media': lesson['media']}
            citations.append(_lesson_citation(lesson))
    return ToolResult('read_concept', True, payload, citations=citations)


def inspect_prerequisites(ctx: ToolContext, concept_id: str, threshold: float = 0.6) -> ToolResult:
    """Which prerequisites are actually weak, per the learner's own evidence.

    This is the tool that answers "why is this learner stuck here". It reports every
    prerequisite with its measured mastery and how much evidence that number rests on,
    so a low number with one attempt is visibly different from a low number with ten.
    """
    graph = graph_for(ctx)
    node = _node_or_lesson(ctx, concept_id)
    if node is None:
        return ToolResult('inspect_prerequisites', False, error=f'Unknown concept {concept_id!r}')
    closure = graph.all_parents(node['id'])
    rows = []
    for cid in closure:
        lesson_id = GRAPH_TO_LESSON.get(cid, cid)
        state = _learner_state(ctx.db, ctx.user_id, lesson_id) or _learner_state(ctx.db, ctx.user_id, cid)
        mastery = float(state.get('mastery', 0.15))
        attempts = int(state.get('attempts', 0))
        rows.append({'concept_id': cid, 'title': graph.nodes[cid].title,
                     'lesson_id': lesson_id if lesson_id in CONCEPTS else '',
                     'mastery': round(mastery, 4), 'attempts': attempts,
                     'evidence_strength': 'none' if attempts == 0 else ('thin' if attempts < 3 else 'usable'),
                     'below_threshold': attempts > 0 and mastery < threshold})
    weak = [r for r in rows if r['below_threshold']]
    rows.sort(key=lambda r: (r['mastery'], r['concept_id']))
    return ToolResult('inspect_prerequisites', True,
                      {'concept_id': node['id'], 'closure': rows, 'weak': weak,
                       'threshold': threshold},
                      notes=['Mastery is a heuristic posterior over responses, not a measurement '
                             'of understanding. A prerequisite with no attempts is unknown, not weak.'])


def recall_learner_memory(ctx: ToolContext, concept_id: str = '', limit: int = 10,
                          kinds: Sequence[str] = ()) -> ToolResult:
    """Read what the harness already believes about this learner, with decay applied."""
    from . import memory
    if not ctx.db or not ctx.user_id:
        return ToolResult('recall_learner_memory', True, {'notes': [], 'digest': ''},
                          notes=['No learner is bound to this call.'])
    related: Iterable[str] = ()
    node = _node_or_lesson(ctx, concept_id) if concept_id else None
    if node:
        graph = graph_for(ctx)
        related = [*graph.all_parents(node['id']), *graph.children(node['id'])]
    notes = memory.recall(ctx.db, ctx.user_id, concept_id=concept_id or None,
                          kinds=list(kinds) or None, limit=limit, now=ctx.now or None,
                          related=related)
    digest = memory.digest(ctx.db, ctx.user_id, concept_id=concept_id, related=related, limit=limit)
    return ToolResult('recall_learner_memory', True,
                      {'notes': [n.to_dict() for n in notes], 'digest': digest,
                       'summary': memory.summarise(notes)},
                      citations=[{'kind': 'learner_memory', 'source': 'this account only',
                                  'licence_class': 'personal'}],
                      notes=['Beliefs decay with a three-week half-life and are never promoted to facts.'])


def read_learner_evidence(ctx: ToolContext, concept_id: str, limit: int = 12) -> ToolResult:
    """Recent scored attempts for one concept, with the error categories they imply."""
    rows = _attempt_rows(ctx.db, ctx.user_id, concept_id, limit)
    # Only incorrect responses contribute an error category; a correct response's
    # category describes support, not a mistake.
    categories: dict[str, int] = {}
    for row in rows:
        if not row.correct:
            categories[row.category] = categories.get(row.category, 0) + 1
    correct = sum(1 for row in rows if row.correct)
    return ToolResult('read_learner_evidence', True,
                      {'concept_id': concept_id, 'sample': len(rows), 'correct': correct,
                       'incorrect': len(rows) - correct,
                       'accuracy': round(correct / len(rows), 4) if rows else None,
                       'error_categories': [{'category': k, 'count': v}
                                            for k, v in sorted(categories.items(), key=lambda kv: (-kv[1], kv[0]))],
                       'recent': [{'question_id': r.question_id, 'correct': r.correct,
                                   'category': r.category, 'elapsed_seconds': r.elapsed_seconds,
                                   'confidence': r.confidence} for r in rows]},
                      notes=[f'Sample size {len(rows)}; below about five attempts, error categories '
                             'cannot separate a slip from a gap.'])


def search_material(ctx: ToolContext, query: str, limit: int = 8,
                    include_external: bool = True) -> ToolResult:
    """Search available material, honouring the licence gate on every outside source.

    Internal structure and cleared sources come back as content. Everything else comes
    back as a link with an explicit reason why no text was returned.
    """
    graph = graph_for(ctx)
    internal = graph.search(query, limit=limit)
    internal.extend({'id': node.id, 'title': node.title, 'unit': node.unit,
                     'has_lesson': node.has_lesson, 'score': 60, 'strand': node.strand}
                    for node in graph.nodes.values()
                    if _matches(query, node.title, node.summary))
    seen, deduped = set(), []
    for hit in sorted(internal, key=lambda h: (-h.get('score', 0), h['id'])):
        if hit['id'] in seen:
            continue
        seen.add(hit['id'])
        deduped.append(hit)

    external: list[dict[str, Any]] = []
    if include_external:
        for entry in (policy.WIKIDATA, policy.OPERATOR_SCOPE_SEQUENCE, *policy.RESTRICTED):
            if not _matches(query, entry.name, entry.scope, entry.licence):
                continue
            external.append({'name': entry.name, 'url': entry.url, 'licence': entry.licence,
                             'licence_class': entry.licence_class.value, 'scope': entry.scope,
                             'ingestible': entry.ingestible,
                             'mode': 'ingestible' if entry.ingestible else 'link_only',
                             'text_returned': False,
                             'refusal_reason': '' if entry.ingestible else
                             'This source is not cleared for reuse; the harness records the link '
                             'and returns no text.'})
    return ToolResult('search_material', True,
                      {'query': query, 'internal': deduped[:limit], 'external': external},
                      citations=[{'kind': 'concept_graph', 'source': 'internal curriculum graph',
                                  'licence_class': 'internal'}],
                      notes=['Restricted sources are returned as links only. No text from a '
                             'link-only or prohibited source is ever returned by any tool.'])


def fetch_material_text(ctx: ToolContext, source_name: str) -> ToolResult:
    """Return outside text *only* when the licence explicitly clears it.

    Deliberately narrow. The point of the tool is that the refusal is a first-class
    outcome rather than an exception the caller has to remember to catch.
    """
    entry = _policy_for(source_name)
    if entry is None:
        return ToolResult('fetch_material_text', False, refused=f'Unknown source {source_name!r}',
                          error='Unknown source')
    try:
        policy.assert_ingestible(entry)
    except policy.IngestionRefused as refusal:
        return ToolResult('fetch_material_text', False, data={'source': entry.to_dict()},
                          refused=str(refusal),
                          notes=['Recorded as a link-only reference instead.'])
    return ToolResult('fetch_material_text', True,
                      {'source': entry.to_dict(), 'provenance': policy.provenance_for(entry),
                       'text': ''},
                      citations=[policy.provenance_for(entry)],
                      notes=['No local copy of this source exists in the build; ingestion is an '
                             'operator step that writes nodes into the graph.'])


def prepare_case_study(ctx: ToolContext, concept_id: str, angle: str = '') -> ToolResult:
    """Compose a case study from project-authored curriculum and the graph neighbourhood.

    Grounded by construction: the setting, the quantities and the expected reasoning all
    come from the concept's own authored blocks, so the case study cannot drift off the
    syllabus it is meant to teach.
    """
    graph = graph_for(ctx)
    node = _node_or_lesson(ctx, concept_id)
    lesson = _lesson_for(concept_id)
    if node is None and lesson is None:
        return ToolResult('prepare_case_study', False, error=f'Unknown concept {concept_id!r}')
    title = (lesson or node)['title']
    summary = (lesson or {}).get('summary') or node.get('summary', '')
    blocks = (lesson or {}).get('blocks', [])
    concept_block = next((b for b in blocks if b.get('kind') == 'concept'), None)
    worked = next((b for b in blocks if b.get('kind') == 'worked_example'), None)
    prerequisites = [graph.nodes[p].title for p in
                     graph.parents(node['id'] if node else '')] if node else []
    dependants = [graph.nodes[c].title for c in
                  graph.children(node['id'])] if node else []
    study = {
        'title': f'{title}: a case to reason through',
        'angle': angle or 'apply the idea to a situation where the numbers are not round',
        'setting': summary,
        'core_idea': (concept_block or {}).get('body', ''),
        'formula': (concept_block or {}).get('formula', ''),
        'worked_example': (worked or {}).get('body', ''),
        'prerequisites_to_use': prerequisites,
        'where_this_leads': dependants[:4],
        'tasks': [
            {'prompt': 'State what is given, what is asked, and which relationship connects them.',
             'looks_for': 'An explicit list of quantities with units, and a named relationship.'},
            {'prompt': 'Carry out the method, showing each step so a reader can follow it.',
             'looks_for': 'A valid method with intermediate steps, not only a final number.'},
            {'prompt': 'Change one quantity and predict the effect before recomputing.',
             'looks_for': 'A prediction, then a check that matches or explains the difference.'},
            {'prompt': 'Say what would make your answer wrong.',
             'looks_for': 'A named failure mode, for example a unit slip or an invalid step.'},
        ],
        'rubric': (lesson or {}).get('project', {}).get('rubric', []),
        'extension': f'Where does {title.lower()} stop being useful? Find a case just outside it.',
    }
    citations = [_node_citation(node)] if node else []
    if lesson:
        citations.append(_lesson_citation(lesson))
    return ToolResult('prepare_case_study', True, study, citations=citations,
                      notes=['Composed from project-authored material only; no restricted source '
                             'text is used or quoted.'])


def build_figure(ctx: ToolContext, concept_id: str,
                 overrides: Mapping[str, float] | None = None) -> ToolResult:
    """Build the interactive figure for a concept, optionally at given parameter values.

    This is real executable content, not a picture: the payload carries the series, the
    roots and extrema, the parameter bounds and the reasoning steps, so the client can
    draw it and the learner can move it.

    The builder is chosen by subject. The symbolic engine is only valid for a
    mathematics course - handed a physics concept it does not fail, it returns a generic
    quadratic labelled with the concept's name, which is worse than no figure. Every
    other subject gets a concept map built from real prerequisite edges and the
    learner's own recorded mastery.
    """
    node = _node_or_lesson(ctx, concept_id)
    if node is None:
        return ToolResult('build_figure', False, error=f'Unknown concept {concept_id!r}')
    concept = {'id': node['id'], 'title': node['title'], 'strand': node['strand'],
               'unit': node['unit'], 'topic': node['topic']}
    if (getattr(ctx, 'subject_kind', '') or 'mathematics') != 'mathematics':
        from .. import figures
        payload = figures.concept_map(node, graph_for(ctx), learner_states(ctx))
        payload['concept'] = concept
        return ToolResult('build_figure', True, payload, citations=[_node_citation(node)],
                          notes=['Subject-aware dispatch: this course is not routed through the '
                                 'symbolic engine, so the figure is a concept map derived from '
                                 'real prerequisite edges and recorded mastery rather than a '
                                 'simulation.'])
    try:
        spec = _template_for_node(node)
    except (MathSyntaxError, ValueError, ZeroDivisionError) as exc:
        return ToolResult('build_figure', False, error=f'{type(exc).__name__}: {exc}')
    from .. import figures
    if spec.kind == figures.GENERIC_PROBE_KIND:
        # No template is written for this concept. The engine's fallback is a quadratic
        # probe; building it would hand the learner a fabricated curve labelled with the
        # concept's own name, so the graph-derived map is served instead.
        payload = figures.concept_map(node, graph_for(ctx), learner_states(ctx))
        payload['concept'] = concept
        return ToolResult('build_figure', True, payload, citations=[_node_citation(node)],
                          notes=['No figure of one variable can show this concept honestly, so '
                                 'the figure is a concept map derived from real prerequisite '
                                 'edges and recorded mastery.'])
    try:
        payload = build_simulation(spec, overrides or None)
    except (MathSyntaxError, ValueError, ZeroDivisionError) as exc:
        return ToolResult('build_figure', False, error=f'{type(exc).__name__}: {exc}')
    payload['concept'] = concept
    # The label is set here as well as in the API layer so the two paths cannot report
    # different engines for the same figure.
    payload['engine'] = 'symbolic'
    return ToolResult('build_figure', True, payload, citations=[_node_citation(node)],
                      notes=['Generated by the symbolic engine from the concept classification; '
                             'no model inference is involved.'])


def deck_control(ctx: ToolContext, concept_id: str = '', action: str = 'next',
                 slide: int = -1) -> ToolResult:
    """Move the slide deck the learner has open.

    The tutor's hand on the *view*, not on the lesson: this writes a cursor the client
    polls, and nothing about the plan, the progress record or mastery moves. That is why
    it is ungated - the deck is on the learner's own screen, the same way ``board_apply``
    writes their own board. A teacher-only gate here would recreate exactly the bug this
    exists to fix: a tutor that says "next slide" and is refused.

    ``concept_id`` may be omitted when exactly one lesson is running, because the tutor
    usually says "next slide" without naming the concept. Two open lessons are refused
    rather than resolved: moving the wrong deck is worse than asking which one.
    """
    from sqlalchemy import select

    from .. import procedure_service
    from ..db import ProcedureRun

    db, user = ctx.db, ctx.user
    if db is None or user is None:
        return ToolResult('deck_control', False,
                          refused='No session is bound to this call.')
    concept = ' '.join(str(concept_id or '').split())
    if not concept:
        open_runs = list(db.scalars(select(ProcedureRun).where(
            ProcedureRun.user_id == user.id, ProcedureRun.status == 'active')
            .order_by(ProcedureRun.updated_at.desc()).limit(2)))
        if not open_runs:
            return ToolResult('deck_control', False,
                              refused='No lesson is running, so there is no deck to move.')
        if len(open_runs) > 1:
            return ToolResult('deck_control', False,
                              refused=(f'{len(open_runs)} lessons are open, so "next" has '
                                       'no single deck to move. Name the concept.'))
        concept = str(open_runs[0].concept_id)

    current = procedure_service.deck_cursor(db, user, concept)
    count = int(current.get('count') or 0)
    if not count:
        return ToolResult('deck_control', False,
                          refused=(f'The lesson on {concept!r} has no deck, so there is '
                                   'no slide to move to.'))
    index = int(current.get('slide') or 0)
    verb = ' '.join(str(action or 'next').split()).lower() or 'next'
    if verb == 'next':
        index += 1
    elif verb == 'prev':
        index -= 1
    elif verb == 'first':
        index = 0
    elif verb == 'last':
        index = count - 1
    elif verb == 'goto':
        if slide is None or int(slide) < 0:
            return ToolResult('deck_control', False,
                              refused='goto needs a slide number, counted from 0.')
        index = int(slide)
    else:
        return ToolResult('deck_control', False,
                          refused=(f'Unknown deck action {action!r}; use next, prev, '
                                   'first, last or goto.'))

    payload = procedure_service.set_deck_cursor(db, user, concept, index)
    moved = int(payload.get('slide') or 0) != int(current.get('slide') or 0)
    position = int(payload.get('slide') or 0) + 1
    return ToolResult('deck_control', True, {**payload, 'action': verb},
                      notes=[f'Slide {position} of {count}'
                             + ('' if moved else ' (it was already showing)')])


def _template_for_node(node: Mapping[str, Any]):
    from ..mathkit import template_for
    return template_for(dict(node))


def check_understanding(ctx: ToolContext, concept_id: str, exclude: Sequence[str] = ()) -> ToolResult:
    """Offer one internally-authored retrieval item for a concept.

    The item bank is small and hand-written on purpose: a generated multiple-choice
    question is only trustworthy when its distractors encode real error processes, so
    the bank stays authoritative and generation is used to *extend* it, never to
    replace it silently.
    """
    from .. import courses, exam_guard, receipts, security
    from ..curriculum import course_concepts, course_questions
    from fastapi import HTTPException

    db, user, settings = ctx.db, ctx.user, ctx.settings
    if db is None or user is None or not ctx.user_id or settings is None:
        return ToolResult('check_understanding', False,
                          refused='A signed-in account, database and receipt settings are '
                                  'required to issue an answerable question. No receipt was issued.')
    try:
        user = security._live_user(db, ctx.user_id, settings)
        exam_guard.block(db, user)
        course = courses.course(getattr(user, 'course_id', None))
    except HTTPException as exc:
        return ToolResult('check_understanding', False, refused=str(exc.detail))
    except courses.UnknownCourse:
        return ToolResult('check_understanding', False,
                          refused='The enrolled course is unavailable. Choose a valid course '
                                  'before requesting a question.')
    if ctx.course_id and ctx.course_id != course.id:
        return ToolResult('check_understanding', False,
                          refused='The tool course does not match the authenticated enrollment.')
    concepts = course_concepts(course.id)
    lesson_id = concept_id if concept_id in concepts else next(
        (cid for cid, lesson in concepts.items()
         if lesson.get('graph_id') == concept_id), '')
    lesson = concepts.get(lesson_id)
    if lesson is None:
        return ToolResult('check_understanding', False,
                          refused=f'Concept {concept_id!r} is not in the enrolled course.')
    pool = [q for q in course_questions(course.id).values()
            if q['concept_id'] == lesson_id]
    excluded = set(exclude)
    pool = [q for q in pool if q['id'] not in excluded] or pool
    if not pool:
        return ToolResult('check_understanding', False,
                          refused=f'No retrieval item covers {concept_id!r} in this course. '
                                  'No question or receipt was invented.')
    from ..db import Secret
    configured_secret = getattr(settings, 'secret', '')
    stored_secret = db.get(Secret, 'receipt') if not configured_secret else None
    secret = configured_secret or (stored_secret.value if stored_secret else '')
    ttl = getattr(settings, 'receipt_ttl', None)
    if not secret or ttl is None:
        return ToolResult('check_understanding', False,
                          refused='Receipt signing is unavailable in this runtime. '
                                  'Start the authenticated application before requesting a check.')
    pool.sort(key=lambda q: q['id'])
    question = receipts.issue(
        db, user, pool[0], mode='practice', ttl=ttl, secret=secret,
        reason='The tutor requested a retrieval check for this enrolled-course concept.')
    return ToolResult('check_understanding', True,
                      {'question': question, 'available': len(pool)},
                      citations=[_lesson_citation(lesson)],
                      notes=['Submit this signed question to /api/v1/attempts. Answers and '
                             'diagnoses stay server-side until the attempt is scored.'])


def compose_content(ctx: ToolContext, concept_id: str, kind: str,
                    options: Mapping[str, Any] | None = None) -> ToolResult:
    """Generate a multimodal artifact (explanation, cards, quiz, deck, figure).

    The tool result is the payload the agent loop serialises into a message the model
    reads, so verbatim textbook quote text is redacted here (``generate.redact_textbook_quotes``):
    the agent keeps the citation metadata and a pointer to the rendered quote, never the
    OpenStax text itself. The unredacted artefact still renders on lesson surfaces.
    """
    from . import generate
    try:
        artifact = generate.compose(ctx, concept_id, kind, dict(options or {}))
    except (ValueError, MathSyntaxError) as exc:
        return ToolResult('compose_content', False, error=f'{type(exc).__name__}: {exc}')
    return ToolResult('compose_content', True,
                      generate.redact_textbook_quotes(artifact.to_dict()),
                      citations=artifact.citations, notes=artifact.notes)


def find_image(ctx: ToolContext, concept_id: str, query: str = '') -> ToolResult:
    """Find one internet photograph for a concept, licence-cleared before download.

    The gate is the licence, not the search ranking: a candidate whose own licence does not
    permit this project to store a copy is dropped with its reason, whatever it looks like.
    ``query`` narrows the search to the visual the caller is about to show; the licence,
    size and relevance gates are unchanged.
    """
    from . import media
    settings = getattr(ctx, 'settings', None)
    if settings is None:
        return ToolResult('find_image', False, error='No settings are bound to this call')
    node = _node_or_lesson(ctx, concept_id)
    title = (node or {}).get('title', concept_id)
    summary = (node or {}).get('summary', '')
    found = media.find_image(settings, title, summary=summary,
                             alt_text=f'Photograph illustrating {title}', query=query)
    citations = []
    if found.get('asset'):
        asset = found['asset']
        citations.append({'kind': 'image', 'id': asset.get('source_id'),
                          'title': asset.get('title'), 'source': asset.get('source'),
                          'url': asset.get('landing_page_url'),
                          'licence': asset.get('licence_code'),
                          'licence_class': asset.get('licence_class')})
    return ToolResult('find_image', bool(found.get('asset')), found, citations=citations,
                      notes=list(found.get('notes') or []),
                      refused='' if found.get('asset') else str(found.get('outcome') or ''))


#: One day. A concept that could not be curated (no network, no browser, no
#: on-topic candidate) is retried tomorrow, not on every lesson open.
VIDEO_CURATE_RETRY_SECONDS = 24 * 3600


def _curation_attempts_path(settings) -> Path:
    return Path(settings.data_dir) / 'media' / 'video_curation_attempts.json'


def _read_curation_attempts(settings) -> dict[str, float]:
    try:
        raw = json.loads(_curation_attempts_path(settings).read_text(encoding='utf-8'))
        return {str(k): float(v) for k, v in raw.items()} if isinstance(raw, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _curation_recently_failed(settings, course_id: str, concept_id: str) -> bool:
    stamp = _read_curation_attempts(settings).get(f'{course_id}:{concept_id}')
    return bool(stamp) and time.time() - stamp < VIDEO_CURATE_RETRY_SECONDS


def _remember_curation(settings, course_id: str, concept_id: str, curated: bool) -> None:
    """Remember a miss, forget one on success. Written atomically like the allowlist."""
    table = _read_curation_attempts(settings)
    key = f'{course_id}:{concept_id}'
    if curated:
        table.pop(key, None)
    else:
        table[key] = time.time()
    path = _curation_attempts_path(settings)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        staging = path.with_suffix('.json.part')
        staging.write_text(json.dumps(table), encoding='utf-8')
        staging.replace(path)
    except OSError:
        # A read-only data dir must not turn a lesson into a 500. The worst case
        # is one extra curation attempt per request, which the caller can switch
        # off with HARNESS_VIDEO_AUTO_CURATE=0.
        pass


def _curate_video_for_lesson(ctx, settings, concept_id: str) -> dict[str, Any]:
    """Run the teacher's curation job for one lesson, with its own gates intact."""
    from . import video_search

    node = _node_or_lesson(ctx, concept_id) or {}
    lesson = _lesson_for(concept_id) or {}
    title = str(node.get('title') or lesson.get('title') or concept_id)
    keywords = [str(word) for word in
                (node.get('keywords') or lesson.get('keywords') or [])]
    concept = {'id': concept_id, 'title': title, 'keywords': keywords}
    try:
        return video_search.curate_for_concept(settings, concept, ctx.course_id, limit=6)
    except Exception as exc:  # noqa: BLE001 - a failed curation is a note, not a 500
        return {'curated': False, 'reason': f'{type(exc).__name__}: {exc}'}


def find_video(ctx: ToolContext, concept_id: str) -> ToolResult:
    """Curated video for a concept, verified for embeddability and never downloaded.

    A concept with no allowlist row used to mean no video at all. The teacher's
    curation job (:func:`video_search.curate_for_concept`) already existed to
    close that gap but was only ever run by a separate sweep, so an ordinary
    lesson stayed empty. Here it runs on demand, once per concept per day, behind
    the same four gates (title relevance, neighbouring lesson, trusted source and
    oEmbed embeddability). Writing goes through ``video.curate`` -- the same
    idempotent allowlist a human edits -- and a failure is reported in ``notes``
    rather than as a fabricated card.
    """
    from . import video
    settings = getattr(ctx, 'settings', None)
    if settings is None:
        return ToolResult('find_video', False, error='No settings are bound to this call')
    if not ctx.course_id:
        return ToolResult('find_video', False,
                          refused='Video curation is keyed by course; no course is bound.')
    cards = video.resolve(settings, ctx.course_id, concept_id)
    curation: dict[str, Any] | None = None
    if (not cards
            and getattr(settings, 'video_auto_curate', False)
            and getattr(settings, 'media_enabled', False)
            and getattr(settings, 'chromium_search_enabled', False)
            and not _curation_recently_failed(settings, ctx.course_id, concept_id)):
        curation = _curate_video_for_lesson(ctx, settings, concept_id)
        _remember_curation(settings, ctx.course_id, concept_id,
                           bool(curation.get('curated')))
        if curation.get('curated'):
            cards = video.resolve(settings, ctx.course_id, concept_id)
    citations = [{'kind': 'video', 'id': card.get('provider'), 'title': card.get('title'),
                  'source': card.get('channel'), 'url': card.get('watch_url'),
                  'licence': card.get('licence'), 'licence_class': card.get('licence_class')}
                 for card in cards]
    notes = ['Embedded through the provider\'s own player. Embeddability was '
             'verified per video and fails closed; nothing was downloaded, '
             'transcribed or re-hosted.']
    if curation is not None:
        if curation.get('curated'):
            best = curation.get('video') or {}
            notes.append('On-demand curation attached a verified video '
                         f'({best.get("video_id") or "unknown"}) via '
                         f'{curation.get("path") or "the search provider"}.')
        else:
            notes.append('On-demand curation found no qualifying video: '
                         f'{curation.get("reason") or "unknown reason"}. '
                         'No video was invented; retry is suppressed for 24h.')
    return ToolResult('find_video', True, {'videos': cards}, citations=citations,
                      notes=notes)


def find_simulation(ctx: ToolContext, concept_id: str) -> ToolResult:
    """A real external simulation for a concept, or a named gap.

    The result is marked unobservable on purpose. Free simulations expose no telemetry, so
    the harness cannot see what happened inside one, and a resource it cannot observe must
    never be counted as evidence.
    """
    from .. import simulation_map
    settings = getattr(ctx, 'settings', None)
    if settings is None:
        return ToolResult('find_simulation', False, error='No settings are bound to this call')
    if not ctx.course_id:
        return ToolResult('find_simulation', False,
                          refused='The simulation map is keyed by course; no course is bound.')
    node = _node_or_lesson(ctx, concept_id)
    title = (node or {}).get('title', concept_id)
    payload = simulation_map.for_concept(settings, ctx.course_id, title)
    ready = [s for s in payload.get('simulations', []) if s.get('status') == 'ready']
    citations = [{'kind': 'simulation', 'id': s.get('slug') or s.get('gizmo_title_search'),
                  'title': s.get('title'), 'source': s.get('provider'),
                  'url': s.get('public_url') or s.get('launch_url'),
                  'licence': s.get('licence'), 'licence_class': 'embed_only'} for s in ready]
    notes = list(payload.get('notes') or [])
    if payload.get('gap'):
        notes.append(payload['gap'])
    return ToolResult('find_simulation', True, payload, citations=citations, notes=notes)


def build_presentation(ctx: ToolContext, concept_id: str,
                       options: Mapping[str, Any] | None = None) -> ToolResult:
    """Assemble a narrated deck for a concept."""
    from . import presentation
    settings = getattr(ctx, 'settings', None)
    try:
        payload = presentation.compose(ctx, concept_id, dict(options or {}))
    except ValueError as exc:
        return ToolResult('build_presentation', False, error=str(exc))
    if settings is not None:
        payload.setdefault('notes', []).append(
            'Timing is estimated from word count; the client synthesiser is authoritative.')
    return ToolResult('build_presentation', True, payload, notes=list(payload.get('notes') or []))


def run_in_workspace(ctx: ToolContext, language: str, code: str,
                     timeout: float = 5.0) -> ToolResult:
    """Execute learner or harness code inside the restricted workspace."""
    from . import sandbox
    if ctx.workspace is None:
        return ToolResult('run_in_workspace', False, error='No workspace is bound to this call')
    try:
        outcome = ctx.workspace.run(language, code, timeout=timeout)
    except sandbox.SandboxRefused as refusal:
        return ToolResult('run_in_workspace', False, refused=str(refusal),
                          data={'language': language})
    return ToolResult('run_in_workspace', outcome['ok'], outcome,
                      notes=outcome.get('limits', []))


def list_workspace(ctx: ToolContext) -> ToolResult:
    """List the files the harness has written for this learner."""
    if ctx.workspace is None:
        return ToolResult('list_workspace', False, error='No workspace is bound to this call')
    return ToolResult('list_workspace', True, {'files': ctx.workspace.list_files(),
                                               'root': ctx.workspace.label})


def write_workspace_file(ctx: ToolContext, path: str, content: str) -> ToolResult:
    """Persist a generated artifact into the learner's workspace."""
    from . import sandbox
    if ctx.workspace is None:
        return ToolResult('write_workspace_file', False, error='No workspace is bound to this call')
    try:
        record = ctx.workspace.write(path, content)
    except sandbox.SandboxRefused as refusal:
        return ToolResult('write_workspace_file', False, refused=str(refusal))
    return ToolResult('write_workspace_file', True, record)


def read_workspace_file(ctx: ToolContext, path: str) -> ToolResult:
    from . import sandbox
    if ctx.workspace is None:
        return ToolResult('read_workspace_file', False, error='No workspace is bound to this call')
    try:
        return ToolResult('read_workspace_file', True, ctx.workspace.read(path))
    except sandbox.SandboxRefused as refusal:
        return ToolResult('read_workspace_file', False, refused=str(refusal))


# ------------------------------------------------------------------- registry

REGISTRY: dict[str, tuple[ToolSpec, Callable[..., ToolResult]]] = {}


def _importable(module: str) -> bool:
    """Whether ``module`` can be imported here. A cached answer per process is fine:
    packages do not appear while a process is running."""
    import importlib.util

    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        # A module whose *parent* package is missing raises rather than returning None.
        return False


def available(spec: ToolSpec) -> bool:
    """Whether every module this tool declared is importable in this process.

    A tool with no ``requires`` is always available. The check is a presence test, not a
    health check: an installed-but-unconfigured provider is a different question, and the
    tools that have one answer it themselves with a structured refusal.
    """
    return all(_importable(module) for module in spec.requires)


def available_specs() -> list[ToolSpec]:
    """The specs the model may be told about, in catalogue order.

    This - not :func:`catalogue` - is what the system prompt and the wire tool list are
    built from. The catalogue stays complete so an operator can see everything that is
    registered alongside whether each one is live; the model is only offered the ones it
    can actually call.
    """
    return [spec for spec, _ in sorted(REGISTRY.values(), key=lambda pair: pair[0].name)
            if available(spec)]


def unavailable_specs() -> list[ToolSpec]:
    """Registered but not usable here, with the module that is missing named by ``requires``."""
    return [spec for spec, _ in sorted(REGISTRY.values(), key=lambda pair: pair[0].name)
            if not available(spec)]


def available_catalogue() -> list[dict[str, Any]]:
    """The available tools as dicts, which is what the prompt and the transparency panel
    both consume: the panel's ``tools`` must not claim the prompt listed something it did
    not, so both read this one list."""
    return [spec.to_dict() for spec in available_specs()]


def _register(spec: ToolSpec, fn: Callable[..., ToolResult]) -> None:
    REGISTRY[spec.name] = (spec, fn)


def _require_teacher(ctx, tool: str) -> ToolResult | None:
    """Teacher gate shared by the curation-facing tools.

    The role is read from the authenticated principal (server-side only), never from
    model-supplied arguments; an unknown or learner role gets a named refusal rather
    than an empty success, mirroring creation_gate's fail-close posture.

    Shared publishing and classroom operations remain privileged. Personal creation
    is a separate scope, not a reason to grant a learner a teacher or admin role.
    """
    role = _tools_creation._principal_role(ctx)
    if role not in {'teacher', 'staff', 'admin'}:
        return ToolResult(tool, False,
                          refused=f'{tool} is a teacher-facing tool (fail-closed); the '
                                  f'authenticated role is {role or "unknown"}. The '
                                  f'operation affects shared course or classroom content '
                                  f'and requires an authorized teacher account. Personal '
                                  f'learning tools do not require role promotion: '
                                  f'compose_content, image_search, find_image, '
                                  f'board_place_media, board_apply, generate_slides and '
                                  f'text_to_speech keep their own ownership, exam and '
                                  f'provider gates.')
    return None


def _find_game(ctx, query: str) -> ToolResult:
    """Curated math-game search over the audited pack. Teacher-facing."""
    gate = _require_teacher(ctx, 'find_game')
    if gate is not None:
        return gate
    from . import game_search
    query = ' '.join((query or '').split())[:200]
    if not query:
        return ToolResult('find_game', False, refused='No query supplied.')
    settings = getattr(ctx, 'settings', None)
    commercial = bool(getattr(settings, 'commercial_use', False)) if settings else False
    payload = game_search.for_query(query, commercial=commercial)
    citations = [{'kind': 'game', 'title': g.get('title'), 'url': g.get('url'),
                  'source': g.get('source'), 'licence': g.get('licence'),
                  'licence_class': 'link_only'} for g in payload['games']]
    notes = ['Every card is a deep link into the rights-holder\'s own site. Nothing is '
             'copied, embedded or ingested; gaps are named rather than invented.']
    if payload.get('gap'):
        notes.append(payload['gap'])
    return ToolResult('find_game', bool(payload['games']), payload,
                      citations=citations, notes=notes)


def _search_videos(ctx, query: str, limit: int = 6) -> ToolResult:
    """Teacher video search with per-candidate embeddability verification."""
    gate = _require_teacher(ctx, 'search_videos')
    if gate is not None:
        return gate
    from . import video_search
    payload = video_search.search_videos(ctx, query, limit=limit)
    if not payload.get('ok'):
        return ToolResult('search_videos', False, payload,
                          refused=payload.get('refused', ''),
                          error=payload.get('error', ''),
                          notes=payload.get('notes', []))
    citations = [{'kind': 'video', 'id': v.get('video_id'), 'title': v.get('title'),
                  'source': v.get('channel'), 'url': v.get('watch_url'),
                  'licence': v.get('licence', 'link only'),
                  'licence_class': 'embed_only' if v.get('verified') else 'link_only'}
                 for v in payload.get('videos', [])]
    return ToolResult('search_videos', True, payload, citations=citations,
                      notes=payload.get('notes', []))


def _browser_snapshot(ctx, url: str, full_page: bool = False) -> ToolResult:
    """Headless-browser still capture for teacher review. Gated + teacher-only."""
    gate = _require_teacher(ctx, 'browser_snapshot')
    if gate is not None:
        return gate
    settings = getattr(ctx, 'settings', None)
    if settings is None:
        return ToolResult('browser_snapshot', False, error='No settings are bound to this call')
    if not getattr(settings, 'browser_enabled', False):
        return ToolResult('browser_snapshot', False,
                          refused='The browser tool is disabled for this instance '
                                  '(HARNESS_BROWSER_ENABLED). No browser was launched.')
    from . import browser as browser_module
    payload = browser_module.snapshot(url, settings=settings, full_page=full_page)
    if not payload.get('ok'):
        return ToolResult('browser_snapshot', False, payload,
                          refused=payload.get('refused', ''),
                          error=payload.get('error', ''))
    citations = [{'kind': 'web_reference', 'title': payload.get('title'),
                  'url': payload.get('url'),
                  'source': payload.get('url', ''), 'licence': payload.get('licence'),
                  'licence_class': payload.get('licence_class')}]
    return ToolResult('browser_snapshot', True, payload, citations=citations,
                      notes=['Screenshot is a local TTL copy for teacher review only; '
                             'it is never returned as source text.'])


_register(ToolSpec('search_concepts',
                   'Find course concepts by term, to orient before choosing a move.',
                   'query: str, limit: int = 8', 'internal',
                   '{query, hits: [{id, title, strand, unit, topic, difficulty}]}'),
          search_concepts)
_register(ToolSpec('read_concept',
                   'Read one concept: classification, prerequisite and dependant neighbourhood, '
                   'and its authored lesson.',
                   'concept_id: str, include_lesson: bool = true', 'internal',
                   '{node, prerequisites, direct_prerequisites, dependants, lesson}'),
          read_concept)
_register(ToolSpec('inspect_prerequisites',
                   'Report which prerequisites are measurably weak for this learner, with the '
                   'strength of evidence behind each number.',
                   'concept_id: str, threshold: float = 0.6', 'personal',
                   '{closure: [...], weak: [...]}'),
          inspect_prerequisites)
_register(ToolSpec('recall_learner_memory',
                   'Read durable notes about this learner, with time decay already applied.',
                   'concept_id: str = "", limit: int = 10', 'personal',
                   '{notes: [...], digest: str, summary: {...}}'),
          recall_learner_memory)
_register(ToolSpec('read_learner_evidence',
                   'Read recent scored attempts and the error categories they imply.',
                   'concept_id: str, limit: int = 12', 'personal',
                   '{sample, accuracy, error_categories, recent: [...]}'),
          read_learner_evidence)
_register(ToolSpec('search_material',
                   'Search available material. Cleared sources return content; everything else '
                   'returns a link and a refusal reason.',
                   'query: str, limit: int = 8, include_external: bool = true', 'ingestible',
                   '{internal: [...], external: [{name, url, licence, mode, text_returned}]}'),
          search_material)
_register(ToolSpec('fetch_material_text',
                   'Return outside text only when the licence clears it; otherwise refuse and '
                   'record a link-only reference.',
                   'source_name: str', 'link_only', '{source, provenance, text} or refusal'),
          fetch_material_text)
_register(ToolSpec('prepare_case_study',
                   'Compose a case study with tasks and a rubric, grounded in authored curriculum.',
                   'concept_id: str, angle: str = ""', 'internal',
                   '{title, setting, tasks: [...], rubric: [...]}'),
          prepare_case_study)
_register(ToolSpec('build_figure',
                   'Build the interactive figure for a concept at given parameter values.',
                   'concept_id: str, overrides: dict = {}', 'internal',
                   '{expression, parameters, series, parts, marks, features, steps}'),
          build_figure)
_register(ToolSpec('deck_control',
                   'Move the slide deck the learner has open: next, prev, first, last or '
                   'goto. Say which slide you moved to in the same turn, because the '
                   'learner is watching the sheet, not the transcript. Ungated: it moves '
                   'the learner\'s own view and never changes the lesson plan.',
                   'concept_id: str = "" (omit when one lesson is open), '
                   'action: str = "next" | "prev" | "first" | "last" | "goto", '
                   'slide: int = -1 (0-based, for goto)', 'internal',
                   '{concept_id, action, slide, count, at} or refusal'),
          deck_control)
_register(ToolSpec('check_understanding',
                   'Offer one authored retrieval item for a concept.',
                   'concept_id: str, exclude: [str] = []', 'internal', '{question, available}'),
          check_understanding)
_register(ToolSpec('compose_content',
                   'Generate a multimodal artifact: explanation, flashcards, quiz, slide deck, '
                   'figure, photograph, video lesson or narrated presentation.',
                   'concept_id: str, kind: str, options: dict = {}', 'internal',
                   'artifact {kind, title, blocks, citations}'),
          compose_content)
_register(ToolSpec('find_image',
                   'Find one internet photograph for a concept. Nothing is downloaded until '
                   'the image\'s own licence has been classified and cleared. Pass query to '
                   'search for a specific visual (for example "fraction bar") instead of the '
                   'concept title.',
                   'concept_id: str, query: str = ""', 'ingestible',
                   '{asset, outcome, seen, accepted, rejections: [{source, title, why}]}'),
          find_image)
_register(ToolSpec('find_video',
                   'Return curated video for a concept, embedded through the provider\'s own '
                   'player after a per-video embeddability check.',
                   'concept_id: str', 'embed_only',
                   '{videos: [{status, embed_url, licence, verified_at, verify_method}]}'),
          find_video)
_register(ToolSpec('find_simulation',
                   'Return a real external simulation for a concept, or the named gap when '
                   'none covers it. The result is unobservable by construction.',
                   'concept_id: str', 'embed_only',
                   '{simulations: [{provider, launch_url, open_mode}], gap, observable: false}'),
          find_simulation)
_register(ToolSpec('build_presentation',
                   'Assemble a narrated slide deck: single narrator, one visual per slide, '
                   'audio-led timing, a WebVTT track and a self-contained HTML render.',
                   'concept_id: str, options: dict = {}', 'internal',
                   '{slides: [...], script: [...], vtt: str, html: str, total_seconds: float}'),
          build_presentation)
_register(ToolSpec('run_in_workspace',
                   'Execute code in the restricted workspace and return stdout, stderr and status.',
                   'language: str, code: str, timeout: float = 5.0', 'sandboxed',
                   '{ok, stdout, stderr, exit_code, limits}'),
          run_in_workspace)
_register(ToolSpec('list_workspace',
                   'List files in this learner workspace.',
                   '', 'sandboxed', '{files: [...], root: str}'),
          list_workspace)
_register(ToolSpec('write_workspace_file',
                   'Write a generated artifact into this learner workspace.',
                   'path: str, content: str', 'sandboxed', '{path, bytes, written_at}'),
          write_workspace_file)
_register(ToolSpec('read_workspace_file',
                   'Read a file from this learner workspace.',
                   'path: str', 'sandboxed', '{path, content}'),
          read_workspace_file)

# ------------------------------------------------ creation & multimodal pack
# Registered from app.harness.tools_creation. Every tool that can change a teaching
# artifact passes through app.harness.creation_gate first: teachers create freely,
# students file change requests in four categories that are passed to the model as
# scoped requirements, and `create`/`restructure` are teacher-only.

from . import tools_creation as _tools_creation  # noqa: E402

_register(ToolSpec('write_simulation',
                   'Create a new self-contained HTML teaching simulation from a spec. '
                   'Gated: creation is a teacher capability (the role is taken from the '
                   'authenticated account, never from a tool argument); the output is '
                   'validated (self-contained, parseable, data-series tagged) before it '
                   'is stored and versioned.',
                   'title: str, description: str = "", requirements: [str] = []',
                   'sandboxed',
                   '{artifact_id, version, raw_url, bytes, diff_summary, gate} '
                   'or refusal'),
          _tools_creation.write_simulation)
_register(ToolSpec('edit_simulation',
                   'Apply a scoped change request to an existing simulation: bug, '
                   'wrong_info, ugly or ux (student-filed, passed to the model as a '
                   'requirement), or create/restructure (teacher only, per the '
                   'authenticated account). The previous version is kept and remains '
                   'revertible.',
                   'artifact_id: str, requirement_category: str, requirement_note: str, '
                   'selection: str = ""', 'sandboxed',
                   '{artifact_id, version, previous_version, raw_url, diff_summary, gate} '
                   'or refusal'),
          _tools_creation.edit_simulation)
_register(ToolSpec('check_simulation',
                   'Run a stored simulation in a headless browser and report whether it '
                   'behaves: script errors, a throwing console, a blank frame, or a '
                   'non-finite value in the visible text after being driven. Structural '
                   'validation at creation cannot catch any of these. Reports unverified '
                   '(not broken) when the instance has no browser.',
                   'artifact_id: str', 'sandboxed',
                   '{artifact_id, version, checked, problems, reason} or refusal'),
          _tools_creation.check_simulation)
_register(ToolSpec('generate_slides',
                   'Compose a real slide deck from a spec or from authored curriculum: '
                   'a printable self-contained HTML deck plus a .pptx twin when '
                   'python-pptx is available. Deterministic; no model inference.',
                   'title: str, sections: [{heading, bullets, notes}] = [], '
                   'concept_id: str = "", include_pptx: bool = true', 'internal',
                   '{artifact_id, slides, raw_url, pptx_file} or refusal'),
          _tools_creation.generate_slides)
_register(ToolSpec('text_to_speech',
                   'Speak a passage as cached mp3 audio through a local VoiceStudio '
                   'backend. Returns an honest refusal naming the fix when voice output '
                   'is switched off, the service is not running, the model is missing, '
                   'or its licence has not been accepted; never returns fake audio. '
                   '`tone` is a delivery instruction (e.g. "warm, patient teacher '
                   'explaining slowly"); engines differ in what they honour and the '
                   'result reports the tone actually applied.',
                   'text: str, voice: str = "", rate: str = "", tone: str = ""',
                   'internal', '{path, bytes, voice, model, speed, tone, provider} or refusal'),
          _tools_creation.text_to_speech)
_register(ToolSpec('image_search',
                   'Search open image APIs through the existing licence-gated media '
                   'machinery. Candidates are returned for embedding/reference only; '
                   'nothing is downloaded in this posture.',
                   'query: str, limit: int = 8', 'embed_only',
                   '{query, images: [{source, title, licence, landing_page_url}], '
                   'rejections: [...]} or refusal'),
          _tools_creation.image_search)
_register(ToolSpec('web_search',
                   'Search the open web for case-study material. Every hit passes the '
                   'licence gate: audited cleared domains may return a snippet, all '
                   'others come back link_only (URL and title, no copied text).',
                   'query: str, limit: int = 6', 'ingestible',
                   '{query, results: [{title, url, licence_class, mode, snippet?}]} '
                   'or refusal'),
          _tools_creation.web_search)
_register(ToolSpec('image_generate',
                   'Generate an illustration through the configured provider chain '
                   '(currently the keyless pollinations.ai entry) and report which '
                   'provider served it. Honest refusal when the chain cannot.',
                   'prompt: str, width: int = 1024, height: int = 1024, seed: int = null',
                   'internal', '{path, bytes, mime, provider} or refusal'),
          _tools_creation.image_generate)
_register(ToolSpec('fetch_page_text',
                   'Read the visible text of a licence-cleared page (e.g. a web_search '
                   'hit on wikipedia.org). The fetched domain is re-classified before '
                   'any text is returned; uncleared domains come back link_only with '
                   'no text, and redirects are re-gated.',
                   'url: str, max_chars: int = 4000', 'ingestible',
                   '{url, text, licence_class, truncated} or refusal'),
          _tools_creation.fetch_page_text)
_register(ToolSpec('wikipedia_summary',
                   'One Wikipedia REST summary (title, extract, canonical URL) with the '
                   'CC BY-SA attribution string attached. Honest refusal when the page '
                   'does not exist.',
                   'title: str, lang: str = "en"', 'ingestible',
                   '{title, lang, url, extract, attribution} or refusal'),
          _tools_creation.wikipedia_summary)

from . import tools_vision as _tools_vision  # noqa: E402  (needs REGISTRY-side gate)

_register(ToolSpec('look_at_image',
                   'See an image. With no question, the image is attached to the '
                   'conversation so you can look at it yourself before the next step. '
                   'With a question, one vision call answers it as text and the picture '
                   'does not stay in context. Accepts a data: URL or a path inside this '
                   'learner\'s workspace; a remote URL is refused. Needs a vision model.',
                   'source: str, question: str = ""', 'personal',
                   '{attached, image: {sha256, bytes, origin, model}, description?} '
                   'or refusal'),
          _tools_vision.look_at_image)
_register(ToolSpec('check_on_task',
                   'Read whether the learner is working on the stated task, from the '
                   'client\'s own telemetry (idle time, hidden window, attempts) and, when '
                   'a snapshot is supplied, from the work visible in it. Returns a state, '
                   'its evidence, and a teaching move - never a grade, a flag or an '
                   'accusation. Frames are not stored. Gated by HARNESS_ATTENTION_MONITOR.',
                   'task: str, snapshot: str = "", '
                   'signals: {idle_seconds, hidden_seconds, active_seconds, blur_events, '
                   'attempts, window_seconds} = {}', 'personal',
                   '{state, confidence, evidence, suggested_action, dimensions, privacy} '
                   'or refusal'),
          _tools_vision.check_on_task)
_register(ToolSpec('find_game',
                   'Search the curated, operator-edited math-game pack for interactive '
                   'activities matching a topic. Every card is a verified deep link '
                   'stamped with its policy_name; coverage gaps are named, not invented. '
                   'Teacher-facing.',
                   'query: str', 'link_only',
                   '{query, games: [{title, url, policy_name, licence, topics}], gap}'),
          _find_game)
_register(ToolSpec('search_videos',
                   'Search YouTube for class material (Data API when a key is '
                   'configured, keyless DDG fallback otherwise). Every candidate passes '
                   'the per-video embeddability verify; failures become plain links. '
                   'Nothing reaches a learner until a teacher attaches it. Teacher-facing.',
                   'query: str, limit: int = 6', 'embed_only',
                   '{query, path, videos: [{video_id, title, verified, embed_url?, watch_url}]} '
                   'or refusal'),
          _search_videos)
_register(ToolSpec('browser_snapshot',
                   'Open a page in a fresh headless chromium and capture a still image '
                   'plus title, for teacher review of a candidate class resource. No '
                   'cookies persist; text is extracted only for licence-cleared '
                   'domains; screenshots expire after 24h. Teacher-facing and gated by '
                   'HARNESS_BROWSER_ENABLED.',
                   'url: str, full_page: bool = false', 'sandboxed',
                   '{url, title, screenshot, text_excerpt?} or refusal',
                   # Declared optional: the desktop bundle ships without playwright on
                   # purpose (see scripts/package.py BUNDLE_EXCLUDES). Where it is absent
                   # the catalogue reports this tool as unavailable and the prompt does
                   # not offer it, instead of spending a turn on a guaranteed refusal.
                   requires=('playwright',)),
          _browser_snapshot)

from . import tools_whiteboard as _tools_whiteboard  # noqa: E402  (needs REGISTRY-side gate)

_register(ToolSpec('whiteboard_read',
                   'Read the shared whiteboard: every node with its kind, geometry and '
                   'text, a compact digest of the board, plus how many raised hands are '
                   'open. Read the board BEFORE editing so your drawing composes with '
                   'what is already there.',
                   'board_id: str', 'internal',
                   '{board_id, title, version, space, nodes, digest, open_interrupts} '
                   'or refusal'),
          _tools_whiteboard.whiteboard_read)
_register(ToolSpec('whiteboard_apply',
                   'Draw on the shared whiteboard with vector ops: path (points list), '
                   'shape (rect/ellipse/arrow), connector (from/to), text (<=200 chars), '
                   'image (from whiteboard_place_image). The ops land on the same board '
                   'the learner\'s canvas shows. Atomic; ids and z order are server-side. '
                   'Teacher-facing.',
                   'board_id: str, ops: list, summary: str = ""', 'internal',
                   '{board_id, version, applied} or refusal'),
          _tools_whiteboard.whiteboard_apply)
_register(ToolSpec('whiteboard_write',
                   'Write a text block on the shared whiteboard (the sugar over '
                   'whiteboard_apply for plain text). The board stores searchable text, '
                   'never rendered handwriting. Teacher-facing.',
                   'board_id: str, text: str, x: float, y: float, size: float = 16',
                   'internal', '{board_id, version} or refusal'),
          _tools_whiteboard.whiteboard_write)
_register(ToolSpec('whiteboard_place_image',
                   'Acquire a licence-cleared image through the media pipeline and pin it '
                   'on the whiteboard with its licence attribution. The node carries the '
                   'content hash the canvas resolves by. An uncleared result is refused, '
                   'never faked with a URL. Teacher-facing.',
                   'board_id: str, query: str, x: float = 0, y: float = 0, w: float = 320',
                   'internal',
                   '{board_id, version, placed: {title, licence, credit, source_url}} '
                   'or refusal'),
          _tools_whiteboard.whiteboard_place_image)

from . import tools_board as _tools_board  # noqa: E402  (needs REGISTRY-side gate)

_register(ToolSpec('board_read',
                   'Read one interactive board this account owns: every node with its id, '
                   'kind, position and payload. Read BEFORE editing so your nodes compose '
                   'with what is already there; node ids and z order are server facts.',
                   'board_id: str', 'internal',
                   '{board_id, title, version, space, nodes} or refusal'),
          _tools_board.board_read)
_register(ToolSpec('board_apply',
                   'Mutate an interactive board you own with a validated batch: add a node '
                   '(kind: path/shape/connector/text/image/video/simulation/answer), move '
                   '(x/y and optional before_id/after_id for z order), update text, or '
                   'delete by id. Atomic; ids and z indices are assigned server-side.',
                   'board_id: str, mutations: list, summary: str = ""', 'internal',
                   '{board_id, version, applied} or refusal'),
          _tools_board.board_apply)
_register(ToolSpec('board_place_media',
                   'Acquire a licence-cleared asset and pin it on the board with its '
                   'attribution: kind "image" searches by query; "video" resolves the '
                   'curated concept video; "simulation" resolves PhET/Gizmos by concept. '
                   'An uncleared result is refused, never faked with a URL.',
                   'board_id: str, kind: str, query: str = "", concept_id: str = "", '
                   'x: float = 0, y: float = 0, w: float = 320',
                   'internal',
                   '{board_id, version, placed: {kind, status, title, licence_class}} '
                   'or refusal'),
          _tools_board.board_place_media)


from .authoring import tools as _authoring_tools  # noqa: E402  (needs REGISTRY-side gate)

_register(ToolSpec('author_course',
                   'Build and publish a whole course from a blueprint document: units, '
                   'concepts, worked examples, misconceptions and transfer tasks. The '
                   'course is synthesized into the same graph, lesson and item shapes the '
                   'shipped courses use, audited (every item answerable from its lesson, '
                   'prerequisites acyclic and backwards-pointing, prose floors met), and '
                   'published into the course picker and the practice routes. With '
                   'illustrate=True (the default) each concept also gets a real, '
                   'licence-cleared photograph, so the textbook is multimodal on the first '
                   'read. A refusal carries the audit findings so the blueprint can be '
                   'fixed and retried. Teacher-facing.',
                   'blueprint_json: object|str, replace: bool = false, '
                   'illustrate: bool = true', 'internal',
                   '{course: {id, title, concepts, questions, digest}, audit, '
                   'illustration} or refusal'),
          _authoring_tools.author_course)
_register(ToolSpec('draft_course',
                   'Author a course from a topic alone, using the configured model '
                   'provider: it designs the outline, then writes the lesson prose unit by '
                   'unit, then the audit decides whether it may ship, then each concept '
                   'gets a real licence-cleared photograph. Needs a model; without one it '
                   'refuses and says to supply a blueprint instead. Teacher-facing.',
                   'topic: str, units: int = 3, level: str = "intro", '
                   'profile: str = "default", illustrate: bool = true', 'internal',
                   '{course: {id, title, ...}, audit, attempts, illustration} or refusal'),
          _authoring_tools.draft_course)
_register(ToolSpec('list_authored_courses',
                   'Every course the harness has authored in this deployment, with its '
                   'audit status, digest and unit count. Includes records that could not '
                   'be published, and why.',
                   '', 'internal', '{courses: [...], withheld: [...]}'),
          _authoring_tools.list_authored_courses)
_register(ToolSpec('read_course_blueprint',
                   'The design document behind an authored course, plus the audit that '
                   'let it in. Read this before extending or rebuilding a course.',
                   'course_id: str', 'internal',
                   '{course, blueprint, audit} or refusal'),
          _authoring_tools.read_course_blueprint)
_register(ToolSpec('extend_course',
                   'Append one unit to an existing authored course and rebuild it. The '
                   'whole course is re-synthesized and re-audited, so a unit that breaks '
                   'the sequence is refused rather than appended. Teacher-facing.',
                   'course_id: str, unit_json: object|str', 'internal',
                   '{course, audit, previous_digest} or refusal'),
          _authoring_tools.extend_course)
_register(ToolSpec('describe_methodology',
                   'The authoring methodology this harness enforces - shape, load, '
                   'sequence, assessment rules and the published findings each one rests '
                   'on. Read it before writing a blueprint so the document passes first '
                   'time.',
                   'profile: str = "default"', 'internal',
                   '{name, shape, load, assessment, blocks, lineage} or refusal'),
          _authoring_tools.describe_methodology)
_register(ToolSpec('illustrate_course',
                   'Attach real, licence-cleared photographs to an authored textbook. Each '
                   'concept gets one photograph from the same search/gate/cache pipeline '
                   'the shipped courses use, placed where the lesson needs it, with its '
                   'author, licence and attribution. A concept that finds nothing is '
                   'reported with the reason its candidates were dropped and keeps its '
                   'deterministic figure - nothing is generated or faked. Needs network '
                   'media; offline it reports that and changes nothing. Teacher-facing.',
                   'course_id: str, limit: int = 1, concept_ids: list[str] | None = None',
                   'internal', '{outcome, assigned, concepts: [...], coverage} or refusal'),
          _authoring_tools.illustrate_course)
_register(ToolSpec('attach_lesson_image',
                   'Put one chosen photograph into one lesson of an authored textbook. Name '
                   'it by query (acquire and attach in one step) or by sha256 (attach an '
                   'asset you already found with image_search/find_image - the right move '
                   'when you have looked at the candidates). The lesson serves it on the '
                   'next read, with its credit line. An image with no verified licence is '
                   'refused rather than printed. Teacher-facing.',
                   'course_id: str, concept_id: str, query: str = "", sha256: str = "", '
                   'block_index: int = 1, caption: str = ""', 'internal',
                   '{attached, block, asset, outcome} or refusal'),
          _authoring_tools.attach_lesson_image)
_register(ToolSpec('course_images',
                   'What photographs an authored textbook currently carries, per concept, '
                   'with the credits and the served URLs. Use it to check what a learner '
                   'would actually see before claiming a lesson is illustrated.',
                   'course_id: str', 'internal', '{concepts, illustrated, bare, rows}'),
          _authoring_tools.course_images)


def catalogue() -> list[dict[str, Any]]:
    """Every registered tool, for the client and the readiness panel.

    Complete on purpose, and each entry carries ``available`` and ``requires``. An
    operator asking "what can this build do" gets the whole registry with the answer
    attached, rather than a list that silently shrank. The model is offered
    :func:`available_specs` instead.
    """
    return [spec.to_dict() for spec, _ in sorted(REGISTRY.values(), key=lambda pair: pair[0].name)]


def signatures() -> list[str]:
    """One line per *available* tool, for a prompt that must not promise what it lacks."""
    return [spec.signature() for spec in available_specs()]


def invoke(ctx: ToolContext, name: str, arguments: Mapping[str, Any] | None = None) -> ToolResult:
    """Call a tool by name. Unknown names are a refusal, never a silent no-op."""
    entry = REGISTRY.get(name)
    if entry is None:
        return ToolResult(name, False, refused=f'Unknown tool {name!r}',
                          error=f'Unknown tool {name!r}')
    spec, fn = entry
    arguments = dict(arguments or {})
    try:
        return fn(ctx, **arguments)
    except TypeError as exc:
        return ToolResult(name, False, refused=f'Bad arguments for {name}: {exc}',
                          error=str(exc))


def postures() -> dict[str, int]:
    """How many registered tools sit in each posture.

    Counted over the whole registry, not the available subset: this describes the shape
    of the toolbox as designed. Whether a particular tool is live in this build is on the
    entry itself, as ``available``.
    """
    counts: dict[str, int] = {posture: 0 for posture in POSTURES}
    for spec, _ in REGISTRY.values():
        counts[spec.posture] = counts.get(spec.posture, 0) + 1
    return counts
