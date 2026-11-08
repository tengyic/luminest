"""The caller's own account: consumption and settings.

    GET   /api/v1/usage        -> what this account has consumed against its quota
    GET   /api/v1/preferences  -> the account's stored preferences
    PATCH /api/v1/preferences  -> a partial update of them

Why this family was the first one moved
---------------------------------------
Three routes, all six handler lines reading the caller's own row and serialising it, and
no reference to a single helper defined inside ``main.create_app``. That last property is
the whole reason: a pure relocation must not drag a closure across a module boundary, and
every other inline family in ``main.py`` that is small enough to move (auth, access,
experiments, ta, boards, knowledge-graph) calls at least one ``create_app``-local helper -
``require_admin``, ``_teacher``, ``auth_limits``, ``client_ip``, ``course_graph``. Moving
one of those in the same commit would have mixed "move the code" with "rehome the helper",
and a helper rehome is a behaviour change hiding inside a no-behaviour-change commit.

Why a builder instead of a module-level ``router``
--------------------------------------------------
The sibling feature routers (``app/routes_supervision.py`` and friends) can declare
``router = APIRouter(...)`` at import time because their dependency is
``security.require_principal``, a module-level callable that reaches the session factory
through ``request.app.state``. This family uses ``authenticated``, which is a closure over
the engine factory created *inside* ``create_app``: it also updates the token and user
heartbeats and commits them before the body streams, so swapping in
``require_principal`` here would be a silent behaviour change, not a relocation.

A module-level router cannot see an object that does not exist until ``create_app`` runs,
so the module exposes ``build_router(authenticated=...)`` and the composition root passes
the very same callable object the inline handlers used. The dependency FastAPI executes is
therefore identical, which is why the surface instrument reports the same
``app.main.create_app.authenticated`` for these routes before and after the move.

This builder is a bridge, not the destination. When ``authenticated`` itself moves to
``app/core/auth.py`` and reads ``app.state`` the way ``require_principal`` does (ADR-0002,
wave 2), this module can drop the parameter and go back to a plain module-level ``router``.
"""

from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, Depends

from ... import accounts, schemas
from ...db import now_ts

#: The version segment, declared once. The paths below are relative to it.
PREFIX = '/api/v1'


def build_router(*, authenticated: Callable) -> APIRouter:
    """The account router. ``authenticated`` is the session dependency from the app."""
    router = APIRouter(prefix=PREFIX, tags=['account'])

    @router.get('/usage')
    def usage(auth=Depends(authenticated)):
        db, user = auth
        return accounts.usage_summary(db, user)

    @router.get('/preferences')
    def get_preferences(auth=Depends(authenticated)):
        db, user = auth
        row = accounts.preferences_for(db, user)
        db.commit()
        return accounts.preferences_json(row)

    @router.patch('/preferences')
    def patch_preferences(payload: schemas.PreferencePatch, auth=Depends(authenticated)):
        db, user = auth
        row = accounts.preferences_for(db, user)
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        row.updated_at = now_ts()
        db.commit()
        return accounts.preferences_json(row)

    return router
