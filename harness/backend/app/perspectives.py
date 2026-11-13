"""Multi-perspective evidence: scored human observations, never telemetry inference.

Why this module exists
----------------------
The product brief asks for participation, soft skills, creativity, communication and
collaboration analytics. The November 8 audit correctly recorded that four of those had
*zero* implementation, and that presenting them as percentages would be a fabrication: a
foreground heartbeat measures how long a window was active, not whether a learner
collaborated, explained something clearly, or tried an original approach. Inferring a
"creativity score" from click counts would be worse than leaving the field empty.

So a perspective dimension is populated only by a **rubric observation with written
evidence**, attached to an artifact that actually exists in the database. Three rules
follow, and they are the point of the module:

* A dimension with no observations is ``insufficient_evidence`` with ``value: null``.
  It is never a zero, never a guess, and never derived from active seconds.
* Creativity, communication and soft skills are *judgements*. The score records who
  made the judgement (self / teacher / peer) and the note they wrote, so a reader can
  disagree with it. A number without a note is refused.
* Collaboration has no single-learner shortcut. It can only be scored as a
  teacher-recorded group observation (``group_size >= 2``) attached to a real project,
  because a learner working alone has produced no collaboration evidence at all.

Consent and disclosure: no telemetry, mouse position, idle time or camera data is read
here. The only inputs are text a person chose to write. ``GET /perspectives/dimensions``
publishes each measurement definition so the UI can say what a number means rather than
implying it is a psychometric instrument.

New table, no ``SCHEMA_VERSION`` bump: ``create_all`` creates it on a fresh database, and
``scripts/init_db.initialize()`` creates it on an existing one because that function calls
``create_all`` unconditionally and imports this module so the model is registered (see
``course_builder`` for the precedent and the reason).

**App startup does not do this.** ``app/main.py`` gates ``create_all`` on the ``users`` table
being absent, deliberately refusing to migrate an existing database. An install created
before this table existed is therefore stamped at the current version but lacks the table,
and dashboard/export/analytics fail with ``no such table: perspective_reviews`` until the
operator runs ``scripts/init_db.py``. ``init_db._needs_upgrade`` now detects that drift and
takes a pre-migration backup. See ``tests/test_schema_equivalence.py``.
"""
from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, now_ts, uid

#: Ordered, because ``/analytics`` renders them in this order and stability matters more
#: than alphabetical tidiness. ``source`` is what a client must display alongside the
#: number; without it a 3/4 is indistinguishable from a measurement.
DIMENSIONS = (
    {
        'code': 'participation',
        'name': 'Participation',
        'definition': 'Observed contribution to lessons, discussions and project work, scored on a 0-4 rubric.',
        'source': 'rubric observation',
        'limitation': 'A count of active minutes is not a participation score. Only written observations count here.',
    },
    {
        'code': 'communication',
        'name': 'Communication',
        'definition': 'Clarity, structure and audience awareness of a written or spoken explanation, scored on a 0-4 rubric.',
        'source': 'rubric observation',
        'limitation': 'The presence of a written answer does not measure its quality. A human judgement is required.',
    },
    {
        'code': 'creativity',
        'name': 'Creativity',
        'definition': 'Originality and independent choice of method in a submitted artifact, scored on a 0-4 rubric.',
        'source': 'rubric observation',
        'limitation': 'Originality cannot be inferred from response time or from a novelty string match.',
    },
    {
        'code': 'collaboration',
        'name': 'Collaboration',
        'definition': 'Documented contribution to a shared artifact with at least one other learner, scored on a 0-4 rubric.',
        'source': 'teacher-recorded group observation',
        'limitation': 'Single-learner sessions produce no collaboration evidence. A solo score would be invented.',
    },
    {
        'code': 'soft_skills',
        'name': 'Soft skills',
        'definition': 'Self-direction, revision after feedback, reflection and help-seeking, scored on a 0-4 rubric.',
        'source': 'rubric observation',
        'limitation': 'These are dispositions observed over time, not a trait measurement or a diagnosis.',
    },
)

CODES = tuple(row['code'] for row in DIMENSIONS)
DEFINITIONS = {row['code']: row for row in DIMENSIONS}

#: Anchors are real persisted rows. A review for an artifact that does not exist is
#: refused (404), because otherwise a score could be attached to a made-up submission.
ARTIFACT_TYPES = ('project', 'unit_test', 'group_project')
REVIEWER_ROLES = ('self', 'teacher', 'peer')
STAFF_ROLES = ('teacher', 'staff', 'admin')
MIN_NOTE_LENGTH = 12
MAX_NOTE_LENGTH = 2000
SCORE_MAX = 4


class PerspectiveReview(Base):
    """One rubric observation about one learner, on one dimension of one artifact."""

    __tablename__ = 'perspective_reviews'
    __table_args__ = (
        Index('perspective_reviews_subject_dimension_idx', 'user_id', 'dimension'),
        # One reviewer scores one dimension of one artifact once. Re-scoring is an
        # UPDATE, not an ever-growing pile of contradictions.
        UniqueConstraint('user_id', 'artifact_type', 'artifact_id',
                         'dimension', 'reviewer_id', name='perspective_reviews_once'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    #: The learner the observation is about. Named ``user_id`` so the shared
    #: ``own_rows(db, Model, user)`` scoping helper applies without a special case.
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    artifact_type: Mapped[str] = mapped_column(String(24))
    artifact_id: Mapped[str] = mapped_column(String(64))
    dimension: Mapped[str] = mapped_column(String(32))
    score: Mapped[int] = mapped_column(Integer)
    evidence_note: Mapped[str] = mapped_column(Text)
    reviewer_id: Mapped[str] = mapped_column(String(36))
    reviewer_role: Mapped[str] = mapped_column(String(16))
    #: Only meaningful for a teacher-recorded group observation. ``None`` for solo work,
    #: which is itself the evidence that collaboration was not observed.
    group_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=now_ts)
    updated_at: Mapped[float] = mapped_column(Float, default=now_ts)


def validate_observation(payload: dict, *, caller_id: str, caller_role: str,
                         subject_id: str, artifact_exists: bool) -> str | None:
    """Return an error string, or ``None`` when the observation is admissible.

    Kept as a pure function so the rules are unit-testable without an app, a database or
    a role fixture. The route does authentication and artifact lookup; this decides the
    rest, in one place.
    """
    if not artifact_exists:
        return 'That artifact does not exist, so no observation can be attached to it.'
    dimension = payload.get('dimension')
    if dimension not in DEFINITIONS:
        return f'Unknown dimension. Choose one of: {", ".join(CODES)}.'
    artifact_type = payload.get('artifact_type')
    if artifact_type not in ARTIFACT_TYPES:
        return f'Unknown artifact type. Choose one of: {", ".join(ARTIFACT_TYPES)}.'
    role = payload.get('reviewer_role')
    if role not in REVIEWER_ROLES:
        return f'Unknown reviewer role. Choose one of: {", ".join(REVIEWER_ROLES)}.'
    score = payload.get('score')
    if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= SCORE_MAX:
        return f'Score must be an integer from 0 to {SCORE_MAX}.'
    note = (payload.get('evidence_note') or '').strip()
    if not MIN_NOTE_LENGTH <= len(note) <= MAX_NOTE_LENGTH:
        return (f'An observation needs {MIN_NOTE_LENGTH}-{MAX_NOTE_LENGTH} characters of '
                'written evidence. A bare number is not an assessment.')
    if role == 'self':
        if subject_id != caller_id:
            return 'A self-review can only describe your own work.'
    elif caller_role not in STAFF_ROLES:
        return 'Only a teacher, staff or admin account can record an observation about another learner.'
    if role == 'peer':
        group_size = payload.get('group_size')
        if isinstance(group_size, bool) or not isinstance(group_size, int) or group_size < 2:
            return ('Collaboration requires a group observation with group_size >= 2. '
                    'A solo submission has no collaboration evidence.')
        if artifact_type != 'group_project':
            return 'A peer observation must be attached to a group project artifact.'
    elif role == 'teacher' and artifact_type == 'group_project':
        return 'Use reviewer_role="peer" for a group observation.'
    return None


def summary(reviews) -> list[dict]:
    """The five dimensions, with values only where written observations exist.

    ``value`` is the mean rubric score divided by ``SCORE_MAX`` (0-1) so it renders in the
    same progress bars as the retrieval dimensions. ``status`` distinguishes "measured
    from N observations" from "we have no evidence" — the UI must not colour these alike.
    """
    reviews = list(reviews or [])
    rows = []
    for entry in DIMENSIONS:
        code = entry['code']
        matching = [r for r in reviews if r.dimension == code]
        if code == 'collaboration':
            matching = [r for r in matching if (r.group_size or 0) >= 2]
        if matching:
            mean = sum(r.score for r in matching) / len(matching)
            roles = sorted({r.reviewer_role for r in matching})
            rows.append({
                'name': entry['name'],
                'code': code,
                'value': round(mean / SCORE_MAX, 4),
                'evidence': (f'{len(matching)} written rubric observation(s) from '
                             f'{"/".join(roles)} on a 0-{SCORE_MAX} scale. '
                             + entry['limitation']),
                'status': 'observed',
                'measurement': entry['definition'],
                'source': entry['source'],
            })
        else:
            reason = ('No group observation has been recorded; a single-learner session '
                      'cannot produce collaboration evidence.' if code == 'collaboration'
                      else 'No written rubric observation has been recorded for this dimension.')
            rows.append({
                'name': entry['name'],
                'code': code,
                'value': None,
                'evidence': reason + ' ' + entry['limitation'],
                'status': 'not_measured' if code == 'collaboration' else 'insufficient_evidence',
                'measurement': entry['definition'],
                'source': entry['source'],
            })
    return rows


def public_definitions() -> dict:
    """What the client must disclose alongside any number it renders."""
    return {
        'scale': {'min': 0, 'max': SCORE_MAX,
                  'meaning': 'Human rubric judgement with written evidence, not a psychometric score.'},
        'dimensions': list(DIMENSIONS),
        'artifact_types': list(ARTIFACT_TYPES),
        'reviewer_roles': list(REVIEWER_ROLES),
        'privacy': ('No telemetry, pointer activity, idle time, camera or microphone signal is '
                    'used to infer any perspective. Foreground activity is disclosed separately '
                    'as interaction time and is never called attention.'),
        'accreditation': ('These observations are formative feedback. They are not an '
                          'accredited grade, a trait diagnosis, or an AP/official assessment.'),
    }


def review_json(row: PerspectiveReview) -> dict:
    return {
        'id': row.id, 'artifact_type': row.artifact_type, 'artifact_id': row.artifact_id,
        'dimension': row.dimension, 'score': row.score, 'evidence_note': row.evidence_note,
        'reviewer_role': row.reviewer_role, 'group_size': row.group_size,
        'created_at': row.created_at, 'updated_at': row.updated_at,
    }


# Imported names that SQLAlchemy's mapped_column needs at class-definition time.
# Kept at the bottom of the import block rather than re-importing inside the model.
__all__ = ['ARTIFACT_TYPES', 'CODES', 'DEFINITIONS', 'DIMENSIONS', 'PerspectiveReview',
           'public_definitions', 'review_json', 'summary', 'validate_observation']
