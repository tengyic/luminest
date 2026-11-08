"""Explicit, non-destructive schema initializer and migration.

Every version this project has ever shipped is listed as acceptable, because refusing an
older database would force an operator to hand-edit it. Migration is additive: new tables
are created and new columns are added, and no existing row is ever rewritten or dropped.

v1 -> v2  added ``users.training_consent``
v2 -> v3  added ``memory_notes`` and ``harness_runs`` (the harness memory system)
v3 -> v4  added the Beta multi-user layer: cohorts, waitlist, invites, feedback,
          experiments, session metadata, the usage/quota ledger, durable personalisation,
          a generalised consent ledger and the admin audit log. See
          ``migrations/004_beta_multiuser.sql`` for the PostgreSQL reference DDL.
v4 -> v5  added ``users.course_id``, the course a learner is enrolled in. Every
          course-scoped view (map, figures, practice) reads it, so the same harness
          serves several subjects without mixing their graphs.
v5 -> v6  added ``refresh_tokens`` and ``auth_tokens`` (the session/credential token
          split) and ``waitlist_signups.confirm_digest`` / ``confirmed_at`` (waitlist
          double opt-in). See ``migrations/006_session_tokens.sql`` for the PostgreSQL
          reference DDL.
v6 -> v7  no new columns. v7 closes the gap between the two build paths: the PostgreSQL
          reference DDL declared roughly twenty indexes that the SQLAlchemy models did not,
          so a database created fresh (this script) had none of them while a migrated one
          did. Those indexes are now declared in ``app/db.py`` (``BETA_INDEXES``), the
          ``users.role`` CHECK accepts ``staff`` (which ``main.require_admin`` already
          admitted but 004's constraint rejected), and ``quota_policies`` gained an explicit
          partial unique index for the global case. See
          ``migrations/007_index_and_role_parity.sql``. ``scripts/schema_parity.py`` is the
          guard; ``tests/test_schema_equivalence.py`` compares only table and column names,
          so it cannot see index drift.
v7 -> v8  added ``assessments.delay_days`` (the 7d/28d delay of a ``mode='transfer'``
          assessment; nullable, so no existing row changes) and the
          ``experiment_exposures`` table (the writer half of the v4 A/B layer, which
          until now had zero writers). See ``migrations/008_learning_science.sql``.
v8 -> v9  added the ``flashcards`` table: a persisted, per-learner deck with an FSRS-6
          DSR state, so a generated card can be reviewed and scheduled instead of
          existing only for the duration of one generation call. A brand-new table, so
          no existing row or column changes. See ``migrations/009_flashcards.sql``.
v10 -> v11 added the ``procedure_runs`` table: one compiled lesson procedure per
          (learner, concept, plan fingerprint), with its blocks and an append-only
          ``completed`` list. It records a *plan and its progress*, never an
          observation - mastery still moves only through the question and playground
          routes. A brand-new table, so no existing row or column changes. See
          ``migrations/010_lesson_procedure.sql``.

``create_all`` creates missing *tables* but never adds a column to a table that already
exists, so any column added to a table that shipped in an earlier version must also be
listed in ``ADDED_COLUMNS`` below. Omitting it means the column appears on a freshly
created database and silently never appears on an upgraded one.

The migration is written so the same code path works on PostgreSQL (production) and on
SQLite (development), because the schema is the same shape on both.
"""
import sys
from pathlib import Path

from sqlalchemy import inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.db import Base, SCHEMA_VERSION, SchemaVersion, make_database
from app.database_backup import (MAINTENANCE_LOCK_NAME, BackupError,
                                 create_sqlite_backup, default_backup_dir,
                                 list_sqlite_backups, maintenance_lock,
                                 schema_fingerprint, sqlite_path_from_engine)

# Import every module that declares a model on the shared ``Base``. ``create_all`` only
# creates tables that have been *registered*, and a model defined outside ``app.db`` is
# registered by importing its module - not by importing ``Base``. ``CreatedCourse`` lives
# in ``course_builder`` because it owns that table's lifecycle; without this import a
# fresh database was created without ``created_courses``, and the first learner who tried
# to save a course hit "no such table". Tests never saw it: the test app imports
# ``routes_create``, which imports ``course_builder``, so the table was always registered
# there. Keep this list in step with any new out-of-``db`` model.
from app import course_builder  # noqa: F401  - registers ``created_courses``
from app import assessment_book, perspectives  # noqa: F401 - register unit_grades, perspective_reviews

#: Versions this migration path knows how to bring forward.
KNOWN_VERSIONS = (None, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)

#: Columns added to tables that already exist in shipped databases. ``create_all`` cannot
#: add a column to an existing table, so each one is applied explicitly. Every entry is
#: safe to run against a database that already has the column (the inspector gates it) and
#: safe to run against a database that does not yet have the table.
ADDED_COLUMNS = {
    'users': (
        ('role', "text NOT NULL DEFAULT 'learner'"),
        ('status', "text NOT NULL DEFAULT 'active'"),
        ('cohort_id', "text"),
        ('display_name', "text"),
        ('locale', "text NOT NULL DEFAULT 'en'"),
        ('timezone', "text NOT NULL DEFAULT 'UTC'"),
        ('email_verified_at', "double precision"),
        ('onboarding_completed_at', "double precision"),
        ('last_seen_at', "double precision"),
        ('referral_code', "text"),
        ('referred_by', "text"),
        ('deleted_at', "double precision"),
        ('course_id', "text NOT NULL DEFAULT 'integrated_math_1'"),
        # v6 legal / age attestation. `users` shipped in v1, so these are exactly the
        # columns that exist on a fresh database and go missing on an upgraded one.
        ('age_confirmed_at', "double precision"),
        ('terms_accepted_at', "double precision"),
        ('terms_version', "text"),
    ),
    'tokens': (
        ('label', "text"),
        ('user_agent_hash', "text"),
        ('ip_hash', "text"),
        ('last_used_at', "double precision"),
        ('revoked_at', "double precision"),
        ('rotated_from', "text"),
    ),
    # v6. `waitlist_signups` is itself a v4 table, so a database that already ran the
    # v4/v5 migration has the table but not these columns - and ``create_all`` will not
    # add them. Without this entry, ``accounts.confirm_waitlist`` fails at runtime on
    # every upgraded database while working perfectly on a fresh one.
    'waitlist_signups': (
        ('confirm_digest', "text"),
        ('confirmed_at', "double precision"),
    ),
    # v8. `assessments` shipped in v1, so an upgraded database has the table but not
    # this column - and `create_all` will not add it. Without this entry, every
    # delayed transfer test fails on an upgraded database while working on a fresh one.
    'assessments': (
        ('delay_days', "integer"),
    ),
}

#: The first version each piece of schema appeared in. ``ADDED_COLUMNS`` says how to add a
#: column; this says *when* it arrived, which is what a half-finished migration needs.
#:
#: A SIGKILL between two ``ALTER TABLE`` statements leaves a database stamped at the old
#: version with the new columns already in place. A retry then sees "version 5", decides it
#: still needs to upgrade, and writes another ``pre-migration`` snapshot -- of a database
#: that is no longer pre-migration at all. Ten retries and the retention cap has discarded
#: the one honest snapshot. These landmarks are how that contradiction is caught instead.
SCHEMA_LANDMARKS: dict[str, int] = {
    'users.training_consent': 2,
    'memory_notes': 3,
    'harness_runs': 3,
    'users.course_id': 5,
    'users.age_confirmed_at': 6,
    'users.terms_accepted_at': 6,
    'users.terms_version': 6,
    'refresh_tokens': 6,
    'auth_tokens': 6,
    'assessments.delay_days': 8,
    'experiment_exposures': 8,
    'flashcards': 9,
    'procedure_runs': 11,
}


def _columns(engine, table):
    inspector = inspect(engine)
    if not inspector.has_table(table):
        return None
    return {column['name'] for column in inspector.get_columns(table)}


def _add_missing_columns(engine):
    """Add v4 columns to pre-existing tables, dialect-agnostically."""
    for table, columns in ADDED_COLUMNS.items():
        present = _columns(engine, table)
        if present is None:
            continue  # table was just created by create_all with every column already
        with engine.begin() as connection:
            for name, ddl in columns:
                if name in present:
                    continue
                connection.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'))


def _needs_upgrade(engine, current):
    """A database can claim v11 while still missing columns a fresh install would have.

    ``create_all`` never adds a column to an existing table, so drift is repaired by the
    same additive path. A drifted database must be backed up too, even though its version
    stamp already matches ``SCHEMA_VERSION``.
    """
    if current != SCHEMA_VERSION:
        return True
    for table, columns in ADDED_COLUMNS.items():
        present = _columns(engine, table)
        if present is not None and any(name not in present for name, _ in columns):
            return True
    users = _columns(engine, 'users')
    return users is not None and 'training_consent' not in users


def _schema_ahead(engine, current):
    """Schema features from a *later* version than the stamp says, as ``(name, version)``.

    Only the earliest offender is returned: it is the evidence that the last migration
    died part way through, and its version is the one the operator has to reconcile.
    """
    if current is None:
        return []
    tables = set(inspect(engine).get_table_names())
    ahead = []
    for landmark, version in SCHEMA_LANDMARKS.items():
        if version <= current:
            continue
        table, _, column = landmark.partition('.')
        if table not in tables:
            continue
        if column:
            present = _columns(engine, table)
            if present is None or column not in present:
                continue
        ahead.append((landmark, version))
    ahead.sort(key=lambda item: item[1])
    return ahead


def _refuse_if_schema_ahead(engine, current, backup_dir):
    """Never migrate a database whose own schema contradicts its version stamp.

    A crash between two DDL statements leaves exactly this state, and a retry would write
    another ``pre-migration`` snapshot of an already half-upgraded database until retention
    discarded the last honest one.

    The evidence has to be a *snapshot*, not just a shape: a fixture (or a hand-built test
    database) can legitimately present a current schema with an old stamp and no snapshot,
    and refusing that would block a migration there is nothing to protect. Any crash that
    mutated the schema already wrote its pre-migration snapshot first -- the backup is taken
    before the first DDL statement -- so a snapshot of this version plus a schema that no
    longer matches it is proof that a previous attempt ran.
    """
    ahead = _schema_ahead(engine, current)
    if not ahead:
        return
    path = sqlite_path_from_engine(engine)
    if path is None:
        return
    directory = (
        Path(backup_dir) if backup_dir is not None else default_backup_dir(path)
    )
    anchor = _earliest_pre_migration(directory, current)
    if anchor is None:
        return  # nothing honest to protect; the copy about to be written is the first
    live = schema_fingerprint(path)
    if live is not None and anchor.get('schema_fingerprint') == live:
        return  # this database already *is* the anchor: a clean retry from a restored copy
    landmark, version = ahead[0]
    raise RuntimeError(
        f'Refusing to migrate: the database records schema version {current} but already '
        f'contains {landmark}, which arrived in version {version}. A previous migration '
        f'did not finish, so migrating again would snapshot a half-upgraded database and '
        f'retention would eventually discard the last honest one. Restore the earliest '
        f'pre-migration snapshot, {anchor["path"]}, and retry from there.'
    )


def _earliest_pre_migration(directory, version=None):
    """The oldest usable ``pre-migration`` snapshot in ``directory``, or ``None``."""
    candidates = [
        row for row in list_sqlite_backups(directory)
        if row.get('kind') == 'pre-migration' and row.get('checksum_valid')
        and (version is None or row.get('from_version') == version)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda row: (row.get('created_at') or '', row.get('name') or ''))
    return candidates[0]


def initialize(engine, *, automatic_backup=True, backup_dir=None,
               backup_creator=create_sqlite_backup):
    """Create a fresh schema or apply data-preserving migrations.

    Before the first DDL statement on an existing, non-empty SQLite database an online
    backup is written and verified. If the backup cannot be created, migration stops
    with an understandable error and the original database is left untouched. PostgreSQL
    backup stays the deployment operator's responsibility (no file-backed DB to copy).
    ``backup_creator`` is an injectable hook, so backup failure can be tested without
    touching a real learner database.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    is_fresh = not existing_tables
    current = None
    if inspector.has_table('schema_version'):
        with engine.connect() as connection:
            current = connection.execute(
                text('SELECT version FROM schema_version WHERE id = 1')
            ).scalar()
        current = int(current) if current is not None else 1
        if current not in KNOWN_VERSIONS and current != SCHEMA_VERSION:
            raise ValueError(f'Unsupported schema version {current}; refusing to modify tables')
    elif not is_fresh:
        current = 1  # legacy pre-version-table database

    # Before deciding to migrate, check that the schema does not already contradict the
    # stamp. A crash mid-migration leaves exactly that state, and migrating it again would
    # write a `pre-migration` snapshot of a database that is already half-upgraded.
    if not is_fresh:
        _refuse_if_schema_ahead(engine, current, backup_dir)

    needs_upgrade = True if is_fresh else _needs_upgrade(engine, current)

    if automatic_backup and needs_upgrade and not is_fresh:
        path = sqlite_path_from_engine(engine)
        if path is not None and path.is_file() and path.stat().st_size > 0:
            try:
                backup_creator(
                    path, backup_dir=backup_dir, kind='pre-migration',
                    from_version=current, to_version=SCHEMA_VERSION,
                )
            except Exception as exc:
                raise BackupError(
                    f'Pre-migration backup failed; database left unchanged ({path}): {exc}'
                ) from exc

    with engine.begin() as connection:
        if inspector.has_table('users') and 'training_consent' not in {c['name'] for c in inspector.get_columns('users')}:
            connection.execute(text('ALTER TABLE users ADD COLUMN training_consent BOOLEAN NOT NULL DEFAULT FALSE'))
        Base.metadata.create_all(connection)

    _add_missing_columns(engine)

    with engine.begin() as connection:
        current = connection.execute(text('SELECT version FROM schema_version WHERE id = 1')).scalar()
        if current is None:
            connection.execute(text('INSERT INTO schema_version (id, version) VALUES (1, :v)'), {'v': SCHEMA_VERSION})
        else:
            connection.execute(text('UPDATE schema_version SET version = :v WHERE id = 1'), {'v': SCHEMA_VERSION})


if __name__ == '__main__':
    settings = Settings.from_env()
    engine, _ = make_database(settings)
    try:
        with maintenance_lock(settings.data_dir / MAINTENANCE_LOCK_NAME):
            initialize(engine)
        print(f'Schema version {SCHEMA_VERSION} initialized. Existing data was not deleted.')
    finally:
        engine.dispose()
