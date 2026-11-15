"""Probing a learner while they use the product, without turning practice into a test.

The design problem
------------------
Measuring learning from inside the thing being measured is circular unless the measurement
condition differs from the practice condition. The harness's practice mode gives feedback
after every answer, offers the lesson text, and has a tutor one message away. Accuracy under
those conditions measures *performance with support*, and the 2024 evidence says that
quantity can go up while learning goes down.

So a probe is not "another question". A probe is a deliberately **different condition**,
inserted into normal use, whose defining property is that the support has been removed:
no feedback until it is over, no lesson text on screen, and no tutor turn in the window.
Only observations from that condition enter the unaided bucket, which is the bucket every
honest efficiency figure is computed from.

Why the learner is told, and told plainly
-----------------------------------------
The probe is surfaced as what it is: *a quick recall check with no hints and no feedback*.
That is not a euphemism, it is the accurate description, and it is also a real
pedagogical activity - retrieval practice with delayed feedback is one of the
best-evidenced study techniques there is (Karpicke & Roediger 2008). So the learner is
doing something that genuinely helps them, and the harness is measuring it. Hiding the
nature of the task would be deception and would also break the measurement: a learner who
believes they are being tested behaves differently from one who believes they are
practising (the Hawthorne effect, and pretest sensitization).

What is *not* said, because it would corrupt the reading, is how any particular answer
affects their mastery estimate. That is a property of the record, not of the interaction.

The three probes
----------------
* **cold** - one unaided retrieval. Measures storage strength. This is the only probe whose
  results can support the word "learning".
* **effort** - the Paas (1992) single-item 9-point mental-effort rating, one tap, after a
  sitting. Measures the *cost* side of efficiency, and is the cheapest usable cognitive-load
  instrument.
* **retained** - the 7-day / 28-day delayed test the harness already schedules. Measures
  what survived, which is the question a within-session score cannot answer.

Budget, because unbounded probing is intrusive
----------------------------------------------
At most one cold probe per sitting, and at most one every :data:`PROBE_COOLDOWN_MINUTES`.
A harness that interrupts every third question to check up on the learner has replaced
teaching with assessment, and the learner will start practising for the probe - which
changes the very behaviour it is trying to observe.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

#: Minimum gap between cold probes. Long enough that a learner meets at most one in a normal
#: sitting, so the probe stays a change of mode rather than the mode itself.
PROBE_COOLDOWN_MINUTES = 20

#: At most one cold probe per episode, regardless of the cooldown. Two in one sitting doubles
#: the interruption and adds almost no information - the second is a retest minutes after the
#: first, which measures the first.
MAX_COLD_PROBES_PER_EPISODE = 1

#: Practice observations a concept needs before probing it is informative. Before this, the
#: "unaided" reading is not a gap against anything - the learner has barely seen the idea -
#: and a low score would be misread as weak retention instead of first exposure.
MIN_PRACTICE_BEFORE_PROBE = 3

#: The Paas rating scale. One item, nine points, administered immediately after the task.
#: Anchors are part of the instrument, not decoration: without them the numbers are not
#: comparable between learners.
EFFORT_SCALE = {
    'min': 1,
    'max': 9,
    'low_anchor': 'very, very low mental effort',
    'high_anchor': 'very, very high mental effort',
    'instrument': 'Paas (1992) single-item subjective mental-effort scale',
}

#: The conditions a probe must hold, stated once so the scheduler, the route and the tests
#: all read them from the same place.
COLD_PROBE_CONDITIONS = (
    'No feedback is shown until the probe is submitted.',
    'No lesson text is on screen while it is answered.',
    'No tutor turn occurs between the probe being issued and answered.',
    'The item has not been answered within the recognition window, so the answer cannot '
    'be recognised rather than recalled.',
)

PROBE_SPECS: dict[str, dict[str, Any]] = {
    'cold': {
        'title': 'Cold retrieval check',
        'measures': 'Storage strength under the same conditions as an unaided test.',
        'why': 'Feedback, lesson text and a tutor all raise measured accuracy while leaving '
               'what is retained unchanged or worse (Soderstrom & Bjork 2015; Bastani et al. '
               '2024 found practice +48% and unaided exam -17%). Only an unsupported answer '
               'separates the two.',
        'learner_facing': 'A quick recall check: no hints, no feedback until you finish.',
        'burden_seconds': 45,
    },
    'effort': {
        'title': 'Mental-effort rating',
        'measures': 'The cost side of instructional efficiency (Paas & van Merriënboer 1993).',
        'why': 'Efficiency is result per unit of invested effort. Without an effort reading, '
               'a harness can only report that a learner improved, not whether the '
               'improvement was cheap or expensive - and those call for opposite responses.',
        'learner_facing': 'How much mental effort did that take? (1 = very low, 9 = very high)',
        'burden_seconds': 5,
    },
    'retained': {
        'title': 'Delayed retention check',
        'measures': 'What survived a delay of 7 or 28 days.',
        'why': 'Retention is the outcome that matters and the one a within-session score '
               'cannot see. The delays are the ones the harness already uses for transfer.',
        'learner_facing': 'A short check on material from a while back.',
        'burden_seconds': 300,
    },
}


def describe() -> dict[str, Any]:
    """The probe programme, for a transparency panel and for the API's own documentation."""
    return {
        'probes': PROBE_SPECS,
        'cooldown_minutes': PROBE_COOLDOWN_MINUTES,
        'max_per_episode': MAX_COLD_PROBES_PER_EPISODE,
        'min_practice_before_probe': MIN_PRACTICE_BEFORE_PROBE,
        'cold_probe_conditions': list(COLD_PROBE_CONDITIONS),
        'effort_scale': EFFORT_SCALE,
        'budget_note': (
            'Probing is rate-limited on purpose. A harness that checks the learner every few '
            'questions has replaced practice with assessment, and a learner who expects a '
            'probe starts practising for it - which changes the behaviour being observed.'
        ),
        'scope_note': (
            'A cold probe is a real retrieval-practice activity with delayed feedback, '
            'presented as such. The harness does not hide that it is measuring; it does not '
            'say how any particular answer changes the learner\'s mastery estimate, because '
            'that would change the answer.'
        ),
    }


def cold_probe_decision(*, minutes_since_last: float | None,
                        probes_this_episode: int,
                        practice_by_concept: Mapping[str, int],
                        seen_recently: Iterable[str] = (),
                        blocked: bool = False) -> dict[str, Any]:
    """Whether to insert a cold probe now, which concept, and why not if not.

    Pure: every input is supplied by the caller, so the policy can be tested exhaustively and
    the same decision can be replayed from stored signals. Inputs are the *minimum* set that
    changes the answer - nothing here reads the clock or the database.

    ``blocked`` covers the conditions under which a probe would corrupt something else: an
    exam in progress, an assessment already covering the full curriculum, or a learner who
    has asked not to be interrupted.
    """
    if blocked:
        return {'due': False, 'reason': 'blocked', 'concept_id': None,
                'why': 'An assessment is in progress or the learner has paused prompting; '
                       'inserting a probe now would corrupt it and intrude.'}
    if probes_this_episode >= MAX_COLD_PROBES_PER_EPISODE:
        return {'due': False, 'reason': 'already_probed_this_episode', 'concept_id': None,
                'why': 'One cold probe per sitting is the budget. A second one minutes later '
                       'mostly measures the first.'}
    if minutes_since_last is not None and minutes_since_last < PROBE_COOLDOWN_MINUTES:
        remaining = round(PROBE_COOLDOWN_MINUTES - minutes_since_last, 1)
        return {'due': False, 'reason': 'cooldown', 'concept_id': None,
                'remaining_minutes': remaining,
                'why': f'Last cold probe was {minutes_since_last:.0f} minutes ago; the '
                       f'cooldown has {remaining:.0f} minutes left.'}
    seen = {str(value) for value in seen_recently}
    eligible = {concept: count for concept, count in practice_by_concept.items()
                if count >= MIN_PRACTICE_BEFORE_PROBE and str(concept) not in seen}
    if not eligible:
        return {'due': False, 'reason': 'no_eligible_concept', 'concept_id': None,
                'why': f'No concept has both {MIN_PRACTICE_BEFORE_PROBE} practice attempts and '
                       'an item the learner has not just seen.'}
    # Most-practised first: the concept with the most evidence has the most to be checked
    # against, and a probe there is also the most useful retrieval practice. Ties break on
    # the concept id so the choice is reproducible rather than dict-order dependent.
    concept = max(sorted(eligible), key=lambda key: eligible[key])
    return {'due': True, 'reason': 'eligible', 'concept_id': concept,
            'practice_attempts': eligible[concept],
            'conditions': list(COLD_PROBE_CONDITIONS),
            'why': f'{concept} has {eligible[concept]} practice attempts and no recent '
                   'exposure to a probe item, so an unaided answer there is informative.',
            'spec': PROBE_SPECS['cold']}


def effort_decision(*, answered_this_episode: int, asked_this_episode: int,
                    minutes_since_last: float | None) -> dict[str, Any]:
    """Whether to ask for an effort rating. One per sitting, and not a bare one.

    Requires a minimum amount of work to have happened, because "how much effort did that
    take" about a single answer is unanswerable and a learner asked it will produce a number
    to end the prompt. Ratings collected that way are worse than no ratings: they look like
    data.
    """
    if asked_this_episode >= 1:
        return {'due': False, 'reason': 'already_asked', 'why': 'One rating per sitting.'}
    if answered_this_episode < MIN_PRACTICE_BEFORE_PROBE:
        return {'due': False, 'reason': 'too_little_work',
                'needed': MIN_PRACTICE_BEFORE_PROBE - answered_this_episode,
                'why': 'An effort rating needs enough work behind it to be about something.'}
    if minutes_since_last is not None and minutes_since_last < PROBE_COOLDOWN_MINUTES:
        return {'due': False, 'reason': 'cooldown',
                'why': 'Another micro-probe was asked recently; they are spaced apart so the '
                       'sitting is not a survey.'}
    return {'due': True, 'reason': 'eligible', 'scale': EFFORT_SCALE,
            'spec': PROBE_SPECS['effort']}


def coverage(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """How much probing has actually happened, and how much of it is usable.

    Reported next to every efficiency figure. An instrument that cannot say how often it has
    been applied is not an instrument, and the failure this prevents is subtle: a report built
    on four cold probes looks exactly like one built on four hundred until someone asks.
    """
    by_kind: dict[str, dict[str, int]] = {}
    for record in records:
        kind = str(record.get('kind') or 'unknown')
        row = by_kind.setdefault(kind, {'issued': 0, 'completed': 0, 'abandoned': 0})
        row['issued'] += 1
        status = str(record.get('status') or '')
        if status == 'completed':
            row['completed'] += 1
        elif status == 'abandoned':
            row['abandoned'] += 1
    total = sum(row['completed'] for row in by_kind.values())
    abandoned = sum(row['abandoned'] for row in by_kind.values())
    issued = sum(row['issued'] for row in by_kind.values())
    return {
        'by_kind': by_kind,
        'issued': issued,
        'completed': total,
        'abandoned': abandoned,
        'completion_rate': round(total / issued, 4) if issued else None,
        'note': ('A low completion rate is a design problem, not a learner problem: probes '
                 'that get abandoned are probing at the wrong moment.'),
    }


__all__ = ['COLD_PROBE_CONDITIONS', 'EFFORT_SCALE', 'MAX_COLD_PROBES_PER_EPISODE',
           'MIN_PRACTICE_BEFORE_PROBE', 'PROBE_COOLDOWN_MINUTES', 'PROBE_SPECS',
           'cold_probe_decision', 'coverage', 'describe', 'effort_decision']
