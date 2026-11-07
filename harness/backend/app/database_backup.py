"""SQLite backup / restore for the desktop learning harness.

The desktop install keeps one learner database at ``<data_dir>/harness.sqlite3``.
Upgrades are additive but not reversible, so ``scripts/init_db.initialize()`` takes an
online, WAL-safe copy *before* the first DDL statement and refuses to migrate if that
copy cannot be created and verified.

The public surface is deliberately small and dependency-free (stdlib only), so it works
inside the PyInstaller frozen backend and from a pinned virtualenv alike:

    create_sqlite_backup(db_path, ...)   -> manifest dict
    list_sqlite_backups(backup_dir)      -> [manifest dict]
    verify_sqlite_backup(backup_path)    -> verified manifest dict
    restore_sqlite_backup(backup, db)    -> restore receipt dict
    maintenance_lock(lock_path)          -> exclusive, non-blocking context manager
    sqlite_path_from_engine(engine)      -> resolved Path, or None for PostgreSQL/memory

A backup is a plain ``.sqlite3`` file plus a ``.json`` sidecar holding its SHA-256,
size, UTC timestamp, kind and schema versions. Verification recomputes the checksum and
opens the copy independently with ``PRAGMA integrity_check``; a mismatch or a damaged
file is rejected before anything is replaced.

Restore is guarded by an exclusive, non-blocking lock, folds the live WAL into the main
file, writes a ``pre-restore`` recovery snapshot, and swaps the verified copy in with a
single ``os.replace``. Any failure after the swap rolls the recovery snapshot back in.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import hmac
import json
import os
import shutil
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

BACKUP_FORMAT = 1
BACKUP_DIR_NAME = 'backups'
MAINTENANCE_LOCK_NAME = '.luminest-maintenance.lock'


class BackupError(RuntimeError):
    """A backup/restore operation could not be completed safely."""


class BackupVerificationError(BackupError):
    """A backup failed checksum or integrity verification and must not be restored."""


class BackupBusyError(BackupError):
    """Another process holds the maintenance lock or the live database."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _fsync(path: Path) -> None:
    with open(path, 'rb') as stream:
        os.fsync(stream.fileno())


def _sidecar_for(backup_path: Path) -> Path:
    return backup_path.with_suffix('.json')


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
    if payload.get('format') != BACKUP_FORMAT:
        raise BackupVerificationError(f'Unsupported backup format in {sidecar}')
    return payload


def _open_readonly(path: Path) -> sqlite3.Connection:
    # ``as_uri`` keeps spaces and non-ASCII characters in the resolved path intact.
    return sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro', uri=True, timeout=0)


def _integrity_ok(path: Path) -> bool:
    try:
        with _open_readonly(path) as connection:
            row = connection.execute('PRAGMA integrity_check').fetchone()
            return bool(row) and row[0] == 'ok'
    except sqlite3.Error:
        return False


def _schema_version(path: Path) -> int | None:
    try:
        with _open_readonly(path) as connection:
            row = connection.execute(
                'SELECT version FROM schema_version WHERE id = 1'
            ).fetchone()
            return int(row[0]) if row else None
    except sqlite3.Error:
        return None


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


@contextmanager
def maintenance_lock(lock_path: Path) -> Iterator[Path]:
    """Hold an exclusive, non-blocking lock; never wait on or disturb another process."""
    path = Path(lock_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, 'a+b')
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise BackupBusyError(
                f'Another maintenance operation holds {path}; restore refused.'
            ) from exc
        yield path
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def create_sqlite_backup(
    db_path: os.PathLike | str,
    *,
    backup_dir: os.PathLike | str | None = None,
    kind: str = 'manual',
    from_version: int | None = None,
    to_version: int | None = None,
) -> dict[str, Any]:
    """Copy a live SQLite database online (WAL-safe) and verify the copy.

    Uses ``sqlite3.Connection.backup`` rather than ``shutil.copyfile``: a plain file copy
    of a WAL database can miss committed frames. Failure leaves no partial backup file.
    """
    source = Path(db_path).expanduser().resolve()
    if not source.is_file() or source.stat().st_size == 0:
        raise BackupError(f'Refusing to back up an empty or missing database: {source}')
    destination_dir = (
        Path(backup_dir).expanduser().resolve()
        if backup_dir is not None
        else default_backup_dir(source)
    )
    destination_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    name = f'{stamp}-{kind}-{uuid.uuid4().hex[:8]}.sqlite3'
    final = destination_dir / name
    staging = destination_dir / f'.{name}.tmp'

    try:
        src = _open_readonly(source)
        try:
            row = src.execute('PRAGMA integrity_check').fetchone()
            if not row or row[0] != 'ok':
                raise BackupError(f'Source database failed integrity_check: {source}')
            dst = sqlite3.connect(str(staging))
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        _fsync(staging)
        checksum = _sha256(staging)
        manifest: dict[str, Any] = {
            'format': BACKUP_FORMAT,
            'name': name,
            'path': str(final),
            'sha256': checksum,
            'size': staging.stat().st_size,
            'created_at': _utc_now(),
            'kind': kind,
            'from_version': from_version,
            'to_version': to_version,
            'schema_version': _schema_version(staging),
            'source_database': str(source),
        }
        os.replace(staging, final)
        _write_json_atomic(_sidecar_for(final), manifest)
        # Re-read the finished file, not the staging file: detect a truncated swap.
        if _sha256(final) != checksum or not _integrity_ok(final):
            raise BackupError(f'Backup verification failed after write: {final}')
        return manifest
    except Exception:
        staging.unlink(missing_ok=True)
        final.unlink(missing_ok=True)
        _sidecar_for(final).unlink(missing_ok=True)
        raise


def verify_sqlite_backup(backup_path: os.PathLike | str) -> dict[str, Any]:
    """Recompute the SHA-256 and open the backup independently before it can be restored."""
    path = Path(backup_path).expanduser().resolve()
    if not path.is_file():
        raise BackupVerificationError(f'Backup file does not exist: {path}')
    manifest = _load_manifest(path)
    actual = _sha256(path)
    expected = manifest.get('sha256')
    if not isinstance(expected, str) or not hmac.compare_digest(actual, expected):
        raise BackupVerificationError(
            f'Backup checksum mismatch for {path.name}: manifest={expected} actual={actual}'
        )
    if manifest.get('size') != path.stat().st_size:
        raise BackupVerificationError(f'Backup size mismatch for {path.name}')
    with open(path, 'rb') as stream:
        if stream.read(16) != b'SQLite format 3\x00':
            raise BackupVerificationError(f'Backup is not a SQLite database: {path.name}')
    try:
        with _open_readonly(path) as connection:
            row = connection.execute('PRAGMA integrity_check').fetchone()
            if not row or row[0] != 'ok':
                raise BackupVerificationError(
                    f'Backup integrity_check failed for {path.name}: {row}'
                )
    except sqlite3.Error as exc:
        raise BackupVerificationError(
            f'Backup cannot be opened for integrity check: {path.name}: {exc}'
        ) from exc
    return {**manifest, 'verified': True, 'resolved_path': str(path)}


def list_sqlite_backups(backup_dir: os.PathLike | str) -> list[dict[str, Any]]:
    """List backups with their checksum status; a corrupt sidecar is reported, not hidden."""
    directory = Path(backup_dir).expanduser().resolve()
    if not directory.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(directory.glob('*.sqlite3')):
        row: dict[str, Any] = {'path': str(path), 'name': path.name}
        try:
            manifest = _load_manifest(path)
            row.update({
                'created_at': manifest.get('created_at'),
                'kind': manifest.get('kind'),
                'size': manifest.get('size'),
                'sha256': manifest.get('sha256'),
                'schema_version': manifest.get('schema_version'),
            })
            row['checksum_valid'] = hmac.compare_digest(_sha256(path), manifest['sha256'])
            row['integrity_ok'] = _integrity_ok(path)
        except (BackupVerificationError, KeyError, TypeError, OSError) as exc:
            row.update({'checksum_valid': False, 'integrity_ok': False, 'error': str(exc)})
        rows.append(row)
    rows.sort(key=lambda item: (item.get('created_at') or '', item['name']))
    return rows


def _checkpoint_and_check_idle(db_path: Path) -> None:
    """Fold WAL frames into the main file; refuse if another connection is busy."""
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


def restore_sqlite_backup(
    backup_path: os.PathLike | str,
    db_path: os.PathLike | str,
    *,
    backup_dir: os.PathLike | str | None = None,
    lock_path: os.PathLike | str | None = None,
) -> dict[str, Any]:
    """Restore a verified backup atomically, with a pre-restore recovery snapshot.

    Rejects invalid checksums, damaged files and databases held by another process.
    A failed replacement rolls the recovery snapshot back in so the active database is
    never left unusable.
    """
    verified = verify_sqlite_backup(backup_path)
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

    with maintenance_lock(lock):
        if target.is_file():
            _checkpoint_and_check_idle(target)
        recovery = create_sqlite_backup(
            target, backup_dir=snapshot_dir, kind='pre-restore'
        ) if target.is_file() else None
        try:
            shutil.copyfile(source_backup, replacement)
            _fsync(replacement)
            if _sha256(replacement) != verified['sha256'] or not _integrity_ok(replacement):
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
        except Exception as exc:
            for original, parked in reversed(stashed):
                if parked.exists() and not original.exists():
                    os.replace(parked, original)
            if swapped:
                if recovery is not None:
                    snapshot = Path(recovery['path'])
                    rollback = target.with_name(f'.{target.name}.rollback-{token}.tmp')
                    try:
                        shutil.copyfile(snapshot, rollback)
                        _fsync(rollback)
                        os.replace(rollback, target)
                    finally:
                        rollback.unlink(missing_ok=True)
                    if not _integrity_ok(target):
                        raise BackupError(
                            'Restore failed AND recovery snapshot rollback failed; '
                            f'manual recovery required from {snapshot}'
                        ) from exc
                raise BackupError(
                    f'Restore failed and the pre-restore snapshot was rolled back: {exc}'
                ) from exc
            raise
        finally:
            replacement.unlink(missing_ok=True)

    return {
        'restored_from': str(source_backup),
        'database': str(target),
        'sha256': verified['sha256'],
        'recovery_snapshot': recovery['path'] if recovery else None,
        'backup_dir': str(snapshot_dir),
        'wal_sidecars_parked': [str(parked) for _, parked in stashed],
        'status': 'restored',
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Luminest SQLite backup maintenance')
    sub = parser.add_subparsers(dest='command', required=True)
    p_create = sub.add_parser('create')
    p_create.add_argument('--database', required=True)
    p_create.add_argument('--dir')
    p_create.add_argument('--kind', default='manual')
    p_list = sub.add_parser('list')
    p_list.add_argument('--dir', required=True)
    p_verify = sub.add_parser('verify')
    p_verify.add_argument('--backup', required=True)
    p_restore = sub.add_parser('restore')
    p_restore.add_argument('--backup', required=True)
    p_restore.add_argument('--database', required=True)
    p_restore.add_argument('--dir')
    args = parser.parse_args(argv)
    try:
        if args.command == 'create':
            payload: Any = create_sqlite_backup(
                args.database, backup_dir=args.dir, kind=args.kind
            )
        elif args.command == 'list':
            payload = list_sqlite_backups(args.dir)
        elif args.command == 'verify':
            payload = verify_sqlite_backup(args.backup)
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
