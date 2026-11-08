"""Account erasure: what deleting an account destroys, what survives, and for how long.

This module is the one place the deletion policy is stated, and ``legal/privacy.md``
section 7 restates it for the reader. When the two disagree the document is wrong, which
is why :func:`policy` is data rather than prose scattered through a route handler.

Two mechanisms carry the policy:

**The cascade.** Deleting the ``users`` row with ``PRAGMA foreign_keys=ON`` removes every
row that declares ``ON DELETE CASCADE`` against it - 25 tables plus the children that
cascade from those (``receipts`` via ``assessments``, ``attempts`` via ``receipts``,
``feedback_events`` via ``feedback``). The deletion path does not re-list those tables:
duplicating the schema in Python is how a deletion routine drifts from the database it
claims to describe. :func:`foreign_key_fates` reads the live schema instead, and
``tests/test_account_deletion.py`` fails if a new table with a ``users`` foreign key is
neither ``CASCADE`` nor ``SET NULL`` (``NO ACTION`` would block the delete at runtime).

**The erasure ledger.** A restore of an older snapshot replaces ``harness.sqlite3``
wholesale, so any tombstone stored *in that file* travels with the snapshot and is
rolled back with it. The ledger therefore lives outside the database, at
``<data_dir>/erased_accounts.jsonl``: an append-only, fsync'd line per erased account id.
It survives a restore, survives a WAL checkpoint, and is only removed when the data
directory is. On boot, and on every authenticated request, an account id in this file is
re-purged rather than trusted. That is what stops a restored pre-deletion snapshot from
silently reintroducing the account as a live login.

The ledger holds the account's opaque UUID, a timestamp and counts - never the email
address, the name, or anything the learner wrote.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Iterable

log = logging.getLogger('luminfest.erasure')

from .database_backup import (RETENTION_MAX_AGE_DAYS, RETENTION_MAX_ANCHORS,
                               RETENTION_MAX_BACKUPS, RETENTION_MAX_ON_DISK,
                               RETENTION_MAX_PRE_RESTORE)

#: How long a plaintext database snapshot may outlive the account it contains.
#:
#: ``app/database_backup.py`` writes whole-database copies to ``<data_dir>/backups/``
#: (manual, pre-migration and pre-restore). Those copies are the only place a deleted
#: account can still exist, and they are plaintext. The number is *imported*, not retyped:
#: the retention sweep and the deletion receipt must agree, and two constants typed in
#: different months is how a policy document ends up quoting a window the code does not
#: honour. The sweep also keeps the newest usable snapshot of each kind even when it is
#: older than this, and caps a directory at ``RETENTION_MAX_BACKUPS`` copies - both facts
#: the policy states, because "erased after 30 days" would otherwise be an over-claim.
BACKUP_RETENTION_DAYS = RETENTION_MAX_AGE_DAYS
BACKUP_MAX_COPIES = RETENTION_MAX_BACKUPS
BACKUP_MAX_PRE_RESTORE = RETENTION_MAX_PRE_RESTORE
BACKUP_MAX_ANCHORS = RETENTION_MAX_ANCHORS
BACKUP_MAX_ON_DISK = RETENTION_MAX_ON_DISK

ERASURE_LEDGER_NAME = 'erased_accounts.jsonl'
LEDGER_FORMAT = 1

#: Tables the cascade removes. Not a hand-maintained list: see :func:`foreign_key_fates`.
#: ``SET NULL`` tables keep their row and lose the reference; ``feedback`` is the one such
#: table whose *content* is the learner's own words, so the deletion path removes those
#: rows explicitly (the cascade cannot: it is told to null the column, not drop the row).
_SET_NULL_CONTENT_TABLES = ('feedback',)

#: Directories under ``data_dir`` that hold account-addressable artefacts and are deleted
#: with the account. Named here so the policy table and the purge cannot drift apart.
_ACCOUNT_DIRECTORIES = ('workspaces',)


# --------------------------------------------------------------------------- policy


def policy() -> dict[str, Any]:
    """The deletion policy as data: what goes, what stays, for how long, recoverable by whom.

    ``legal/privacy.md`` section 7 renders this. ``tests/test_account_deletion.py`` asserts
    the document still quotes :data:`BACKUP_RETENTION_DAYS`, so the number cannot be
    changed in code without the reader being told.
    """
    return {
        'backup_retention_days': BACKUP_RETENTION_DAYS,
        'destroyed_immediately': [
            {'what': 'The account row', 'detail': 'email, name, password hash, role, status'},
            {'what': 'All rows keyed to the account',
             'detail': 'attempts, assessments, receipts, learning states, tutor messages, '
                       'projects and reflections, memory notes, harness runs, flashcards, '
                       'projects and reflections, unit grade-book records, written '
                       'multi-perspective observations, procedure and playground runs, '
                       'telemetry, consent records, tokens, preferences, style profiles, '
                       'quota counters, experiment assignments, invite redemptions, '
                       'daily usage rollups, learner-built courses'},
            {'what': 'Feedback you submitted', 'detail': 'including its contact email field'},
            {'what': 'Your pre-launch waitlist entry, if you had one',
             'detail': 'matched by the address you signed up with; other people on the list '
                       'are untouched and you may sign up again'},
            {'what': 'The address on an invite addressed to you',
             'detail': 'the invite row is the operator\'s record and is kept with its email '
                       'fields blanked; invites you created for other people survive'},
            {'what': 'Sandbox workspace', 'detail': '<data_dir>/workspaces/<account id>/'},
            {'what': 'Decks and boards you own',
             'detail': 'decks/*.json and boards/board-*.json whose owner_id is the account; '
                       'any share link to a deleted board stops resolving'},
            {'what': 'Image-library entries', 'detail': 'your lines in media/image_owners.jsonl'},
        ],
        'survives': [
            {'what': 'Database snapshots in <data_dir>/backups/',
             'form': 'complete copies of the database, including the account row; '
                     'plaintext in the shipped desktop build',
             'for': (
                    f'up to {BACKUP_RETENTION_DAYS} days; at most {BACKUP_MAX_COPIES} '
                    f'ordinary copies (a total that includes the at most '
                    f'{BACKUP_MAX_PRE_RESTORE} automatic pre-restore copies) plus up to '
                    f'{BACKUP_MAX_ANCHORS} rollback anchors - never more than '
                    f'{BACKUP_MAX_ON_DISK} files. The newest snapshot overall and up to '
                    f'{BACKUP_MAX_ANCHORS} pre-migration rollback anchors (oldest dropped '
                    f'first) are kept past {BACKUP_RETENTION_DAYS} days'),
             'recoverable_by': 'anyone who can read this Mac\'s data directory, including '
                               'you. The developer holds no copy.'},
            {'what': 'Usage ledger rows (cost, tokens, latency)',
             'form': 'rows kept with the account reference removed; no learner content',
             'for': 'indefinitely (billing/accounting record)',
             'recoverable_by': 'nobody as an account: the row can no longer be tied to you'},
            {'what': 'Cached images the account fetched',
             'form': 'content-addressed files that lessons and other accounts may also use',
             'for': 'until nothing references them; the app has no reference-counting sweep',
             'recoverable_by': 'filesystem access only; no longer listed in your library'},
            {'what': 'Generated simulations and decks in <data_dir>/sims/',
             'form': 'generated content with no owner field',
             'for': 'indefinitely',
             'recoverable_by': 'they carry no account identifier, so they cannot be '
                               'attributed to you'},
            {'what': 'Board audit lines and share records',
             'form': 'opaque account id, action, timestamp, version - no work content',
             'for': 'indefinitely',
             'recoverable_by': 'filesystem access only'},
            {'what': 'The erasure ledger itself',
             'form': 'one line per erased account: opaque id, timestamp, counts',
             'for': 'indefinitely, so a restore cannot resurrect the account',
             'recoverable_by': 'filesystem access only; it is not a record of your activity'},
        ],
        'not_erased_by_unlink': (
            'Deleting a file does not overwrite the disk blocks it occupied. A filesystem '
            'snapshot or Time Machine backup taken before the sweep may still hold a copy '
            'until that snapshot expires; the app cannot reach into it.'
        ),
    }


# --------------------------------------------------------------------------- schema


def foreign_key_fates() -> dict[str, str]:
    """Every table with a foreign key to ``users``, mapped to its ``ON DELETE`` action.

    Read from ``Base.metadata`` rather than typed out, so the answer tracks the schema.
    ``course_builder`` owns one user-keyed table (``created_courses``) and is imported
    lazily by the app, so it is imported here: a policy that silently omitted a table
    because nobody had imported its module yet would be the defect this function exists
    to prevent.
    """
    from . import course_builder  # noqa: F401 - registers created_courses on Base
    from .db import Base

    fates: dict[str, str] = {}
    for table in Base.metadata.sorted_tables:
        for foreign_key in table.foreign_keys:
            if foreign_key.column.table.name == 'users':
                fates[table.name] = (foreign_key.ondelete or 'NO ACTION').upper()
    return fates


def cascade_tables() -> tuple[str, ...]:
    """Tables whose rows the ``users`` delete removes, per the declared foreign keys."""
    return tuple(sorted(name for name, fate in foreign_key_fates().items() if fate == 'CASCADE'))


def set_null_tables() -> tuple[str, ...]:
    """Tables that keep their row and lose the account reference when the account goes."""
    return tuple(sorted(name for name, fate in foreign_key_fates().items() if fate == 'SET NULL'))


# --------------------------------------------------------------------------- ledger


class ErasureLedgerUnreadable(RuntimeError):
    """The erasure ledger exists but cannot be read.

    Never folded into "nothing was ever erased". A security list that cannot be read is not
    a list of zero, so the caller must refuse: credentials are not issued, and startup is
    not completed.
    """


def ledger_path(settings) -> Path:
    """The authoritative ledger, next to the database."""
    return Path(settings.data_dir) / ERASURE_LEDGER_NAME


def ledger_paths(settings) -> tuple[Path, Path]:
    """The ledger and its mirror, **outside** the data directory.

    A database restore replaces one file, so the ledger lives beside it. A rollback of the
    whole data directory replaces the ledger too - and then the deletion and the file that
    records it disappear together, which is indistinguishable from "it never happened".
    The mirror sits in the parent directory (``.../Luminfest Learning Harness.erased_
    accounts.jsonl``), so a Time Machine restore of the data folder leaves the evidence
    behind and :func:`erased_ids` still condemns the account.

    The limit is worth stating: a restore of the *parent* folder (the whole of Application
    Support) takes the mirror with it, and no file inside that tree can detect it.
    """
    base = Path(settings.data_dir)
    mirror = base.parent / f'{base.name}.{ERASURE_LEDGER_NAME}'
    return base / ERASURE_LEDGER_NAME, mirror


def _fsync_dir(directory: Path) -> None:
    """Make a just-created or just-appended directory entry durable.

    ``fsync`` on the file does not persist the *name*: a power loss can leave the bytes on
    disk and the directory entry missing, which for this file means the tombstone silently
    never existed. macOS and Linux both support fsync on a directory descriptor.

    A failure is logged with the path and the errno and does not stop the deletion. Losing
    a directory fsync weakens a durability guarantee; refusing the user's deletion because
    of it would not restore that guarantee, so the deletion proceeds and the gap is said
    out loud in the log rather than swallowed.
    """
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError as exc:
        log.warning('could not open %s to fsync the ledger entry (errno=%s): %s',
                    directory, exc.errno, exc)
        return
    try:
        os.fsync(descriptor)
    except OSError as exc:
        log.warning('fsync of directory %s failed (errno=%s): %s - the ledger line is '
                    'written but its name may not survive a power loss',
                    directory, exc.errno, exc)
    finally:
        os.close(descriptor)


def _append_one(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'a', encoding='utf-8') as handle:
        handle.write(line + '\n')
        handle.flush()
        os.fsync(handle.fileno())
    _fsync_dir(path.parent)


def _append(settings, record: dict[str, Any]) -> None:
    """Append one tombstone line to the ledger and its out-of-directory mirror."""
    line = json.dumps({'format': LEDGER_FORMAT, **record}, ensure_ascii=False, sort_keys=True)
    primary, mirror = ledger_paths(settings)
    # Primary first: it is what protects a database-only restore, and it must be durable
    # before the row is deleted. The mirror extends the same protection to a rollback of
    # the whole data directory; if the parent directory refuses the write, the deletion
    # still proceeds (the account is not left half-alive) but the gap is logged loudly
    # rather than assumed away.
    _append_one(primary, line)
    try:
        _append_one(mirror, line)
    except OSError as exc:  # pragma: no cover - depends on the parent directory's mode
        log.error('erasure mirror could not be written (%s); a rollback of the data '
                  'directory would lose this deletion: %s', mirror, exc)


def record_erasure(settings, *, user_id: str, source: str = 'self_service',
                   artefacts: dict[str, Any] | None = None) -> dict[str, Any]:
    """Write the tombstone. Called **before** the database row is deleted, never after."""
    record = {
        'user_id': str(user_id),
        'at': round(time.time(), 3),
        'source': str(source),
        'backup_retention_days': BACKUP_RETENTION_DAYS,
        'phase': 'complete' if artefacts is not None else 'requested',
    }
    if artefacts is not None:
        record['artefacts'] = dict(artefacts)
    _append(settings, record)
    return record


_cache: dict[tuple, frozenset[str]] = {}


def _read_ids(path: Path) -> set[str]:
    """Every account id in one ledger file.

    A missing file is "nothing was ever erased" - a fresh install. A file that exists and
    cannot be read is :class:`ErasureLedgerUnreadable`: permissions, a partial restore, a
    volume that came back read-only. Returning an empty set there would turn an
    unreadable security list into a list of zero and let every deleted account sign in.
    """
    try:
        text = path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return set()
    except OSError as exc:
        raise ErasureLedgerUnreadable(f'{path}: {exc}') from exc
    ids: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get('user_id'):
            ids.add(str(row['user_id']))
    return ids


def erased_ids(settings) -> frozenset[str]:
    """Account ids that must never be live again: the union of the ledger and its mirror.

    Cached on the ``(mtime_ns, size)`` of both files, so a request does not re-read them
    while an append from another process is still picked up. Raises
    :class:`ErasureLedgerUnreadable` when a file is present but unreadable.
    """
    ids: set[str] = set()
    stamp: list[tuple] = []
    for path in ledger_paths(settings):
        try:
            stat = path.stat()
        except FileNotFoundError:
            stamp.append((str(path), None))
            continue
        except OSError as exc:
            raise ErasureLedgerUnreadable(f'{path}: {exc}') from exc
        stamp.append((str(path), (stat.st_mtime_ns, stat.st_size)))
    key = tuple(stamp)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    for path in ledger_paths(settings):
        ids |= _read_ids(path)
    frozen = frozenset(ids)
    if len(_cache) > 32:  # bounded: one entry per file state seen, not per request
        _cache.clear()
    _cache[key] = frozen
    return frozen


def ledger_readable(settings) -> bool:
    """Whether the ledger can be read. Used by startup to refuse rather than fail open."""
    erased_ids(settings)
    return True


def is_erased(settings, user_id: str) -> bool:
    return str(user_id) in erased_ids(settings)


def load_ledger(settings) -> list[dict[str, Any]]:
    """The whole ledger, oldest first. Used by tests and by operator tooling."""
    path = ledger_path(settings)
    out: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except OSError:
        return out
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


# --------------------------------------------------------------------------- artefacts


def _workspace_root(settings, user_id: str) -> Path | None:
    """The account's sandbox directory, or ``None`` when the id is not a safe path part."""
    user_id = str(user_id or '')
    if not user_id or user_id in {'.', '..', 'anonymous'} or '/' in user_id or '\\' in user_id:
        return None
    base = Path(settings.data_dir) / 'workspaces'
    return base / user_id


def purge_artefacts(settings, user_id: str) -> dict[str, Any]:
    """Remove the account's filesystem artefacts and return what was removed.

    Only stores the database is the sole index for, or that carry the account id as a
    path/field, are touched. Content-addressed caches shared with other accounts and
    generated artefacts with no owner field are deliberately left alone; the policy says
    so and ``tests/test_account_deletion.py`` asserts both halves.
    """
    user_id = str(user_id or '')
    removed: dict[str, Any] = {'decks': 0, 'boards': 0, 'workspaces': 0, 'image_claims': 0}
    if not user_id:
        return removed

    from . import deck as deck_store
    for row in deck_store.list_decks(settings, user_id):
        if deck_store.delete_deck(settings, str(row.get('id') or ''), owner_id=user_id):
            removed['decks'] += 1

    from .harness import board as board_store
    for row in board_store.list_for_owner(settings, user_id):
        if board_store.delete(settings, str(row.get('id') or ''), owner_id=user_id):
            removed['boards'] += 1

    workspace = _workspace_root(settings, user_id)
    if workspace is not None and workspace.is_dir():
        shutil.rmtree(workspace, ignore_errors=True)
        removed['workspaces'] = 0 if workspace.exists() else 1

    from .harness import media
    for sha in sorted(media.owned_shas(settings, user_id)):
        removed['image_claims'] += media.release_ownership(settings, user_id, sha)

    return removed


# --------------------------------------------------------------------------- erasure


def _remove_learner_traces(db, user) -> dict[str, int]:
    """Remove the surviving rows a ``SET NULL`` cascade would only anonymise *partly*.

    Three of the seven ``SET NULL`` tables keep something that still identifies or
    describes the learner after the reference is nulled. Each is handled here rather than
    described and left:

    * ``feedback`` -- keeps the message text and the contact email. The row *is* the
      learner's submission, so it is deleted.
    * ``waitlist_signups`` -- keeps the email address they signed up with. An erasure
      request outranks a marketing list; the row is deleted. Signing up again is open to
      them, and the other rows on the list are untouched.
    * ``beta_invites`` -- an invite addressed to their address keeps that address. The
      invite is the operator's record (it may have been redeemed, and the operator's
      counters should stay true), so the address fields are blanked and the row is kept.
    * ``rate_buckets`` -- not linked to ``users`` by a foreign key at all, so no cascade
      reaches it. Its key is ``sha256('auth:email:' + address)``, unsalted: a persisted hash
      of something that identifies the learner, kept for no reason once the account is gone.
      The address is known here, so the counter is deleted.

    ``feedback_events`` needs nothing: its events cascade away with their ``feedback`` row,
    and an event the learner *wrote* on someone else's ticket is operator correspondence
    with its author nulled. ``admin_audit_log`` and ``usage_ledger`` hold no learner
    content; ``users.referred_by`` is a pointer in *another* account's row.
    """
    from sqlalchemy import delete, update

    from . import accounts
    from .db import BetaInvite, Feedback, WaitlistSignup

    counts = {'feedback': 0, 'waitlist': 0, 'invite_addresses': 0, 'rate_buckets': 0}
    user_id = str(user.id)
    counts['feedback'] = int(db.execute(
        delete(Feedback).where(Feedback.user_id == user_id)).rowcount or 0)

    email = accounts.normalize_email(getattr(user, 'email', '') or '')
    if not email:
        return counts
    counts['waitlist'] = int(db.execute(
        delete(WaitlistSignup).where(WaitlistSignup.normalized_email == email)).rowcount or 0)
    counts['invite_addresses'] = int(db.execute(
        update(BetaInvite).where(BetaInvite.normalized_email == email)
        .values(email=None, normalized_email=None)).rowcount or 0)

    # The sign-in rate limiter persists ``sha256('auth:email:' + address)`` - unsalted, so
    # anyone with the database can test candidate addresses offline and learn whether a
    # given person used the app. That is a link to an erased account, so the counter is
    # deleted with it. The address is known here, which makes this a lookup rather than a
    # break. Spellings from before ``auth_limits`` normalised the address are included:
    # those rows were written from whatever casing the client sent.
    from .security import digest as _digest
    from .db import RateBucket

    spellings = {email, email.lower(), email.casefold(),
                 str(getattr(user, 'email', '') or '').strip(),
                 str(getattr(user, 'email', '') or '').strip().casefold()}
    keys = [_digest('auth:email:' + spelling) for spelling in spellings if spelling]
    if keys:
        counts['rate_buckets'] = int(db.execute(
            delete(RateBucket).where(RateBucket.key.in_(keys))).rowcount or 0)
    return counts


def erase(db, settings, user, *, source: str = 'self_service') -> dict[str, Any]:
    """Delete one account: tombstone first, then artefacts, then the row.

    Ordering is the safety property. If the process dies after the tombstone is written,
    the account is already condemned: :func:`reconcile` (boot) and :func:`purge_stale`
    (authenticated request) finish the job, and the account cannot log in meanwhile. The
    reverse order would leave a window in which the row was gone but a restore could
    still bring it back unwarned.
    """
    user_id = str(user.id)
    tombstone = record_erasure(settings, user_id=user_id, source=source)
    artefacts = purge_artefacts(settings, user_id)
    traces = _remove_learner_traces(db, user)
    db.delete(user)
    db.commit()
    completed = record_erasure(settings, user_id=user_id, source=source, artefacts=artefacts)
    log.info('erased account %s: %s, surviving-row traces %s', user_id, artefacts, traces)
    return {
        'user_id': user_id,
        'erased_at': tombstone['at'],
        'artefacts': artefacts,
        'traces': traces,
        'backup_retention_days': BACKUP_RETENTION_DAYS,
        'ledger': str(ledger_path(settings)),
        'phase': completed['phase'],
    }


def purge_stale(db, settings, user_id: str) -> bool:
    """Re-erase an account id that a restored snapshot has reintroduced.

    Returns ``True`` when a live row was found and removed. The caller has already
    refused the session; this leaves the database and the filesystem agreeing with the
    ledger instead of waiting for the next boot.
    """
    from .db import User

    user = db.get(User, str(user_id))
    if user is None:
        return False
    purge_artefacts(settings, str(user_id))
    _remove_learner_traces(db, user)
    db.delete(user)
    db.commit()
    log.warning('re-erased account %s that a database restore reintroduced', user_id)
    return True


def reconcile(factory, settings) -> list[str]:
    """Apply the ledger to the current database. Run at boot, before any route is served.

    A restore replaces the whole database file; this is what makes the deletion survive
    that. It is idempotent and cheap when the ledger is empty (one missing-file stat).
    """
    ids = erased_ids(settings)
    if not ids:
        return []
    from sqlalchemy import select

    from .db import User

    purged: list[str] = []
    with factory() as db:
        rows = list(db.scalars(select(User).where(User.id.in_(sorted(ids)))))
        for user in rows:
            try:
                purge_artefacts(settings, str(user.id))
                _remove_learner_traces(db, user)
                db.delete(user)
                purged.append(str(user.id))
            except Exception:  # noqa: BLE001 - one bad row must not stop the others
                log.exception('could not re-erase account from the ledger: %s', user.id)
        if purged:
            db.commit()
    if purged:
        log.warning('re-erased %s account(s) reintroduced by a database restore', len(purged))
    return purged


__all__ = [
    'BACKUP_RETENTION_DAYS',
    'ERASURE_LEDGER_NAME',
    'LEDGER_FORMAT',
    'cascade_tables',
    'erase',
    'erased_ids',
    'foreign_key_fates',
    'is_erased',
    'ledger_path',
    'load_ledger',
    'policy',
    'purge_artefacts',
    'purge_stale',
    'reconcile',
    'record_erasure',
    'set_null_tables',
]
