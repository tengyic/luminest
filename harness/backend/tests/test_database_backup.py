"""Regression tests for the SQLite backup/restore subsystem (acceptance 3.3 / 3.8).

Every database here is a disposable file under pytest's tmp_path. The real learner
database in ~/Library/Application Support is never opened.
"""
import hashlib
import importlib.util
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.database_backup import (
    BACKUP_FORMAT,
    BACKUP_FORMAT_ENCRYPTED,
    BACKUP_KEY_ENV,
    BACKUP_REQUIRE_ENCRYPTION_ENV,
    ENCRYPTED_MAGIC,
    RETENTION,
    RETENTION_MAX_ANCHORS,
    RETENTION_MAX_ON_DISK,
    RETENTION_MAX_AGE_DAYS,
    RETENTION_MAX_BACKUPS,
    BackupBusyError,
    BackupEncryptionError,
    BackupError,
    BackupVerificationError,
    create_sqlite_backup,
    list_sqlite_backups,
    maintenance_lock,
    prune_sqlite_backups,
    restore_sqlite_backup,
    sqlite_path_from_engine,
    STAGING_ORPHAN_AGE_HOURS,
    verify_sqlite_backup,
)
from app.db import SCHEMA_VERSION

INIT_DB_PY = Path(__file__).resolve().parents[1] / 'scripts' / 'init_db.py'

#: A fixed 32-byte key, expressed both ways the loader accepts it.
TEST_KEY_HEX = '00' * 16 + '11' * 16


@pytest.fixture(autouse=True)
def clean_backup_environment(monkeypatch):
    """No test inherits a developer's key or an encryption requirement from the shell."""
    monkeypatch.delenv(BACKUP_KEY_ENV, raising=False)
    monkeypatch.delenv(BACKUP_REQUIRE_ENCRYPTION_ENV, raising=False)


@pytest.fixture
def init_db():
    spec = importlib.util.spec_from_file_location('init_db_backup_test', INIT_DB_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _make_db(path, *, version=10, wal=False):
    connection = sqlite3.connect(str(path))
    if wal:
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('PRAGMA wal_autocheckpoint=0')
    connection.execute(
        'CREATE TABLE users (id VARCHAR(36) PRIMARY KEY, name VARCHAR(100), '
        'email VARCHAR(254), password_hash TEXT)'
    )
    connection.execute(
        'CREATE TABLE schema_version (id INTEGER PRIMARY KEY, version INTEGER)'
    )
    connection.execute('INSERT INTO schema_version (id, version) VALUES (1, ?)', (version,))
    connection.execute(
        'INSERT INTO users (id, name, email, password_hash) VALUES (?, ?, ?, ?)',
        ('learner-1', 'Test Learner', 'learner@example.test', 'not-a-real-hash'),
    )
    connection.commit()
    connection.close()


def _rows(path):
    with sqlite3.connect(str(path)) as connection:
        return connection.execute('SELECT id FROM users ORDER BY id').fetchall()


def _version(path):
    with sqlite3.connect(str(path)) as connection:
        return connection.execute(
            'SELECT version FROM schema_version WHERE id = 1'
        ).fetchone()[0]


# --------------------------------------------------------------------------- 3.8 API

def test_create_list_verify_and_open_backup_independently(tmp_path):
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    resolved = db.resolve()
    manifest = create_sqlite_backup(db, kind='manual')
    backup = Path(manifest['path'])

    assert manifest['sha256'] == _sha256(backup)
    assert manifest['source_database'] == str(resolved)
    assert manifest['schema_version'] == 10
    verified = verify_sqlite_backup(backup)
    assert verified['verified'] is True
    assert verified['resolved_path'] == str(backup.resolve())

    listed = list_sqlite_backups(backup.parent)
    assert len(listed) == 1
    assert listed[0]['checksum_valid'] is True
    assert listed[0]['integrity_ok'] is True
    assert listed[0]['kind'] == 'manual'
    # The backup is a standalone SQLite file, readable without the live connection.
    with sqlite3.connect(f'{backup.as_uri()}?mode=ro', uri=True) as independent:
        assert independent.execute('PRAGMA integrity_check').fetchone() == ('ok',)
        assert independent.execute('SELECT id FROM users').fetchall() == [('learner-1',)]


def test_invalid_checksum_is_rejected_before_restore(tmp_path):
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    backup = Path(create_sqlite_backup(db)['path'])
    sidecar = backup.with_suffix('.json')
    payload = json.loads(sidecar.read_text())
    payload['sha256'] = '0' * 64
    sidecar.write_text(json.dumps(payload))
    before = _sha256(db)

    with pytest.raises(BackupVerificationError, match='checksum mismatch'):
        verify_sqlite_backup(backup)
    with pytest.raises(BackupVerificationError):
        restore_sqlite_backup(backup, db)
    assert list_sqlite_backups(backup.parent)[0]['checksum_valid'] is False
    assert _sha256(db) == before


def test_corrupted_backup_is_rejected_before_restore(tmp_path):
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    backup = Path(create_sqlite_backup(db)['path'])
    backup.write_bytes(b'this is not a sqlite database' + b'\x00' * 64)
    before = _sha256(db)

    with pytest.raises(BackupVerificationError):
        verify_sqlite_backup(backup)
    with pytest.raises(BackupVerificationError):
        restore_sqlite_backup(backup, db)
    assert _sha256(db) == before
    assert _rows(db) == [('learner-1',)]


def test_restore_valid_backup_preserves_data_and_uncheckpointed_wal(tmp_path):
    db = tmp_path / 'learner.sqlite3'
    _make_db(db, wal=True)
    # A committed row that still lives only in the -wal file.
    with sqlite3.connect(str(db)) as connection:
        connection.execute('PRAGMA wal_autocheckpoint=0')
        connection.execute(
            'INSERT INTO users (id, name, email, password_hash) VALUES (?, ?, ?, ?)',
            ('learner-2', 'WAL Learner', 'wal@example.test', 'not-a-real-hash'),
        )
        connection.commit()
    assert Path(str(db) + '-wal').stat().st_size > 0
    backup = Path(create_sqlite_backup(db)['path'])

    with sqlite3.connect(str(db)) as connection:
        connection.execute(
            'INSERT INTO users (id, name, email, password_hash) VALUES (?, ?, ?, ?)',
            ('learner-3', 'Post-backup', 'post@example.test', 'not-a-real-hash'),
        )
        connection.commit()

    receipt = restore_sqlite_backup(backup, db)
    assert receipt['status'] == 'restored'
    assert receipt['sha256'] == _sha256(backup)
    assert Path(receipt['recovery_snapshot']).is_file()
    assert _rows(db) == [('learner-1',), ('learner-2',)]
    with sqlite3.connect(str(db)) as connection:
        assert connection.execute('PRAGMA integrity_check').fetchone() == ('ok',)
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []


def test_restore_under_active_lock_is_rejected(tmp_path):
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    backup = Path(create_sqlite_backup(db)['path'])
    lock = tmp_path / '.luminest-maintenance.lock'
    before = _sha256(db)
    with maintenance_lock(lock):
        with pytest.raises(BackupBusyError, match='Another maintenance operation'):
            restore_sqlite_backup(backup, db, lock_path=lock)
    assert _sha256(db) == before


def test_failed_replacement_leaves_active_database_usable(tmp_path, monkeypatch):
    from app import database_backup as module

    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    backup = Path(create_sqlite_backup(db)['path'])
    with sqlite3.connect(str(db)) as connection:
        connection.execute(
            'INSERT INTO users (id, name, email, password_hash) VALUES (?, ?, ?, ?)',
            ('learner-4', 'Before restore', 'before@example.test', 'not-a-real-hash'),
        )
        connection.commit()
    before = _sha256(db)
    target = db.resolve()
    real_replace = os.replace

    def failing_replace(src, dst, *args, **kwargs):
        if Path(dst).resolve() == target:
            raise OSError('injected replacement failure')
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(module.os, 'replace', failing_replace)
    with pytest.raises(OSError, match='injected replacement failure'):
        restore_sqlite_backup(backup, db)

    assert _sha256(db) == before
    assert _rows(db) == [('learner-1',), ('learner-4',)]
    with sqlite3.connect(str(db)) as connection:
        assert connection.execute('PRAGMA integrity_check').fetchone() == ('ok',)


def test_post_swap_failure_rolls_back_recovery_snapshot(tmp_path, monkeypatch):
    from app import database_backup as module

    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    backup = Path(create_sqlite_backup(db)['path'])
    with sqlite3.connect(str(db)) as connection:
        connection.execute(
            'INSERT INTO users (id, name, email, password_hash) VALUES (?, ?, ?, ?)',
            ('learner-5', 'Live only', 'live@example.test', 'not-a-real-hash'),
        )
        connection.commit()
    target = db.resolve()
    real_integrity = module._integrity_ok
    state = {'injected': False}

    def target_is_bad(path):
        # Fail the post-swap verification once; the rollback verification must pass.
        if Path(path).resolve() == target and not state['injected']:
            state['injected'] = True
            return False
        return real_integrity(path)

    monkeypatch.setattr(module, '_integrity_ok', target_is_bad)
    with pytest.raises(BackupError, match='rolled back'):
        restore_sqlite_backup(backup, db)

    assert _rows(db) == [('learner-1',), ('learner-5',)]
    with sqlite3.connect(str(db)) as connection:
        assert connection.execute('PRAGMA integrity_check').fetchone() == ('ok',)


def test_sqlite_path_from_engine_is_resolved_and_postgres_is_skipped(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "relative.sqlite3"}')
    assert sqlite_path_from_engine(engine) == (tmp_path / 'relative.sqlite3').resolve()
    engine.dispose()
    memory = create_engine('sqlite:///:memory:')
    assert sqlite_path_from_engine(memory) is None
    memory.dispose()

    class FakeURL:
        database = 'dbname'

    class FakeEngine:
        dialect = type('Dialect', (), {'name': 'postgresql'})()
        url = FakeURL()

    assert sqlite_path_from_engine(FakeEngine()) is None


# --------------------------------------------------------------------------- 3.3 hook

def test_initialize_creates_verified_pre_migration_backup(tmp_path, init_db):
    db = tmp_path / 'learner.sqlite3'
    _make_db(db, version=10)
    engine = create_engine(f'sqlite:///{db}')
    try:
        init_db.initialize(engine)
    finally:
        engine.dispose()

    listed = list_sqlite_backups(tmp_path / 'backups')
    assert len(listed) == 1
    assert listed[0]['kind'] == 'pre-migration'
    assert listed[0]['checksum_valid'] is True
    manifest = verify_sqlite_backup(listed[0]['path'])
    assert manifest['from_version'] == 10
    assert manifest['to_version'] == SCHEMA_VERSION
    assert _rows(listed[0]['path']) == [('learner-1',)]
    assert _version(db) == SCHEMA_VERSION
    assert _rows(db) == [('learner-1',)]


def test_backup_failure_stops_migration_and_leaves_database_byte_identical(tmp_path, init_db):
    db = tmp_path / 'learner.sqlite3'
    _make_db(db, version=10)
    before = _sha256(db)
    engine = create_engine(f'sqlite:///{db}')

    def failing_backup_creator(*args, **kwargs):
        raise OSError('injected backup failure')

    try:
        with pytest.raises(BackupError, match='Pre-migration backup failed'):
            init_db.initialize(engine, backup_creator=failing_backup_creator)
    finally:
        engine.dispose()

    assert _sha256(db) == before
    assert _version(db) == 10
    assert _rows(db) == [('learner-1',)]
    assert not (tmp_path / 'backups').exists()


def test_fresh_database_does_not_create_a_backup(tmp_path, init_db):
    engine = create_engine(f'sqlite:///{tmp_path / "fresh.sqlite3"}')
    try:
        init_db.initialize(engine)
        with engine.connect() as connection:
            assert connection.execute(
                text('SELECT version FROM schema_version WHERE id = 1')
            ).scalar() == SCHEMA_VERSION
    finally:
        engine.dispose()
    assert not (tmp_path / 'backups').exists()


# --------------------------------------------------------------------------- retention

def _manifest_path(backup_path):
    return Path(backup_path).with_suffix('.json')


def _read_manifest(backup_path):
    return json.loads(_manifest_path(backup_path).read_text())


def _write_manifest(backup_path, payload):
    _manifest_path(backup_path).write_text(json.dumps(payload, indent=2, sort_keys=True))


def _backdate(backup_path, *, hours=0.0, days=0.0):
    """Move a backup's recorded timestamp into the past.

    ``created_at`` is deliberately not covered by the checksum -- it describes the copy,
    it is not part of it -- so back-dating is exactly a one-field edit.
    """
    payload = _read_manifest(backup_path)
    when = datetime.now(timezone.utc) - timedelta(hours=hours, days=days)
    payload['created_at'] = when.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    _write_manifest(backup_path, payload)
    return payload


def _make_n_backups(db, directory, count, *, kind='manual', age_hours=None):
    """Create ``count`` backups, optionally back-dating each one by a growing age."""
    made = []
    for index in range(count):
        manifest = create_sqlite_backup(db, backup_dir=directory, kind=kind, prune=False)
        if age_hours is not None:
            _backdate(manifest['path'], hours=age_hours * (count - index))
        made.append(Path(manifest['path']))
    return made


def test_retention_keeps_the_newest_ten_backups(tmp_path):
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    directory = tmp_path / 'backups'
    made = _make_n_backups(db, directory, RETENTION_MAX_BACKUPS + 3, age_hours=1)

    report = prune_sqlite_backups(directory, lock_path=tmp_path / 'lock')

    assert len(report['deleted']) == 3
    assert len(report['kept']) == RETENTION_MAX_BACKUPS
    assert sorted(item['name'] for item in report['kept']) == sorted(
        path.name for path in made[-RETENTION_MAX_BACKUPS:]
    )
    assert {item['path'] for item in report['deleted']} == {str(p) for p in made[:3]}
    assert all('more than' in item['reason'] for item in report['deleted'])
    remaining = sorted(directory.glob('*.sqlite3'))
    assert len(remaining) == RETENTION_MAX_BACKUPS
    # A pruned backup leaves no sidecar behind.
    assert len(list(directory.glob('*.json'))) == RETENTION_MAX_BACKUPS


def test_retention_expires_backups_older_than_the_age_cap(tmp_path):
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    directory = tmp_path / 'backups'
    made = _make_n_backups(db, directory, 4)
    _backdate(made[0], days=RETENTION_MAX_AGE_DAYS + 10)
    _backdate(made[1], days=RETENTION_MAX_AGE_DAYS + 1)

    report = prune_sqlite_backups(directory, lock_path=tmp_path / 'lock')

    deleted = {item['path']: item['reason'] for item in report['deleted']}
    assert set(deleted) == {str(made[0]), str(made[1])}
    assert all('older than' in reason for reason in deleted.values())
    assert [path for path in made if path.exists()] == made[2:]


def test_retention_never_deletes_the_newest_usable_backup(tmp_path):
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    directory = tmp_path / 'backups'
    only = Path(create_sqlite_backup(db, backup_dir=directory, prune=False)['path'])
    _backdate(only, days=400)

    report = prune_sqlite_backups(directory, lock_path=tmp_path / 'lock')

    assert report['deleted'] == []
    assert only.exists()
    assert report['kept'][0]['reason'] == 'newest usable backup in the directory'


def test_prune_never_touches_a_file_that_is_not_a_recognised_backup(tmp_path):
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    directory = tmp_path / 'backups'
    made = _make_n_backups(db, directory, RETENTION_MAX_BACKUPS + 2, age_hours=1)

    # 1. A SQLite-looking file with no sidecar at all: not ours, not deletable.
    stranger = directory / 'notes.sqlite3'
    stranger.write_bytes(b'not a backup, just a file with the same extension')
    # 2. A backup whose sidecar was truncated mid-write: unverifiable, kept as evidence.
    damaged = made[0]
    _manifest_path(damaged).write_text('{"format": 1, "sha256": "')
    # 3. A file that is not even named like a backup.
    unrelated = directory / 'README.txt'
    unrelated.write_text('operator notes')

    report = prune_sqlite_backups(directory, lock_path=tmp_path / 'lock')

    assert stranger.exists() and unrelated.exists() and damaged.exists()
    skipped = {item['name']: item['reason'] for item in report['skipped']}
    assert 'notes.sqlite3' in skipped and damaged.name in skipped
    assert 'README.txt' not in skipped  # not even a backup name: never enumerated
    assert str(damaged) not in {item['path'] for item in report['deleted']}
    assert {item['name'] for item in report['deleted']}.isdisjoint(
        {'notes.sqlite3', damaged.name}
    )


def test_prune_leaves_a_backup_another_writer_is_staging(tmp_path):
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    directory = tmp_path / 'backups'
    made = _make_n_backups(db, directory, RETENTION_MAX_BACKUPS + 2, age_hours=1)
    oldest = made[0]
    staging = oldest.with_name(f'.{oldest.name}.tmp')
    staging.write_bytes(b'in flight')

    report = prune_sqlite_backups(directory, lock_path=tmp_path / 'lock')

    assert oldest.exists()
    assert str(oldest) not in {item['path'] for item in report['deleted']}
    reasons = {item['name']: item['reason'] for item in report['skipped']}
    assert 'staging' in reasons[oldest.name]


def test_creating_a_backup_enforces_retention_without_being_asked(tmp_path):
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    directory = tmp_path / 'backups'
    last = {}
    for _ in range(RETENTION_MAX_BACKUPS + 4):
        last = create_sqlite_backup(db, backup_dir=directory, lock_path=tmp_path / 'lock')

    assert 'error' not in (last['retention'] or {})
    assert len(list(directory.glob('*.sqlite3'))) == RETENTION_MAX_BACKUPS
    assert len(last['retention']['deleted']) == 1


def test_prune_is_safe_while_the_caller_holds_the_maintenance_lock(tmp_path):
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    directory = tmp_path / 'backups'
    lock = tmp_path / '.luminest-maintenance.lock'
    _make_n_backups(db, directory, RETENTION_MAX_BACKUPS + 2, age_hours=1)

    # No BackupBusyError colliding with ourselves, and no deadlock: this is the nesting
    # restore_sqlite_backup -> create_sqlite_backup -> prune_sqlite_backups performs.
    with maintenance_lock(lock):
        report = prune_sqlite_backups(directory, lock_path=lock)
        manifest = create_sqlite_backup(db, backup_dir=directory, lock_path=lock)

    assert len(report['deleted']) == 2
    assert len(manifest['retention']['deleted']) == 1


def test_prune_cli_reports_before_deleting_on_dry_run(tmp_path, capsys):
    from app import database_backup as module

    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    directory = tmp_path / 'backups'
    _make_n_backups(db, directory, RETENTION_MAX_BACKUPS + 2, age_hours=1)

    assert module._main(['prune', '--dir', str(directory), '--dry-run']) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['dry_run'] is True
    assert len(payload['deleted']) == 2
    assert len(list(directory.glob('*.sqlite3'))) == RETENTION_MAX_BACKUPS + 2

    assert module._main(['prune', '--dir', str(directory)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload['deleted']) == 2
    assert len(list(directory.glob('*.sqlite3'))) == RETENTION_MAX_BACKUPS


# --------------------------------------------------------------------------- encryption

def test_encryption_round_trip_restores_byte_identically(tmp_path, monkeypatch):
    monkeypatch.setenv(BACKUP_KEY_ENV, TEST_KEY_HEX)
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)

    manifest = create_sqlite_backup(db, encrypt=True, prune=False)
    artefact = Path(manifest['path'])

    assert manifest['format'] == BACKUP_FORMAT_ENCRYPTED
    assert manifest['container'] == 'aes-256-gcm'
    assert manifest['sha256'] != manifest['plaintext_sha256']
    # The artefact on disk is a container, not a SQLite file, and carries no key.
    assert artefact.read_bytes()[:8] == ENCRYPTED_MAGIC
    assert not artefact.read_bytes().startswith(b'SQLite format 3\x00')
    sidecar_bytes = _manifest_path(artefact).read_bytes()
    assert bytes.fromhex(TEST_KEY_HEX) not in sidecar_bytes
    assert TEST_KEY_HEX.encode() not in sidecar_bytes

    listed = list_sqlite_backups(artefact.parent)
    assert listed[0]['encrypted'] is True
    assert listed[0]['checksum_valid'] is True
    assert listed[0]['integrity_ok'] is True

    verify_sqlite_backup(artefact)
    receipt = restore_sqlite_backup(artefact, db)

    assert receipt['encrypted'] is True
    # The restored file is byte-identical to the plaintext that was sealed: a snapshot
    # restores exactly what it contained, not a re-serialised approximation of it.
    assert _sha256(db) == manifest['plaintext_sha256']
    assert _sha256(db) != manifest['sha256']
    assert _rows(db) == [('learner-1',)]
    # Verification materialises plaintext only in the system temp directory: every
    # artefact left in the backup directory is a sealed container, none is a database.
    artefacts = sorted(artefact.parent.glob('*.sqlite3'))
    assert artefact in artefacts
    for other in artefacts:
        assert other.read_bytes()[:8] == ENCRYPTED_MAGIC


def test_tampered_ciphertext_is_refused_rather_than_restored(tmp_path, monkeypatch):
    monkeypatch.setenv(BACKUP_KEY_ENV, TEST_KEY_HEX)
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    manifest = create_sqlite_backup(db, encrypt=True, prune=False)
    artefact = Path(manifest['path'])
    before = _sha256(db)

    # An attacker with write access to the backup directory can also rewrite the plaintext
    # sidecar, so make the checksum consistent: only the GCM tag can refuse this.
    tampered = bytearray(artefact.read_bytes())
    tampered[-1] ^= 0xFF
    artefact.write_bytes(bytes(tampered))
    payload = _read_manifest(artefact)
    payload['sha256'] = _sha256(artefact)
    payload['size'] = artefact.stat().st_size
    _write_manifest(artefact, payload)

    with pytest.raises(BackupVerificationError, match='authentication'):
        verify_sqlite_backup(artefact)
    with pytest.raises(BackupVerificationError, match='authentication'):
        restore_sqlite_backup(artefact, db)
    assert _sha256(db) == before
    assert _rows(db) == [('learner-1',)]


def test_tampered_ciphertext_is_refused_with_a_key_id_mismatch(tmp_path, monkeypatch):
    monkeypatch.setenv(BACKUP_KEY_ENV, TEST_KEY_HEX)
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    artefact = Path(create_sqlite_backup(db, encrypt=True, prune=False)['path'])
    before = _sha256(db)

    monkeypatch.setenv(BACKUP_KEY_ENV, '22' * 32)
    with pytest.raises(BackupEncryptionError, match='sealed with key id'):
        verify_sqlite_backup(artefact)
    with pytest.raises(BackupEncryptionError, match='sealed with key id'):
        restore_sqlite_backup(artefact, db)
    assert _sha256(db) == before


def test_replaying_an_older_valid_container_under_a_new_sidecar_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv(BACKUP_KEY_ENV, TEST_KEY_HEX)
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    old = Path(create_sqlite_backup(db, encrypt=True, prune=False)['path'])
    new = Path(create_sqlite_backup(db, encrypt=True, prune=False)['path'])

    # Both containers are genuine and sealed with the same key, so neither the checksum
    # nor the GCM tag can tell them apart. The timestamp authenticated inside the header
    # is what exposes the swap.
    new.write_bytes(old.read_bytes())
    payload = _read_manifest(new)
    payload['sha256'] = _sha256(new)
    payload['size'] = new.stat().st_size
    _write_manifest(new, payload)

    with pytest.raises(BackupVerificationError, match='Sealed timestamp does not match'):
        verify_sqlite_backup(new)


def test_plaintext_legacy_backup_still_restores_once_a_key_is_configured(tmp_path, monkeypatch):
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    manifest = create_sqlite_backup(db, prune=False)
    artefact = Path(manifest['path'])
    assert manifest['format'] == BACKUP_FORMAT
    assert manifest['container'] == 'sqlite-plaintext'

    monkeypatch.setenv(BACKUP_KEY_ENV, TEST_KEY_HEX)
    assert verify_sqlite_backup(artefact)['encrypted'] is False
    receipt = restore_sqlite_backup(artefact, db)

    assert receipt['status'] == 'restored'
    assert _sha256(db) == manifest['sha256']
    assert _rows(db) == [('learner-1',)]


def test_encryption_requested_without_a_key_refuses_and_writes_nothing(tmp_path):
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    directory = tmp_path / 'backups'

    with pytest.raises(BackupEncryptionError, match='refusing to write a plaintext copy'):
        create_sqlite_backup(db, backup_dir=directory, encrypt=True)

    # Not one byte of plaintext was left behind, and no half-written container either.
    assert list(directory.glob('*')) == []


def test_required_encryption_refuses_a_plaintext_write(tmp_path, monkeypatch):
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    directory = tmp_path / 'backups'
    monkeypatch.setenv(BACKUP_REQUIRE_ENCRYPTION_ENV, '1')

    with pytest.raises(BackupEncryptionError):
        create_sqlite_backup(db, backup_dir=directory)
    with pytest.raises(BackupEncryptionError, match='plaintext backup is refused'):
        create_sqlite_backup(db, backup_dir=directory, encrypt=False)
    assert list(directory.glob('*')) == []


def test_encrypted_pre_restore_snapshot_is_created_and_prunable(tmp_path, monkeypatch):
    monkeypatch.setenv(BACKUP_KEY_ENV, TEST_KEY_HEX)
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    artefact = Path(create_sqlite_backup(db, encrypt=True, prune=False)['path'])

    receipt = restore_sqlite_backup(artefact, db)

    snapshot = Path(receipt['recovery_snapshot'])
    assert snapshot.is_file()
    assert _read_manifest(snapshot)['format'] == BACKUP_FORMAT_ENCRYPTED
    assert verify_sqlite_backup(snapshot)['encrypted'] is True
    listed = list_sqlite_backups(snapshot.parent)
    assert {row['kind'] for row in listed} == {'manual', 'pre-restore'}


def test_total_backup_count_includes_pre_restore_snapshots(tmp_path):
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    directory = tmp_path / 'backups'
    upgrade = _make_n_backups(db, directory, RETENTION_MAX_BACKUPS, kind='pre-migration', age_hours=3)
    snapshots = _make_n_backups(db, directory, 5, kind='pre-restore', age_hours=1)

    report = prune_sqlite_backups(directory, lock_path=tmp_path / 'lock')

    remaining = sorted(directory.glob('*.sqlite3'))
    assert len(remaining) == RETENTION_MAX_BACKUPS
    pre_restore = [row for row in list_sqlite_backups(directory) if row['kind'] == 'pre-restore']
    assert len(pre_restore) == RETENTION.max_pre_restore
    # Two snapshots went to the 3-snapshot sub-cap, then the three oldest upgrade copies
    # went to the total: the directory never holds 10 + 3 full copies.
    assert sorted(item['path'] for item in report['deleted']) == sorted(
        [str(path) for path in upgrade[:3]] + [str(path) for path in snapshots[:2]]
    )


def test_retention_caps_pre_restore_snapshots_more_tightly_than_upgrade_backups(tmp_path):
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    directory = tmp_path / 'backups'
    _make_n_backups(db, directory, 6, kind='pre-migration', age_hours=2)
    made = _make_n_backups(db, directory, 6, kind='pre-restore', age_hours=1)

    report = prune_sqlite_backups(directory, lock_path=tmp_path / 'lock')

    surviving_pre_restore = sorted(
        path for path in made if path.exists()
    )
    assert len(surviving_pre_restore) == RETENTION.max_pre_restore
    assert surviving_pre_restore == sorted(made[-RETENTION.max_pre_restore:])
    assert len(list(directory.glob('*.sqlite3'))) == 6 + RETENTION.max_pre_restore
    assert all(
        item['kind'] == 'pre-restore' for item in report['deleted']
    )


# ------------------------------------------------------------------- retry-safe rollback

def test_retention_protects_the_oldest_pre_migration_snapshot_per_version(tmp_path):
    """A crashed migration is retried, so the *newest* pre-migration copy is not the anchor."""
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    directory = tmp_path / 'backups'
    made = []
    count = RETENTION_MAX_BACKUPS + 2
    for index in range(count):
        manifest = create_sqlite_backup(
            db, backup_dir=directory, kind='pre-migration', from_version=5,
            prune=False,
        )
        # made[0] is the oldest: each later snapshot is one day less old.
        _backdate(
            manifest['path'], days=RETENTION_MAX_AGE_DAYS + 20 + (count - index),
        )
        made.append(Path(manifest['path']))

    report = prune_sqlite_backups(directory, lock_path=tmp_path / 'lock')

    anchor = Path(report['kept'][0]['path'])
    assert made[0].exists(), 'the oldest snapshot of the recorded version is the rollback anchor'
    kept_reason = {item['path']: item['reason'] for item in report['kept']}
    assert 'oldest pre-migration snapshot from version 5' in kept_reason[str(made[0])]
    # It survived despite being far outside the age cap, and it is the oldest, not the newest.
    assert anchor == made[0]


def test_schema_fingerprint_tells_a_true_snapshot_from_a_half_migrated_one(tmp_path):
    from app.database_backup import schema_fingerprint

    whole = tmp_path / 'whole.sqlite3'
    _make_db(whole)
    half = tmp_path / 'half.sqlite3'
    _make_db(half)
    with sqlite3.connect(str(half)) as connection:
        connection.execute('ALTER TABLE users ADD COLUMN terms_version TEXT')
        connection.execute('CREATE TABLE procedure_runs (id TEXT PRIMARY KEY)')
        connection.commit()

    assert schema_fingerprint(whole) != schema_fingerprint(half)
    assert schema_fingerprint(whole).startswith('sha256:')

    manifest = create_sqlite_backup(half, backup_dir=tmp_path / 'backups', prune=False)
    assert manifest['schema_fingerprint'] == schema_fingerprint(half)
    listed = list_sqlite_backups(tmp_path / 'backups')
    assert listed[0]['schema_fingerprint'] == manifest['schema_fingerprint']


def test_retry_after_a_partial_migration_is_refused_and_names_the_anchor(tmp_path, init_db):
    db = tmp_path / 'learner.sqlite3'
    _make_db(db, version=5)

    # The honest snapshot is taken *before* any DDL, exactly as initialize() does it...
    directory = tmp_path / 'backups'
    anchor = Path(create_sqlite_backup(
        db, backup_dir=directory, kind='pre-migration', from_version=5, prune=False,
    )['path'])
    # ...and then the migration dies part way through: a v6 column is already present
    # while the stamp still says v5. That is the state a SIGKILL leaves behind.
    with sqlite3.connect(str(db)) as connection:
        connection.execute('ALTER TABLE users ADD COLUMN terms_version TEXT')
        connection.commit()

    engine = create_engine(f'sqlite:///{db}')
    try:
        with pytest.raises(RuntimeError) as caught:
            init_db.initialize(engine, backup_dir=directory)
    finally:
        engine.dispose()

    message = str(caught.value)
    assert 'users.terms_version' in message
    assert 'did not finish' in message
    assert str(anchor) in message
    # Nothing was migrated and no new snapshot was written over the honest one.
    assert _version(db) == 5
    assert [path.name for path in directory.glob('*.sqlite3')] == [anchor.name]


# ------------------------------------------------------------- restore over a broken live db

def test_restore_recovers_over_a_physically_corrupt_live_database(tmp_path):
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    backup = Path(create_sqlite_backup(db, backup_dir=tmp_path / 'backups')['path'])
    garbage = b'not a sqlite database\n' * 100
    db.write_bytes(garbage)

    receipt = restore_sqlite_backup(backup, db)

    assert receipt['status'] == 'restored'
    assert _rows(db) == [('learner-1',)]
    parked = Path(receipt['damaged_live_file_parked'])
    assert parked.is_file() and parked.read_bytes() == garbage, 'evidence must be kept'
    assert parked.parent == (tmp_path / 'backups')


def test_restore_recovers_over_a_zero_byte_live_database(tmp_path):
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    backup = Path(create_sqlite_backup(db, backup_dir=tmp_path / 'backups')['path'])
    db.write_bytes(b'')

    receipt = restore_sqlite_backup(backup, db)

    assert _rows(db) == [('learner-1',)]
    assert Path(receipt['damaged_live_file_parked']).exists()
    assert receipt['recovery_snapshot'] is None, 'an empty file is no recovery point'


def test_restore_leaves_no_orphan_sidecars_behind(tmp_path):
    db = tmp_path / 'learner.sqlite3'
    _make_db(db, wal=True)
    directory = tmp_path / 'backups'
    backup = Path(create_sqlite_backup(db, backup_dir=directory)['path'])

    restore_sqlite_backup(backup, db)

    debris = sorted(
        path.name
        for folder in (directory, tmp_path)
        for path in folder.iterdir()
        if path.name.endswith(('-wal', '-shm', '-journal')) and path.stat().st_size > 0
    )
    assert debris == [], f'staging debris left behind: {debris}'


def test_verify_refuses_a_snapshot_with_a_stray_wal(tmp_path):
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    backup = Path(create_sqlite_backup(db)['path'])
    stray = Path(str(backup) + '-wal')
    stray.write_bytes(b'\x00' * 8272)
    before = _sha256(db)

    with pytest.raises(BackupVerificationError, match='not self-contained'):
        verify_sqlite_backup(backup)
    with pytest.raises(BackupVerificationError, match='not self-contained'):
        restore_sqlite_backup(backup, db)
    assert _sha256(db) == before
    assert list_sqlite_backups(backup.parent)[0]['self_contained'] is False


# ------------------------------------------------------------------- staging and error types

def test_prune_sweeps_stale_staging_debris_but_never_a_live_write(tmp_path):
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    directory = tmp_path / 'backups'
    keep = Path(create_sqlite_backup(db, backup_dir=directory)['path'])

    stale = directory / f'.{keep.name}.tmp'
    stale.write_bytes(b'crashed mid-write')
    ancient = (datetime.now(timezone.utc) - timedelta(hours=STAGING_ORPHAN_AGE_HOURS + 1)).timestamp()
    os.utime(stale, (ancient, ancient))
    stale_journal = directory / f'.{keep.name}.tmp-journal'
    stale_journal.write_bytes(b'j')
    os.utime(stale_journal, (ancient, ancient))
    # Younger than the published cutoff: indistinguishable from a slow live write.
    younger = (datetime.now(timezone.utc) - timedelta(hours=STAGING_ORPHAN_AGE_HOURS - 1)).timestamp()
    fresh = directory / '.20200101T000000000000Z-manual-deadbeef.sqlite3.tmp'
    fresh.write_bytes(b'in flight')
    os.utime(fresh, (younger, younger))

    report = prune_sqlite_backups(directory, lock_path=tmp_path / 'lock')

    assert not stale.exists() and not stale_journal.exists(), 'old debris is debris'
    assert fresh.exists(), 'a staging file younger than the stated cutoff is never touched'
    assert keep.exists()
    assert {item['name'] for item in report['staging_deleted']} == {
        stale.name, stale_journal.name,
    }


def test_create_raises_a_typed_busy_error_when_the_live_database_is_locked(tmp_path):
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    holder = sqlite3.connect(str(db), isolation_level=None, timeout=0)
    try:
        holder.execute('BEGIN EXCLUSIVE')
        with pytest.raises(BackupBusyError, match='locked by another process'):
            create_sqlite_backup(db, backup_dir=tmp_path / 'backups')
    finally:
        holder.execute('ROLLBACK')
        holder.close()
    assert not (tmp_path / 'backups').exists() or not list(
        (tmp_path / 'backups').glob('*.sqlite3')
    )

# ------------------------------------------------------- anchors: exempt, but bounded

def _anchor_backups(db, directory, count, *, kind='pre-migration', base_days=60.0):
    """``count`` anchors with distinct from_versions; index 0 is the oldest."""
    made = []
    for index in range(count):
        manifest = create_sqlite_backup(
            db, backup_dir=directory, kind=kind, from_version=index + 1, prune=False,
        )
        # index 0 is the oldest: it gets the largest back-date.
        _backdate(manifest['path'], days=base_days + (count - 1 - index))
        made.append(Path(manifest['path']))
    return made


def _hostile_layout(db, directory):
    """The layout verification built: 11 anchors at 60-70 days plus 2 manual at 61-62.

    This is the tree that used to leave 12 files behind while the policy promised a total
    of 10 and an age cap of 30 days.
    """
    anchors = _anchor_backups(db, directory, 11)
    manuals = []
    for index in range(2):
        manifest = create_sqlite_backup(db, backup_dir=directory, prune=False)
        _backdate(manifest['path'], days=61 + index)
        manuals.append(Path(manifest['path']))
    return anchors, manuals


def test_anchors_survive_the_age_rule(tmp_path):
    """An anchor is exempt from the age cap: that is the whole point of keeping it.

    Ordinary copies are not, including the newest of a kind. Being protected from the
    *count* cap is not protection from *expiry*; if it were, "deleted once older than 30
    days" would be false for exactly the copies an operator looks at first.
    """
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    directory = tmp_path / 'backups'
    anchors = _anchor_backups(db, directory, RETENTION_MAX_ANCHORS, base_days=65)
    ordinary = []
    for index in range(3):
        manifest = create_sqlite_backup(db, backup_dir=directory, prune=False)
        # Older than every anchor, so none of them can win "newest overall".
        _backdate(manifest['path'], days=70 + index)
        ordinary.append(Path(manifest['path']))

    report = prune_sqlite_backups(directory, lock_path=tmp_path / 'lock')

    assert all(path.exists() for path in anchors), 'no anchor may be removed by age'
    deleted = {item['path']: item['reason'] for item in report['deleted']}
    assert not any(path.exists() for path in ordinary)
    assert all('older than' in deleted[str(path)] for path in ordinary)


def test_anchor_ceiling_evicts_the_oldest_anchor(tmp_path):
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    directory = tmp_path / 'backups'
    anchors = _anchor_backups(db, directory, RETENTION_MAX_ANCHORS + 7, base_days=60)

    report = prune_sqlite_backups(directory, lock_path=tmp_path / 'lock')

    surviving = [path for path in anchors if path.exists()]
    assert len(surviving) == RETENTION_MAX_ANCHORS
    assert surviving == anchors[-RETENTION_MAX_ANCHORS:], 'the newest anchors are kept'
    evicted = {item['path']: item['reason'] for item in report['deleted']}
    for path in anchors[:-RETENTION_MAX_ANCHORS]:
        assert 'rollback anchors' in evicted[str(path)]


def test_hostile_layout_has_no_non_anchor_file_past_the_age_cap(tmp_path):
    """Separates "protected anchor" from "ordinary file that simply outlived the rule"."""
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    directory = tmp_path / 'backups'
    anchors, manuals = _hostile_layout(db, directory)

    report = prune_sqlite_backups(directory, lock_path=tmp_path / 'lock')

    remaining = list_sqlite_backups(directory)
    now = datetime.now(timezone.utc)
    newest_overall = remaining[-1]['path'] if remaining else None
    over_the_cap = []
    for row in remaining:
        created = datetime.strptime(row['created_at'], '%Y-%m-%dT%H:%M:%S.%fZ').replace(
            tzinfo=timezone.utc
        )
        if (now - created).total_seconds() / 86400.0 <= RETENTION_MAX_AGE_DAYS:
            continue
        # Two documented exemptions, and nothing else: a rollback anchor, and the newest
        # usable copy in the directory (the folder is never emptied by age). Anything else
        # surviving past the cap is the over-claim this test exists to catch.
        anchor = row['kind'] == 'pre-migration' and row['from_version'] is not None
        last_resort = str(row['path']) == newest_overall
        if not (anchor or last_resort):
            over_the_cap.append(row['name'])
    assert over_the_cap == [], (
        f'copies older than {RETENTION_MAX_AGE_DAYS} days that are neither an anchor nor '
        f'the newest usable copy: {over_the_cap}'
    )
    # The hostile layout is 13 files at 60-70 days: nothing there is young, so every
    # manual copy ages out and only the anchor ceiling keeps 4 of the 11 anchors.
    assert not any(path.exists() for path in manuals)
    assert len(remaining) == RETENTION_MAX_ANCHORS


def test_hostile_layout_never_exceeds_the_published_bound(tmp_path):
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    directory = tmp_path / 'backups'
    _hostile_layout(db, directory)

    report = prune_sqlite_backups(directory, lock_path=tmp_path / 'lock')

    on_disk = sorted(directory.glob('*.sqlite3'))
    assert RETENTION_MAX_ON_DISK == RETENTION_MAX_BACKUPS + RETENTION_MAX_ANCHORS
    assert len(on_disk) <= RETENTION_MAX_ON_DISK, (
        f'{len(on_disk)} files on disk, published bound is {RETENTION_MAX_ON_DISK}'
    )
    assert report['policy']['max_anchors'] == RETENTION_MAX_ANCHORS
    assert report['policy']['max_backups'] + report['policy']['max_anchors'] == (
        RETENTION_MAX_ON_DISK
    )


# ------------------------------------------------------- encrypted sidecar must agree

def _encrypted_backup(tmp_path, monkeypatch):
    monkeypatch.setenv(BACKUP_KEY_ENV, TEST_KEY_HEX)
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    manifest = create_sqlite_backup(db, backup_dir=tmp_path / 'backups', encrypt=True, prune=False)
    return db, manifest, Path(manifest['path'])


def test_encrypted_sidecar_without_the_plaintext_digest_is_refused(tmp_path, monkeypatch):
    """Dropping the field used to be accepted, which made the replay check skippable."""
    db, manifest, artefact = _encrypted_backup(tmp_path, monkeypatch)
    payload = _read_manifest(artefact)
    payload.pop('plaintext_sha256')
    _write_manifest(artefact, payload)

    with pytest.raises(BackupVerificationError, match='missing plaintext_sha256'):
        verify_sqlite_backup(artefact)
    with pytest.raises(BackupVerificationError, match='missing plaintext_sha256'):
        restore_sqlite_backup(artefact, db)


def test_encrypted_sidecar_without_the_plaintext_size_is_refused(tmp_path, monkeypatch):
    db, manifest, artefact = _encrypted_backup(tmp_path, monkeypatch)
    payload = _read_manifest(artefact)
    payload.pop('plaintext_size')
    _write_manifest(artefact, payload)

    with pytest.raises(BackupVerificationError, match='missing plaintext_size'):
        verify_sqlite_backup(artefact)


def test_sidecar_from_an_older_snapshot_cannot_be_paired_with_a_newer_artefact(
    tmp_path, monkeypatch
):
    """The other half of the replay: swap the sidecars, leave the artefacts alone."""
    monkeypatch.setenv(BACKUP_KEY_ENV, TEST_KEY_HEX)
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    older = create_sqlite_backup(db, backup_dir=tmp_path / 'backups', encrypt=True, prune=False)
    with sqlite3.connect(str(db)) as connection:
        connection.execute(
            'INSERT INTO users (id, name, email, password_hash) VALUES (?, ?, ?, ?)',
            ('learner-9', 'Newer', 'newer@example.test', 'not-a-real-hash'),
        )
        connection.commit()
    newer = create_sqlite_backup(db, backup_dir=tmp_path / 'backups', encrypt=True, prune=False)

    # The older sidecar is authentic and internally consistent -- and it describes a
    # different snapshot, so the artefact it is attached to no longer matches it.
    _write_manifest(Path(newer['path']), _read_manifest(Path(older['path'])))

    with pytest.raises(BackupVerificationError):
        verify_sqlite_backup(Path(newer['path']))
    with pytest.raises(BackupVerificationError):
        restore_sqlite_backup(Path(newer['path']), db)

def test_a_forged_sidecar_cannot_reuse_an_older_plaintext_digest(tmp_path, monkeypatch):
    """The digest that binds artefact to sidecar is the one a rewrite cannot produce.

    An attacker can recompute the ciphertext hash and copy any timestamp; the plaintext
    digest only exists inside the authenticated header, so leaving the older one behind
    while pointing everything else at the newer artefact has to fail.
    """
    monkeypatch.setenv(BACKUP_KEY_ENV, TEST_KEY_HEX)
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    older = create_sqlite_backup(db, backup_dir=tmp_path / 'backups', encrypt=True, prune=False)
    with sqlite3.connect(str(db)) as connection:
        connection.execute(
            'INSERT INTO users (id, name, email, password_hash) VALUES (?, ?, ?, ?)',
            ('learner-9', 'Newer', 'newer@example.test', 'not-a-real-hash'),
        )
        connection.commit()
    newer = create_sqlite_backup(db, backup_dir=tmp_path / 'backups', encrypt=True, prune=False)
    newer_path = Path(newer['path'])

    forged = _read_manifest(Path(older['path']))
    forged['sha256'] = _sha256(newer_path)
    forged['size'] = newer_path.stat().st_size
    forged['created_at'] = _read_manifest(newer_path)['created_at']
    _write_manifest(newer_path, forged)

    with pytest.raises(BackupVerificationError, match='disagrees with the sealed header'):
        verify_sqlite_backup(newer_path)
    with pytest.raises(BackupVerificationError, match='disagrees with the sealed header'):
        restore_sqlite_backup(newer_path, db)


def test_one_unreadable_artefact_does_not_abort_the_sweep(tmp_path):
    db = tmp_path / 'learner.sqlite3'
    _make_db(db)
    directory = tmp_path / 'backups'
    made = _make_n_backups(db, directory, 4, age_hours=1)
    for path in made[:2]:
        _backdate(path, days=RETENTION_MAX_AGE_DAYS + 5)
    blocked = directory / 'notes.sqlite3'
    blocked.write_bytes(b'not a backup')
    os.chmod(blocked, 0o000)
    try:
        report = prune_sqlite_backups(directory, lock_path=tmp_path / 'lock')
    finally:
        os.chmod(blocked, 0o600)

    skipped = {item['name']: item['reason'] for item in report['skipped']}
    assert 'notes.sqlite3' in skipped
    # The two expired copies were still swept: one unreadable file protects nothing.
    assert not made[0].exists() and not made[1].exists()
    assert made[2].exists() and made[3].exists()
    assert blocked.exists()
