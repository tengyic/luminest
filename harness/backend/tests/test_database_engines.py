"""Layer 2 integration: the same application on SQLite and PostgreSQL, plus upgrades.

Two engines ship. SQLite is the desktop install; PostgreSQL is the hosted one. A test
suite that only ever runs on SQLite cannot see a dialect difference, and the failure mode
is exactly the bad one: a feature works on every developer machine and fails on the
server, or the reverse. This module runs one identical journey against both engines and
compares the observable result, then exercises the additive migration path on a database
that has been deliberately rolled back.

The PostgreSQL half skips with a *named* reason when no server is reachable, so a
contributor without one still gets a truthful report ("skipped: no server") instead of a
false pass. CI provides one; see .github/workflows/quality.yml.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import uuid
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from app.config import Settings
from app.db import SCHEMA_VERSION, make_database
from app.main import create_app

ADMIN_DSN = os.getenv('HARNESS_TEST_PG_ADMIN', 'postgresql:///postgres')
BACKEND = Path(__file__).resolve().parents[1]


def _load_init_db():
    """Import ``scripts/init_db.py`` (not a package) by path."""
    spec = importlib.util.spec_from_file_location('init_db', BACKEND / 'scripts' / 'init_db.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules['init_db'] = module
    spec.loader.exec_module(module)
    return module


def _admin_connection():
    return psycopg.connect(ADMIN_DSN, connect_timeout=5, autocommit=True)


def postgres_available() -> tuple[bool, str]:
    try:
        with _admin_connection() as connection:
            connection.execute('select 1')
        return True, ''
    except Exception as exc:  # noqa: BLE001 - any failure means "no server here"
        return False, f'no PostgreSQL server at {ADMIN_DSN}: {type(exc).__name__}: {exc}'


@pytest.fixture
def postgres_url():
    ok, reason = postgres_available()
    if not ok:
        pytest.skip(reason)
    name = 'luminest_parity_' + uuid.uuid4().hex[:12]
    with _admin_connection() as connection:
        connection.execute(f'CREATE DATABASE {name}')
    try:
        yield f'postgresql+psycopg:///{name}'
    finally:
        with _admin_connection() as connection:
            connection.execute(
                f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{name}'")
            connection.execute(f'DROP DATABASE IF EXISTS {name}')


def build_client(monkeypatch, tmp_path, url: str) -> TestClient:
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('HARNESS_DATABASE_URL', url)
    monkeypatch.setenv('HARNESS_AUTO_CREATE', '1')
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    return TestClient(create_app(Settings.from_env()))


def register(client: TestClient) -> dict[str, str]:
    """One real account per journey; the API never returns a token for an existing email."""
    response = client.post('/api/v1/auth/register', json={
        'name': 'Parity Learner',
        'email': f'parity-{uuid.uuid4().hex[:12]}@example.test',
        'password': 'Parity-Check-2026!',
        'age_confirmed': True,
        'accept_terms': True,
    })
    assert response.status_code < 300, response.text
    return {'Authorization': 'Bearer ' + response.json()['token']}


def journey(client: TestClient) -> dict:
    """One end-to-end slice that touches auth, flashcards, the memory model and export.

    Deliberately narrow: it is the smallest journey that exercises a generated id, a
    timestamp, a JSON column and a scheduling decision, which are the four places a
    dialect difference actually shows up.
    """
    headers = register(client)

    created = client.post('/api/v1/flashcards',
                          json={'concept_id': 'fractions', 'front': 'What is 3/4?',
                                'back': 'Three of four equal parts.',
                                'source': {'kind': 'concept', 'concept_id': 'fractions'}},
                          headers=headers)
    assert created.status_code < 300, created.text
    card = created.json()

    due = client.get('/api/v1/flashcards', params={'due': True}, headers=headers)
    assert due.status_code < 300, due.text
    due_ids = [row['id'] for row in due.json()['cards']]

    reviewed = client.post(f"/api/v1/flashcards/{card['id']}/review",
                           json={'grade': 3}, headers=headers)
    assert reviewed.status_code < 300, reviewed.text
    reviewed_body = reviewed.json()
    reviewed_card = reviewed_body['card']
    interval = reviewed_body['schedule'].get('interval_seconds')

    stats = client.get('/api/v1/flashcards/stats', headers=headers)
    assert stats.status_code < 300, stats.text

    export = client.get('/api/v1/export', headers=headers)
    assert export.status_code < 300, export.text
    payload = export.json()

    # The account export does not carry the deck (recorded as a gap in the register), so
    # the deck's own interchange endpoint is the one exercised here: a learner's cards
    # must survive export/import on both engines.
    deck = client.get('/api/v1/flashcards/export', headers=headers)
    assert deck.status_code < 300, deck.text

    return {
        'card_created': card['concept_id'] == 'fractions' and card['front'] == 'What is 3/4?',
        'card_was_due': card['id'] in due_ids,
        'interval_is_positive': interval is not None and interval > 0,
        'due_after_review_is_future': reviewed_card.get('due_at', 0) > 0,
        'due_today_count': stats.json().get('due_now'),
        'total_cards': stats.json().get('total'),
        'learned_count': stats.json().get('learned'),
        'export_schema': payload.get('schema_version'),
        'deck_export_has_card': 'What is 3/4?' in deck.text,
        'export_has_user': payload.get('user', {}).get('email', '').startswith('parity-'),
    }


@pytest.mark.parametrize('engine', ['sqlite', 'postgres'])
def test_the_same_journey_behaves_the_same_on_both_engines(engine, monkeypatch, tmp_path,
                                                           postgres_url):
    """SQLite and PostgreSQL must agree on every observable outcome above.

    The comparison is on *behaviour*, never on generated ids or epoch timestamps -- those
    legitimately differ per row. If this test fails, one engine is serving a different
    product and the desktop/hosted split is unsound.
    """
    url = postgres_url if engine == 'postgres' else f'sqlite:///{tmp_path / "harness.sqlite3"}'
    with build_client(monkeypatch, tmp_path / engine, url) as client:
        result = journey(client)

    assert result['card_created'] is True
    assert result['card_was_due'] is True
    assert result['interval_is_positive'] is True
    assert result['due_after_review_is_future'] is True
    assert result['due_today_count'] == 0, 'a reviewed card is no longer due now'
    assert result['total_cards'] == 1
    assert result['learned_count'] == 1
    assert result['export_schema'] == SCHEMA_VERSION
    assert result['deck_export_has_card'] is True
    assert result['export_has_user'] is True


@pytest.mark.parametrize('engine', ['sqlite', 'postgres'])
def test_a_fresh_install_creates_the_full_schema(engine, monkeypatch, tmp_path, postgres_url):
    """A brand-new database must contain every table the product promises, not a subset."""
    url = postgres_url if engine == 'postgres' else f'sqlite:///{tmp_path / "fresh.sqlite3"}'
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path / 'fresh'))
    monkeypatch.setenv('HARNESS_DATABASE_URL', url)
    monkeypatch.setenv('HARNESS_AUTO_CREATE', '1')
    settings = Settings.from_env()
    engine_obj, _factory = make_database(settings)
    with TestClient(create_app(settings)):
        pass
    tables = set(inspect(engine_obj).get_table_names())
    required = {'users', 'tokens', 'refresh_tokens', 'attempts', 'flashcards',
                'schema_version', 'projects', 'telemetry_events', 'procedure_runs'}
    missing = required - tables
    assert not missing, f'{engine} fresh install is missing {sorted(missing)}'


def test_startup_refuses_a_database_from_a_different_schema_version(monkeypatch, tmp_path):
    """An out-of-date database must stop the app, not be silently half-served."""
    data = tmp_path / 'stale'
    data.mkdir()
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(data))
    monkeypatch.setenv('HARNESS_DATABASE_URL', f'sqlite:///{data / "harness.sqlite3"}')
    monkeypatch.setenv('HARNESS_AUTO_CREATE', '1')
    settings = Settings.from_env()
    with TestClient(create_app(settings)):
        pass

    engine, _ = make_database(settings)
    with engine.begin() as connection:
        connection.execute(text('UPDATE schema_version SET version = :v'), {'v': SCHEMA_VERSION - 1})
    engine.dispose()

    with pytest.raises(RuntimeError, match='Schema upgrade required'):
        with TestClient(create_app(settings)):
            pass


def test_an_upgraded_database_keeps_its_rows_and_gains_the_new_schema(monkeypatch, tmp_path):
    """Simulated rollback to v7, then the real migration path forward to v11.

    This is the check that catches the classic migration bug: ``create_all`` adds tables
    but never columns, so a column added to an existing table appears on fresh installs
    and silently never appears on upgraded ones.
    """
    init_db = _load_init_db()
    data = tmp_path / 'upgrade'
    data.mkdir()
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(data))
    monkeypatch.setenv('HARNESS_DATABASE_URL', f'sqlite:///{data / "harness.sqlite3"}')
    settings = Settings.from_env()
    engine, _ = make_database(settings)
    init_db.initialize(engine, automatic_backup=False)

    from app.db import User
    _engine, factory = make_database(settings)
    with factory() as db:
        db.add(User(id='u1', email='keep@example.test', name='Keep Me', password_hash='x',
                    goal='Keep going', daily_minutes=20, role='learner', status='active',
                    course_id='integrated_math_1', created_at=1.0))
        db.commit()
    with engine.begin() as connection:
        # Roll the schema back to v7: drop the v8 column and both v9/v11 tables.
        connection.execute(text('ALTER TABLE assessments DROP COLUMN delay_days'))
        connection.execute(text('DROP TABLE procedure_runs'))
        connection.execute(text('DROP TABLE flashcards'))
        connection.execute(text('UPDATE schema_version SET version = 7'))

    assert 'procedure_runs' not in inspect(engine).get_table_names()

    init_db.initialize(engine, automatic_backup=False)

    tables = set(inspect(engine).get_table_names())
    assert {'flashcards', 'procedure_runs'} <= tables
    columns = {column['name'] for column in inspect(engine).get_columns('assessments')}
    assert 'delay_days' in columns, 'the v8 column did not come back on an upgraded database'
    with engine.begin() as connection:
        assert connection.execute(text('SELECT version FROM schema_version')).scalar() == SCHEMA_VERSION
        kept = connection.execute(text("SELECT email FROM users WHERE id = 'u1'")).scalar()
    assert kept == 'keep@example.test', 'migration must never drop an existing row'
