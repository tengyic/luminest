"""Account deletion: the policy, the cascade, the artefacts, and the restore that undoes them.

The policy itself lives in ``app/account_erasure.py``; this file is the evidence that the
code does what the policy and ``legal/privacy.md`` say. Three things are being proved,
because all three were false before:

1. Deleting the account removes every row the schema says it removes - asserted table by
   table, against the *live* SQLite foreign keys rather than against the ORM declaration.
2. The filesystem artefacts the policy names are gone afterwards, and the ones it names as
   surviving are still there.
3. A backup taken **before** the deletion, restored afterwards, does not bring the account
   back as a login. The tombstone is the ledger outside the database; the test restores a
   real snapshot made by ``app/database_backup.py`` and tries both a token and a password.

Every path is a disposable ``tmp_path``. The real data directory in Application Support is
never opened.
"""
import json
import os
import sqlite3
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import account_erasure
from app import assessment_book, perspectives
from app import deck as deck_store
from app.config import Settings
from app.database_backup import create_sqlite_backup, restore_sqlite_backup, sqlite_path_from_engine
from app.course_builder import CreatedCourse
from app.db import (Assessment, Attempt, AuthToken, BetaInvite, ConsentLedger,
                    Experiment, ExperimentAssignment, ExperimentExposure, Feedback, Flashcard,
                    HarnessRun, InviteRedemption, MemoryNote, Message, PlaygroundRun,
                    ProcedureRun, Project, QuotaCounter, Receipt, RefreshToken, State,
                    TeacherStyleProfile, TelemetryEvent, Token, TrainingConsent, UsageDailyRollup,
                    UsageLedger, UserPreference, WaitlistSignup, now_ts, uid)
from app.harness import board as board_store
from app.harness import media as media_store
from app.main import create_app

PASSWORD = 'long-secret-password'

#: A 1x1 PNG. The media cache sniffs its own bytes, so the "shared bytes survive" assertion
#: needs a real image rather than an arbitrary blob the store would refuse.
ONE_PIXEL_PNG = bytes.fromhex(
    '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489'
    '0000000a49444154789c6360000002000100ffff03000006000557bfabd4'
    '0000000049454e44ae426082')


# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    return Settings.from_env()


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as value:
        yield value


def account(client, label='one'):
    response = client.post('/api/v1/auth/register', json={
        'name': label, 'email': f'{label}@example.test', 'password': PASSWORD})
    assert response.status_code == 201, response.text
    value = response.json()
    return {'Authorization': 'Bearer ' + value['token']}, value


def delete_account(client, headers):
    return client.request('DELETE', '/api/v1/me', headers=headers,
                          json={'confirmation': 'DELETE MY ACCOUNT'})


def db_path(settings) -> Path:
    return Path(settings.data_dir) / 'harness.sqlite3'


def rows(path: Path, sql: str, params=()):  # noqa: ANN001 - tiny test helper
    with sqlite3.connect(str(path)) as connection:
        return connection.execute(sql, params).fetchall()


# --------------------------------------------------------------------------- seeding


def seed_every_user_table(factory, user_id: str) -> dict[str, str]:
    """One row in every table that holds the account, and the id of the row for later checks.

    Written through the ORM so the rows satisfy the real column and CHECK constraints; a
    raw INSERT per table would test a schema nobody ships. Returns ``{table: row_id}`` for
    the rows a test wants to follow into the "survives" half of the policy.
    """
    marked: dict[str, str] = {}
    with factory() as db:
        assessment = Assessment(user_id=user_id, mode='practice', total=1,
                                expires_at=now_ts() + 3600)
        receipt = Receipt(user_id=user_id, question_id='q1', mode='practice',
                          expires_at=now_ts() + 60)
        experiment = Experiment(key=f'exp-{user_id[:8]}', variants=[])
        invite = BetaInvite(code=f'inv-{user_id[:8]}', max_uses=5)
        db.add_all([assessment, receipt, experiment, invite])
        db.flush()

        attempt = Attempt(user_id=user_id, receipt_id=receipt.id, client_event_id='evt-1',
                          question_id='q1', concept_id='fractions', mode='practice',
                          correct=True, elapsed_seconds=1.5, category='arithmetic',
                          payload={}, payload_hash='0' * 64, response={})
        course = CreatedCourse(id=uid(), user_id=user_id, title='Mine', source_kind='text',
                               source_label='note.txt', source_text='hello', pack={},
                               concepts={}, questions={})
        feedback = Feedback(user_id=user_id, kind='bug', message='the button is stuck',
                            contact_email='one@example.test')
        ledger = UsageLedger(user_id=user_id, feature='other', provider='offline',
                             total_tokens=10, cost_micros=5)
        db.add_all([
            Token(digest=uid(), user_id=user_id, expires_at=now_ts() + 3600),
            RefreshToken(digest=uid(), user_id=user_id, session_digest='s', expires_at=now_ts() + 3600),
            AuthToken(user_id=user_id, kind='verify_email', digest=uid(), expires_at=now_ts() + 60),
            TrainingConsent(user_id=user_id, enabled=True),
            ConsentLedger(user_id=user_id, kind='telemetry', enabled=False),
            State(user_id=user_id, concept_id='fractions', data={}),
            assessment, receipt,
            attempt,
            Message(user_id=user_id, concept_id='fractions', role='user', content='why?'),
            Project(user_id=user_id, concept_id='fractions', submission='my work'),
            TelemetryEvent(user_id=user_id, client_id='c1', type='tap', payload={},
                           occurred_at='2026-01-01T00:00:00Z'),
            MemoryNote(user_id=user_id, kind='episodic', concept_id='fractions', text='asked why'),
            HarnessRun(user_id=user_id, move='explain', reason='stuck'),
            Flashcard(user_id=user_id, concept_id='fractions', front='1/2', back='0.5',
                      front_key='k1'),
            InviteRedemption(invite_id=invite.id, user_id=user_id),
            experiment,
            ExperimentAssignment(experiment_id=experiment.id, user_id=user_id, variant='a'),
            ExperimentExposure(experiment_id=experiment.id, user_id=user_id, surface='home'),
            UsageDailyRollup(user_id=user_id, day=date(2026, 1, 1), feature='other',
                             provider='offline', model=''),
            QuotaCounter(user_id=user_id, period='day', period_start=0),
            UserPreference(user_id=user_id),
            TeacherStyleProfile(user_id=user_id, name='Mine'),
            PlaygroundRun(user_id=user_id, artifact_id='sim-1', slug='game', archetype='pick',
                          concept_id='fractions', correct=True),
            ProcedureRun(user_id=user_id, concept_id='fractions', procedure_hash='h1'),
            assessment_book.UnitGrade(
                user_id=user_id, course_id='integrated_math_1', unit_key='seeded-unit',
                strand='Number', unit='Fractions', standards=[], score=1, max_score=2,
                percent=0.5, standards_met=1, standards_total=1, attempts=2),
            perspectives.PerspectiveReview(
                user_id=user_id, artifact_type='project', artifact_id='seeded-project',
                dimension='communication', score=2,
                evidence_note='Explained the method but skipped the units.',
                reviewer_id=user_id, reviewer_role='self'),
            course, feedback, ledger,
        ])
        db.commit()
        marked['feedback'] = feedback.id
        marked['usage_ledger'] = str(ledger.id)
        marked['created_course'] = course.id
        marked['experiment'] = experiment.id
        marked['invite'] = invite.id
    return marked


# --------------------------------------------------------------- schema is the policy


def test_every_foreign_key_into_users_cascades_or_nulls(settings):
    """No table may use ``ON DELETE NO ACTION`` against ``users``: it would block the delete.

    Read from the live SQLite schema, not from the ORM, so a table created by
    ``create_all`` with a different action is caught. ``SET NULL`` is allowed only for the
    seven tables the policy names.
    """
    from app.db import Base, make_database

    engine, _ = make_database(settings)
    Base.metadata.create_all(engine)
    try:
        with engine.connect() as connection:
            tables = [row[0] for row in connection.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table'"))]
            live: dict[str, set[str]] = {}
            for table in tables:
                for row in connection.execute(text(f'PRAGMA foreign_key_list("{table}")')):
                    if row[2] == 'users':
                        live.setdefault(table, set()).add(str(row[6]).upper())
    finally:
        engine.dispose()

    assert live, 'no table references users: the schema probe is wrong'
    for table, actions in live.items():
        assert actions <= {'CASCADE', 'SET NULL'}, f'{table} would block the delete: {actions}'

    declared = account_erasure.foreign_key_fates()
    assert set(live) == set(declared), 'the live schema and the ORM disagree about users FKs'
    assert set(account_erasure.cascade_tables()) | set(account_erasure.set_null_tables()) == set(declared)
    # The seven SET NULL tables are a decision, not an accident; a new one must be
    # classified here rather than silently surviving with its row intact.
    assert set(account_erasure.set_null_tables()) == {
        'admin_audit_log', 'beta_invites', 'feedback', 'feedback_events', 'usage_ledger',
        'users', 'waitlist_signups'}


# ------------------------------------------------------------------- the cascade runs


def test_delete_removes_every_cascading_row(app, client, settings):
    headers, value = account(client)
    user_id = value['user']['id']
    path = db_path(settings)

    cascade = account_erasure.cascade_tables()
    # Snapshot before seeding, then assert the seed *added* a row. A bare ``count >= 1``
    # would be satisfied by registration for ``tokens``, ``refresh_tokens`` and
    # ``auth_tokens`` even if the seed had silently failed, so those three would not be
    # covered by the claim. The delta makes the assertion load-bearing for all 25.
    pre = {name: rows(path, f'SELECT count(*) FROM "{name}" WHERE user_id = ?', (user_id,))[0][0]
           for name in cascade}
    seed_every_user_table(app.state.factory, user_id)
    before = {name: rows(path, f'SELECT count(*) FROM "{name}" WHERE user_id = ?', (user_id,))[0][0]
              for name in cascade}
    unseeded = {name: (pre[name], before[name]) for name in cascade if before[name] <= pre[name]}
    assert unseeded == {}, f'the seed did not add a row, so the assertion below is vacuous: {unseeded}'

    response = delete_account(client, headers)
    assert response.status_code == 204

    after = {name: rows(path, f'SELECT count(*) FROM "{name}" WHERE user_id = ?', (user_id,))[0][0]
             for name in cascade}
    assert {name: count for name, count in after.items() if count} == {}
    assert rows(path, 'SELECT count(*) FROM users WHERE id = ?', (user_id,))[0][0] == 0


def test_owned_feedback_is_deleted_not_anonymised(app, client, settings):
    """The cascade would only null ``feedback.user_id``; the learner's own words must go."""
    headers, value = account(client)
    user_id = value['user']['id']
    marked = seed_every_user_table(app.state.factory, user_id)
    path = db_path(settings)
    assert rows(path, 'SELECT count(*) FROM feedback WHERE id = ?', (marked['feedback'],))[0][0] == 1

    assert delete_account(client, headers).status_code == 204

    assert rows(path, 'SELECT count(*) FROM feedback WHERE id = ?', (marked['feedback'],))[0][0] == 0


def test_sign_in_rate_limit_counter_is_deleted(app, client, settings):
    """``rate_buckets`` has no foreign key to ``users``, so no cascade reaches it.

    Its key is an **unsalted** ``sha256('auth:email:' + address)``: anyone with the database
    can hash a candidate address and learn whether that person used the app. The address is
    known at deletion time, so the counter is removed rather than disclosed.
    """
    from app.security import digest

    headers, value = account(client)
    user_id, email = value['user']['id'], value['user']['email']
    path = db_path(settings)
    key = digest('auth:email:' + email.casefold())
    assert rows(path, 'SELECT count(*) FROM rate_buckets WHERE key = ?', (key,))[0][0] == 1, \
        'registration did not create the sign-in counter this test is about'

    assert delete_account(client, headers).status_code == 204

    assert rows(path, 'SELECT count(*) FROM rate_buckets WHERE key = ?', (key,))[0][0] == 0
    assert rows(path, 'SELECT count(*) FROM users WHERE id = ?', (user_id,))[0][0] == 0


def test_waitlist_entry_is_deleted_and_everyone_elses_is_kept(app, client, settings):
    """``waitlist_signups`` survives with only the reference nulled, and it holds the address."""
    headers, value = account(client)
    user_id, email = value['user']['id'], value['user']['email']
    path = db_path(settings)
    with app.state.factory() as db:
        db.add_all([
            WaitlistSignup(email=email, normalized_email=email.casefold(), name='one',
                           source='landing', priority=0, consent_marketing=True,
                           converted_user_id=user_id),
            WaitlistSignup(email='other@example.test', normalized_email='other@example.test',
                           name='other', source='landing', priority=0, consent_marketing=True),
        ])
        db.commit()

    assert delete_account(client, headers).status_code == 204

    assert rows(path, 'SELECT count(*) FROM waitlist_signups WHERE normalized_email = ?',
                (email.casefold(),))[0][0] == 0
    assert rows(path, 'SELECT count(*) FROM waitlist_signups WHERE normalized_email = ?',
                ('other@example.test',))[0][0] == 1


def test_invite_addressed_to_the_account_keeps_its_code_and_loses_the_address(
        app, client, settings):
    """The invite is the operator's record; the address in it is the learner's."""
    headers, value = account(client)
    user_id, email = value['user']['id'], value['user']['email']
    path = db_path(settings)
    with app.state.factory() as db:
        addressed = BetaInvite(code='addressed-code', email=email,
                               normalized_email=email.casefold(), max_uses=1, uses=0,
                               status='active', created_by=user_id)
        generic = BetaInvite(code='generic-code', max_uses=3, uses=0, status='active',
                             created_by=user_id)
        db.add_all([addressed, generic])
        db.commit()
        addressed_id, generic_id = addressed.id, generic.id

    assert delete_account(client, headers).status_code == 204

    kept = rows(path, 'SELECT email, normalized_email, created_by, uses FROM beta_invites WHERE id = ?',
                (addressed_id,))
    assert kept == [(None, None, None, 0)], kept
    assert rows(path, 'SELECT count(*) FROM beta_invites WHERE id = ?', (generic_id,))[0][0] == 1


def test_usage_ledger_survives_with_the_account_reference_removed(app, client, settings):
    headers, value = account(client)
    user_id = value['user']['id']
    marked = seed_every_user_table(app.state.factory, user_id)
    path = db_path(settings)

    assert delete_account(client, headers).status_code == 204

    row = rows(path, 'SELECT user_id FROM usage_ledger WHERE id = ?', (int(marked['usage_ledger']),))
    assert row, 'the usage ledger row was deleted; it is an accounting record, not learner content'
    assert row[0][0] is None, 'the account reference survived the delete'


def test_operator_records_survive_with_the_reference_removed(app, client, settings):
    """An invite an operator created and a cohort-wide experiment are not the learner's."""
    headers, value = account(client)
    user_id = value['user']['id']
    marked = seed_every_user_table(app.state.factory, user_id)
    path = db_path(settings)

    assert delete_account(client, headers).status_code == 204

    assert rows(path, 'SELECT count(*) FROM beta_invites WHERE id = ?', (marked['invite'],))[0][0] == 1
    assert rows(path, 'SELECT count(*) FROM experiments WHERE id = ?', (marked['experiment'],))[0][0] == 1


# ------------------------------------------------------------------------- artefacts


def test_account_artefacts_are_removed_and_other_accounts_are_untouched(app, client, settings):
    headers, value = account(client, 'one')
    other_headers, other = account(client, 'two')
    user_id, other_id = value['user']['id'], other['user']['id']

    deck_store.save_deck(settings, deck_store.normalise_document(
        {'id': 'deck-mine', 'title': 'Mine'}, owner_id=user_id))
    deck_store.save_deck(settings, deck_store.normalise_document(
        {'id': 'deck-theirs', 'title': 'Theirs'}, owner_id=other_id))
    board_store.create(settings, owner_id=user_id, board_id='board-mine', title='Mine')
    board_store.create(settings, owner_id=other_id, board_id='board-theirs', title='Theirs')
    share = board_store.create_share(settings, 'board-mine', owner_id=user_id)
    assert client.get(f"/api/v1/share/{share['token']}").status_code == 200

    sha_mine = 'a' * 64
    sha_theirs = 'b' * 64
    # One real cached image, so the "shared bytes survive" half is asserted against a file
    # rather than against nothing existing in the first place.
    media_store.store_bytes(settings, ONE_PIXEL_PNG, sha=sha_mine)
    media_store.record_ownership(settings, user_id, [sha_mine], query='cell')
    media_store.record_ownership(settings, other_id, [sha_theirs], query='cell')
    assert board_store.image_file(settings, sha_mine) is not None

    workspace = Path(settings.data_dir) / 'workspaces' / user_id
    workspace.mkdir(parents=True)
    (workspace / 'scratch.py').write_text('print(1)', encoding='utf-8')
    other_workspace = Path(settings.data_dir) / 'workspaces' / other_id
    other_workspace.mkdir(parents=True)
    (other_workspace / 'keep.py').write_text('print(2)', encoding='utf-8')

    assert delete_account(client, headers).status_code == 204

    assert not (Path(settings.data_dir) / 'decks' / 'deck-mine.json').exists()
    assert (Path(settings.data_dir) / 'decks' / 'deck-theirs.json').exists()
    assert not (Path(settings.data_dir) / 'boards' / 'board-mine.json').exists()
    assert (Path(settings.data_dir) / 'boards' / 'board-theirs.json').exists()
    # The document promises a share link stops working with the board. Asserted, because a
    # share token that outlived its board would be a public copy of deleted work.
    assert client.get(f"/api/v1/share/{share['token']}").status_code == 410
    assert not workspace.exists()
    assert (other_workspace / 'keep.py').exists()
    assert media_store.owned_shas(settings, user_id) == set()
    assert media_store.owned_shas(settings, other_id) == {sha_theirs}
    # The policy says the cached bytes survive: they are content-addressed and a lesson or
    # another account may still use them. Asserted, so the document cannot drift.
    assert board_store.image_file(settings, sha_mine) is not None


def test_generated_artifacts_without_an_owner_are_retained(app, client, settings):
    """Decks and simulations in ``sims/`` carry no owner id; they are content, not account data.

    The policy says they survive. This asserts both halves: they do survive, and the
    store has no per-account index to delete them by - which is why the policy says so
    rather than promising a purge it cannot perform.
    """
    from app.harness import sims_store

    headers, value = account(client)
    entry = sims_store.create_artifact(settings, kind='simulation', title='Loop',
                                       html='<!doctype html><html><body>ok</body></html>')
    assert 'owner' not in entry.get('meta', {})

    assert delete_account(client, headers).status_code == 204

    assert (sims_store.store_root(settings) / entry['id'] / 'v1.html').is_file()


# ----------------------------------------------------------------------- the ledger


def test_ledger_lives_outside_the_database_and_names_no_personal_data(app, client, settings):
    headers, value = account(client)
    user_id = value['user']['id']

    assert delete_account(client, headers).status_code == 204

    ledger = account_erasure.ledger_path(settings)
    assert ledger.is_file()
    assert ledger.parent == Path(settings.data_dir)
    body = ledger.read_text(encoding='utf-8')
    assert user_id in body
    assert 'one@example.test' not in body
    assert PASSWORD not in body
    records = account_erasure.load_ledger(settings)
    assert {record['user_id'] for record in records} == {user_id}
    assert {record['phase'] for record in records} == {'requested', 'complete'}
    assert all(record['backup_retention_days'] == account_erasure.BACKUP_RETENTION_DAYS
               for record in records)
    # The tombstone must not amount to a permanent ban on the address: a person who deletes
    # their account can make a new one. The new account is a new id and a new consent trail.
    again = client.post('/api/v1/auth/register', json={
        'name': 'one', 'email': 'one@example.test', 'password': PASSWORD})
    assert again.status_code == 201, again.text
    assert again.json()['user']['id'] != user_id


def test_deletion_reports_the_retention_window(client):
    headers, _ = account(client)
    response = delete_account(client, headers)
    assert response.status_code == 204
    assert response.headers['X-Erasure-Backup-Retention-Days'] == str(
        account_erasure.BACKUP_RETENTION_DAYS)


# ------------------------------------------------------------------- restore cannot undo


def _snapshot_then_delete(app, client, settings):
    headers, value = account(client)
    user_id = value['user']['id']
    with app.state.factory() as db:
        db.add(Message(user_id=user_id, concept_id='fractions', role='user', content='secret note'))
        db.commit()
    path = sqlite_path_from_engine(app.state.engine)
    backup = create_sqlite_backup(path, backup_dir=Path(settings.data_dir) / 'backups',
                                  kind='manual')
    assert delete_account(client, headers).status_code == 204
    assert rows(db_path(settings), 'SELECT count(*) FROM users WHERE id = ?', (user_id,))[0][0] == 0
    # The app quits before a restore: its pooled connections would otherwise keep reading
    # the replaced inode, and the test would be asserting about a database nobody has.
    app.state.engine.dispose()
    restore_sqlite_backup(backup['path'], db_path(settings),
                          backup_dir=Path(settings.data_dir) / 'backups',
                          lock_path=Path(settings.data_dir) / '.restore-test.lock')
    # The snapshot really did bring the row back; without that this test proves nothing.
    assert rows(db_path(settings), 'SELECT count(*) FROM users WHERE id = ?', (user_id,))[0][0] == 1
    return user_id, headers, value


def test_restored_snapshot_cannot_be_used_as_a_live_login(app, client, settings):
    """An access token that the snapshot still contains must not open the account again."""
    user_id, headers, value = _snapshot_then_delete(app, client, settings)

    assert client.get('/api/v1/me', headers=headers).status_code == 401

    # The request did not merely refuse: it finished the deletion the restore undid.
    assert rows(db_path(settings), 'SELECT count(*) FROM users WHERE id = ?', (user_id,))[0][0] == 0
    assert rows(db_path(settings), 'SELECT count(*) FROM messages WHERE user_id = ?',
                (user_id,))[0][0] == 0


def test_restored_snapshot_cannot_sign_in_with_the_old_password(app, client, settings):
    """Login mints a session before any token is checked, so it needs its own guard."""
    user_id, _, value = _snapshot_then_delete(app, client, settings)

    response = client.post('/api/v1/auth/login', json={
        'email': value['user']['email'], 'password': PASSWORD})
    assert response.status_code == 401
    assert 'token' not in response.text
    assert rows(db_path(settings), 'SELECT count(*) FROM users WHERE id = ?', (user_id,))[0][0] == 0


def test_boot_reconcile_reapplies_the_delete(app, client, settings):
    """What runs at startup: the ledger is applied to whatever database is on disk."""
    user_id, _, _ = _snapshot_then_delete(app, client, settings)

    purged = account_erasure.reconcile(app.state.factory, settings)

    assert purged == [user_id]
    assert rows(db_path(settings), 'SELECT count(*) FROM users WHERE id = ?', (user_id,))[0][0] == 0
    assert account_erasure.reconcile(app.state.factory, settings) == []


# --------------------------------------------------------------------------- the ledger is not fail-open


def _restore_after_delete(app, client, settings):
    """Register, snapshot, delete, restore. Returns (user_id, headers, email, tokens)."""
    headers, value = account(client)
    user_id, email = value['user']['id'], value['user']['email']
    tokens = {'access': value['token'], 'refresh': value['refresh_token']}
    snapshot = create_sqlite_backup(sqlite_path_from_engine(app.state.engine),
                                    backup_dir=Path(settings.data_dir) / 'backups',
                                    kind='manual')
    assert delete_account(client, headers).status_code == 204
    app.state.engine.dispose()
    restore_sqlite_backup(snapshot['path'], db_path(settings),
                          backup_dir=Path(settings.data_dir) / 'backups',
                          lock_path=Path(settings.data_dir) / '.restore-ledger.lock')
    assert rows(db_path(settings), 'SELECT count(*) FROM users WHERE id = ?', (user_id,))[0][0] == 1
    return user_id, headers, email, tokens


@pytest.mark.skipif(not hasattr(os, 'chmod'), reason='needs POSIX permissions')
def test_unreadable_ledger_refuses_login_and_refresh(app, client, settings):
    """chmod 000 on the ledger used to mean "nothing was ever erased" and issued a token.

    A list you cannot read is not a list of zero. The credential is refused with 503 (the
    state is unknown, not invalid), which is what stops a restored account signing in.
    """
    user_id, _, email, tokens = _restore_after_delete(app, client, settings)
    ledger = account_erasure.ledger_path(settings)
    assert user_id in ledger.read_text(encoding='utf-8')

    os.chmod(ledger, 0)
    try:
        login = client.post('/api/v1/auth/login', json={'email': email, 'password': PASSWORD})
        assert login.status_code == 503, login.text
        assert 'token' not in login.text
        assert rows(db_path(settings), 'SELECT count(*) FROM users WHERE id = ?', (user_id,))[0][0] == 1

        refresh = client.post('/api/v1/auth/refresh', json={'refresh_token': tokens['refresh']})
        assert refresh.status_code == 503, refresh.text
        assert 'token' not in refresh.text
    finally:
        os.chmod(ledger, 0o600)


@pytest.mark.skipif(not hasattr(os, 'chmod'), reason='needs POSIX permissions')
def test_unreadable_ledger_refuses_startup(settings):
    """Starting anyway would serve every deleted account. Boot fails instead."""
    with TestClient(create_app(settings)):
        pass
    ledger = account_erasure.ledger_path(settings)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text('{"format": 1, "user_id": "x"}\n', encoding='utf-8')
    os.chmod(ledger, 0)
    try:
        with pytest.raises(RuntimeError, match='deletion ledger'):
            with TestClient(create_app(settings)):
                pass
    finally:
        os.chmod(ledger, 0o600)


def test_whole_directory_rollback_still_condemns_the_account(app, client, settings):
    """The mirror lives outside the data folder, so a rollback of the folder loses nothing.

    A rollback that restores the database *and* the ledger together is indistinguishable
    from "the deletion never happened" - no file inside the folder can detect it. The
    mirror is the evidence that survives: it is written one level up.
    """
    user_id, headers, email, _tokens = _restore_after_delete(app, client, settings)
    primary, mirror = account_erasure.ledger_paths(settings)
    assert mirror.parent == Path(settings.data_dir).parent
    assert mirror.is_file() and user_id in mirror.read_text(encoding='utf-8')

    # Roll the data directory back to a state without the primary ledger.
    primary.unlink()
    app.state.engine.dispose()

    assert user_id in account_erasure.erased_ids(settings)
    response = client.post('/api/v1/auth/login', json={'email': email, 'password': PASSWORD})
    assert response.status_code == 401
    assert rows(db_path(settings), 'SELECT count(*) FROM users WHERE id = ?', (user_id,))[0][0] == 0


def test_absent_ledger_is_a_fresh_install_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    settings = Settings.from_env()
    assert account_erasure.erased_ids(settings) == frozenset()


# --------------------------------------------------------------------------- the text


def _privacy_flat() -> str:
    """The policy with runs of whitespace collapsed, so assertions survive re-wrapping."""
    text = (Path(__file__).resolve().parents[1] / 'legal' / 'privacy.md').read_text(
        encoding='utf-8')
    return ' '.join(text.split())


def test_privacy_document_states_the_same_retention_number():
    """Every retention number in the document is the code's number, read from constants.

    No literal "30", "10", "3", "4" or "14" appears in these assertions: changing a
    ``RETENTION_*`` constant must fail the document test until the prose is updated, which
    is the only way a compliance surface stays true across a policy change.
    """
    from app import database_backup as backup

    flat = _privacy_flat()
    assert f'**{backup.RETENTION_MAX_AGE_DAYS} days**' in flat
    assert f'at most **{backup.RETENTION_MAX_BACKUPS}** ordinary snapshots' in flat
    assert f'at most **{backup.RETENTION_MAX_PRE_RESTORE}** are the automatic pre-restore' in flat
    assert f'at most **{backup.RETENTION_MAX_ANCHORS}** anchors' in flat
    total = backup.RETENTION_MAX_BACKUPS + backup.RETENTION_MAX_ANCHORS
    assert f'never more than **{total}** files' in flat
    # The caps nest; they are not added twice. The pre-restore cap must be described as
    # *inside* the ordinary budget ("a total that includes the at most 3"), and the only
    # thing added on top is the anchors. An earlier draft said "10 (plus at most 3)", which
    # promised 13 before anchors existed and contradicted the sweep; a draft that said
    # "10 + 3 + 4" would promise 17.
    assert f'a total that includes the at most **{backup.RETENTION_MAX_PRE_RESTORE}**' in flat
    assert flat.count('plus at most') == 1, 'only the anchors ride on top of the 10'
    assert 'there is no backup we hold' not in flat.lower()


def test_privacy_document_does_not_promise_a_hard_30_day_bound():
    """§8 used to say snapshots go "within 30 days"; §7 keeps recovery anchors forever.

    Two sentences in one document contradicting each other is a compliance defect even when
    each is true in isolation. §8 must carry both exceptions rather than a flat deadline.
    """
    flat = _privacy_flat()
    erasure = flat.split('**Erasure**', 1)[1]
    assert 'within 30 days' not in erasure
    assert 'newest snapshot overall' in erasure
    assert 'pre-migration rollback anchors' in erasure
    section7 = flat.split('## 7.', 1)[1].split('## 8.', 1)[0]
    assert 'newest usable snapshot in the folder' in section7
    assert 'oldest pre-migration snapshot of a schema version' in section7
    # The age rule is absolute for ordinary copies. A count-cap protection ("newest of each
    # kind") that was also treated as an age exemption is the over-claim this check exists
    # to prevent; if it ever returns, the sentence is false again.
    assert 'newest of each kind' not in section7
    # The promise has a stated scope: HTTP routes that accept a credential. "Any route"
    # would be invalidated by the first WebSocket endpoint, and the runtime refusal cannot
    # see one.
    assert 'cannot reach any HTTP route of the app that accepts a credential' in section7
    assert 'in the query string' in section7
    assert 'reach any route again' not in section7


def test_privacy_document_names_the_retention_protections_the_sweep_implements():
    """The rollback anchors are code, and the document may not invent or omit them.

    The phrases are the sweep's own: ``database_backup._prune`` protects the newest usable
    snapshot of each kind and the oldest pre-migration snapshot of each ``from_version``,
    labelled "rollback anchor". If that protection is removed from the code, the document
    would promise something the sweep does not do; if the document drops the sentence, the
    reader is told a 30-day bound that is false on a machine whose oldest upgrade snapshot is
    a year old. This is the deliberate amount of coupling: the document is tied to the
    implementation's own words without importing it.
    """
    backend = Path(__file__).resolve().parents[1]
    flat = _privacy_flat()
    sweep = (backend / 'app' / 'database_backup.py').read_text(encoding='utf-8')

    assert 'oldest pre-migration snapshot from version' in sweep, \
        'the sweep no longer protects the oldest pre-migration copy; §7 would over-claim'
    assert 'rollback anchor' in sweep
    assert 'oldest pre-migration' in flat
    # A restore writes a snapshot of what it replaces; §7 says so, so a reader who restores
    # files knows they are adding copies rather than consuming a fixed set.
    assert 'writes a snapshot of the database it is about to replace' in flat


def test_retention_ceilings_are_quoted_from_the_sweep__and_never_invented():
    """Bidirectional coupling between the sweep's ceilings and §7.

    Named for what it protects rather than for the migration that added it: the day a new
    ``RETENTION_*`` ceiling appears, the document must quote it; the day one disappears, the
    document must stop quoting it. Direction one is the common case (a constant is added and
    the paragraph goes stale); direction two is the one that catches a protection being
    removed while the promise survives in the text.
    """
    import re

    from app import database_backup as backup

    flat = _privacy_flat()
    anchors = getattr(backup, 'RETENTION_MAX_ANCHORS', None)
    quoted = re.search(r'at most \*\*(\d+)\*\* anchors', flat)

    if anchors is None:
        assert quoted is None, (
            '§7 quotes an anchor ceiling the sweep does not enforce: %s' % (quoted.group(0),))
        return

    assert quoted is not None, 'the sweep caps anchors at %s but §7 does not say so' % anchors
    assert int(quoted.group(1)) == anchors
    total = getattr(backup, 'RETENTION_MAX_ON_DISK',
                    backup.RETENTION_MAX_BACKUPS + anchors)
    assert total == backup.RETENTION_MAX_BACKUPS + anchors, (
        'RETENTION_MAX_ON_DISK must be the sum the document quotes')
    assert f'never more than **{total}** files' in flat
    # The ceiling is a number, not an identifier: a legal document must not print a constant
    # name at the reader.
    assert 'RETENTION_MAX_ANCHORS' not in flat
