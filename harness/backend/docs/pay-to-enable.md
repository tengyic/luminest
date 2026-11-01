# Pay-to-enable: the runbook

End to end, from "multimodality is off" to "a user has paid and it is on". Numbered
so a non-author can follow it. Every command is copy-pasteable from `harness/backend`.

**Honest state of the money path.** Everything below a real payment provider is real
and tested: the capability matrix, the entitlement row, the metered ceiling, the
grant and revoke endpoints, and the signed-receipt verifier. What is *not* wired is
the store itself — there is no App Store or Stripe integration in this repository, and
nothing here pretends otherwise. Step 6 names the exact seam where one plugs in, and
the `402` response body a client receives carries that seam as data.

## 1. Declare the instance commercial

Charging for a product that embeds Khan Academy, PhET or MIT OCW content is a
licence violation decided by use, not by user. Set this **first**:

```bash
export HARNESS_COMMERCIAL_USE=1
```

Non-commercial sources are then withheld by evaluation — the card that would have
shown them says why — rather than by somebody remembering to delete an entry.

## 2. Turn the network capabilities on

```bash
export HARNESS_MEDIA_ENABLED=1        # images, video, speech, web search
export HARNESS_TUTOR_PROVIDER=openai  # the cost driver for course creation
export HARNESS_TUTOR_URL=https://api.deepseek.com/v1
export HARNESS_TUTOR_MODEL=deepseek-v4-pro
export HARNESS_TUTOR_KEY=...          # or DEEPSEEK_API_KEY in backend/.env
```

Optional but recommended before charging: `HARNESS_YOUTUBE_API_KEY` (authoritative
embeddability, teacher video search) and `HARNESS_OPENVERSE_CLIENT_ID/SECRET` (lift
Openverse from 200 to 10,000 requests/day). `HARNESS_BROWSER_ENABLED=1` only if the
teacher snapshot tool is part of the offer.

Restart the API, then confirm what the instance now offers:

```bash
curl -s localhost:8765/api/v1/capabilities | python3 -m json.tool | \
  python3 -c "import json,sys; [print(r['id'], r['tier'], r['state']) for r in json.load(sys.stdin)['capabilities']]"
```

Expected: the four `free` rows are `enabled`; the `plus` rows are `withheld` with
"Sign in to use this capability". That is the storefront rendering before anyone has
paid — the desired state for an anonymous visitor.

## 3. Enable the first paid capability (no store required yet)

The grant endpoint accepts a signed receipt. Until a store exists, the operator has
two honest ways to produce one; both write the same entitlement row.

### 3a. Comp an account by setting

```bash
export HARNESS_ENTITLEMENTS='staff@example.test:images,video'
```

Then, as that user (after signing in and keeping the bearer token in `$TOKEN`):

```bash
curl -s -X POST localhost:8765/api/v1/capabilities/images/grant \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'
# -> {"capability": "images", "granted": true, "entitlement": {"source": "operator", ...}}
```

### 3b. Mint a receipt exactly as a store webhook will

This is the shape every future store integration will produce; doing it by hand today
proves the verifier before the store exists. The key is
`app.state.signing_secret` — seeded from `HARNESS_SECRET` in production, otherwise a
persisted random secret (set `HARNESS_SECRET` before launch so receipts survive
restarts):

```bash
python3 - <<'PY'
import os
os.environ.setdefault('HARNESS_ENV', 'development')
from app.config import Settings
from app.main import create_app
from app import capabilities
settings = Settings.from_env()
app = create_app(settings)
key = app.state.signing_secret
print(capabilities.mint_receipt('images', key=key))
PY
```

Paste the printed token into:

```bash
curl -s -X POST localhost:8765/api/v1/capabilities/images/grant \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"receipt": "images.1794542251.65bb1378..."}'
```

## 4. Verify the grant

```bash
# The caller's own matrix now says enabled.
curl -s localhost:8765/api/v1/capabilities -H "Authorization: Bearer $TOKEN" | \
  python3 -c "import json,sys; [print(r['id'], r['state']) for r in json.load(sys.stdin)['capabilities']]"

# The entitlement row that resulted:
python3 - <<'PY'
import os
os.environ.setdefault('HARNESS_ENV', 'development')
from app.config import Settings
from app.main import create_app
settings = Settings.from_env()
with create_app(settings).state.factory() as db:
    from app.db import User, UserPreference, QuotaPolicy
    from sqlalchemy import select
    user = db.scalar(select(User).where(User.email == 'staff@example.test'))
    print('entitlement:', db.get(UserPreference, user.id).ui['capabilities'])
    print('quota:', [(p.period, p.request_limit, p.enforcement)
                     for p in db.scalars(select(QuotaPolicy).where(QuotaPolicy.scope_id == user.id))])
PY
```

And as a test, the whole flow end to end:

```bash
export TMPDIR="$PWD/.pytest-tmp"
/Users/tengyi/miniconda3/bin/python3 -m pytest tests/test_capabilities.py -q
```

## 5. Refusals a client must render

- `402` with `{"reason": ..., "seam": {...}}` — no valid receipt and no comp. The
  `seam` names the exact wiring step; the client shows the purchase UI.
- `402` "issued for a different capability" — a receipt is capability-bound by
  construction (the id is inside the signed payload), so it cannot be replayed across
  capabilities.
- `402` "signature does not verify" / "has expired" — tampered or lapsed.
- `409` — the capability is `missing` in this build; it cannot be granted.
- `200` with `granted: true, entitlement: null` — a free capability: a no-op by design.
- `503` (if the route adopts `require_capability`) — entitled but the provider is off;
  the reason names the knob and the fallback.

## 6. The one remaining step: wire the store

Everything above the store is real. This is the seam, and it is the only place a real
payment provider touches the system. A store integration does exactly two things:

1. **Verify the store's own signature, server-side.** App Store: the StoreKit
   transaction against the App Store Server API (`/verifyReceipt` or the Server API
   endpoints). Stripe: the `checkout.session.completed` and
   `customer.subscription.*` webhook events, verified with the webhook signing
   secret. Never trust the client's word that a payment happened.
2. **Mint the internal receipt and POST it to the existing endpoint.**

   ```python
   # in the webhook handler, after the store's signature verifies:
   from app.capabilities import mint_receipt
   receipt = mint_receipt(capability_id, key=app.state.signing_secret)
   # then POST {"receipt": receipt} to /api/v1/capabilities/{capability_id}/grant
   # on the user's behalf (or hand the receipt to the client to POST itself).
   ```

The verify side — `verify_receipt`, the entitlement row, the quota ceiling, the
resolver — does not change when this lands. Renewal events mint a fresh receipt (the
entitlement extends, never shortens); cancellation mints nothing, because expiry does
the work. `app/routes_multimodal.py` returns this same seam as data in every `402`
body, so the docs and the API cannot drift apart.

## 7. After charging

- **Refunds and corrections:** `DELETE /api/v1/capabilities/{id}/grant` revokes. The
  metered `quota_policies` row stays — it is a ceiling, not a permission, and an
  operator usually wants to keep watching a lapsed account's usage.
- **Expiry:** entitlement rows carry `expires_at`; a lapsed subscription stops
  resolving immediately, not at the next cron tick, and the matrix says "expired"
  rather than "not purchased".
- **Metering:** every provider call is already appended to `usage_ledger` (including
  fallbacks and errors) and rolled up daily, so cost per paid capability is
  reportable before anyone asks.
- **Hard enforcement:** the grant installs a monthly ceiling with
  `enforcement='soft'` — Beta practice is to record and report. Flipping a policy to
  `hard` is an operator edit in `quota_policies`, not a code change.
