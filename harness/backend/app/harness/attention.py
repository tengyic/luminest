"""Whether the learner is working on the task: an evidence reading, not surveillance.

The request was to "monitor if the student is doing the task". That sentence can be built
two ways, and the difference is the whole module.

**The version this is not.** A camera pointed at a child, frames uploaded, a model asked
"is this student paying attention?", a score written to a record that follows them. That
product is a facial-analysis system with a tutor attached: it is wrong more often for
disabled learners, it fails silently for anyone whose face is not centred, and it turns a
teaching decision into an accusation. It is also, in a growing number of jurisdictions,
illegal to run on minors without a specific consent process.

**The version this is.** A reading assembled from signals the client already has - whether
the window was visible, how long since the last interaction, how many attempts were made -
plus, when the learner has opted in and a snapshot exists, a *visual check of the work*
rather than of the face. The output is a **state, its evidence, and a teaching move**. It is
never a grade, never a discipline record, and never a claim about a person's character.

The rules that make that true, and that a reader can check:

* **Opt-in, per instance.** ``HARNESS_ATTENTION_MONITOR`` decides whether the feature
  exists at all. Off means a refusal that names the switch, not a silent no-op.
* **Frames are not stored.** The image is read in the request that carries it. What is
  returned - and all a caller may persist - is a state, a confidence, evidence sentences
  and per-image digests. :data:`PRIVACY` states this in the payload itself so a client
  cannot quietly keep the picture and claim the guarantee.
* **The face is not the subject.** The visual question is about the *work in the frame*
  (is there an attempt on screen, does it match the task), and the observer prompt in
  :mod:`app.harness.vla` forbids identifying anyone.
* **Disagreement is reported, not resolved.** When the telemetry and the picture point
  different ways the answer is ``unclear`` with both readings, because a confident wrong
  verdict here costs a learner their trust in the whole system.
* **No punitive move exists.** Every ``suggested_action`` is something a teacher would do
  next: ask a question, shrink the step, offer a break. There is no branch that reports,
  flags or blocks.

The telemetry path is deterministic and works with no model at all, which is the same
posture as the rest of the harness: the feature is real offline, and a model improves it
rather than being required for it.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from . import vla

#: The reading. Deliberately coarse: four states a teacher would recognise.
STATES = ('on_task', 'drifting', 'off_task', 'unclear')

#: The window a reading describes, in seconds. Five minutes is long enough for a stable
#: telemetry ratio and short enough that a learner who just got up is not still "drifting".
DEFAULT_WINDOW_SECONDS = 300.0

#: Thresholds. Named rather than inlined because they are the reviewable part of this
#: module: a reader can disagree with 240 s and change one number.
IDLE_OFF_TASK_SECONDS = 240.0
IDLE_DRIFTING_SECONDS = 90.0
HIDDEN_OFF_TASK_RATIO = 0.60
HIDDEN_DRIFTING_RATIO = 0.25
BLUR_DRIFTING_EVENTS = 4

#: The visual check only overrides telemetry at or above this confidence. Below it the
#: picture is a second opinion, not a verdict.
VISUAL_AUTHORITY = 0.70

#: What a caller may keep. Stated in the payload so the guarantee travels with the data.
PRIVACY = {
    'frames_stored': False,
    'stored': 'the state, its confidence, evidence sentences and per-image digests',
    'opt_in': 'HARNESS_ATTENTION_MONITOR',
    'learner_visible': True,
    'used_for_grading': False,
    'identifies_people': False,
    'subject': 'the work in the frame, never the face',
}

VISUAL_INSTRUCTION = (
    'Look at this frame of a learner\'s screen and answer only about the work visible in '
    'it. Do not describe or identify any person, and do not read anything that is not part '
    'of the task. Reply with one JSON object and nothing else:\n'
    '{"work_visible": true|false, '
    '"attempt_visible": true|false, '
    '"matches_task": "yes"|"partly"|"no"|"cannot_tell", '
    '"evidence": ["one short sentence per observation"], '
    '"confidence": 0.0-1.0}\n'
    'The task is: {task}'
)


def available(settings) -> bool:
    return bool(getattr(settings, 'attention_monitor', False))


def status(settings) -> tuple[bool, str]:
    """(ready, sentence) for the capability probe. Never raises."""
    if not available(settings):
        return False, ('On-task monitoring is switched off for this instance '
                       '(HARNESS_ATTENTION_MONITOR=0).')
    vision, note = vla.vision_status(settings)
    if vision:
        return True, 'Telemetry and the visual work check are both available.'
    return True, ('Telemetry only: ' + note)


def _number(signals: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    try:
        value = float(signals.get(key, default) or default)
    except (TypeError, ValueError):
        return default
    return value if value == value and value not in (float('inf'), float('-inf')) else default


def telemetry(signals: Mapping[str, Any] | None) -> dict[str, Any]:
    """The deterministic reading, from signals the client already has.

    Every threshold is in this module's constants, so the reading is reproducible and can
    be argued with. Nothing here needs a model, a camera or the network.
    """
    signals = dict(signals or {})
    window = max(30.0, min(_number(signals, 'window_seconds', DEFAULT_WINDOW_SECONDS), 3600.0))
    idle = max(0.0, _number(signals, 'idle_seconds'))
    hidden = max(0.0, min(_number(signals, 'hidden_seconds'), window))
    active = max(0.0, min(_number(signals, 'active_seconds'), window))
    blurs = max(0, int(_number(signals, 'blur_events')))
    attempts = max(0, int(_number(signals, 'attempts')))
    hidden_ratio = hidden / window

    evidence: list[str] = []
    if idle >= IDLE_OFF_TASK_SECONDS:
        state = 'off_task'
        evidence.append(f'No interaction for {idle:.0f} s (threshold {IDLE_OFF_TASK_SECONDS:.0f} s).')
    elif hidden_ratio >= HIDDEN_OFF_TASK_RATIO:
        state = 'off_task'
        evidence.append(f'The task window was not visible for {hidden_ratio:.0%} of the '
                        f'last {window:.0f} s (threshold {HIDDEN_OFF_TASK_RATIO:.0%}).')
    elif idle >= IDLE_DRIFTING_SECONDS:
        state = 'drifting'
        evidence.append(f'No interaction for {idle:.0f} s (threshold {IDLE_DRIFTING_SECONDS:.0f} s).')
    elif hidden_ratio >= HIDDEN_DRIFTING_RATIO:
        state = 'drifting'
        evidence.append(f'The task window was hidden for {hidden_ratio:.0%} of the window.')
    elif blurs >= BLUR_DRIFTING_EVENTS:
        state = 'drifting'
        evidence.append(f'Focus left the task {blurs} times in the window.')
    elif attempts >= 1 and idle < 60:
        state = 'on_task'
        evidence.append(f'{attempts} attempt(s) in the window, last one {idle:.0f} s ago.')
    elif active >= 0.5 * window:
        state = 'on_task'
        evidence.append(f'{active:.0f} s of interaction in a {window:.0f} s window.')
    else:
        state = 'unclear'
        evidence.append('Too little interaction to read: no attempt and under half the '
                        'window active.')

    # Confidence is a statement about the evidence, not about the learner. A single strong
    # signal is more trustworthy than several weak ones.
    strength = 0.0
    if state == 'off_task':
        strength = 0.85 if idle >= IDLE_OFF_TASK_SECONDS * 1.5 or hidden_ratio >= 0.8 else 0.7
    elif state == 'drifting':
        strength = 0.6
    elif state == 'on_task':
        strength = 0.75 if attempts >= 2 else 0.6
    else:
        strength = 0.3
    return {'state': state, 'confidence': strength, 'evidence': evidence,
            'signals': {'window_seconds': window, 'idle_seconds': idle,
                        'hidden_ratio': round(hidden_ratio, 4), 'active_seconds': active,
                        'blur_events': blurs, 'attempts': attempts}}


def _visual(settings, task: str, snapshot: str) -> dict[str, Any] | None:
    """The picture's opinion of the work, or ``None`` when it cannot be had."""
    if not snapshot or not vla.vision_ready(settings):
        return None
    parsed = vla.read_json(settings, [snapshot], VISUAL_INSTRUCTION.replace('{task}', task))
    if not parsed:
        return None
    matches = str(parsed.get('matches_task') or 'cannot_tell').strip().casefold()
    work = bool(parsed.get('work_visible'))
    attempt = bool(parsed.get('attempt_visible'))
    if matches == 'yes' and work:
        state = 'on_task'
    elif matches == 'no':
        state = 'off_task'
    elif matches == 'partly' or (work and not attempt):
        state = 'drifting'
    else:
        state = 'unclear'
    try:
        confidence = max(0.0, min(float(parsed.get('confidence') or 0.0), 1.0))
    except (TypeError, ValueError):
        confidence = 0.0
    evidence = [str(item)[:240] for item in (parsed.get('evidence') or []) if str(item).strip()][:4]
    return {'state': state, 'confidence': confidence, 'evidence': evidence,
            'matches_task': matches, 'work_visible': work, 'attempt_visible': attempt}


def assess(settings, *, task: str, signals: Mapping[str, Any] | None = None,
           snapshot: str = '', history: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """One reading of whether the learner is on the task, with its evidence and a move.

    ``snapshot`` is an optional ``data:`` URL of the work area. It is read in this call and
    never written anywhere; see :data:`PRIVACY`.
    """
    if not available(settings):
        return {'ok': False, 'state': 'unclear', 'enabled': False,
                'refused': ('On-task monitoring is switched off for this instance. An '
                            'operator turns it on with HARNESS_ATTENTION_MONITOR=1.'),
                'privacy': dict(PRIVACY)}

    task = (task or '').strip()
    if not task:
        return {'ok': False, 'state': 'unclear', 'enabled': True,
                'refused': 'The task is required: a reading without the task cannot say '
                           'whether the work matches it.',
                'privacy': dict(PRIVACY)}

    telemetry_reading = telemetry(signals)
    visual_reading = _visual(settings, task, snapshot) if snapshot else None

    notes: list[str] = []
    if snapshot and visual_reading is None:
        notes.append('A snapshot was supplied but no visual reading was possible '
                     '(no vision model, or the reply was unusable); the telemetry stands alone.')

    if visual_reading and visual_reading['confidence'] >= VISUAL_AUTHORITY:
        if visual_reading['state'] == telemetry_reading['state']:
            state = visual_reading['state']
            confidence = min(0.95, max(visual_reading['confidence'],
                                        telemetry_reading['confidence']) + 0.1)
            evidence = telemetry_reading['evidence'] + visual_reading['evidence']
        elif telemetry_reading['state'] == 'unclear':
            state = visual_reading['state']
            confidence = visual_reading['confidence']
            evidence = visual_reading['evidence']
            notes.append('Telemetry was inconclusive; the work in the frame decided the reading.')
        else:
            state = 'unclear'
            confidence = 0.35
            evidence = (telemetry_reading['evidence'] + visual_reading['evidence'])
            notes.append('The telemetry and the picture disagree, so this is reported as '
                         'unclear rather than resolved in either direction.')
    elif visual_reading:
        state = telemetry_reading['state']
        confidence = min(telemetry_reading['confidence'], 0.6)
        evidence = telemetry_reading['evidence'] + visual_reading['evidence']
        notes.append(f'The visual check was below {VISUAL_AUTHORITY:.0%} confidence, so it '
                     'is reported as a second opinion and does not decide the reading.')
    else:
        state = telemetry_reading['state']
        confidence = telemetry_reading['confidence']
        evidence = list(telemetry_reading['evidence'])

    return {
        'ok': True,
        'enabled': True,
        'state': state if state in STATES else 'unclear',
        'confidence': round(float(confidence), 3),
        'evidence': evidence[:6],
        'suggested_action': SUGGESTED_ACTIONS[state if state in STATES else 'unclear'],
        'dimensions': {'telemetry': telemetry_reading, 'visual': visual_reading},
        'trend': _trend(history, state),
        'notes': notes,
        'privacy': dict(PRIVACY),
    }


#: Every move is something a teacher does next. None of them reports, flags or blocks.
SUGGESTED_ACTIONS = {
    'on_task': 'Continue. Do not interrupt a working learner.',
    'drifting': ('Shrink the next step and ask for a prediction: "what do you expect the '
                 'next line to be?" A short, answerable question re-enters the task '
                 'without an accusation.'),
    'off_task': ('Pause the timer and ask one question about where they got to, then offer '
                 'a two-minute break if the session is already long. Do not accuse; the '
                 'reading may be a device that slept.'),
    'unclear': ('Ask the learner to say in one sentence what they are working on. Do not '
                'accuse, and do not change the task on the strength of this reading.'),
}


def _trend(history: Sequence[Mapping[str, Any]], state: str) -> dict[str, Any]:
    """Whether this reading continues a run. A single reading is not a pattern."""
    recent = [str(entry.get('state') or '') for entry in list(history)[-5:] if isinstance(entry, Mapping)]
    same = 0
    for previous in reversed(recent):
        if previous != state:
            break
        same += 1
    return {'previous': recent[-1] if recent else None, 'same_state_in_a_row': same,
            'note': ('A single reading is not a pattern; three in a row is the smallest '
                     'run worth acting on.' if same < 2 else
                     'This state has now repeated; the suggested move is worth making.')}


def describe(settings) -> dict[str, Any]:
    """The posture, for ``/api/v1/harness/status`` and the transparency panel."""
    ready, note = status(settings)
    return {'enabled': available(settings), 'ready': ready, 'note': note,
            'states': list(STATES), 'thresholds': {
                'idle_off_task_seconds': IDLE_OFF_TASK_SECONDS,
                'idle_drifting_seconds': IDLE_DRIFTING_SECONDS,
                'hidden_off_task_ratio': HIDDEN_OFF_TASK_RATIO,
                'hidden_drifting_ratio': HIDDEN_DRIFTING_RATIO,
                'blur_drifting_events': BLUR_DRIFTING_EVENTS,
                'visual_authority': VISUAL_AUTHORITY},
            'privacy': dict(PRIVACY),
            'suggested_actions': dict(SUGGESTED_ACTIONS)}
