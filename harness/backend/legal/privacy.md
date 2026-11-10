# Privacy Policy

**Version:** 2026-11 · **Effective:** 1 November 2026

Luminfest is a desktop learning application that runs on your own Mac. This policy is short
because the product is small in this respect: there is no Luminfest server holding your data.
What the app records stays in a file you own, on a disk you own.

> **Status.** This document describes the shipped macOS build and was written from the
> software's actual behaviour, not from a template. It has not been reviewed by a lawyer.
> If you need a contractual assurance rather than a description, ask before relying on it.

## 1. Who we are

Luminfest is an unincorporated project operated by its developer. There is no registered
company, and no postal address is published — a project that has not incorporated has no
registered office to name, and inventing one would be worse than saying so.

**Data controller:** the Luminfest project. In practice, because the data never leaves your
device, the person who controls it is you.

**Contact:** *Settings → Report a problem* inside the app. We deliberately do not publish an
email address. A mailbox nobody staffs is a worse disclosure than no address at all, and an
in-app route reaches the developer with the diagnostic context attached.

## 2. Where your data lives

Everything the app records — your account, your answers, your messages to the tutor, your
progress — stays on your Mac. It is one SQLite database plus the files the app writes next
to it:

```
~/Library/Application Support/Luminfest Learning Harness/
├── harness.sqlite3     your account, answers, messages, progress, consent records
├── decks/  boards/     decks and boards you made, each file naming its owner
├── workspaces/         scratch files a lesson's sandbox wrote for you, one folder per account
├── media/              images the app downloaded, and which account asked for each
├── sims/  lectures/    generated lessons, decks and simulations (no account attached)
├── backend.log         the diagnostics log
└── backups/            snapshots of harness.sqlite3 — see section 7
```

The app's backend runs as a process on your own machine and listens only on the loopback
interface (`127.0.0.1`). It is not reachable from your local network or from the internet.
There is no account server and no sync, and the app itself sends nothing off this Mac
except the outbound paths listed in section 4. The `backups/` folder is a copy of your
data, but it is a copy on *your* disk: we never receive it.

## 3. What the app stores

| Category | Examples | Why | Lawful basis (GDPR) |
|---|---|---|---|
| Account | name, email address, Argon2id password hash | Identify your local profile and secure it | Contract |
| Learning records | attempts, correctness, time taken, self-reported confidence, concept mastery | Run the adaptive engine and show your progress | Contract |
| Content you write | project submissions, reflections, tutor messages, decks, boards, sandbox scratch files | Give feedback and keep your history | Contract |
| Consent records | when you accepted these Terms, what you consented to | Prove what you agreed to | Legal obligation |
| Optional activity signal | foreground-window heartbeats, **off by default** | Measure time-on-task in your own dashboard | Consent |
| Diagnostics | a local `backend.log` with process and error lines | Keep the app working | Legitimate interest |
| Interaction events | which control you tapped, never what you typed | Improve the app's own navigation | Consent |

**What the app does not collect:** it does not read your screen, keystrokes, clipboard,
files, other applications, contacts, or location. It does not run advertising trackers, and
it builds no advertising profile. Interaction events record *that* a control was used and
never the characters you typed; there is no field in which a character could be stored.

**Diagnostics stay on your device.** The app writes a log file next to its database. Nothing
uploads it. If you report a problem through *Report a problem*, you choose what to include.

## 4. The one outbound path, and how to turn it off

Until you configure a language model, **nothing leaves your Mac.** No key is shipped with the
app. In that state the tutor is explicitly degraded: it reports *model required*, and can
show grounded curriculum material with a notice that no model answered. It is not an offline
tutor product and we do not present it as one.

**A language model is required for the product to work as intended.** You supply your own
provider, model name and API key in **Settings → Language model**. The key is saved in the
app's data directory in a file readable only by your account, is never displayed again, and
is never sent anywhere except as the credential for requests to the provider you chose. An
operator may instead set the `HARNESS_TUTOR_*` variables, or place them in:

```
~/Library/Application Support/Luminfest Learning Harness/tutor.env
```

From that point on, the text of your messages and the lesson context needed to answer them
are sent to **the provider you chose**, under **your** account with that provider. Luminfest
does not operate that service, does not receive a copy of the exchange, and holds no key of
its own. To stop it, remove the configuration in Settings if you entered it there, or
delete `tutor.env` if an operator supplied it. The provider's own privacy terms govern
what it does with those requests — read them, because we cannot make promises on their
behalf.

Two further outbound paths exist. **Image and video search are on in the desktop build**
and off in a hosted production instance unless its operator enables them:

- **Image search.** The app queries open image collections (Openverse, the Metropolitan
  Museum, Wikimedia, NASA) for figures. It sends a search term, not your identity. A
  candidate is downloaded only when its own licence permits local storage; otherwise it
  remains a linked reference.
- **Video search.** The app reads YouTube's public results pages and oEmbed endpoint to
  verify that a video can be embedded. It sends the concept or segment search phrase, not
  your identity.
- **Curated links.** Lessons link to external resources such as Khan Academy, OpenStax and
  PhET. Opening one is an ordinary web request from your browser to that site, which will see
  your IP address as any website would. Luminfest does not embed trackers in those links.

## 5. Sharing

**We share nothing, because we hold nothing.** There are no sub-processors for learner data:
no hosting provider, no managed database, no transactional email service, and no crash or
error monitoring. The tables that appear in a hosted product's privacy policy have no rows
here, and this document says so rather than listing vendors that do not exist.

The app does contain a mailer, and it is deliberately inert in this build: its transport
defaults to *offline*, which queues messages in memory and sends nothing. A practical
consequence you should know before you rely on it: **this build cannot email you a password
reset.** Keep the password somewhere safe, and use *Settings → Export data* if you want an
independent copy of your progress.

| Sub-processor | Purpose | Location |
|---|---|---|
| None | Learner data is never transmitted to us | — |
| Your chosen LLM provider *(only if you configure one)* | Answers your tutor messages | Wherever that provider operates |
| Openverse, the Metropolitan Museum, Wikimedia, NASA, YouTube | Returns image/video results and embed verification for a search phrase | Wherever those providers operate |

The last two rows are **your** contracts, not ours. We disclose them so that the set of
parties who could see anything is complete.

## 6. International transfers

There is no transfer to disclose: we receive no personal data, so there is no export, no
onward transfer, and no transfer mechanism for us to rely on. If you configure a tutor or
image provider, that provider's location and transfer terms apply to your own use of it.

## 7. Retention

| Data | Retention |
|---|---|
| Account & learning records | On your device until you delete them |
| Interaction events | On your device; cleared when you delete your account |
| Auth tokens | Stored as digests; access tokens expire after 1 hour, refresh tokens after 60 days |
| Consent ledger | On your device until you delete your account |
| Decks, boards, sandbox files, image-library entries | On your device until you delete them |
| Snapshots in `backups/` | Deleted once older than **30 days**, except the newest snapshot overall and up to **4** pre-migration rollback anchors (oldest dropped first); at most **14** files in the folder |
| Diagnostics log | On your device; overwritten as it grows, removed with the app |

**Deleting an account is immediate for the live data.** In the same request that answers
success, the app deletes the account row and every row that belongs to it — answers,
assessments, tutor messages, projects, memory notes, flashcards, lesson and game runs,
telemetry, consent records, sessions and password-reset tokens, preferences, quota counters,
experiment assignments, invite redemptions, learner-built courses, the feedback you sent
us, your pre-launch waitlist entry if you had one, and the sign-in rate-limit counter keyed
by your address. That counter is an unsalted digest of the address: a persisted hash of
something that identifies you, kept for no reason after the account is gone, so it is
deleted with it. It also removes your address from any
invite that was addressed to you — the invite code itself is the operator's record and stays.
It also deletes the files that belong to the account and that nothing else indexes: the
sandbox folder in `workspaces/<your account id>/`, the decks and boards whose record names
you as owner (so any share link to them stops working), and your entries in the image
library index.

**One copy can survive the deletion, and only on your own disk: a snapshot in `backups/`.**
The app copies the whole database there before a schema upgrade, before a restore, and when
you ask it to. Those copies are complete copies of the database — unencrypted SQLite files
in the shipped build — so a snapshot taken before your deletion still contains your account,
including your email address and your messages. The folder holds at most **10** ordinary
snapshots, a total that includes the at most **3** automatic pre-restore copies, and any
snapshot older than **30 days** is deleted.

Two things are kept past 30 days, and both are stated because "deleted after 30 days" would
otherwise be an over-claim. The **newest usable snapshot in the folder** is never deleted,
whatever its kind, so the folder is never emptied by the age rule alone — that is the only
snapshot that escapes expiry by being recent. The **oldest pre-migration snapshot of a schema
version** is kept as a *rollback anchor*, because it is the only copy taken before that
upgrade: a crashed upgrade is retried, and each retry writes another snapshot of a database
that is already part-way through, so only the oldest one is a real rollback point. At most
**4** anchors are kept: the four most recently created anchors keep their schema version, and
the oldest is dropped first when a fifth arrives, so the upgrades you could realistically undo
are the ones that survive. Every other snapshot is deleted once it is older than 30 days,
including the newest of its kind.

The folder is therefore bounded, and this is the worst case rather than an average: at most
**10** snapshots — of which at most **3** are the automatic pre-restore copies — plus at most
**4** anchors, so never more than **14** files at once. Each is a plain file in a folder you
own, and deleting it is enough.

A restore also writes a snapshot of the database it is about to replace, before swapping the
older file in. Restoring these files yourself therefore adds copies to the folder, and those
copies are subject to the same 30 days and the same limits.

**Who could recover a deleted account from a snapshot:** anyone who can read that folder —
which means you, or anyone to whom you have given access to your Mac, for as long as the
snapshot exists. We never receive these files, so we cannot recover your account and cannot
read it. If you want the deletion to leave no recoverable copy at all, delete the
`backups/` folder yourself after deleting the account.

**A restored snapshot does not bring the account back — as long as the erasure record
survives.** Deletion writes the account's identifier to `erased_accounts.jsonl` next to the
database — deliberately *outside* the database, because restoring a snapshot replaces the
database file and would roll back anything stored inside it — and to a second copy one level
up, outside the data folder, so restoring the whole folder still leaves the record. The app
applies that record at every launch and on every request, sign-in, refresh and password
reset: the rows are deleted again and the credential is refused. **So long as either copy of
that record exists, the account cannot sign in, and cannot reach any HTTP route of the app
that accepts a credential** — whether the credential arrives in the `Authorization` header or
in the query string — even though the pre-deletion snapshot still contains its rows until the
snapshot itself is deleted. A WebSocket endpoint would sit outside that runtime refusal; the
app has none today.

**The limit of that promise is the record itself.** If both copies are removed, or the whole
parent folder is replaced from a backup taken before the deletion, the app cannot distinguish
that from a deletion that never happened: the account would be usable again. Nothing inside
the data folder can detect this, which is why the second copy lives outside it and why this
paragraph exists. Deleting the record is, in effect, undoing the deletion.

**Deleting a file is not the same as overwriting it.** The app unlinks its snapshots; it does
not scrub the disk blocks they used. A filesystem snapshot or a Time Machine backup taken
before the 30-day sweep may therefore still hold a copy of the database until that snapshot
expires. That copy is outside the app's reach and outside ours; FileVault, or turning off
Time Machine for this folder, is the control for it.

**Some records are kept, without your account attached to them.** Deleting the account
removes your reference from:

| Kept | What it is | Why |
|---|---|---|
| Model-call accounting | token counts, cost, latency per call | Billing and budget records; no learner content |
| Invites and experiments an operator created | access codes, cohort definitions, experiment variants | They are the operator's records, not yours. An invite addressed to you keeps its code and loses your address. |
| Audit lines for boards and shares | an opaque account id, an action, a timestamp, a version | Accountability for who changed a document; no work content |

Generated lessons, decks and simulations in `sims/` and `lectures/` are not tied to an
account at all: they carry no owner field, so they cannot be attributed to you and are not
deleted. Cached images are stored by content hash and may still be used by a lesson or by
another account; deleting your account removes only your library entries, not the shared
bytes.

**Spoken audio is the one artefact the app cannot trace back to you.** When the tutor reads a
passage aloud, the MP3 is cached under a hash of the text it speaks. That cache has no record
of which account asked for which clip, so a clip rendered from something you typed stays in
`media/audio/` after your account is deleted, and the app cannot remove yours without
removing every account's. Deleting the data folder removes it. We are telling you this rather
than describing the deletion as complete.

**Removing the application and the folder named in section 2 removes everything**, including
the snapshots and the erasure list, permanently — subject only to the block-level copies
described above.

## 8. Your rights

Because the data is on your machine, most of these need no request to anyone:

- **Access and portability** — *Settings → Export data* writes a machine-readable copy you
  can read, keep, or move.
- **Erasure** — *Settings → Delete account* removes the account and its records immediately.
  Snapshots of them follow the 30-day retention in section 7, with two deliberate exceptions —
  the newest snapshot overall, and up to four pre-migration rollback anchors (the oldest of
  those dropped first) — so a copy can outlive the deletion until you remove that file.
  Section 7 states exactly what goes, what stays and for how long. Deleting the data folder
  removes everything.
- **Rectification** — edit your profile in the app; your answers are your own record and can
  be deleted with the account.
- **Withdraw consent** — *Settings* toggles for activity tracking and model improvement, both
  off by default.
- **Object or complain** — use *Report a problem*. If you believe the processing is unlawful you
  may also complain to your local supervisory authority.

## 9. Security

Passwords are stored only as Argon2id hashes. Session tokens are stored as digests, never as
raw values. The backend binds to the loopback interface, so there is no listening port on
your network to attack. Data at rest is protected by your Mac's own disk encryption if you
have FileVault on — we cannot turn it on for you, and it is the single most effective control
available here.

No system is perfectly secure. Because we hold no copy of your data, a breach of our systems
cannot expose it; a breach of your Mac could, which is why FileVault and a login password
matter more here than in a hosted product.

## 10. Children

Luminfest is for users **13 and older**. Registration requires you to confirm your age and to
accept these Terms; both are enforced by the app, not merely stated. We do not knowingly
collect data from children under 13 — and in this build there is nowhere for such data to be
sent even if someone tried.

## 11. Changes

We version this policy. Material changes are announced in the app and, where required, ask you
to accept the new version before you continue. The version you accepted is recorded with your
account.

## 12. Accessibility of this notice

If you need this policy in another format or language, ask through *Report a problem* and we will
provide it.
