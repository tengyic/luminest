"""Audit: does the ORM declare the same indexes as the migration reference DDL?

Two build paths produce one schema. ``scripts/init_db.py`` builds a *fresh* database from
``Base.metadata``; ``migrations/*.sql`` upgrades an existing one. Nothing forced them to
agree, and until v7 they did not -- 004 declared roughly twenty indexes the SQLAlchemy models
never declared anywhere, so a database created fresh carried none of them.

No other test can see this. ``tests/test_schema_equivalence.py`` compares table and column
*names*, and an index contributes neither. So the drift is silent, and it surfaces not as a
wrong answer but as a ``COUNT(*)`` over ``waitlist_signups`` with nothing behind it (that is
``POST /api/v1/waitlist``, i.e. every signup), or a cost dashboard scanning an append-only
ledger because ``created_at`` is unindexed.

Indexes are compared by ``(table, sorted column names, unique)`` rather than by name, because
the two paths legitimately name the same index differently: the models write
``ix_users_email`` where the DDL writes a column-level ``UNIQUE``.

Usage::

    PYTHONPATH=backend python3 backend/scripts/schema_parity.py           # report only
    PYTHONPATH=backend python3 backend/scripts/schema_parity.py --check   # exit 1 on drift

Exit status is 1 only for the actionable direction (declared by the DDL, missing from the
ORM). Indexes the ORM declares but no migration does are printed as information, because
tables from v1-v3 carry inline ``UNIQUE`` constraints in DDL this scan does not parse.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import UniqueConstraint  # noqa: E402

from app import db  # noqa: E402

MIGRATIONS = ROOT / 'migrations'

#: Reference-DDL indexes the ORM deliberately does not reproduce, keyed the same way as every
#: other entry: ``(table, sorted column names, unique)``.
INTENTIONAL_SQL_ONLY = {
    ('quota_counters', ('period', 'period_start', 'user_id'), False):
        'duplicates the (user_id, period, period_start) UNIQUE constraint already on the table',
}

#: ``ON <table> [USING m] ( <columns> ) <WHERE ... | ;>``. The column group is terminated by
#: ``)`` followed by ``WHERE`` or ``;`` rather than by the first ``)``, because an index
#: expression may contain its own parentheses -- ``quota_policies_unique_active`` is on
#: ``(scope, coalesce(scope_id, ''), period)`` and a naive scan would stop inside the call.
_CREATE_INDEX = re.compile(
    r'CREATE\s+(?P<unique>UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<name>[\w"]+)\s+'
    r'ON\s+(?P<table>[\w"]+)\s*(?:USING\s+\w+\s*)?'
    r'\((?P<columns>.*?)\)\s*(?:WHERE\b|;)',
    re.IGNORECASE | re.DOTALL)

_IDENT = re.compile(r'[A-Za-z_][A-Za-z_0-9]*')


def _column_names(table_name: str, expression: str) -> tuple[str, ...]:
    """Columns named in one index expression, sorted.

    Index expressions carry noise: sort direction (``priority DESC``), an operator class
    (``context jsonb_path_ops``) and function calls (``coalesce(scope_id, '')``). Rather than
    teach this script a SQL parser, keep only the identifiers that are real columns of the
    table being indexed -- the noise is precisely what is left over.
    """
    known = set(db.Base.metadata.tables[table_name].c.keys())
    seen: set[str] = set()
    ordered: list[str] = []
    for identifier in _IDENT.findall(expression):
        name = identifier.lower()
        if name in known and name not in seen:
            seen.add(name)
            ordered.append(name)
    return tuple(sorted(ordered))


def sql_indexes() -> dict:
    """Every index the reference DDL declares, for tables the models know about."""
    found: dict = {}
    for path in sorted(MIGRATIONS.glob('*.sql')):
        source = path.read_text(encoding='utf-8', errors='replace')
        for match in _CREATE_INDEX.finditer(source):
            table = match.group('table').strip('"')
            if table not in db.Base.metadata.tables:
                continue
            columns = _column_names(table, match.group('columns'))
            if not columns:
                continue
            found[(table, columns, bool(match.group('unique')))] = (
                match.group('name').strip('"'), path.name)
    return found


def orm_indexes() -> dict:
    """Every index and UNIQUE constraint the models declare.

    ``unique=True`` on a column produces a ``UniqueConstraint``, not an ``Index``, so reading
    ``Table.indexes`` alone would report every natural key as missing.
    """
    found: dict = {}
    for table in db.Base.metadata.tables.values():
        for index in table.indexes:
            columns = tuple(sorted(column.name for column in index.columns if column.name))
            if columns:
                found[(table.name, columns, bool(index.unique))] = index.name
        for constraint in table.constraints:
            if isinstance(constraint, UniqueConstraint):
                columns = tuple(sorted(column.name for column in constraint.columns if column.name))
                if columns:
                    found.setdefault((table.name, columns, True),
                                     constraint.name or f'{table.name}:unique')
    return found


def _describe(key) -> str:
    table, columns, unique = key
    return f'  {"UNIQUE " if unique else ""}{table} ({", ".join(columns)})'


def main(argv: list[str]) -> int:
    check = '--check' in argv
    reference = sql_indexes()
    declared = orm_indexes()

    missing = sorted(key for key in reference
                     if key not in declared and key not in INTENTIONAL_SQL_ONLY)
    extra = sorted(key for key in declared if key not in reference)
    skipped = sorted(key for key in reference if key in INTENTIONAL_SQL_ONLY)

    print(f'reference DDL indexes: {len(reference)}    '
          f'ORM indexes: {len(declared)}    BETA_INDEXES: {len(db.BETA_INDEXES)}')
    print()

    if missing:
        print(f'DRIFT -- declared by migrations/*.sql, absent from the ORM ({len(missing)}):')
        for key in missing:
            print(_describe(key))
        print()
        print('  A database built by scripts/init_db.py will not have these. Add them to')
        print('  BETA_INDEXES in app/db.py, or list them in INTENTIONAL_SQL_ONLY with a reason.')
    else:
        print('OK -- every index the reference DDL declares is also declared by the ORM.')

    if skipped:
        print()
        print(f'intentionally SQL-only ({len(skipped)}):')
        for key in skipped:
            print(_describe(key))
            print(f'    reason: {INTENTIONAL_SQL_ONLY[key]}')

    if extra:
        print()
        print(f'information -- declared by the ORM but not by any migration ({len(extra)}).')
        print('  Expected for v1-v3 tables whose inline UNIQUE constraints this scan does not')
        print('  parse. Anything on a v4+ table is worth a second look:')
        for key in extra[:12]:
            print(_describe(key))
        if len(extra) > 12:
            print(f'  ... and {len(extra) - 12} more')

    print()
    if check and missing:
        print('FAIL: the two build paths disagree.')
        return 1
    print('PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
