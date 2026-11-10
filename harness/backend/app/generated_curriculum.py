"""Generated lesson and question layer for courses with no authored content.

The algebra course ships with 15 hand-authored lessons and 60 hand-written questions.
The other courses ship with a knowledge graph and nothing else, which would leave a
physics learner able to browse a map but unable to practise - a course that looks
complete and is not.

This module closes that gap by *materialising* the graph into the same shapes the
authored layer uses (``CONCEPTS`` and ``QUESTIONS``), so every downstream path -
receipts, grading, diagnosis, memory, spaced review, projects - works unchanged.
Nothing here is special-cased for generated content.

Two rules keep the generated items honest.

1. **Every item is answerable from the curriculum itself, and every item is about a
   concept rather than about the course.** The correct option is a fact the course
   states about the concept: its own summary, its own title, one of its own terms.
   No item asks the learner to guess at something the harness does not actually know.

   The first generated layer also asked which *unit* a concept sat in, which idea
   had to come *first* and which came *later*. Those are answerable from the course
   tree without knowing any of the material, so a learner who had only browsed the
   outline could do well on a diagnostic that was supposed to place them - the
   diagnostic measured navigation, not understanding. Nothing here asks where a
   concept lives; it asks what the concept is.

2. **Generated items say so.** They carry ``generated: True``, a distinct ``kind``, and
   an explanation that names the source of the fact. A learner and a reviewer can both
   tell an authored item from a derived one.
"""

from __future__ import annotations

import hashlib
from typing import Any, Iterable, Mapping

from . import courses
from .ingest import policy

#: Marks a question as derived from graph structure rather than hand-written.
GENERATED_KIND = 'generated_multiple_choice'

#: Options per item, including the correct one.
OPTIONS = 4

#: How many distractor candidates a builder offers before de-duplication. More than ``OPTIONS``
#: is passed so that a course with repeated titles or summaries still yields four distinct
#: options rather than an item that offers its own correct answer.
CANDIDATES = OPTIONS + 8

#: Items per concept. ``validate_curriculum`` requires at least four variants.
VARIANTS = 4

OPTION_IDS = ('a', 'b', 'c', 'd')

#: Question ids must fit the receipt schema, which caps them at 64 characters.
MAX_QUESTION_ID = 64


def _short(value: str, length: int = 20) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()[:length]


def _stable_order(seed: str, items: Iterable[Any]) -> list[Any]:
    """Deterministic ordering, so the same course always yields the same items."""
    return sorted(items, key=lambda item: hashlib.sha256(
        f'{seed}|{getattr(item, "id", item)}'.encode('utf-8')).hexdigest())


def _question_id(course_id: str, node_id: str, variant: int) -> str:
    prefix = course_id[:8]
    candidate = f'{prefix}-{node_id}-{variant}'
    if len(candidate) <= MAX_QUESTION_ID:
        return candidate
    # Long slugs are truncated and disambiguated by a digest of the full id, so two
    # different nodes can never collide onto the same question id.
    room = MAX_QUESTION_ID - len(prefix) - len(str(variant)) - len(_short(node_id, 12)) - 3
    return f'{prefix}-{node_id[:room]}-{_short(node_id, 12)}-{variant}'


# --------------------------------------------------------------- concept entries

def _blocks(node, graph, ordered: list) -> list[dict[str, Any]]:
    """Four teaching blocks derived entirely from the graph."""
    title = node.title
    prerequisites = [graph.nodes[n] for n in graph.parents(node.id) if n in graph.nodes]
    dependants = [graph.nodes[n] for n in graph.children(node.id) if n in graph.nodes]
    depth = len([n for n in graph.ancestors(node.id) if n in graph.nodes])

    core = node.summary or f'{title} is a concept in this course.'
    if prerequisites:
        rests = '; '.join(f'{p.title} — {p.summary}' for p in prerequisites[:3])
        core += f' It builds directly on {len(prerequisites)} earlier idea(s): {rests}'
    else:
        core += ' Nothing in this course has to come before it, so it is a place you can start.'

    concept_block = {
        'kind': 'concept',
        'title': 'Core idea',
        'body': core,
        'formula': '',
    }

    context_block = {
        'kind': 'concept',
        'title': 'Where this sits',
        'body': (
            f'{title} belongs to the unit "{node.unit or "unassigned"}"'
            + (f' and the topic "{node.topic}"' if node.topic else '')
            + f' inside the strand "{node.strand or "unassigned"}".'
            + (f' Counting indirect dependencies, {depth} concept(s) in this course sit '
               f'underneath it in the prerequisite order, so gaps lower down tend to show '
               f'up as difficulty here.' if depth else '')
            + (f' Understanding it unlocks {len(dependants)} later idea(s): '
               + ', '.join(d.title for d in dependants[:4]) + '.' if dependants else
               ' It is a leaf of the course: nothing later in this course depends on it.')
        ),
        'formula': '',
    }

    if prerequisites:
        weakest = min(prerequisites, key=lambda p: (p.difficulty or 3))
        retrieval_block = {
            'kind': 'retrieval',
            'title': 'Check before you go on',
            'body': (
                f'Before working on {title}, try to state in your own words what '
                f'{weakest.title} means and why it matters. If you cannot, that is the '
                f'gap to close first — a weak prerequisite is the most common reason a '
                f'later idea feels harder than it is.'
            ),
            'formula': '',
        }
    else:
        retrieval_block = {
            'kind': 'retrieval',
            'title': 'Check before you go on',
            'body': (f'Before working on {title}, write one sentence saying what you '
                     f'already believe it means. Being wrong in writing is more useful '
                     f'than being vague in your head.'),
            'formula': '',
        }

    reflection_block = {
        'kind': 'reflection',
        'title': 'Reflect',
        'body': (
            f'Which part of {title} is still unclear to you? Name the specific step or '
            f'term rather than the whole idea — a named gap is one you can close, and a '
            f'vague one is not. If you used any AI tool while studying this, say where.'
        ),
        'formula': '',
    }

    return [concept_block, context_block, retrieval_block, reflection_block]


def _concept_entry(course_id: str, node, graph) -> dict[str, Any]:
    prerequisites = [n for n in graph.parents(node.id) if n in graph.nodes]
    # Authored lessons are keyed by lesson id; a generated lesson is keyed by its own
    # graph node id, because that is what a receipt and an attempt will carry.
    return {
        'id': node.id,
        'title': node.title,
        'unit': node.unit or '',
        'strand': node.strand or '',
        'topic': node.topic or '',
        'tier': node.tier or 'core',
        'difficulty': int(node.difficulty or 3),
        'graph_id': node.id,
        'has_lesson': True,
        'generated': True,
        'course_id': course_id,
        'prerequisites': prerequisites,
        'summary': node.summary or '',
        'blocks': _blocks(node, graph, prerequisites),
        'simulation': {
            'kind': 'concept_map',
            'title': f'{node.title}: how it connects',
            'scope': ('A concept map derived from this course\'s own prerequisite edges and '
                      'your own recorded mastery. It is not a physical or mathematical model.'),
            'parameters': [],
        },
        'project': {
            'title': f'{node.title}: explain and apply',
            'prompt': (f'Explain {node.title} in your own words to someone who has not met '
                       f'it, then apply it to one concrete example of your own choosing.'),
            'rubric': [
                'State the idea in your own words, not the course wording.',
                'Connect it explicitly to at least one prerequisite concept.',
                'Work one concrete example end to end.',
                'Name one thing you are still unsure about, and disclose any AI assistance.',
            ],
        },
        # External readings and videos the learner may open elsewhere. These are links, never
        # content: the licence gate classes every one as link-only, so nothing is copied,
        # embedded or trained on. They are not decoration -- the tutor cites this list as its
        # curriculum grounding, and a science learner whose concept had no reference at all
        # got an answer with no citable source behind it.
        'media': policy.reference_media(course_id),
        'hint': (f'Start from {graph.nodes[prerequisites[0]].title}, not from this concept.'
                 if prerequisites else
                 f'Define {node.title} in one sentence before trying to use it.'),
    }


# ---------------------------------------------------------------- question items

def _near_duplicate(text: str, other: str) -> bool:
    """Whether two option texts are so close that offering both is ambiguous.

    Exact equality is already handled by de-duplication, but two concepts in one unit can
    carry summaries that differ by a word ("...counts ordered arrangements" vs
    "...counts arrangements"), and a learner faced with both cannot tell which the item
    wants. Near-duplicates are the cost of drawing distractors from the same unit, so they
    are filtered here rather than avoided by drawing from a distant one.
    """
    left = {word for word in text.casefold().split() if len(word) > 2}
    right = {word for word in other.casefold().split() if len(word) > 2}
    if not left or not right:
        return False
    return len(left & right) / len(left | right) >= 0.8


def _neighbours(pool: list, node) -> list:
    """Distractor candidates, nearest first.

    Proximity is the whole point of a distractor: an option drawn from another unit is
    obviously wrong on sight, so it tests nothing and the item becomes a vocabulary
    exercise. The order here is the same topic, then the same unit, then the rest of the
    course -- near enough to be tempting, far enough to be wrong.
    """
    def rank(other) -> tuple[int, str]:
        if other.id == node.id:
            return (9, other.id)
        if node.topic and other.topic == node.topic:
            return (0, other.id)
        if node.unit and other.unit == node.unit:
            return (1, other.id)
        if node.strand and other.strand == node.strand:
            return (2, other.id)
        return (3, other.id)
    return sorted((n for n in pool if n.id != node.id), key=rank)


def _definition_item(course_id: str, node, graph, pool: list) -> dict[str, Any]:
    """Which statement best describes this concept? Correct = its own summary."""
    # Exclude any node whose summary is identical to this one's. Two concepts in one course
    # can legitimately carry the same summary text, and a distractor that reproduces the
    # correct option would make the item unanswerable.
    distractors = [n for n in _neighbours(pool, node)
                   if n.summary and n.summary != node.summary
                   and not _near_duplicate(n.summary, node.summary)][:CANDIDATES]
    return _assemble(course_id, node, 0,
                     prompt=f'Which statement best describes {node.title}?',
                     correct_text=node.summary,
                     distractors=[(d, d.summary) for d in distractors],
                     category='definition_recall',
                     explanation=(f'The correct option is this course\'s own summary of '
                                  f'{node.title}. The other options are the summaries of '
                                  f'nearby concepts, which is what makes them plausible.'),
                     next_action=f'Re-read the "Core idea" block for {node.title}.')


def _keywords(node) -> list[str]:
    """The concept's own terms, defensively.

    Every shipped pack carries them and a blueprint may carry them, but a
    hand-written blueprint can omit them - and an item that asks about a term the
    course never stated would be unanswerable, so the builders check before they
    build rather than after.
    """
    return [term for term in (str(k).strip() for k in (getattr(node, 'keywords', None) or []))
            if term]


def _term_item(course_id: str, node, graph, pool: list) -> dict[str, Any]:
    """Which term belongs to this concept? Correct = one of its own keywords."""
    own = _keywords(node)
    if not own:
        # No terms to ask about. The item degrades to the definition check rather
        # than naming a term the course never stated.
        return _definition_item(course_id, node, graph, pool)
    own_folded = {term.casefold() for term in own}
    # A term the course also lists for *this* concept would be a second correct
    # option, so the candidate set excludes the concept's own terms outright.
    elsewhere = [(n, term) for n in _neighbours(pool, node)
                 for term in _keywords(n) if term.casefold() not in own_folded]
    return _assemble(course_id, node, 1,
                     prompt=f'Which of these terms belongs to {node.title}?',
                     correct_text=own[0],
                     distractors=elsewhere[:CANDIDATES],
                     category='term_association',
                     explanation=(f'"{own[0]}" is one of the terms this course lists '
                                  f'for {node.title}. The other options are terms it '
                                  f'lists for nearby concepts, which is what makes '
                                  f'them tempting.'),
                     next_action=f'Re-read the "Core idea" block for {node.title} '
                                 f'and note the words it uses.',
                     confusion='This term belongs to "{confused}", not to "{title}".')


def _identification_item(course_id: str, node, graph, pool: list) -> dict[str, Any]:
    """Which concept is this statement about? Correct = the concept itself."""
    if not node.summary:
        # Nothing to quote. The item degrades to the term check, which asks about
        # the same concept from the other side.
        return _term_item(course_id, node, graph, pool)
    others = [n for n in _neighbours(pool, node) if n.title and n.title != node.title]
    return _assemble(course_id, node, 2,
                     prompt=f'Which concept does this statement describe? '
                            f'"{node.summary}"',
                     correct_text=node.title,
                     distractors=[(n, n.title) for n in others[:CANDIDATES]],
                     category='concept_identification',
                     explanation=(f'The statement is this course\'s own summary of '
                                  f'{node.title}. The other options are nearby concepts '
                                  f'whose summaries say something else, which is what '
                                  f'makes them plausible.'),
                     next_action=f'Re-read the "Core idea" block for {node.title}.',
                     confusion='This describes "{confused}", not "{title}".')


def _term_set_item(course_id: str, node, graph, pool: list) -> dict[str, Any]:
    """Which concept do these terms describe? Correct = the concept itself."""
    own = _keywords(node)
    if not own:
        return _identification_item(course_id, node, graph, pool)
    own_folded = {term.casefold() for term in own}
    # A concept whose terms are a superset of these would also answer the prompt,
    # which would give the item two right answers. Such a concept is dropped from
    # the candidates; the ``or`` keeps the item buildable if that empties the pool.
    candidates = [n for n in _neighbours(pool, node) if n.title and n.title != node.title]
    candidates = [n for n in candidates
                  if not own_folded <= {t.casefold() for t in _keywords(n)}] or candidates
    listed = ', '.join(f'"{term}"' for term in own)
    prompt = (f'Which concept do these terms describe: {listed}?' if len(own) > 1
              else f'Which concept does this term describe: {listed}?')
    return _assemble(course_id, node, 3,
                     prompt=prompt,
                     correct_text=node.title,
                     distractors=[(n, n.title) for n in candidates[:CANDIDATES]],
                     category='term_set_identification',
                     explanation=(f'This course lists {listed} as the terms for '
                                  f'{node.title}. The other options are nearby concepts '
                                  f'the course describes with different words.'),
                     next_action=f'Re-read the "Core idea" block for {node.title}.',
                     confusion='These terms describe "{confused}", not "{title}".')


def _assemble(course_id: str, node, variant: int, *, prompt: str, correct_text: str,
              distractors: list[tuple[Any, str]], category: str, explanation: str,
              next_action: str,
              confusion: str = 'This is the statement for "{confused}", not for "{title}".',
              ) -> dict[str, Any]:
    """Build one four-option item, shuffling deterministically and recording diagnoses.

    Candidates are de-duplicated by their visible text, and exactly ``OPTIONS - 1`` distinct
    distractors are selected before the correct option is added. Two concepts in a course can
    legitimately share a title or a summary, and a distractor that reproduced the correct
    option would make the item unanswerable rather than merely hard. Selecting the distractors
    *first* and then appending the correct entry is what guarantees the answer is always one of
    the four: truncating a merged candidate list instead could drop the correct option and leave
    ``answer_id`` on its default, which is a silently wrong answer key.
    """
    options: list[dict[str, str]] = []
    diagnoses: dict[str, dict[str, str]] = {}
    seed = f'{course_id}|{node.id}|{variant}'
    seen = {correct_text}
    pool_entries: list[tuple[Any, str]] = []
    for source, text in distractors:
        if text in seen:
            continue
        seen.add(text)
        pool_entries.append((source, text))
    pool_entries.sort(key=lambda e: hashlib.sha256(
        f'{seed}|pick|{e[1]}'.encode('utf-8')).hexdigest())
    entries: list[tuple[bool, Any, str]] = [(True, node, correct_text)]
    entries.extend((False, source, text) for source, text in pool_entries[:OPTIONS - 1])
    entries = sorted(entries, key=lambda e: hashlib.sha256(
        f'{seed}|order|{e[2]}'.encode('utf-8')).hexdigest())

    answer_id = OPTION_IDS[0]
    for index, (is_correct, source, text) in enumerate(entries[:OPTIONS]):
        option_id = OPTION_IDS[index]
        options.append({'id': option_id, 'text': text})
        if is_correct:
            answer_id = option_id
        else:
            # A distractor is another concept in the same course. Naming which one makes
            # the wrong answer diagnostic rather than merely wrong. ``confusion`` phrases
            # that naming in the item's own terms - a statement, a term, a description -
            # so the diagnosis reads as an answer to the question that was asked.
            confused = getattr(source, 'title', None)
            diagnoses[option_id] = {
                'category': 'conceptual',
                'reason': (confusion.format(confused=confused, title=node.title) if confused else
                           'This belongs to a different part of the course.'),
                'next_action': next_action,
            }

    return {
        'id': _question_id(course_id, node.id, variant),
        'concept_id': node.id,
        'concept_title': node.title,
        'prompt': prompt,
        'options': options,
        'kind': GENERATED_KIND,
        'generated': True,
        'expected_seconds': 45,
        'answer_id': answer_id,
        'answer_text': correct_text,
        'explanation': explanation,
        'category': category,
        'distractor_diagnoses': diagnoses,
    }


# -------------------------------------------------------------------- materialise

def question_id(course_id: str, node_id: str, variant: int) -> str:
    """The public name of :func:`_question_id`.

    The authoring layer adds items at variants 4+ for a concept the generated layer owns
    at 0-3. It must mint those ids the same way - including the truncation-and-digest
    rule for long slugs - or two different concepts could collide onto one id and one
    item would silently replace another. Exposing the function is the only way to share
    that rule without copying it.
    """
    return _question_id(course_id, node_id, variant)


def materialise(course: courses.Course) -> tuple[dict[str, dict], dict[str, dict]]:
    """Build the generated lesson and question layer for one course.

    Returns ``(concepts, questions)`` keyed by concept id and question id.
    """
    return materialise_graph(course, courses.graph_for(course.id))


def structural_items(course_id: str, node, graph, pool: list | None = None,
                     ) -> dict[str, dict[str, Any]]:
    """The four structural items for one concept, keyed by question id.

    Exposed for the authoring layer's *overlay* path. An overlay replaces a concept's
    lesson, and the old items go with it - so it has to put the structural layer back
    rather than only add its two deeper items, or a concept that had four questions
    ships with two. This is the same builders :func:`materialise_graph` uses, run for
    one node instead of a whole course; a distinct name because "materialise" would
    promise the concept entry too, and that one the overlay must not take.
    """
    pool = [n for n in graph.nodes.values()] if pool is None else pool
    items: dict[str, dict[str, Any]] = {}
    builders = (_definition_item, _term_item, _identification_item, _term_set_item)
    for variant, builder in enumerate(builders):
        item = builder(course_id, node, graph, pool)
        item['id'] = _question_id(course_id, node.id, variant)
        items[item['id']] = item
    return items


def materialise_graph(course: courses.Course, graph) -> tuple[dict[str, dict], dict[str, dict]]:
    """The same materialisation, against a graph the caller already holds.

    Split out for the authoring layer (``app.harness.authoring``), which synthesizes a
    course's graph and needs its structural items *before* the course is published -
    a preview of a course that has not been saved yet cannot resolve itself through
    ``courses.graph_for``. Nothing else changes: ``materialise`` is now this function
    with the lookup folded in, so the shipped courses and an authored one are built by
    exactly the same code.
    """
    pool = [node for node in graph.nodes.values()]
    concepts: dict[str, dict] = {}
    questions: dict[str, dict] = {}
    for node in pool:
        concepts[node.id] = _concept_entry(course.id, node, graph)
        # Four questions per concept, and every one of them about the concept: its
        # statement, its terms, and the concept behind each. None asks where the
        # concept sits in the course - see the module docstring.
        questions.update(structural_items(course.id, node, graph, pool))
    return concepts, questions


def register(target_concepts: dict, target_questions: dict,
             course_ids: Iterable[str] | None = None) -> dict[str, Any]:
    """Merge generated content for every non-authored course into the registries.

    The authored mathematics course is skipped: it already has hand-written content,
    and overwriting it would replace better material with derived material.
    """
    summary: dict[str, Any] = {}
    for spec in courses.COURSES:
        if course_ids is not None and spec.id not in set(course_ids):
            continue
        if spec.authored:
            summary[spec.id] = {'concepts': 0, 'questions': 0, 'skipped': 'authored'}
            continue
        concepts, questions = materialise(spec)
        target_concepts.update(concepts)
        target_questions.update(questions)
        summary[spec.id] = {'concepts': len(concepts), 'questions': len(questions)}
    return summary


def as_problem(item: Mapping[str, Any]):
    """View a generated multiple-choice item as a canonical :class:`Problem`.

    The generated layer and the authored layer share the same *shapes* (``CONCEPTS`` /
    ``QUESTIONS``), so a generated item - which already carries ``options``, ``answer_id``
    and ``distractor_diagnoses`` - can be lifted into the structured problem schema without
    changing how it is stored. ``format`` is fixed to ``multipleChoice``; every option that
    is not the correct one becomes a ``distractor`` whose ``mistake_type`` is taken from the
    diagnosis category the builder already records (e.g. ``"conceptual"``). ``figure_*`` /
    ``given_equation`` are left absent: generated items are derived from graph structure and
    carry no authored figure or equation, which is exactly the honest case the schema's
    optional fields describe.

    Reconstructing the object this way (rather than round-tripping through a dict) also runs
    :class:`MultipleChoiceProblem`'s ``correct_label in choices`` check, so a malformed
    generated item fails loudly instead of shipping a silently wrong answer key.
    """
    options = list(item.get('options') or [])
    correct_label = item.get('answer_id')
    diagnoses = item.get('distractor_diagnoses') or {}
    # Local import: problem_schema pulls in visual_specs through app.harness, which is a
    # heavy package that imports this module back (via curriculum.register at load time).
    # Importing it here, at call time, avoids a circular import at module import time.
    from .harness import problem as problem_schema
    choices = [problem_schema.Choice(label=o['id'], text=o.get('text')) for o in options]
    distractors = [
        problem_schema.MistakeMeta(
            mistake_type=str(diagnoses.get(o['id'], {}).get('category', 'conceptual')))
        for o in options if o['id'] != correct_label
    ]
    return problem_schema.MultipleChoiceProblem(
        stem=item['prompt'],
        explanation=item.get('explanation') or '',
        choices=choices,
        correct_label=correct_label,
        distractors=distractors,
    )


__all__ = ['GENERATED_KIND', 'VARIANTS', 'as_problem', 'materialise', 'materialise_graph',
           'question_id', 'register', 'structural_items']
