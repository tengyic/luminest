# B8 — post-registration navigation blocker

**Date of defect:** 2026-11-11 · **Evidence written:** 2026-11-15 · **Status:** fixed, code + tests + journey gate evidence below. This document is the missing deliverable inherited from the pre-beta backlog.

## Symptom

A learner who had just registered successfully was thrown back to the registration form
after the machine slept across the one-hour access-token TTL. The account existed in the
database, but the native app presented `AuthView` again and the freshly created account
looked "lost". Registration alone was never a successful journey — that is exactly why
the ten-journey gate exists.

## Root cause

The backend issues **two** credentials (`harness/backend/app/main.py:1063`,
`session_payload(access, refresh, user)`): a short-lived access token and a 60-day
rotating refresh token, with a public rotation endpoint `POST /api/v1/auth/refresh`
(`main.py:1065-1080`; public-route declaration at `app/security.py:283`).

The native client only persisted the access half. `AppStore.record(_:)` treated **every**
401 as an intentional sign-out and called `logout()` unconditionally. Once the access
token expired, a routine 401 was indistinguishable from a forced logout and the app
discarded a perfectly valid session. `logout()` also bumps `epoch`, which silently
invalidates every in-flight reply through the epoch guards.

## Fix (all four halves, verified in source)

| # | Change | Source |
| --- | --- | --- |
| 1 | Persist **both** halves on register/login: `SessionVault.store(access:refresh:endpoint:)` plus the legacy `SecureSession.write` for older builds; keep an in-memory refresh fallback when no default Keychain is available, and say so plainly in `notice`. | `Shared/State/AppStore.swift:470-493` |
| 2 | 401 on a **live authenticated** session now calls `renewExpiredSession()` instead of `logout()`. 403 is deliberately excluded — `StateViews` renders 401/403 with the same wording, but a forbidden request must never trigger a credential exchange. | `AppStore.swift:506-526` |
| 3 | Single-flight guard `sessionRefreshInFlight` prevents four concurrent loads from rotating against the same refresh token (the server invalidates it on first use). | `AppStore.swift:527-537` |
| 4 | `refreshSession()` swaps the refresh half for a new session with **no bearer**, keeps `user` and `epoch` intact, stores the rotated refresh token, replays `retryAction` (or reloads shell data), and signs out **only on a failed exchange**. | `AppStore.swift:538-590` |

Durable storage: `harness/native/Sources/LearningHarness/SessionVault.swift`. Test seam
`sessionRefreshExchange` (`AppStore.swift:329`) is deliberately narrow — only
`/auth/refresh` goes through it, so a regression test can drive the state machine without
network or a one-hour sleep.

## Regression tests

`harness/native/Tests/LearningHarnessTests/SessionRenewalTests.swift`

- `testExpiredAccessRenewsWithoutSigningOut()` (line 76)
- `test403NeitherRenewsNorSignsOut()` (line 113)
- `testNoRefreshCredentialStillSignsOut()` (line 142)

`harness/native/Tests/LearningHarnessTests/SessionVaultTests.swift`

- `testNilRefreshDropsAnyStaleRefreshCredential()` (line 63)

## Journey-gate evidence (not a claim)

`harness/outputs/native-qa/journey-full-10/run-summary.json` — this is the run that
closed the gate. Verified fields read directly from the file on 2026-11-15:

```json
"status": "passed",
"appExitCode": 0,
"nativeStatus": "completed",
"journeyGate": {"allGreen": true, "total": 10,
                "passed": ["J1","J2","J3","J4","J5","J6","J7","J9","J10","J8"],
                "failed": [], "blocked": [], "gaps": [], "missing": []},
"databaseVerified": true,
"screenshotsPresent": true
```

Selected database counts from the same run: `users=1`, `tokens=1`,
`refresh_tokens=1`, `attempts=1`, `flashcards=12`, `created_courses=1`,
`consent_ledger=2`, `learning_states=1`, `receipts=1`. The presence of
`refresh_tokens=1` is the data-side confirmation that the second credential half is
actually minted and stored during the real UI registration journey — the exact thing
B8 was missing.

## What is *not* claimed

- This document does not re-run the journey suite; it cites the existing green run.
  Re-running is a separate evidence action.
- A successful database registration alone is still not counted as a successful journey.
- The fix is in the working tree (`git status` shows `AppStore.swift` modified); it is
  **not committed**. Commit `60a70bd` is the last commit and is one ahead of origin.
