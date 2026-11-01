"""HTTP surface for the capability matrix: what this instance offers, and what you get.

Mounted by convention -- ``main.create_app`` imports this module and includes
``router`` -- so multimodality can be removed by deleting the file. The read routes
are anonymous on purpose: a client must be able to render the store (what exists,
what it costs, what it degrades to) before the learner has an account. The write
routes are not.

    GET    /api/v1/capabilities              the matrix as resolved for the caller
    GET    /api/v1/capabilities/{id}         one capability: price, provider, fallback
    POST   /api/v1/capabilities/{id}/grant   pay-to-enable (signed receipt or operator comp)
    DELETE /api/v1/capabilities/{id}/grant   revoke (support, refunds, testing)

The grant route is deliberately store-agnostic. It accepts *evidence of payment* --
a signed receipt whose mint/verify lives in :mod:`app.capabilities` -- and writes the
entitlement through the existing ``user_preferences`` plus ``quota_policies``
machinery. No payment SDK is imported, because wiring one is the one remaining step,
and ``docs/pay-to-enable.md`` names the exact seam where it plugs in.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from . import capabilities
from .db import Token, User, now_ts
from .security import digest, rate_limit

log = logging.getLogger('luminfest.multimodal.routes')

router = APIRouter()

API = '/api/v1/capabilities'

#: Upper bound on a receipt string. A receipt is ``capability.expiry.hex`` -- about
#: sixty characters. Anything longer is an attempt to make the server parse something
#: expensive, and it is refused at the model boundary instead.
MAX_RECEIPT_CHARS = 512


class GrantInput(BaseModel):
    """Body for ``POST /api/v1/capabilities/{id}/grant``.

    ``receipt`` is optional so the operator-comp path (``HARNESS_ENTITLEMENTS``)
    works with an empty body. Sending neither a receipt nor having a comp is a 402
    whose body names the seam -- not a 500, and not a fake grant.
    """

    receipt: str = Field(default='', max_length=MAX_RECEIPT_CHARS)


def _resolve_for(request: Request) -> dict:
    """The matrix resolved for this request's caller, with no session leaked.

    The read endpoints are anonymous on purpose: a client must be able to render the
    store (what exists, what it costs, what it degrades to) before the learner has an
    account. A token that is present but invalid is still a 401 -- silently treating a
    broken token as anonymous would show a paid learner the wrong plan. Every row of
    database work happens inside the ``with`` and only plain dicts cross the boundary,
    which is the same discipline ``app/routes_media.py`` keeps.
    """
    factory = getattr(request.app.state, 'factory', None)
    settings = request.app.state.settings
    header = request.headers.get('authorization', '')
    if not header.startswith('Bearer '):
        return capabilities.resolve(None, settings)
    if factory is None:
        raise HTTPException(503, 'Account storage is unavailable')
    if len(header) > 200:
        raise HTTPException(401, 'Valid bearer token required',
                            headers={'WWW-Authenticate': 'Bearer'})
    raw = header[7:]
    rate_limit(factory, 'capabilities:' + digest(raw), 120)
    with factory() as db:
        token = db.get(Token, digest(raw))
        if not token:
            # No token row at all is the anonymous case for a *read*; the write
            # routes re-check and 401 on the same condition.
            return capabilities.resolve(None, settings)
        if token.expires_at <= now_ts() or token.revoked_at is not None:
            raise HTTPException(401, 'Invalid or expired token')
        user = db.get(User, token.user_id)
        if not user or getattr(user, 'status', 'active') != 'active':
            raise HTTPException(401, 'Account unavailable')
        return capabilities.resolve(user, settings, db=db)


@router.get(API)
def capability_matrix(request: Request):
    """The whole matrix as resolved for this caller.

    The response is the store: every capability with its tier, provider, fallback,
    status and current state, plus the price bundle and the reason for anything
    withheld. A client greys out what it cannot use from this payload alone -- no
    second call, no optimistic tap and a 402 afterwards.
    """
    return _resolve_for(request)


@router.get(API + '/{capability_id}')
def capability_detail(capability_id: str, request: Request):
    """One capability, resolved for the caller: price, provider, fallback, status."""
    capability = capabilities.by_id(capability_id)
    if capability is None:
        raise HTTPException(404, f'Unknown capability {capability_id!r}')
    resolved = _resolve_for(request)
    entry = next((row for row in resolved['capabilities'] if row['id'] == capability.id),
                 None)
    if entry is None:  # pragma: no cover - by_id and resolve share one table
        raise HTTPException(404, f'Unknown capability {capability_id!r}')
    return {'capability': entry, 'receipt_ttl_days': capabilities.RECEIPT_TTL_DAYS,
            'paid_plan': resolved['paid_plan']}


@router.post(API + '/{capability_id}/grant')
def grant_capability(capability_id: str, payload: GrantInput, request: Request):
    """Enable a paid capability for this account.

    Success writes two real rows through existing machinery: the entitlement in
    ``user_preferences.ui`` and, once per account, the paid ceiling in
    ``quota_policies``. Failure is a 402 whose body carries the matrix's own reason
    string and the seam where a real store plugs in -- see ``docs/pay-to-enable.md``.
    """
    factory = request.app.state.factory
    settings = request.app.state.settings
    # The lifespan seeds this from HARNESS_SECRET or a persisted random secret; fall
    # back to settings so a direct call without a lifespan still verifies.
    key = getattr(request.app.state, 'signing_secret', None) or None
    header = request.headers.get('authorization', '')
    if not header.startswith('Bearer ') or len(header) > 200:
        raise HTTPException(401, 'Valid bearer token required',
                            headers={'WWW-Authenticate': 'Bearer'})
    raw = header[7:]
    rate_limit(factory, 'capabilities:' + digest(raw), 120)
    with factory() as db:
        token = db.get(Token, digest(raw))
        if not token or token.expires_at <= now_ts() or token.revoked_at is not None:
            raise HTTPException(401, 'Invalid or expired token')
        user = db.get(User, token.user_id)
        if not user or getattr(user, 'status', 'active') != 'active':
            raise HTTPException(401, 'Account unavailable')
        ok, reason, record = capabilities.grant(
            db, user, capability_id, settings=settings,
            receipt=payload.receipt.strip() or None, key=key)
        if not ok:
            # Roll back before classifying: a refused grant must leave no partial
            # entitlement, and a failed write must never be reported as a success.
            db.rollback()
            capability = capabilities.by_id(capability_id)
            if capability is None:
                raise HTTPException(404, reason)
            if capability.status == capabilities.STATUS_MISSING:
                raise HTTPException(409, reason)
            # The payment seam, stated in the response so a client can render the
            # real purchase UI instead of a generic error.
            raise HTTPException(402, {'reason': reason, 'seam': _SEAM})
        db.commit()
        # ``record`` is None for the free-tier no-op: nothing was written because
        # nothing needed writing, and the response must say so rather than pretend
        # an entitlement exists.
        return {'capability': capability_id, 'granted': True,
                'entitlement': record['entitlement'] if record else None,
                'quota': record['quota'] if record else None,
                'note': 'Entitlement and metered ceiling written. The capability now '
                        'resolves as enabled (or degraded, if its provider is '
                        'unconfigured -- check GET ' + API + ').'}


@router.delete(API + '/{capability_id}/grant')
def revoke_capability(capability_id: str, request: Request):
    """Revoke the entitlement: refunds, support corrections, end of a comp."""
    factory = request.app.state.factory
    header = request.headers.get('authorization', '')
    if not header.startswith('Bearer ') or len(header) > 200:
        raise HTTPException(401, 'Valid bearer token required',
                            headers={'WWW-Authenticate': 'Bearer'})
    raw = header[7:]
    rate_limit(factory, 'capabilities:' + digest(raw), 120)
    with factory() as db:
        token = db.get(Token, digest(raw))
        if not token or token.expires_at <= now_ts() or token.revoked_at is not None:
            raise HTTPException(401, 'Invalid or expired token')
        user = db.get(User, token.user_id)
        if not user or getattr(user, 'status', 'active') != 'active':
            raise HTTPException(401, 'Account unavailable')
        removed = capabilities.revoke(db, user, capability_id)
        db.commit()
        return {'capability': capability_id, 'revoked': removed,
                'note': 'The metered quota policy stays in place: it is a ceiling, '
                        'not a permission.'}


#: The one remaining step to take real money, stated as data so the 402 body and the
#: docs cannot drift apart. A store integration verifies the store's own signature,
#: then calls ``capabilities.mint_receipt``; this route never changes.
_SEAM = {
    'step': 'Wire a payment provider, then mint the internal receipt this API already '
            'verifies.',
    'app_store': 'Verify the StoreKit transaction server-side (App Store Server API '
                 'or /verifyReceipt), then call capabilities.mint_receipt(capability, '
                 'key=app.state.signing_secret) and POST it here.',
    'stripe': 'Handle checkout.session.completed / customer.subscription events in a '
              'webhook after verifying the Stripe signature, then mint as above and '
              'POST here. Renewal events mint a fresh receipt; cancellation nothing '
              '(expiry does the work).',
    'no_store_yet': 'Until one is wired, operators grant via HARNESS_ENTITLEMENTS '
                    '(a comp) and developers mint receipts in tests with '
                    'capabilities.mint_receipt.',
    'runbook': 'docs/pay-to-enable.md',
}
