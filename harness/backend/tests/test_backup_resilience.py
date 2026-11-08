"""Backup/restore under the conditions that actually break it.

Four scenarios, each run against a *real* learner database built by the production
migration path (see ``tests/fixtures/build_snapshot.py``) rather than a toy table:

1. **Real snapshot restore.** WAL-dirty live database, non-ASCII content, foreign-key
   chains, a dropped table and forged rows. Restore must return every table, column,
   index and FK byte-for-byte, with schema version and foreign-key enforcement intact
   and no stale ``-wal`` frames left to replay over the restored file.
2. **Interrupted migration.** A ``SIGKILL`` (not an injected exception: the process is
   genuinely killed) lands between ``ALTER TABLE users`` and ``ALTER TABLE tokens``
   while ``scripts/init_db.py`` migrates an older database. The pre-migration snapshot
   must restore the *pre-migration* schema and data, not a half-migrated hybrid.
3. **Storage full.** A real APFS image with no room, and a real ``RLIMIT_FSIZE`` write
   ceiling. The dangerous failure is not "backup refused": it is a truncated file that
   a later ``verify_sqlite_backup`` accepts. Both mechanisms are asserted against that.
4. **Locked database.** Another connection holds ``BEGIN EXCLUSIVE``. WAL readers are
   supposed to proceed, so create must succeed with a *consistent* copy that excludes
   the uncommitted row; restore must refuse in bounded time, and neither may corrupt or
   silently half-write the live file. The rollback-journal path (``journal_mode=DELETE``)
   is checked too, because there the reader is blocked rather than isolated.

Nothing here touches a real learner data directory: every database, image and mount
lives under ``tmp_path`` and is removed with it.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from app.database_backup import (
    BACKUP_FORMAT,
    BackupBusyError,
    BackupEncryptionError,
    BackupError,
    create_sqlite_backup,
    list_sqlite_backups,
    restore_sqlite_backup,
    verify_sqlite_backup,
)
from app.db import SCHEMA_VERSION
from fixtures.build_snapshot import (
    BACKEND_ROOT,
    app_like_engine,
    build_snapshot,
    create_schema,
    fingerprint,
    populate,
    sha256,
    sidecar_paths,
)

#: Generous per-operation ceiling. The measured times are 0.02-0.15s; anything near
#: this bound means the call waited on a lock instead of failing fast, which is the
#: defect this file exists to catch (``pytest.ini``'s 300s global timeout would hide it).
BOUNDED_SECONDS = 5.0


@pytest.fixture(autouse=True)
def no_backup_encryption(monkeypatch):
    """Keep the drill hermetic, and keep the disk-full tests about storage.

    A machine with ``LUMINEST_BACKUP_KEY`` exported would seal every artefact (format 2),
    and these tests inspect the bytes of the backup they just wrote. Clearing the
    variables also means a failure under ``RLIMIT_FSIZE``/ENOSPC is the *writer* running
    out of room, not the key resolver refusing to start - the two are asserted apart
    below, because an encryption error masquerading as a storage error would make the
    scenario pass for the wrong reason.
    """
    for name in [key for key in os.environ if key.startswith('LUMINEST_')]:
        monkeypatch.delenv(name, raising=False)


# --------------------------------------------------------------------------- helpers

def _assert_same_database(expected: dict, actual: dict) -> None:
    """Assert two fingerprints describe the same database, naming what differs.

    A bare ``assert expected == actual`` on a 38-table dict prints an unreadable wall.
    This reports the *tables* that differ and the row counts on each side, which is what
    tells an operator whether a restore lost rows or only lost a column.
    """
    assert actual['schema_version'] == expected['schema_version'], (
        f'schema version {actual["schema_version"]} != expected {expected["schema_version"]}')
    assert actual['columns'] == expected['columns'], 'column definitions differ'
    assert actual['foreign_keys'] == expected['foreign_keys'], 'foreign keys differ'
    assert actual['indexes'] == expected['indexes'], 'indexes differ'
    assert actual['integrity'] == 'ok', f'integrity_check = {actual["integrity"]}'
    assert actual['foreign_key_violations'] == [], (
        f'foreign_key_check found {actual["foreign_key_violations"]}')

    differing = sorted(
        table
        for table in set(expected['tables']) | set(actual['tables'])
        if expected['tables'].get(table) != actual['tables'].get(table)
    )
    detail = {
        table: {
            'expected_rows': len(expected['tables'].get(table) or []),
            'actual_rows': len(actual['tables'].get(table) or []),
        }
        for table in differing
    }
    assert not differing, f'table contents differ: {json.dumps(detail, sort_keys=True)}'


def _hold_exclusive(db_path: Path, sql: str | None = None) -> sqlite3.Connection:
    """Open a second connection and take the database's write lock, as a peer would."""
    connection = sqlite3.connect(str(db_path), isolation_level=None, timeout=0)
    connection.execute('BEGIN EXCLUSIVE')
    if sql is not None:
        connection.execute(sql)
    return connection


def _write_child_script(path: Path, body: str) -> Path:
    path.write_text(body, encoding='utf-8')
    return path


def _run_child(script: Path, *args: str) -> subprocess.CompletedProcess:
    environment = dict(os.environ)
    environment['PYTHONPATH'] = os.pathsep.join(
        [str(BACKEND_ROOT), str(BACKEND_ROOT / 'tests')])
    # HARNESS_* variables must not leak into the child's Settings, and a LUMINEST_*
    # backup key would silently encrypt the artefact this drill inspects.
    for name in [key for key in environment
                 if key.startswith('HARNESS_') or key.startswith('LUMINEST_')]:
        environment.pop(name)
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(BACKEND_ROOT), env=environment, capture_output=True, text=True, timeout=120,
    )


# =========================================================== 1. real snapshot restore

def test_snapshot_restore_returns_a_real_database_byte_for_byte(tmp_path):
    with build_snapshot(tmp_path) as snapshot:
        db = snapshot.db_path
        expected = snapshot.expected

        # Preconditions. Without these the test could pass on a database that was never
        # interesting: empty, not in WAL, or with no foreign keys to lose.
        assert expected['schema_version'] == SCHEMA_VERSION
        assert expected['integrity'] == 'ok'
        assert expected['foreign_key_violations'] == []
        assert expected['journal_mode'] == 'wal'
        assert len(expected['tables']) > 20
        assert expected['foreign_keys']['attempts'], 'attempts must carry real FKs'
        wal = sidecar_paths(db)['wal']
        assert wal.exists() and wal.stat().st_size > 0, 'the snapshot must be WAL-dirty'
        assert any(
            '李雷' in repr(row) for row in expected['tables']['users']
        ), 'the snapshot must carry non-ASCII content'

        manifest = create_sqlite_backup(db, kind='manual')
        backup = Path(manifest['path'])
        assert manifest['schema_version'] == SCHEMA_VERSION
        assert sha256(backup) == manifest['sha256']
        verify_sqlite_backup(backup)

        # Destroy the live database the way a bad upgrade or a bad operator would: rows
        # deleted, a whole table dropped, forged rows inserted. The WAL keeps the frames,
        # so the restored file must not inherit them.
        with sqlite3.connect(str(db)) as connection:
            connection.execute('PRAGMA foreign_keys=OFF')
            connection.execute('DELETE FROM attempts')
            connection.execute('DELETE FROM messages')
            connection.execute('DELETE FROM invite_redemptions')
            connection.execute('DROP TABLE flashcards')
            connection.execute(
                'INSERT INTO users (id, name, email, password_hash, goal, daily_minutes, '
                'telemetry_consent, created_at) '
                "VALUES ('intruder', 'Intruder', 'intruder@example.test', 'x', 'x', 1, 0, 1.0)")
            connection.commit()
        damaged = fingerprint(db)
        assert damaged['tables'] != expected['tables'], 'the destruction must be real'

        receipt = restore_sqlite_backup(backup, db)
        assert receipt['status'] == 'restored'

        restored = fingerprint(db)
        _assert_same_database(expected, restored)
        # Byte level: the restored file *is* the verified backup, not a re-serialisation.
        assert sha256(db) == manifest['sha256']
        assert restored['journal_mode'] == 'wal', 'the restored file must still be a WAL database'

        # The old database's committed frames were parked as evidence, not replayed.
        assert receipt['wal_sidecars_parked'], 'the stale -wal/-shm must be parked'
        for parked in receipt['wal_sidecars_parked']:
            assert Path(parked).exists()
        live_wal = sidecar_paths(db)['wal']
        assert (not live_wal.exists()) or live_wal.stat().st_size == 0, (
            'a non-empty -wal next to the restored file would replay stale pages')

        # Foreign keys still exist *and* are still enforced by the application's engine.
        engine = app_like_engine(db)
        try:
            with engine.connect() as connection:
                assert connection.exec_driver_sql('PRAGMA foreign_keys').scalar() == 1
                assert connection.exec_driver_sql('PRAGMA foreign_key_check').fetchall() == []
                with pytest.raises(IntegrityError):
                    connection.exec_driver_sql(
                        "INSERT INTO tokens (digest, user_id, expires_at) "
                        "VALUES ('orphan', 'no-such-user', 1.0)")
        finally:
            engine.dispose()


def test_restore_recovers_a_zero_length_live_database_and_keeps_the_evidence(tmp_path):
    """A zero-length main file is what a crash or a failed copy leaves behind.

    It cannot be used as a recovery source, but that is not a reason to refuse the
    restore - refusing would block the one action that fixes the situation. The empty
    file is parked as evidence and the snapshot's rows come back; the snapshot itself is
    never modified.
    """
    with build_snapshot(tmp_path) as snapshot:
        db = snapshot.db_path
        expected = snapshot.expected
        backup = Path(create_sqlite_backup(db)['path'])
        backup_before = sha256(backup)
        db.write_bytes(b'')
        assert db.stat().st_size == 0

        receipt = restore_sqlite_backup(backup, db)
        assert receipt['status'] == 'restored'
        parked = Path(receipt['damaged_live_file_parked'])
        assert parked.is_file() and parked.stat().st_size == 0, (
            'the unusable live file must be parked as evidence')
        assert sha256(backup) == backup_before, 'a restore must never modify the snapshot'
        _assert_same_database(expected, fingerprint(db))


def test_restore_recovers_a_physically_corrupt_live_database(tmp_path):
    """Restoring onto a corrupt database is the main reason restore exists.

    Regression guard for the path that made recovery impossible exactly when it was
    needed: ``_checkpoint_and_check_idle`` must classify "this file is not a database" as
    *damage* (park it as evidence and restore over it), not as *busy* (refuse), and the
    rows that come back must be the ones the snapshot held.
    """
    with build_snapshot(tmp_path) as snapshot:
        db = snapshot.db_path
        expected = snapshot.expected
        backup = Path(create_sqlite_backup(db)['path'])
        garbage = b'not a sqlite database\n' * 100
        db.write_bytes(garbage)

        receipt = restore_sqlite_backup(backup, db)
        assert receipt['status'] == 'restored'
        # The damaged file is not destroyed: its bytes stay available for diagnosis.
        parked = receipt['damaged_live_file_parked']
        assert parked and Path(parked).read_bytes() == garbage, (
            'the damaged live file must be parked as evidence, not silently dropped')
        _assert_same_database(expected, fingerprint(db))


def test_restore_leaves_no_orphan_wal_or_shm_beside_the_live_database(tmp_path):
    """A restore must not leave SQLite sidecars of its own staging copy behind.

    Regression guard. The staging copy is opened read-only for ``integrity_check``, which
    creates ``.<name>.restore-<token>.tmp-wal`` / ``.tmp-shm`` beside it; the swap then
    renames only the main file, so every restore used to deposit those two files plus a
    zero-byte ``<name>-wal`` in the live data directory. They cannot replay - their names
    do not match the live file - but they carry the WAL index of the restored pages and
    accumulate one set per restore. Repeated here on purpose: accumulation, not a single
    stray file, is what this test refuses.
    """
    with build_snapshot(tmp_path / 'source') as snapshot:
        backup = Path(create_sqlite_backup(
            snapshot.db_path, backup_dir=tmp_path / 'backups')['path'])
        live = tmp_path / 'live'
        live.mkdir()
        target = live / 'harness.sqlite3'

        for attempt in range(3):
            restore_sqlite_backup(backup, target)
            # Only sidecars of the live file itself are legitimate here, and after a
            # restore even those are gone; anything else is debris from the staging copy.
            leftovers = sorted(
                path.name for path in live.iterdir()
                if path.is_file()
                and path.name not in (target.name, '.luminest-maintenance.lock')
            )
            assert leftovers == [], (
                f'restore #{attempt + 1} left files behind: {leftovers}')


# ========================================================== 2. interrupted migration

#: Runs the real ``init_db.initialize`` and kills its own process at the worst moment:
#: after the pre-migration backup exists and after ``ALTER TABLE users`` has committed,
#: but before ``ALTER TABLE tokens``. A SIGKILL means no cleanup handler runs and no
#: transaction is rolled back politely - the same end state as a power cut.
_MIGRATION_CHILD = '''
import os, signal, sys
from pathlib import Path
from sqlalchemy import create_engine
sys.path.insert(0, '.')
sys.path.insert(0, 'tests')
from fixtures.build_snapshot import init_db_module
from app.database_backup import create_sqlite_backup

init_db = init_db_module()
db = Path(sys.argv[1])
engine = create_engine(f'sqlite:///{db}')
state = {'armed': False}
real_columns = init_db._columns


def hooked_columns(engine_, table):
    # ``ADDED_COLUMNS`` is walked users -> tokens -> waitlist_signups -> assessments and
    # each table's ALTER commits on its own, so reaching 'tokens' proves users is done.
    if state['armed'] and table == 'tokens':
        os.kill(os.getpid(), signal.SIGKILL)
    return real_columns(engine_, table)


def arming_creator(*args, **kwargs):
    manifest = create_sqlite_backup(*args, **kwargs)
    state['armed'] = True
    return manifest


init_db._columns = hooked_columns
init_db.initialize(engine, backup_creator=arming_creator)
print('MIGRATION COMPLETED WITHOUT BEING KILLED')
'''


def _downgrade_to_v5(connection: sqlite3.Connection) -> None:
    """Turn a current database into a plausible older install.

    The shape is not a guess: it is the current schema minus exactly what the later
    migrations add (the v6 legal/session columns, the v8 assessment column and the
    v6/v8/v9/v11 tables), stamped version 5. That is enough for
    ``init_db._add_missing_columns`` to have real work to do on more than one table -
    which is what makes a half-migrated state possible at all.
    """
    for table in ('refresh_tokens', 'auth_tokens', 'experiment_exposures',
                  'flashcards', 'procedure_runs'):
        connection.execute(f'DROP TABLE {table}')
    for column in ('age_confirmed_at', 'terms_accepted_at', 'terms_version'):
        connection.execute(f'ALTER TABLE users DROP COLUMN {column}')
    connection.execute('ALTER TABLE assessments DROP COLUMN delay_days')
    connection.execute('UPDATE schema_version SET version = 5 WHERE id = 1')


@pytest.mark.skipif(not hasattr(signal, 'SIGKILL'), reason='needs SIGKILL to imitate a crash')
def test_interrupted_migration_restores_the_pre_migration_schema_and_data(tmp_path):
    with build_snapshot(tmp_path) as snapshot:
        db = snapshot.db_path
        # The downgrade goes through the held writer, so the old shape is the committed
        # state and the -wal is clean before the migration starts.
        _downgrade_to_v5(snapshot.writer)
        snapshot.writer.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        before = fingerprint(db)
        assert before['schema_version'] == 5

        child = _write_child_script(tmp_path / 'migrate_and_die.py', _MIGRATION_CHILD)
        completed = _run_child(child, str(db))
        assert completed.returncode == -signal.SIGKILL, (
            f'the migration was not killed as intended: rc={completed.returncode} '
            f'stdout={completed.stdout!r} stderr={completed.stderr[-2000:]!r}')
        assert 'MIGRATION COMPLETED' not in completed.stdout

        # Prove the crash really landed mid-migration: one table gained its columns, the
        # next did not, and the version stamp still says 5. Without this the test would
        # pass on a database that was never touched.
        midway = fingerprint(db)
        user_columns = {row[0] for row in midway['columns']['users']}
        assessment_columns = {row[0] for row in midway['columns']['assessments']}
        assert midway['schema_version'] == 5, 'a crash must not leave a half-written version stamp'
        assert 'terms_version' in user_columns, 'users should have been migrated before the kill'
        assert 'delay_days' not in assessment_columns, 'assessments should not have been migrated'
        assert midway['integrity'] == 'ok'

        backups = list_sqlite_backups(tmp_path / 'backups')
        pre_migration = [row for row in backups if row.get('kind') == 'pre-migration']
        assert len(pre_migration) == 1, f'expected exactly one pre-migration snapshot: {backups}'
        assert pre_migration[0]['checksum_valid'] is True
        manifest = verify_sqlite_backup(pre_migration[0]['path'])
        assert manifest['from_version'] == 5
        assert manifest['to_version'] == SCHEMA_VERSION

        restore_sqlite_backup(manifest['path'], db)

        after = fingerprint(db)
        _assert_same_database(before, after)
        assert after['schema_version'] == 5, 'restore must return the pre-migration version'
        assert 'terms_version' not in {row[0] for row in after['columns']['users']}, (
            'a half-migrated column survived the restore')
        assert 'procedure_runs' not in after['tables'], (
            'a table created during the crashed migration survived the restore')


# ================================================================= 3. storage full

#: Runs one backup in a child process whose writes are capped by RLIMIT_FSIZE. The cap
#: makes the kernel reject everything past N bytes with EFBIG, which SQLite surfaces as
#: a write error mid-copy - the exact situation where a truncated backup could be left
#: behind. SIGXFSZ is ignored so the child reports the error instead of dying silently.
_WRITE_LIMIT_CHILD = '''
import json, resource, signal, sys
signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
limit = int(sys.argv[1])
resource.setrlimit(resource.RLIMIT_FSIZE, (limit, limit))
from app.database_backup import create_sqlite_backup

try:
    manifest = create_sqlite_backup(sys.argv[2], backup_dir=sys.argv[3])
except BaseException as exc:
    print(json.dumps({'ok': False,
                      'type': type(exc).__module__ + '.' + type(exc).__name__,
                      'message': str(exc)}))
else:
    print(json.dumps({'ok': True, 'path': manifest['path'], 'size': manifest['size']}))
'''


def _assert_no_incomplete_backup_is_accepted(backup_dir: Path, source: Path,
                                             expected: dict) -> list[dict]:
    """The invariant under test: nothing that verifies may be an incomplete copy.

    A short file with no sidecar is safe (verification rejects it). The dangerous case
    is a short file *with* a sidecar describing the short file, because then
    ``verify_sqlite_backup`` reports success on a backup that cannot restore the data.
    """
    listed = list_sqlite_backups(backup_dir)
    accepted = [row for row in listed
                if row.get('checksum_valid') and row.get('integrity_ok')]
    for row in accepted:
        assert verify_sqlite_backup(row['path'])['verified'] is True
        copied = fingerprint(Path(row['path']))
        assert copied['tables'] == expected['tables'], (
            f'{row["name"]} verifies as valid but is missing data from {source.name}'
        )
    return listed


def test_write_ceiling_mid_copy_leaves_no_backup_that_verifies(tmp_path):
    """A real partial write: the copy dies part-way through, not before it starts."""
    with build_snapshot(tmp_path) as snapshot:
        db = snapshot.db_path
        expected = snapshot.expected
        backup_dir = tmp_path / 'limited'
        backup_dir.mkdir()

        script = _write_child_script(tmp_path / 'write_until_limit.py', _WRITE_LIMIT_CHILD)
        completed = _run_child(script, str(db.stat().st_size // 2), str(db), str(backup_dir))
        assert completed.returncode == 0, (
            f'child crashed instead of reporting: {completed.stderr[-2000:]}')
        payload = json.loads(completed.stdout.strip().splitlines()[-1])

        assert payload['ok'] is False, (
            f'a backup larger than its write ceiling reported success: {payload}')
        # The failure must be the *write ceiling*, not the encryption resolver: a sealed
        # artefact (format 2) taken because a key was configured would make this pass for
        # the wrong reason.
        assert payload['type'] != 'app.database_backup.BackupEncryptionError', payload
        assert payload['type'] in {
            'sqlite3.OperationalError', 'sqlite3.DatabaseError', 'OSError',
            'app.database_backup.BackupError',
        }, f'unexpected failure type: {payload}'
        assert any(word in payload['message'].lower()
                   for word in ('full', 'i/o', 'disk', 'space')), payload

        listed = _assert_no_incomplete_backup_is_accepted(backup_dir, db, expected)
        assert listed == [], f'a failed copy left backup files behind: {listed}'
        leftovers = sorted(path.name for path in backup_dir.iterdir())
        assert leftovers == [], f'a failed copy left files behind: {leftovers}'

        # The source is untouched and still restorable from a fresh backup.
        _assert_same_database(expected, fingerprint(db))
        healthy = Path(create_sqlite_backup(db)['path'])
        assert verify_sqlite_backup(healthy)['verified'] is True


@pytest.mark.skipif(shutil.which('hdiutil') is None, reason='hdiutil is unavailable')
def test_full_filesystem_does_not_produce_a_backup_that_verifies(tmp_path):
    """A genuinely full filesystem (APFS image), not a simulated one.

    ``hdiutil`` is the macOS-native way to get a filesystem with a hard size limit
    without touching the machine's real disks, so it is used in preference to a
    ``RLIMIT_FSIZE`` stand-in. If the image cannot be created or mounted (a hardened
    sandbox, a machine without the APFS user-space tools), the test skips with the
    command and its output rather than silently falling back to something weaker.
    """
    image = tmp_path / 'full.dmg'
    mount = tmp_path / 'volume'
    mount.mkdir()
    created = subprocess.run(
        ['hdiutil', 'create', '-size', '16m', '-fs', 'APFS', '-volname', 'BKPFULL',
         str(image)], capture_output=True, text=True)
    if created.returncode != 0:
        pytest.skip(f'hdiutil create failed ({created.returncode}): '
                    f'{created.stdout}{created.stderr}')
    attached = subprocess.run(
        ['hdiutil', 'attach', str(image), '-nobrowse', '-mountpoint', str(mount)],
        capture_output=True, text=True)
    if attached.returncode != 0:
        pytest.skip(f'hdiutil attach failed ({attached.returncode}): '
                    f'{attached.stdout}{attached.stderr}')
    try:
        with build_snapshot(tmp_path) as snapshot:
            db = snapshot.db_path
            expected = snapshot.expected
            backup_dir = mount / 'backups'
            backup_dir.mkdir()

            # Fill the volume, then hand back a little room so the copy has somewhere to
            # start and nowhere to finish: that is the case that leaves a truncated file.
            filler = backup_dir / 'filler.bin'
            chunk = b'\x00' * (512 * 1024)
            with open(filler, 'wb') as stream:
                while True:
                    try:
                        stream.write(chunk)
                        stream.flush()
                    except OSError:
                        break
            os.truncate(filler, max(0, filler.stat().st_size - db.stat().st_size // 2))

            started = time.monotonic()
            try:
                manifest = create_sqlite_backup(db, backup_dir=backup_dir)
            except Exception as exc:  # noqa: BLE001 - the type is recorded, not required
                elapsed = time.monotonic() - started
                assert elapsed < BOUNDED_SECONDS, f'ENOSPC took {elapsed:.2f}s to surface'
                # Discriminate the reason: a key nobody configured must not be what stopped
                # the write, or this scenario would be green for the wrong cause.
                assert not isinstance(exc, BackupEncryptionError), (
                    f'the artefact was refused by the encryption resolver, not by the '
                    f'full filesystem: {type(exc).__name__}: {exc}')
                assert isinstance(exc, (OSError, sqlite3.Error, BackupError)), (
                    f'undistinguishable failure on a full disk: {type(exc).__name__}: {exc}')
                assert any(word in str(exc).lower()
                           for word in ('full', 'space', 'disk', 'i/o')), (
                    f'a full filesystem must fail for a storage reason, got '
                    f'{type(exc).__name__}: {exc}')
                listed = _assert_no_incomplete_backup_is_accepted(backup_dir, db, expected)
                assert all(not (row.get('checksum_valid') and row.get('integrity_ok'))
                           for row in listed), f'a truncated backup was accepted: {listed}'
            else:
                # Succeeding is acceptable only if the copy is complete - and the copy
                # under test must be the plaintext writer, not a sealed container.
                assert manifest['format'] == BACKUP_FORMAT, (
                    f"expected a plaintext artefact, got format {manifest['format']}; "
                    'the environment leaked a backup key into this test')
                verify_sqlite_backup(manifest['path'])
                _assert_no_incomplete_backup_is_accepted(backup_dir, db, expected)
                assert fingerprint(Path(manifest['path']))['tables'] == expected['tables'], (
                    'the backup reported success but does not contain the source data')
    finally:
        subprocess.run(['hdiutil', 'detach', str(mount), '-force'],
                       capture_output=True, text=True)


# ================================================================== 4. locked database

def test_backup_under_an_exclusive_writer_takes_a_consistent_snapshot(tmp_path):
    """WAL readers are isolated, so create must *succeed* - but only with committed data.

    The failure this guards against is a backup that reads torn/uncommitted pages and
    then verifies; the assertion is that the copy equals the last committed state and
    excludes the row the other connection has not committed.
    """
    with build_snapshot(tmp_path) as snapshot:
        db = snapshot.db_path
        expected = snapshot.expected
        unforgiven = 'this row was never committed'
        connection = _hold_exclusive(
            db,
            "INSERT INTO messages (id, user_id, concept_id, role, content, created_at) "
            f"VALUES ('uncommitted', 'user-zoe', 'x', 'user', '{unforgiven}', 1.0)",
        )
        try:
            started = time.monotonic()
            manifest = create_sqlite_backup(db, backup_dir=tmp_path / 'under-lock')
            elapsed = time.monotonic() - started
            assert elapsed < BOUNDED_SECONDS, f'create waited {elapsed:.2f}s on a WAL writer'

            assert verify_sqlite_backup(manifest['path'])['verified'] is True
            copied = fingerprint(manifest['path'])
            assert copied['tables'] == expected['tables'], (
                'the backup under a concurrent writer does not match the committed state')
            assert 'uncommitted' not in {
                row[0] for row in copied['tables']['messages']
            }, 'an uncommitted row leaked into the backup'
        finally:
            connection.execute('ROLLBACK')
            connection.close()


def test_restore_under_an_exclusive_writer_refuses_in_bounded_time(tmp_path):
    with build_snapshot(tmp_path) as snapshot:
        db = snapshot.db_path
        expected = snapshot.expected
        backup = Path(create_sqlite_backup(db)['path'])
        backups_before = sorted(path.name for path in (tmp_path / 'backups').iterdir())
        # Damage the live database, so a restore that *did* go ahead would be visible.
        with sqlite3.connect(str(db)) as connection:
            connection.execute("DELETE FROM messages WHERE id = 'msg-1'")
            connection.commit()
        damaged = fingerprint(db)

        connection = _hold_exclusive(db)
        try:
            started = time.monotonic()
            with pytest.raises(BackupBusyError):
                restore_sqlite_backup(backup, db)
            elapsed = time.monotonic() - started
            assert elapsed < BOUNDED_SECONDS, (
                f'restore waited {elapsed:.2f}s on a held lock instead of refusing')
        finally:
            connection.execute('ROLLBACK')
            connection.close()

        # Nothing was written: not the restore, not the pre-restore snapshot, not a
        # staging copy. The live database is exactly as damaged as it was.
        assert fingerprint(db)['tables'] == damaged['tables']
        assert sorted(path.name for path in (tmp_path / 'backups').iterdir()) == backups_before
        assert not list(tmp_path.glob('.*.tmp')), 'a refused restore left staging files'

        # Once the lock is gone the same restore succeeds, so the refusal was the lock.
        restore_sqlite_backup(backup, db)
        _assert_same_database(expected, fingerprint(db))


def test_backup_under_an_exclusive_lock_in_rollback_journal_mode(tmp_path):
    """``journal_mode=DELETE`` has no snapshot isolation: the reader is blocked.

    The live application always runs WAL, but a database restored from an older build
    (or an operator's copy) can be in rollback-journal mode, and then a concurrent
    writer does block the backup. Bounded refusal is acceptable; a hang is not.
    """
    db = tmp_path / 'harness.sqlite3'
    create_schema(db)
    engine = app_like_engine(db)
    try:
        populate(engine)
    finally:
        engine.dispose()
    with sqlite3.connect(str(db)) as connection:
        assert connection.execute('PRAGMA journal_mode=DELETE').fetchone()[0] == 'delete'
    expected = fingerprint(db)
    backup = Path(create_sqlite_backup(db)['path'])
    backup_dir = backup.parent
    before_files = sorted(path.name for path in backup_dir.iterdir())
    before_bytes = sha256(db)

    connection = _hold_exclusive(db)
    try:
        started = time.monotonic()
        with pytest.raises(BackupBusyError) as excinfo:
            create_sqlite_backup(db)
        elapsed = time.monotonic() - started
        assert elapsed < BOUNDED_SECONDS, (
            f'create waited {elapsed:.2f}s on an exclusive lock instead of failing')
        assert 'lock' in str(excinfo.value).lower(), (
            f'a locked database produced an unrelated error: {excinfo.value!r}')
        # A bare sqlite3.OperationalError here would print as a traceback from
        # ``python -m app.database_backup create``, whose handler catches BackupError.
        # The type is therefore part of the contract, not an implementation detail.
    finally:
        connection.execute('ROLLBACK')
        connection.close()

    assert sha256(db) == before_bytes, 'a failed backup must not modify the live database'
    assert sorted(path.name for path in backup_dir.iterdir()) == before_files, (
        'a failed backup left files in the backup directory')
    _assert_same_database(expected, fingerprint(db))
