"""Build a realistic learner database for the backup/resilience tests.

This module is **not** a pytest module (no ``test_*`` functions); it is the fixture
builder that ``tests/test_backup_resilience.py`` and ``scripts/backup_drill.py`` share.

Everything here builds a *real* database through the production schema path
(``scripts/init_db.py:initialize``) rather than a hand-written toy table, because the
question under test is "can backup/restore return a real learner database to the state
it had", and a two-column toy table cannot answer that. The data it writes is:

* several users, one of them in a cohort and referred by another user (foreign keys in
  two directions, including a self-reference),
* rows in eleven dependent tables, each reached through a real ``FOREIGN KEY``,
* non-ASCII text in names, notes and messages, including text outside the BMP,
* an uncheckpointed ``-wal`` file holding committed frames, because that is the state a
  running desktop install is actually in when the upgrade path snapshots it.

``fingerprint()`` captures the whole logical database (every table, every row, every
column definition, every index and every foreign key) as a plain, comparable structure,
so a test can say "row-for-row and column-for-column identical" instead of "the users
table still has a row".
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

BACKEND_ROOT = Path(__file__).resolve().parents[2]
INIT_DB_PY = BACKEND_ROOT / 'scripts' / 'init_db.py'

#: Fixed identifiers, so two builds of the same snapshot are logically identical and a
#: failing assertion prints a stable diff instead of a wall of fresh UUIDs.
COHORT_ID = 'cohort-beta-ctl'
USER_IDS = ('user-an, 李雷', 'user-zoe', 'user-thor')
INVITE_CODE = 'BETA-LI-0001'

_init_db_module = None


def init_db_module():
    """Import ``scripts/init_db.py`` by path, the way the existing backup tests do.

    ``scripts`` is not a package, so a normal import would depend on the caller's
    ``sys.path``. Loading by path keeps this independent of how pytest was invoked.
    """
    global _init_db_module
    if _init_db_module is None:
        spec = importlib.util.spec_from_file_location('init_db_snapshot_fixture', INIT_DB_PY)
        if spec is None or spec.loader is None:  # pragma: no cover - packaging damage
            raise RuntimeError(f'cannot load {INIT_DB_PY}')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _init_db_module = module
    return _init_db_module


def app_like_engine(db_path: Path):
    """An engine whose connections carry the same pragmas the desktop app installs.

    ``app.db.make_database`` runs ``foreign_keys=ON`` and ``journal_mode=WAL`` on every
    connection (``app/db.py:885-891``). The snapshot has to be built under those
    pragmas, otherwise "foreign keys come back intact" would be asserting against a
    database that never enforced them in the first place.
    """
    from sqlalchemy import create_engine, event

    engine = create_engine(f'sqlite:///{db_path}', connect_args={'check_same_thread': False})

    @event.listens_for(engine, 'connect')
    def _pragmas(connection, _record):  # noqa: ANN001 - sqlalchemy callback signature
        cursor = connection.cursor()
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.close()

    return engine


# --------------------------------------------------------------------------- content

def _rows() -> list[tuple[str, list[dict[str, Any]]]]:
    """The fixture content, as ``(table_name, [row, ...])`` in dependency order."""
    user_a, user_b, user_c = USER_IDS
    return [
        ('cohorts', [{
            'id': COHORT_ID,
            'name': 'Closed Beta 控制组',
            'description': 'Cohort with a 200 000-token monthly quota — 测试用',
            'rollout_stage': 'closed_beta',
            'token_quota_monthly': 200_000,
            'request_quota_daily': 400,
            'is_active': True,
            'created_at': 1_700_000_000.0,
        }]),
        ('users', [
            {
                'id': user_a,
                'name': '李雷',
                'email': 'lilei@example.test',
                'password_hash': 'argon2id$v=19$m=65536,t=3,p=4$c2FsdA$hash-a',
                'goal': '把微积分真正学懂，而不是背公式',
                'daily_minutes': 35,
                'course_id': 'integrated_math_1',
                'telemetry_consent': True,
                'training_consent': False,
                'created_at': 1_700_000_100.0,
                'role': 'learner',
                'status': 'active',
                'cohort_id': COHORT_ID,
                'display_name': '雷',
                'locale': 'zh-CN',
                'timezone': 'Asia/Shanghai',
                'email_verified_at': 1_700_000_200.0,
                'referral_code': 'LI-LEI-01',
                'referred_by': None,
                'age_confirmed_at': 1_700_000_200.0,
                'terms_accepted_at': 1_700_000_200.0,
                'terms_version': 'terms-2026-09',
            },
            {
                'id': user_b,
                'name': 'Zoë Müller-李',
                'email': 'zoe@example.test',
                'password_hash': 'argon2id$v=19$m=65536,t=3,p=4$c2FsdB$hash-b',
                'goal': 'Pass the transfer test 28 days later — not just today',
                'daily_minutes': 20,
                'course_id': 'integrated_math_1',
                'telemetry_consent': False,
                'training_consent': True,
                'created_at': 1_700_000_300.0,
                'role': 'learner',
                'status': 'active',
                'cohort_id': COHORT_ID,
                # Self-referential FK: a learner referred by another learner.
                'referred_by': user_a,
                'locale': 'de-DE',
                'timezone': 'Europe/Berlin',
                'referral_code': 'ZOE-MUEL-1',
            },
            {
                'id': user_c,
                'name': 'Ægir Þórsson',
                'email': 'aegir@example.test',
                'password_hash': 'argon2id$v=19$m=65536,t=3,p=4$c2FsdC$hash-c',
                'goal': 'Teach, then measure what actually moved 👩‍🏫',
                'daily_minutes': 15,
                'course_id': 'integrated_math_1',
                'role': 'teacher',
                'status': 'active',
                'cohort_id': None,
                'locale': 'is-IS',
                'timezone': 'Atlantic/Reykjavik',
                'deleted_at': None,
            },
        ]),
        ('user_preferences', [
            {'user_id': user_a, 'theme': 'dark', 'default_modality': 'reading',
             'accessibility': {'dyslexia_font': True, 'reduce_motion': False},
             'notifications': {'weekly_digest': True},
             'ui': {'sidebar': 'collapsed'}, 'updated_at': 1_700_000_400.0},
            {'user_id': user_b, 'theme': 'high_contrast', 'default_modality': 'audio',
             'accessibility': {'large_text': True}, 'notifications': {}, 'ui': {},
             'updated_at': 1_700_000_500.0},
        ]),
        ('tokens', [
            {'digest': 'a' * 64, 'user_id': user_a, 'expires_at': 1_800_000_000.0,
             'created_at': 1_700_000_600.0, 'label': 'MacBook Pro — 书房',
             'user_agent_hash': 'b' * 64, 'ip_hash': 'c' * 64, 'last_used_at': 1_700_000_700.0},
            {'digest': 'd' * 64, 'user_id': user_b, 'expires_at': 1_800_000_000.0,
             'created_at': 1_700_000_800.0, 'label': 'iPad',
             'user_agent_hash': 'e' * 64, 'ip_hash': 'f' * 64},
        ]),
        ('learning_states', [
            {'id': 'state-1', 'user_id': user_a, 'concept_id': 'limits/epsilon-delta',
             'data': {'mastery': 0.62, 'attempts': 7, 'note': '混淆 ε 与 δ 的角色'}},
            {'id': 'state-2', 'user_id': user_b, 'concept_id': 'derivatives/chain-rule',
             'data': {'mastery': 0.81, 'attempts': 12, 'note': 'solid'}},
        ]),
        ('assessments', [
            {'id': 'assess-1', 'user_id': user_a, 'mode': 'transfer', 'delay_days': 7,
             'total': 6, 'answered': 6, 'correct': 4, 'complete': True,
             'created_at': 1_700_001_000.0, 'expires_at': 1_700_009_000.0},
            {'id': 'assess-2', 'user_id': user_b, 'mode': 'practice',
             'total': 10, 'answered': 3, 'correct': 3, 'complete': False,
             'created_at': 1_700_001_100.0, 'expires_at': 1_700_009_100.0},
        ]),
        ('receipts', [
            {'id': 'receipt-1', 'user_id': user_a, 'question_id': 'q-epsilon-01',
             'mode': 'transfer', 'assessment_id': 'assess-1',
             'issued_at': 1_700_001_200.0, 'expires_at': 1_700_001_800.0, 'used': True},
            {'id': 'receipt-2', 'user_id': user_b, 'question_id': 'q-chain-07',
             'mode': 'practice', 'assessment_id': 'assess-2',
             'issued_at': 1_700_001_300.0, 'expires_at': 1_700_001_900.0, 'used': False},
        ]),
        ('attempts', [
            {'id': 'attempt-1', 'user_id': user_a, 'receipt_id': 'receipt-1',
             'client_event_id': 'evt-0001', 'question_id': 'q-epsilon-01',
             'concept_id': 'limits/epsilon-delta', 'mode': 'transfer', 'correct': True,
             'elapsed_seconds': 143.5, 'confidence': 0.7, 'category': 'transfer',
             'payload': {'answer': 'δ = ε/3', 'note': '先固定 ε'},
             'payload_hash': '1' * 64,
             'response': {'chosen': 'B', 'free_text': '因为 |x-2| < δ 推出 |f(x)-4| < ε'},
             'created_at': 1_700_001_400.0},
            {'id': 'attempt-2', 'user_id': user_b, 'receipt_id': 'receipt-2',
             'client_event_id': 'evt-0002', 'question_id': 'q-chain-07',
             'concept_id': 'derivatives/chain-rule', 'mode': 'practice', 'correct': False,
             'elapsed_seconds': 88.0, 'confidence': None, 'category': 'recall',
             'payload': {'answer': '2x·cos(x²)'},
             'payload_hash': '2' * 64,
             'response': {'chosen': 'A'},
             'created_at': 1_700_001_500.0},
        ]),
        ('messages', [
            {'id': 'msg-1', 'user_id': user_a, 'concept_id': 'limits/epsilon-delta',
             'session_id': 'sess-1', 'role': 'user',
             'content': '我还是不明白为什么 δ 可以依赖 ε。',
             'provider': None, 'created_at': 1_700_001_600.0},
            {'id': 'msg-2', 'user_id': user_a, 'concept_id': 'limits/epsilon-delta',
             'session_id': 'sess-1', 'role': 'assistant',
             'content': '因为 ε 是别人给你的挑战，δ 是你的回应。',
             'provider': 'offline-tutor', 'created_at': 1_700_001_601.0},
        ]),
        ('flashcards', [
            {'id': 'card-1', 'user_id': user_a, 'concept_id': 'limits/epsilon-delta',
             'front': 'ε-δ 定义中，谁先被给定？', 'back': 'ε 先被给定，δ 随后选取。',
             'hint': '挑战与回应', 'tags': ['definition', 'limits'],
             'source': {'kind': 'concept', 'concept_id': 'limits/epsilon-delta'},
             'kind': 'definition', 'front_key': '3' * 64, 'due_at': 1_700_010_000.0,
             'stability': 4.2, 'difficulty': 6.1, 'reps': 3, 'lapses': 1,
             'last_review_at': 1_700_002_000.0, 'last_grade': 3, 'state': 'review',
             'created_at': 1_700_001_700.0, 'updated_at': 1_700_002_000.0},
        ]),
        ('procedure_runs', [
            {'id': 'proc-1', 'user_id': user_a, 'concept_id': 'limits/epsilon-delta',
             'course_id': 'integrated_math_1', 'procedure_hash': '4' * 64,
             'profile_name': 'default', 'budget_minutes': 25, 'total_minutes': 22,
             'blocks': [{'order': 1, 'kind': 'read', 'concept_id': 'limits/epsilon-delta'}],
             'completed': [{'order': 1, 'kind': 'read', 'outcome': 'done', 'at': 1_700_002_100.0,
                            'seconds': 300, 'note': '读完了 但 δ 还是模糊'}],
             'skipped': [{'kind': 'video', 'reason': 'no vetted video for this concept'}],
             'rationale': '先读定义，再做一个反向例子。',
             'status': 'active', 'created_at': 1_700_002_100.0, 'updated_at': 1_700_002_200.0},
        ]),
        ('usage_ledger', [
            {'id': 1, 'user_id': user_a, 'request_id': 'req-1', 'feature': 'tutor_chat',
             'provider': 'offline', 'model': None, 'prompt_tokens': 800,
             'completion_tokens': 320, 'total_tokens': 1120, 'cost_micros': 0,
             'latency_ms': 41, 'outcome': 'fallback', 'created_at': 1_700_002_300.0},
            {'id': 2, 'user_id': None, 'request_id': 'req-2', 'feature': 'ingest',
             'provider': 'offline', 'model': None, 'prompt_tokens': 0,
             'completion_tokens': 0, 'total_tokens': 0, 'cost_micros': 0,
             'latency_ms': 12, 'outcome': 'error', 'created_at': 1_700_002_400.0},
        ]),
        ('beta_invites', [
            {'id': 'invite-1', 'code': INVITE_CODE, 'cohort_id': COHORT_ID,
             'email': 'lilei@example.test', 'normalized_email': 'lilei@example.test',
             'max_uses': 1, 'uses': 1, 'status': 'exhausted',
             'expires_at': 1_800_000_000.0, 'created_by': user_c,
             'created_at': 1_700_002_500.0},
        ]),
        ('invite_redemptions', [
            {'id': 'redeem-1', 'invite_id': 'invite-1', 'user_id': user_a,
             'redeemed_at': 1_700_002_600.0, 'ip_hash': '5' * 64},
        ]),
        ('feedback', [
            {'id': 'feedback-1', 'user_id': user_b, 'kind': 'bug', 'rating': None,
             'message': '提交作业后白板把公式渲染成了问号 —— 只在 Safari 上',
             'context': {'surface': 'project', 'locale': 'de-DE', 'build': '1.0.0'},
             'contact_email': 'zoe@example.test', 'status': 'triaged',
             'severity': 'high', 'client_event_id': 'fb-evt-1',
             'created_at': 1_700_002_700.0, 'updated_at': 1_700_002_800.0},
        ]),
        ('memory_notes', [
            {'id': 'note-1', 'user_id': user_a, 'kind': 'semantic',
             'concept_id': 'limits/epsilon-delta',
             'text': '把 δ 当成可以依赖 ε 的量，而不是固定常数。',
             'evidence': {'attempt_id': 'attempt-1', 'correct': True},
             'confidence': 0.55, 'reinforcements': 2,
             'created_at': 1_700_002_900.0, 'last_seen': 1_700_003_000.0},
        ]),
        ('waitlist_signups', [
            {'id': 'wait-1', 'email': 'Futur Schüler@Example.Test',
             'normalized_email': 'futur.schueler@example.test', 'name': 'Jürgen 张',
             'source': 'referral', 'referrer_code': 'LI-LEI-01', 'position': 12,
             'priority': 0, 'status': 'invited', 'consent_marketing': True,
             'created_at': 1_700_003_100.0, 'converted_user_id': None,
             'confirm_digest': '6' * 64, 'confirmed_at': 1_700_003_200.0},
        ]),
    ]


def populate(engine) -> None:
    """Insert the fixture content through the real table definitions.

    Using SQLAlchemy Core rather than hand-written ``INSERT`` text means a schema change
    (a new ``NOT NULL`` column with a server default) does not silently make this builder
    write rows the application could never write.
    """
    from app.db import Base

    with engine.begin() as connection:
        for table_name, rows in _rows():
            table = Base.metadata.tables[table_name]
            # One statement per row, so a row that omits a nullable column is inserted
            # with that column's default rather than being forced to spell every column
            # out (an executemany needs a single, identical key set for every row).
            for row in rows:
                connection.execute(table.insert(), row)


def create_schema(db_path: Path) -> None:
    """Create the current schema with the production migration path (no backup)."""
    engine = app_like_engine(db_path)
    try:
        init_db_module().initialize(engine, automatic_backup=False)
    finally:
        engine.dispose()


def open_wal_writer(db_path: Path) -> sqlite3.Connection:
    """Return an open writer whose committed frames stay in the ``-wal`` file.

    A real desktop install always has a live connection when an upgrade starts, and the
    interesting pages are exactly the ones that have not been checkpointed yet. Closing
    every connection would checkpoint and delete the WAL, which would quietly test the
    easy case. ``wal_autocheckpoint=0`` plus this held-open connection keeps the frames
    in place; callers must keep the connection alive and close it in teardown.
    """
    connection = sqlite3.connect(str(db_path), timeout=0, isolation_level=None)
    connection.execute('PRAGMA journal_mode=WAL')
    connection.execute('PRAGMA wal_autocheckpoint=0')
    connection.execute('PRAGMA foreign_keys=ON')
    connection.execute('BEGIN')
    connection.execute(
        'INSERT INTO messages (id, user_id, concept_id, session_id, role, content, provider, created_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        ('msg-wal-only', USER_IDS[0], 'limits/epsilon-delta', 'sess-1', 'user',
         '这条消息只存在于 -wal 里 —— 尚未 checkpoint。', None, 1_700_003_300.0),
    )
    connection.execute('COMMIT')
    return connection


# ----------------------------------------------------------------------- fingerprint

def _table_names(connection: sqlite3.Connection) -> list[str]:
    return [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def fingerprint(db_path: Path) -> dict[str, Any]:
    """Capture the whole logical database as a comparable structure.

    Rows are sorted by ``repr`` so the comparison is order-insensitive: two databases
    with the same content are equal even if a ``VACUUM`` reordered a table, while a
    single changed byte in a stored value still shows up.
    """
    path = Path(db_path)
    uri = f'{path.resolve().as_uri()}?mode=ro'
    with sqlite3.connect(uri, uri=True, timeout=0) as connection:
        tables: dict[str, list[list[Any]]] = {}
        columns: dict[str, list[list[Any]]] = {}
        foreign_keys: dict[str, list[list[Any]]] = {}
        indexes: dict[str, list[str]] = {}
        for table in _table_names(connection):
            rows = connection.execute(f'SELECT * FROM {_quote(table)}').fetchall()
            tables[table] = sorted((list(row) for row in rows), key=repr)
            columns[table] = [
                [row[1], row[2], row[3], row[5]]  # name, type, notnull, pk
                for row in connection.execute(f'PRAGMA table_info({_quote(table)})')
            ]
            foreign_keys[table] = sorted(
                (list(row) for row in connection.execute(
                    f'PRAGMA foreign_key_list({_quote(table)})')), key=repr)
            indexes[table] = sorted(
                row[1] for row in connection.execute(f'PRAGMA index_list({_quote(table)})')
                if row[1] is not None
            )
        version_row = connection.execute(
            'SELECT version FROM schema_version WHERE id = 1').fetchone()
        integrity = connection.execute('PRAGMA integrity_check').fetchone()[0]
        fk_violations = [list(row) for row in connection.execute('PRAGMA foreign_key_check')]
        journal_mode = connection.execute('PRAGMA journal_mode').fetchone()[0]
    return {
        'schema_version': version_row[0] if version_row else None,
        'tables': tables,
        'columns': columns,
        'foreign_keys': foreign_keys,
        'indexes': indexes,
        'integrity': integrity,
        'foreign_key_violations': fk_violations,
        'journal_mode': journal_mode,
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def sidecar_paths(db_path: Path) -> dict[str, Path]:
    base = str(Path(db_path))
    return {'wal': Path(base + '-wal'), 'shm': Path(base + '-shm')}


def dump_json(payload: Any) -> str:
    """A stable textual rendering, used for readable assertion messages."""
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=str)


@dataclass
class Snapshot:
    """A populated, WAL-dirty learner database plus its logical fingerprint."""

    db_path: Path
    writer: sqlite3.Connection
    expected: dict[str, Any]

    def close(self) -> None:
        try:
            self.writer.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        except sqlite3.Error:
            pass
        self.writer.close()


@contextmanager
def build_snapshot(directory: Path, name: str = 'harness.sqlite3') -> Iterator[Snapshot]:
    """Build a populated database in ``directory`` and keep it WAL-dirty while in use."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    db_path = directory / name
    create_schema(db_path)
    engine = app_like_engine(db_path)
    try:
        populate(engine)
    finally:
        engine.dispose()
    writer = open_wal_writer(db_path)
    snapshot = Snapshot(db_path=db_path, writer=writer, expected=fingerprint(db_path))
    try:
        yield snapshot
    finally:
        snapshot.close()
