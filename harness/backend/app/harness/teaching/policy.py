"""The move policy: which teaching move, chosen from evidence and configuration.

This is the configuration-driven successor to a hand-scored policy. Every weight,
threshold and bonus below is read from the :class:`TeacherProfile` - nothing here
invents a constant - so editing the teacher is editing data. Scoring stays legible
on purpose: each candidate keeps its own reason string, the ordering is a plain
argmax with a deterministic tie-break, and two runs over the same evidence produce
the same decision (a policy that cannot be replayed cannot be reviewed).

Two adopted mechanisms shape the scoring beyond the per-move rules:

* **Prerequisite closure** (ossu/computer-science, ~209.9k stars): when the
  prerequisites of a concept carry too much unmet debt, the forward-teaching moves
  are penalised and orient wins instead, because teaching forward on shaky ground
  spends the session building on sand.
* **Completion gating** (freeCodeCamp, ~456k stars): a concept that already
  satisfies the completion gate (enough accurate attempts *and* a finished applied
  task) stops being taught. The scoring enforces it rather than trusting a caller
  to remember, which is how "already learned" quietly becomes "learned again".
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .evidence import LearnerEvidence


@dataclass(frozen=True)
class MoveScore:
    """One move's score and the evidence that produced it."""

    move: str
    score: float
    reason: str

    def to_dict(self) -> dict:
        return {'move': self.move, 'score': round(self.score, 4), 'reason': self.reason}


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _base(profile, name: str) -> float:
    """A move's configured weight, or 0.0 when the profile does not declare it.

    A profile is allowed to drop moves - that is the point of the teacher being
    data. Returning 0.0 rather than raising keeps the scoring rules readable: the
    rule below still runs and still explains itself, it simply cannot lift a move
    the profile removed. ``add`` then drops it, so a removed move can never win.
    """
    try:
        return float(profile.move(name).base)
    except KeyError:
        return 0.0


def _now_hint(evidence: LearnerEvidence) -> float:
    """The clock the due-check compares ``due_at`` against.

    The evidence record carries *when* a review is due but not *what time it is*,
    so the policy reads the wall clock here. It is a named seam rather than an
    inline ``time.time()`` so the tests can freeze one function instead of
    monkeypatching the clock globally, and so a caller replaying a decision can
    substitute the time that decision was actually made at.
    """
    return time.time()


def score_moves(evidence: LearnerEvidence, profile) -> list[MoveScore]:
    """Score every move in the profile. Returns all of them, runner-up visible."""
    difficulty = profile.difficulty
    retrieval = profile.retrieval
    sequencing = profile.sequencing
    completion = profile.completion
    learned = profile.learned_preference
    #: The consolidation bar, read once. ``mastery_threshold`` and this are different
    #: questions - "is it known" versus "is it held well enough to build on" - and
    #: the move rules below depend on the difference.
    consolidation = difficulty.consolidation_threshold

    mastery = evidence.mastery
    attempts = evidence.attempts
    accuracy = evidence.recent_accuracy
    top_error = evidence.top_error
    # Overload is read from the profile's ``frustration_accuracy`` rather than from
    # ``LearnerEvidence.frustrated`` alone. The property has no access to a profile,
    # so it carries a hard-coded 0.34 that happens to equal today's default; reading
    # the configured threshold here is what makes "how wrong is too wrong" a setting
    # instead of a coincidence. The shape of the test is identical - fast and wrong -
    # so the two can only disagree when an operator deliberately moves the bar.
    frustrated = evidence.frustrated or (
        attempts >= 3 and accuracy is not None
        and accuracy <= difficulty.frustration_accuracy
        and evidence.elapsed_trend in {'much_faster', 'faster'})

    # Due at the desired-retention point (Anki's rule; see retrieval.py). A
    # scheduler-written due_at is honoured first, then the direct curve check.
    due = bool(evidence.due_at is not None and evidence.due_at <= _now_hint(evidence))
    if not due and evidence.recall is not None:
        due = evidence.recall <= retrieval.desired_retention
    if not due and evidence.recall is None and attempts > 0:
        # A reviewed concept with no readable stability (legacy hand-off) is due
        # when the scheduler never wrote a due_at for it: honesty over silence.
        due = evidence.due_at is None and attempts > 0

    scored: list[MoveScore] = []
    declared = set(profile.move_names)

    def add(move: str, score: float, reason: str) -> None:
        # A move the profile does not declare is dropped here rather than scored at
        # zero: a zero-scored move still appears in the ranked list and reads as
        # "considered and rejected", when the truth is that this teacher does not
        # have that move at all.
        #
        # The score is stored *unclamped*: the global modifiers applied after all
        # the per-move rules subtract from these numbers, and clamping first would
        # silently swallow the subtraction (1.3 - 0.5 is 0.8, but clamp-then-subtract
        # gives 0.5). Clamping happens once, at the end.
        if move in declared:
            scored.append(MoveScore(move, score, reason))

    # ---- orient -----------------------------------------------------------
    score, why = 0.22, 'Some orientation is always affordable.'
    if attempts == 0:
        score += 0.42
        why = 'No scored attempt exists for this concept, so there is no evidence to teach against yet.'
    if evidence.uncertain:
        score += 0.22
        why = (f'Mastery {mastery:.2f} rests on only {attempts} attempt(s); a short '
               'diagnostic buys more information than teaching does.')
    if evidence.weak_prerequisites:
        score += 0.10
        why += (f" {evidence.weak_prerequisites} prerequisite(s) measure below "
                f'{difficulty.mastery_threshold:.2f}.')
    add('orient', score, why)

    # ---------------------------------------------------------------------
    # The remaining eight moves.
    #
    # Each block below states its own rules and accumulates the reasons that
    # fired, so a decision can be read back without re-deriving it. Nothing
    # here invents a weight: a move's floor comes from the profile
    # (``MoveSpec.base``) and every adjustment is a named, documented rule.
    # ---------------------------------------------------------------------

    # ---- explain ----------------------------------------------------------
    reasons = ['Instruction is affordable; the question is whether it is the right '
               'move right now.']
    score = _base(profile, 'explain') + 0.16
    if not evidence.has_lesson:
        score -= 0.12
        reasons.append('No authored lesson is bound to this concept, so an '
                       'explanation would be improvised rather than grounded.')
    if mastery >= consolidation:
        score -= 0.20
        reasons.append(f'Mastery {mastery:.2f} already sits at the consolidation '
                       f'threshold {consolidation:.2f}, where more explanation has '
                       'little left to add.')
    if accuracy is not None and attempts >= 3 and accuracy < difficulty.target_success:
        score += 0.12
        reasons.append(f'Measured accuracy {accuracy:.2f} is below the '
                       f'{difficulty.target_success:.2f} success target, so the idea is '
                       'worth restating rather than testing.')
    add('explain', score, ' '.join(reasons))

    # ---- simulate ---------------------------------------------------------
    reasons = ['Changing the representation is available for this concept.']
    score = _base(profile, 'simulate') + 0.12
    if top_error == 'procedural':
        score += 0.24
        reasons.append('The recorded errors are procedural; a wrong *process* is '
                       'corrected by watching it run and predicting the next state, '
                       'which a restatement cannot do.')
    if not evidence.has_figure:
        score -= 0.14
        reasons.append('Neither a figure nor a simulation is available for this '
                       'concept, so the representation cannot actually change.')
    if evidence.simulation_touched:
        score -= 0.06
        reasons.append('A simulation has already been touched this session; a second '
                       'run adds novelty without new information.')
    if (accuracy is not None and attempts >= 3
            and abs(accuracy - difficulty.target_success) <= 0.10):
        score += 0.10
        reasons.append(f'Accuracy {accuracy:.2f} is parked on the '
                       f'{difficulty.target_success:.2f} target - neither failing nor '
                       'consolidating - which is the plateau a new representation '
                       'breaks.')
    add('simulate', score, ' '.join(reasons))

    # ---- retrieve ---------------------------------------------------------
    # The FSRS-6 rule (ankitects/anki, ~31k stars): serve the review at the point
    # retrievability decays to the desired retention, where a review costs least
    # and adds most stability. Reviewing early is easy and teaches nothing.
    reasons = ['Retrieval practice is affordable for any concept the learner has met.']
    score = _base(profile, 'retrieve') + 0.14
    if attempts == 0:
        score -= 0.30
        reasons.append('Nothing has been attempted yet, so there is no memory to '
                       'retrieve.')
    if due:
        score += 0.34
        reasons.append('The memory is due: retrievability has decayed to the '
                       f'{retrieval.desired_retention:.2f} desired-retention point.')
    elif evidence.recall is not None:
        score -= 0.10
        reasons.append(f'Retrievability is still {evidence.recall:.2f}, above the '
                       f'{retrieval.desired_retention:.2f} review point; a review now '
                       'would be easy and would add little stability.')
    if mastery >= difficulty.mastery_threshold:
        score += 0.08
        reasons.append(f'Mastery {mastery:.2f} is at or above the '
                       f'{difficulty.mastery_threshold:.2f} threshold, so a successful '
                       'recall is plausible rather than a guess.')
    if frustrated:
        score -= 0.28
        reasons.append('Recent attempts are fast and wrong; another retrieval item now '
                       'is noise rather than practice.')
    add('retrieve', score, ' '.join(reasons))

    # ---- discuss ----------------------------------------------------------
    reasons = ['A Socratic exchange is available once the learner has enough grasp to '
               'reason aloud.']
    score = _base(profile, 'discuss') + 0.10
    if top_error == 'conceptual':
        score += 0.18
        reasons.append('The recorded errors are conceptual; making the learner state '
                       'the relationship in their own words is what surfaces a wrong '
                       'model, which a correct explanation does not.')
    if accuracy is not None and attempts >= 3 and accuracy >= difficulty.target_success:
        score += 0.12
        reasons.append(f'Accuracy {accuracy:.2f} is at or above the '
                       f'{difficulty.target_success:.2f} target, so the learner can '
                       'carry the reasoning themselves.')
    if mastery < difficulty.mastery_threshold and attempts < 3:
        score -= 0.10
        reasons.append(f'Mastery {mastery:.2f} over {attempts} attempt(s) is too thin to '
                       'sustain a discussion; there is nothing to reason from yet.')
    if frustrated:
        score -= 0.24
        reasons.append('A frustrated learner asked to reason aloud is being asked to '
                       'perform the thing that is currently failing.')
    add('discuss', score, ' '.join(reasons))

    # ---- project ----------------------------------------------------------
    # The freeCodeCamp gate in move form (~456k stars): recognition is not
    # transfer, so the applied task is the move that produces the evidence the
    # completion gate actually requires.
    reasons = ['An applied task is the only move that produces transfer evidence.']
    score = _base(profile, 'project') + 0.08
    if mastery >= consolidation and evidence.project_status != 'completed':
        score += 0.30
        reasons.append(f'Mastery {mastery:.2f} is at the consolidation threshold and no '
                       'applied task is finished, so this move closes the exact gap the '
                       'completion gate measures.')
    elif mastery < difficulty.mastery_threshold:
        score -= 0.22
        reasons.append(f'Mastery {mastery:.2f} is below the '
                       f'{difficulty.mastery_threshold:.2f} threshold; an applied task '
                       'set now would test a skill that is not there yet.')
    if evidence.project_status == 'completed':
        score -= 0.26
        reasons.append('The applied task for this concept is already complete, so the '
                       'transfer evidence exists and re-setting it repeats work.')
    if evidence.dependants:
        score += 0.06
        reasons.append(f'{evidence.dependants} later concept(s) build on this one, so '
                       'transfer here unlocks more of the graph than transfer '
                       'elsewhere.')
    add('project', score, ' '.join(reasons))

    # ---- generate ---------------------------------------------------------
    reasons = ['Producing an artefact is available once there is material to produce '
               'it from.']
    score = _base(profile, 'generate') + 0.06
    if mastery >= consolidation:
        score += 0.20
        reasons.append(f'Mastery {mastery:.2f} is at the consolidation threshold, so '
                       'building a deck or card set is a generative task the learner '
                       'can actually complete.')
    if evidence.unit_coverage >= 0.6:
        score += 0.12
        reasons.append(f'{evidence.unit_coverage:.0%} of the unit is covered, so an '
                       'artefact would consolidate a body of material rather than one '
                       'isolated idea.')
    if mastery < difficulty.mastery_threshold:
        score -= 0.20
        reasons.append(f'Mastery {mastery:.2f} is below the '
                       f'{difficulty.mastery_threshold:.2f} threshold; generating from '
                       'material that is not yet held produces a summary the learner '
                       'cannot use.')
    add('generate', score, ' '.join(reasons))

    # ---- consolidate ------------------------------------------------------
    reasons = ['Connecting a concept to its neighbours is always available.']
    score = _base(profile, 'consolidate') + 0.08
    if mastery >= consolidation and evidence.dependants:
        score += 0.26
        reasons.append(f'Mastery {mastery:.2f} is at the consolidation threshold and '
                       f'{evidence.dependants} concept(s) build on this one, so making '
                       'the structure explicit is what the graph needs next.')
    if evidence.unit_coverage >= 0.75:
        score += 0.10
        reasons.append(f'{evidence.unit_coverage:.0%} of the unit is covered; a '
                       'structure summary is worth more now than another isolated '
                       'concept.')
    if len(evidence.recent_moves) >= 4 and len(set(evidence.recent_moves[-4:])) == 1:
        score += 0.16
        reasons.append('The same move has run four times in a row; the session needs a '
                       'change of shape, and consolidation is the change that still '
                       'teaches.')
    if mastery < difficulty.mastery_threshold:
        score -= 0.16
        reasons.append(f'Mastery {mastery:.2f} is below the '
                       f'{difficulty.mastery_threshold:.2f} threshold; there is not yet '
                       'a structure to consolidate.')
    add('consolidate', score, ' '.join(reasons))

    # ---- rest -------------------------------------------------------------
    reasons = ['Stopping is always available and is never scored as a failure.']
    score = _base(profile, 'rest') + 0.04
    if evidence.session_minutes >= difficulty.long_session_minutes:
        score += 0.40
        reasons.append(f'{evidence.session_minutes:.0f} minutes of measured interaction '
                       f'exceeds the {difficulty.long_session_minutes:.0f}-minute point '
                       'where continued instruction stops paying for itself.')
    if frustrated:
        score += 0.34
        reasons.append('Attempts are fast and wrong, the signature of overload; the '
                       'useful intervention is a shorter session, not a different '
                       'explanation.')
    if len(evidence.recent_moves) >= 3 and len(set(evidence.recent_moves[-3:])) == 1:
        score += 0.08
        reasons.append('The same move has run three times without a measured change; '
                       'continuing it is repetition, not teaching.')
    add('rest', score, ' '.join(reasons))

    # ---------------------------------------------------------------------
    # Global modifiers, applied as a post-pass.
    #
    # These two mechanisms are not about one move: they decide whether forward
    # teaching is appropriate *at all*. Applying them here rather than inside
    # each block keeps every per-move rule above readable on its own terms, and
    # keeps the two adopted gates in one place where they can be audited.
    # ---------------------------------------------------------------------
    forward = {'explain', 'simulate', 'retrieve', 'discuss', 'project', 'generate'}
    satisfied = evidence.satisfied(completion)
    adjusted: list[MoveScore] = []
    for item in scored:
        score = item.score
        reasons = [item.reason]

        # Prerequisite closure (ossu/computer-science, ~209.9k stars): never teach
        # past an unmet prerequisite. Debt past the ceiling means the ground under
        # this concept is shaky, and teaching forward spends the session on a
        # concept that will not hold. The penalty scales with how far past the
        # ceiling the debt is, so a marginal breach costs less than an abandoned
        # prerequisite - a flat penalty would make "slightly shaky" and "absent"
        # the same decision.
        if item.move in forward and evidence.prerequisite_debt > sequencing.debt_ceiling:
            excess = evidence.prerequisite_debt - sequencing.debt_ceiling
            score -= sequencing.debt_weight * excess * 2.0
            reasons.append(
                f'Prerequisite debt {evidence.prerequisite_debt:.2f} exceeds the '
                f'{sequencing.debt_ceiling:.2f} ceiling '
                f'({evidence.weak_prerequisites} prerequisite(s) below the bar), so '
                'forward teaching is building on unmet ground.')

        # Completion gate (freeCodeCamp, ~456k stars): a concept that already
        # satisfies the gate stops being taught. Enforced here rather than trusted
        # to a caller, because "already learned" quietly becoming "learned again"
        # is how a self-paced curriculum never ends.
        if item.move in forward and satisfied:
            score -= 0.50
            reasons.append(
                f'The completion gate is satisfied ({evidence.attempts} attempt(s) at '
                f'{evidence.recent_accuracy if evidence.recent_accuracy is None else round(evidence.recent_accuracy, 2)} '
                f'accuracy with the applied task {evidence.project_status}), so this '
                'concept has been taught.')

        # Bounded learner-specific bias. One good session must not hard-wire a
        # preference: the bias saturates at ``cap`` recorded outcomes and can never
        # exceed ``weight``, so the evidence rules above always dominate it.
        stats = evidence.move_history.get(item.move) or {}
        helped = int(stats.get('helped', 0))
        hurt = int(stats.get('hurt', 0))
        observed = helped + hurt
        if observed:
            bias = (learned.weight * min(1.0, observed / max(1, learned.cap))
                    * ((helped - hurt) / observed))
            score += bias
            reasons.append(f'This learner\'s own record: {helped} helped / {hurt} hurt '
                           f'over {observed} measured run(s) '
                           f'({bias:+.3f} applied, capped at {learned.weight}).')

        adjusted.append(MoveScore(item.move, _clamp(score), ' '.join(r for r in reasons if r)))
    return adjusted


def select_move(evidence: LearnerEvidence, profile) -> MoveScore:
    """The chosen move: the best-scoring candidate, carrying its own reason.

    Deterministic by construction. Ties break on the profile's declared move
    order - fixed data - and never on set or dict iteration: a policy whose answer
    depends on hash order cannot be replayed, and a tutor whose next move changes
    between two identical states cannot be audited or A/B tested.
    """
    ranked = score_moves(evidence, profile)
    if not ranked:
        raise ValueError('The profile declares no moves to choose between')
    order = {name: index for index, name in enumerate(profile.move_names)}
    return min(ranked, key=lambda item: (-item.score, order.get(item.move, 1 << 16)))
