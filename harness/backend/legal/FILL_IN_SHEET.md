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
| Required LLM provider | User-supplied, user's own key, user's own contract | No model is shipped or defaulted. The app boots in a declared *model-required* state until the user enters a provider/model/key in Settings, or an operator sets `HARNESS_TUTOR_*` / `tutor.env`. Requests then go only to that provider. |
| Optional image providers | Disclosed, and **on** by default in the shipped desktop build; off in a hosted production instance unless its operator opts in | `media_enabled` evaluates to `1` for `HARNESS_ENV=desktop` (`app/config.py`, `media_default`), so the shipped app *does* make these calls, and `privacy.md` §4 discloses exactly that. This row previously claimed the desktop default was `0`; that contradicted both the code and the published notice, and it is corrected here rather than by changing the behaviour, because the notice is the statement users are shown. Whether the desktop build *should* default outbound media on is an open product/legal decision — see *Open decisions* below. |
| Telemetry retention | Not applicable — nothing is transmitted | Interaction events are rows in the local database, not outbound telemetry. |
| Account deletion | Immediate deletion of the account row, every cascading row, the account's sandbox folder, its decks and boards, and its image-library entries | Self-service in *Settings*. The database is the only index for those files, so leaving them would be a deletion that did not delete. |
| What the `SET NULL` tables keep | Feedback the learner wrote is deleted; their waitlist entry is deleted; the address on an invite addressed to them is blanked; `feedback_events` cascade away with their feedback row; `usage_ledger` and `admin_audit_log` hold no learner content; `users.referred_by` is a pointer in another account's row. `rate_buckets` is not linked by a foreign key at all and held `sha256('auth:email:' + address)`; the sign-in counter is deleted too | Deleting the account nulls seven references rather than removing seven rows, so each of the seven was checked for surviving content rather than assumed clean. `rate_buckets` was the one table no foreign key reached: an unsalted digest of the address, kept for no reason once the account is gone. `admin_audit_log` and `feedback_events` currently have no writer in `app/`, so the surviving-note question is theoretical until one is added — a new writer must be reviewed against this row. |
| Generated audio | Kept, and disclosed in `privacy.md` §7 as the one artefact the app cannot attribute | Clips are cached under a hash of the spoken text with no account index. Making them erasable means an ownership index for the audio cache — a feature, not a change to the deletion path. |
| Backup retention | At most 10 ordinary snapshots per folder (a total that includes the at most 3 automatic pre-restore copies) **plus up to 4 rollback anchors — never more than 14 files**; any ordinary snapshot older than 30 days is deleted, except **the newest snapshot overall** and **up to 4 pre-migration rollback anchors** (one per schema version, the oldest anchor evicted first beyond 4); the newest of a kind is *not* exempt from age, only from the count cap; nothing unverifiable is ever deleted | The numbers live in `app/database_backup.RETENTION_*` and are imported by `app/account_erasure.py`, so the deletion receipt, the sweep and `privacy.md` cannot quote different ones. The newest-snapshot exception is stated because "erased after 30 days" would otherwise be false on a machine that has not taken a snapshot since. The age rule is absolute for ordinary copies — a count-cap protection was previously, wrongly, also treated as an age exemption, and the text said "the newest of each kind" was kept forever; the only two age exemptions are the newest snapshot overall and the anchors. The anchor exception is the upgrade rollback point: a crashed upgrade is retried, and each retry writes another snapshot of an already part-migrated database, so only the oldest of that version is a true pre-upgrade copy. Anchors are capped at `RETENTION_MAX_ANCHORS = 4` and ride on top of the ordinary budget, which is why the published worst case is `RETENTION_MAX_ON_DISK = 14` and not 10 — `privacy.md` states the two numbers with the nesting made explicit so a reader does not compute 10 + 3 + 4. A restore also writes a pre-restore snapshot of what it replaces, so restoring files adds copies subject to the same clock. `init_db.initialize()` refuses to migrate a database whose schema is ahead of its version stamp when such a snapshot exists, naming the file to restore. |
| Deletion and backups | A pre-deletion snapshot may still contain the account for up to 30 days; a restore cannot bring it back as a login **while the erasure record survives** | Deletion writes the account id to `erased_accounts.jsonl` **outside** the database, because restoring a snapshot replaces the database file and rolls back anything stored inside it, plus a mirror one level up so a rollback of the data folder still leaves the record. The list is applied by one resolver that every route module calls (enforced structurally: the HTTP boundary refuses a credentialed 2xx from a route that never resolved a principal), and at boot, login, refresh and password reset. An unreadable list refuses credentials and refuses startup — a security list you cannot read is not a list of zero. **Limit, stated in `privacy.md` §7 and here:** if both copies of the record are removed, or the whole parent folder is replaced from a backup, the app cannot distinguish that from a deletion that never happened; nothing inside the data folder can detect it. |
| Erasure ledger contents | Account UUID, timestamp, counts, retention window — no email, no name, nothing written by the learner | It must outlive the account to do its job, so it must be disclosable without keeping personal data. |
| Liability cap | Amount paid in the prior twelve months (zero, the Service being free), or the statutory minimum where local law forbids exclusion | No round figure is named. Naming one would imply an insurance policy this project does not have. |
| Accessibility response SLA | Ten business days | Matches the statement in `accessibility.md`. |

## Open decisions

Decisions the code and the published documents are consistent about, but which a human has
to ratify. Nothing here is blocked on engineering; each is a product/policy call that must
not be settled by an agent editing a document.

1. **Desktop outbound media default.** The shipped desktop build currently fetches from
   Openverse, the Metropolitan Museum, Wikimedia, NASA and YouTube by default
   (`media_enabled = 1` for `HARNESS_ENV=desktop`), and `privacy.md` §4 discloses that.
   Keeping it is defensible — the learner asked for live image and video search — but it is
   the one outbound network path the app takes on a learner's behalf without an explicit
   per-session action, so it needs a named owner's sign-off. If the decision is instead to
   default it off, the change is `config.py::media_default` plus `privacy.md` §4 plus this
   record, and `tests/test_desktop_environment.py` must move with them.

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
