"""The capability matrix: every multimodal thing Luminfest can offer, and who gets it.

Multimodality used to be a property of the codebase -- an image was available if
``app/harness/media.py`` existed. That makes it impossible to sell, impossible to
explain to a learner whose image never arrives, and impossible for an operator to
switch off after an incident without a deploy. This module makes it a property of the
*configuration*: one declarative table (:data:`CAPABILITIES`), one resolver
(:func:`resolve`) and one grant path (:func:`grant`). Turning multimodality on is then
an operator flipping a setting and a learner paying -- not writing code.

Three rules the whole module obeys.

**Fail closed.** An unknown or unauthenticated principal resolves to the free tier.
There is no "default allow": a capability is granted by an entitlement row that
exists, not by the absence of a denial. A capability whose provider is unconfigured
*degrades* to its declared fallback with a reason string; it never errors and never
fakes output -- the same contract ``app/harness/provider.py`` already keeps for the
language model.

**Tiers are only what the database can enforce.** The honest reading of ``app/db.py``
is that there is no tier system: there are ``QuotaPolicy`` rows (scope
user/cohort/global, period day/month/lifetime, enforcement hard/soft/observe) and
cohort defaults. So this module ships exactly two tiers, ``free`` and ``plus``, where
``plus`` means "an entitlement row exists and a metered ``QuotaPolicy`` ceiling was
written with it". A tier that nothing enforces is a label, and a learner shown "Pro"
while the metering counter says "observe" has been lied to.

**The money is a seam, not a fake.** :func:`grant` accepts either a signed receipt
(minted by :func:`mint_receipt`, verified by :func:`verify_receipt`) or an operator
flag on ``Settings.entitlements``. Wiring App Store IAP or Stripe means writing the
*store* side only: verify the store's own signature in a webhook, then mint the
internal receipt this module already understands. The verify side of this file never
changes. ``docs/pay-to-enable.md`` is the runbook.
"""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import logging
import secrets
from dataclasses import dataclass
from typing import Any, Mapping

from fastapi import HTTPException, Request
from sqlalchemy import select

from .db import QuotaPolicy, UserPreference, now_ts
from .security import digest

log = logging.getLogger('luminfest.capabilities')

# --------------------------------------------------------------------- vocabulary

#: Tiers. Two, on purpose: a tier the quota machinery cannot enforce is a lie.
TIER_FREE = 'free'
TIER_PLUS = 'plus'
TIERS = (TIER_FREE, TIER_PLUS)

#: Code reality of a capability. ``missing`` rows are shown to the client so the UI
#: can hide them; they are never grantable.
STATUS_IMPLEMENTED = 'implemented'
STATUS_STUBBED = 'stubbed'
STATUS_MISSING = 'missing'

#: What the resolver decides for one principal.
STATE_ENABLED = 'enabled'      # entitled (or free) and the provider is ready
STATE_DEGRADED = 'degraded'    # entitled, but the provider is unconfigured; fallback
STATE_WITHHELD = 'withheld'    # not entitled; the reason explains what unlocks it

#: Default lifetime of a minted receipt: one month, matching a monthly subscription.
RECEIPT_TTL_DAYS = 31

#: Lifetime of an operator comp (``HARNESS_ENTITLEMENTS``). Ten years: a comp is not
#: a subscription and must not silently lapse.
OPERATOR_TTL_DAYS = 3650

#: Entitlements live in the ``ui`` JSON column of ``user_preferences`` under this key.
#: Deliberately not a new table: an entitlement is a small, account-scoped fact and
#: ``user_preferences`` is already the durable per-account JSON row that export and
#: deletion cover. A new table would also force a schema migration across every other
#: agent's in-flight work, for no enforcement gain.
ENTITLEMENT_KEY = 'capabilities'

#: Generated once per process. Only used when ``HARNESS_SECRET`` is unset, so receipts
#: do not verify across a restart -- exactly the failure mode the production
#: strong-secret requirement exists to prevent.
_PROCESS_KEY = secrets.token_urlsafe(32)


@dataclass(frozen=True)
class Capability:
    """One row of the matrix. Static facts only; the resolver adds the per-user view."""

    id: str
    title: str
    tier: str
    #: Which external service this consumes and what it costs the operator. 'none'
    #: means the capability runs entirely on this machine.
    provider: str
    #: The operator-level setting(s) that enable it. 'none' means always available.
    knob: str
    #: What the learner still gets when the provider is unavailable.
    fallback: str
    #: implemented / stubbed / missing -- the code reality, not the aspiration.
    status: str = STATUS_IMPLEMENTED
    #: Which provider probe decides readiness. See PROBES.
    probe: str = 'local'
    #: How a use of this capability is metered in ``usage_ledger``. The feature column
    #: is CHECK-constrained to a fixed set, so every capability reports as ``other``
    #: and carries its own name in the provider column instead.
    meter: str = ''
    #: Monthly price in micro-dollars. 0 for every row today: the paid shape is one
    #: Plus subscription that unlocks every ``plus`` row, not per-capability pricing.
    #: This is the field to change if that decision changes -- the doc records it as a
    #: placeholder, not a pricing study.
    price_micros: int = 0
    note: str = ''

    def public(self) -> dict:
        return {'id': self.id, 'title': self.title, 'tier': self.tier,
                'provider': self.provider, 'knob': self.knob, 'fallback': self.fallback,
                'status': self.status, 'meter': self.meter,
                'price': {'micros': self.price_micros, 'currency': 'USD',
                          'bundle': TIER_PLUS if self.tier == TIER_PLUS else None,
                          'note': 'Included in the Plus subscription; no per-capability '
                                  'price is charged.'},
                'note': self.note}


# --------------------------------------------------------------------- the matrix
#
# Every row was determined by reading the code that would have to run, not by reading a
# roadmap. "implemented" means a real call site exists today (the routes or the
# harness tools); "missing" means the interface would have to be invented. Nothing
# here is a stub: a stub is a promise of code that does not exist, and the one gap in
# the matrix is called ``missing`` rather than dressed up.
#
# The tutor's own language-model chat is deliberately absent: the teacher core is
# being rebuilt concurrently and its capability row belongs with it, not here.

CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        id='images', title='Real photographs in lessons', tier=TIER_PLUS,
        provider='Openverse, Wikimedia Commons, the Met and NASA over keyless HTTPS '
                 'through the licence gate (app/harness/media.py). Openverse is '
                 'rate-limited at 20 requests/minute and 200/day anonymously; '
                 'HARNESS_OPENVERSE_CLIENT_ID/SECRET lift that to 10,000/day.',
        knob='HARNESS_MEDIA_ENABLED=1 (plus optional Openverse credentials)',
        fallback='The deterministic figure pipeline (mathkit + harness/render.py) '
                 'still draws every concept figure from the mathematics; only real '
                 'photographs are withheld, and the lesson says which is which.',
        probe='media_network', meter='capability:images',
        note='Implemented: POST /api/v1/images/fetch and /for-lesson in '
             'app/routes_media.py are live today for every authenticated account.'),
    Capability(
        id='video', title='Curated video lessons', tier=TIER_PLUS,
        provider='YouTube oEmbed keyless probe for embeddability; '
                 'HARNESS_YOUTUBE_API_KEY enables the authoritative Data API check '
                 '(status.embeddable) and teacher search, which costs 100 units per '
                 'query against a 10,000/day default.',
        knob='HARNESS_MEDIA_ENABLED=1 (optionally HARNESS_YOUTUBE_API_KEY)',
        fallback='The curated allowlist still renders as plain outbound links; a '
                 'video that cannot be verified is never embedded on an assumption.',
        probe='media_network', meter='capability:video',
        note='Implemented: the allowlist, verification and teacher search live in '
             'app/harness/video.py and video_search.py.'),
    Capability(
        id='audio_tts', title='Spoken lessons (text to speech)', tier=TIER_PLUS,
        provider='edge-tts reaching Microsoft\'s public speech endpoint; no API key. '
                 'The package is NOT installed in this environment, so the tool refuses '
                 'honestly rather than synthesising anything.',
        knob='HARNESS_MEDIA_ENABLED=1 plus the edge-tts package installed',
        fallback='The lesson stays text; decks keep their speaker notes. No audio is '
                 'faked and no partial file is written.',
        probe='tts_package', meter='capability:audio_tts',
        note='Implemented: the text_to_speech tool in '
             'app/harness/tools_creation.py is complete; the readiness probe reports '
             'the missing package.'),
    Capability(
        id='web_search', title='Case-study web search', tier=TIER_PLUS,
        provider='DuckDuckGo through the ddgs package (the legacy duckduckgo_search '
                 'name is still honoured); every result passes the ingest licence gate '
                 'and an unaudited domain returns a link with no copied text. The '
                 'provider must be installed for live search.',
        knob='HARNESS_MEDIA_ENABLED=1 plus the ddgs package installed',
        fallback='No live search; the local material pack search still works and the '
                 'tutor cites only what it actually read.',
        probe='ddg_package', meter='capability:web_search',
        note='Implemented: the web_search and fetch_page_text tools exist and are '
             'licence-gated; the probe reports whether a provider is installed.'),
    Capability(
        id='browser_snapshot', title='Teacher page snapshots (headless browser)',
        tier=TIER_PLUS,
        provider='Playwright (installed) driving a fresh headless Chromium over the '
                 'open network. Teacher-only: the role gate lives in the toolbox.',
        knob='HARNESS_BROWSER_ENABLED=1 plus the teacher role',
        fallback='None -- the tool refuses with the reason. A snapshot is a copy of '
                 'pixels, so there is no degraded substitute to pretend with.',
        probe='browser', meter='capability:browser_snapshot',
        note='Implemented: app/harness/browser.py, gated in toolbox._browser_snapshot.'),
    Capability(
        id='course_creation', title='Build a course from your own material',
        tier=TIER_PLUS,
        provider='The configured OpenAI-compatible language model '
                 '(HARNESS_TUTOR_PROVIDER/URL/KEY). This is the capability whose use '
                 'is measured in tokens and dollars.',
        knob='HARNESS_TUTOR_PROVIDER != offline (plus an entitlement)',
        fallback='None: the builder refuses a plan it cannot ground, and says so. '
                 'Creating nothing is the honest outcome of having no model.',
        probe='llm', meter='capability:course_creation',
        note='Implemented: POST /api/v1/create/course and /upload are live; the '
             'builder refuses without a provider.'),
    Capability(
        id='vision_understanding', title='The tutor reads an image you upload',
        tier=TIER_PLUS, status=STATUS_MISSING,
        provider='Would need image content parts on the OpenAI-compatible chat API; '
                 'app/harness/provider.py is text-only today and there is no '
                 'image-to-model path anywhere in the codebase.',
        knob='none yet',
        fallback='None. The image still displays with its attribution; the tutor '
                 'simply cannot comment on it.',
        probe='none', meter='capability:vision_understanding',
        note='MISSING, and listed so the UI can hide it rather than sell it.'),
    Capability(
        id='simulations', title='Interactive simulations', tier=TIER_FREE,
        provider='none -- mathkit builds self-contained, validated HTML locally.',
        knob='none (always available)',
        fallback='Not applicable: no external service is involved, so the '
                 'capability is fully offline.',
        probe='local', meter='capability:simulations',
        note='Implemented: app/mathkit plus app/harness/sims_store.py validation.'),
    Capability(
        id='whiteboard_rich', title='Rich whiteboard', tier=TIER_FREE,
        provider='none -- the board document is local SVG state.',
        knob='none (always available)',
        fallback='Not applicable: fully local.',
        probe='local', meter='capability:whiteboard_rich',
        note='Implemented: app/harness/whiteboard.py and board.py.'),
    Capability(
        id='flashcards_auto', title='Automatic flashcards', tier=TIER_FREE,
        provider='The language model improves the prose when configured; the cards '
                 'themselves are generated deterministically from the curriculum and '
                 'scheduled by FSRS-6.',
        knob='HARNESS_TUTOR_PROVIDER (optional; offline still generates)',
        fallback='Deterministic cards from the curriculum -- generation degrades in '
                 'quality, never in availability.',
        probe='local', meter='capability:flashcards_auto',
        note='Implemented: app/flashcards.py plus /api/v1/flashcards in '
             'app/routes_flash.py.'),
    Capability(
        id='pptx_export', title='Real .pptx export', tier=TIER_FREE,
        provider='python-pptx, installed locally; the projection runs both ways '
                 '(export and import).',
        knob='none (python-pptx present)',
        fallback='The HTML/SVG deck remains available when the package is absent.',
        probe='pptx_package', meter='capability:pptx_export',
        note='Implemented: app/deck.py export_pptx/import_pptx with a structured '
             'refusal when the package is missing.'),
)

_BY_ID: dict[str, Capability] = {capability.id: capability for capability in CAPABILITIES}


def by_id(capability_id: str) -> Capability | None:
    return _BY_ID.get(capability_id or '')


def all_capabilities() -> tuple[Capability, ...]:
    return CAPABILITIES


# --------------------------------------------------------------------- the probes
#
# A probe answers one question: can this capability's cost driver actually run right
# now? It must never raise and never touch the network -- an import check and the
# settings it belongs to are enough to distinguish "off by the operator" from "the
# package is absent" from "ready", and the distinction is what the UI shows the
# learner.

def _installed(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):  # a namespace package with no usable spec
        return False


def _probe_media_network(settings) -> tuple[bool, str]:
    if not getattr(settings, 'media_enabled', False):
        return False, ('Network media is switched off for this instance '
                       '(HARNESS_MEDIA_ENABLED=0).')
    return True, 'Network media is enabled.'


def _probe_browser(settings) -> tuple[bool, str]:
    if not getattr(settings, 'browser_enabled', False):
        return False, ('The headless browser is switched off for this instance '
                       '(HARNESS_BROWSER_ENABLED=0).')
    if not _installed('playwright'):
        return False, 'The playwright package is not installed in this environment.'
    return True, 'The browser is enabled and playwright is installed.'


def _probe_tts_package(settings) -> tuple[bool, str]:
    if not getattr(settings, 'media_enabled', False):
        return False, ('Speech needs network media, which is off for this instance '
                       '(HARNESS_MEDIA_ENABLED=0).')
    if not _installed('edge_tts'):
        return False, 'The edge-tts package is not installed in this environment.'
    return True, 'edge-tts is installed.'


def _probe_ddg_package(settings) -> tuple[bool, str]:
    if not getattr(settings, 'media_enabled', False):
        return False, ('Search needs network media, which is off for this instance '
                       '(HARNESS_MEDIA_ENABLED=0).')
    from .harness import ddg_provider
    if not ddg_provider.installed():
        return False, ('No DuckDuckGo provider is installed in this environment '
                       '(neither ddgs nor the legacy duckduckgo_search).')
    return True, 'A DuckDuckGo search provider is installed.'


def _probe_pptx_package(settings) -> tuple[bool, str]:
    if not _installed('pptx'):
        return False, 'The python-pptx package is not installed in this environment.'
    return True, 'python-pptx is installed.'


def _probe_llm(settings) -> tuple[bool, str]:
    try:
        from .harness import provider
    except ImportError:  # pragma: no cover - harness is a core dependency
        return False, 'The provider adapter could not be imported.'
    if not provider.available(settings):
        return False, ('No language model is configured (HARNESS_TUTOR_PROVIDER is '
                       'offline).')
    return True, f"Language model {settings.provider_model} is configured."


def _probe_local(settings) -> tuple[bool, str]:
    return True, 'Runs on this machine; no external service is involved.'


PROBES = {
    'media_network': _probe_media_network,
    'browser': _probe_browser,
    'tts_package': _probe_tts_package,
    'ddg_package': _probe_ddg_package,
    'pptx_package': _probe_pptx_package,
    'llm': _probe_llm,
    'local': _probe_local,
    'none': lambda settings: (False, 'This capability does not exist yet.'),
}


def provider_ready(capability: Capability, settings) -> tuple[bool, str]:
    """(ready, note) for one capability. Never raises; never touches the network."""
    probe = PROBES.get(capability.probe, _probe_local)
    try:
        ready, note = probe(settings)
    except Exception as exc:  # a probe bug must not take the API down
        log.warning('capability probe %s failed: %s', capability.id, exc)
        return False, f'The readiness check for {capability.id} failed.'
    return bool(ready), str(note)


# --------------------------------------------------------------------- entitlements

def entitlements_of(db, user) -> dict:
    """This account's entitlement records, keyed by capability id.

    Read by primary key: ``user_preferences`` is user-scoped and its primary key *is*
    the user id, so the lookup is the one shape the ``app.user_scope`` guard allows
    without the audited hatch.
    """
    row = db.get(UserPreference, user.id) if user is not None else None
    caps = (row.ui or {}).get(ENTITLEMENT_KEY) if row is not None else None
    return caps if isinstance(caps, dict) else {}


def active_entitlement(entitlements: Mapping, capability_id: str,
                        now: float | None = None) -> dict | None:
    """The live entitlement for one capability, or None. An expired row is not a row.

    The expiry is checked here rather than swept by a job because a lapsed
    subscription must stop resolving *immediately*, not at the next cron tick.
    """
    now = now if now is not None else now_ts()
    entry = entitlements.get(capability_id) if isinstance(entitlements, Mapping) else None
    if not isinstance(entry, Mapping):
        return None
    try:
        # A corrupt row (a string where a number belongs) must read as "no
        # entitlement", not as a 500 on every matrix request.
        expires_at = entry.get('expires_at')
        if expires_at is not None and float(expires_at) <= now:
            return None
    except (TypeError, ValueError):
        log.warning('corrupt entitlement for %s ignored', capability_id)
        return None
    return dict(entry)


def operator_grants(settings) -> dict[str, set[str]]:
    """Parse ``Settings.entitlements``: comma-separated ``selector:cap,cap`` entries.

    The selector is an email address or ``*``. This is the no-store path: an operator
    comps a staff or tester account without a payment provider existing at all. It is
    a setting, not a loophole -- the doc says so in the same table as the prices.
    """
    grants: dict[str, set[str]] = {}
    for entry in getattr(settings, 'entitlements', ()) or ():
        selector, sep, caps = str(entry).partition(':')
        if not sep:
            continue
        selector = selector.strip().casefold()
        wanted = {cap.strip() for cap in caps.split(',') if cap.strip()}
        if selector and wanted:
            grants.setdefault(selector, set()).update(wanted)
    return grants


def operator_granted(settings, user, capability_id: str) -> bool:
    grants = operator_grants(settings)
    if not grants:
        return False
    email = str(getattr(user, 'email', '') or '').strip().casefold()
    return (capability_id in grants.get('*', set())
            or (bool(email) and capability_id in grants.get(email, set())))


def paid_plan(settings) -> dict:
    """The metered ceiling a grant installs. Soft enforcement, like the rest of Beta."""
    return {'period': 'month',
            'requests': getattr(settings, 'paid_monthly_requests', 2000),
            'total_tokens': getattr(settings, 'paid_monthly_tokens', 2_000_000),
            'enforcement': 'soft',
            'meter': 'usage_ledger (append-only; every provider call is recorded, '
                     'including fallbacks and errors)',
            'note': 'Metering is observational during the Beta: it records usage and '
                    'reports it without blocking a learner mid-session. Flipping the '
                    'policy to hard enforcement is an operator decision in '
                    'quota_policies, not a code change.'}


def _write_entitlement(db, user, capability_id: str, *, expires_at: float, source: str,
                       receipt_digest: str = '') -> dict:
    """Write the entitlement row and return the record that was stored.

    Goes through ``accounts.preferences_for`` so the row is created by the same path
    every other preference write uses. The dict is replaced rather than mutated in
    place: SQLAlchemy does not see in-place JSON mutation, and a grant that silently
    failed to persist is a paid feature that disappears on restart.
    """
    from . import accounts
    prefs = accounts.preferences_for(db, user)
    ui = dict(prefs.ui or {})
    caps = dict(ui.get(ENTITLEMENT_KEY) or {})
    now = now_ts()
    existing = caps.get(capability_id) if isinstance(caps.get(capability_id), dict) else {}
    # A renewal extends; it never shortens. An operator lowering a ceiling revokes
    # rather than re-grants, so max() is the honest merge.
    previous = float(existing.get('expires_at') or 0)
    caps[capability_id] = {'granted_at': now,
                           'expires_at': max(float(expires_at), previous),
                           'source': source,
                           'receipt_digest': receipt_digest,
                           'renewals': int(existing.get('renewals') or 0) + (1 if existing else 0)}
    ui[ENTITLEMENT_KEY] = caps
    prefs.ui = ui
    prefs.updated_at = now
    db.flush()
    return caps[capability_id]


def ensure_paid_quota(db, user, settings):
    """Install the paid monthly ceiling once; never clobber an operator's own policy.

    The unique partial index on ``(scope, scope_id, period)`` for active rows means a
    second grant cannot create a duplicate ceiling, so the existence check is a
    correctness check as well as an optimisation.
    """
    existing = db.scalar(select(QuotaPolicy).where(
        QuotaPolicy.scope == 'user', QuotaPolicy.scope_id == user.id,
        QuotaPolicy.is_active.is_(True)))
    if existing is not None:
        return existing
    policy = QuotaPolicy(scope='user', scope_id=user.id, period='month',
                         request_limit=getattr(settings, 'paid_monthly_requests', 2000),
                         token_limit=getattr(settings, 'paid_monthly_tokens', 2_000_000),
                         enforcement='soft')
    db.add(policy)
    db.flush()
    return policy


# --------------------------------------------------------------------- receipts

def receipt_key(settings, key: str | None = None) -> str:
    """The HMAC key for entitlement receipts.

    Preference order: the caller's key (``app.state.signing_secret``, which the
    lifespan seeds from ``HARNESS_SECRET`` or a persisted random secret), then
    ``HARNESS_SECRET``, then a per-process fallback so development still works. The
    fallback is why production requires a strong secret: without one, a restart
    invalidates every outstanding receipt.
    """
    if key:
        return key
    configured = str(getattr(settings, 'secret', '') or '')
    return configured or _PROCESS_KEY


def mint_receipt(capability_id: str, *, key: str, ttl_days: int = RECEIPT_TTL_DAYS,
                 now: float | None = None) -> str:
    """Issue ``capability.expires_at.hmac_sha256``. This is the store-side seam.

    A real App Store or Stripe integration verifies the store's own signature first,
    then calls this function with its own key. The rest of the system only ever sees
    the token this returns.
    """
    now = now if now is not None else now_ts()
    expires = int(now + ttl_days * 86400)
    payload = f'{capability_id}.{expires}'
    signature = hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f'{payload}.{signature}'


def verify_receipt(raw: str, capability_id: str, *, key: str,
                   now: float | None = None) -> tuple[bool, str, int]:
    """(ok, reason, expires_at). Never raises: a malformed token is a refusal.

    The capability id is inside the signed payload, so a receipt minted for ``video``
    cannot be replayed against ``images`` -- the classic capability-confusion bug this
    format exists to prevent. Expiry is part of the signed payload too, so extending
    it requires the key.
    """
    now = now if now is not None else now_ts()
    parts = str(raw or '').split('.')
    if len(parts) != 3:
        return False, 'The receipt is malformed (expected capability.expiry.signature).', 0
    cap, expiry, signature = parts
    if cap != capability_id:
        return False, 'The receipt was issued for a different capability.', 0
    if not expiry.isdigit():
        return False, 'The receipt has an unreadable expiry.', 0
    expected = hmac.new(key.encode(), f'{cap}.{expiry}'.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return False, 'The receipt signature does not verify.', 0
    if int(expiry) <= now:
        return False, 'The receipt has expired; renew the subscription.', 0
    return True, '', int(expiry)


# --------------------------------------------------------------------- grant/revoke

def grant(db, user, capability_id: str, *, settings, receipt: str | None = None,
          key: str | None = None, ttl_days: int | None = None,
          now: float | None = None) -> tuple[bool, str, dict | None]:
    """Grant one capability to one account. (ok, reason, record).

    The payment itself is out of scope by design: this function accepts *evidence of
    payment* -- a signed receipt, or the operator's own comp list -- and writes the
    entitlement plus the metered ceiling. Wiring a real store means minting the
    receipt after verifying the store's signature; see ``docs/pay-to-enable.md`` for
    the exact seam. Nothing here contacts a payment provider, and nothing here fakes
    one.

    ``ttl_days`` overrides the operator-comp lifetime only; a receipt's own expiry
    always wins, because a subscription that outlives its receipt is a free month.
    """
    capability = by_id(capability_id)
    if capability is None:
        return False, f'Unknown capability {capability_id!r}.', None
    if capability.status == STATUS_MISSING:
        return False, (f'{capability.title} is not implemented in this build, so it '
                       'cannot be granted.'), None
    if capability.tier == TIER_FREE:
        # Idempotent no-op, not an error: a free capability is already available and
        # "granting" it should read as a success to an app that does not know tiers.
        return True, 'Free-tier capabilities need no grant; nothing was written.', None
    now = now if now is not None else now_ts()
    key = receipt_key(settings, key)
    if receipt:
        ok, reason, expires_at = verify_receipt(receipt, capability_id, key=key, now=now)
        if not ok:
            return False, reason, None
        source = 'receipt'
    else:
        if not operator_granted(settings, user, capability_id):
            return False, ('No signed receipt was supplied, and the operator has not '
                           'comped this account (Settings.entitlements).'), None
        expires_at = now + (ttl_days if ttl_days is not None else OPERATOR_TTL_DAYS) * 86400
        source = 'operator'
    record = _write_entitlement(db, user, capability_id, expires_at=expires_at,
                                 source=source,
                                 receipt_digest=digest(receipt) if receipt else '')
    policy = ensure_paid_quota(db, user, settings)
    log.info('capability granted: user=%s capability=%s source=%s expires=%s',
             user.id, capability_id, source, record['expires_at'])
    return True, '', {'capability': capability_id, 'entitlement': record,
                      'quota': {'id': policy.id, 'period': policy.period,
                                'requests': policy.request_limit,
                                'total_tokens': policy.token_limit,
                                'enforcement': policy.enforcement}}


def revoke(db, user, capability_id: str) -> bool:
    """Remove the entitlement, if it exists. The quota policy stays on purpose: it is
    a ceiling, not a permission, and an operator may want to keep watching a lapsed
    account's usage."""
    row = db.get(UserPreference, user.id) if user is not None else None
    if row is None:
        return False
    ui = dict(row.ui or {})
    caps = dict(ui.get(ENTITLEMENT_KEY) or {})
    if capability_id not in caps:
        return False
    del caps[capability_id]
    ui[ENTITLEMENT_KEY] = caps
    row.ui = ui
    row.updated_at = now_ts()
    db.flush()
    log.info('capability revoked: user=%s capability=%s', user.id, capability_id)
    return True


# --------------------------------------------------------------------- resolver

def _withhold_reason(capability: Capability, *, authenticated: bool,
                     expired: bool) -> str:
    if not authenticated:
        return ('Sign in to use this capability; free capabilities are available '
                'without an account.')
    if expired:
        return ('This capability was part of your plan, but the entitlement has '
                'expired. Renew to switch it back on.')
    return ('This capability is part of Luminfest Plus. Pay to enable it, or ask the '
            'operator to comp this account.')


def resolve(user, settings, *, db=None, now: float | None = None) -> dict:
    """The capabilities this principal actually gets, with a reason for each refusal.

    ``user`` is a User row or None (anonymous / unknown). ``db`` is optional: without
    it only the operator comp list is consulted, which is the fail-closed answer for
    a caller with no account context. Nothing here raises; a caller with no settings
    gets the free tier.
    """
    now = now if now is not None else now_ts()
    authenticated = user is not None
    entitlements = entitlements_of(db, user) if (db is not None and user is not None) else {}
    live = {cap.id: active_entitlement(entitlements, cap.id, now=now)
            for cap in CAPABILITIES}
    rows = []
    for capability in CAPABILITIES:
        record = live.get(capability.id)
        granted = record is not None
        expired = (isinstance(entitlements.get(capability.id), Mapping)
                   and not granted
                   and bool(entitlements.get(capability.id)))
        ready, note = provider_ready(capability, settings)
        entry = capability.public()
        entry.update({'state': STATE_ENABLED, 'reason': '', 'granted': False,
                      'provider_ready': ready, 'provider_note': note})
        if capability.status == STATUS_MISSING:
            entry['state'] = STATE_WITHHELD
            entry['reason'] = ('Not implemented in this build; the UI should hide it '
                               'rather than offer it.')
        elif capability.tier == TIER_PLUS and not (authenticated and granted):
            entry['state'] = STATE_WITHHELD
            entry['reason'] = _withhold_reason(capability, authenticated=authenticated,
                                               expired=expired)
        elif not ready:
            entry['state'] = STATE_DEGRADED
            entry['reason'] = f'{note} Fallback: {capability.fallback}'
        if granted and record:
            entry['granted'] = True
            entry['entitlement'] = {'granted_at': record.get('granted_at'),
                                    'expires_at': record.get('expires_at'),
                                    'source': record.get('source')}
        rows.append(entry)
    return {'tiers': list(TIERS),
            'principal': {'authenticated': authenticated,
                          'user_id': getattr(user, 'id', None),
                          'tier': TIER_PLUS if any(r['granted'] for r in rows) else TIER_FREE},
            'paid_plan': paid_plan(settings) if settings is not None else {},
            'capabilities': rows,
            'note': 'Fail-closed by default: an unknown or unauthenticated principal '
                    'sees the free tier only. A capability whose provider is '
                    'unconfigured degrades to its fallback with the reason attached, '
                    'never an error and never a fake result.'}


def require_capability(capability_id: str):
    """A FastAPI dependency: refuse a caller who has not been granted ``capability_id``.

    This is the adoption seam for the existing routes. One line per route::

        @router.post('/api/v1/images/fetch')
        def fetch(payload: FetchInput, request: Request,
                  capability=Depends(require_capability('images'))):

    A withheld caller gets 402/403 carrying the matrix's own reason string, so the
    client can explain rather than silently downgrade; a degraded caller gets 503
    because the provider really is off and the fallback lives on a different route.
    """
    from .db import Token, User

    def dependency(request: Request):
        factory = getattr(request.app.state, 'factory', None)
        settings = getattr(request.app.state, 'settings', None)
        header = request.headers.get('authorization', '')
        if not header.startswith('Bearer ') or len(header) > 200:
            raise HTTPException(401, 'Valid bearer token required',
                                headers={'WWW-Authenticate': 'Bearer'})
        raw = header[7:]
        from .security import rate_limit
        rate_limit(factory, 'capabilities:' + digest(raw), 120)
        with factory() as db:
            token = db.get(Token, digest(raw))
            if not token or token.expires_at <= now_ts() or token.revoked_at is not None:
                raise HTTPException(401, 'Invalid or expired token')
            user = db.scalar(select(User).where(User.id == token.user_id))
            if not user or getattr(user, 'status', 'active') != 'active':
                raise HTTPException(401, 'Account unavailable')
            resolved = resolve(user, settings, db=db)
        entry = next((row for row in resolved['capabilities']
                      if row['id'] == capability_id), None)
        if entry is None:
            raise HTTPException(404, f'Unknown capability {capability_id!r}')
        if entry['state'] == STATE_WITHHELD:
            # Auth already passed above, so a withheld caller is always a payment
            # problem, never an authentication one: 402 is the honest code.
            raise HTTPException(402, entry['reason'])
        if entry['state'] == STATE_DEGRADED:
            raise HTTPException(503, entry['reason'])
        return entry

    return dependency
