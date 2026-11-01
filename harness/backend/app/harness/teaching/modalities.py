"""Multimodal move selection: *how* a concept is taught, grounded in evidence.

The harness prompt already promises multimodality; this module decides it. The
choice is deliberately not decorative. Every rule below states the evidence that
fires it and the reason that channel teaches that concept type, because a channel
picked for variety rather than fit is decoration with a tool call attached.

Three properties hold throughout:

* **Grounding over preference.** The non-mathematics case routes to a concept map
  because the symbolic engine is valid only for mathematics (the same constraint
  the prompt's grounding rule 6 states) - a plotted function for a physics concept
  would present a concept map as a physical model. Channels the instance cannot
  honour (network media disabled, no course binding) fall back rather than pretend.
* **Difficulty-aware.** A conceptual error and a procedural error want different
  representations: structure made visible (draw it) versus process made watchable
  (run it). Mastery bands pick the same channel differently - a learner near
  consolidation gets to draw it themselves; a learner mid-progress gets to watch it
  move.
* **Variety-bounded.** Repeating the previous modality is penalised per the
  profile's ``variety_penalty``, so the teacher does not explain four concepts in a
  row with four whiteboards - but variety never overrides a fit rule.

Tool calls below name tools that already exist in ``app.harness.toolbox``. Nothing
here invents a tool: an action the registry cannot perform is a refusal the caller
must surface, not a new capability smuggled in through the teacher.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .evidence import ConceptFacts, LearnerEvidence

#: The channels the router may choose between. Kept in sync with
#: ``TeacherProfile.modalities.allowed`` - the profile is the ceiling, this is the
#: catalogue of channels the rules know how to justify.
MODALITIES = ('text', 'figure', 'whiteboard', 'simulation', 'image', 'video',
              'audio', 'concept_map')

#: Placeholders a plan fills from its call site; the router cannot know a board id
#: or a course binding, so it emits the contract and the session resolves it.
BOARD_PLACEHOLDER = '{board_id}'
COURSE_PLACEHOLDER = '{course_id}'


@dataclass(frozen=True)
class ToolCall:
    """One registry call a modality implies, with the reason it is needed."""

    tool: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    why: str = ''

    def resolved(self, *, board_id: str = '', course_id: str = '') -> tuple[str, dict]:
        """Substitute the placeholders the router had to leave open.

        Resolution is explicit rather than magic so a caller that cannot fill a
        placeholder (no board id) sees the unresolved value and the tool refuses -
        a silent empty string would draw on a board nobody named.
        """
        args = {}
        for key, value in self.arguments.items():
            if value == BOARD_PLACEHOLDER:
                args[key] = board_id
            elif value == COURSE_PLACEHOLDER:
                args[key] = course_id
            else:
                args[key] = value
        return self.tool, args

    def to_dict(self) -> dict[str, Any]:
        return {'tool': self.tool, 'arguments': dict(self.arguments), 'why': self.why}


@dataclass(frozen=True)
class ModalityChoice:
    """The chosen channel, its justification, and the calls that deliver it."""

    modality: str
    why: str
    tools: tuple[ToolCall, ...] = ()
    fallback: tuple[ToolCall, ...] = ()
    needs_teacher: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {'modality': self.modality, 'why': self.why,
                'tools': [t.to_dict() for t in self.tools],
                'fallback': [t.to_dict() for t in self.fallback],
                'needs_teacher': self.needs_teacher}


def _figure_call(concept_id: str) -> ToolCall:
    """The grounded figure: a function plot for mathematics, a concept map
    otherwise - the toolbox's build_figure makes exactly this dispatch."""
    return ToolCall('build_figure', {'concept_id': concept_id},
                    'The generated figure for this concept (function plot for '
                    'mathematics; prerequisite-derived concept map otherwise).')


def _simulation_call(concept_id: str) -> ToolCall:
    return ToolCall('find_simulation', {'concept_id': concept_id,
                                        'course_id': COURSE_PLACEHOLDER},
                    'A course-bound interactive simulation, when the course has '
                    'one; otherwise the figure fallback runs.')


def _whiteboard_call(concept_id: str, intent: str) -> ToolCall:
    return ToolCall('whiteboard_apply', {'board_id': BOARD_PLACEHOLDER,
                                         'intent': intent},
                    'Draw on the shared Stage board so the structure is visible '
                    'while it is discussed.')


def _video_call(concept_id: str) -> ToolCall:
    """Video is offered as a link/embed through the licence-gated search, never as
    ingested text - curriculum video media is embed-only for most sources."""
    return ToolCall('find_video', {'concept_id': concept_id,
                                   'course_id': COURSE_PLACEHOLDER},
                    'A curated video for this concept, offered as an embed/link '
                    'under its licence, never as ingested content.')


def _image_call(concept_id: str, query: str) -> ToolCall:
    return ToolCall('find_image', {'concept_id': concept_id, 'query': query},
                    'A licence-cleared image acquired through the media pipeline; '
                    'a withheld result stays withheld.')


def _audio_call(text: str) -> ToolCall:
    return ToolCall('text_to_speech', {'text': text},
                    'Speak the explanation alongside the text, so the channel '
                    'serves learners who asked for audio without replacing it.')


def choose_modality(facts: ConceptFacts, evidence: LearnerEvidence, profile,
                    *, last_modality: str = '', board_id: str = '',
                    course_id: str = '', media_enabled: bool = False) -> ModalityChoice:
    """Choose the teaching channel for one concept for one learner, right now.

    Two passes. :func:`_route` runs the fit rules - the channel that *teaches* this
    concept type for this evidence. :func:`_within_ceiling` then enforces the
    profile's ``allowed`` list on whatever the rules produced.

    The second pass exists because the rules cannot each police the ceiling
    themselves. They are written to answer "what teaches this", and a rule that also
    had to remember what the operator switched off would eventually forget: rules 1,
    2, 3 and 5 all name a channel directly (concept map, simulation, whiteboard) and
    none of them consulted ``allowed``. So ``allowed`` was documented as a ceiling
    that did not exist, and a text-only instance still drew on the board.
    """
    choice = _route(facts, evidence, profile, last_modality=last_modality,
                    board_id=board_id, course_id=course_id,
                    media_enabled=media_enabled)
    return _within_ceiling(choice, profile, facts, media_enabled=media_enabled)


def _tools_for(modality: str, facts: ConceptFacts, *,
               media_enabled: bool) -> tuple[tuple[ToolCall, ...], tuple[ToolCall, ...]]:
    """(tools, fallback) for a channel, so a degraded choice still carries its calls.

    A channel named without the calls that deliver it is a plan step the runner
    cannot execute, which is why the ceiling pass below re-derives them rather than
    keeping the ones belonging to the channel it just replaced.
    """
    if modality in ('figure', 'concept_map'):
        return (_figure_call(facts.id),), ()
    if modality == 'simulation':
        return (_simulation_call(facts.id),), (_figure_call(facts.id),)
    if modality == 'image':
        if media_enabled:
            return (_image_call(facts.id, facts.title),), (_figure_call(facts.id),)
        return (), ()
    if modality == 'video':
        return (_video_call(facts.id),), (_figure_call(facts.id),)
    if modality == 'audio':
        return (_audio_call('{explanation_text}'),), ()
    return (), ()   # text needs no tool


def _within_ceiling(choice: ModalityChoice, profile, facts: ConceptFacts, *,
                    media_enabled: bool) -> ModalityChoice:
    """Enforce ``ModalityConfig.allowed``: a channel outside it is never chosen.

    Degradation follows the profile's own order - its preferred channel for this
    concept type first, then plain text - so an operator who switches a channel off
    gets the next-best channel they *did* allow rather than a silent failure or a
    fallback they did not choose.
    """
    allowed = set(profile.modalities.allowed)
    if choice.modality in allowed:
        return choice
    preferred = profile.modalities.prefer.get(facts.concept_type, 'text')
    candidate = next((name for name in (preferred, 'text') if name in allowed), None)
    if candidate is None or candidate == choice.modality:
        # Nothing is allowed (or the only allowed channel is the one already
        # chosen): the rules' answer stands rather than being replaced by a channel
        # the operator also switched off.
        return choice
    tools, fallback = _tools_for(candidate, facts, media_enabled=media_enabled)
    return ModalityChoice(
        candidate,
        f'{choice.modality!r} is switched off on this instance, so the channel '
        f'degrades to {candidate!r}. ' + choice.why,
        tools, fallback, False)


def _route(facts: ConceptFacts, evidence: LearnerEvidence, profile,
           *, last_modality: str = '', board_id: str = '',
           course_id: str = '', media_enabled: bool = False) -> ModalityChoice:
    """The fit rules. The first match wins and each states why the channel fits.

    The rules fire in order; the first match wins, and each returns the reason the
    channel fits. ``last_modality`` feeds the variety rule; ``board_id`` /
    ``course_id`` / ``media_enabled`` describe what this instance can actually
    reach, so the router never schedules a channel the deployment cannot honour.
    """
    allowed = set(profile.modalities.allowed)
    prefer = profile.modalities.prefer
    consolidation = profile.difficulty.consolidation_threshold

    def default_for(kind: str, why: str) -> ModalityChoice:
        modality = prefer.get(kind, 'text')
        if modality not in allowed:
            modality = 'text'
        tools: tuple[ToolCall, ...] = ()
        fallback: tuple[ToolCall, ...] = ()
        needs_teacher = False
        if modality == 'figure':
            tools = (_figure_call(facts.id),)
        elif modality == 'simulation':
            tools = (_simulation_call(facts.id),)
            fallback = (_figure_call(facts.id),)
        elif modality == 'concept_map':
            tools = (_figure_call(facts.id),)
        elif modality == 'image' and media_enabled:
            tools = (_image_call(facts.id, facts.title),)
            fallback = (_figure_call(facts.id),)
        elif modality == 'image':
            modality, tools = 'text', ()
            why += ' No image pipeline is enabled, so the channel is text.'
        return ModalityChoice(modality, why, tools, fallback, needs_teacher)

    # Rule 1 - non-mathematics subject: concept map, never a function plot.
    # The symbolic engine is valid only for mathematics; for every other subject
    # the figure is a concept map derived from real prerequisite edges, and
    # presenting anything else as a model of the phenomenon would over-claim.
    if facts.subject_kind != 'mathematics':
        choice = ModalityChoice(
            'concept_map',
            'This is not a mathematics course, so the honest figure is a concept map '
            'derived from prerequisite edges, not a symbolic model.',
            (_figure_call(facts.id),))
        return _variety(choice, last_modality, profile, facts, evidence,
                        board_id=board_id, course_id=course_id,
                        media_enabled=media_enabled)

    # Rule 2 - a procedural error wants the process watched, not restated.
    if evidence.top_error == 'procedural' and facts.has_figure:
        choice = ModalityChoice(
            'simulation',
            f'The recorded errors on this concept are procedural '
            f'(top error {evidence.top_error!r}); a wrong *process* is corrected by '
            'watching the process run and predicting its next state.',
            (_simulation_call(facts.id),),
            fallback=(_figure_call(facts.id),))
        return _variety(choice, last_modality, profile, facts, evidence,
                        board_id=board_id, course_id=course_id,
                        media_enabled=media_enabled)

    # Rule 3 - a conceptual error wants the structure drawn where it can be
    # annotated live: the whiteboard when the caller has one, the figure otherwise.
    if evidence.top_error == 'conceptual':
        if board_id:
            choice = ModalityChoice(
                'whiteboard',
                'The recorded errors are conceptual; drawing the relationship on the '
                'shared board makes the structure visible while it is discussed, '
                'which a paragraph cannot do.',
                (_whiteboard_call(facts.id, 'concept_map'),), needs_teacher=True)
        else:
            choice = ModalityChoice(
                'figure',
                'The recorded errors are conceptual; the generated figure makes the '
                'relationship visible in place of a no-board explanation.',
                (_figure_call(facts.id),))
        return _variety(choice, last_modality, profile, facts, evidence,
                        board_id=board_id, course_id=course_id,
                        media_enabled=media_enabled)

    # Rule 4 - frustrated learner: novelty is the enemy. Text is the channel a
    # struggling learner is not failing to parse.
    if evidence.frustrated:
        choice = ModalityChoice(
            'text',
            'Recent attempts are fast and wrong, which reads as overload; adding a '
            'new representation now competes with the one that is already not '
            'landing, so the channel stays plain text.',
            ())
        return _variety(choice, last_modality, profile, facts, evidence,
                        board_id=board_id, course_id=course_id,
                        media_enabled=media_enabled)

    # Rule 5 - a learner at or above consolidation on a spatial concept is ready
    # to draw it themselves; the board is the channel where their drawing can be
    # corrected, not where the tutor draws for them.
    if (board_id and facts.concept_type == 'spatial'
            and evidence.mastery >= consolidation):
        choice = ModalityChoice(
            'whiteboard',
            f'Mastery {evidence.mastery:.2f} is at or above the consolidation '
            'threshold for a spatial concept; the learner is ready to produce the '
            'diagram themselves on the shared board.',
            (_whiteboard_call(facts.id, 'learner_draws'),), needs_teacher=True)
        return choice

    # Rule 6 - spoken output requested: audio rides *alongside* text, never
    # instead of it (audio alone would exclude exactly the learners the text
    # version is for).
    if profile.persona.spoken_output and 'audio' in allowed:
        choice = ModalityChoice(
            'audio',
            'The learner asked for spoken output; the explanation is spoken in '
            'addition to the text, not instead of it.',
            (_figure_call(facts.id), _audio_call('{explanation_text}')))
        return choice

    # Rule 7 - the profile's per-type default, refined by a curated-video offer
    # when the course has one (video as an embed under its licence).
    choice = default_for(facts.concept_type,
                         f'Default channel for concept type '
                         f'{facts.concept_type!r} from the teacher profile.')
    if (facts.has_video and course_id and 'video' in allowed
            and evidence.mastery < consolidation):
        choice = ModalityChoice(
            'video',
            'The course carries a curated video for this concept and the learner is '
            'still building mastery; a guided walkthrough precedes independent '
            'retrieval. Offered as an embed under its licence.',
            (_video_call(facts.id), _figure_call(facts.id)))
    return _variety(choice, last_modality, profile, facts, evidence,
                    board_id=board_id, course_id=course_id, media_enabled=media_enabled)


def _variety(choice: ModalityChoice, last_modality: str, profile, facts: ConceptFacts,
             evidence: LearnerEvidence, *, board_id: str, course_id: str,
             media_enabled: bool) -> ModalityChoice:
    """Downgrade an exact repeat of the previous modality, once.

    Variety is bounded by design. It fires only when the *same* channel just played,
    and it can only substitute a channel from a fixed swappable set (a figure, plain
    text, a concept map) - a fit rule's channel is never variety-swapped, because
    "the learner is confused and we already drew once" is not a reason to stop
    drawing the structure.

    Two substitutions, tried in order. First the profile's own alternative for this
    concept type, when that alternative is genuinely a different channel. Then - and
    this is the case that actually occurs - a **register swap**: the profile's
    preferred channel *is* the one that just played (a quantitative concept defaults
    to a figure and will default to a figure again), so the same idea is re-encoded
    in the other register, visual to verbal or verbal to visual.

    The register swap is what stops this rule being decorative. Before it, the
    substitution only fired when ``prefer`` named a channel *different* from the one
    chosen, which for the common concept types is never: the rule was documented,
    tested by nothing, and could not fire.
    """
    if not last_modality or last_modality != choice.modality:
        return choice
    allowed = set(profile.modalities.allowed)
    swappable = {'figure', 'text', 'concept_map'}
    if choice.modality not in swappable:
        return choice
    alternative = profile.modalities.prefer.get(facts.concept_type)
    if (alternative and alternative != choice.modality and alternative in allowed):
        if alternative == 'simulation' and course_id:
            return ModalityChoice(
                'simulation',
                f'The previous turn already used {choice.modality}; the profile '
                'routes this concept type to a simulation, which also varies the '
                'representation.',
                (_simulation_call(facts.id),), fallback=(_figure_call(facts.id),))
        if alternative == 'text':
            return ModalityChoice(
                'text',
                f'The previous turn already used {choice.modality}; for this '
                'concept type the profile allows plain text, which avoids '
                'repeating the same channel.',
                ())
    # The profile's preferred channel is the one that just played. Change the
    # register rather than the content: words instead of a picture, or a picture
    # instead of words. That is the one substitution that is always defensible,
    # because it changes the encoding and not what is being taught.
    if choice.modality != 'text' and 'text' in allowed:
        return ModalityChoice(
            'text',
            f'The previous turn already used {choice.modality}; the same idea is '
            'restated in words instead, so the session changes register rather than '
            'repeating one encoding.',
            ())
    if choice.modality == 'text' and facts.has_figure and 'figure' in allowed:
        return ModalityChoice(
            'figure',
            'The previous turn already used text; the same idea is shown as a figure '
            'instead, so the session changes register rather than repeating one '
            'encoding.',
            (_figure_call(facts.id),))
    return choice
