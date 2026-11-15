"""What this harness is allowed to call a measurement, and what it is not.

The problem this package exists to solve
----------------------------------------
The harness could already answer "how many questions did I get right", which is a
*performance* number. It could not answer "am I learning efficiently", which is a
different question, and the difference is not cosmetic. Soderstrom & Bjork (2015)
show that performance during acquisition and durable learning can move in opposite
directions: conditions that raise in-session accuracy - feedback, worked support, a
tutor that will just tell you - often lower what survives to a later unaided test.
Bastani et al. (2024) measured exactly this with an LLM tutor: practice accuracy
+48% with plain GPT-4, unaided exam performance **-17%** against control.

So a system that reports progress from practice accuracy alone will confidently
report the wrong thing, and it will report it most strongly for the learners who
are being helped the most. Every number in this package therefore has to survive
one question: *was help available when this was measured?*

The three commitments
---------------------
1. **Aid is recorded, not assumed.** Every observation carries the support that was
   present when it was made. An observation with unknown support is reported as
   unknown, never pooled into the aided or the unaided bucket to make a sample size.
2. **A single learner is enough to measure rate, not level.** Level ("how good am I
   at fractions") needs a normed scale and many people. Rate ("how fast does my error
   fall with practice") is a within-person slope and is identified from one person's
   own sequence. This is why the headline efficiency metric is a slope, and it is the
   same reason Cen, Koedinger & Junker (2006) prefer it to pretest-posttest gain: the
   slope does not move when the starting point does.
3. **Insufficient evidence is a result.** Below :data:`MIN_OPPORTUNITIES` a rate
   estimate is not a noisy version of the truth, it is unidentified. The estimators
   return ``status='insufficient_evidence'`` with the shortfall named, rather than a
   number that will be read as a finding.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

#: Consecutive attempts further apart than this start a new episode. 15 minutes is the
#: conventional session-boundary value in learning analytics (half of the 30-minute
#: standard sessionization cut; short enough that two sittings are never merged, long
#: enough that thinking about a hard problem does not split one sitting in two).
EPISODE_GAP_SECONDS = 900.0

#: A gap between attempts longer than this is treated as *not engaged*: reading, thinking
#: and re-working count, but a gap the length of a coffee break does not. Time-on-task
#: that silently includes idle time inflates every efficiency ratio computed from it,
#: and it inflates them most for the learner who walks away most often.
IDLE_CAP_SECONDS = 120.0

#: How long an item must have been out of sight before a correct answer on it counts as
#: retrieval rather than recognition. Within this window the learner may be reproducing
#: an answer they saw minutes ago, which is memory of the interface, not of the idea.
RECOGNITION_WINDOW_HOURS = 24.0

#: Opportunities on one concept needed before a learning-rate estimate is reported.
#: Below roughly this many, an exponential decay can be fit to almost any monotone noise
#: and the half-life is dominated by the prior. The research convention is 8-10.
MIN_OPPORTUNITIES = 8

#: Opportunities needed before the *aided-minus-unaided* gap is reported. This is the one
#: metric that must be honest about power: with two unaided observations a gap is a coin
#: flip, and reporting it would manufacture the most alarming number in the product.
MIN_UNAIDED_OBSERVATIONS = 5

#: The support conditions an observation can carry. Ordered by how much help they imply.
#: ``none`` is the only level whose accuracy can be read as evidence about the learner
#: rather than about the help.
AID_LEVELS: tuple[str, ...] = ('none', 'repeat', 'lesson', 'feedback', 'tutor')

#: Which aid levels are compatible with an unaided reading. Deliberately a set of one.
UNAIDED: frozenset[str] = frozenset({'none'})

SCOPE_NOTE = (
    'Within-person measurement of rate and retention from this account\'s own attempts. '
    'Not a normed ability score, not a comparison to other learners, and not a prediction '
    'of an external exam. Every figure carries the aid conditions it was measured under; '
    'an aided figure is evidence about performance with support, never about unaided skill.'
)


def aid_level(*, tutor_turns: int = 0, lesson_open: bool = False,
              feedback_before: bool = False, item_seen: bool = False) -> str:
    """Classify the support present for one observation.

    Precedence is by how much the condition can manufacture a correct answer, not by how
    often it occurs. A tutor turn is the strongest confound because the model may simply
    state the answer; feedback is next because it reveals the right option; an open lesson
    supplies the method; and item repetition supplies the answer from memory. Returning the
    *strongest* aid present is what makes ``aid_level == 'none'`` a real claim: it means
    every source was checked and absent.
    """
    if tutor_turns > 0:
        return 'tutor'
    if feedback_before:
        return 'feedback'
    if lesson_open:
        return 'lesson'
    if item_seen:
        return 'repeat'
    return 'none'


def unaided(level: str) -> bool:
    """Whether an observation at this aid level may be read as unaided evidence.

    An unrecognised level returns ``False``. The failure mode to avoid is a typo or a new
    level silently joining the unaided bucket, which would quietly inflate the single
    number the whole report is built to keep honest.
    """
    return level in UNAIDED


def describe_aid(level: str) -> str:
    """A learner-facing sentence for why an observation counts or does not."""
    return {
        'none': 'Answered with no tutor, no lesson text and no feedback: the only condition '
                'that measures what you can do unprompted.',
        'repeat': 'Answered on an item you had seen recently, so a correct answer may be '
                  'recognition rather than recall.',
        'lesson': 'Answered with the lesson material open, so the method was available to '
                  'copy rather than to retrieve.',
        'feedback': 'Answered after feedback had already been shown for this item.',
        'tutor': 'Answered during a conversation with the tutor, which may have supplied '
                 'part of the answer.',
    }.get(level, 'Support conditions were not recorded, so this cannot be scored as '
                 'unaided evidence.')


def evidence_status(observations: int, minimum: int) -> dict[str, Any]:
    """The gate every estimator reports through.

    Returning a dict rather than raising keeps one missing sample from taking down a whole
    report: a learner with three practice attempts should see their attempt count and an
    explanation of what is still missing, not a 500 or an empty screen.
    """
    observations = max(0, int(observations))
    minimum = max(1, int(minimum))
    if observations >= minimum:
        return {'status': 'measured', 'observations': observations,
                'minimum': minimum, 'shortfall': 0}
    return {'status': 'insufficient_evidence', 'observations': observations,
            'minimum': minimum, 'shortfall': minimum - observations,
            'note': f'Needs {minimum - observations} more observation(s) before this '
                    'figure is identified; fewer would report noise as a finding.'}


def count_by(values: Iterable[str]) -> dict[str, int]:
    """Small helper so every caller reports the same shape of aid breakdown."""
    out: dict[str, int] = {}
    for value in values:
        out[value] = out.get(value, 0) + 1
    return out


def summarise_aid(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Aid composition of an observation set, with the unaided share made explicit.

    The share matters more than the counts: a report that says "40 attempts" while 39 were
    tutor-assisted is describing a different measurement than the reader will assume.
    """
    levels = [str(row.get('aid') or 'unknown') for row in rows]
    total = len(levels)
    breakdown = count_by(levels)
    unaided_count = sum(1 for level in levels if unaided(level))
    return {
        'total': total,
        'unaided': unaided_count,
        'unaided_share': round(unaided_count / total, 4) if total else None,
        'by_level': breakdown,
        'unknown': breakdown.get('unknown', 0),
    }


__all__ = ['AID_LEVELS', 'EPISODE_GAP_SECONDS', 'IDLE_CAP_SECONDS', 'MIN_OPPORTUNITIES',
           'MIN_UNAIDED_OBSERVATIONS', 'RECOGNITION_WINDOW_HOURS', 'SCOPE_NOTE', 'UNAIDED',
           'aid_level', 'count_by', 'describe_aid', 'evidence_status', 'summarise_aid',
           'unaided']
