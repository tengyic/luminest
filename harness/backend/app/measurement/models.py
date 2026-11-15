"""The one table measurement needs: what the harness asked, and what came back.

Why a table at all
------------------
Everything else in this package is derived. Episodes are reconstructed from attempt
timestamps, aid is inferred from data that already exists, and the estimators are pure
functions over those shapes. A probe is the exception, and it is a real one: a probe's whole
value depends on the *conditions it was issued under*, and those conditions are true for a
moment and then gone.

If the record were reconstructed afterwards, "this answer was unaided" would be an inference
from absence - no tutor message found, no lesson view found, no repeat found - and absence is
exactly what a missing event looks like. Storing the conditions at issue time turns a claim
into a fact, so a later audit can ask "was this really unaided" and get an answer rather than
an argument.

Same lifecycle as ``unit_grades`` and ``perspective_reviews``: the model lives here rather
than in ``db.py`` because this module owns the table, and ``scripts/init_db.py`` imports it.
No ``SCHEMA_VERSION`` bump is needed - ``_needs_upgrade`` detects that ``Base.metadata``
names a table the database does not have and writes the pre-migration backup before
``create_all`` repairs it.
"""

from __future__ import annotations

from sqlalchemy import (JSON, CheckConstraint, Float, ForeignKey, Index, String, Text)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base, now_ts, uid

#: Row states, in lifecycle order. ``abandoned`` is kept rather than deleted: a probe the
#: learner walked away from is information about *when* the harness probed, and dropping it
#: would make the completion rate look better than it is.
STATUSES = ('scheduled', 'issued', 'completed', 'abandoned')

#: The probe kinds. Mirrors :data:`app.measurement.probe.PROBE_SPECS`; the test suite asserts
#: the two cannot drift apart.
KINDS = ('cold', 'effort', 'retained')


class MeasurementProbe(Base):
    """One measurement the harness asked for, and the conditions it was issued under.

    ``conditions`` is the load-bearing column. It records the support state *at issue* -
    whether feedback was withheld, whether the lesson was open, whether the tutor was
    reachable, whether the item had been seen inside the recognition window - so that the
    unaided claim attached to the response is auditable and cannot be re-derived from a
    database that has since lost the events it would need.

    ``value`` is the scalar reading: 1.0/0.0 for a cold probe's correctness, 1-9 for an
    effort rating. Nullable because an abandoned probe has no reading, and a zero would be
    indistinguishable from a wrong answer.
    """

    __tablename__ = 'measurement_probes'
    __table_args__ = (
        CheckConstraint("kind IN ('cold','effort','retained')", name='probes_kind_ck'),
        CheckConstraint("status IN ('scheduled','issued','completed','abandoned')",
                        name='probes_status_ck'),
        Index('probes_user_kind_idx', 'user_id', 'kind', 'issued_at'),
        Index('probes_user_concept_idx', 'user_id', 'concept_id'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    concept_id: Mapped[str] = mapped_column(String(64), default='')
    question_id: Mapped[str] = mapped_column(String(64), default='')
    status: Mapped[str] = mapped_column(String(20), default='issued', server_default='issued')
    #: Support conditions captured at issue time. See the class docstring.
    conditions: Mapped[dict] = mapped_column(JSON, default=dict)
    response: Mapped[dict] = mapped_column(JSON, default=dict)
    #: The scalar reading: correctness for ``cold``, the 1-9 rating for ``effort``.
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: Why the scheduler asked. Kept so a report can explain a probe instead of merely
    #: counting it, and so an intrusive scheduler can be diagnosed after the fact.
    reason: Mapped[str] = mapped_column(Text, default='')
    issued_at: Mapped[float] = mapped_column(Float, default=now_ts)
    completed_at: Mapped[float | None] = mapped_column(Float, nullable=True)


__all__ = ['KINDS', 'MeasurementProbe', 'STATUSES']
