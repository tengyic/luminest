"""Map the internal IRT ability theta (logits) onto labels a learner can read.

The harness estimates one continuous ability theta per learner (``app/harness/psychometrics``,
2PL IRT, EAP). That number is honest but unreadable: "ability 0.7 logits" means nothing to a
learner, and "about 67% on an average question" does. This module is the communication layer
between the two, and it is written to fail closed.

**Three ways this kind of mapping goes wrong, and what stops each here.**

1. *A learner with no evidence is given a level.* The prior theta is 0.0, so a naive mapping
   renders a brand-new account as "A2 / Grade 5" - a specific, confident, entirely
   fabricated claim. :func:`learner_level` therefore returns ``known=False`` and no band at
   all until :data:`MIN_ITEMS_FOR_LEVEL` calibrated items have been answered. This is the
   same rule as ``mastery_known`` in the teaching core: "no attempts yet" is not "weak".
2. *CEFR is applied to a subject it does not describe.* CEFR is a language-proficiency
   framework. Reporting a mathematics learner as "B1 Threshold" is a category error dressed
   as precision. ``cefr`` is ``None`` unless the enrolled subject is a language, with a
   reason attached rather than a silent omission.
3. *A cut point is presented as a measurement.* The bands are explicit numbers a reader can
   argue with (they are in :data:`CEFR_BANDS`, not buried in a lookup), and every payload
   carries ``not_certified`` plus a note saying so.

The grade mapping is linear across the theta range the harness actually serves (about
-4..+4 logits, the 0.02-0.98 success band on an average item). It is a rough school-year
equivalent, not a placement decision, and it is labelled as such.
"""

from __future__ import annotations

from typing import Any

from . import psychometrics

#: Calibrated items needed before any level is shown. Below this the estimate is the prior
#: wearing a label, and a prior is not evidence about a person.
MIN_ITEMS_FOR_LEVEL = 5

#: theta -> CEFR band (cut point, label, name). Product decisions, not psychometric facts;
#: stated here so a reader can disagree with one number instead of with a black box.
CEFR_BANDS = (
    (-3.0, 'Pre-A1', 'Breakthrough'),
    (-1.5, 'A1', 'Waystage'),
    (-0.2, 'A2', 'Elementary'),
    (1.0, 'B1', 'Threshold'),
    (2.2, 'B2', 'Vantage'),
    (3.2, 'C1', 'Advanced'),
    (4.01, 'C2', 'Mastery'),
)

#: theta -> US school grade (K=0 .. Grade 12), linear across the served range.
GRADE_MIN_THETA = -3.0
GRADE_MAX_THETA = 4.0

#: Subjects whose theta a CEFR band legitimately describes. Matched on the enrolled course's
#: subject string, case-folded. A subject absent from this list gets ``cefr=None`` - the
#: honest answer for a physics or economics learner, whose ability is not a language level.
LANGUAGE_SUBJECTS = ('english', 'spanish', 'french', 'german', 'italian', 'portuguese',
                     'chinese', 'japanese', 'korean', 'russian', 'arabic', 'latin',
                     'language', 'esl', 'efl', 'literacy')


def is_language_subject(subject: str | None) -> bool:
    text = (subject or '').casefold()
    return any(word in text for word in LANGUAGE_SUBJECTS)


def cefr_from_theta(theta: float) -> tuple[str, str]:
    """Return ``(cefr_label, cefr_name)`` for an ability estimate."""
    label, name = CEFR_BANDS[0][1], CEFR_BANDS[0][2]
    for cut, lab, nm in CEFR_BANDS:
        if theta >= cut:
            label, name = lab, nm
    return label, name


def grade_from_theta(theta: float) -> tuple[int, str]:
    """Return ``(grade_number, grade_label)`` for an ability estimate (K=0 .. 12).

    The label is "Grade 5", not "Grade 5th": the ordinal belongs in front ("5th grade") and
    appending it to the noun reads as a mistake to anyone who looks at the screen.
    """
    t = max(GRADE_MIN_THETA, min(GRADE_MAX_THETA, float(theta)))
    frac = (t - GRADE_MIN_THETA) / (GRADE_MAX_THETA - GRADE_MIN_THETA)
    grade = max(0, min(12, int(round(frac * 12))))
    if grade == 0:
        return grade, 'Kindergarten'
    return grade, f'Grade {grade}'


def level_summary(theta: float, se: float = 0.0, *, subject: str | None = None,
                  n: int | None = None) -> dict[str, Any]:
    """The raw mapping, with no knowledge of whether it should be shown.

    Kept separate from :func:`learner_level` on purpose: the mapping is a pure function that
    a test can pin, and the decision to display it is the part that has to fail closed. A
    caller that needs the learner-facing answer wants :func:`learner_level`.
    """
    theta = float(theta)
    cefr, cefr_name = cefr_from_theta(theta)
    grade, grade_label = grade_from_theta(theta)
    language = is_language_subject(subject)
    success = psychometrics.theta_to_success(theta)
    return {
        'theta': round(theta, 3),
        'se': round(float(se), 3),
        'n_items': n,
        # A band is only reported for the subject it describes.
        'cefr': cefr if language else None,
        'cefr_name': cefr_name if language else None,
        'cefr_reason': (None if language else
                        f'CEFR describes language proficiency; this course is {subject or "not a language"}.'),
        'grade': grade,
        'grade_label': grade_label,
        'success_on_average_item': success,
        'interpretable': (f'{cefr} ({cefr_name}) ~ {grade_label}' if language
                          else f'{grade_label} · about {round(success * 100)}% on an average question'),
        'not_certified': True,
    }


def learner_level(theta: float, se: float = 0.0, *, n: int | None = None,
                  subject: str | None = None) -> dict[str, Any]:
    """What to show a learner. Returns ``known=False`` and no band when there is no evidence.

    ``n`` is the number of calibrated items behind ``theta``. ``None`` means the caller did
    not say, and an unstated count is treated as *not enough*: the permissive default is
    exactly how a prior becomes a label.
    """
    enough = n is not None and n >= MIN_ITEMS_FOR_LEVEL
    if not enough:
        return {
            'known': False,
            'label': 'Not yet measured',
            'n_items': n,
            'needed': MIN_ITEMS_FOR_LEVEL,
            'cefr': None,
            'grade': None,
            'success_on_average_item': None,
            'note': (f'A level appears after {MIN_ITEMS_FOR_LEVEL} calibrated questions; '
                     f'you have answered {n or 0}. Showing one now would describe the '
                     'starting assumption, not you.'),
            'not_certified': True,
        }
    payload = level_summary(theta, se, subject=subject, n=n)
    payload['known'] = True
    payload['label'] = payload['interpretable']
    payload['note'] = ('A rough band from your own answer history, not a certified CEFR or '
                       'age calibration. It narrows as you answer more calibrated questions; '
                       f'standard error {round(float(se), 2)} logits.')
    return payload


def describe() -> dict[str, Any]:
    """The mapping, for the transparency panel and the tests."""
    return {'model': 'theta (logits) -> CEFR (languages only) / grade / success',
            'cefr_bands': [{'theta_gte': cut, 'label': lab, 'name': nm}
                           for cut, lab, nm in CEFR_BANDS],
            'grade_range': {'min_theta': GRADE_MIN_THETA, 'max_theta': GRADE_MAX_THETA,
                            'min_grade': 0, 'max_grade': 12, 'mapping': 'linear'},
            'min_items_for_level': MIN_ITEMS_FOR_LEVEL,
            'language_subjects': list(LANGUAGE_SUBJECTS),
            'not_certified': True}
