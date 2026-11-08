#!/usr/bin/env python3
"""Operator drill: prove the backup you hold actually restores.

A backup that has never been restored is a hypothesis. This script turns it into a
measurement, without touching the database it is pointed at:

1. take an online, WAL-safe copy of the live database into a scratch directory;
2. restore that copy into an empty target and compare it table by table against the
   source (row counts and a content digest per table);
3. physically corrupt the scratch target, restore again, and compare again;
4. hold ``BEGIN EXCLUSIVE`` on the scratch target and confirm restore refuses in
   bounded time instead of hanging, and leaves the file untouched.

Everything runs on copies under ``tempfile.mkdtemp()``; the directory is removed unless
``--keep`` is passed. Exit code is 0 only if every step passed.

    python scripts/backup_drill.py --database "<data dir>/harness.sqlite3"
    python scripts/backup_drill.py --backup backups/20260101T...Z-manual-....sqlite3 \
        --database "<data dir>/harness.sqlite3"     # rehearse a *specific* snapshot
    python scripts/backup_drill.py --database ... --keep --json

``--backup`` is the snapshot under test; ``--database`` is only read (copied) so the
drill can compare against the live rows. Omit ``--database`` to drill a snapshot on its
own - then only steps 2-4 run, and step 2's comparison is against the snapshot itself.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database_backup import (  # noqa: E402 - after the sys.path fix-up
    BackupBusyError,
    BackupError,
    create_sqlite_backup,
    restore_sqlite_backup,
    verify_sqlite_backup,
)

#: A restore that has not finished by now is not "slow", it is waiting on a lock.
BOUNDED_SECONDS = 10.0


def _tables(connection: sqlite3.Connection) -> list[str]:
    return [
        row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name")
    ]


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def digest(path: Path) -> dict[str, dict]:
    """Row count plus a content digest per table, so "restored" can be checked.

    Read-only and lock-free: the drill must never disturb the database it inspects.
    """
    with sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro', uri=True, timeout=0) as db:
        result: dict[str, dict] = {}
        for table in _tables(db):
            rows = db.execute(f'SELECT * FROM {_quote(table)}').fetchall()
            body = repr(sorted((list(row) for row in rows), key=repr)).encode('utf-8')
            result[table] = {
                'rows': len(rows),
                'sha256': hashlib.sha256(body).hexdigest()[:16],
            }
        version = db.execute(
            'SELECT version FROM schema_version WHERE id = 1').fetchone()
        result['__schema_version__'] = {'rows': 1, 'sha256': str(version[0] if version else None)}
        return result


def _compare(expected: dict[str, dict], actual: dict[str, dict]) -> list[str]:
    problems = []
    for table in sorted(set(expected) | set(actual)):
        want, got = expected.get(table), actual.get(table)
        if want is None:
            problems.append(f'{table}: present after restore but absent before')
        elif got is None:
            problems.append(f'{table}: LOST by the restore')
        elif want != got:
            problems.append(
                f'{table}: {got["rows"]} rows / {got["sha256"]} after restore, '
                f'expected {want["rows"]} rows / {want["sha256"]}')
    return problems


class Drill:
    def __init__(self, database: Path | None, backup: Path | None, scratch: Path) -> None:
        self.database = database
        self.backup = backup
        self.scratch = scratch
        self.steps: list[dict] = []

    def record(self, name: str, ok: bool, detail: str) -> None:
        self.steps.append({'step': name, 'ok': ok, 'detail': detail})

    # -- steps ---------------------------------------------------------------

    def take_snapshot(self) -> Path:
        assert self.database is not None
        manifest = create_sqlite_backup(
            self.database, backup_dir=self.scratch / 'seed', kind='drill-seed')
        verified = verify_sqlite_backup(manifest['path'])
        self.record('snapshot', True,
                    f"{manifest['size']} bytes, sha256 {manifest['sha256'][:16]}, "
                    f"schema version {manifest['schema_version']}")
        return Path(verified['resolved_path'])

    def restore_into_empty_target(self, snapshot: Path) -> Path:
        target = self.scratch / 'restored.sqlite3'
        receipt = restore_sqlite_backup(snapshot, target)
        staging = sorted(
            path.name for path in self.scratch.iterdir()
            if path.name.startswith(f'.{target.name}') and path.name.endswith('.tmp'))
        orphans = sorted(
            path.name for path in self.scratch.iterdir()
            if path.name.startswith(f'.{target.name}') and path.name.endswith(('-wal', '-shm'))
            and path.stat().st_size > 0)
        ok = receipt['status'] == 'restored' and not staging
        self.record('restore-into-empty-target', ok,
                    f"status={receipt['status']} staging_leftovers={staging} "
                    f"orphan_sidecars={orphans}")
        return target

    def compare_with_source(self, target: Path) -> None:
        source = self.database if self.database is not None else self.backup
        assert source is not None
        expected, actual = digest(source), digest(target)
        problems = _compare(expected, actual)
        self.record('compare-row-for-row', not problems,
                    'identical' if not problems else '; '.join(problems[:8]))

    def restore_over_corrupted_target(self, snapshot: Path, target: Path) -> None:
        garbage = b'corrupted by backup_drill.py\n' * 64
        with open(target, 'wb') as stream:
            stream.write(garbage)
        try:
            receipt = restore_sqlite_backup(snapshot, target)
        except Exception as exc:  # noqa: BLE001 - the type is the finding
            # Refusing is a *safe* outcome (nothing is half-written); it is only
            # unhelpful, because the operator must move the corrupt file aside by hand.
            untouched = target.read_bytes() == garbage
            self.record(
                'restore-over-corrupt-file', untouched,
                f'refused with {type(exc).__name__} and the file was left untouched='
                f'{untouched}; the snapshot itself is fine. To recover, move the corrupt '
                f'file aside and restore into its place.')
            return
        source = self.database if self.database is not None else self.backup
        problems = _compare(digest(source), digest(target)) if source else []
        detail = 'restored a corrupt database' if not problems else '; '.join(problems[:8])
        parked = receipt.get('damaged_live_file_parked')
        if parked:
            detail += f'; the damaged file was kept as evidence at {parked}'
        self.record('restore-over-corrupt-file', not problems, detail)

    def restore_under_exclusive_lock(self, snapshot: Path, target: Path) -> None:
        # The target must be a valid database for this step to mean anything: a lock on a
        # corrupt file fails for a different reason and would be recorded as the wrong
        # finding.
        restore_sqlite_backup(snapshot, target)
        before = hashlib.sha256(target.read_bytes()).hexdigest()
        holder = sqlite3.connect(str(target), isolation_level=None, timeout=0)
        locked = False
        try:
            holder.execute('BEGIN EXCLUSIVE')
            locked = True
            started = time.monotonic()
            try:
                restore_sqlite_backup(snapshot, target)
            except BackupBusyError as exc:
                elapsed = time.monotonic() - started
                untouched = hashlib.sha256(target.read_bytes()).hexdigest() == before
                self.record('restore-under-exclusive-lock',
                            elapsed < BOUNDED_SECONDS and untouched,
                            f'refused in {elapsed:.3f}s, live file untouched={untouched}: {exc}')
            except Exception as exc:  # noqa: BLE001
                elapsed = time.monotonic() - started
                self.record('restore-under-exclusive-lock',
                            isinstance(exc, BackupError) and elapsed < BOUNDED_SECONDS,
                            f'{type(exc).__name__} after {elapsed:.3f}s: {exc}')
            else:
                elapsed = time.monotonic() - started
                self.record('restore-under-exclusive-lock', elapsed < BOUNDED_SECONDS,
                            f'restore COMPLETED in {elapsed:.3f}s while a writer held the lock')
        finally:
            if locked:
                try:
                    holder.execute('ROLLBACK')
                except sqlite3.Error:
                    pass
            holder.close()

    # -- driver --------------------------------------------------------------

    def run(self) -> bool:
        try:
            snapshot = self.backup or self.take_snapshot()
            verified = verify_sqlite_backup(snapshot)
            self.record('verify-snapshot', True,
                        f'{verified["resolved_path"]} (schema {verified["schema_version"]})')
            target = self.restore_into_empty_target(snapshot)
            self.compare_with_source(target)
            self.restore_under_exclusive_lock(snapshot, target)
            self.restore_over_corrupted_target(snapshot, target)
        except (BackupError, OSError, sqlite3.Error) as exc:
            self.record('drill', False, f'{type(exc).__name__}: {exc}')
        return all(step['ok'] for step in self.steps)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Prove a SQLite backup restores (drill)')
    parser.add_argument('--database', help='live database to copy and compare against')
    parser.add_argument('--backup', help='an existing snapshot to drill instead')
    parser.add_argument('--keep', action='store_true', help='keep the scratch directory')
    parser.add_argument('--json', action='store_true', help='machine-readable output')
    args = parser.parse_args(argv)

    if not args.database and not args.backup:
        parser.error('pass --database and/or --backup')
    database = Path(args.database).expanduser().resolve() if args.database else None
    backup = Path(args.backup).expanduser().resolve() if args.backup else None
    if database is not None and not database.is_file():
        parser.exit(2, f'ERROR: no such database: {database}\n')
    if backup is not None and not backup.is_file():
        parser.exit(2, f'ERROR: no such backup: {backup}\n')

    scratch = Path(tempfile.mkdtemp(prefix='luminest-backup-drill-'))
    drill = Drill(database, backup, scratch)
    try:
        ok = drill.run()
    finally:
        if args.keep:
            kept = str(scratch)
        else:
            shutil.rmtree(scratch, ignore_errors=True)
            kept = None

    payload = {'ok': ok, 'scratch': kept, 'steps': drill.steps}
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for step in drill.steps:
            print(f'[{"PASS" if step["ok"] else "FAIL"}] {step["step"]}: {step["detail"]}')
        print(f'\nresult: {"PASS" if ok else "FAIL"}'
              + (f' (scratch kept at {kept})' if kept else ''))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
