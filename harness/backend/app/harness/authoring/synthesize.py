"""Materialise a blueprint into a course the rest of the harness already understands.

The rule this module exists to keep: **a foundry course is not a special case.** It is
published into ``courses.COURSE_BY_ID`` and ``curriculum.CONCEPTS``/``QUESTIONS``, so
the map, the lesson view, grading, diagnosis, memory, spaced review, projects and the
tutor's own concept lookup all serve it through the paths they already had. If a
foundry course needed its own route, its own lesson renderer or its own grading branch,
the capability would not really have moved into the harness - it would have moved next
to it.

Two sources of structure, used in this order
--------------------------------------------
1. **The generated layer** (:func:`app.generated_curriculum.materialise_graph`) builds
   the structural items - definition recall, prerequisite, unit placement, teaching
   order - from the graph itself. They are reused rather than reimplemented, because
   they are already audited, deterministic and answerable from the course's own facts.
2. **The blueprint** supplies the depth the generated layer cannot: a worked example,
   the misconception learners actually hold, the task that requires the idea, and the
   item that asks the learner to repair the misconception. Depth is an *overlay* on the
   generated concept entry, so the two never disagree about what a concept is.

Why the overlay is not just "more blocks"
-----------------------------------------
The generated layer's blocks are honest but generic: they tell the learner to re-read
the summary and name what is unclear. A course that is only that is a map with a
glossary. The overlay replaces those blocks with the blueprint's prose, which means the
lesson a learner reads and the items they are asked are written by the same author
about the same sentence - and the audit can check that the answer to every item is
literally present in the lesson.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ... import courses
from ...generated_curriculum import (GENERATED_KIND, materialise_graph, question_id,
                                     structural_items)
from ...ingest import policy
from ...knowledge_graph import ConceptNode, KnowledgeGraph, Taxonomy
from .. import econ_figures
from . import blueprint, methodology

#: Marker on every concept and item this module produces. It is what
#: ``curriculum.authored_share`` counts, so a course whose lessons were composed by the
#: harness reports as derived rather than hand-written. That is not modesty: a reviewer
#: deciding whether to trust a course is entitled to know who wrote it.
ORIGIN = 'harness_authoring'

#: Question kinds this module adds on top of the generated four. The numbering matters:
#: the generated layer owns variants 0-3 for a concept, so a foundry item starts at 4 and
#: a collision would overwrite an existing item rather than add one.
_VARIANT_MISCONCEPTION = 4
_VARIANT_APPLICATION = 5

OPTION_IDS = ('a', 'b', 'c', 'd')

#: The distractor used when a course is too small to supply three sibling statements.
#: It is a real trap - a learner who does not know the concept may well believe the
#: misconception is fine - and it is always available, which keeps a small course
#: assessable instead of silently dropping the item.
_NO_REPAIR_NEEDED = 'No correction is needed: that statement is accurate.'


@dataclass
class AuthoredCourse:
    """A synthesized course, before it is published or audited."""

    plan: blueprint.CoursePlan
    course: courses.Course
    graph: KnowledgeGraph
    concepts: dict[str, dict[str, Any]]
    questions: dict[str, dict[str, Any]]
    profile: methodology.AuthoringProfile
    notes: list[str] = field(default_factory=list)

    @property
    def concept_count(self) -> int:
        return len(self.concepts)

    @property
    def question_count(self) -> int:
        return len(self.questions)

    def summary(self) -> dict[str, Any]:
        return {'id': self.course.id, 'title': self.course.title,
                'units': len(self.plan.units), 'concepts': self.concept_count,
                'questions': self.question_count, 'profile': self.profile.name,
                'author': self.plan.author, 'digest': self.plan.digest(),
                'notes': list(self.notes)}


# ------------------------------------------------------------------------- graph

def _tier(index: int, total: int) -> str:
    """Foundation, core, extension by position in the course.

    Derived from position rather than declared per concept, because the tier is a
    statement about the course's shape - "the first third is the ground everything else
    stands on" - and a per-concept tier lets an author (or a model) label every concept
    ``core`` and quietly delete the ramp.
    """
    if total <= 1:
        return 'core'
    share = index / max(1, total - 1)
    if share < 0.34:
        return 'foundation'
    if share > 0.75:
        return 'extension'
    return 'core'


def _ramp(index: int, total: int, profile: methodology.AuthoringProfile) -> int:
    low, high = profile.shape.difficulty_min, profile.shape.difficulty_max
    if total <= 1:
        return (low + high) // 2
    return round(low + (high - low) * (index / (total - 1)))


def build_graph(plan: blueprint.CoursePlan,
                profile: methodology.AuthoringProfile) -> KnowledgeGraph:
    """The course as a validated DAG, with teaching order recorded separately.

    ``sequence_predecessors`` carries the order the course is *presented* in (previous
    concept in the unit, and the previous unit's last concept as a spiral reminder),
    while ``prerequisites`` carries only hard dependencies. Keeping them apart is what
    lets the map lay the course out in the order it is taught without claiming that
    every consecutive pair is a dependency - the distinction
    :class:`app.knowledge_graph.ConceptNode` documents and that a flat "next" edge
    destroys.
    """
    graph = KnowledgeGraph(Taxonomy({unit.strand: {unit.title: [unit.title]}
                                     for unit in plan.units}))
    ordered = plan.concepts()
    total = len(ordered)
    previous: str | None = None
    for index, concept in enumerate(ordered):
        prerequisites = [edge for edge in concept.prerequisites if edge in plan.by_id()]
        sequence = [previous] if previous and previous not in prerequisites else []
        graph.add(ConceptNode(
            id=concept.id,
            title=concept.title,
            strand=concept.strand or concept.unit,
            unit=concept.unit,
            topic=concept.unit,
            tier=concept.tier if concept.tier in ('foundation', 'core', 'extension')
            else _tier(index, total),
            difficulty=concept.difficulty or _ramp(index, total, profile),
            prerequisites=prerequisites,
            sequence_predecessors=sequence,
            keywords=list(concept.keywords),
            summary=concept.summary,
            has_lesson=True,
            lesson_id=concept.id,
            provenance={'origin': ORIGIN, 'course_id': plan.id,
                        'blueprint_digest': plan.digest(),
                        'authored_by': plan.author},
        ))
        previous = concept.id
    return graph


def build_course(plan: blueprint.CoursePlan) -> courses.Course:
    """The registry entry.

    ``subject_kind`` is ``custom`` for every foundry course, even a mathematics one, and
    that is deliberate. ``courses.Course.uses_symbolic_engine`` is true only for
    ``mathematics``, and it routes a concept through the maths templates in
    ``app/mathkit``. Those templates match on authored concept ids and fall back to a
    generic quadratic for anything they do not recognise - so declaring a foundry maths
    course ``mathematics`` would draw an unrelated parabola and present it as though it
    were about the concept. The subject *name* still says Mathematics; only the engine
    binding is withheld, because the foundry does not author symbolic templates.
    """
    return courses.Course(
        id=plan.id,
        title=plan.title,
        subject=plan.subject,
        subject_kind='custom',
        description=plan.description,
        pack=f'foundry/{plan.id}',
        expected_weeks=plan.expected_weeks,
        authored=False,
    )


# ------------------------------------------------------------------------ blocks

def _block(kind: str, title: str, body: str, **extra: Any) -> dict[str, Any]:
    payload = {'kind': kind, 'title': title, 'body': body.strip(), 'formula': ''}
    payload.update({key: value for key, value in extra.items() if value})
    return payload


#: A step that already numbers itself: "1. Draw the axes", "2) Read the intercept",
#: "Step 3: check". Used only to decide whether to add numbering, never to rewrite it.
_STEP_NUMBER = re.compile(r'^\s*(?:step\s*)?\d+\s*[.):\-]\s*', re.IGNORECASE)


def _example_body(concept: blueprint.ConceptPlan) -> str:
    """The worked example, numbered exactly once.

    The model is asked for the steps as a list and frequently returns them already
    numbered - "1. Draw the axes", "2. Read the intercept". Prefixing our own index on top
    of that produced "1. 1. Draw the axes" in the review copy, and a reviewer who sees
    that reads the whole document as careless. So the numbering is added only when the
    model did not number the steps itself; when it did, its own numbering stands.

    Nothing is renumbered. A step list whose numbers disagree with their order is a
    content problem for the audit, not something to paper over by rewriting the text.
    """
    if not concept.example:
        return ''
    steps = [str(step).strip() for step in concept.example if str(step).strip()]
    if not steps:
        return ''
    if len(steps) == 1:
        return steps[0]
    if all(_STEP_NUMBER.match(step) for step in steps):
        return '\n'.join(steps)
    return '\n'.join(f'{index}. {step}' for index, step in enumerate(steps, 1))


def _retrieval_body(concept: blueprint.ConceptPlan, parents: Sequence[str],
                    titles: Mapping[str, str]) -> str:
    """A retrieval prompt that names what to retrieve, not "review this".

    Retrieval practice works when the learner has to *produce* something specific; "go
    over the idea" is re-reading with extra steps. So the prompt names the two things
    the lesson actually established: what the concept is, and what it rests on.
    """
    parts = [f'Without notes, state what {concept.title} is in one sentence.']
    if parents:
        named = ', '.join(titles.get(parent, parent) for parent in parents[:2])
        parts.append(f'Then name the idea it rests on ({named}) and say why the order '
                     f'matters.')
    else:
        parts.append('Then give one example of it and one thing that is *not* an example.')
    parts.append('Rate your confidence from 0 to 1 before you check.')
    return ' '.join(parts)


def _fade_body(concept: blueprint.ConceptPlan, titles: Mapping[str, str],
               parents: Sequence[str]) -> str:
    """The worked-example fade: the scaffold is withdrawn in the final unit.

    The expertise-reversal effect is the reason this exists rather than "more practice".
    A learner who has met five worked examples in this course does not need a sixth;
    continuing to supply one substitutes for the retrieval they now need to do. The
    prompt therefore keeps the *structure* of the example (what to decide, in what
    order) and withholds the worked content.
    """
    steps = ('name the quantities or terms involved, state the rule that connects them, '
             'carry the step out, then check the result against a case you already know')
    if parents:
        steps = (f'start from {titles.get(parents[0], parents[0])}, ' + steps)
    return (f'The worked example is withdrawn here on purpose: you have met this shape '
            f'of problem before in this course. For {concept.title}, {steps}. '
            f'If you stall, re-read the definition rather than looking for a model answer.')


def _misconception_body(concept: blueprint.ConceptPlan) -> str:
    if not concept.misconception:
        return ''
    body = f'The mistake: {concept.misconception}'
    if concept.correction:
        body += f'\nThe repair: {concept.correction}'
    return body


def _scope_block(plan: blueprint.CoursePlan) -> dict[str, Any]:
    """The provenance block. Same posture as the authored course's disclosure block.

    A course composed by the harness says so, in the lesson, where the learner is. It is
    the cheapest possible defence against the failure mode this whole subsystem could
    create: generated prose that reads exactly like reviewed prose.
    """
    return _block(
        'reflection', 'Where this lesson comes from',
        f'This lesson was composed by the harness from a course blueprint '
        f'(digest {plan.digest()}), authored by {plan.author}. It has not been externally '
        f'peer-reviewed, and it is not a substitute for a teacher\'s judgement about your '
        f'work. External readings are link-only: no outside text is copied into this '
        f'course. If you used an AI tool while studying, say where.')


def build_blocks(plan: blueprint.CoursePlan, concept: blueprint.ConceptPlan,
                 graph: KnowledgeGraph, profile: methodology.AuthoringProfile,
                 *, final_unit: bool) -> list[dict[str, Any]]:
    """The lesson, in the profile's declared order, with the fade applied."""
    titles = {node_id: node.title for node_id, node in graph.nodes.items()}
    parents = [edge for edge in concept.prerequisites if edge in graph.nodes]
    faded = set(profile.fade_in_final_unit) if final_unit else set()
    blocks: list[dict[str, Any]] = []
    for spec in profile.blocks:
        if spec.kind in faded:
            # The fade replaces the block rather than deleting it. A learner in the final
            # unit gets the *structure* of the method and none of the worked content,
            # which is what expertise reversal says they need; an empty slot would be a
            # gap in the lesson and the audit would (correctly) call it one.
            blocks.append(_block('reflection', 'Your turn, without a model',
                                 _fade_body(concept, titles, parents)))
            continue
        body = ''
        if spec.source:
            body = concept.prose().get(spec.source, '')
            if spec.source == 'example':
                body = _example_body(concept)
            if spec.source == 'misconception':
                body = _misconception_body(concept)
        elif spec.kind == 'retrieval':
            body = _retrieval_body(concept, parents, titles)
        if not body:
            # A required block with no prose is a gap, not a block. Emitting an empty
            # body would render as a titled blank and the audit could no longer tell a
            # missing worked example from a present one.
            continue
        blocks.append(_block(spec.kind, spec.title, body))
    blocks.append(_scope_block(plan))
    return blocks


# ------------------------------------------------------------------------- items

def _pick(seed: str, candidates: Sequence[tuple[Any, str]], correct: str,
          count: int) -> list[tuple[Any, str]]:
    """Deterministic, de-duplicated distractor selection.

    Mirrors the rule the generated layer learned the hard way: choose distractors
    *first*, then add the correct option. Truncating a merged list can drop the answer
    and leave ``answer_id`` pointing at a distractor, which is a silently wrong key
    rather than an obviously broken item.
    """
    seen = {correct}
    pool: list[tuple[Any, str]] = []
    for source, text in candidates:
        text = (text or '').strip()
        if not text or text in seen:
            continue
        seen.add(text)
        pool.append((source, text))
    pool.sort(key=lambda entry: hashlib.sha256(
        f'{seed}|pick|{entry[1]}'.encode('utf-8')).hexdigest())
    return pool[:count]


def _assemble(course_id: str, concept: blueprint.ConceptPlan, variant: int, *,
              prompt: str, correct: str, candidates: Sequence[tuple[Any, str]],
              category: str, explanation: str, next_action: str,
              answerable_from: str, seconds: int = 60) -> dict[str, Any] | None:
    """One generated item, or ``None`` when the course cannot supply three distractors.

    The refusal is the point. An item with three options instead of four is not a slightly
    worse item: guessing scores 33% instead of 25%, the per-distractor diagnoses are
    incomplete, and nothing downstream can tell that this item is easier than its
    neighbours. Since distractors are drawn from *other concepts' prose*, a lesson written
    on its own - one concept, or a single unit before the rest exist - genuinely cannot
    produce them, and the honest answer is to ship no generated item than a broken one.
    The concept still gets whatever the blueprint wrote by hand, and the audit's
    ``items_too_few`` names the shortfall in the terms a fix would need.
    """
    seed = f'{course_id}|{concept.id}|{variant}'
    picks = _pick(seed, candidates, correct, 3)
    if len(picks) < 3:
        return None
    entries: list[tuple[bool, Any, str]] = [(True, concept, correct)]
    entries.extend((False, source, text) for source, text in picks)
    entries.sort(key=lambda entry: hashlib.sha256(
        f'{seed}|order|{entry[2]}'.encode('utf-8')).hexdigest())

    options: list[dict[str, str]] = []
    diagnoses: dict[str, dict[str, str]] = {}
    answer_id = OPTION_IDS[0]
    for index, (is_correct, source, text) in enumerate(entries[:4]):
        option_id = OPTION_IDS[index]
        options.append({'id': option_id, 'text': text})
        if is_correct:
            answer_id = option_id
        else:
            confused = getattr(source, 'title', None)
            diagnoses[option_id] = {
                'category': 'conceptual',
                'reason': (f'This is the statement for "{confused}", not for '
                           f'"{concept.title}".' if confused else
                           'This does not follow from the lesson you were given.'),
                'next_action': next_action,
            }
    return {
        'id': question_id(course_id, concept.id, variant),
        'concept_id': concept.id,
        'concept_title': concept.title,
        'prompt': prompt,
        'options': options,
        'kind': GENERATED_KIND,
        'generated': True,
        'origin': ORIGIN,
        'expected_seconds': seconds,
        'answer_id': answer_id,
        'answer_text': correct,
        'explanation': explanation,
        'category': category,
        #: Which lesson block contains this answer. The audit reads it to prove the item
        #: is answerable from material the learner actually received, rather than
        #: trusting that it is.
        'answerable_from': answerable_from,
        'distractor_diagnoses': diagnoses,
    }


def _siblings(plan: blueprint.CoursePlan, concept: blueprint.ConceptPlan,
              attribute: str) -> list[tuple[Any, str]]:
    """Other concepts' text for one attribute, nearest-first.

    Same-unit siblings first: a distractor drawn from the same unit is plausible in a
    way one drawn from three units away is not, and plausibility is the whole point of a
    distractor. The wider course is the fallback, not the first choice.
    """
    same_unit, elsewhere = [], []
    for other in plan.concepts():
        if other.id == concept.id:
            continue
        value = getattr(other, attribute, '') or ''
        if isinstance(value, (list, tuple)):
            value = ' '.join(value)
        if not value:
            continue
        (same_unit if other.unit == concept.unit else elsewhere).append((other, value))
    return same_unit + elsewhere


def build_questions(plan: blueprint.CoursePlan, concept: blueprint.ConceptPlan,
                    profile: methodology.AuthoringProfile,
                    notes: list[str] | None = None) -> dict[str, dict[str, Any]]:
    """The foundry's two items, plus any hand-written ones the blueprint supplied.

    The generated layer already asks what each concept is — its statement, its terms,
    and the concept behind each. What it cannot ask is the two questions that require
    authored prose: *which repair is right for this specific mistake*, and *which task
    actually requires this idea*. Those are the items that distinguish a lesson from a
    definition list.

    ``notes`` collects the cases where a generated item was withheld for want of
    distractors. A lesson is never *told* it lost an item otherwise: the concept would
    look complete while being assessed on the hand-written layer alone.
    """
    items: dict[str, dict[str, Any]] = {}
    if concept.misconception and concept.correction:
        candidates = _siblings(plan, concept, 'correction')
        candidates.append((None, _NO_REPAIR_NEEDED))
        item = _assemble(
            plan.id, concept, _VARIANT_MISCONCEPTION,
            prompt=(f'A learner studying {concept.title} says: "{concept.misconception}" '
                    f'Which correction is right?'),
            correct=concept.correction, candidates=candidates,
            category='misconception_repair',
            explanation=(f'The lesson names this exact mistake and its repair. The other '
                         f'options repair different misconceptions from this course, '
                         f'which is what makes them tempting.'),
            next_action=f'Re-read "The mistake to expect" for {concept.title}.',
            answerable_from='misconception',
            seconds=profile.assessment.expected_seconds)
        if item is not None:
            items[item['id']] = item
        elif notes is not None:
            notes.append(f'{concept.id}: no misconception item; the course does not '
                         f'supply three other repairs to use as distractors')

    if concept.application:
        item = _assemble(
            plan.id, concept, _VARIANT_APPLICATION,
            prompt=(f'Which task actually requires {concept.title}, rather than '
                    f'something else in this course?'),
            correct=concept.application,
            candidates=_siblings(plan, concept, 'application'),
            category='application_transfer',
            explanation=(f'The lesson ends by asking for exactly this task. The other '
                         f'options are tasks set for other concepts in the course.'),
            next_action=f'Try the task in "Use it somewhere new" for {concept.title}.',
            answerable_from='transfer',
            seconds=profile.assessment.expected_seconds)
        if item is not None:
            items[item['id']] = item
        elif notes is not None:
            notes.append(f'{concept.id}: no transfer item; the course does not supply '
                         f'three other tasks to use as distractors')

    for index, raw in enumerate(concept.items):
        item = _hand_written(plan, concept, raw, index + _VARIANT_APPLICATION + 1)
        if item is not None:
            items[item['id']] = item
    return items


def _hand_written(plan: blueprint.CoursePlan, concept: blueprint.ConceptPlan,
                  raw: Mapping[str, Any], variant: int) -> dict[str, Any] | None:
    """A blueprint-supplied item, normalized into the same shape as a generated one.

    Refused (``None``) rather than repaired when it is malformed: an item with three
    options or no answer key is not a slightly worse item, it is an ungradeable one, and
    the audit would rather report the concept as short than accept it.
    """
    prompt = str(raw.get('prompt') or '').strip()
    options = raw.get('options')
    answer = raw.get('answer')
    if not prompt or not isinstance(options, Sequence) or isinstance(options, (str, bytes)):
        return None
    texts = [str(option).strip() for option in options]
    if len(texts) != 4 or len(set(texts)) != 4 or not answer:
        return None
    answer_text = str(answer).strip()
    if answer_text not in texts:
        return None
    order = sorted(range(4), key=lambda index: hashlib.sha256(
        f'{plan.id}|{concept.id}|{variant}|{texts[index]}'.encode()).hexdigest())
    assembled = [{'id': OPTION_IDS[position], 'text': texts[index]}
                 for position, index in enumerate(order)]
    answer_id = next(option['id'] for option in assembled if option['text'] == answer_text)
    return {
        'id': question_id(plan.id, concept.id, variant),
        'concept_id': concept.id, 'concept_title': concept.title, 'prompt': prompt,
        'options': assembled, 'kind': 'multiple_choice', 'generated': False,
        'origin': ORIGIN, 'expected_seconds': 60, 'answer_id': answer_id,
        'answer_text': answer_text,
        'explanation': str(raw.get('explanation') or '').strip(),
        'category': str(raw.get('category') or 'authored_item'),
        'answerable_from': str(raw.get('answerable_from') or 'summary'),
        'distractor_diagnoses': {},
    }


# ------------------------------------------------------------------------- build

def build(plan: blueprint.CoursePlan, *,
          profile: methodology.AuthoringProfile | None = None) -> AuthoredCourse:
    """Synthesize the whole course. Pure: it touches no global registry.

    Purity is what makes the preview endpoint honest - a teacher can see the course, its
    lessons and its items before a single row or file exists - and what lets the audit
    run on a course that will never be published.
    """
    resolved = profile or plan.profile
    graph = build_graph(plan, resolved)
    course = build_course(plan)
    concepts, questions = materialise_graph(course, graph)

    notes: list[str] = []
    final_unit_title = plan.units[-1].title if plan.units else ''
    by_id = plan.by_id()
    for concept_id_value, entry in concepts.items():
        concept = by_id.get(concept_id_value)
        if concept is None:
            continue
        final_unit = concept.unit == final_unit_title
        blocks = build_blocks(plan, concept, graph, resolved, final_unit=final_unit)
        entry['blocks'] = blocks
        entry['origin'] = ORIGIN
        entry['objective'] = concept.objective
        entry['lesson_id'] = concept.id
        entry['project'] = _project(plan, concept, graph)
        entry['hint'] = _hint(concept, graph)
        entry['media'] = policy.reference_media(plan.id)
        if not blocks:
            notes.append(f'{concept.id}: no lesson blocks were produced')

    for concept_id_value, concept in by_id.items():
        if concept_id_value not in concepts:
            notes.append(f'{concept.id}: synthesized but not materialised')
            continue
        questions.update(build_questions(plan, concept, resolved, notes))

    # A planned concept that produced no lesson entry would be invisible: the course
    # would look smaller than its blueprint and nothing downstream would know. Reported
    # here, and the audit refuses it as ``concept_not_materialised``.
    missing = [concept.id for concept in by_id.values() if concept.id not in concepts]
    for concept_id_value in missing:
        notes.append(f'{concept_id_value}: planned but not materialised')

    return AuthoredCourse(plan=plan, course=course, graph=graph, concepts=concepts,
                          questions=questions, profile=resolved, notes=notes)


#: The marker on an overlay lesson's own field. ``origin`` is shared with an authored
#: course because both are model-written prose audited by the same gate; ``overlay`` says
#: which of the two shapes this is, so a reader can tell "a course the harness built" from
#: "lessons the harness wrote inside a course it did not build".
OVERLAY_MARKER = 'overlay'


def build_overlay(plan: blueprint.CoursePlan, *, course: courses.Course, graph: KnowledgeGraph,
                  base: Mapping[str, Mapping[str, Any]],
                  profile: methodology.AuthoringProfile | None = None) -> AuthoredCourse:
    """Synthesize lessons *into* an existing course instead of creating a new one.

    Why this exists at all: ``build`` derives its own graph from the blueprint, so an
    authored course is a second course standing next to the shipped pack. For a subject
    whose pack already declares the full scope and sequence - AP Microeconomics ships 57
    nodes and 0 lessons - a parallel course would duplicate the map, split the learner's
    progress between two ids, and leave ``ap_microeconomics`` permanently empty. The
    concept ids here are the pack's own; the plan is a *framed outline* of them.

    What is taken from where, and why:

    * **Structure from the pack.** ``id``, ``unit``, ``strand``, ``topic``, ``tier``,
      ``difficulty``, ``prerequisites`` and ``graph_id`` are the shipped graph's, so the
      map, prerequisite gating and diagnosis keep working against the same nodes they
      always did.
    * **Depth from the blueprint.** Blocks, the project, the hint and the items replace
      what the generated layer produced, because that layer's blocks only tell a learner
      to re-read the summary.
    * **The ``generated`` flag is dropped.** That flag is what ``authored_share`` counts,
      and after this pass the concept genuinely has a written lesson. Dropping it is the
      claim; :func:`app.curriculum.authored_share` is where it is cashed.

    A concept the plan names but the pack does not own is reported, not invented:
    ``concept_not_in_course`` is a fact about the blueprint, and silently adding a node
    would create a concept no graph edge reaches.
    """
    resolved = profile or plan.profile
    by_id = plan.by_id()
    # The fade belongs to the *course's* last unit, not to the last unit written today.
    # ``plan.units[-1]`` would be right for a course the foundry designed in one sitting,
    # and wrong for a patch: a lesson written on its own is that plan's final unit, so its
    # worked example would be withdrawn as if the learner had already met five of them.
    # The graph is the authority on teaching order, so it supplies the answer.
    course_units = graph.units()
    final_unit_title = (course_units[-1] if course_units
                        else (plan.units[-1].title if plan.units else ''))
    concepts: dict[str, dict[str, Any]] = {}
    questions: dict[str, dict[str, Any]] = {}
    notes: list[str] = []

    for concept_id, entry in base.items():
        concept = by_id.get(concept_id)
        if concept is None:
            continue
        merged = dict(entry)
        blocks = build_blocks(plan, concept, graph, resolved,
                              final_unit=concept.unit == final_unit_title)
        # Classified from the *pack's* title, summary and keywords, not from the blueprint's
        # paraphrase and not from the prose the model just wrote. Two reasons, both learned
        # from a rebuild that silently lost figures: the pack's text is the concept's stable
        # identity, and an overlay publish writes its own summary onto the materialised
        # concept, so reading it here made the classification depend on what earlier runs had
        # published. A rewrite that happens to drop the word "elasticity" must not leave a
        # lesson on price elasticity without its curve, and a rewrite that mentions a
        # "market" must not hand an accounting distinction a supply-and-demand picture.
        node = graph.nodes.get(str(concept_id))
        figure = econ_figures.for_concept(
            str(concept_id),
            str(getattr(node, 'title', '') or merged.get('title') or ''),
            ' '.join(str(part) for part in
                     (getattr(node, 'summary', ''), ' '.join(getattr(node, 'keywords', []) or []))
                     if part) or str(merged.get('summary') or concept.summary or ''))
        if figure is not None:
            blocks = _with_figure(blocks, figure)
        merged['blocks'] = blocks
        # ``generated`` stays true, and that is the honest answer rather than the
        # flattering one: a model wrote this prose, nobody reviewed it yet, and
        # ``authored_share`` must keep saying so. What changed is that the concept now has
        # a lesson with a worked example instead of four definition items, which is what
        # ``curriculum.written_share`` reports separately.
        merged['generated'] = True
        merged['origin'] = ORIGIN
        merged['overlay'] = True
        merged['lesson_id'] = str(concept_id)
        merged['objective'] = concept.objective
        merged['summary'] = concept.summary or str(merged.get('summary') or '')
        merged['project'] = _project(plan, concept, graph)
        merged['hint'] = _hint(concept, graph)
        merged['media'] = policy.reference_media(plan.id)
        merged['figure'] = figure or None
        concepts[str(concept_id)] = merged
        if not blocks:
            notes.append(f'{concept_id}: no lesson blocks were produced')

    pool = list(graph.nodes.values())
    for concept_id, concept in by_id.items():
        if concept_id not in concepts:
            notes.append(f'{concept_id}: named by the blueprint but not owned by '
                         f'{course.id}; no lesson written')
            continue
        # The structural four come first, then the two the authored prose makes possible.
        # Publishing drops a written concept's old items - they test a summary the new
        # lesson no longer contains - so skipping this step would leave the concept with
        # *fewer* questions than before the overlay. Deepening is not allowed to be a
        # trade against coverage.
        node = graph.nodes.get(concept_id)
        if node is not None:
            questions.update(structural_items(course.id, node, graph, pool))
        questions.update(build_questions(plan, concept, resolved, notes))

    return AuthoredCourse(plan=plan, course=course, graph=graph, concepts=concepts,
                          questions=questions, profile=resolved, notes=notes)


def _with_figure(blocks: list[dict[str, Any]],
                 figure: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Put the deterministic diagram after the first prose block.

    A ``figure`` block is invisible to the audit's depth rules (it has no prose to
    measure) and its caption is counted in the lesson's word budget, so it is kept to one
    sentence plus the stated parameters. The payload also travels on ``entry['figure']``
    for clients that render figures from data rather than from an inline SVG.
    """
    block = {'kind': 'figure', 'title': 'Diagram',
             'body': econ_figures.caption_with_parameters(dict(figure)),
             'svg': figure.get('svg', ''), 'figure_kind': figure.get('kind', ''),
             'parameters': figure.get('parameters') or {}}
    placed = list(blocks)
    seen = 0
    index = 0
    for position, existing in enumerate(placed):
        if existing.get('kind') == 'concept':
            seen += 1
            index = position + 1
            if seen >= 2:
                break
    placed.insert(index, block)
    return placed


def _project(plan: blueprint.CoursePlan, concept: blueprint.ConceptPlan,
             graph: KnowledgeGraph) -> dict[str, Any]:
    """The unit's applied task, expressed as the concept's project.

    The project is unit-level in the methodology and concept-level in the data model
    because every surface that renders a project is scoped to a concept. Rather than
    invent a unit-level object nothing reads, the unit objective becomes the project for
    each of its concepts - which is also true: the unit's objective is what every concept
    in it is for.
    """
    unit = next((u for u in plan.units if u.title == concept.unit), None)
    objective = (unit.objective if unit else '') or concept.objective
    return {
        'title': f'{concept.title}: apply it',
        'prompt': (concept.application or
                   f'Explain {concept.title} in your own words, then use it to answer: '
                   f'{objective}'),
        'rubric': [
            'State the idea in your own words, not the course wording.',
            'Name the prerequisite it rests on and say why the order matters.',
            'Work one concrete case end to end.',
            'Name one thing you are still unsure about, and disclose any AI assistance.',
        ],
    }


def _hint(concept: blueprint.ConceptPlan, graph: KnowledgeGraph) -> str:
    if concept.prerequisites:
        first = concept.prerequisites[0]
        title = graph.nodes[first].title if first in graph.nodes else first
        return f'Start from {title}, not from this concept.'
    return f'Define {concept.title} in one sentence before trying to use it.'


def build_from_document(document: Mapping[str, Any], *, author: str = 'operator',
                        ) -> tuple[AuthoredCourse | None, list[blueprint.Problem]]:
    """Parse then synthesize. The single entry point a route or tool should call."""
    plan, problems = blueprint.parse(document, author=author)
    if plan is None:
        return None, problems
    return build(plan), problems


__all__ = ['AuthoredCourse', 'ORIGIN', 'build', 'build_blocks', 'build_course',
           'build_from_document', 'build_graph', 'build_questions']
