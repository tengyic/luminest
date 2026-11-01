"""User-scope isolation guard: the multi-tenant safety baseline.

The product is multi-tenant from the first hosted Beta user onward, yet until this
module nothing *structural* stopped a query on user-owned tables from returning
another learner's rows. The only protection was the convention that every route
reaches for ``own_rows()`` -- a convention, not a constraint. One forgotten
``user_id`` filter in a new endpoint would leak learner data silently, and no test
would fail.

The guard turns the convention into a constraint. It hooks SQLAlchemy's
``do_orm_execute`` event and enforces one rule on every ORM ``SELECT``:

    A select that reads a user-scoped table must be restricted to that table's
    ``user_id`` column, or to the table's primary key (an unguessable row id),
    or it must run inside an explicit, audited ``unscoped()`` escape hatch.

What counts as user-scoped is a fixed, reviewed list of table *names* in
:data:`USER_SCOPED_TABLES` -- every table whose rows exist per learner and whose
``user_id`` is ``NOT NULL``. Tables with a nullable ``user_id`` (``feedback``,
``usage_ledger`` -- an unauthenticated waitlist visitor may create feedback, and a
provider call may precede authentication) and tables where the user reference is
not a partition key (``feedback_events`` / ``admin_audit_log`` ``actor_user_id``)
are deliberately excluded and say so here, so the list is a decision rather than
an accident.

Three deliberate allowances, each reasoned:

* **Primary-key lookups** (``db.get(Token, digest)``): the predicate is the row's
  primary key -- a SHA-256 digest of a secret or a random UUID. It cannot be
  guessed, so it cannot leak a stranger's row. Requiring ``user_id`` on these
  would force every credential check to run two lookups for no safety gain.
* **``unscoped()`` escape hatch**: some reads are cross-user *by design* (global
  question-difficulty calibration) or are keyed by something other than
  ``user_id`` (revoking a whole session by ``session_digest``). The hatch never
  silently permits: it requires a reason string, logs a warning, and appends to
  :func:`unscoped_events`, which tests and the audit tooling assert on.
* **Non-ORM statements** (``text()``, DDL, migrations) and writes are not
  inspected. This is a *read* guard: writes are bounded by foreign keys and by
  the same code review, and guarding them here would double the surface without
  a matching threat.

The hook installs on the ``Session`` class the first time ``app.db`` is imported,
so every session in the API, the scripts and the tests runs under the same rule.
A query that violates it raises :class:`UnsafeQueryError` -- loudly, in
development and production alike. A 500 on an unscoped query is the guard
working; the fix is to add the ``user_id`` predicate or take the audited hatch.
"""
from __future__ import annotations

import contextvars
import logging
import time
from collections import deque

from sqlalchemy import Select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import BinaryExpression
from sqlalchemy.sql.schema import Table
from sqlalchemy.sql.visitors import traverse

log = logging.getLogger('luminfest.user_scope')

#: Tables whose rows belong to exactly one learner. ``user_id`` is NOT NULL on
#: every one of them and each row is meaningless outside its user. Keep this list
#: in step with ``app.db``: adding a user-owned table without listing it here
#: recreates the leak this guard exists to close.
USER_SCOPED_TABLES: frozenset[str] = frozenset({
    'tokens',                      # sessions
    'refresh_tokens',              # refresh credential chain
    'auth_tokens',                 # single-use verify/reset tokens
    'learning_states',             # per-concept mastery state
    'flashcards',                  # per-learner card deck (v9)
    'assessments',
    'receipts',                    # question leases
    'attempts',
    'messages',                    # tutor chat
    'projects',
    'telemetry_events',
    'memory_notes',
    'harness_runs',
    'training_consent_ledger',
    'consent_ledger',
    'user_preferences',            # PK is user_id
    'teacher_style_profiles',
    'invite_redemptions',
    'quota_counters',
    'experiment_assignments',
    'experiment_exposures',
    'usage_daily_rollup',          # PK includes user_id
})

#: Deliberately NOT guarded (see module docstring): ``feedback`` and
#: ``usage_ledger`` have a nullable ``user_id``; ``feedback_events`` and
#: ``admin_audit_log`` carry ``actor_user_id`` as accountability metadata, not a
#: partition key; ``users``, ``cohorts``, ``beta_invites``, ``waitlist_signups``
#: and the rest are operator/admin domain tables.


class UnsafeQueryError(RuntimeError):
    """A select on a user-scoped table ran without a user-scoping predicate."""


_current_reason: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    'luminfest_unscoped_reason', default=None)

#: Process-local audit trail of every query allowed through the escape hatch.
#: ``unscoped()`` appends ``(epoch, reason, tables)``; tests assert on it and a
#: production deployment should ship it to the admin audit log.
_AUDIT: deque[tuple[float, str, tuple[str, ...]]] = deque(maxlen=1000)


class unscoped:
    """Explicitly allow cross-user reads of user-scoped tables, audited.

    Usage: ``with unscoped('global question calibration pooling'):``
    The reason is mandatory and is what makes the hatch reviewable: a code
    reviewer sees every place that deliberately reads across users, and the
    audit trail records every time one actually ran.
    """

    def __init__(self, reason: str):
        if not reason or not reason.strip():
            raise ValueError('unscoped() requires a non-empty reason')
        self.reason = reason.strip()

    def __enter__(self) -> 'unscoped':
        self._token = _current_reason.set(self.reason)
        return self

    def __exit__(self, *_exc) -> None:
        _current_reason.reset(self._token)


def unscoped_events() -> list[tuple[float, str, tuple[str, ...]]]:
    """A copy of the escape-hatch audit trail (oldest first)."""
    return list(_AUDIT)


def clear_unscoped_events() -> None:
    _AUDIT.clear()


def _tables_in(statement: Select) -> set[str]:
    """Every concrete table the select reads, including joins and ``select_from``."""
    names: set[str] = set()

    def visit_column(column):
        table = getattr(column, 'table', None)
        if isinstance(table, Table):
            names.add(table.name)

    def visit_table(table):
        if isinstance(table, Table):
            names.add(table.name)

    traverse(statement, {}, {'column': visit_column, 'table': visit_table})
    return names


def _scoped_by_predicate(statement: Select, tables: set[str]) -> bool:
    """True when every listed table is constrained by a user_id or PK predicate."""
    if statement.whereclause is None:
        return False
    covered: set[str] = set()

    # ``traverse`` with a 'binary' visitor; each BinaryExpression is inspected for
    # a bare Column comparison naming user_id or the table's primary key.
    def check(binary):
        for side in (binary.left, binary.right):
            table = getattr(side, 'table', None)
            if not isinstance(table, Table):
                continue
            if side.name == 'user_id' or getattr(side, 'primary_key', False):
                covered.add(table.name)

    traverse(statement.whereclause, {}, {'binary': check})
    return tables <= covered


def _guard_execute(orm_context):
    if not orm_context.is_select:
        return
    statement = orm_context.statement
    if not isinstance(statement, Select):
        return  # text() and friends are out of scope: this guards ORM reads.
    reason = _current_reason.get()
    tables = _tables_in(statement) & USER_SCOPED_TABLES
    if not tables:
        return
    if reason is not None:
        _AUDIT.append((time.time(), reason, tuple(sorted(tables))))
        log.warning('unscoped read of %s permitted: %s', ', '.join(sorted(tables)), reason)
        return
    if _scoped_by_predicate(statement, tables):
        return
    raise UnsafeQueryError(
        'SELECT on user-scoped table(s) %s without a user_id or primary-key '
        'predicate. Add the predicate (e.g. .where(cls.user_id == user.id)) or '
        'wrap the read in user_scope.unscoped(reason) if it is cross-user by '
        'design.' % ', '.join(sorted(tables)))


_INSTALLED = False


def install() -> None:
    """Attach the guard to the ORM ``Session`` class, once per process."""
    global _INSTALLED
    if _INSTALLED:
        return
    from sqlalchemy import event
    event.listen(Session, 'do_orm_execute', _guard_execute)
    _INSTALLED = True


def installed() -> bool:
    return _INSTALLED
