"""Grounded generation of multimodal teaching content.

This is the piece that makes the harness a harness rather than a practice app. Given a
concept and a learner, it produces the artefact that concept needs right now: an
explanation, a set of flashcards, a quiz, a slide deck, a worked example, a figure, or an
image brief.

Two design commitments.

**Retrieval is graph-shaped, not a flat vector search.** The context bundle for a concept
is assembled by walking the knowledge graph: the node itself, its prerequisite closure
(so an explanation can name what the learner must already hold), its dependants (so the
content can say where the idea leads), the authored lesson if one exists, and the
learner's own memory notes. The bundle records every citation, and every artefact carries
those citations forward.

**Deterministic first, model second.** Every artefact is fully composed without a
language model, from real curriculum structure and the symbolic maths engine. When a
provider *is* configured, the model is asked to improve the prose and the speaker notes -
never to invent the mathematics, the citations or the structure. If the model is
unavailable, misconfigured or returns nonsense, the artefact is still complete, and the
artefact says which path produced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..curriculum import CONCEPTS, GRAPH_TO_LESSON, QUESTIONS
from ..mathkit import MathSyntaxError, build as build_simulation, derivative, evaluate, parse
from ..mathkit import template_for
from . import provider, render
from .toolbox import graph_for, learner_states

#: Artefact kinds the harness can produce.
KINDS = ('explanation', 'flashcards', 'quiz', 'slide_deck', 'worked_example', 'figure',
         'image_brief', 'case_study', 'photo', 'video_lesson', 'presentation')

#: A hard ceiling. Generated items are for practice; an unbounded list is a way to bury a
#: learner, so every generator is capped and the cap is reported in the artefact.
MAX_ITEMS = 20

#: Marker for blocks whose verbatim text must never travel toward a model. OpenStax's own
#: notices prohibit ingesting their content into generative-AI offerings, so a stored
#: textbook quote is fine on a rendered lesson surface and forbidden in any payload the
#: agent loop serialises into a tool message. See :func:`redact_textbook_quotes`.
REDACT_TEXTBOOK = 'redact_textbook'

#: What the model sees in place of a redacted textbook quote. It keeps the pointer to the
#: citation so the agent can still name the source; only the verbatim text is withheld.
TEXTBOOK_REDACTED_TEXT = ('[Verbatim textbook quote withheld from model context: OpenStax '
                          'prohibits ingesting its content into generative-AI offerings. '
                          'The quote renders on the lesson surface with its citation.]')


def redact_textbook_quotes(data: Any) -> Any:
    """Return a copy of *data* with verbatim textbook quote text removed.

    Walks nested dicts and lists recursively. A block marked
    ``model_facing: REDACT_TEXTBOOK`` keeps its title (which names the section) and loses
    its verbatim text; everything else is copied unchanged. Applied to tool results in
    ``toolbox.compose_content`` -- the one surface where a composed artefact is
    serialised into a message the model reads.
    """
    if isinstance(data, Mapping):
        if data.get('model_facing') == REDACT_TEXTBOOK:
            redacted = {k: v for k, v in data.items() if k != 'model_facing'}
            redacted['text'] = TEXTBOOK_REDACTED_TEXT
            return redacted
        return {k: redact_textbook_quotes(v) for k, v in data.items()}
    if isinstance(data, list):
        return [redact_textbook_quotes(item) for item in data]
    return data


@dataclass
class Artifact:
    """A generated teaching artefact, with its provenance attached."""

    kind: str
    title: str
    concept_id: str
    blocks: list[dict[str, Any]]
    citations: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    mode: str = 'grounded-offline'
    review_required: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {'kind': self.kind, 'title': self.title, 'concept_id': self.concept_id,
                'blocks': self.blocks, 'citations': self.citations, 'notes': self.notes,
                'mode': self.mode, 'review_required': self.review_required,
                'metadata': self.metadata}


@dataclass
class Context:
    """The retrieval bundle. Everything a generator is allowed to draw on."""

    concept_id: str
    node: dict[str, Any]
    lesson: dict[str, Any] | None
    prerequisites: list[dict[str, Any]]
    dependants: list[dict[str, Any]]
    siblings: list[dict[str, Any]]
    memory_digest: str
    memory_notes: list[dict[str, Any]]
    learner_state: dict[str, Any]
    payload: dict[str, Any] | None
    citations: list[dict[str, Any]]
    textbook_cards: list[dict[str, Any]] = field(default_factory=list)

    @property
    def title(self) -> str:
        return (self.lesson or {}).get('title') or self.node.get('title', self.concept_id)

    @property
    def summary(self) -> str:
        return (self.lesson or {}).get('summary') or self.node.get('summary', '')

    def blocks_of(self, kind: str) -> list[dict[str, Any]]:
        return [b for b in (self.lesson or {}).get('blocks', []) if b.get('kind') == kind]


# ------------------------------------------------------------------ retrieval

def _node_dict(ctx, concept_id: str) -> dict[str, Any] | None:
    """Resolve a graph node id *or* an authored lesson id, within this call's graph.

    Lessons and graph nodes are separate namespaces (``fractions`` is a lesson,
    ``fraction_equivalence`` is a node). Accepting both here means a caller can ask for
    content using whichever id it already holds.
    """
    graph = graph_for(ctx)
    node = graph.nodes.get(concept_id)
    if node is None:
        from ..curriculum import LESSON_TARGETS
        target = LESSON_TARGETS.get(concept_id) or ''
        node = graph.nodes.get(target) if target else None
    return node.to_dict() if node is not None else None


def _node_citation(node: Mapping[str, Any]) -> dict[str, Any]:
    provenance = dict(node.get('provenance') or {})
    return {'kind': 'concept_node', 'id': node.get('id', ''), 'title': node.get('title', ''),
            'source': provenance.get('source', 'internal curriculum graph'),
            'url': provenance.get('url', ''),
            'licence': provenance.get('licence', 'project-authored'),
            'licence_class': provenance.get('licence_class', 'internal')}


def _lesson_citation(lesson: Mapping[str, Any]) -> dict[str, Any]:
    return {'kind': 'authored_lesson', 'id': lesson.get('id', ''), 'title': lesson.get('title', ''),
            'source': 'Project-authored curriculum', 'url': '',
            'licence': 'project-authored', 'licence_class': 'internal'}


def retrieve(ctx, concept_id: str) -> Context:
    """Assemble the grounded context for one concept. Raises ``ValueError`` if unknown."""
    graph = graph_for(ctx)
    node = _node_dict(ctx, concept_id)
    if node is None:
        raise ValueError(f'Unknown concept {concept_id!r}')
    node_id = node['id']
    lesson = CONCEPTS.get(concept_id) or CONCEPTS.get(GRAPH_TO_LESSON.get(node_id, ''))

    def brief(nid: str) -> dict[str, Any]:
        other = graph.nodes[nid]
        return {'id': nid, 'title': other.title, 'summary': other.summary,
                'unit': other.unit, 'topic': other.topic}

    prerequisites = [brief(p) for p in graph.all_parents(node_id)]
    dependants = [brief(c) for c in graph.children(node_id)]
    siblings = [brief(n.id) for n in graph.nodes.values()
                if n.unit == node['unit'] and n.id != node_id][:12]

    notes: list[dict[str, Any]] = []
    digest = 'No prior observations recorded for this learner.'
    if getattr(ctx, 'db', None) and getattr(ctx, 'user_id', ''):
        from . import memory
        related = [*graph.all_parents(node_id), *graph.children(node_id)]
        notes = [n.to_dict() for n in memory.recall(ctx.db, ctx.user_id, concept_id=node_id,
                                                    limit=8, now=getattr(ctx, 'now', 0) or None,
                                                    related=related)]
        digest = memory.digest(ctx.db, ctx.user_id, concept_id=node_id, related=related, limit=8)

    state: dict[str, Any] = {}
    if getattr(ctx, 'db', None) and getattr(ctx, 'user_id', ''):
        from ..db import State
        from sqlalchemy import select
        row = ctx.db.scalar(select(State).where(State.user_id == ctx.user_id,
                                                State.concept_id == (lesson or {}).get('id', node_id)))
        state = dict(row.data) if row else {}

    payload: dict[str, Any] | None = None
    from .. import figures
    subject_kind = getattr(ctx, 'subject_kind', '') or 'mathematics'
    try:
        payload = figures.figure_for(node, graph, learner_states(ctx), subject_kind)
    except (MathSyntaxError, ValueError, ZeroDivisionError):
        payload = None

    citations = [_node_citation(node)]
    if lesson:
        citations.append(_lesson_citation(lesson))

    # Grounded textbook layer, when one has been fetched and licence-cleared. Reads only the
    # local store, never the network, so retrieval cannot block and the licence evaluation
    # stays where it happened: at fetch time, under app.ingest.policy's fail-close gate.
    textbook_cards: list[dict[str, Any]] = []
    try:
        from ..ingest.sources import openstax as openstax_textbook
        textbook_cards = openstax_textbook.grounding(getattr(ctx, 'settings', None), concept_id)
        for card in textbook_cards:
            if card.get('status') == 'ready':
                citations.append({'kind': 'textbook', 'id': card.get('policy_name'),
                                  'title': card.get('title'), 'source': card.get('attribution'),
                                  'url': card.get('source_url'), 'licence': card.get('licence'),
                                  'licence_class': card.get('licence_class')})
    except Exception as exc:  # noqa: BLE001 - grounding must never break retrieval
        textbook_cards = [{'kind': 'reading', 'media_kind': 'textbook_section',
                           'status': 'withheld', 'quote': '',
                           'withheld_reason': f'Textbook grounding unavailable: '
                                              f'{type(exc).__name__}: {exc}'}]
    return Context(concept_id=concept_id, node=node, lesson=lesson, prerequisites=prerequisites,
                   dependants=dependants, siblings=siblings, memory_digest=digest,
                   memory_notes=notes, learner_state=state, payload=payload, citations=citations,
                   textbook_cards=textbook_cards)


# ------------------------------------------------------------------ explanation

def _explanation(ctx: Context) -> Artifact:
    blocks: list[dict[str, Any]] = [{'type': 'heading', 'level': 1, 'text': ctx.title}]
    if ctx.summary:
        blocks.append({'type': 'paragraph', 'text': ctx.summary})
    # A verbatim quote from a licence-cleared textbook section, with its citation. This is a
    # ``callout``, not a ``paragraph``, on purpose: the model-enhancement pass rewrites
    # paragraph blocks, and OpenStax's own notices prohibit ingesting their content into
    # generative-AI offerings. The quote travels only into the rendered lesson, next to its
    # source URL and licence -- and the block is marked ``model_facing: 'redact_textbook'``
    # so that every payload bound for a model (the agent loop's tool results, in
    # ``toolbox.compose_content``) carries the citation, never the verbatim text. See
    # :func:`redact_textbook_quotes`.
    for card in ctx.textbook_cards:
        if card.get('status') == 'ready' and card.get('quote'):
            blocks.append({'type': 'callout', 'tone': 'note',
                           'model_facing': REDACT_TEXTBOOK,
                           'title': f"From the textbook: {card.get('title', '')}",
                           'text': f"\u201c{card['quote']}\u201d — {card.get('attribution', '')}. "
                                   f"Source: {card.get('source_url', '')}"})
        elif card.get('status') == 'withheld' and card.get('withheld_reason'):
            blocks.append({'type': 'callout', 'tone': 'note', 'title': 'Textbook reference withheld',
                           'text': card['withheld_reason']})
    for authored in ctx.blocks_of('concept'):
        if authored.get('formula'):
            blocks.append({'type': 'formula', 'plain': authored['formula'], 'latex': ''})
        blocks.append({'type': 'paragraph', 'text': authored.get('body', '')})
    for authored in ctx.blocks_of('intuition') + ctx.blocks_of('why'):
        blocks.append({'type': 'heading', 'level': 2, 'text': authored.get('title', 'Why it works')})
        blocks.append({'type': 'paragraph', 'text': authored.get('body', '')})
    if ctx.prerequisites:
        blocks.append({'type': 'heading', 'level': 2, 'text': 'What this rests on'})
        blocks.append({'type': 'bullets', 'items': [f"{p['title']} — {p['summary']}"
                                                    for p in ctx.prerequisites[:6]]})
    if ctx.payload:
        blocks.append({'type': 'heading', 'level': 2, 'text': 'See it move'})
        blocks.append({'type': 'figure', 'payload': ctx.payload,
                       'svg': render.figure_svg(ctx.payload, title=ctx.title),
                       'caption': 'Generated by the symbolic engine. Change a parameter and '
                                  'predict the effect before you look.'})
        if ctx.payload.get('steps'):
            blocks.append({'type': 'steps', 'items': [{'index': i + 1, 'text': step}
                                                      for i, step in enumerate(ctx.payload['steps'])]})
        if ctx.payload.get('readouts'):
            blocks.append({'type': 'readouts', 'items': ctx.payload['readouts']})
    worked = ctx.blocks_of('worked_example')
    if worked:
        blocks.append({'type': 'heading', 'level': 2, 'text': 'Worked example'})
        for authored in worked:
            blocks.append({'type': 'paragraph', 'text': authored.get('body', '')})
    if ctx.dependants:
        blocks.append({'type': 'heading', 'level': 2, 'text': 'Where this leads'})
        blocks.append({'type': 'bullets', 'items': [f"{d['title']} — {d['summary']}"
                                                    for d in ctx.dependants[:5]]})
    if ctx.memory_notes:
        blocks.append({'type': 'callout', 'tone': 'memory', 'title': 'From your own record',
                       'text': '; '.join(n['text'] for n in ctx.memory_notes[:3])})
    if (ctx.lesson or {}).get('hint'):
        blocks.append({'type': 'callout', 'tone': 'note', 'title': 'Check yourself',
                       'text': ctx.lesson['hint']})
    return Artifact('explanation', f'{ctx.title} — explanation', ctx.concept_id, blocks,
                    citations=list(ctx.citations),
                    notes=['Composed from the authored lesson and the graph neighbourhood.'])


# ------------------------------------------------------------------ flashcards

def _flashcards(ctx: Context, count: int) -> Artifact:
    cards: list[dict[str, Any]] = []

    def add(front: str, back: str, tag: str) -> None:
        front = ' '.join(front.split())
        back = ' '.join(back.split())
        if front and back and len(cards) < count:
            cards.append({'front': front, 'back': back, 'tags': [tag, ctx.concept_id]})

    add(f'What is {ctx.title}?', ctx.summary, 'definition')
    for authored in ctx.blocks_of('concept'):
        body = authored.get('body', '')
        if body:
            add(authored.get('title', ctx.title), body, 'idea')
        if authored.get('formula'):
            add(f"Write the relationship for {ctx.title.lower()}.", authored['formula'], 'formula')
    for authored in ctx.blocks_of('worked_example')[:2]:
        add(f"{authored.get('title', 'Worked example')} — what is the method?",
            authored.get('body', ''), 'method')
    for prerequisite in ctx.prerequisites[:3]:
        add(f'Which idea does {ctx.title.lower()} build on, and how?',
            f"{prerequisite['title']}: {prerequisite['summary']}", 'prerequisite')
    for dependant in ctx.dependants[:2]:
        add(f'What does {ctx.title.lower()} make possible?',
            f"{dependant['title']}: {dependant['summary']}", 'transfer')
    # A curve payload carries ``features`` as a mapping; a concept map carries it as an
    # empty list. Testing the shape rather than assuming it is what keeps one subject's
    # artefact from crashing on another subject's figure.
    features = ctx.payload.get('features') if ctx.payload else None
    expression = (ctx.payload or {}).get('expression') or {}
    if isinstance(features, Mapping) and features.get('roots') and expression.get('substituted'):
        roots = ', '.join(str(r) for r in features['roots'][:4])
        add(f'Where does {expression["substituted"]} cross zero?', roots, 'graph')
    for note in ctx.memory_notes[:2]:
        add('Something you got wrong before — what was it?', note['text'], 'personal')
    return Artifact('flashcards', f'{ctx.title} — {len(cards)} cards', ctx.concept_id,
                    [{'type': 'cards', 'items': cards}], citations=list(ctx.citations),
                    notes=[f'{len(cards)} cards, capped at {count}.',
                           'Retrieval practice beats re-reading; answer before you flip.'])


# ------------------------------------------------------------------ quiz

def _sample_points(payload: Mapping[str, Any]) -> list[float]:
    """Three interior sample points. Interior on purpose: an endpoint is often a boundary
    artefact of the window rather than a value the concept is about."""
    domain = payload.get('domain') or {}
    if isinstance(domain, Mapping):
        low, high = float(domain.get('min', -5.0)), float(domain.get('max', 5.0))
    else:
        low, high = float(domain[0]), float(domain[-1])
    span = high - low
    return [round(low + span * fraction, 4) for fraction in (0.25, 0.5, 0.75)]


def _numeric_items(ctx: Context, count: int) -> list[dict[str, Any]]:
    """Generate evaluation and root items, with each distractor naming its error process.

    Only function-shaped concepts qualify. A fraction bar or a dot plot has no
    "evaluate at x" question, and inventing one would be worse than generating nothing.
    """
    payload = ctx.payload
    if not payload or payload.get('figure') != 'curve':
        return []
    expression = (payload.get('expression') or {}).get('substituted', '')
    variable = (payload.get('variable') or 'x')
    try:
        tree = parse(expression, variables=(variable,))
    except MathSyntaxError:
        return []
    items: list[dict[str, Any]] = []

    for point in _sample_points(payload):
        if len(items) >= count:
            break
        try:
            answer = evaluate(tree, {variable: point})
            mirrored = evaluate(tree, {variable: -point})
            slope = evaluate(derivative(tree, variable), {variable: point})
        except (MathSyntaxError, ValueError, ZeroDivisionError, OverflowError):
            continue
        if not all(isinstance(v, (int, float)) and abs(v) < 1e6 for v in (answer, mirrored, slope)):
            continue
        options = [
            {'value': answer, 'text': _round_text(answer), 'correct': True,
             'error_process': ''},
            {'value': mirrored, 'text': _round_text(mirrored),
             'error_process': 'Sign error on the input: substitutes the opposite value of x.'},
            {'value': slope, 'text': _round_text(slope),
             'error_process': 'Reports the rate of change where the value was asked for.'},
            {'value': -answer, 'text': _round_text(-answer),
             'error_process': 'Sign error on the output: drops or flips the sign of the result.'},
        ]
        items.append(_assemble_item(
            item_id=f'gen-eval-{ctx.node["id"]}-{_round_text(point).replace(".", "_")}',
            stem=f'Evaluate {expression} at {variable} = {_round_text(point)}.',
            options=options,
            explanation=(f'Substitute {variable} = {_round_text(point)} and compute in order of '
                         f'operations: the value is {_round_text(answer)}.'),
            concept_id=ctx.concept_id))

    roots = (payload.get('features') or {}).get('roots') or []
    if roots and len(items) < count and len(roots) <= 2:
        root = float(roots[0])
        options = [
            {'value': root, 'text': _round_text(root), 'correct': True, 'error_process': ''},
            {'value': -root, 'text': _round_text(-root),
             'error_process': 'Sign error when solving: moves the constant without changing its sign.'},
            {'value': root + 1, 'text': _round_text(root + 1),
             'error_process': 'Arithmetic slip in the final inverse operation.'},
            {'value': 0.0, 'text': '0',
             'error_process': 'Confuses the root with the y-intercept at x = 0.'},
        ]
        items.append(_assemble_item(
            item_id=f'gen-root-{ctx.node["id"]}',
            stem=f'For which {variable} does {expression} equal zero?',
            options=options,
            explanation=f'Setting the expression to zero and solving gives {variable} = {_round_text(root)}.',
            concept_id=ctx.concept_id))
    return items[:count]


def _round_text(value: float) -> str:
    if value is None:
        return ''
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f'{value:.4g}'


def _assemble_item(*, item_id: str, stem: str, options: list[dict[str, Any]], explanation: str,
                   concept_id: str) -> dict[str, Any]:
    """Turn a candidate option set into a well-formed item, or refuse to."""
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for option in options:
        text = option['text']
        if text in seen:
            continue
        seen.add(text)
        deduped.append(option)
    if not any(o.get('correct') for o in deduped) or len(deduped) < 3:
        return {}
    labels = 'abcd'
    rendered = []
    answer_id = ''
    for index, option in enumerate(deduped[:4]):
        label = labels[index]
        rendered.append({'id': label, 'text': option['text']})
        if option.get('correct'):
            answer_id = label
    processes = {labels[index]: {'category': 'generated',
                                 'reason': option.get('error_process', ''),
                                 'next_action': 'Cross-check the same step on a fresh variant.'}
                 for index, option in enumerate(deduped[:4]) if option.get('error_process')}
    return {'id': item_id, 'kind': 'multiple_choice', 'concept_id': concept_id, 'stem': stem,
            'options': rendered, 'answer_id': answer_id, 'explanation': explanation,
            'error_processes': processes, 'origin': 'generated',
            'review_required': True,
            'expected_seconds': 75}


def _concept_items(ctx: Context, count: int) -> list[dict[str, Any]]:
    """Recognition items whose distractors are neighbouring concepts in the same unit."""
    if len(ctx.siblings) < 3:
        return []
    options = [{'text': ctx.summary, 'correct': True, 'error_process': ''}]
    for sibling in ctx.siblings[:3]:
        options.append({'text': sibling['summary'],
                        'error_process': f"Confuses this with {sibling['title']}, a neighbouring "
                                         f'idea in the same unit.'})
    item = _assemble_item(
        item_id=f'gen-concept-{ctx.node["id"]}',
        stem=f'Which statement describes {ctx.title}?',
        options=options,
        explanation=f'{ctx.title}: {ctx.summary}',
        concept_id=ctx.concept_id)
    return [item] if item else []


def _quiz(ctx: Context, count: int) -> Artifact:
    lesson_id = (ctx.lesson or {}).get('id', ctx.concept_id)
    authored = [q for q in QUESTIONS.values() if q['concept_id'] == lesson_id]
    items: list[dict[str, Any]] = []
    for question in authored:
        items.append({'id': question['id'], 'kind': question['kind'], 'concept_id': lesson_id,
                      'stem': question['prompt'], 'options': question['options'],
                      'answer_id': question['answer_id'], 'explanation': question['explanation'],
                      'error_processes': question.get('distractor_diagnoses', {}),
                      'origin': 'authored', 'review_required': False,
                      'expected_seconds': question['expected_seconds']})
    generated = _numeric_items(ctx, max(0, count - len(items)))
    generated.extend(_concept_items(ctx, max(0, count - len(items) - len(generated))))
    items.extend([item for item in generated if item])
    items = items[:count]
    notes = [f'{len(items)} items: {sum(1 for i in items if i["origin"] == "authored")} authored, '
             f'{sum(1 for i in items if i["origin"] == "generated")} generated.']
    if any(i['origin'] == 'generated' for i in items):
        notes.append('Generated items carry the error process each distractor represents, and are '
                     'flagged review_required: a distractor is only useful if it is a real mistake, '
                     'and that claim is a hypothesis until a teacher or response data confirms it.')
    return Artifact('quiz', f'{ctx.title} — {len(items)} items', ctx.concept_id,
                    [{'type': 'quiz', 'items': items}], citations=list(ctx.citations),
                    notes=notes, review_required=any(i['origin'] == 'generated' for i in items),
                    metadata={'authored': sum(1 for i in items if i['origin'] == 'authored'),
                              'generated': sum(1 for i in items if i['origin'] == 'generated')})


# ------------------------------------------------------------------ deck

def _slide_deck(ctx: Context, options: Mapping[str, Any]) -> Artifact:
    deck: list[dict[str, Any]] = []
    payload = ctx.payload

    deck.append({'layout': 'title', 'title': ctx.title,
                 'subtitle': ctx.summary[:140],
                 'bullets': [], 'speaker_notes':
                 f'Open by asking what the learner already expects. {ctx.memory_digest[:220]}'})

    core = ctx.blocks_of('concept')
    if core:
        deck.append({'layout': 'idea', 'title': core[0].get('title', 'The core idea'),
                     'bullets': [core[0].get('body', '')[:220]],
                     'formula': core[0].get('formula', ''),
                     'speaker_notes': 'Say it once plainly, then have the learner restate it.'})
    if ctx.prerequisites:
        deck.append({'layout': 'bullets', 'title': 'What it rests on',
                     'bullets': [f"{p['title']}: {p['summary'][:110]}" for p in ctx.prerequisites[:4]],
                     'speaker_notes': 'If any of these is shaky, fix it here rather than later.'})
    if payload:
        deck.append({'layout': 'figure', 'title': 'See it move',
                     'bullets': [s[:150] for s in (payload.get('steps') or [])[:3]],
                     'figure': payload, 'figure_svg': render.figure_svg(payload, title=ctx.title),
                     'speaker_notes': 'Predict first, then change one parameter and compare.'})
    worked = ctx.blocks_of('worked_example')
    if worked:
        deck.append({'layout': 'worked', 'title': worked[0].get('title', 'Worked example'),
                     'bullets': [worked[0].get('body', '')[:260]],
                     'speaker_notes': 'Narrate the decision at each step, not just the algebra.'})
    for authored in ctx.blocks_of('pitfall') + ctx.blocks_of('misconception'):
        deck.append({'layout': 'callout', 'title': authored.get('title', 'A common slip'),
                     'bullets': [authored.get('body', '')[:220]],
                     'speaker_notes': 'Name the error process explicitly.'})
    if ctx.memory_notes:
        deck.append({'layout': 'callout', 'title': 'From your own record',
                     'bullets': [n['text'][:150] for n in ctx.memory_notes[:3]],
                     'speaker_notes': 'Personalised from recorded evidence, not a diagnosis.'})
    if ctx.dependants:
        deck.append({'layout': 'bullets', 'title': 'Where this leads',
                     'bullets': [f"{d['title']}: {d['summary'][:110]}" for d in ctx.dependants[:4]],
                     'speaker_notes': 'Motivation: show the learner the door this opens.'})
    lesson_id = (ctx.lesson or {}).get('id', ctx.concept_id)
    check = next((q for q in QUESTIONS.values() if q['concept_id'] == lesson_id), None)
    if check:
        deck.append({'layout': 'check', 'title': 'Check yourself',
                     'bullets': [check['prompt']] + [f"{o['id']}. {o['text']}" for o in check['options']],
                     'answer_id': check['answer_id'],
                     'speaker_notes': 'Withhold the answer until the learner commits.'})
    deck.append({'layout': 'close', 'title': 'Next step',
                 'bullets': [(ctx.lesson or {}).get('hint', 'Explain the method on a fresh variant.')],
                 'speaker_notes': 'End with a retrieval question, not a summary.'})

    blocks = [{'type': 'slides', 'slides': deck}]
    if options.get('include_svg_preview'):
        blocks.append({'type': 'figure', 'payload': payload or {},
                       'svg': render.deck_svg(deck[0], figure=payload), 'caption': 'Title slide'})
    return Artifact('slide_deck', f'{ctx.title} — {len(deck)} slides', ctx.concept_id, blocks,
                    citations=list(ctx.citations),
                    notes=[f'{len(deck)} slides with speaker notes.',
                           'Figures are the same payloads the app draws, so a printed slide and '
                           'the on-screen figure cannot disagree.'])


# ------------------------------------------------------------------ others

def _worked_example(ctx: Context) -> Artifact:
    blocks: list[dict[str, Any]] = [{'type': 'heading', 'level': 1, 'text': f'{ctx.title}: worked through'}]
    for authored in ctx.blocks_of('worked_example'):
        blocks.append({'type': 'paragraph', 'text': authored.get('body', '')})
    payload = ctx.payload
    if payload:
        blocks.append({'type': 'figure', 'payload': payload,
                       'svg': render.figure_svg(payload, title=ctx.title),
                       'caption': payload.get('objective', '')})
        if payload.get('steps'):
            blocks.append({'type': 'steps', 'items': [{'index': i + 1, 'text': step}
                                                      for i, step in enumerate(payload['steps'])]})
        if payload.get('readouts'):
            blocks.append({'type': 'readouts', 'items': payload['readouts']})
        if payload.get('table'):
            blocks.append({'type': 'table', 'columns': ['x', 'value'], 'rows': payload['table']})
    if not payload and not ctx.blocks_of('worked_example'):
        blocks.append({'type': 'paragraph',
                       'text': 'This concept is defined rather than computed, so the worked step is '
                               'the definition itself: state it, then instantiate it on an example.'})
    return Artifact('worked_example', f'{ctx.title} — worked example', ctx.concept_id, blocks,
                    citations=list(ctx.citations))


def _figure(ctx: Context) -> Artifact:
    if not ctx.payload:
        raise ValueError(f'No figure template applies to {ctx.concept_id!r}')
    svg = render.figure_svg(ctx.payload, title=ctx.title)
    return Artifact('figure', f'{ctx.title} — figure', ctx.concept_id,
                    [{'type': 'figure', 'payload': ctx.payload, 'svg': svg,
                      'caption': ctx.payload.get('objective', '')}],
                    citations=list(ctx.citations),
                    notes=['Rendered from the same payload the app draws.'])


def _image_brief(ctx: Context) -> Artifact:
    """A brief for an illustration, with a deterministic fallback that needs no model."""
    must_show = [ctx.summary[:200]] if ctx.summary else []
    if ctx.payload and ctx.payload.get('figure') == 'scene':
        must_show.append('A part-whole diagram whose parts are visibly equal in size.')
    if ctx.payload and ctx.payload.get('figure') == 'curve':
        must_show.append('A labelled set of axes with the curve, its zero crossings and one '
                         'annotated point.')
    brief = {
        'prompt': f'A clear, uncluttered instructional illustration for {ctx.title}. '
                  f'Show {ctx.summary[:160]} No text labels other than axis numbers.',
        'must_show': must_show,
        'must_avoid': ['brand marks', 'photorealistic people', 'text that duplicates the '
                       'explanation', 'decorative clutter that competes with the figure'],
        'alt_text': f'Diagram illustrating {ctx.title}: {ctx.summary[:140]}',
        'fallback_svg': render.figure_svg(ctx.payload, title=ctx.title) if ctx.payload else '',
        'requires_api': 'image-generation-api',
    }
    return Artifact('image_brief', f'{ctx.title} — illustration brief', ctx.concept_id,
                    [{'type': 'paragraph', 'text': brief['prompt']},
                     {'type': 'bullets', 'items': brief['must_show']},
                     {'type': 'callout', 'tone': 'warning', 'title': 'Must avoid',
                      'text': '; '.join(brief['must_avoid'])}]
                    + ([{'type': 'figure', 'payload': ctx.payload, 'svg': brief['fallback_svg'],
                         'caption': 'Deterministic fallback, available with no external service.'}]
                       if brief['fallback_svg'] else []),
                    citations=list(ctx.citations), metadata=brief,
                    notes=['The deterministic figure above is always available. Generating a '
                           'photographic or illustrative image needs an image API; until then '
                           'the brief is the deliverable.'])


def _case_study(ctx: Context, ctx_tool) -> Artifact:
    from . import toolbox
    result = toolbox.prepare_case_study(ctx_tool, ctx.concept_id)
    if not result.ok:
        raise ValueError(result.error or 'Case study could not be prepared')
    study = result.data
    blocks: list[dict[str, Any]] = [
        {'type': 'heading', 'level': 1, 'text': study['title']},
        {'type': 'paragraph', 'text': study['setting']},
    ]
    if study['core_idea']:
        blocks.append({'type': 'paragraph', 'text': study['core_idea']})
    if study['formula']:
        blocks.append({'type': 'formula', 'plain': study['formula'], 'latex': ''})
    blocks.append({'type': 'heading', 'level': 2, 'text': 'Your tasks'})
    blocks.append({'type': 'steps', 'items': [{'index': i + 1, 'text': t['prompt']}
                                              for i, t in enumerate(study['tasks'])]})
    blocks.append({'type': 'heading', 'level': 2, 'text': 'What a strong answer shows'})
    blocks.append({'type': 'bullets', 'items': [t['looks_for'] for t in study['tasks']]})
    if study['rubric']:
        blocks.append({'type': 'bullets', 'items': list(study['rubric'])})
    if study['extension']:
        blocks.append({'type': 'callout', 'tone': 'note', 'title': 'Push further',
                       'text': study['extension']})
    return Artifact('case_study', study['title'], ctx.concept_id, blocks,
                    citations=result.citations, notes=result.notes)


# ------------------------------------------------------------------ photograph

def _photo(ctx: Context, ctx_tool, options: Mapping[str, Any]) -> Artifact:
    """A real, licence-cleared photograph for this concept, or an honest refusal.

    The licence-clean path is the whole point, so this never falls back to an unlicensed
    image. When nothing clears the gate the artefact still renders - it carries the reason
    and the deterministic figure the app already draws, because a lesson that cannot get a
    photograph must not become a lesson that cannot run.
    """
    from . import media as media_pipeline
    settings = getattr(ctx_tool, 'settings', None)
    blocks: list[dict[str, Any]] = [{'type': 'heading', 'level': 1, 'text': f'{ctx.title} — image'}]
    if settings is None:
        return Artifact('photo', f'{ctx.title} — image', ctx.concept_id,
                        blocks + [{'type': 'callout', 'tone': 'note', 'title': 'No settings bound',
                                   'text': 'No media configuration is bound to this call, so no '
                                           'image was searched for.'}],
                        citations=list(ctx.citations))

    found = media_pipeline.find_image(
        settings, ctx.title, summary=ctx.summary,
        alt_text=f'Photograph illustrating {ctx.title}: {ctx.summary[:140]}')
    notes = list(found.get('notes') or [])
    if found.get('asset'):
        asset = found['asset']
        blocks.append(asset_block(asset, caption=ctx.summary[:200]))
        blocks.append({'type': 'callout', 'tone': 'note', 'title': 'Why this is allowed',
                       'text': f"{asset.get('licence_code')} "
                               f"({asset.get('licence_class')}). {asset.get('attribution_text')}"})
        citations = [*ctx.citations, {'kind': 'image', 'id': asset.get('source_id'),
                                      'title': asset.get('title'),
                                      'source': asset.get('source'),
                                      'url': asset.get('landing_page_url'),
                                      'licence': asset.get('licence_code'),
                                      'licence_class': asset.get('licence_class')}]
        metadata = {'asset': asset, 'outcome': found.get('outcome'),
                    'seen': found.get('seen'), 'accepted': found.get('accepted')}
    else:
        citations = list(ctx.citations)
        metadata = {'outcome': found.get('outcome'), 'seen': found.get('seen'),
                    'accepted': found.get('accepted'), 'rejections': found.get('rejections')}
        blocks.append({'type': 'callout', 'tone': 'note', 'title': 'No image was added',
                       'text': f"No photograph cleared the licence gate and the relevance filter "
                               f"({found.get('outcome')}). Nothing was downloaded and no image is "
                               f"claimed for this concept."})
        if found.get('rejections'):
            blocks.append({'type': 'bullets',
                           'items': [f"{r['source']}: {r['title']} — {r['why']}"
                                     for r in found['rejections'][:5]]})
        if ctx.payload:
            blocks.append({'type': 'figure', 'payload': ctx.payload,
                           'svg': render.figure_svg(ctx.payload, title=ctx.title),
                           'caption': 'The deterministic figure remains available with no network '
                                      'at all.'})
    return Artifact('photo', f'{ctx.title} — image', ctx.concept_id, blocks,
                    citations=citations, notes=notes, metadata=metadata)


def asset_block(asset: Mapping[str, Any], *, caption: str = '') -> dict[str, Any]:
    """One image block, in the single shape every renderer reads."""
    return {
        'type': 'image', 'kind': 'photograph', 'src': asset.get('cache_path'),
        'cached': True, 'title': asset.get('title'), 'alt': asset.get('alt_text'),
        'caption': caption or str(asset.get('description') or '')[:200],
        'credit': asset.get('attribution_text'), 'licence': asset.get('licence_code'),
        'licence_class': asset.get('licence_class'), 'licence_url': asset.get('licence_url'),
        'source': asset.get('source'), 'source_url': asset.get('landing_page_url'),
        'creator': asset.get('creator'), 'width': asset.get('width'),
        'height': asset.get('height'), 'sha256': asset.get('sha256'),
    }


# ------------------------------------------------------------------ video lesson

def _video_lesson(ctx: Context, ctx_tool, options: Mapping[str, Any]) -> Artifact:
    """Curated video for this concept, verified for embeddability, never downloaded."""
    from . import video as video_pipeline
    settings = getattr(ctx_tool, 'settings', None)
    course_id = str(options.get('course_id') or getattr(ctx_tool, 'course_id', '') or '')
    blocks: list[dict[str, Any]] = [
        {'type': 'heading', 'level': 1, 'text': f'{ctx.title} — video'},
        {'type': 'paragraph',
         'text': 'Video is embedded through the provider\'s own player. Nothing is downloaded, '
                 're-encoded or re-hosted, and captions and transcripts are never fetched.'},
    ]
    citations = list(ctx.citations)
    if settings is None or not course_id:
        blocks.append({'type': 'callout', 'tone': 'note', 'title': 'No course bound',
                       'text': 'Video curation is keyed by course, and no course is bound to this '
                               'call.'})
        return Artifact('video_lesson', f'{ctx.title} — video', ctx.concept_id, blocks,
                        citations=citations, metadata={'videos': []})
    cards = video_pipeline.resolve(settings, course_id, ctx.concept_id)
    if not cards:
        blocks.append({'type': 'callout', 'tone': 'note', 'title': 'Nothing curated yet',
                       'text': 'No video is curated for this concept. A search is not run here on '
                               'purpose: an automatic search spends API quota and surfaces '
                               'whatever the ranking returns, so curation is an operator step.'})
    for card in cards:
        blocks.append({'type': 'media', 'media': card})
        if card.get('notice'):
            blocks.append({'type': 'callout', 'tone': 'note', 'title': 'Required notice',
                           'text': card['notice']})
        if card.get('withheld_reason'):
            blocks.append({'type': 'callout', 'tone': 'warning', 'title': 'Withheld',
                           'text': card['withheld_reason']})
        citations.append({'kind': 'video', 'id': card.get('provider'),
                          'title': card.get('title'), 'source': card.get('channel'),
                          'url': card.get('watch_url'), 'licence': card.get('licence'),
                          'licence_class': card.get('licence_class')})
    return Artifact('video_lesson', f'{ctx.title} — video', ctx.concept_id, blocks,
                    citations=citations, metadata={'videos': cards})


# ------------------------------------------------------------------ presentation

def _presentation(ctx_tool, concept_id: str, options: Mapping[str, Any]) -> Artifact:
    """The narrated deck, as an artefact. The render itself lives in the presentation module."""
    from . import presentation
    deck = presentation.compose(ctx_tool, concept_id, options)
    blocks: list[dict[str, Any]] = [
        {'type': 'heading', 'level': 1, 'text': deck['title']},
        {'type': 'paragraph',
         'text': f"{len(deck['slides'])} slides, {deck['total_seconds']:.0f} seconds of estimated "
                 f"narration. Single narrator; each slide's duration is its narration length plus "
                 f"a {presentation.SLIDE_PAD_SECONDS}s pad."},
    ]
    for slide in deck['slides']:
        blocks.append({'type': 'slide', 'slide': slide})
    blocks.append({'type': 'callout', 'tone': 'note', 'title': 'How this was assembled',
                   'text': '; '.join(f'{k}: {v}' for k, v in deck['method'].items())})
    artifact = Artifact('presentation', deck['title'], concept_id, blocks,
                        citations=deck['citations'], notes=deck['notes'], mode=deck['mode'],
                        metadata={'slides': deck['slides'], 'total_seconds': deck['total_seconds'],
                                  'method': deck['method'], 'vtt': deck['vtt']})
    if options.get('include_html', True):
        artifact.metadata['html'] = deck['html']
    return artifact



# ------------------------------------------------------------------ dispatch

def compose(ctx_tool, concept_id: str, kind: str, options: Mapping[str, Any] | None = None) -> Artifact:
    """Generate one artefact. The single entry point the toolbox calls."""
    options = dict(options or {})
    if kind not in KINDS:
        raise ValueError(f'Unknown artefact kind {kind!r}; available: {", ".join(KINDS)}')
    count = max(1, min(MAX_ITEMS, int(options.get('count', 8) or 8)))
    # A presentation owns its own retrieval because it needs the context object to build the
    # script, so it is dispatched before the shared context is built.
    if kind == 'presentation':
        return _enhance(ctx_tool, None, _presentation(ctx_tool, concept_id, options), options)
    context = retrieve(ctx_tool, concept_id)
    if kind == 'explanation':
        artifact = _explanation(context)
    elif kind == 'flashcards':
        artifact = _flashcards(context, count)
    elif kind == 'quiz':
        artifact = _quiz(context, count)
    elif kind == 'slide_deck':
        artifact = _slide_deck(context, options)
    elif kind == 'worked_example':
        artifact = _worked_example(context)
    elif kind == 'figure':
        artifact = _figure(context)
    elif kind == 'image_brief':
        artifact = _image_brief(context)
    elif kind == 'photo':
        artifact = _photo(context, ctx_tool, options)
    elif kind == 'video_lesson':
        artifact = _video_lesson(context, ctx_tool, options)
    else:
        artifact = _case_study(context, ctx_tool)
    return _enhance(ctx_tool, context, artifact, options)


def _enhance(ctx_tool, context: Context | None, artifact: Artifact,
             options: Mapping[str, Any]) -> Artifact:
    """Let a configured model improve the prose. Never let it invent the mathematics."""
    settings = getattr(ctx_tool, 'settings', None)
    if not provider.available(settings) or options.get('no_model'):
        artifact.notes.append('Composed deterministically; no language model was used.')
        return artifact
    if artifact.kind not in {'explanation', 'slide_deck', 'worked_example'} or context is None:
        artifact.mode = provider.label(settings)
        artifact.notes.append('Structured artefact: the model is not asked to rewrite items, '
                              'figures or citations.')
        return artifact
    paragraphs = [b['text'] for b in artifact.blocks if b.get('type') == 'paragraph']
    if not paragraphs:
        artifact.mode = provider.label(settings)
        return artifact
    system = ('You are editing teaching prose for a mathematics harness. You may only clarify and '
              'tighten the supplied text. You must not add new mathematical claims, new examples, '
              'new numbers or new sources. Keep every formula exactly as written. Return a JSON '
              'array of strings, one per supplied paragraph, in the same order, same length or '
              'shorter. If you cannot improve a paragraph, return it unchanged.')
    user = ('Concept: ' + context.title + '\n\nParagraphs:\n'
            + '\n'.join(f'[{i}] {p}' for i, p in enumerate(paragraphs)))
    improved = provider.chat_json(settings, [{'role': 'system', 'content': system},
                                            {'role': 'user', 'content': user}], max_tokens=1400)
    if isinstance(improved, list) and len(improved) == len(paragraphs) and all(
            isinstance(item, str) and item.strip() for item in improved):
        cursor = 0
        for block in artifact.blocks:
            if block.get('type') == 'paragraph':
                block['text'] = improved[cursor].strip()[:4000]
                cursor += 1
        artifact.mode = provider.label(settings)
        artifact.notes.append('Prose clarified by the configured model; formulas, figures, '
                              'citations and item content were not modified.')
    else:
        artifact.mode = 'grounded-offline'
        artifact.notes.append('The configured model was unavailable or returned unusable output; '
                              'the deterministic composition was kept.')
    return artifact


def catalogue() -> list[dict[str, Any]]:
    return [
        {'kind': 'explanation', 'summary': 'A grounded explanation with the figure and the steps.',
         'options': ['no_model']},
        {'kind': 'flashcards', 'summary': 'Retrieval cards, including cards built from the '
                                          'learner\'s own recorded mistakes.', 'options': ['count']},
        {'kind': 'quiz', 'summary': 'Authored items first, then generated items whose distractors '
                                    'each name an error process.', 'options': ['count']},
        {'kind': 'slide_deck', 'summary': 'A deck with speaker notes and the concept figure.',
         'options': ['include_svg_preview']},
        {'kind': 'worked_example', 'summary': 'Step-by-step method with the live readouts.',
         'options': []},
        {'kind': 'figure', 'summary': 'The interactive figure payload plus a printable SVG.',
         'options': []},
        {'kind': 'image_brief', 'summary': 'A structured illustration brief with a deterministic '
                                           'SVG fallback.', 'options': []},
        {'kind': 'case_study', 'summary': 'An applied case with tasks and a rubric.',
         'options': []},
        {'kind': 'photo', 'summary': 'A real photograph from an open image API, downloaded only '
                                     'when its own licence permits it, with the attribution '
                                     'stored and shown. Falls back to the deterministic figure '
                                     'with a stated reason.',
         'options': ['count']},
        {'kind': 'video_lesson', 'summary': 'Curated video for this concept, embedded through '
                                            'the provider\'s own player after an embeddability '
                                            'check. Nothing is downloaded or transcribed.',
         'options': ['course_id']},
        {'kind': 'presentation', 'summary': 'A narrated slide deck: single narrator, one visual '
                                            'per slide, audio-led timing, a WebVTT track and a '
                                            'self-contained HTML render.',
         'options': ['include_html', 'include_image', 'include_simulation', 'include_check',
                     'course_id', 'course_label', 'no_model']},
    ]
