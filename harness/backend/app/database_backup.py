"""SQLite backup / restore for the desktop learning harness.

The desktop install keeps one learner database at ``<data_dir>/harness.sqlite3``.
Upgrades are additive but not reversible, so ``scripts/init_db.initialize()`` takes an
online, WAL-safe copy *before* the first DDL statement and refuses to migrate if that
copy cannot be created and verified.

The public surface is deliberately small, so it works inside the PyInstaller frozen
backend and from a pinned virtualenv alike:

    create_sqlite_backup(db_path, ...)   -> manifest dict
    list_sqlite_backups(backup_dir)      -> [manifest dict]
    verify_sqlite_backup(backup_path)    -> verified manifest dict
    restore_sqlite_backup(backup, db)    -> restore receipt dict
    prune_sqlite_backups(backup_dir, ..) -> retention report dict
    schema_fingerprint(path)             -> table+column digest, or None
    maintenance_lock(lock_path)          -> exclusive, non-blocking context manager
    sqlite_path_from_engine(engine)      -> resolved Path, or None for PostgreSQL/memory

A backup is a ``.sqlite3``-named artefact plus a ``.json`` sidecar holding its SHA-256,
size, UTC timestamp, kind, schema versions, a ``schema_fingerprint`` of its tables and
columns, and its container format. Verification recomputes the checksum and opens the copy
independently with ``PRAGMA integrity_check``; a mismatch, a damaged file, or an artefact
that is not self-contained (a stray non-empty ``-wal`` beside it) is rejected before
anything is replaced. The fingerprint exists because a version stamp is one integer a
half-finished migration cannot update: it is what tells a true pre-migration copy from a
post-crash one that carries the same label.

Restore is guarded by an exclusive, non-blocking lock, folds the live WAL into the main
file, writes a ``pre-restore`` recovery snapshot, and swaps the verified copy in with a
single ``os.replace``. Any failure after the swap rolls the recovery snapshot back in.

A live database that cannot be used as a recovery source -- empty, not a SQLite file, or
failing ``integrity_check`` -- does not block the restore: it is moved to
``<backup_dir>/<name>.damaged.pre-restore-<token>`` as evidence and replaced. A database
held by another process is still refused, because that is a live writer rather than damage.
Staging debris (``.<name>.sqlite3.tmp`` and its SQLite siblings) is removed on every path
and swept by prune once it is an hour old, so no page-index remnants of restored data
accumulate in the live directory.

Retention policy
----------------
One sentence, quotable by a privacy reviewer:

    Luminest keeps at most 10 ordinary backups and at most 4 rollback anchors in one
    backup directory -- never more than 14 files in total -- deletes every ordinary backup
    older than 30 days except the newest copy in the directory, and never deletes a backup
    it cannot verify.

The numbers live in exactly one place -- the ``RETENTION_*`` constants immediately below
-- and every code path reads them through :data:`RETENTION`. ``prune_sqlite_backups``
implements them; ``create_sqlite_backup`` calls it after every successful write, and the
``prune`` CLI subcommand lets an operator run it on demand. The worst case is published as
a number rather than left to inference::

    on-disk total <= RETENTION_MAX_BACKUPS + RETENTION_MAX_ANCHORS   (10 + 4 = 14)

Why those numbers:

* ``RETENTION_MAX_BACKUPS = 10`` -- the ordinary budget, a *total* over every kind
  (manual, pre-migration, pre-restore), so the number of complete copies of learner data
  is bounded by one number a policy document can quote. Eleven schema versions have
  shipped and one pre-migration snapshot is taken per upgrade, so 10 preserves roughly the
  whole shipped upgrade history.
* ``RETENTION_MAX_AGE_DAYS = 30`` -- a month is long enough for an operator to notice
  post-upgrade data damage and short enough that an abandoned machine stops holding
  stale copies of learner records. It applies to every ordinary backup, whatever its kind.
* ``RETENTION_MAX_PRE_RESTORE = 3`` -- a pre-restore snapshot is a per-operation undo
  buffer, created by the operator's own restore command rather than by a release. It is
  capped *inside* the ordinary budget, so a run of restores cannot push the upgrade history
  out or grow the directory past the total. Three covers "restored, restored again, undo
  that".
* ``RETENTION_MAX_ANCHORS = 4`` -- see below. Anchors ride *on top* of the ordinary budget
  and are exempt from both the age rule and the count cap, which is why the published worst
  case is 14 and not 10.

Why rollback anchors exist, and why they are time-unbounded but number-bounded: a crashed
migration is *retried*. Each attempt re-reads the same recorded version, decides it still
needs to upgrade, and writes another ``pre-migration`` snapshot -- of a database that is
already half-upgraded. The newest snapshot therefore stops being "before the migration" at
all, and only the oldest one of that version is a real rollback point. That copy has to
outlive the 30-day rule, because the whole reason to keep it is an upgrade that turns out
to be wrong months later.

"Indefinite" must not mean "unbounded", so anchors are capped at ``RETENTION_MAX_ANCHORS``
and the oldest anchor is evicted first when the cap is reached. Four is not "one per
shipped version" (that number would rot with every release); it is the number of upgrades a
machine can be behind and still be a realistic recovery target: the upgrade that just broke,
the one before it, and slack for an install that skipped a couple of releases. Beyond that
an anchor is archaeology rather than recovery -- nobody can act on a v3 schema -- and every
extra one is another full copy of learner records. 4 keeps the worst case at 14 files,
within the same order as the 13 that the design allowed before anchors existed.

The exemptions from the age rule are exactly two, and both are stated so the promise above
is checkable rather than aspirational:

1. a **rollback anchor** (the oldest ``pre-migration`` snapshot of each ``from_version``),
   at most ``RETENTION_MAX_ANCHORS`` of them, oldest evicted beyond that; and
2. the **newest usable copy in the directory**, whatever its kind, so a folder is never
   emptied by age alone. A protection from the *count* cap is not a protection from
   *expiry*: the newest of a kind still dies at 30 days unless it is also the newest copy
   overall. That distinction is what makes "deleted once older than 30 days" true instead
   of nearly true.

There is deliberately no fourth "grace period" number. A backup is half-written only
between the moment its data file appears and the moment its sidecar is written, and the
sidecar is written *last*; in that window there is no sidecar, so the file is not
recognised as a backup and is never deleted. A complete sidecar means a finished copy.
Adding a freshness window on top of that would only make the count cap unenforceable
during a burst of restores, which is exactly when the cap matters.

Retention is *not* a deletion mechanism for learner data: restoring a snapshot restores
exactly what that snapshot contained, including records that a later account deletion
removed. Retention does not remove those records either -- it only bounds how many copies
exist and for how long. Account deletion cannot reach these files by unlinking the
directory (on a multi-account instance that would destroy every other learner's recovery
point, and a hosted PostgreSQL deployment has no such directory); instead
``app/account_erasure.py`` records an erasure ledger *outside* the database, which a
restore cannot roll back, and re-applies it after every restore. This module's promise is
narrow on purpose: a snapshot is an exact, verifiable copy of the moment it was taken, and
the number of such copies is bounded by the policy above.

Backup encryption
-----------------
The on-disk artefact is versioned. Format 1 is a plain SQLite file (legacy, still fully
readable). Format 2 is an encrypted container::

    b'LUMBKUP\\x02' | uint32 BE header length | header JSON | ciphertext | 16-byte GCM tag

Header JSON carries the cipher name, the random 96-bit nonce, a *key id* (a
domain-separated SHA-256 prefix of the key -- it identifies the key without revealing it)
and the creation timestamp. The header is authenticated as GCM additional data, so
downgrading the cipher, swapping the nonce or renaming the key id breaks the tag.

The key is read from ``LUMINEST_BACKUP_KEY`` (64 hex characters, or base64 of 32 raw
bytes) and is never written next to the ciphertext, into the manifest, or into any log.
Losing the key loses the backups; that is the honest trade-off of a key the operator
holds rather than one the app stores beside the data.

Encryption is requested with ``create_sqlite_backup(..., encrypt=True)``, or implied when
a key is configured. It is never silent: if encryption was requested and no key exists,
or the AES implementation is missing, the write fails with
:class:`BackupEncryptionError` instead of falling back to plaintext. Setting
``LUMINEST_BACKUP_REQUIRE_ENCRYPTION=1`` makes a plaintext write an error as well, so a
deployment can refuse to run without a key.

Verifying an encrypted backup necessarily writes a plaintext copy to the *system* temp
directory for the duration of ``PRAGMA integrity_check`` (SQLite cannot check a file it
cannot open); that copy is unlinked in a ``finally`` block and is never placed beside the
backups. This is documented rather than hidden.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import fcntl
import hashlib
import hmac
import json
import os
import shutil
import sqlite3
import struct
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

# --------------------------------------------------------------------------- constants

BACKUP_FORMAT = 1
"""Container format of a plain ``.sqlite3`` copy. Still written when no key is set."""

BACKUP_FORMAT_ENCRYPTED = 2
"""Container format of an AES-256-GCM sealed artefact."""

SUPPORTED_BACKUP_FORMATS = (BACKUP_FORMAT, BACKUP_FORMAT_ENCRYPTED)

CONTAINER_PLAINTEXT = 'sqlite-plaintext'
CONTAINER_AES_GCM = 'aes-256-gcm'

ENCRYPTED_MAGIC = b'LUMBKUP\x02'
ENCRYPTED_HEADER_MAX = 4096
GCM_NONCE_LEN = 12
GCM_TAG_LEN = 16
GCM_KEY_LEN = 32

BACKUP_KEY_ENV = 'LUMINEST_BACKUP_KEY'
BACKUP_REQUIRE_ENCRYPTION_ENV = 'LUMINEST_BACKUP_REQUIRE_ENCRYPTION'
BACKUP_KEY_ID_DOMAIN = b'luminest-backup-key-id\x00'

BACKUP_DIR_NAME = 'backups'
MAINTENANCE_LOCK_NAME = '.luminest-maintenance.lock'
SQLITE_MAGIC = b'SQLite format 3\x00'
TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'
STREAM_BLOCK = 1024 * 1024

#: Staging debris (``.<name>.sqlite3.tmp`` and its ``-journal``/``-wal``/``-shm``) is only
#: swept once it is this old. This is the *stated* cutoff, not a hidden one: debris is only
#: removed when ``STAGING_ORPHAN_AGE_HOURS`` has passed, i.e. "staging debris older than 24
#: hours is removed even if its writer is gone".
#:
#: Why a timer and not a liveness probe: proving that no process is writing would need
#: ``/proc/<pid>/fd`` (Linux only) or an external ``lsof`` (unavailable under a sandbox,
#: and racy anyway). SQLite does not hold a lock on a file it is copying into. So the
#: cutoff is set far past any plausible backup -- a 5 MB database copies in milliseconds,
#: and a 24-hour copy would be a wedged process whose debris is not data -- and the number
#: is published here and in the module docstring instead of being implied.
STAGING_ORPHAN_AGE_HOURS = 24

#: The retention policy, in one place. See the module docstring for the justification.
RETENTION_POLICY_VERSION = 1
RETENTION_MAX_BACKUPS = 10
RETENTION_MAX_AGE_DAYS = 30
RETENTION_MAX_PRE_RESTORE = 3
RETENTION_MAX_ANCHORS = 4
#: The published worst case. Anchors ride on top of the ordinary budget, so an operator or
#: a policy document can quote this one expression instead of reasoning about protections.
RETENTION_MAX_ON_DISK = RETENTION_MAX_BACKUPS + RETENTION_MAX_ANCHORS

#: Kind whose copies are capped by ``RETENTION_MAX_PRE_RESTORE`` instead of the main cap.
PRE_RESTORE_KIND = 'pre-restore'


class BackupError(RuntimeError):
    """A backup/restore operation could not be completed safely."""


class BackupVerificationError(BackupError):
    """A backup failed checksum or integrity verification and must not be restored."""


class BackupBusyError(BackupError):
    """Another process holds the maintenance lock or the live database."""


class BackupEncryptionError(BackupError):
    """A backup could not be encrypted or decrypted; never downgraded to plaintext."""


class BackupSourceError(BackupError):
    """The live database is not usable as a copy source: empty, corrupt or unreadable.

    Distinct from :class:`BackupBusyError` (a live process) because the remedy differs:
    a busy database must be waited on, a corrupt one is what a restore exists to replace.
    """


# --------------------------------------------------------------------------- retention


@dataclass(frozen=True)
class RetentionPolicy:
    """The retention promise, as data. Numbers come from the ``RETENTION_*`` constants."""

    max_backups: int
    max_age_days: int
    max_pre_restore: int
    max_anchors: int

    def __post_init__(self) -> None:
        if self.max_backups < 1:
            raise ValueError('max_backups must keep at least one backup')
        if self.max_pre_restore < 1:
            raise ValueError('max_pre_restore must keep at least one backup')
        if self.max_age_days < 1:
            raise ValueError('max_age_days must be at least one day')
        if self.max_anchors < 1:
            raise ValueError('max_anchors must keep at least one rollback anchor')

    def cap_for(self, kind: str | None) -> int:
        """How many backups of ``kind`` may be retained; ``max_backups`` is the hard total."""
        return self.max_pre_restore if kind == PRE_RESTORE_KIND else self.max_backups

    @property
    def max_on_disk(self) -> int:
        """The published worst case: the ordinary budget plus the anchor ceiling."""
        return self.max_backups + self.max_anchors

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


RETENTION = RetentionPolicy(
    max_backups=RETENTION_MAX_BACKUPS,
    max_age_days=RETENTION_MAX_AGE_DAYS,
    max_pre_restore=RETENTION_MAX_PRE_RESTORE,
    max_anchors=RETENTION_MAX_ANCHORS,
)


# --------------------------------------------------------------------------- utilities


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime(TIMESTAMP_FORMAT)


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(STREAM_BLOCK), b''):
            digest.update(block)
    return digest.hexdigest()


def _fsync(path: Path) -> None:
    with open(path, 'rb') as stream:
        os.fsync(stream.fileno())


def _sidecar_for(backup_path: Path) -> Path:
    return backup_path.with_suffix('.json')


def _staging_siblings(backup_path: Path) -> tuple[Path, Path]:
    """Staging names a concurrent writer would use for this artefact."""
    return (
        backup_path.with_name(f'.{backup_path.name}.tmp'),
        backup_path.with_name(f'.{backup_path.name}.sealed.tmp'),
    )


def _drop_sidecars(path: Path) -> None:
    """Remove SQLite's own siblings of a staging or just-rolled-over file.

    ``-journal``/``-wal``/``-shm`` next to a *staging* name are temporary by definition and
    are deleted only after the main file has been consumed or discarded. The live
    database's sidecars are parked as evidence elsewhere in :func:`restore_sqlite_backup`,
    never deleted here.
    """
    for suffix in ('-wal', '-shm', '-journal'):
        Path(str(path) + suffix).unlink(missing_ok=True)


def _stray_wal(path: Path) -> Path | None:
    """A non-empty ``-wal`` beside a backup artefact, if one is there.

    An artefact is supposed to be self-contained: :func:`create_sqlite_backup` writes a
    fresh file with a rollback journal, so a witness journal beside it means the copy was
    made by hand (or interrupted) and the frames in it were never folded in. Verification
    would silently *apply* those frames and restore would silently drop them - the two
    would disagree about the same snapshot - so the snapshot is refused instead.
    """
    wal = Path(str(path) + '-wal')
    try:
        if wal.is_file() and wal.stat().st_size > 0:
            return wal
    except OSError:
        return None
    return None


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    staging = path.with_name(f'.{path.name}.{uuid.uuid4().hex[:8]}.tmp')
    try:
        staging.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        _fsync(staging)
        os.replace(staging, path)
    finally:
        if staging.exists():
            staging.unlink()


def _load_manifest(backup_path: Path) -> dict[str, Any]:
    sidecar = _sidecar_for(backup_path)
    if not sidecar.is_file():
        raise BackupVerificationError(f'Backup sidecar is missing: {sidecar}')
    try:
        payload = json.loads(sidecar.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise BackupVerificationError(f'Backup sidecar is unreadable: {sidecar}: {exc}') from exc
    if not isinstance(payload, dict):
        raise BackupVerificationError(f'Backup sidecar is not an object: {sidecar}')
    if payload.get('format') not in SUPPORTED_BACKUP_FORMATS:
        raise BackupVerificationError(f'Unsupported backup format in {sidecar}')
    return payload


def _container_of(manifest: dict[str, Any]) -> str:
    if manifest.get('format') == BACKUP_FORMAT_ENCRYPTED:
        return str(manifest.get('container') or CONTAINER_AES_GCM)
    return str(manifest.get('container') or CONTAINER_PLAINTEXT)


def _open_readonly(path: Path, *, immutable: bool = False) -> sqlite3.Connection:
    # ``as_uri`` keeps spaces and non-ASCII characters in the resolved path intact.
    #
    # ``immutable=1`` is for *finished artefacts* only. A backup taken from a WAL database
    # is itself WAL-flagged, and merely opening such a file read-write-ish creates
    # ``-wal``/``-shm`` beside it -- litter in the backup directory, and litter that would
    # then look like the "stray witness journal" verification refuses. Immutable opens
    # never create files and never apply a journal, which is exactly right for a snapshot
    # that must never change. Never use it on the *live* database: it would ignore the
    # live WAL and report a stale schema.
    query = '?mode=ro&immutable=1' if immutable else '?mode=ro'
    return sqlite3.connect(f'{path.resolve().as_uri()}{query}', uri=True, timeout=0)


def _integrity_ok(path: Path) -> bool:
    try:
        with _open_readonly(path) as connection:
            row = connection.execute('PRAGMA integrity_check').fetchone()
            return bool(row) and row[0] == 'ok'
    except sqlite3.Error:
        return False


def _artefact_integrity_ok(path: Path) -> bool:
    """Integrity of a *finished* copy, opened without creating sidecars beside it."""
    try:
        with _open_readonly(path, immutable=True) as connection:
            row = connection.execute('PRAGMA integrity_check').fetchone()
            return bool(row) and row[0] == 'ok'
    except sqlite3.Error:
        return False


def _schema_version(path: Path, *, immutable: bool = False) -> int | None:
    try:
        with _open_readonly(path, immutable=immutable) as connection:
            row = connection.execute(
                'SELECT version FROM schema_version WHERE id = 1'
            ).fetchone()
            return int(row[0]) if row else None
    except sqlite3.Error:
        return None


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def schema_fingerprint(path: os.PathLike | str, *, immutable: bool = False) -> str | None:
    """Digest of the sorted table+column pairs in a database file, or ``None``.

    A version stamp is a single integer a half-finished migration cannot update, so it can
    claim v5 while v6 columns and v11 tables already exist on disk. The fingerprint is what
    distinguishes the two, and it is recorded in every sidecar so ``list`` can show it
    without opening the artefact.

    ``immutable`` must stay ``False`` for a live database (a WAL would otherwise be
    ignored); callers pass ``True`` only for a finished copy.
    """
    try:
        with _open_readonly(Path(path).expanduser().resolve(), immutable=immutable) as connection:
            tables = [
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%' ORDER BY name"
                ).fetchall()
            ]
            shape: list[str] = []
            for table in tables:
                columns = sorted(
                    row[1]
                    for row in connection.execute(
                        f'PRAGMA table_info({_quote(str(table))})'
                    ).fetchall()
                )
                shape.append(f'{table}(' + ','.join(columns) + ')')
    except sqlite3.Error:
        return None
    if not shape:
        return None
    digest = hashlib.sha256('\n'.join(shape).encode('utf-8')).hexdigest()
    return f'sha256:{digest[:32]}'


def sqlite_path_from_engine(engine) -> Path | None:
    """Return the resolved SQLite file path, or ``None`` for PostgreSQL/in-memory DBs.

    Callers must record this value *before* running a database operation; the acceptance
    driver logs it so the isolation of every test database is auditable.
    """
    if getattr(engine.dialect, 'name', None) != 'sqlite':
        return None
    database = getattr(engine.url, 'database', None)
    if not database or database in (':memory:', ''):
        return None
    return Path(database).expanduser().resolve()


def default_backup_dir(db_path: Path) -> Path:
    return db_path.parent / BACKUP_DIR_NAME


def default_lock_path(beside_dir: Path) -> Path:
    """The maintenance lock that guards a backup directory's data directory."""
    return Path(beside_dir).expanduser().resolve().parent / MAINTENANCE_LOCK_NAME


# --------------------------------------------------------------------------- locking

#: Lock files this process currently holds. ``fcntl.flock`` is per open-file-description,
#: so a second acquisition of the same lock file fails even inside the same process --
#: which is the behaviour restore relies on. The set lets ``prune_sqlite_backups`` notice
#: that the lock is already ours (create runs inside restore's critical section) and skip
#: a second acquisition instead of colliding with itself.
_HELD_LOCKS: set[str] = set()


def _lock_held_here(lock_path: os.PathLike | str) -> bool:
    return str(Path(lock_path).expanduser().resolve()) in _HELD_LOCKS


@contextmanager
def maintenance_lock(lock_path: Path) -> Iterator[Path]:
    """Hold an exclusive, non-blocking lock; never wait on or disturb another process."""
    path = Path(lock_path).expanduser().resolve()
    key = str(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, 'a+b')
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise BackupBusyError(
                f'Another maintenance operation holds {path}; restore refused.'
            ) from exc
        _HELD_LOCKS.add(key)
        try:
            yield path
        finally:
            _HELD_LOCKS.discard(key)
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


# --------------------------------------------------------------------------- encryption


def _crypto_module() -> tuple[Any, str]:
    """Return ``(AES, version)`` from pycryptodome, or refuse -- never fall back."""
    try:
        from Crypto.Cipher import AES  # type: ignore[import-not-found]
        from Crypto import __version__ as version  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - depends on the installed environment
        raise BackupEncryptionError(
            'Backup encryption needs the pycryptodome package (AES-GCM) and it is not '
            f'importable from this interpreter: {exc}. Install pycryptodome, or create '
            'plaintext backups on purpose with encrypt=False.'
        ) from exc
    return AES, str(version)


def load_backup_key(environ: Mapping[str, str] | None = None) -> bytes | None:
    """Read the 256-bit backup key from the environment; ``None`` when unset.

    A malformed value is an error, never a silent fallback: a typo in the key must not
    quietly produce a backup nobody can decrypt.
    """
    source = os.environ if environ is None else environ
    raw = source.get(BACKUP_KEY_ENV)
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        raise BackupEncryptionError(f'{BACKUP_KEY_ENV} is set but empty')
    key: bytes | None = None
    if len(value) == 2 * GCM_KEY_LEN:
        try:
            key = binascii.unhexlify(value)
        except (binascii.Error, ValueError):
            key = None
    if key is None:
        padded = value + '=' * (-len(value) % 4)
        try:
            key = base64.urlsafe_b64decode(padded.encode('ascii'))
        except (binascii.Error, ValueError, UnicodeEncodeError):
            key = None
    if key is None or len(key) != GCM_KEY_LEN:
        raise BackupEncryptionError(
            f'{BACKUP_KEY_ENV} must be {GCM_KEY_LEN} raw bytes as '
            f'{2 * GCM_KEY_LEN} hex characters or standard base64'
        )
    return key


def _key_id(key: bytes) -> str:
    """A stable, non-reversible label for a key, safe to store in the manifest."""
    return hashlib.sha256(BACKUP_KEY_ID_DOMAIN + key).hexdigest()[:16]


def _require_encryption_flag(environ: Mapping[str, str] | None = None) -> bool:
    source = os.environ if environ is None else environ
    return str(source.get(BACKUP_REQUIRE_ENCRYPTION_ENV, '')).strip().lower() in (
        '1', 'true', 'yes', 'on',
    )


def _resolve_key(encrypt: bool | None, *, key: bytes | None = None) -> bytes | None:
    """Decide whether this write is encrypted, and with which key.

    Returns the key to use, or ``None`` for an intentional plaintext write. Raises rather
    than downgrading when encryption was asked for and cannot be honoured.
    """
    resolved = load_backup_key() if key is None else key
    required = _require_encryption_flag()
    if encrypt is None:
        encrypt = resolved is not None or required
    if encrypt:
        if resolved is None:
            raise BackupEncryptionError(
                f'Backup encryption was requested but {BACKUP_KEY_ENV} is not set; '
                'refusing to write a plaintext copy of the database instead'
            )
        _crypto_module()  # fail here, before any bytes are staged
        return resolved
    if required:
        raise BackupEncryptionError(
            f'{BACKUP_REQUIRE_ENCRYPTION_ENV} is set, so a plaintext backup is refused'
        )
    return None


def _seal(plain: Path, out_path: Path, key: bytes, plaintext_sha256: str) -> dict[str, Any]:
    """Encrypt ``plain`` into the versioned container at ``out_path``.

    ``plaintext_sha256`` goes *inside* the authenticated header. The digest of the
    ciphertext (in the sidecar) can be recomputed by anyone holding the file, so it proves
    nothing about which snapshot this is; the digest of the plaintext can only be produced
    by someone holding the key. Repeating it in the header is what makes the sidecar's copy
    unforgeable: a verifier can require the two to agree, and the header is authenticated.
    """
    aes, version = _crypto_module()
    nonce = os.urandom(GCM_NONCE_LEN)
    header = {
        'v': BACKUP_FORMAT_ENCRYPTED,
        'cipher': CONTAINER_AES_GCM,
        'nonce': base64.b64encode(nonce).decode('ascii'),
        'key_id': _key_id(key),
        'created_at': _utc_now(),
        'plaintext_sha256': plaintext_sha256,
        'crypto': f'pycryptodome-{version}',
    }
    header_bytes = json.dumps(header, sort_keys=True, separators=(',', ':')).encode('utf-8')
    prefix = ENCRYPTED_MAGIC + struct.pack('>I', len(header_bytes)) + header_bytes
    cipher = aes.new(key, aes.MODE_GCM, nonce=nonce, mac_len=GCM_TAG_LEN)
    cipher.update(prefix)
    digest = hashlib.sha256()
    written = 0
    with open(plain, 'rb') as source, open(out_path, 'wb') as sink:
        sink.write(prefix)
        digest.update(prefix)
        written += len(prefix)
        for block in iter(lambda: source.read(STREAM_BLOCK), b''):
            chunk = cipher.encrypt(block)
            sink.write(chunk)
            digest.update(chunk)
            written += len(chunk)
        tag = cipher.digest()
        sink.write(tag)
        digest.update(tag)
        written += len(tag)
    return {
        'sha256': digest.hexdigest(),
        'size': written,
        'key_id': header['key_id'],
        'header': header,
    }


def _unseal(path: Path, dest: Path, key: bytes) -> dict[str, Any]:
    """Decrypt ``path`` into ``dest``; refuse tampering, truncation or a foreign key.

    On any failure ``dest`` is removed, so a refused artefact can never be mistaken for a
    usable plaintext database by a later step.
    """
    aes, _version = _crypto_module()
    try:
        with open(path, 'rb') as stream:
            magic = stream.read(len(ENCRYPTED_MAGIC))
            if magic != ENCRYPTED_MAGIC:
                raise BackupVerificationError(
                    f'Backup is not a LUMBKUP container: {path.name}'
                )
            raw_length = stream.read(4)
            if len(raw_length) != 4:
                raise BackupVerificationError(f'Encrypted backup header is truncated: {path.name}')
            header_length = struct.unpack('>I', raw_length)[0]
            if not 0 < header_length <= ENCRYPTED_HEADER_MAX:
                raise BackupVerificationError(
                    f'Encrypted backup header length is implausible ({header_length}): {path.name}'
                )
            header_bytes = stream.read(header_length)
            if len(header_bytes) != header_length:
                raise BackupVerificationError(f'Encrypted backup header is truncated: {path.name}')
            try:
                header = json.loads(header_bytes)
            except ValueError as exc:
                raise BackupVerificationError(
                    f'Encrypted backup header is unreadable: {path.name}: {exc}'
                ) from exc
            if not isinstance(header, dict) or header.get('cipher') != CONTAINER_AES_GCM:
                raise BackupVerificationError(
                    f'Unsupported encrypted container in {path.name}: {header!r}'
                )
            expected_key_id = _key_id(key)
            if header.get('key_id') != expected_key_id:
                raise BackupEncryptionError(
                    f'Backup {path.name} was sealed with key id {header.get("key_id")!r} '
                    f'but the configured key is {expected_key_id!r}'
                )
            try:
                nonce = base64.b64decode(str(header.get('nonce')), validate=True)
            except (binascii.Error, ValueError) as exc:
                raise BackupVerificationError(
                    f'Encrypted backup nonce is unreadable: {path.name}'
                ) from exc
            if len(nonce) != GCM_NONCE_LEN:
                raise BackupVerificationError(
                    f'Encrypted backup nonce has the wrong length: {path.name}'
                )

            prefix = magic + struct.pack('>I', header_length) + header_bytes
            total = path.stat().st_size
            body = total - len(prefix)
            if body <= GCM_TAG_LEN:
                raise BackupVerificationError(f'Encrypted backup body is truncated: {path.name}')
            ciphertext_length = body - GCM_TAG_LEN
            cipher = aes.new(key, aes.MODE_GCM, nonce=nonce, mac_len=GCM_TAG_LEN)
            cipher.update(prefix)
            digest = hashlib.sha256()
            produced = 0
            remaining = ciphertext_length
            with open(dest, 'wb') as sink:
                while remaining:
                    block = stream.read(min(STREAM_BLOCK, remaining))
                    if not block:
                        raise BackupVerificationError(
                            f'Encrypted backup is truncated: {path.name}'
                        )
                    remaining -= len(block)
                    plain = cipher.decrypt(block)
                    sink.write(plain)
                    digest.update(plain)
                    produced += len(plain)
                tag = stream.read(GCM_TAG_LEN)
            if len(tag) != GCM_TAG_LEN:
                raise BackupVerificationError(f'Encrypted backup tag is truncated: {path.name}')
        try:
            cipher.verify(tag)
        except ValueError as exc:
            raise BackupVerificationError(
                f'Encrypted backup failed authentication (tampered ciphertext or wrong '
                f'key): {path.name}'
            ) from exc
    except BaseException:
        Path(dest).unlink(missing_ok=True)
        raise
    return {'sha256': digest.hexdigest(), 'size': produced, 'header': header}


def _materialise(source: Path, dest: Path, manifest: dict[str, Any], *, key: bytes | None = None) -> None:
    """Write the plaintext database held in ``source`` to ``dest``."""
    if manifest.get('format') == BACKUP_FORMAT_ENCRYPTED:
        resolved = key if key is not None else load_backup_key()
        if resolved is None:
            raise BackupEncryptionError(
                f'Backup {source.name} is encrypted and {BACKUP_KEY_ENV} is not set'
            )
        _unseal(source, dest, resolved)
    else:
        shutil.copyfile(source, dest)


# --------------------------------------------------------------------------- creation


def create_sqlite_backup(
    db_path: os.PathLike | str,
    *,
    backup_dir: os.PathLike | str | None = None,
    kind: str = 'manual',
    from_version: int | None = None,
    to_version: int | None = None,
    encrypt: bool | None = None,
    prune: bool = True,
    retention: RetentionPolicy = RETENTION,
    lock_path: os.PathLike | str | None = None,
) -> dict[str, Any]:
    """Copy a live SQLite database online (WAL-safe), verify it, then prune.

    Uses ``sqlite3.Connection.backup`` rather than ``shutil.copyfile``: a plain file copy
    of a WAL database can miss committed frames. Failure leaves no partial backup file.

    ``encrypt`` -- ``None`` seals the copy when ``LUMINEST_BACKUP_KEY`` is set (or when
    ``LUMINEST_BACKUP_REQUIRE_ENCRYPTION`` demands it), ``True`` seals it and refuses to
    continue without a key, ``False`` writes plaintext on purpose. There is no silent
    downgrade.

    ``prune`` -- apply the retention policy to the backup directory afterwards. A prune
    failure is reported in the manifest rather than thrown, because the backup itself did
    succeed and callers must not treat a housekeeping problem as a lost backup.
    """
    source = Path(db_path).expanduser().resolve()
    if not source.is_file() or source.stat().st_size == 0:
        raise BackupSourceError(f'Refusing to back up an empty or missing database: {source}')
    destination_dir = (
        Path(backup_dir).expanduser().resolve()
        if backup_dir is not None
        else default_backup_dir(source)
    )
    destination_dir.mkdir(parents=True, exist_ok=True)
    key = _resolve_key(encrypt)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    name = f'{stamp}-{kind}-{uuid.uuid4().hex[:8]}.sqlite3'
    final = destination_dir / name
    staging = destination_dir / f'.{name}.tmp'
    sealed = destination_dir / f'.{name}.sealed.tmp'
    artefact = staging

    try:
        try:
            src = _open_readonly(source)
            try:
                row = src.execute('PRAGMA integrity_check').fetchone()
                if not row or row[0] != 'ok':
                    raise BackupSourceError(
                        f'Source database failed integrity_check: {source}'
                    )
                dst = sqlite3.connect(str(staging))
                try:
                    src.backup(dst)
                finally:
                    dst.close()
            finally:
                src.close()
        except BackupBusyError:
            raise
        except sqlite3.OperationalError as exc:
            # mode=ro with timeout=0 surfaces "database is locked" as a bare OperationalError,
            # which the CLI would print as a traceback instead of a sentence.
            if 'locked' in str(exc).lower() or 'busy' in str(exc).lower():
                raise BackupBusyError(
                    f'Live database is locked by another process: {source}'
                ) from exc
            raise BackupError(f'Could not copy the live database {source}: {exc}') from exc
        except sqlite3.Error as exc:
            raise BackupSourceError(
                f'Live database cannot be read ({exc}): {source}'
            ) from exc
        _fsync(staging)
        schema_version = _schema_version(staging, immutable=True)
        fingerprint = schema_fingerprint(staging, immutable=True)
        plaintext_sha256 = _sha256(staging)
        plaintext_size = staging.stat().st_size

        header: dict[str, Any] | None = None
        key_id: str | None = None
        if key is not None:
            sealed_info = _seal(staging, sealed, key, plaintext_sha256)
            staging.unlink(missing_ok=True)
            _drop_sidecars(staging)
            artefact = sealed
            checksum = sealed_info['sha256']
            size = sealed_info['size']
            header = sealed_info['header']
            key_id = sealed_info['key_id']
        else:
            checksum = plaintext_sha256
            size = plaintext_size

        manifest: dict[str, Any] = {
            'format': BACKUP_FORMAT_ENCRYPTED if key is not None else BACKUP_FORMAT,
            'container': CONTAINER_AES_GCM if key is not None else CONTAINER_PLAINTEXT,
            'name': name,
            'path': str(final),
            'sha256': checksum,
            'size': size,
            'plaintext_sha256': plaintext_sha256,
            'plaintext_size': plaintext_size,
            # For an encrypted artefact the timestamp inside the authenticated header is
            # the authority; the sidecar repeats it so a rewritten sidecar can be caught.
            'created_at': header['created_at'] if header else _utc_now(),
            'kind': kind,
            'from_version': from_version,
            'to_version': to_version,
            'schema_version': schema_version,
            'schema_fingerprint': fingerprint,
            'source_database': str(source),
            'key_id': key_id,
            'crypto': header.get('crypto') if header else None,
            'retention_policy': retention.as_dict(),
        }
        os.replace(artefact, final)
        _drop_sidecars(artefact)
        _write_json_atomic(_sidecar_for(final), manifest)
        # Re-read the finished file, not the staging file: detect a truncated swap.
        if _sha256(final) != checksum:
            raise BackupError(f'Backup checksum changed after write: {final}')
        if key is None:
            if not _artefact_integrity_ok(final):
                raise BackupError(f'Backup verification failed after write: {final}')
            _drop_sidecars(final)
        else:
            with tempfile.TemporaryDirectory(prefix='luminest-postwrite-') as scratch:
                probe = Path(scratch) / 'probe.sqlite3'
                _unseal(final, probe, key)
                try:
                    if not _artefact_integrity_ok(probe):
                        raise BackupError(f'Backup verification failed after write: {final}')
                finally:
                    probe.unlink(missing_ok=True)

        if prune:
            try:
                manifest['retention'] = prune_sqlite_backups(
                    destination_dir,
                    lock_path=lock_path if lock_path is not None
                    else default_lock_path(destination_dir),
                    retention=retention,
                )
            except Exception as exc:  # housekeeping must never discard a good backup
                manifest['retention'] = {'error': str(exc), 'backup_dir': str(destination_dir)}
        return manifest
    except Exception:
        staging.unlink(missing_ok=True)
        sealed.unlink(missing_ok=True)
        final.unlink(missing_ok=True)
        _drop_sidecars(staging)
        _drop_sidecars(sealed)
        _drop_sidecars(final)
        _sidecar_for(final).unlink(missing_ok=True)
        raise


# --------------------------------------------------------------------------- verification


def verify_sqlite_backup(
    backup_path: os.PathLike | str, *, key: bytes | None = None
) -> dict[str, Any]:
    """Recompute the SHA-256 and open the backup independently before it can be restored.

    Plaintext and encrypted artefacts are both accepted. A tampered encrypted artefact is
    rejected by the GCM tag, not merely by the sidecar checksum; a legacy plaintext backup
    keeps verifying exactly as it did before encryption existed.

    A snapshot must also be *self-contained*. A non-empty ``-wal`` beside the artefact would
    be applied by this check and dropped by :func:`restore_sqlite_backup` (which copies only
    the main file), so verification and restore would disagree about the same snapshot.
    Such an artefact is refused rather than guessed at.
    """
    path = Path(backup_path).expanduser().resolve()
    if not path.is_file():
        raise BackupVerificationError(f'Backup file does not exist: {path}')
    witness = _stray_wal(path)
    if witness is not None:
        raise BackupVerificationError(
            f'Backup is not self-contained: {witness.name} holds '
            f'{witness.stat().st_size} bytes of frames that were never folded in. '
            f'Treat the copy as damaged; take a new backup of the source database.'
        )
    manifest = _load_manifest(path)
    actual = _sha256(path)
    expected = manifest.get('sha256')
    if not isinstance(expected, str) or not hmac.compare_digest(actual, expected):
        raise BackupVerificationError(
            f'Backup checksum mismatch for {path.name}: manifest={expected} actual={actual}'
        )
    if manifest.get('size') != path.stat().st_size:
        raise BackupVerificationError(f'Backup size mismatch for {path.name}')

    if manifest.get('format') == BACKUP_FORMAT_ENCRYPTED:
        with open(path, 'rb') as stream:
            if stream.read(len(ENCRYPTED_MAGIC)) != ENCRYPTED_MAGIC:
                raise BackupVerificationError(
                    f'Sidecar claims an encrypted container but the file is not one: {path.name}'
                )
        # These two are mandatory for a sealed artefact. An optional field is a field an
        # attacker may delete, and a deleted digest turns the replay check into a check
        # that compares a timestamp the attacker also controls.
        recorded_digest = manifest.get('plaintext_sha256')
        recorded_size = manifest.get('plaintext_size')
        if not isinstance(recorded_digest, str) or len(recorded_digest) != 64:
            raise BackupVerificationError(
                f'Encrypted backup sidecar is missing plaintext_sha256: {path.name}. '
                'Re-create the backup; a sealed artefact cannot be verified without it.'
            )
        if not isinstance(recorded_size, int):
            raise BackupVerificationError(
                f'Encrypted backup sidecar is missing plaintext_size: {path.name}. '
                'Re-create the backup; a sealed artefact cannot be verified without it.'
            )
        if key is None:
            key = load_backup_key()
        if key is None:
            raise BackupEncryptionError(
                f'Backup {path.name} is encrypted and {BACKUP_KEY_ENV} is not set'
            )
        # SQLite can only integrity-check a file it can open, so the plaintext exists for
        # the duration of the check in the system temp directory and nowhere else.
        with tempfile.TemporaryDirectory(prefix='luminest-verify-') as scratch:
            probe = Path(scratch) / 'probe.sqlite3'
            info = _unseal(path, probe, key)
            try:
                header = info.get('header') or {}
                sealed_at = header.get('created_at')
                if sealed_at is not None and sealed_at != manifest.get('created_at'):
                    raise BackupVerificationError(
                        f'Sealed timestamp does not match the sidecar for {path.name}: '
                        f'the artefact or its sidecar was replaced'
                    )
                sealed_digest = header.get('plaintext_sha256')
                if not isinstance(sealed_digest, str) or len(sealed_digest) != 64:
                    raise BackupVerificationError(
                        f'Encrypted backup header carries no plaintext digest: {path.name}. '
                        'It was sealed by an older build; re-create the backup.'
                    )
                # The authenticated header is the authority. The sidecar must agree with
                # it, and the decrypted bytes must match both -- so a rewritten sidecar
                # cannot substitute a different snapshot (replay) or drop the field.
                if not hmac.compare_digest(sealed_digest, recorded_digest):
                    raise BackupVerificationError(
                        f'Sidecar plaintext hash disagrees with the sealed header for '
                        f'{path.name}: the artefact or its sidecar was replaced'
                    )
                if not hmac.compare_digest(sealed_digest, info['sha256']):
                    raise BackupVerificationError(
                        f'Decrypted content does not match the sealed plaintext hash: {path.name}'
                    )
                if recorded_size != info['size']:
                    raise BackupVerificationError(
                        f'Decrypted content does not match the recorded plaintext size: {path.name}'
                    )
                if _sha256_head(probe) != SQLITE_MAGIC:
                    raise BackupVerificationError(f'Decrypted backup is not a database: {path.name}')
                if not _artefact_integrity_ok(probe):
                    raise BackupVerificationError(
                        f'Backup integrity_check failed for {path.name}'
                    )
            finally:
                probe.unlink(missing_ok=True)
        plaintext_sha256 = info['sha256']
    else:
        with open(path, 'rb') as stream:
            if stream.read(len(SQLITE_MAGIC)) != SQLITE_MAGIC:
                raise BackupVerificationError(f'Backup is not a SQLite database: {path.name}')
        # Opened immutable: a WAL-flagged artefact must not sprout -wal/-shm beside itself
        # just because it was verified, and the snapshot must not be re-read as if a live
        # journal could still change it.
        try:
            with _open_readonly(path, immutable=True) as connection:
                row = connection.execute('PRAGMA integrity_check').fetchone()
                if not row or row[0] != 'ok':
                    raise BackupVerificationError(
                        f'Backup integrity_check failed for {path.name}: {row}'
                    )
        except sqlite3.Error as exc:
            raise BackupVerificationError(
                f'Backup cannot be opened for integrity check: {path.name}: {exc}'
            ) from exc
        plaintext_sha256 = actual

    return {
        **manifest,
        'verified': True,
        'resolved_path': str(path),
        'encrypted': manifest.get('format') == BACKUP_FORMAT_ENCRYPTED,
        'container': _container_of(manifest),
        'plaintext_sha256': plaintext_sha256,
    }


def _sha256_head(path: Path) -> bytes:
    with open(path, 'rb') as stream:
        return stream.read(len(SQLITE_MAGIC))


def _integrity_of(path: Path, manifest: dict[str, Any]) -> tuple[bool | None, str | None]:
    """Integrity of an artefact for listings: ``None`` when it cannot be checked."""
    if manifest.get('format') != BACKUP_FORMAT_ENCRYPTED:
        return _artefact_integrity_ok(path), None
    if not isinstance(manifest.get('plaintext_sha256'), str) or not isinstance(
        manifest.get('plaintext_size'), int
    ):
        return False, (
            'sealed sidecar is missing plaintext_sha256/plaintext_size; verification '
            'will refuse it'
        )
    try:
        key = load_backup_key()
    except BackupEncryptionError as exc:
        return None, str(exc)
    if key is None:
        return None, 'encrypted; LUMINEST_BACKUP_KEY is not set so integrity was not checked'
    with tempfile.TemporaryDirectory(prefix='luminest-list-') as scratch:
        probe = Path(scratch) / 'probe.sqlite3'
        try:
            _unseal(path, probe, key)
            return _artefact_integrity_ok(probe), None
        except BackupError as exc:
            return False, str(exc)
        finally:
            probe.unlink(missing_ok=True)


def list_sqlite_backups(backup_dir: os.PathLike | str) -> list[dict[str, Any]]:
    """List backups with their checksum status; a corrupt sidecar is reported, not hidden."""
    directory = Path(backup_dir).expanduser().resolve()
    if not directory.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(directory.glob('*.sqlite3')):
        rows.append(_summarise_backup(path))
    rows.sort(key=lambda item: (item.get('created_at') or '', item['name']))
    return rows


def _summarise_backup(path: Path) -> dict[str, Any]:
    row: dict[str, Any] = {'path': str(path), 'name': path.name}
    try:
        manifest = _load_manifest(path)
        row.update({
            'created_at': manifest.get('created_at'),
            'kind': manifest.get('kind'),
            'size': manifest.get('size'),
            'sha256': manifest.get('sha256'),
            'schema_version': manifest.get('schema_version'),
            'schema_fingerprint': manifest.get('schema_fingerprint'),
            'from_version': manifest.get('from_version'),
            'to_version': manifest.get('to_version'),
            'format': manifest.get('format'),
            'container': _container_of(manifest),
            'encrypted': manifest.get('format') == BACKUP_FORMAT_ENCRYPTED,
            'key_id': manifest.get('key_id'),
        })
        row['checksum_valid'] = hmac.compare_digest(_sha256(path), str(manifest.get('sha256')))
        witness = _stray_wal(path)
        if witness is not None:
            row['self_contained'] = False
            row['integrity_ok'] = False
            row['error'] = (
                f'a {witness.stat().st_size}-byte {witness.name} sits beside the artefact; '
                'it cannot be verified or restored consistently'
            )
            return row
        row['self_contained'] = True
        integrity, note = _integrity_of(path, manifest)
        row['integrity_ok'] = integrity
        if note:
            row['integrity_note'] = note
    except (BackupVerificationError, BackupEncryptionError, KeyError, TypeError, OSError) as exc:
        row.update({'checksum_valid': False, 'integrity_ok': False, 'error': str(exc)})
    return row


# --------------------------------------------------------------------------- retention


def _prune_candidate(path: Path) -> dict[str, Any]:
    """Classify one ``*.sqlite3`` file as a recognised backup or as untouchable.

    Never raises for a per-file problem. One unreadable artefact must not abort the sweep
    and thereby protect every *other* expired file in the directory, so an ``OSError``
    becomes a ``skipped`` record like any other unrecognised file.
    """
    record: dict[str, Any] = {
        'path': str(path),
        'name': path.name,
        'kind': None,
        'created_at': None,
        'from_version': None,
        'schema_fingerprint': None,
        'reason': None,
    }
    if any(sibling.exists() for sibling in _staging_siblings(path)):
        record['reason'] = 'another writer is staging this name'
        return record
    try:
        manifest = _load_manifest(path)
    except BackupVerificationError as exc:
        record['reason'] = f'unrecognised: {exc}'
        return record
    except OSError as exc:
        record['reason'] = f'unreadable: {exc}'
        return record
    created = _parse_utc(manifest.get('created_at'))
    if created is None:
        record['reason'] = 'unrecognised: created_at is missing or unparseable'
        return record
    expected = manifest.get('sha256')
    try:
        actual = _sha256(path)
    except OSError as exc:
        record['reason'] = f'unreadable: {exc}'
        return record
    if not isinstance(expected, str) or not hmac.compare_digest(actual, expected):
        record['reason'] = 'unverifiable: checksum does not match the sidecar'
        return record
    record['kind'] = str(manifest.get('kind') or 'unknown')
    record['created_at'] = created.strftime(TIMESTAMP_FORMAT)
    record['from_version'] = manifest.get('from_version')
    record['schema_fingerprint'] = manifest.get('schema_fingerprint')
    record['_created'] = created
    return record


def prune_sqlite_backups(
    backup_dir: os.PathLike | str,
    *,
    lock_path: os.PathLike | str | None = None,
    retention: RetentionPolicy = RETENTION,
    dry_run: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Delete only the backups the retention policy allows; report everything it touched.

    Guarantees, in order of precedence:

    1. The newest usable backup in the directory is never deleted.
    2. The newest usable backup of every kind is never deleted.
    3. No file that another process is currently staging under the same name is touched:
       a recognised backup is skipped when its staging sibling exists, and staging debris
       itself is only removed once it is ``STAGING_ORPHAN_AGE_HOURS`` (24) old. That is the
       honest form of the guarantee -- liveness cannot be proven portably, so the cutoff is
       named here and in the module docstring rather than implied, and it sits far past any
       plausible write.
    4. A file is only ever deleted when its sidecar parses, its checksum matches and its
       ``created_at`` parses. Anything else -- a hand-placed file, a truncated write, a
       damaged sidecar, a backup whose sidecar has not been written yet -- is reported
       under ``skipped`` and left on disk, because an unverifiable artefact may be the only
       surviving copy of the data. This is also what protects a backup that is still being
       written: the sidecar is written last, so a half-written copy has no sidecar.
    5. Retention only removes copies it recognises as its own; it cannot widen the blast
       radius to arbitrary files.

    What survives is at most ``retention.max_backups`` recognised backups per directory,
    with at most ``retention.max_pre_restore`` of them ``pre-restore`` snapshots.

    ``dry_run`` returns the same decisions without unlinking. ``lock_path`` defaults to
    no locking; callers that own the maintenance lock pass it so the prune cannot race a
    restore. When this process already holds that lock -- create runs inside restore's
    critical section -- the acquisition is skipped rather than colliding with ourselves;
    when another process holds it, :class:`BackupBusyError` is raised and nothing is
    deleted.
    """
    if lock_path is not None and not _lock_held_here(lock_path):
        with maintenance_lock(lock_path):
            return _prune(backup_dir, retention, dry_run, now)
    return _prune(backup_dir, retention, dry_run, now)


def _prune(
    backup_dir: os.PathLike | str,
    retention: RetentionPolicy,
    dry_run: bool,
    now: datetime | None,
) -> dict[str, Any]:
    directory = Path(backup_dir).expanduser().resolve()
    report: dict[str, Any] = {
        'backup_dir': str(directory),
        'policy': {**retention.as_dict(), 'version': RETENTION_POLICY_VERSION},
        'dry_run': bool(dry_run),
        'generated_at': _utc_now(),
        'deleted': [],
        'kept': [],
        'skipped': [],
        'staging_deleted': [],
    }
    if not directory.is_dir():
        return report

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    recognised: list[dict[str, Any]] = []
    for path in sorted(directory.glob('*.sqlite3')):
        record = _prune_candidate(path)
        if record.pop('_created', None) is not None:
            recognised.append(record)
        else:
            report['skipped'].append({
                'path': record['path'], 'name': record['name'], 'reason': record['reason'],
            })

    by_kind: dict[str, list[dict[str, Any]]] = {}
    for record in recognised:
        by_kind.setdefault(record['kind'], []).append(record)
    for group in by_kind.values():
        group.sort(key=lambda item: (item['created_at'], item['name']), reverse=True)

    policies: dict[int, tuple[str, str]] = {}
    protected: set[int] = set()
    newest_overall = max(recognised, key=lambda item: (item['created_at'], item['name']), default=None)
    for kind, group in by_kind.items():
        cap = retention.cap_for(kind)
        for rank, record in enumerate(group):
            created = datetime.strptime(record['created_at'], TIMESTAMP_FORMAT).replace(
                tzinfo=timezone.utc
            )
            age_days = (current - created).total_seconds() / 86400.0
            if record is newest_overall:
                # The last-resort copy: the directory is never emptied by age. It is the
                # only ordinary exemption from the age rule, and it is stated as such.
                policies[id(record)] = ('keep', 'newest usable backup in the directory')
                protected.add(id(record))
            elif age_days > retention.max_age_days:
                # Age is absolute for ordinary copies, including the newest of a kind: a
                # protection from the count cap is not a protection from expiry, or the
                # published "deleted after 30 days" would be false.
                policies[id(record)] = ('delete', f'older than {retention.max_age_days} days')
            elif rank == 0:
                policies[id(record)] = ('keep', f'newest usable {kind} backup')
                protected.add(id(record))
            elif rank >= cap:
                policies[id(record)] = (
                    'delete', f'more than {cap} retained {kind} backups'
                )
            else:
                policies[id(record)] = ('keep', 'within the retention policy')

    # A crashed migration is retried: each attempt stamps the *same* recorded version and
    # writes another `pre-migration` snapshot of a database that is already half-upgraded.
    # The newest snapshot then stops being "before the migration" at all, so the oldest
    # snapshot of each `from_version` is the one worth keeping - protect both ends. An
    # anchor is exempt from the age rule *and* from the count cap, because the upgrade it
    # defends against may be discovered as wrong long after 30 days; the ceiling below is
    # what keeps "indefinite" from meaning "unbounded".
    anchors: list[dict[str, Any]] = []
    oldest_by_version: dict[str, dict[str, Any]] = {}
    for record in recognised:
        if record['kind'] != 'pre-migration' or record['from_version'] is None:
            continue
        key = str(record['from_version'])
        incumbent = oldest_by_version.get(key)
        if incumbent is None or (record['created_at'], record['name']) < (
            incumbent['created_at'], incumbent['name']
        ):
            oldest_by_version[key] = record
    for version in sorted(oldest_by_version, key=lambda key: (
        oldest_by_version[key]['created_at'], oldest_by_version[key]['name'],
    )):
        record = oldest_by_version[version]
        anchors.append(record)
        policies[id(record)] = (
            'keep',
            f'oldest pre-migration snapshot from version {version} (rollback anchor)',
        )
        protected.add(id(record))

    # Indefinite is not unbounded: past the ceiling the oldest anchor goes first, so a
    # machine that keeps upgrading for years does not accumulate one copy per version. The
    # newest usable backup is never the eviction victim: it is the last-resort copy.
    if len(anchors) > retention.max_anchors:
        evictable = [record for record in anchors if record is not newest_overall]
        for record in evictable[:len(anchors) - retention.max_anchors]:
            policies[id(record)] = (
                'delete',
                f'more than {retention.max_anchors} rollback anchors retained '
                f'(oldest anchor evicted first)',
            )
            protected.discard(id(record))

    # The per-kind caps are not enough on their own: 10 upgrade copies plus 3 pre-restore
    # snapshots would be 13 complete copies of the learner database. The total is enforced
    # over *ordinary* backups only; anchors are the +4 that make the published worst case
    # RETENTION_MAX_BACKUPS + RETENTION_MAX_ANCHORS.
    anchor_ids = {id(record) for record in anchors}
    survivors = [
        record for record in recognised
        if policies[id(record)][0] == 'keep' and id(record) not in anchor_ids
    ]
    excess = len(survivors) - retention.max_backups
    if excess > 0:
        removable = sorted(
            (record for record in survivors if id(record) not in protected),
            key=lambda item: (item['created_at'], item['name']),
        )
        for record in removable[:excess]:
            policies[id(record)] = (
                'delete',
                f'more than {retention.max_backups} backups retained in this directory',
            )

    ordered = sorted(recognised, key=lambda item: (item['created_at'], item['name']))
    for record in ordered:
        action, reason = policies[id(record)]
        entry = {
            'path': record['path'],
            'name': record['name'],
            'kind': record['kind'],
            'created_at': record['created_at'],
            'from_version': record['from_version'],
            'schema_fingerprint': record['schema_fingerprint'],
            'reason': reason,
        }
        if action == 'delete':
            if not dry_run:
                try:
                    Path(record['path']).unlink()
                except OSError as exc:
                    entry['reason'] = f'{reason}, but unlink failed: {exc}'
                    report['skipped'].append(entry)
                    continue
                _sidecar_for(Path(record['path'])).unlink(missing_ok=True)
            report['deleted'].append(entry)
        else:
            report['kept'].append(entry)

    report['staging_deleted'] = _sweep_staging_debris(directory, current, dry_run)
    return report


def _sweep_staging_debris(
    directory: Path, current: datetime, dry_run: bool
) -> list[dict[str, Any]]:
    """Remove staging leftovers of interrupted writes; never a live writer's file.

    These are names this module itself creates (``.<name>.sqlite3.tmp`` and its SQLite
    siblings, plus the sealed staging file). They are invisible to
    :func:`list_sqlite_backups` and would otherwise accumulate forever, but a *live* write
    also looks like them, so the only safe discriminator is age.
    """
    cutoff = current - timedelta(hours=STAGING_ORPHAN_AGE_HOURS)
    removed: list[dict[str, Any]] = []
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        name = path.name
        if not name.startswith('.') or '.sqlite3' not in name:
            continue
        if not (
            name.endswith('.tmp')
            or name.endswith(('.tmp-wal', '.tmp-shm', '.tmp-journal'))
        ):
            continue
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        if modified > cutoff:
            continue
        if not dry_run:
            try:
                path.unlink()
            except OSError:
                continue
        removed.append({
            'path': str(path),
            'name': name,
            'reason': f'staging debris older than {STAGING_ORPHAN_AGE_HOURS} hours',
        })
    return removed


# --------------------------------------------------------------------------- restore


def _checkpoint_and_check_idle(db_path: Path) -> None:
    """Fold WAL frames into the main file; refuse if another connection is busy.

    A file whose header is unusable raises ``sqlite3.DatabaseError`` rather than
    ``OperationalError``; that is not "busy", it is "this is not a database", and the caller
    decides what to do with it (see :func:`restore_sqlite_backup`, which parks it as
    evidence instead of refusing to recover).
    """
    connection = sqlite3.connect(str(db_path), timeout=0, isolation_level=None)
    try:
        connection.execute('PRAGMA busy_timeout=0')
        try:
            connection.execute('BEGIN IMMEDIATE')
        except sqlite3.OperationalError as exc:
            raise BackupBusyError(
                f'Live database is locked by another process: {db_path}'
            ) from exc
        connection.execute('ROLLBACK')
        result = connection.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
        if result and result[0] != 0:
            raise BackupBusyError(
                f'WAL checkpoint could not complete (busy={result[0]}): {db_path}'
            )
    finally:
        connection.close()


def _has_sqlite_header(path: Path) -> bool:
    try:
        with open(path, 'rb') as stream:
            return stream.read(len(SQLITE_MAGIC)) == SQLITE_MAGIC
    except OSError:
        return False


def restore_sqlite_backup(
    backup_path: os.PathLike | str,
    db_path: os.PathLike | str,
    *,
    backup_dir: os.PathLike | str | None = None,
    lock_path: os.PathLike | str | None = None,
    key: bytes | None = None,
) -> dict[str, Any]:
    """Restore a verified backup atomically, with a pre-restore recovery snapshot.

    Rejects invalid checksums, damaged artefacts, tampered ciphertext and databases held by
    another process. A failed replacement rolls the recovery snapshot back in so the
    active database is never left unusable.

    A live database that cannot be used as a recovery source -- empty, no SQLite header, or
    failing ``integrity_check`` -- is *not* a reason to refuse the restore: it is moved to
    ``<backup_dir>/<name>.damaged.pre-restore-<token>`` as evidence and replaced. The
    receipt names the parked copy. A busy database is still refused
    (:class:`BackupBusyError`), because that is a live process, not damage.

    The restored database is byte-identical to the plaintext the verified artefact held:
    a snapshot restores exactly what it contained at the moment it was taken, and nothing
    that changed afterwards.
    """
    verified = verify_sqlite_backup(backup_path, key=key)
    source_backup = Path(verified['resolved_path'])
    target = Path(db_path).expanduser().resolve()
    if not target.parent.is_dir():
        raise BackupError(f'Target directory does not exist: {target.parent}')
    snapshot_dir = (
        Path(backup_dir).expanduser().resolve()
        if backup_dir is not None
        else default_backup_dir(target)
    )
    lock = Path(lock_path).expanduser().resolve() if lock_path else (
        target.parent / MAINTENANCE_LOCK_NAME
    )
    token = uuid.uuid4().hex[:8]
    replacement = target.with_name(f'.{target.name}.restore-{token}.tmp')
    stashed: list[tuple[Path, Path]] = []
    swapped = False
    damaged: Path | None = None

    with maintenance_lock(lock):
        # A *missing* database restores fine, and a *corrupt* one is the state a restore
        # exists to fix. Refusing the second while allowing the first would make recovery
        # hard exactly when it matters, so a file we cannot use as a recovery source is
        # parked as evidence and replaced.
        def _park_unusable() -> Path | None:
            nonlocal damaged
            if not target.is_file() or damaged is not None:
                return damaged
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            damaged = snapshot_dir / f'{target.name}.damaged.pre-restore-{token}'
            os.replace(target, damaged)
            return damaged

        usable = target.is_file() and target.stat().st_size > 0 and _has_sqlite_header(target)
        if usable:
            try:
                _checkpoint_and_check_idle(target)
            except BackupBusyError:
                raise
            except sqlite3.DatabaseError:
                usable = False
        if target.is_file() and not usable:
            _park_unusable()
        recovery = None
        if usable:
            try:
                recovery = create_sqlite_backup(
                    target, backup_dir=snapshot_dir, kind=PRE_RESTORE_KIND, lock_path=lock,
                )
            except BackupSourceError:
                # Looked like a database, is not usable as a rollback source: keep it as
                # evidence and restore over it. Any other backup error still propagates,
                # because it says nothing about the live file's health.
                _park_unusable()
        try:
            _materialise(source_backup, replacement, verified, key=key)
            _fsync(replacement)
            if _sha256(replacement) != verified['plaintext_sha256'] or not _artefact_integrity_ok(replacement):
                raise BackupError('Staged restore copy failed verification')

            # Stale -wal/-shm frames belong to the *old* database and must not be applied
            # to the restored file. They are moved aside (kept as evidence), never deleted.
            for suffix in ('-wal', '-shm'):
                sidecar = Path(str(target) + suffix)
                if sidecar.exists():
                    parked = snapshot_dir / f'{target.name}.{suffix.lstrip("-")}.pre-restore-{token}'
                    snapshot_dir.mkdir(parents=True, exist_ok=True)
                    os.replace(sidecar, parked)
                    stashed.append((sidecar, parked))

            os.replace(replacement, target)
            swapped = True
            if not _integrity_ok(target):
                raise BackupError('Restored database failed integrity_check')
            _drop_sidecars(target)
        except Exception as exc:
            for original, parked in reversed(stashed):
                if parked.exists() and not original.exists():
                    os.replace(parked, original)
            if swapped and recovery is not None:
                snapshot = Path(recovery['path'])
                rollback = target.with_name(f'.{target.name}.rollback-{token}.tmp')
                try:
                    _materialise(snapshot, rollback, recovery, key=key)
                    _fsync(rollback)
                    os.replace(rollback, target)
                finally:
                    rollback.unlink(missing_ok=True)
                    _drop_sidecars(rollback)
                if not _integrity_ok(target):
                    raise BackupError(
                        'Restore failed AND recovery snapshot rollback failed; '
                        f'manual recovery required from {snapshot}'
                    ) from exc
                raise BackupError(
                    f'Restore failed and the pre-restore snapshot was rolled back: {exc}'
                ) from exc
            if damaged is not None and damaged.exists():
                os.replace(damaged, target)
                raise BackupError(
                    'Restore failed; the damaged live database was put back unchanged at '
                    f'{target} (a copy is kept at {damaged}). Fix the backup and retry: {exc}'
                ) from exc
            if swapped:
                raise BackupError(f'Restore failed: {exc}') from exc
            raise
        finally:
            replacement.unlink(missing_ok=True)
            _drop_sidecars(replacement)

    return {
        'restored_from': str(source_backup),
        'database': str(target),
        'sha256': verified['sha256'],
        'plaintext_sha256': verified['plaintext_sha256'],
        'encrypted': verified['encrypted'],
        'recovery_snapshot': recovery['path'] if recovery else None,
        'damaged_live_file_parked': str(damaged) if damaged else None,
        'backup_dir': str(snapshot_dir),
        'wal_sidecars_parked': [str(parked) for _, parked in stashed],
        'status': 'restored',
    }


# --------------------------------------------------------------------------- CLI


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Luminest SQLite backup maintenance')
    sub = parser.add_subparsers(dest='command', required=True)
    p_create = sub.add_parser('create')
    p_create.add_argument('--database', required=True)
    p_create.add_argument('--dir')
    p_create.add_argument('--kind', default='manual')
    group = p_create.add_mutually_exclusive_group()
    group.add_argument(
        '--encrypt', dest='encrypt', action='store_true', default=None,
        help='seal the backup with LUMINEST_BACKUP_KEY, failing when it is unset',
    )
    group.add_argument(
        '--no-encrypt', dest='encrypt', action='store_false',
        help='write a plaintext backup on purpose',
    )
    p_list = sub.add_parser('list')
    p_list.add_argument('--dir', required=True)
    p_verify = sub.add_parser('verify')
    p_verify.add_argument('--backup', required=True)
    p_restore = sub.add_parser('restore')
    p_restore.add_argument('--backup', required=True)
    p_restore.add_argument('--database', required=True)
    p_restore.add_argument('--dir')
    p_prune = sub.add_parser(
        'prune', help='delete the backups the retention policy allows, and nothing else'
    )
    p_prune.add_argument('--dir', required=True)
    p_prune.add_argument('--lock')
    p_prune.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'create':
            payload: Any = create_sqlite_backup(
                args.database, backup_dir=args.dir, kind=args.kind, encrypt=args.encrypt
            )
        elif args.command == 'list':
            payload = list_sqlite_backups(args.dir)
        elif args.command == 'verify':
            payload = verify_sqlite_backup(args.backup)
        elif args.command == 'prune':
            payload = prune_sqlite_backups(
                args.dir,
                lock_path=args.lock if args.lock else default_lock_path(Path(args.dir)),
                dry_run=args.dry_run,
            )
        else:
            payload = restore_sqlite_backup(
                args.backup, args.database, backup_dir=args.dir
            )
    except BackupError as exc:
        parser.exit(1, f'ERROR: {exc}\n')
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(_main())
