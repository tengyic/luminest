"""Issuing a question, and the exact shape a client receives.

A question only counts if the answer can come back, and the answer only counts if the
server can prove this instance asked *that* question. Both halves are a receipt: an
issued row, signed over its own fields, submitted once with the item id.

This module exists because there are now three places that issue one - the practice
card (``/questions/next``), a lesson block (``/procedure/runs/{id}/next-item``) and the
tutor's ``check_understanding`` tool - and three hand-rolled copies of "which keys does a
client need" is three chances for one of them to omit ``options`` and render a question
nobody can answer. The shape is defined once here.

Two properties are deliberate.

**A receipt is issued, never reserved.** Issuing writes a row and nothing else: no
attempt, no state, no mastery. Reading a question must not be evidence that it was
answered, or a learner could raise their own estimate by refreshing.

**The payload is the whole question, minus the answer.** ``options`` carries the ids a
client submits; the correct option, the explanation and the diagnosis stay server-side
until the attempt is scored, which is what makes the receipt the only way to grade.
"""

from __future__ import annotations

from typing import Any, Mapping

from .db import Receipt, iso, now_ts, uid
from .security import sign_receipt

__all__ = ['issue', 'public', 'public_fields']

#: The question keys a client is given, and nothing else.
public_fields = ('id', 'concept_id', 'concept_title', 'prompt', 'options', 'kind',
                 'expected_seconds')


def public(question: Mapping[str, Any], receipt: Receipt, secret: str,
           progress: Mapping[str, Any] | None = None, reason: str = '') -> dict[str, Any]:
    """The question as the client sees it: this item, its receipt, and why it was chosen."""
    return {**{key: question.get(key) for key in public_fields},
            'mode': receipt.mode,
            'issued_at': iso(receipt.issued_at),
            'receipt': sign_receipt(receipt, secret),
            'progress': dict(progress or {}),
            'selection_reason': reason}


def issue(db, user, question: Mapping[str, Any], *, mode: str, ttl: float,
          secret: str, assessment_id: str | None = None,
          progress: Mapping[str, Any] | None = None, reason: str = '',
          expires_by: float | None = None) -> dict[str, Any]:
    """Record one signed receipt for one question and return the client payload.

    ``expires_by`` narrows the window to a deadline that already exists (an assessment's
    own expiry); the receipt never outlives the thing it belongs to. The caller commits -
    this function flushes nothing, so a refusal later in the same request leaves no
    orphan receipt behind.
    """
    now = now_ts()
    expiry = now + float(ttl)
    if expires_by is not None:
        expiry = min(expiry, float(expires_by))
    receipt = Receipt(id=uid(), user_id=user.id, question_id=str(question['id']),
                      mode=str(mode), assessment_id=assessment_id,
                      issued_at=now, expires_at=expiry)
    db.add(receipt)
    return {**public(question, receipt, secret, progress, reason), 'receipt_id': receipt.id}
