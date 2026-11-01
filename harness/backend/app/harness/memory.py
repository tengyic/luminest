"""Learner memory: what the harness knows, how it decays, and how it is cited.

Three kinds of memory are kept apart on purpose, because collapsing them is exactly how
a tutoring system ends up telling a student it has diagnosed them:

``episodic``    what happened - a session, an attempt sequence, a submitted project.
``semantic``    a belief about understanding. Always stored with the evidence that
                produced it, always revisable, never phrased as a verdict.
``procedural``  what worked for this learner - which move actually preceded progress.

A note is never deleted by decay. Decay only lowers how strongly it is believed, so the
record of *why* the harness believed something survives even after the belief fades.
That distinction matters: "this learner used to confuse the sign when distributing"
is useful history, while "this learner confuses signs" is a label.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import delete, select

from ..db import MemoryNote, now_ts, uid

KINDS = ('episodic', 'semantic', 'procedural')

#: Half-life of a memory's confidence, in seconds. Three weeks is a deliberate choice:
#: long enough that a note survives a holiday, short enough that a stale belief cannot
#: quietly drive a decision a term later.
HALF_LIFE = 21 * 24 * 3600

#: Confidence bounds. A note never reaches certainty, because a tutoring system cannot
#: observe a mental state directly; it only observes behaviour.
FLOOR = 0.05
CEILING = 0.95
START = 0.35
REINFORCE = 0.22


@dataclass
class Note:
    id: str
    kind: str
    concept_id: str
    text: str
    evidence: dict
    confidence: float
    reinforcements: int
    created_at: float
    last_seen: float

    def to_dict(self) -> dict[str, Any]:
        return {'id': self.id, 'kind': self.kind, 'concept_id': self.concept_id, 'text': self.text,
                'evidence': self.evidence, 'confidence': round(self.confidence, 4),
                'reinforcements': self.reinforcements, 'created_at': self.created_at,
                'last_seen': self.last_seen}

    def aged(self, now: float) -> float:
        """Confidence after decay, without changing the stored value."""
        elapsed = max(0.0, now - self.last_seen)
        return max(FLOOR, self.confidence * 0.5 ** (elapsed / HALF_LIFE))


def _bounded(value: float) -> float:
    return min(CEILING, max(FLOOR, value))


def _rows(db, user_id: str, kinds: Sequence[str] | None = None, concept_id: str | None = None):
    statement = select(MemoryNote).where(MemoryNote.user_id == user_id)
    if kinds:
        statement = statement.where(MemoryNote.kind.in_(list(kinds)))
    if concept_id is not None:
        statement = statement.where(MemoryNote.concept_id == concept_id)
    return list(db.scalars(statement))


def remember(db, user_id: str, kind: str, text: str, *, concept_id: str = '',
             evidence: Mapping[str, Any] | None = None, confidence: float = START) -> Note:
    """Record a note, or reinforce the identical note if it already exists.

    Reinforcing rather than duplicating is what turns repetition into evidence: the same
    observation seen five times is a stronger belief than the same observation seen once,
    and the count is stored so the difference is inspectable.
    """
    if kind not in KINDS:
        raise ValueError(f'Unknown memory kind {kind!r}')
    text = ' '.join(text.split())[:600]
    if not text:
        raise ValueError('A memory note needs text')
    existing = db.scalar(select(MemoryNote).where(
        MemoryNote.user_id == user_id, MemoryNote.kind == kind,
        MemoryNote.concept_id == concept_id, MemoryNote.text == text))
    now = now_ts()
    if existing is not None:
        existing.reinforcements += 1
        # Decay first, then reinforce. A note that has not been seen for months starts
        # from what is left of it, so repetition cannot compound indefinitely.
        existing.confidence = _bounded(_note(existing).aged(now) + REINFORCE)
        existing.last_seen = now
        if evidence:
            existing.evidence = {**existing.evidence, **dict(evidence)}
        db.commit()
        return _note(existing)
    row = MemoryNote(id=uid(), user_id=user_id, kind=kind, concept_id=concept_id, text=text,
                     evidence=dict(evidence or {}), confidence=_bounded(confidence),
                     created_at=now, last_seen=now)
    db.add(row)
    db.commit()
    return _note(row)


def _note(row: MemoryNote) -> Note:
    return Note(row.id, row.kind, row.concept_id, row.text, dict(row.evidence or {}),
                row.confidence, row.reinforcements, row.created_at, row.last_seen)


def recall(db, user_id: str, *, concept_id: str | None = None, kinds: Sequence[str] | None = None,
           limit: int = 12, now: float | None = None, related: Iterable[str] = ()) -> list[Note]:
    """Rank notes by how much they should influence the next decision.

    Relevance is a weighting, not a filter: a note about a prerequisite still matters
    when the learner is stuck on something further along, and dropping it would hide the
    most common reason a learner is stuck.
    """
    now = now_ts() if now is None else now
    neighbours = {value for value in related if value}
    scored: list[tuple[float, Note]] = []
    for row in _rows(db, user_id, kinds, None):
        note = _note(row)
        weight = 1.0
        if concept_id is not None:
            if note.concept_id == concept_id:
                weight = 1.6
            elif note.concept_id in neighbours:
                weight = 1.2
            elif note.concept_id:
                weight = 0.45
        weight *= {'semantic': 1.25, 'procedural': 1.1, 'episodic': 0.9}[note.kind]
        scored.append((note.aged(now) * weight, note))
    scored.sort(key=lambda pair: (-pair[0], pair[1].last_seen, pair[1].id))
    return [note for _, note in scored[:max(1, limit)]]


def digest(db, user_id: str, *, concept_id: str = '', related: Iterable[str] = (),
           limit: int = 10) -> str:
    """A compact, citable memory block for a system prompt.

    Deliberately terse and hedged. Each line names its own strength so the model is not
    invited to treat a single observation as established fact.
    """
    notes = recall(db, user_id, concept_id=concept_id or None, limit=limit, related=related)
    if not notes:
        return 'No prior observations recorded for this learner.'
    lines = []
    for note in notes:
        strength = 'observed once' if note.reinforcements <= 1 else f'observed {note.reinforcements}x'
        scope = note.concept_id or 'general'
        lines.append(f'- [{note.kind} · {scope} · {strength} · belief {note.confidence:.2f}] {note.text}')
    return '\n'.join(lines)


def forget(db, user_id: str, note_id: str) -> bool:
    row = db.scalar(select(MemoryNote).where(MemoryNote.id == note_id, MemoryNote.user_id == user_id))
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def wipe(db, user_id: str) -> int:
    """Delete every note for a learner. Used by the deletion and export contract."""
    result = db.execute(delete(MemoryNote).where(MemoryNote.user_id == user_id))
    db.commit()
    return int(result.rowcount or 0)


def summarise(notes: Sequence[Note]) -> dict[str, Any]:
    counts: dict[str, int] = {kind: 0 for kind in KINDS}
    for note in notes:
        counts[note.kind] = counts.get(note.kind, 0) + 1
    return {'total': len(notes), 'by_kind': counts,
            'mean_confidence': round(sum(note.confidence for note in notes) / len(notes), 4) if notes else 0.0}


def age_factor(note: Note, now: float | None = None) -> float:
    """How much of a note's confidence survives, for diagnostics."""
    now = now_ts() if now is None else now
    return note.aged(now) / note.confidence if note.confidence else 0.0


def half_life_days() -> float:
    return HALF_LIFE / 86400


def _decay_probe(now: float) -> float:  # pragma: no cover - retained for manual checks
    return math.exp(-math.log(2) * 0.0)
