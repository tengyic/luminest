"""An upgraded database must end up with exactly the same schema as a fresh one.

Why this file exists
--------------------
``Base.metadata.create_all()`` creates missing *tables* but never adds a column to a table
that already exists. So a column added to a table that shipped in an earlier version lands
on every fresh install and silently misses every upgraded one -- the two databases diverge,
and the failure shows up at runtime as ``no such column`` on a path that works perfectly in
development.

That gap is easy to reintroduce and hard to notice, because the rest of the suite is blind
to it by construction:

* every other test starts from a database built by ``create_all``, so it always has every
  column, and
* the other migration tests assert that specific *rows* survive an upgrade, not that the
  resulting *schema* is complete.

Two real instances of this were found in review and are what these tests now pin down:
``waitlist_signups.confirm_digest`` / ``confirmed_at`` (a v4 table that gained v6 columns)
and ``users.age_confirmed_at`` / ``terms_accepted_at`` / ``terms_version`` (a v1 table).
Both worked on a fresh database and broke on an upgraded one.
"""
import pytest
from sqlalchemy import inspect, text

from app.config import Settings
from app.db import make_database
from scripts.init_db import initialize


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    return Settings.from_env()

#: What v6 added relative to a v5 database. Taken from the authoritative differential run
#: (004 + 005 + 006 replayed against a real v3 baseline on PostgreSQL), not from reading
#: the source -- so this list is what the migration actually owes, not what it looks like
#: it owes.
V6_TABLES = ('auth_tokens', 'refresh_tokens')

V6_COLUMNS = {
    'waitlist_signups': ('confirm_digest', 'confirmed_at'),
    'users': ('age_confirmed_at', 'terms_accepted_at', 'terms_version'),
}


def _snapshot(engine):
    """Every table with its column names -- the whole schema, in one comparable value."""
    inspector = inspect(engine)
    return {table: {column['name'] for column in inspector.get_columns(table)}
            for table in inspector.get_table_names()}


def _strip_v6(engine):
    """Rewrite a freshly created v6 database into the shape a v5 database actually has."""
    with engine.begin() as connection:
        for table in V6_TABLES:
            connection.execute(text(f'DROP TABLE IF EXISTS {table}'))
        for table, columns in V6_COLUMNS.items():
            for column in columns:
                # SQLite refuses to drop an indexed column, so drop the index first.
                for _, index, *_ in connection.execute(text(f'PRAGMA index_list({table})')).fetchall():
                    indexed = {row[2] for row in connection.execute(text(f'PRAGMA index_info({index})'))}
                    if column in indexed:
                        connection.execute(text(f'DROP INDEX IF EXISTS {index}'))
                connection.execute(text(f'ALTER TABLE {table} DROP COLUMN {column}'))
        connection.execute(text('UPDATE schema_version SET version = 5 WHERE id = 1'))


def test_upgrading_the_previous_version_matches_a_fresh_schema(settings):
    engine, _ = make_database(settings)
    try:
        initialize(engine)
        fresh = _snapshot(engine)

        _strip_v6(engine)
        downgraded = _snapshot(engine)
        # Guard the test itself: if the downgrade silently did nothing, the comparison
        # below would pass for the wrong reason.
        assert 'auth_tokens' not in downgraded
        assert 'confirm_digest' not in downgraded['waitlist_signups']
        assert 'age_confirmed_at' not in downgraded['users']
        assert downgraded != fresh

        initialize(engine)
        upgraded = _snapshot(engine)

        assert upgraded == fresh, (
            'upgrading a v5 database did not reproduce the fresh schema; '
            f'tables only after upgrade: {sorted(set(upgraded) - set(fresh))}; '
            f'tables only when fresh: {sorted(set(fresh) - set(upgraded))}; '
            + '; '.join(
                f'{table} missing {sorted(fresh[table] - upgraded.get(table, set()))}'
                for table in sorted(set(fresh) & set(upgraded))
                if fresh[table] - upgraded.get(table, set())
            )
        )
    finally:
        engine.dispose()


def test_upgrading_is_idempotent(settings):
    """Running the migration twice must not change the schema the second time."""
    engine, _ = make_database(settings)
    try:
        initialize(engine)
        once = _snapshot(engine)
        initialize(engine)
        assert _snapshot(engine) == once
    finally:
        engine.dispose()
