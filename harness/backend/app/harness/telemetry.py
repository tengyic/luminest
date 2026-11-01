"""What an interaction may say.

Until now the app recorded two things: *time* (``heartbeat``) and *answers*
(``Attempt``). Everything between them - which board node was opened, whether the hint was
reached for before or after an attempt, whether the deck was touched at all - was invisible,
and ``tools_board.py`` said so in as many words: a simulation could be placed on the board
and nothing downstream could tell whether anyone ever looked at it.

This module owns that missing channel's vocabulary. It is deliberately small, because a
click stream is the easiest place in a learning product for surveillance to enter by
accident.

**Four rules, and what enforces each.**

* *A tap is engagement, not evidence.* :data:`EVIDENCE` is ``False`` and nothing in
  ``loop``/``policy``/``classroom`` reads ``click`` rows as answers. A learner who taps
  constantly is not a learner who knows more, and a dashboard that conflates the two
  corrupts the record it is supposed to explain.
* *The vocabulary is closed.* :data:`KINDS` and :data:`TARGET_PATTERN` are the whole
  grammar. A payload outside them is rejected at the route, not silently dropped: a client
  inventing vocabulary is a client whose numbers will not mean anything later.
* *No content, ever.* There is no text field and no keystroke field. ``kind='key'`` records
  *that* a key was pressed, never which one; the app has no code path that could attach a
  character, and :func:`validate` refuses unknown keys outright so one cannot be added by
  accident.
* *No window titles.* An earlier draft of this channel accepted a ``window`` field. A window
  title is a document name, a URL, or a message subject; storing it turns an engagement
  signal into a reading log. It is refused here and removed from the route's allow-list.

**Absence is not a signal.** A learner who never taps may be reading closely. :func:`summary`
therefore reports counts and states what it cannot conclude rather than producing an
"engagement score".
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

#: A tap never counts as learning evidence. Anything that scores must check this.
EVIDENCE = False

#: The complete grammar of an interaction. ``click`` and ``tap`` are the same act on
#: different input devices; ``key`` is contentless by construction; ``blur``/``focus`` are
#: window-level and carry no target.
KINDS = ('click', 'tap', 'key', 'blur', 'focus')

#: Kinds that must name what was touched. A blur has no target; a click without one is a
#: client that could not say where the learner went, which is not worth storing.
TARGETED_KINDS = ('click', 'tap', 'key')

#: The only keys a payload may carry. ``window`` is absent on purpose - see the module note.
FIELDS = ('kind', 'target')

#: A target names a control: ``stage.tab.deck``, ``board.node.cell-theory``, ``question.hint``.
#: It is an identifier, not prose, and the pattern is what keeps a sentence out of the field.
TARGET_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$')

#: Bound on how many events one flush may carry. Matches ``schemas.Events`` (max 100) with
#: room left for a heartbeat in the same batch.
MAX_BATCH = 100


def validate(payload: Mapping[str, Any]) -> tuple[bool, str]:
    """Check one interaction payload. Returns ``(ok, reason)``; the reason is learner-safe."""
    if not isinstance(payload, Mapping):
        return False, 'An interaction payload must be an object.'
    unknown = set(payload) - set(FIELDS)
    if unknown:
        # Named rather than counted: a client sending `text` or `window` should be told that
        # this channel has no such field, not merely that something was unexpected.
        return False, f'An interaction may not carry {", ".join(sorted(unknown))}.'
    kind = payload.get('kind')
    if kind not in KINDS:
        return False, f'Unknown interaction kind {kind!r}.'
    target = payload.get('target')
    if kind in TARGETED_KINDS:
        if not isinstance(target, str) or not target:
            return False, 'This interaction needs a target naming what was touched.'
        if not TARGET_PATTERN.match(target):
            return False, 'target must be a short identifier such as stage.tab.deck.'
    elif target is not None:
        if not isinstance(target, str) or not TARGET_PATTERN.match(target):
            return False, 'target must be a short identifier.'
    return True, ''


def summarise(rows: Iterable[Any], *, window_seconds: float = 86_400.0,
              now: float | None = None, limit: int = 12) -> dict[str, Any]:
    """Aggregate interactions into counts a teacher can read without being misled.

    ``rows`` are ``TelemetryEvent`` rows: anything with ``type``, ``payload`` and
    ``occurred_at`` (ISO string) or ``received_at`` (epoch). Only ``interaction`` rows count.

    The payload deliberately carries no score. ``interpretation`` states the limit in words,
    because the number will be read by someone who did not read this module.
    """
    from datetime import datetime

    if now is None:
        from ..db import now_ts
        now = now_ts()
    cutoff = now - max(0.0, float(window_seconds))

    def when(row) -> float | None:
        raw = getattr(row, 'occurred_at', None)
        if isinstance(raw, (int, float)):
            return float(raw)
        if isinstance(raw, str) and raw:
            try:
                return datetime.fromisoformat(raw.replace('Z', '+00:00')).timestamp()
            except ValueError:
                pass
        fallback = getattr(row, 'received_at', None)
        return float(fallback) if isinstance(fallback, (int, float)) else None

    by_kind: dict[str, int] = {}
    by_target: dict[str, int] = {}
    total = 0
    for row in rows:
        if getattr(row, 'type', None) != 'interaction':
            continue
        stamp = when(row)
        if stamp is None or stamp < cutoff:
            continue
        payload = getattr(row, 'payload', None) or {}
        kind = str(payload.get('kind', ''))
        if kind not in KINDS:
            # A row from a client that predates the closed vocabulary. Skipped rather than
            # counted under '', which would put an unattributable number in the total.
            continue
        total += 1
        by_kind[kind] = by_kind.get(kind, 0) + 1
        target = payload.get('target')
        if isinstance(target, str) and target:
            by_target[target] = by_target.get(target, 0) + 1

    top = sorted(by_target.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    return {
        'window_seconds': float(window_seconds),
        'interactions': total,
        'by_kind': dict(sorted(by_kind.items(), key=lambda kv: (-kv[1], kv[0]))),
        'top_targets': [{'target': name, 'count': count} for name, count in top],
        'is_evidence': EVIDENCE,
        'interpretation': ('Interactions show what was reached for and when. They are not '
                           'answers, not mastery and not an engagement score: a learner who '
                           'never taps may be reading closely, and one who taps constantly '
                           'may be searching for something the screen is not giving them.'),
    }


def describe() -> dict[str, Any]:
    """The vocabulary and its limits, for the transparency panel."""
    return {'kinds': list(KINDS), 'fields': list(FIELDS), 'is_evidence': EVIDENCE,
            'carries_free_text': False, 'carries_keystrokes': False,
            'carries_window_titles': False,
            'note': 'A closed vocabulary with no text field: this channel can say what was '
                    'touched, never what was typed, and never which window was in front.'}
