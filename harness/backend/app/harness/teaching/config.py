"""The teacher profile: the whole pedagogy, as inspectable data.

A tutoring system that keeps its pedagogy inside prompt strings and scoring
constants cannot be audited, compared or A/B'd: the rule that fired is buried in
prose a model paraphrases. So the teacher is declared here instead. A
:class:`TeacherProfile` names which moves exist, when each is chosen, the retrieval
schedule, the difficulty policy, the multimodality mix and the completion gate, and
the rest of the package (policy, retrieval, modalities, render) reads that
declaration. Changing the teacher means editing a profile, never rewriting a prompt.

Lineage. Every section of the default profile traces to a technique adopted from an
open-source teaching system, verified at 10,000+ GitHub stars on 2026-10-13. Nothing
below is copied from those repositories; each mechanism was re-implemented against
this app's own FSRS-6 memory model (``app.memory``), BKT-style mastery
(``app.learning``) and knowledge graph (``app.knowledge_graph``), because a rule that
does not read the same states as the rest of the harness is two truths.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping

#: Auditable lineage: repo -> star count (source, verified 2026-10-13), the technique
#: taken, and the config section it became. Kept in code so the provenance of a
#: pedagogical decision is one attribute lookup away.
LINEAGE: dict[str, dict[str, str]] = {
    'ankitects/anki': {
        'stars': '~31.0k (gitstars.io, 2026-10-13)',
        'technique': 'FSRS desirable-difficulty scheduling: a review is due when '
                     'retrievability R decays to the desired retention, and reviews '
                     'are served weakest-memory first.',
        'adapted_in': 'RetrievalConfig; teaching/retrieval.py',
    },
    'freeCodeCamp/freeCodeCamp': {
        'stars': '~456k (livecounts.nl, 2026-10-13)',
        'technique': 'Mastery gated on completing a required applied project '
                     '(transfer), not on accumulating quiz passes.',
        'adapted_in': 'CompletionConfig; teaching/policy.py completion gate',
    },
    'ossu/computer-science': {
        'stars': '~209.9k (star-history.com, 2026-10-13)',
        'technique': 'Prerequisite-closure sequencing: never teach past an unmet '
                     'prerequisite; order work by accumulated prerequisite debt.',
        'adapted_in': 'SequencingConfig; teaching/policy.py fallback rules',
    },
    'microsoft/AI-For-Beginners': {
        'stars': '~55.7k (explainx.ai curriculum review, 2026-08; repo README)',
        'technique': 'Every lesson is wrapped by a pre-quiz and a post-quiz, so '
                     'retrieval practice brackets the instruction on both sides.',
        'adapted_in': 'WrapConfig; teaching/session.py step assembly',
    },
    'JushBJJ/Mr.-Ranedeer-AI-Tutor': {
        'stars': '~29.6k (star-history.com, 2026-10-13)',
        'technique': 'The tutor persona (depth, style, pace) is a declarative '
                     'configuration block the system prompt is rendered from.',
        'adapted_in': 'PersonaConfig; this whole profile design',
    },
}


@dataclass(frozen=True)
class MoveSpec:
    """One teaching move: what it is, when it is appropriate, what it calls.

    ``summary`` is the prompt-facing sentence: the learner (and the auditor) can read
    exactly when the system thinks each move applies. ``base`` is the move's weight
    in the policy's scoring before any learner evidence is applied - it expresses
    "always affordable" vs "only when something specific holds".
    """

    name: str
    summary: str
    base: float = 0.1


@dataclass(frozen=True)
class RetrievalConfig:
    """The retrieval schedule.

    Adapted from Anki's FSRS scheduler (ankitects/anki, ~31k stars): a review is
    scheduled for the moment retrievability decays to ``desired_retention``, which
    is the computable form of Bjork's desirable difficulty - the review is easiest
    (and weakest) to *schedule* at the point where recall is hardest but still
    successful. ``interleave_every`` inserts one new concept after that many
    reviews so a session is never a same-day cram of one idea; ``max_new_per_session``
    caps novelty, because a queue of all-new material has nothing to review.
    """

    desired_retention: float = 0.9
    per_session: int = 12
    interleave_every: int = 3
    max_new_per_session: int = 2
    weakest_first: bool = True


@dataclass(frozen=True)
class DifficultyConfig:
    """The difficulty policy: where the harness aims, and where it stops.

    ``target_success`` is the practice success rate the item chooser aims at: an
    item the learner gets right 95% of the time teaches little, and one they get
    right 30% of the time is noise. ``mastery_threshold`` mirrors
    ``app.learning.MASTERY_THRESHOLD`` deliberately - a second mastery number would
    let prerequisite gating and move selection disagree about what "known" means.
    """

    target_success: float = 0.7
    mastery_threshold: float = 0.6
    consolidation_threshold: float = 0.8
    #: Below this accuracy the harness treats continued retrieval as harmful noise.
    frustration_accuracy: float = 0.34
    #: Minutes of measured interaction after which rest starts winning arguments.
    long_session_minutes: float = 45.0


@dataclass(frozen=True)
class WrapConfig:
    """Retrieval practice wrapped around instruction.

    Adapted from microsoft/AI-For-Beginners (~55.7k stars), whose every lesson opens
    with a pre-quiz and closes with a post-quiz. The mechanism generalised here: an
    explanation move is bracketed by a low-stakes elicitation *before* (so the new
    material has something to attach to, and the tutor's starting belief is tested
    rather than assumed) and a fresh check *after* (so the learner leaves having
    retrieved the idea, not just read it - the testing effect). Both wrap steps are
    skippable by evidence: eliciting from a learner who just failed a retrieval is
    salt in a wound.
    """

    elicit_before: bool = True
    check_after: bool = True
    transfer_check: bool = True


@dataclass(frozen=True)
class CompletionConfig:
    """When a concept counts as taught.

    Adapted from freeCodeCamp (~456k stars), where a certificate unit is complete
    only once the learner has finished the required applied project: passing the
    lessons' checks is evidence of recognition, and the project is evidence of
    transfer. The gate below mirrors that split - ``min_attempts`` scored attempts
    at or above ``min_accuracy`` on the mastered concept, plus a completed applied
    task when ``transfer_required``. Without this gate the recommender keeps
    polishing concepts the learner can already use, which is how a self-paced
    curriculum quietly never ends.
    """

    min_attempts: int = 3
    min_accuracy: float = 0.8
    transfer_required: bool = True


@dataclass(frozen=True)
class SequencingConfig:
    """Prerequisite-aware sequencing.

    Adapted from ossu/computer-science (~209.9k stars), which teaches in
    prerequisite order and refuses to advance past unmet dependencies. The debt
    measure here is ``1 - mean mastery of direct prerequisites``: a concept can be
    nominally unlocked by the BKT threshold and still be sitting on shaky ground,
    and teaching it anyway spends the session on a concept that will not hold.
    ``debt_ceiling`` is the point at which the policy stops teaching forward and
    repairs the prerequisites instead.
    """

    debt_weight: float = 0.5
    debt_ceiling: float = 0.4


@dataclass(frozen=True)
class PersonaConfig:
    """The tutor's voice: depth, tone and pace, declared as data.

    Adapted from Mr. Ranedeer (~29.6k stars), whose tutor prompt is a configuration
    block: depth, learning style and communication style are declared once and
    rendered into the system prompt, instead of being re-negotiated in prose every
    turn. Depth is 1-10 and scales *how much* scaffolding a move carries, not what
    the policy chooses - a persona setting must never be able to override the
    evidence rules, or a warm tone would start winning arguments a confused learner
    should not be having.
    """

    depth: int = 5
    tone: str = 'warm'
    pace: str = 'adaptive'
    spoken_output: bool = False


@dataclass(frozen=True)
class ModalityConfig:
    """The multimodality mix: which channels exist, and the default routing.

    ``allowed`` is the ceiling - a modality outside it is never chosen even if a
    rule likes it (an operator can run a text-only instance by editing data).
    ``prefer`` maps a concept type to its default teaching channel; the routing
    rules in :mod:`app.harness.teaching.modalities` refine it by mastery and error
    category. ``variety`` is the penalty for repeating the previous modality, so a
    learner is not explained to with four whiteboards in a row.
    """

    allowed: tuple[str, ...] = ('text', 'figure', 'whiteboard', 'simulation', 'image',
                                'video', 'audio', 'concept_map')
    prefer: Mapping[str, str] = field(default_factory=lambda: {
        'quantitative_relation': 'figure',
        'procedure': 'simulation',
        'spatial': 'figure',
        'data': 'figure',
        'concrete_phenomenon': 'image',
        'concept_map': 'concept_map',
        'verbal': 'text',
    })
    variety_penalty: float = 0.25


@dataclass(frozen=True)
class ProcedureConfig:
    """The lesson's run of show: which activities, in which order, for how long.

    The move policy answers "what should this turn do"; this section answers "what
    should this *lesson* be". They are separate because a lesson is not a sequence of
    moves: a deck is not a move, and a learner who needs three example questions needs
    them in one block, not three consecutive turns of ``retrieve``.

    Every threshold below is a decision about *when an activity is the right activity*,
    and each one is a number rather than a sentence in a prompt so it can be moved,
    replayed and tested. The reasoning behind each is in
    :mod:`app.harness.teaching.procedure`, where the rule that reads it lives.

    ``minutes`` is the per-activity cost the planner budgets with. It is deliberately
    pessimistic: a five-minute deck is a deck a learner will actually read, and a
    planner that assumes two minutes produces a session that runs twice as long as the
    learner agreed to.
    """

    #: The lesson is built at all. An operator can switch the procedure off and leave
    #: the move policy running; the tutor then behaves exactly as it did before.
    enabled: bool = True
    #: Hard bounds on the run of show. Below the minimum there is no lesson to run, and
    #: above the maximum the procedure stops being a session and becomes a course.
    min_minutes: int = 6
    max_minutes: int = 45
    #: Accuracy at or above which a learner does not need the input block. This is the
    #: "when to host the PPT" rule: a learner already answering at this level is taught
    #: by practice, not by slides, and showing them the deck costs the session's budget
    #: for no new information.
    skip_input_accuracy: float = 0.8
    #: Mastery at or above which an input block is not offered even without a recent
    #: accuracy figure - the concept is consolidated and another explanation is noise.
    skip_input_mastery: float = 0.8
    #: A simulation is only offered once the learner has enough grasp to *predict* what
    #: it will do. Below this, the interaction is a toy rather than an experiment.
    simulation_min_mastery: float = 0.25
    #: Above this mastery, with no procedural error, the mechanic is already fluent and
    #: a simulation adds novelty rather than information.
    simulation_skip_mastery: float = 0.85
    #: Practice size scales with mastery: a struggling learner gets fewer items, done
    #: properly, and a consolidating learner gets more. Both ends are capped by the
    #: number of authored items that actually exist for the concept.
    practice_min_items: int = 2
    practice_max_items: int = 4
    practice_minutes_per_item: float = 1.5
    #: A diagnostic is two items: one is a coin flip, and three is a quiz the learner
    #: did not ask for.
    diagnostic_items: int = 2
    #: Minutes per activity. Missing keys fall back to ``default_minutes``.
    minutes: Mapping[str, int] = field(default_factory=lambda: {
        'diagnostic': 3, 'deck': 5, 'video': 4, 'explain': 4, 'worked_example': 4,
        'simulation': 5, 'practice': 5, 'discussion': 3, 'recap': 2, 'close': 1,
    })
    default_minutes: int = 4


@dataclass(frozen=True)
class LearnedPreferenceConfig:
    """How much a learner's own history may bend the policy.

    Bounded on purpose (same reasoning as the loop's history weight): one good
    session must not hard-wire a preference, and the evidence rules must always
    dominate the learner-specific bias. ``cap`` is the number of recorded outcomes
    the bias saturates at.
    """

    weight: float = 0.12
    cap: int = 3


#: The nine moves. Names match ``app.harness.loop.MOVES`` on purpose: the prompt
#: template asserts every loop move appears, and two vocabularies for the same nine
#: actions would let a plan reference a move the runner does not know. Order is the
#: deterministic tie-break order for the policy.
DEFAULT_MOVES: tuple[MoveSpec, ...] = (
    MoveSpec('orient',
             'Gather missing evidence with a short diagnostic check before teaching.'),
    MoveSpec('explain',
             'Teach the idea with a grounded explanation and the live figure.'),
    MoveSpec('simulate',
             'Change the representation: build a figure and have the learner predict.'),
    MoveSpec('retrieve',
             'Ask for recall of something already met, at the interval it is due.'),
    MoveSpec('discuss',
             'Open a Socratic exchange where the learner does the reasoning aloud.'),
    MoveSpec('project',
             'Set an applied task with a rubric and limited AI use.'),
    MoveSpec('generate',
             'Produce a multimodal artefact: a deck, a card set, an illustration brief.'),
    MoveSpec('consolidate',
             'Connect this concept to its neighbours and summarise the structure.'),
    MoveSpec('rest',
             'Stop adding new material; shorten the session or change activity.'),
)


@dataclass(frozen=True)
class TeacherProfile:
    """One teacher: the moves, the schedule, the difficulty policy, the mix.

    The profile is the single source of pedagogy. ``name`` and ``description`` are
    what a transparency panel shows a learner who asks "which teacher am I?".
    Everything else is consumed by the policy, the retrieval planner, the modality
    router and the prompt renderer - no other module in this package is allowed to
    invent a constant of its own, because a second constant is how the config drifts
    from the behaviour.
    """

    name: str = 'default'
    description: str = 'Evidence-first tutor: FSRS-6 scheduled retrieval, '\
                       'prerequisite-aware sequencing, grounded multimodality.'
    moves: tuple[MoveSpec, ...] = DEFAULT_MOVES
    retrieval: RetrievalConfig = RetrievalConfig()
    difficulty: DifficultyConfig = DifficultyConfig()
    wrap: WrapConfig = WrapConfig()
    completion: CompletionConfig = CompletionConfig()
    sequencing: SequencingConfig = SequencingConfig()
    persona: PersonaConfig = PersonaConfig()
    modalities: ModalityConfig = ModalityConfig()
    procedure: ProcedureConfig = ProcedureConfig()
    learned_preference: LearnedPreferenceConfig = LearnedPreferenceConfig()

    @property
    def move_names(self) -> tuple[str, ...]:
        return tuple(spec.name for spec in self.moves)

    def move(self, name: str) -> MoveSpec:
        for spec in self.moves:
            if spec.name == name:
                return spec
        raise KeyError(f'Unknown move {name!r}')

    def to_dict(self) -> dict[str, Any]:
        """The profile as plain data, for the transparency panel and storage."""
        return {
            'name': self.name,
            'description': self.description,
            'moves': [{'move': s.name, 'when': s.summary, 'base': s.base}
                      for s in self.moves],
            'retrieval': self.retrieval.__dict__,
            'difficulty': self.difficulty.__dict__,
            'wrap': self.wrap.__dict__,
            'completion': self.completion.__dict__,
            'sequencing': self.sequencing.__dict__,
            'persona': self.persona.__dict__,
            'modalities': {'allowed': list(self.modalities.allowed),
                           'prefer': dict(self.modalities.prefer),
                           'variety_penalty': self.modalities.variety_penalty},
            'procedure': {**self.procedure.__dict__,
                          'minutes': dict(self.procedure.minutes)},
            'learned_preference': self.learned_preference.__dict__,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> TeacherProfile:
        """Build (or patch) a profile from plain data, validating every field.

        This is the "configuration" surface the product asks for: a stored profile
        is a dict, and a dict that cannot be validated is a profile you cannot
        trust. Unknown top-level keys are rejected rather than ignored, because a
        silently-dropped ``{"difficulty": {"mastery_threshold": ...}}`` typo reads
        as success and changes nothing - the operator believes the teacher changed
        when it did not.
        """
        if not isinstance(payload, Mapping):
            raise TypeError('A teacher profile must be a mapping')
        known = {'name', 'description', 'moves', 'retrieval', 'difficulty', 'wrap',
                 'completion', 'sequencing', 'persona', 'modalities', 'procedure',
                 'learned_preference'}
        unknown = sorted(set(payload) - known)
        if unknown:
            raise ValueError(f'Unknown profile section(s): {", ".join(unknown)}')
        sections = dict(payload)
        for key in known - {'moves', 'modalities', 'name', 'description'}:
            if key in sections and not isinstance(sections[key], Mapping):
                raise TypeError(f'Profile section {key!r} must be a mapping')

        profile = cls(name=str(sections.get('name', cls.name)),
                      description=str(sections.get('description', cls.description)))

        def _section(current, data, numeric):
            """Rebuild a section dataclass, clamping every numeric field to (0, 1]
            where it is a probability, and rejecting unknown fields."""
            if data is None:
                return current
            fields = {f: getattr(current, f) for f in current.__dataclass_fields__}
            for key, value in data.items():
                if key not in fields:
                    raise ValueError(f'Unknown field {key!r} in this profile section')
                fields[key] = value
            for key in numeric:
                fields[key] = _clamp01(fields[key], key)
            return replace(current, **fields)

        profile = replace(
            profile,
            retrieval=_section(profile.retrieval, sections.get('retrieval'),
                               ('desired_retention',)),
            difficulty=_section(profile.difficulty, sections.get('difficulty'),
                                ('target_success', 'mastery_threshold',
                                 'consolidation_threshold', 'frustration_accuracy')),
            wrap=_section(profile.wrap, sections.get('wrap'), ()),
            completion=_section(profile.completion, sections.get('completion'),
                                ('min_accuracy',)),
            sequencing=_section(profile.sequencing, sections.get('sequencing'),
                                ('debt_ceiling',)),
            persona=_section(profile.persona, sections.get('persona'), ()),
            procedure=_section(profile.procedure, sections.get('procedure'),
                               ('skip_input_accuracy', 'skip_input_mastery')),
            learned_preference=_section(profile.learned_preference,
                                        sections.get('learned_preference'), ()),
        )
        if 'moves' in sections:
            profile = replace(profile, moves=_moves_from(sections['moves']))
        if 'modalities' in sections:
            profile = replace(profile,
                              modalities=_modalities_from(profile.modalities,
                                                          sections['modalities']))
        _sanity(profile)
        return profile


def _clamp01(value: Any, field_name: str) -> float:
    """Clamp a probability field into (0, 1]. A config typo of 90 for 0.9 is the
    kind of error that silently disables a rule; clamping keeps it loud-but-safe."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{field_name} must be a number, got {value!r}')
    return min(1.0, max(1e-6, number))


def _moves_from(payload: Any) -> tuple[MoveSpec, ...]:
    if not isinstance(payload, (list, tuple)) or not payload:
        raise ValueError('moves must be a non-empty list')
    moves = []
    seen = set()
    for entry in payload:
        if isinstance(entry, str):
            moves.append(MoveSpec(entry, entry.capitalize() + '.'))
        elif isinstance(entry, Mapping):
            # Two field names are accepted for each of these on purpose. The
            # *authoring* shape is ``{'name': ..., 'summary': ...}`` and the shape
            # :meth:`TeacherProfile.to_dict` emits for the client's transparency
            # panel is ``{'move': ..., 'when': ...}`` - the panel's vocabulary is
            # the product's, and it is what the API already returns. Accepting both
            # is what makes ``from_dict(to_dict(p))`` a round trip; accepting only
            # one of them silently made every saved profile unloadable, because the
            # stored moves were dropped and the teacher fell back to the defaults.
            name = str(entry.get('name', entry.get('move', ''))).strip()
            if not name:
                raise ValueError(f'A move needs a name: {entry!r}')
            if name in seen:
                raise ValueError(f'Duplicate move {name!r}')
            seen.add(name)
            summary = str(entry.get('summary', entry.get('when', name + '.')))
            moves.append(MoveSpec(name, summary,
                                  _clamp01(entry.get('base', 0.1), f'{name}.base')))
        else:
            raise TypeError(f'A move is a name or a mapping, got {type(entry).__name__}')
    return tuple(moves)


def _modalities_from(current: ModalityConfig, payload: Mapping[str, Any]) -> ModalityConfig:
    fields = {'allowed': current.allowed, 'prefer': dict(current.prefer),
              'variety_penalty': current.variety_penalty}
    for key, value in payload.items():
        if key not in fields:
            raise ValueError(f'Unknown field {key!r} in the modalities section')
        fields[key] = value
    return replace(current,
                   allowed=tuple(fields['allowed']),
                   prefer=dict(fields['prefer']),
                   variety_penalty=_clamp01(fields['variety_penalty'], 'variety_penalty'))


def _sanity(profile: TeacherProfile) -> None:
    """Cross-field checks no single-field clamp can catch."""
    if profile.difficulty.consolidation_threshold < profile.difficulty.mastery_threshold:
        raise ValueError('consolidation_threshold must not sit below mastery_threshold')
    if profile.retrieval.per_session < 1:
        raise ValueError('retrieval.per_session must be at least 1')
    if profile.completion.min_attempts < 1:
        raise ValueError('completion.min_attempts must be at least 1')
    if not 1 <= profile.persona.depth <= 10:
        raise ValueError('persona.depth is a 1-10 scale')
    _procedure_sanity(profile.procedure)


def _procedure_sanity(procedure: ProcedureConfig) -> None:
    """The procedure's own cross-field rules.

    These are checked rather than clamped because each one is a *relationship*: a
    minimum budget above the maximum produces a session that can never fit, and a
    practice floor above its ceiling produces a count that is silently overridden -
    either way the operator's saved profile reads as accepted and behaves as something
    else, which is the failure mode the whole "teacher is data" design exists to avoid.
    """
    if not isinstance(procedure.minutes, Mapping):
        raise ValueError('procedure.minutes must be a mapping of activity -> minutes')
    for kind, value in procedure.minutes.items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f'procedure.minutes[{kind!r}] must be a positive integer')
    if procedure.min_minutes < 1:
        raise ValueError('procedure.min_minutes must be at least 1')
    if procedure.max_minutes < procedure.min_minutes:
        raise ValueError('procedure.max_minutes must not sit below procedure.min_minutes')
    if procedure.practice_min_items < 1:
        raise ValueError('procedure.practice_min_items must be at least 1')
    if procedure.practice_max_items < procedure.practice_min_items:
        raise ValueError('procedure.practice_max_items must not sit below practice_min_items')
    if procedure.diagnostic_items < 1:
        raise ValueError('procedure.diagnostic_items must be at least 1')
    if procedure.practice_minutes_per_item <= 0:
        raise ValueError('procedure.practice_minutes_per_item must be positive')


def default_profile() -> TeacherProfile:
    """The shipped teacher. Every default here is a deliberate, documented choice;
    the rationale is the docstring of the section that owns it."""
    return TeacherProfile()
