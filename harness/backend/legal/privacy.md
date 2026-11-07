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
progress — is stored in one SQLite database on your Mac:

```
~/Library/Application Support/Luminfest Learning Harness/harness.sqlite3
```

The app's backend runs as a process on your own machine and listens only on the loopback
interface (`127.0.0.1`). It is not reachable from your local network or from the internet.
There is no account server, no sync, and no copy of your data anywhere else.

## 3. What the app stores

| Category | Examples | Why | Lawful basis (GDPR) |
|---|---|---|---|
| Account | name, email address, Argon2id password hash | Identify your local profile and secure it | Contract |
| Learning records | attempts, correctness, time taken, self-reported confidence, concept mastery | Run the adaptive engine and show your progress | Contract |
| Content you write | project submissions, reflections, tutor messages | Give feedback and keep your history | Contract |
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

By default, **nothing leaves your Mac.** The tutor is a deterministic offline tutor: it reads
the curriculum, your own answer history and the course graph, and answers with citations. It
needs no network connection.

If you want a language-model tutor, you supply your own provider URL, model name and API key
in:

```
~/Library/Application Support/Luminfest Learning Harness/tutor.env
```

From that point on, the text of your messages and the lesson context needed to answer them
are sent to **the provider you chose**, under **your** account with that provider. Luminfest
does not operate that service, does not receive a copy of the exchange, and holds no key of
its own. Delete the file to stop it. The provider's own privacy terms govern what it does
with those requests — read them, because we cannot make promises on their behalf.

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
| Consent ledger | Kept as long as needed to prove consent |
| Diagnostics log | On your device; overwritten as it grows, removed with the app |

**Deleting an account** purges that account's records from the database immediately. Removing
the application and the folder named in section 2 removes everything, permanently. There is no
backup we hold and therefore none to rotate out.

## 8. Your rights

Because the data is on your machine, most of these need no request to anyone:

- **Access and portability** — *Settings → Export data* writes a machine-readable copy you
  can read, keep, or move.
- **Erasure** — *Settings → Delete account* removes the account and its records. Deleting the
  data folder removes everything.
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
