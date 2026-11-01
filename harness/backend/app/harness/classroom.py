"""The classroom decision engine: one polling tick in, one teaching decision out.

This is the layer above :mod:`app.harness.attention`. Attention answers *"is the learner
on the task?"*; this module answers *"given that reading, what does the tutor do next?"* -
deterministically, with no model, no camera and no network.

It is deliberately built on :mod:`app.harness.teaching.supervision`, not beside it. The two
answer different questions and are both mounted:

* ``supervision.assess`` - *should the tutor interrupt right now, and with what kind of move?*
  It owns the shared primitives: the idle thresholds (90 s drifting / 300 s away), the
  **notice cooldown** (180 s, so an idle learner is not nagged every tick), **plan-relative
  progress** (elapsed/planned vs work done, not a fixed ``n``), the ``mastery_known`` rule
  (an unknown belief is not a weak one), the difficulty direction, and the participation
  reading.
* this module - the *full spec state machine*: the same core states plus the explicit
  **cheat-check** evidence report, the **staying quiz**, **stay-too-long**, and the
  participation reading on the decision.

Because every shared threshold and reading is imported from ``supervision`` and the state
vocabulary is aligned, the two engines **cannot contradict each other** on the states they
both decide. The consistency is pinned by
``tests/test_classroom.py::test_classroom_and_supervision_agree_on_shared_states``.

The branches, in priority order (first match wins):

1. **Rest** - an allowed break. Never disturb.
2. **Abnormal - other app** - the task window lost focus. Pause the timer, note it.
3. **Cheat check** - strong suspicion, or a quiz with conclusive signals. Evidence for a
   human; the engine never auto-bans.
4. **Away** - idle past 300 s (or the window hidden). A frame that shows work means
   *reading*, not absence. Otherwise notify, run the timeout, and - rest quota spent -
   mark participation; a still-unanswered learner gets a staying quiz.
5. **Drifting** - idle past 90 s but under 300 s. One small, answerable question; never a
   penalty.
6. **Lagging** - behind the session's own plan. Still scrolling -> let them browse; stopped
   -> help.
7. **Stay too long** - far past the expected time on a node. Suggest and note.
8. **Struggling** - active but stuck. Ask whether they need help; once asked, hint + skip.
9. **Active** - continue. The node-memory layer decides explain / ask-reason / hold.

Positive-only and non-punitive: nothing stores a frame, identifies a person or writes a
grade. A cheat check reports evidence (``requires_human_review``); it does not ban.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from .teaching import supervision

# ---------------------------------------------------------------------------
# Thresholds. Shared values are imported from the supervisor so the two
# engines cannot drift apart; classroom-only values live here.
# ---------------------------------------------------------------------------

#: Idle thresholds (shared). 90 s drifting, 300 s away.
IDLE_DRIFTING_SECONDS = supervision.IDLE_DRIFTING_SECONDS
IDLE_AWAY_SECONDS = supervision.IDLE_AWAY_SECONDS
HIDDEN_AWAY_RATIO = supervision.HIDDEN_AWAY_RATIO

#: Do not repeat the same interruption more often than this (shared).
NOTICE_COOLDOWN_SECONDS = supervision.NOTICE_COOLDOWN_SECONDS

#: Plan-relative progress (shared): lagging, and the minimum elapsed time for it to count.
PROGRESS_LAG_RATIO = supervision.PROGRESS_LAG_RATIO
PROGRESS_MIN_ELAPSED_SECONDS = supervision.PROGRESS_MIN_ELAPSED_SECONDS

#: Mastery band (shared): below this is weak, at or above it is strong.
MASTERY_WEAK = supervision.MASTERY_WEAK
MASTERY_STRONG = supervision.MASTERY_STRONG

#: Classroom-only thresholds.
UNHUMAN_SPEED_RATIO = 0.25
STAY_TOO_LONG_RATIO = 2.5
STRUGGLE_ERROR_RATE = 0.50
MIN_SCROLL_FOR_ACTIVE = 3
VISUAL_AUTHORITY = 0.70

PARTICIPATION_TIMEOUT = 0.15
PARTICIPATION_OTHER_APP = 0.10
PARTICIPATION_CHEAT = 0.20

#: The supervisor's vocabulary, plus ``suspicious`` for the cheat check. Aligning the
#: names is what lets a consistency test compare the two engines directly.
STATES = ('working', 'drifting', 'away', 'resting', 'struggling', 'suspicious')
BRANCHES = ('rest', 'abnormal', 'cheat_check', 'away', 'drifting', 'lagging', 'struggling', 'active')
ACTIONS = ('continue', 'notify', 'ask', 'ask_help', 'quiz_stay', 'hint', 'grant_skip',
           'explain', 'ask_reason', 'cheat_check', 'adjust', 'pause')
DIFFICULTY = ('inc', 'dec', 'normal')

#: Actions that speak to the learner; the cooldown suppresses only these.
INTERRUPTIONS = frozenset({'notify', 'ask', 'ask_help', 'hint', 'quiz_stay'})


@dataclass(frozen=True)
class Config:
    """The thresholds, gathered so a caller can replay a decision with different rules."""

    idle_drifting: float = IDLE_DRIFTING_SECONDS
    idle_away: float = IDLE_AWAY_SECONDS
    hidden_away_ratio: float = HIDDEN_AWAY_RATIO
    cooldown_seconds: float = NOTICE_COOLDOWN_SECONDS
    progress_lag_ratio: float = PROGRESS_LAG_RATIO
    progress_min_elapsed: float = PROGRESS_MIN_ELAPSED_SECONDS
    mastery_weak: float = MASTERY_WEAK
    mastery_strong: float = MASTERY_STRONG
    unhuman_speed_ratio: float = UNHUMAN_SPEED_RATIO
    stay_too_long_ratio: float = STAY_TOO_LONG_RATIO
    struggle_error_rate: float = STRUGGLE_ERROR_RATE
    min_scroll_for_active: int = MIN_SCROLL_FOR_ACTIVE
    visual_authority: float = VISUAL_AUTHORITY
    participation_timeout: float = PARTICIPATION_TIMEOUT
    participation_other_app: float = PARTICIPATION_OTHER_APP
    participation_cheat: float = PARTICIPATION_CHEAT


DEFAULT_CONFIG = Config()


@dataclass
class Snapshot:
    """One polling tick's worth of signals. Every field is optional."""

    interval_seconds: float = 30.0
    now: float | None = None
    last_notice_at: float | None = None

    # -- activity --
    idle_seconds: float = 0.0
    active_seconds: float = 0.0
    window_seconds: float = 300.0
    scroll_events: int = 0
    click_events: int = 0
    selection_events: int = 0
    typing_events: int = 0
    hidden_seconds: float = 0.0
    blur_events: int = 0
    attempts: int = 0

    # -- progress --
    progress: float = 0.0
    progress_target: float = 0.60       # fallback when no plan clock is supplied
    elapsed_seconds: float = 0.0        # plan-relative: time spent this session
    planned_seconds: float = 0.0        # plan-relative: planned session length

    # -- rest quota --
    on_break: bool = False
    rest_quota: int = 1

    # -- node / time --
    node_id: str = ''
    seconds_in_node: float = 0.0
    expected_node_seconds: float = 180.0

    # -- node memory --
    node_confidence: float = 0.50
    mastery_known: bool = True          # unknown belief != weak belief

    # -- quiz / suspicion --
    on_quiz: bool = False
    suspicious: bool = False
    very_suspicious: bool = False
    playing_other: bool = False
    answer_speed_ratio: float = 1.0
    answer_latency_seconds: float = 0.0
    personal_average_latency: float = 0.0
    explained_procedure: bool | None = None
    solved_variant: bool | None = None
    ai_trace: bool = False
    camera_suspicion: bool = False

    # -- struggle --
    error_streak: int = 0
    accuracy: float = 1.0
    help_requested: bool = False
    unanswered_reminders: int = 0

    # -- vision (a reading, not a frame) --
    vision_state: str = ''
    vision_confidence: float = 0.0

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> 'Snapshot':
        raw = dict(data or {})

        def num(key: str, default: float = 0.0) -> float:
            value = raw.get(key, default)
            if value is None:
                return default
            try:
                result = float(value)
            except (TypeError, ValueError):
                return default
            return result if result == result and result not in (float('inf'), float('-inf')) else default

        def integer(key: str, default: int = 0) -> int:
            value = raw.get(key, default)
            if value is None:
                return default
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return default

        def boolean(key: str, default: bool = False) -> bool:
            value = raw.get(key, default)
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.strip().lower() in ('1', 'true', 'yes', 'on')
            return bool(value)

        def optional_bool(key: str) -> bool | None:
            if key not in raw or raw[key] is None:
                return None
            return boolean(key)

        def optional_num(key: str) -> float | None:
            if key not in raw or raw[key] is None:
                return None
            return num(key)

        def text(key: str, default: str = '') -> str:
            value = raw.get(key, default)
            return default if value is None else str(value)[:200]

        return cls(
            interval_seconds=num('interval_seconds', 30.0),
            now=optional_num('now'),
            last_notice_at=optional_num('last_notice_at'),
            idle_seconds=num('idle_seconds'),
            active_seconds=num('active_seconds'),
            window_seconds=num('window_seconds', 300.0),
            scroll_events=integer('scroll_events'),
            click_events=integer('click_events'),
            selection_events=integer('selection_events'),
            typing_events=integer('typing_events'),
            hidden_seconds=num('hidden_seconds'),
            blur_events=integer('blur_events'),
            attempts=integer('attempts'),
            progress=num('progress'),
            progress_target=num('progress_target', 0.60),
            elapsed_seconds=num('elapsed_seconds'),
            planned_seconds=num('planned_seconds'),
            on_break=boolean('on_break'),
            rest_quota=integer('rest_quota', 1),
            node_id=text('node_id'),
            seconds_in_node=num('seconds_in_node'),
            expected_node_seconds=num('expected_node_seconds', 180.0),
            node_confidence=num('node_confidence', 0.50),
            mastery_known=boolean('mastery_known', True),
            on_quiz=boolean('on_quiz'),
            suspicious=boolean('suspicious'),
            very_suspicious=boolean('very_suspicious'),
            playing_other=boolean('playing_other'),
            answer_speed_ratio=num('answer_speed_ratio', 1.0),
            answer_latency_seconds=num('answer_latency_seconds'),
            personal_average_latency=num('personal_average_latency'),
            explained_procedure=optional_bool('explained_procedure'),
            solved_variant=optional_bool('solved_variant'),
            ai_trace=boolean('ai_trace'),
            camera_suspicion=boolean('camera_suspicion'),
            error_streak=integer('error_streak'),
            accuracy=num('accuracy', 1.0),
            help_requested=boolean('help_requested'),
            unanswered_reminders=integer('unanswered_reminders'),
            vision_state=text('vision_state'),
            vision_confidence=num('vision_confidence'),
        )


@dataclass
class Decision:
    """What the tutor does next, with the evidence that produced it."""

    branch: str
    state: str
    action: str
    tts: str = ''
    notification: str = ''
    hint: str = ''
    quiz: bool = False
    grant_skip: bool = False
    quiet: bool = False
    participation_penalty: float = 0.0
    difficulty: str = ''
    cheat: dict[str, Any] | None = None
    participation: dict[str, Any] | None = None
    evidence: list[str] = field(default_factory=list)
    timers: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'branch': self.branch,
            'state': self.state,
            'action': self.action,
            'tts': self.tts,
            'notification': self.notification,
            'hint': self.hint,
            'quiz': self.quiz,
            'grant_skip': self.grant_skip,
            'quiet': self.quiet,
            'participation_penalty': round(float(self.participation_penalty), 3),
            'difficulty': self.difficulty,
            'cheat': self.cheat,
            'participation': self.participation,
            'evidence': list(self.evidence)[:8],
            'timers': dict(self.timers),
        }


# ---------------------------------------------------------------------------
# Predicates
# ---------------------------------------------------------------------------

def _activity_count(snap: Snapshot) -> int:
    return (max(0, snap.scroll_events) + max(0, snap.click_events)
            + max(0, snap.selection_events) + max(0, snap.typing_events))


def _has_activity(snap: Snapshot, config: Config) -> bool:
    return _activity_count(snap) >= config.min_scroll_for_active or snap.attempts >= 1


def _signals(snap: Snapshot) -> dict[str, Any]:
    """The subset of signals the supervisor's shared readings need."""
    return {
        'idle_seconds': snap.idle_seconds,
        'window_seconds': snap.window_seconds,
        'active_seconds': snap.active_seconds,
        'hidden_seconds': snap.hidden_seconds,
        'scroll_events': snap.scroll_events,
        'progress': snap.progress,
        'elapsed_seconds': snap.elapsed_seconds,
        'planned_seconds': snap.planned_seconds,
        'mastery': snap.node_confidence,
        'mastery_known': snap.mastery_known,
        'recent_accuracy': snap.accuracy if snap.attempts else -1.0,
        'answer_latency_seconds': snap.answer_latency_seconds,
        'personal_average_latency': snap.personal_average_latency,
    }


def _hidden_ratio(snap: Snapshot) -> float:
    return min(1.0, max(0.0, snap.hidden_seconds) / max(30.0, snap.window_seconds))


def _vision_confirms_work(snap: Snapshot, config: Config) -> bool:
    return snap.vision_state == 'on_task' and snap.vision_confidence >= config.visual_authority


def _is_struggling(snap: Snapshot, config: Config) -> bool:
    if not _has_activity(snap, config):
        return False
    if snap.error_streak >= 2 or snap.accuracy < config.struggle_error_rate:
        return True
    # An unknown belief is not a weak one, so low mastery only counts when it is known.
    return (snap.mastery_known and snap.node_confidence < config.mastery_weak
            and snap.seconds_in_node > snap.expected_node_seconds * 0.5)


def _cheat_reasons(snap: Snapshot, config: Config) -> list[str]:
    reasons: list[str] = []
    if snap.explained_procedure is False:
        reasons.append('Gave the answer but could not explain the method.')
    if snap.solved_variant is False:
        reasons.append('Solved the original but failed a same-concept variant.')
    if snap.answer_speed_ratio < config.unhuman_speed_ratio:
        reasons.append(f'Answer speed is {snap.answer_speed_ratio:.0%} of the expected time '
                       '(inhumanly fast).')
    if snap.ai_trace:
        reasons.append('The answer carries an AI-generation trace.')
    if snap.camera_suspicion:
        reasons.append('The camera check flagged the attempt.')
    return reasons


def _lagging(snap: Snapshot, config: Config) -> tuple[bool, dict[str, Any]]:
    """Plan-relative when a clock is supplied, fixed-threshold otherwise."""
    if snap.elapsed_seconds > 0 and snap.planned_seconds > 0:
        reading = supervision.progress_reading(_signals(snap))
        return bool(reading['lagging']), reading
    lagging = snap.progress < snap.progress_target
    return lagging, {'progress': round(snap.progress, 4), 'expected': round(snap.progress_target, 4),
                     'lag': round(snap.progress_target - snap.progress, 4), 'lagging': lagging,
                     'elapsed_seconds': 0.0, 'planned_seconds': 0.0, 'comparable': False}


def _difficulty(snap: Snapshot, config: Config) -> str:
    if not snap.mastery_known:
        return 'normal'
    reading = supervision.difficulty(_signals(snap))
    return {'up': 'inc', 'down': 'dec'}.get(reading['direction'], 'normal')


# ---------------------------------------------------------------------------
# Decision builders
# ---------------------------------------------------------------------------

def _decision(config: Config, *, branch: str, state: str, action: str,
              **kwargs: Any) -> Decision:
    return Decision(branch=branch, state=state, action=action, **kwargs)


def _rest(config: Config) -> Decision:
    return _decision(
        config, branch='rest', state='resting', action='continue',
        evidence=['The learner is on an allowed break; the tutor stays quiet.'])


def _other_app(config: Config, snap: Snapshot) -> Decision:
    return _decision(
        config, branch='abnormal', state='away', action='pause',
        notification='Timer paused - come back to the lesson when you are ready.',
        participation_penalty=config.participation_other_app,
        evidence=['The task window lost focus to another application.',
                  'The timer is paused and participation is docked; this is a note, not an accusation.'],
        timers={'paused': True})


def _suspicious_ask(config: Config, snap: Snapshot) -> Decision:
    return _decision(
        config, branch='abnormal', state='working', action='ask',
        tts='Show me how you worked that out.',
        notification='Let us check the reasoning together.',
        evidence=['The behaviour is suspicious but not conclusive; ask before concluding.'],
        timers={'stream_correct': True})


def _cheat_check(config: Config, snap: Snapshot, reasons: list[str]) -> Decision:
    items = {
        'answer_speed': {'ratio': round(snap.answer_speed_ratio, 3),
                         'unhuman': snap.answer_speed_ratio < config.unhuman_speed_ratio},
        'procedure': {'explained': snap.explained_procedure,
                      'lock_in_test_shell': True,
                      'ban_candidate': snap.explained_procedure is False},
        'ai_trace': {'detected': bool(snap.ai_trace)},
        'camera': {'suspicious': bool(snap.camera_suspicion)},
        # The engine never bans. It reports evidence for a human review.
        'requires_human_review': True,
    }
    return _decision(
        config, branch='cheat_check', state='suspicious', action='cheat_check',
        notification='Before this counts, please explain how you got your answer.',
        tts='Walk me through your reasoning for that answer.',
        participation_penalty=config.participation_cheat,
        cheat=items,
        evidence=reasons + ['A cheat check gathers evidence; one signal never bans.'],
        timers={'review': 'manual'})


def _unactive(config: Config, snap: Snapshot) -> Decision:
    hidden_ratio = _hidden_ratio(snap)
    evidence = []
    if snap.idle_seconds >= config.idle_away:
        evidence.append(f'No interaction for {snap.idle_seconds:.0f} s '
                        f'(away threshold {config.idle_away:.0f} s).')
    else:
        evidence.append(f'The task window was hidden for {hidden_ratio:.0%} of the sample.')
    if snap.vision_state:
        evidence.append(f'Vision: {snap.vision_state} '
                        f'(confidence {snap.vision_confidence:.2f}).')

    if snap.unanswered_reminders >= 1:
        evidence.append('The reminder went unanswered; a short staying quiz re-engages.')
        return _decision(
            config, branch='away', state='away', action='quiz_stay',
            quiz=True, tts='Let us do a quick check to get you back into it.',
            notification='Quick check to get you back on track.',
            evidence=evidence,
            timers={'unactive_timeout_seconds': config.idle_away})

    if snap.rest_quota <= 0:
        evidence.append('The rest quota is spent; the timeout counts against participation.')
        return _decision(
            config, branch='away', state='away', action='notify',
            tts='Are you still with me?',
            notification='You have been away a while - are you still there?',
            participation_penalty=config.participation_timeout,
            evidence=evidence,
            timers={'unactive_timeout_seconds': config.idle_away})

    evidence.append('The learner still has rest quota; remind gently and do not penalise.')
    return _decision(
        config, branch='away', state='away', action='notify',
        tts='Are you still there?',
        notification='Still there? Take a short break if you need one.',
        evidence=evidence,
        timers={'unactive_timeout_seconds': config.idle_away})


def _drifting(config: Config, snap: Snapshot) -> Decision:
    return _decision(
        config, branch='drifting', state='drifting', action='ask',
        tts='What do you expect the next step to be?',
        evidence=[f'No interaction for {snap.idle_seconds:.0f} s '
                  f'(drifting threshold {config.idle_drifting:.0f} s).',
                  'One small answerable question re-enters the task without an accusation.'])


def _memory_layer(decision: Decision, snap: Snapshot, config: Config) -> Decision:
    """Refine a teaching action by what node memory believes about this concept."""
    if decision.branch in ('rest', 'abnormal', 'cheat_check', 'away', 'drifting'):
        return decision

    if not snap.mastery_known:
        decision.evidence.append(
            'No attempts recorded on this concept, so the belief is unknown; hold the band '
            'rather than treat it as weak.')
        return decision

    if snap.on_quiz and snap.node_confidence < config.mastery_weak:
        decision.grant_skip = True
        decision.evidence.append('Node memory confidence is low; on a quiz this node may be skipped.')

    if snap.node_confidence < config.mastery_weak and decision.action in ('continue', 'ask_help', 'hint'):
        decision.action = 'explain'
        decision.tts = 'Let me explain this once more, step by step.'
        decision.evidence.append(
            f'Node memory confidence is low ({snap.node_confidence:.2f}); explain rather than advance.')
    elif snap.node_confidence >= config.mastery_strong and decision.action == 'continue':
        decision.action = 'ask_reason'
        decision.tts = 'Explain back to me why that works.'
        decision.evidence.append(
            f'Node memory confidence is strong ({snap.node_confidence:.2f}); '
            'ask the learner to reason aloud.')
    return decision


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------

def _core(snap: Snapshot, config: Config) -> Decision:
    if snap.on_break:
        return _rest(config)

    if snap.playing_other:
        return _other_app(config, snap)

    reasons = _cheat_reasons(snap, config)
    if snap.very_suspicious or (snap.on_quiz and reasons):
        return _cheat_check(config, snap, reasons)
    if snap.suspicious:
        return _suspicious_ask(config, snap)

    # Away: idle past the away threshold, or the window hidden for most of the sample.
    if snap.idle_seconds >= config.idle_away or _hidden_ratio(snap) >= config.hidden_away_ratio:
        if _vision_confirms_work(snap, config):
            return _decision(
                config, branch='active', state='working', action='continue',
                evidence=['No recent input, but the work is visible in the frame; '
                          'treat this as reading, not absence.'])
        return _unactive(config, snap)

    # Drifting: interaction stopped, but not long enough to be an absence.
    if snap.idle_seconds >= config.idle_drifting:
        return _drifting(config, snap)

    # Lagging: behind the plan. Still browsing -> allow; stopped -> help.
    lagging, reading = _lagging(snap, config)
    if lagging:
        if _has_activity(snap, config):
            return _memory_layer(_decision(
                config, branch='lagging', state='working', action='continue',
                evidence=[f'Behind the plan (lag {reading["lag"]:.0%}) but still scrolling; '
                          'allow it.'],
                difficulty='dec' if reading['lag'] >= 0.5 else 'normal',
                timers={'progress': reading}), snap, config)
        return _memory_layer(_decision(
            config, branch='lagging', state='struggling', action='ask_help',
            tts='Want a nudge to move forward?',
            evidence=[f'Behind the plan (lag {reading["lag"]:.0%}) and not scrolling.'],
            difficulty='dec',
            timers={'progress': reading}), snap, config)

    # Stay too long on one node.
    if snap.seconds_in_node > snap.expected_node_seconds * config.stay_too_long_ratio:
        return _memory_layer(_decision(
            config, branch='struggling', state='struggling', action='hint',
            notification='You have been on this step a while - here is a hint.',
            hint='Re-read the step and try the next small part; you do not have to finish it '
                 'all at once.',
            evidence=[f'This node has taken {snap.seconds_in_node:.0f} s, well past the '
                      f'{snap.expected_node_seconds:.0f} s expected.'],
            difficulty='dec'), snap, config)

    # Struggling: active but stuck.
    if _is_struggling(snap, config):
        if snap.help_requested:
            return _memory_layer(_decision(
                config, branch='struggling', state='struggling', action='hint',
                hint='Start from the part you are sure of and take the next single step.',
                grant_skip=True,
                evidence=['The learner asked for help; give a hint and grant a skip of this node.'],
                difficulty='dec'), snap, config)
        return _memory_layer(_decision(
            config, branch='struggling', state='struggling', action='ask_help',
            tts='Do you need help with this part?',
            evidence=['Active, but the evidence suggests the learner is stuck.'],
            difficulty='dec'), snap, config)

    return _memory_layer(_decision(
        config, branch='active', state='working', action='continue',
        evidence=['The learner is active and on track.'],
        difficulty=_difficulty(snap, config)), snap, config)


def evaluate(snapshot: Snapshot | Mapping[str, Any] | None, config: Config | None = None) -> Decision:
    """Turn one polling tick into one teaching decision.

    The order of the checks *is* the policy, stated at the top of this module. The output
    is deterministic and offline. ``quiet`` is set when an interruption falls inside the
    supervisor's notice cooldown, so a client does not repeat itself every tick; safety
    actions (pause, cheat check) are never silenced.
    """
    cfg = config or DEFAULT_CONFIG
    snap = snapshot if isinstance(snapshot, Snapshot) else Snapshot.from_mapping(snapshot)

    decision = _core(snap, cfg)
    decision.participation = supervision.participation(_signals(snap))

    if decision.action in INTERRUPTIONS and snap.last_notice_at is not None:
        now = snap.now if snap.now is not None else time.time()
        try:
            elapsed = now - float(snap.last_notice_at)
        except (TypeError, ValueError):
            elapsed = cfg.cooldown_seconds
        if elapsed < cfg.cooldown_seconds:
            decision.quiet = True
            decision.evidence.append(
                f'Within the {cfg.cooldown_seconds:.0f} s notice cooldown; do not repeat the '
                'interruption.')
    return decision


def describe(config: Config | None = None) -> dict[str, Any]:
    """The engine's posture, for ``/api/v1/harness/status`` and the transparency panel."""
    cfg = config or DEFAULT_CONFIG
    return {
        'states': list(STATES),
        'branches': list(BRANCHES),
        'actions': list(ACTIONS),
        'difficulty': list(DIFFICULTY),
        'thresholds': {
            'idle_drifting_seconds': cfg.idle_drifting,
            'idle_away_seconds': cfg.idle_away,
            'hidden_away_ratio': cfg.hidden_away_ratio,
            'cooldown_seconds': cfg.cooldown_seconds,
            'progress_lag_ratio': cfg.progress_lag_ratio,
            'progress_min_elapsed_seconds': cfg.progress_min_elapsed,
            'mastery_weak': cfg.mastery_weak,
            'mastery_strong': cfg.mastery_strong,
            'unhuman_speed_ratio': cfg.unhuman_speed_ratio,
            'stay_too_long_ratio': cfg.stay_too_long_ratio,
            'min_scroll_for_active': cfg.min_scroll_for_active,
            'visual_authority': cfg.visual_authority,
        },
        'participation_penalties': {
            'timeout': cfg.participation_timeout,
            'other_app': cfg.participation_other_app,
            'cheat': cfg.participation_cheat,
        },
        'shared_with_supervision': [
            'idle thresholds (90 s / 300 s)', 'hidden-window ratio', 'notice cooldown (180 s)',
            'plan-relative progress', 'mastery band (0.45 / 0.80)', 'mastery_known',
            'difficulty direction', 'participation reading'],
        'posture': ('Deterministic and offline: a snapshot always yields the same decision. '
                    'No frame is stored, no grade is written, and the cheat check never '
                    'auto-bans.'),
    }
