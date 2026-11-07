"""Regression tests for the SQLite backup/restore subsystem (acceptance 3.3 / 3.8).

Every database here is a disposable file under pytest's tmp_path. The real learner
database in ~/Library/Application Support is never opened.
"""
import hashlib
import importlib.util
import json
import os
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.database_backup import (
    BackupBusyError,
    BackupError,
    BackupVerificationError,
    create_sqlite_backup,
    list_sqlite_backups,
    maintenance_lock,
    restore_sqlite_backup,
    sqlite_path_from_engine,
    verify_sqlite_backup,
)
from app.db import SCHEMA_VERSION

INIT_DB_PY = Path(__file__).resolve().parents[1] / 'scripts' / 'init_db.py'


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
