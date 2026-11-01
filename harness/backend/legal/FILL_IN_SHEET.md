# Legal decision record

> **This document is not legal advice.** It records the decisions that were made so that the
> shipped legal text describes the product truthfully, and it names what still requires a
> lawyer. It is shipped inside the application bundle, so it contains no placeholders: the
> decisions below are the ones the text actually relies on.

**Status: filled, for the local desktop build.** Last decision: 1 November 2026.
Run `python backend/scripts/check_legal.py` for the live placeholder count (expected: zero).

## Why the previous draft could not ship

The four documents were written for a **hosted Beta** — a service with a managed PostgreSQL
database, a transactional email provider, an error-monitoring vendor and a company behind it.
The shipped bundle is not that. It is a single-user macOS application whose backend is a
process on the learner's own machine writing to one SQLite file. Filling the blanks in that
draft would have produced a privacy policy that was *specific and false*: it would have named
sub-processors that process nothing, promised encryption in transit over a loopback socket,
and told the reader their data was stored by a provider that does not exist.

Fixing the blanks was therefore not the task. The task was making the text describe the
product. Both were done in the same pass, because a filled template that describes the wrong
deployment is worse than an obvious template.

## Decisions recorded

| Decision | Value shipped | Rationale |
| --- | --- | --- |
| Operator | The Luminfest project, an unincorporated project operated by its developer | No entity has been incorporated. Naming one would be a false statement in a contract of adhesion. |
| Registered address | None claimed | An unincorporated project has no registered office. The text says so explicitly rather than omitting the line. |
| Governing law | Hong Kong Special Administrative Region of the People's Republic of China | Operator's jurisdiction. |
| Exclusive venue | Courts of the Hong Kong Special Administrative Region | Paired with an express preservation of local consumer-law rights, which no choice-of-court clause can override in the EU or UK. |
| Contact channel | In-app *Settings → Report a problem* | No mailbox is staffed. An address nobody reads is a worse disclosure than none, and the in-app route attaches version, platform and log context. |
| Sub-processors | None for learner data | Verified against the code: no error-reporting SDK, no hosted database path on the desktop profile (`HARNESS_ENV=desktop` keeps SQLite), and the mailer's transport defaults to `offline` — it queues in memory and sends nothing. SMTP exists but is reachable only when an operator sets `HARNESS_SMTP_HOST`, which the bundle does not. |
| Optional LLM provider | User-supplied, user's own key, user's own contract | The offline tutor is the default. A model is used only if `tutor.env` names one. |
| Optional image providers | Disclosed, and off by default in this build | `media_enabled` defaults to `0` on the desktop profile, so the shipped app makes none of these calls; the disclosure stays because a user can turn it on. |
| Telemetry retention | Not applicable — nothing is transmitted | Interaction events are rows in the local database, not outbound telemetry. |
| Account deletion | Immediate purge of that account's rows | Self-service in *Settings*. No backup copy exists to rotate out. |
| Backup rotation | None — we hold no backups | Stated rather than left blank. |
| Liability cap | Amount paid in the prior twelve months (zero, the Service being free), or the statutory minimum where local law forbids exclusion | No round figure is named. Naming one would imply an insurance policy this project does not have. |
| Accessibility response SLA | Ten business days | Matches the statement in `accessibility.md`. |

## What still requires a lawyer

Recorded here so that "filled" is not mistaken for "reviewed":

1. **Consumer-law review of the liability and venue clauses** in the markets you actually
   distribute to. The text preserves mandatory local rights, but only counsel can confirm it
   does so effectively in each jurisdiction.
2. **GDPR/UK GDPR applicability.** A controller established outside the EU/UK may still be in
   scope if it offers goods or services to, or monitors, people there. The text is written to
   GDPR vocabulary so the analysis is straightforward, but the analysis has not been done.
3. **Whether an EU representative is required** under Article 27 if the app is offered to EU
   users.
4. **The AI Act classification** in `ai.md`. The current text claims no high-risk use; that
   claim should be confirmed rather than assumed, particularly if a school deploys it.
5. **Age assurance.** The app enforces a 13+ attestation, not verification. Whether an
   attestation is sufficient depends on where you distribute.

## Procedure

1. Change a decision above → edit the four documents so the text still matches the decision.
2. Run `python backend/scripts/check_legal.py` until it prints `LEGAL OK`.
3. Bump `Settings.terms_version` (`HARNESS_TERMS_VERSION`, default in `app/config.py`) so that
   the version recorded at registration distinguishes accounts that accepted the old text.
4. Re-package. The packaging gate refuses a bundle whose legal text still contains
   placeholders, and there is no override that also produces a releasable filename.
