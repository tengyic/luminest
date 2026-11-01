"""Whether an account is mid-exam, and what that forbids.

During an active exam the harness withholds every surface that could supply an
answer: images, video, external simulations, presentations, the tutor. The
playground belongs on that list - a game that teaches the concept being examined is
help, whatever it is called - and it is the kind of surface that gets forgotten,
because it is added later and it does not look like a help feature.

This lives in its own module rather than in the application module because two
surfaces now need it and they cannot import each other: ``main`` mounts the routers,
and the routers are imported *by* ``main``. A second copy of the query would be a
second place for the rule to be relaxed by accident, which is exactly the failure a
guard like this exists to prevent.
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select

from .db import Assessment, now_ts


def active(db, user):
    """The learner's open, unexpired exam, or ``None``.

    ``with_for_update`` matches the question route: it takes the row lock so that an
    exam cannot be started and then observed as inactive by a concurrent request in
    the window between the insert and the commit.
    """
    return db.scalar(select(Assessment).where(Assessment.user_id == user.id,
                                             Assessment.mode == 'exam',
                                             Assessment.complete.is_(False),
                                             Assessment.expires_at > now_ts())
                     .with_for_update())


def block(db, user) -> None:
    """Raise 403 when an exam is running. A no-op otherwise."""
    if active(db, user):
        raise HTTPException(
            403,
            'Help and other learning activities are unavailable during an active exam. '
            'Complete the exam or wait for its two-hour expiry.')
