"""A course blueprint: the document a course is designed as, before it is materialised.

The blueprint is the unit of authorship. It is plain JSON, it is versioned, it is
stored beside the course it produced, and it is the only thing a model is ever asked
to write. Everything downstream - the knowledge graph, the lessons, the items, the
registry entry - is *derived* from it by :mod:`app.harness.authoring.synthesize`, so a
reviewer who wants to know why a course teaches what it teaches reads one file.

The division of labour is the same one :mod:`app.harness.playground.pipeline` uses for
games, and for the same reason: **a model may fill a declared schema, it may not write
the machinery.** A blueprint has no field that can become code, no field that can
override a limit, and no field whose value is evaluated. The worst a bad blueprint can
do is fail the audit.

Shape::

    {
      "schema": 1,
      "course": {
        "id": "cell_biology",            # optional; derived from the title if absent
        "title": "Cell Biology",
        "subject": "Biology",
        "description": "One paragraph a learner reads before enrolling.",
        "expected_weeks": 8,
        "level": "intro",
        "profile": "default",            # optional; names a profile in methodology.py
        "overrides": {"shape": {"max_concepts": 30}}   # optional, validated
      },
      "units": [
        {"title": "What a cell is", "strand": "Structure",
         "objective": "Distinguish a cell from its contents.",
         "concepts": [
           {"title": "Cell membrane",
            "summary": "...", "definition": "...",
            "example": ["step one", "step two"],
            "misconception": "...", "correction": "...",
            "application": "...", "objective": "...",
            "prerequisites": ["Cell theory"],   # id OR title; resolved here
            "keywords": ["phospholipid"], "difficulty": 2}
         ]}
      ]
    }

Two conveniences that exist because a model writes these documents: prerequisites may
be given by **title** rather than id (a model reliably knows the title it just wrote
and unreliably invents slugs), and concept ids are derived from titles when absent. Both
are resolved here, once, so the synthesizer never has to guess.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from ...knowledge_graph import slug
from . import methodology

#: Blueprint schema version this module reads. A document declaring a different one is
#: refused rather than coerced: a field whose meaning changed must not be read under
#: the old rules.
SCHEMA = 1

#: Longest concept id we will mint. Question ids are ``{concept_id}-{variant}`` and the
#: receipt schema caps a question id at 64 characters, so a concept id has to leave room
#: for the suffix. 48 leaves 16 - more than enough for ``-10``.
MAX_CONCEPT_ID = 48

#: Longest course id. Course ids travel in URLs and in ``user_preferences`` rows.
MAX_COURSE_ID = 40

_SLUG = re.compile(r'[^a-z0-9]+')

#: A string that is already a clean slug, so minting it again would only lose information.
#: Used to police ``id_final``: the flag says "do not shorten me", and it would be a hole
#: in the validator if it also said "do not sanitise me".
_CLEAN_SLUG = re.compile(r'[a-z0-9_]+')


class BlueprintError(ValueError):
    """A blueprint that cannot be read at all (wrong shape, wrong version)."""


@dataclass(frozen=True)
class Problem:
    """One reason a blueprint is not acceptable, with the path that carries it.

    ``path`` is a dotted location (``units[2].concepts[1].summary``) rather than prose,
    because the primary consumer of a problem is not a person - it is the model being
    asked to fix it. A retry prompt built from these reads as a list of edits.
    """

    code: str
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {'code': self.code, 'path': self.path, 'message': self.message}

    def __str__(self) -> str:  # used when a problem is fed back to a model
        return f'{self.path}: {self.message}'


@dataclass
class ConceptPlan:
    """One concept: what it is, why it matters, and the prose that teaches it."""

    id: str
    title: str
    summary: str = ''
    definition: str = ''
    example: tuple[str, ...] = ()
    misconception: str = ''
    correction: str = ''
    application: str = ''
    objective: str = ''
    prerequisites: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    difficulty: int = 3
    tier: str = 'core'
    unit: str = ''
    strand: str = ''
    #: Optional hand-written items. They are used before generated ones and are audited
    #: exactly like generated ones, so a hand-written item is not a way to skip a check.
    items: tuple[dict[str, Any], ...] = ()

    def prose(self) -> dict[str, str]:
        return {'summary': self.summary, 'definition': self.definition,
                'example': '\n'.join(self.example), 'misconception': self.misconception,
                'application': self.application}

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            'id': self.id, 'title': self.title, 'summary': self.summary,
            'definition': self.definition, 'example': list(self.example),
            'misconception': self.misconception, 'correction': self.correction,
            'application': self.application, 'objective': self.objective,
            'prerequisites': list(self.prerequisites), 'keywords': list(self.keywords),
            'difficulty': self.difficulty, 'tier': self.tier,
        }
        if self.items:
            payload['items'] = [dict(item) for item in self.items]
        return payload


@dataclass
class UnitPlan:
    title: str
    strand: str
    objective: str
    concepts: list[ConceptPlan] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {'title': self.title, 'strand': self.strand, 'objective': self.objective,
                'concepts': [c.to_dict() for c in self.concepts]}


@dataclass
class CoursePlan:
    id: str
    title: str
    subject: str
    description: str
    units: list[UnitPlan]
    expected_weeks: int = 12
    level: str = 'intro'
    profile_name: str = 'default'
    overrides: dict[str, Any] = field(default_factory=dict)
    #: Who wrote the prose. ``operator`` for a blueprint supplied by a person or a tool
    #: call, ``model`` for one drafted in-process, ``template`` for one framed from an
    #: outline. Recorded on the course so a reviewer can tell them apart.
    author: str = 'operator'

    # ------------------------------------------------------------------ lookups

    @property
    def profile(self) -> methodology.AuthoringProfile:
        return methodology.profile(self.profile_name, self.overrides)

    def concepts(self) -> list[ConceptPlan]:
        return [concept for unit in self.units for concept in unit.concepts]

    def by_id(self) -> dict[str, ConceptPlan]:
        return {concept.id: concept for concept in self.concepts()}

    def unit_of(self, concept_id: str) -> str:
        for unit in self.units:
            if any(concept.id == concept_id for concept in unit.concepts):
                return unit.title
        return ''

    def to_dict(self) -> dict[str, Any]:
        return {'schema': SCHEMA,
                'course': {'id': self.id, 'title': self.title, 'subject': self.subject,
                           'description': self.description,
                           'expected_weeks': self.expected_weeks, 'level': self.level,
                           'profile': self.profile_name, 'overrides': self.overrides,
                           'author': self.author},
                'units': [unit.to_dict() for unit in self.units]}

    def digest(self) -> str:
        """A stable hash of the design, so a rebuild can tell "same course" from "edited"."""
        import json
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True,
                                         ensure_ascii=False).encode('utf-8')).hexdigest()[:16]


# --------------------------------------------------------------------- id helpers

def course_id(text: str) -> str:
    """A URL-safe course id from a title. Never empty, never over-long."""
    candidate = _SLUG.sub('_', (text or '').strip().lower()).strip('_')
    candidate = candidate[:MAX_COURSE_ID].strip('_')
    if not candidate:
        candidate = 'course_' + hashlib.sha256((text or '').encode()).hexdigest()[:8]
    return candidate


def concept_id(text: str) -> str:
    candidate = slug(text or '')
    candidate = candidate[:MAX_CONCEPT_ID].strip('_')
    if not candidate:
        candidate = 'concept_' + hashlib.sha256((text or '').encode()).hexdigest()[:8]
    return candidate


def _concept_id_for(raw: Any, title: str) -> str:
    """The concept id a blueprint document meant.

    A declared id that is already a clean slug is kept as written. That is not a relaxation
    of the length cap, it is what makes a blueprint survive a round trip: ``concept_id``
    both slugifies *and truncates to 48 characters*, so re-parsing a document that carried
    ``ap_microeconomics_least_cost_combination_of_inputs`` (52 characters) would hand back
    a truncated id and attach the lesson to a node that does not exist. The authored plan
    is parsed at least twice - once when framed, once after the expansion pass merges the
    prose in - so an id that is shortened on the second read is a concept silently lost.

    Anything that is not already a clean slug is slugified as before, so the rule cannot
    be used to smuggle in an id with a slash or a space. The doubled ceiling is the limit
    the shipped packs already exceed 48 with; :func:`question_id` mints ids for long
    concepts with a digest suffix and is the thing that keeps them under the receipt
    schema's 64-character cap.
    """
    declared = _text(raw.get('id')) if isinstance(raw, Mapping) else ''
    if declared and _CLEAN_SLUG.fullmatch(declared) and len(declared) <= MAX_CONCEPT_ID * 2:
        return declared
    return concept_id(declared or title)


def _words(text: str) -> int:
    return len([part for part in re.split(r'\s+', (text or '').strip()) if part])


# ------------------------------------------------------------------------ parsing

def _text(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, str):
        return value.strip()
    return ''


def _steps(value: Any) -> tuple[str, ...]:
    """A worked example as steps. A paragraph is accepted and split on newlines.

    A model asked for steps sometimes answers with one paragraph containing numbered
    lines, and refusing that would fail a perfectly good blueprint over formatting. The
    split is on newlines only - splitting on ``1.`` inside a sentence would mangle it.
    """
    if isinstance(value, str):
        parts = [line.strip() for line in value.splitlines()]
        return tuple(part for part in parts if part)
    if isinstance(value, (list, tuple)):
        return tuple(_text(part) for part in value if _text(part))
    return ()


def _string_list(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, (list, tuple)):
        out = []
        for part in value:
            text = _text(part)
            if text and text not in out:
                out.append(text)
        return tuple(out)
    return ()


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _difficulty(value: Any) -> int:
    """An explicit difficulty in 1..5, or ``0`` for "let the synthesizer ramp it".

    Zero rather than a default of 3, because 3 is also a legitimate authored value and
    a synthesizer cannot tell "the author said core difficulty" from "the author said
    nothing" once both have been coerced to the same number. The ramp is then the
    profile's business, not the parser's.
    """
    if value is None or value == '':
        return 0
    try:
        return max(1, min(5, int(value)))
    except (TypeError, ValueError):
        return 0


def parse(document: Mapping[str, Any], *, author: str = 'operator',
          ) -> tuple[CoursePlan | None, list[Problem]]:
    """Read a blueprint document. Never raises on content; always returns problems.

    A ``BlueprintError`` is raised only when the document is not an object at all, or
    declares a schema this module does not read - those are caller bugs, not authoring
    mistakes, and a caller that passed the wrong thing needs a different signal from a
    caller whose course is missing a summary.

    The returned plan is ``None`` whenever any problem is fatal, because a partially
    read blueprint is not a course and synthesizing one would mean guessing the rest.
    """
    problems: list[Problem] = []
    if not isinstance(document, Mapping):
        raise BlueprintError('A blueprint must be a JSON object')
    schema = _int(document.get('schema', SCHEMA), SCHEMA)
    if schema != SCHEMA:
        raise BlueprintError(f'Blueprint schema {schema} is not readable by this build '
                             f'(reads {SCHEMA})')

    meta = document.get('course')
    if not isinstance(meta, Mapping):
        problems.append(Problem('course_missing', 'course',
                                'a blueprint needs a "course" object'))
        return None, problems

    title = _text(meta.get('title'))
    if not title:
        problems.append(Problem('title_missing', 'course.title', 'the course needs a title'))
    subject = _text(meta.get('subject')) or 'General'
    description = _text(meta.get('description'))
    if _words(description) < 12:
        problems.append(Problem('description_thin', 'course.description',
                                'the description must be at least 12 words: it is what a '
                                'learner reads before enrolling'))
    raw_id = _text(meta.get('id'))
    resolved_id = course_id(raw_id or title)
    if raw_id and course_id(raw_id) != raw_id:
        problems.append(Problem('course_id_not_slug', 'course.id',
                                f'{raw_id!r} is not a lowercase slug; use {resolved_id!r}'))

    profile_name = _text(meta.get('profile')) or 'default'
    overrides = meta.get('overrides') or {}
    if not isinstance(overrides, Mapping):
        problems.append(Problem('overrides_not_object', 'course.overrides',
                                'overrides must be an object'))
        overrides = {}
    try:
        profile = methodology.profile(profile_name, overrides)
    except (KeyError, ValueError) as exc:
        problems.append(Problem('profile_invalid', 'course.profile', str(exc)))
        profile = methodology.default_profile()

    units_raw = document.get('units')
    if not isinstance(units_raw, Sequence) or isinstance(units_raw, (str, bytes)):
        problems.append(Problem('units_missing', 'units',
                                'a blueprint needs a "units" list'))
        return None, problems

    units: list[UnitPlan] = []
    seen_ids: dict[str, str] = {}
    for index, unit_raw in enumerate(units_raw):
        path = f'units[{index}]'
        if not isinstance(unit_raw, Mapping):
            problems.append(Problem('unit_not_object', path, 'a unit must be an object'))
            continue
        unit_title = _text(unit_raw.get('title'))
        if not unit_title:
            problems.append(Problem('unit_title_missing', f'{path}.title',
                                    'a unit needs a title'))
            continue
        strand = _text(unit_raw.get('strand')) or unit_title
        objective = _text(unit_raw.get('objective'))
        if _words(objective) < 6:
            problems.append(Problem('unit_objective_thin', f'{path}.objective',
                                    'a unit needs a one-sentence objective (at least 6 words): '
                                    'it is what the unit is for'))
        concepts_raw = unit_raw.get('concepts')
        if not isinstance(concepts_raw, Sequence) or isinstance(concepts_raw, (str, bytes)):
            problems.append(Problem('unit_concepts_missing', f'{path}.concepts',
                                    'a unit needs a "concepts" list'))
            continue
        concepts: list[ConceptPlan] = []
        for c_index, concept_raw in enumerate(concepts_raw):
            c_path = f'{path}.concepts[{c_index}]'
            concept, c_problems = _parse_concept(concept_raw, c_path, unit_title, strand,
                                                 profile)
            problems.extend(c_problems)
            if concept is None:
                continue
            if concept.id in seen_ids:
                problems.append(Problem('concept_id_duplicate', f'{c_path}.id',
                                        f'{concept.id!r} is already used by '
                                        f'{seen_ids[concept.id]!r}'))
                continue
            seen_ids[concept.id] = c_path
            concepts.append(concept)
        units.append(UnitPlan(title=unit_title, strand=strand, objective=objective,
                              concepts=concepts))

    if not units:
        problems.append(Problem('no_units', 'units', 'no readable unit was found'))
        return None, problems

    plan = CoursePlan(id=resolved_id, title=title or resolved_id, subject=subject,
                      description=description, units=units,
                      expected_weeks=max(1, _int(meta.get('expected_weeks'), 12)),
                      level=_text(meta.get('level')) or 'intro',
                      profile_name=profile_name,
                      overrides=dict(overrides), author=author)

    problems.extend(_resolve_prerequisites(plan, profile))
    problems.extend(_check_shape(plan, profile))
    return (plan if not _fatal(problems) else None), problems


def _parse_concept(raw: Any, path: str, unit: str, strand: str,
                   profile: methodology.AuthoringProfile,
                   ) -> tuple[ConceptPlan | None, list[Problem]]:
    problems: list[Problem] = []
    if not isinstance(raw, Mapping):
        return None, [Problem('concept_not_object', path, 'a concept must be an object')]
    title = _text(raw.get('title'))
    if not title:
        return None, [Problem('concept_title_missing', f'{path}.title',
                              'a concept needs a title')]
    summary = _text(raw.get('summary'))
    if _words(summary) < profile.load.min_summary_words:
        problems.append(Problem('summary_thin', f'{path}.summary',
                                f'the summary must be at least '
                                f'{profile.load.min_summary_words} words: it is the first '
                                f'thing the learner reads'))
    example = _steps(raw.get('example'))
    if len(example) < profile.load.min_example_steps:
        problems.append(Problem('example_thin', f'{path}.example',
                                f'a worked example needs at least '
                                f'{profile.load.min_example_steps} steps; '
                                f'{len(example)} given'))
    if len(example) > profile.load.max_example_steps:
        problems.append(Problem('example_long', f'{path}.example',
                                f'at most {profile.load.max_example_steps} steps; '
                                f'{len(example)} given'))
    misconception = _text(raw.get('misconception'))
    correction = _text(raw.get('correction'))
    if not misconception:
        problems.append(Problem('misconception_missing', f'{path}.misconception',
                                'name the mistake a learner actually makes here; '
                                'without it the lesson cannot teach the discrimination'))
    if misconception and not correction:
        problems.append(Problem('correction_missing', f'{path}.correction',
                                'a misconception needs its correction: the repair is the '
                                'part that teaches'))
    application = _text(raw.get('application'))
    if _words(application) < 6:
        problems.append(Problem('application_thin', f'{path}.application',
                                'give one concrete task that requires this concept '
                                '(at least 6 words)'))

    concept = ConceptPlan(
        id=_concept_id_for(raw, title),
        title=title, summary=summary, definition=_text(raw.get('definition')),
        example=example, misconception=misconception, correction=correction,
        application=application, objective=_text(raw.get('objective')),
        prerequisites=_string_list(raw.get('prerequisites')),
        keywords=_string_list(raw.get('keywords')),
        difficulty=_difficulty(raw.get('difficulty')),
        tier=_text(raw.get('tier')) or 'core',
        unit=unit, strand=strand,
        items=tuple(item for item in (raw.get('items') or []) if isinstance(item, Mapping)),
    )
    return concept, problems


def _resolve_prerequisites(plan: CoursePlan, profile: methodology.AuthoringProfile,
                           ) -> list[Problem]:
    """Turn title references into ids, then check the edges are real and acyclic.

    Resolution happens here rather than in the synthesizer because a dangling
    prerequisite is an authoring mistake with a precise location, and the model that
    wrote it can fix it from a message that says which reference did not resolve.
    """
    problems: list[Problem] = []
    by_title = {concept.title.casefold(): concept.id for concept in plan.concepts()}
    ids = {concept.id for concept in plan.concepts()}
    order = {concept.id: index for index, concept in enumerate(plan.concepts())}

    resolved: dict[str, list[str]] = {}
    for index, concept in enumerate(plan.concepts()):
        edges: list[str] = []
        for ref in concept.prerequisites:
            target = ref if ref in ids else by_title.get(ref.casefold())
            if target is None:
                problems.append(Problem(
                    'prerequisite_unresolved',
                    f'concept {concept.id!r}',
                    f'prerequisite {ref!r} is neither a concept id nor a title in this '
                    f'blueprint'))
                continue
            if target == concept.id:
                problems.append(Problem('prerequisite_self', f'concept {concept.id!r}',
                                        'a concept cannot be its own prerequisite'))
                continue
            if target in edges:
                continue
            edges.append(target)
        if len(edges) > profile.shape.max_prerequisites:
            problems.append(Problem(
                'prerequisite_overload', f'concept {concept.id!r}',
                f'{len(edges)} prerequisites; the profile allows '
                f'{profile.shape.max_prerequisites}. A concept that needs more than that '
                f'is a topic - split it.'))
        resolved[concept.id] = edges

    # A prerequisite that points *later* in the blueprint is a forward edge: it makes the
    # course unteachable in the order it is presented, and it is the most common shape of
    # a model's sequencing error. Reported per edge so the fix is mechanical.
    for concept_id_value, edges in resolved.items():
        for edge in edges:
            if order.get(edge, 0) > order.get(concept_id_value, 0):
                problems.append(Problem(
                    'prerequisite_forward', f'concept {concept_id_value!r}',
                    f'prerequisite {edge!r} is taught later in this blueprint; a concept '
                    f'may only depend on something earlier'))
            elif not profile.shape.allow_cross_unit_prerequisites:
                if plan.unit_of(edge) != plan.unit_of(concept_id_value):
                    problems.append(Problem(
                        'prerequisite_cross_unit', f'concept {concept_id_value!r}',
                        f'prerequisite {edge!r} lives in another unit. A cross-unit '
                        f'dependency is teachable when it points backwards, so this is '
                        f'reported rather than refused - but the profile prefers hard '
                        f'dependencies inside a unit, where the unit can be studied on '
                        f'its own'))

    cycle = _cycle(resolved)
    if cycle:
        problems.append(Problem('prerequisite_cycle', 'units',
                                'these prerequisites form a cycle: ' + ' -> '.join(cycle)))
    for concept in plan.concepts():
        concept.prerequisites = tuple(resolved.get(concept.id, ()))
    return problems


def _cycle(edges: Mapping[str, Sequence[str]]) -> list[str]:
    """The first prerequisite cycle found, as a path, or an empty list.

    Kahn's algorithm rather than a recursive depth-first walk: the graph is small, but
    "small" is a property of today's profile, and a recursive walk over a graph a caller
    supplied is exactly the kind of code that raises ``RecursionError`` in production on
    input nobody tested. Whatever cannot be peeled off has a cycle in it by definition;
    the walk then recovers one path through the residue so the message names the loop
    rather than a set of nodes.
    """
    indegree = {node: 0 for node in edges}
    for node, parents in edges.items():
        for parent in parents:
            if parent in indegree:
                indegree[node] += 1
    queue = [node for node, degree in indegree.items() if degree == 0]
    remaining = dict(indegree)
    while queue:
        node = queue.pop()
        remaining.pop(node, None)
        for child, parents in edges.items():
            if node in parents and child in remaining:
                remaining[child] -= 1
                if remaining[child] == 0:
                    queue.append(child)
    if not remaining:
        return []
    # Walk the residue, following edges that stay inside it, until a node repeats.
    start = next(iter(remaining))
    path: list[str] = [start]
    seen: dict[str, int] = {start: 0}
    current = start
    while True:
        next_node = next((parent for parent in edges.get(current, ())
                          if parent in remaining), None)
        if next_node is None:
            return path + [start]
        if next_node in seen:
            return path[seen[next_node]:] + [next_node]
        seen[next_node] = len(path)
        path.append(next_node)
        current = next_node


def _check_shape(plan: CoursePlan, profile: methodology.AuthoringProfile) -> list[Problem]:
    problems: list[Problem] = []
    shape = profile.shape
    if len(plan.units) < shape.min_units:
        problems.append(Problem('too_few_units', 'units',
                                f'{len(plan.units)} units; profile {profile.name!r} needs '
                                f'at least {shape.min_units}'))
    if len(plan.units) > shape.max_units:
        problems.append(Problem('too_many_units', 'units',
                                f'{len(plan.units)} units; the ceiling is '
                                f'{shape.max_units}'))
    total = len(plan.concepts())
    if total < shape.min_concepts:
        problems.append(Problem('too_few_concepts', 'units',
                                f'{total} concepts; a course needs at least '
                                f'{shape.min_concepts} to sequence and assess'))
    if total > shape.max_concepts:
        problems.append(Problem('too_many_concepts', 'units',
                                f'{total} concepts; the ceiling is {shape.max_concepts}. '
                                f'Split the course rather than shipping one nobody finishes'))
    for index, unit in enumerate(plan.units):
        if len(unit.concepts) < shape.concepts_per_unit_min:
            problems.append(Problem('unit_too_thin', f'units[{index}]',
                                    f'{len(unit.concepts)} concepts; a unit needs at least '
                                    f'{shape.concepts_per_unit_min}'))
        if len(unit.concepts) > shape.concepts_per_unit_max:
            problems.append(Problem('unit_too_dense', f'units[{index}]',
                                    f'{len(unit.concepts)} concepts; the ceiling per unit '
                                    f'is {shape.concepts_per_unit_max}'))
    return problems


#: Problems that make a blueprint unreadable as a course. Everything else is advisory:
#: a thin summary or a two-concept unit is a course that can be read, reviewed and
#: fixed, and the gate that refuses it is the audit, which sees the built course.
#:
#: The line is drawn at *structure*, not at quality. A dangling prerequisite, a forward
#: edge or a cycle means the synthesizer cannot build a teachable graph at all, and
#: guessing a repair would silently author a different course than the one written.
#: Quality problems are left to :mod:`app.harness.authoring.audit` so that there is one
#: gate that decides what may ship, not two that disagree.
_FATAL_CODES = frozenset({
    'course_missing', 'title_missing', 'units_missing', 'unit_not_object',
    'unit_title_missing', 'unit_concepts_missing', 'concept_not_object',
    'concept_title_missing', 'concept_id_duplicate', 'prerequisite_unresolved',
    'prerequisite_self', 'prerequisite_cycle', 'prerequisite_forward',
    'prerequisite_overload', 'no_units', 'profile_invalid',
})


def frame_from_entries(course: Mapping[str, Any], entries: Sequence[Mapping[str, Any]],
                       ) -> dict[str, Any]:
    """Frame a blueprint around concepts a course already owns.

    This is the "template" arm the ``CoursePlan.author`` field anticipated: the structure
    is not invented, it is *taken*. Every id, unit, strand, tier and difficulty comes from
    the course's own graph, so an overlay cannot silently mint a concept the graph has no
    edge to, and a lesson cannot land on the wrong node.

    What is deliberately left blank is everything the writing pass must supply: the
    worked example, the misconception and its repair, the transfer task, the definition.
    ``parse`` reports those as non-blocking problems and :func:`draft.expand` feeds the
    same complaints back to the model, which is the loop that makes the second pass
    better than the first rather than merely longer.

    Prerequisites are dropped here on purpose. They belong to the graph, the graph is the
    authority on them, and a copy in the blueprint would be a second opinion that could
    disagree with the pack after an edit.
    """
    course_meta = {
        'id': str(course.get('id') or ''),
        'title': str(course.get('title') or ''),
        'subject': str(course.get('subject') or ''),
        'description': str(course.get('description') or ''),
        'expected_weeks': int(course.get('expected_weeks') or 12),
        'level': str(course.get('level') or 'intro'),
    }
    order: list[str] = []
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for entry in entries:
        unit = str(entry.get('unit') or '').strip() or 'Course content'
        if unit not in grouped:
            grouped[unit] = []
            order.append(unit)
        grouped[unit].append(entry)
    units: list[dict[str, Any]] = []
    widest = max((len(grouped[unit]) for unit in order), default=0)
    # The pack's largest unit decides the ceiling, not the other way round. The profile's
    # six-per-unit limit is a statement about how much a model writes well in one pass; it
    # is not permission to re-cut a course whose units somebody else designed. Raising it
    # to the structure we were handed keeps the course intact and leaves the limit doing
    # its real job on courses the foundry designs itself.
    if widest > 6:
        course_meta['overrides'] = {'shape': {'concepts_per_unit_max': widest}}
    for unit in order:
        concepts = []
        for entry in grouped[unit]:
            concepts.append({
                'id': str(entry.get('id') or ''),
                'title': str(entry.get('title') or ''),
                'summary': str(entry.get('summary') or ''),
                'strand': str(entry.get('strand') or ''),
                'tier': str(entry.get('tier') or 'core'),
                'difficulty': int(entry.get('difficulty') or 3),
                'objective': str(entry.get('objective') or ''),
            })
        units.append({
            'title': unit,
            'strand': str(grouped[unit][0].get('strand') or ''),
            'objective': '',
            'concepts': concepts,
        })
    return {'course': course_meta, 'units': units}


def _fatal(problems: Iterable[Problem]) -> bool:
    return any(problem.code in _FATAL_CODES for problem in problems)


def is_fatal(problem: Problem) -> bool:
    return problem.code in _FATAL_CODES


def blocking(problems: Iterable[Problem]) -> list[Problem]:
    return [problem for problem in problems if is_fatal(problem)]


__all__ = ['BlueprintError', 'ConceptPlan', 'CoursePlan', 'MAX_CONCEPT_ID', 'Problem',
           'SCHEMA', 'UnitPlan', 'blocking', 'concept_id', 'course_id', 'frame_from_entries',
           'is_fatal', 'parse']
