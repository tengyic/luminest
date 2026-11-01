"""Tests for the user-scope isolation guard (app.user_scope).

The guard is the multi-tenant safety baseline: a select on a user-scoped table
without a ``user_id`` (or primary-key) predicate must not execute. These tests
deliberately construct the query a careless endpoint would write and assert it
*raises*, then assert the legitimate paths still work -- and that every escape
hatch use is audited.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import State, User, make_database
from app.main import create_app
from app.user_scope import (USER_SCOPED_TABLES, UnsafeQueryError, clear_unscoped_events,
                            install, installed, unscoped, unscoped_events)
from test_api import account, settings, client  # noqa: F401


def _two_users_with_states(app):
    """Two learners, each with their own learning state row for the same concept."""
    factory = app.state.factory
    with factory() as db:
        alice = User(name='alice', email='alice@scope.test', password_hash='x')
        bob = User(name='bob', email='bob@scope.test', password_hash='x')
        db.add_all([alice, bob])
        db.flush()
        db.add(State(user_id=alice.id, concept_id='fractions', data={'mastery': 0.9}))
        db.add(State(user_id=bob.id, concept_id='fractions', data={'mastery': 0.1}))
        db.commit()
        return alice.id, bob.id


def test_guard_is_installed(create_app_unused=None):
    assert installed(), 'the user-scope guard must be installed app-wide'
    # create_app -> make_database installs it; installing twice is a no-op.
    install()
    assert installed()


def test_unscoped_select_on_user_scoped_table_raises(settings):
    app = create_app(settings)
    with TestClient(app):
        _two_users_with_states(app)
        with app.state.factory() as db:
            # Exactly the query a forgotten user_id filter produces.
            with pytest.raises(UnsafeQueryError) as exc:
                list(db.scalars(select(State).where(State.concept_id == 'fractions')))
            assert 'learning_states' in str(exc.value)
            assert 'user_id' in str(exc.value)


def test_unscoped_select_without_any_where_raises(settings):
    app = create_app(settings)
    with TestClient(app):
        _two_users_with_states(app)
        with app.state.factory() as db:
            with pytest.raises(UnsafeQueryError):
                db.execute(select(State.concept_id, State.user_id).group_by(State.concept_id, State.user_id)).all()


def test_user_scoped_predicate_still_works_and_isolates(settings):
    app = create_app(settings)
    with TestClient(app):
        alice_id, bob_id = _two_users_with_states(app)
        with app.state.factory() as db:
            alice_rows = db.scalars(select(State).where(State.user_id == alice_id)).all()
            bob_rows = db.scalars(select(State).where(State.user_id == bob_id)).all()
        assert [row.data['mastery'] for row in alice_rows] == [0.9]
        assert [row.data['mastery'] for row in bob_rows] == [0.1]


def test_primary_key_lookup_is_allowed(settings):
    app = create_app(settings)
    with TestClient(app):
        alice_id, _ = _two_users_with_states(app)
        with app.state.factory() as db:
            row = db.scalar(select(State).where(State.user_id == alice_id))
            state_id = row.id
        with app.state.factory() as db:
            # An unguessable primary key is a legitimate scope.
            assert db.get(State, state_id).user_id == alice_id


def test_escape_hatch_runs_and_is_audited(settings):
    app = create_app(settings)
    with TestClient(app):
        _two_users_with_states(app)
        clear_unscoped_events()
        with app.state.factory() as db:
            with unscoped('operator export for a support ticket'):
                rows = db.scalars(select(State).where(State.concept_id == 'fractions')).all()
        assert len(rows) == 2
        events = unscoped_events()
        assert len(events) == 1
        assert events[0][1] == 'operator export for a support ticket'
        assert 'learning_states' in events[0][2]


def test_escape_hatch_requires_a_reason():
    with pytest.raises(ValueError):
        unscoped('   ')
    with pytest.raises(ValueError):
        unscoped('')


def test_guard_covers_the_whole_user_scoped_surface(settings):
    """Every guarded table name must actually exist in the schema.

    A renamed or dropped table in this list would silently stop being protected.
    """
    from app.db import Base
    real = set(Base.metadata.tables)
    missing = USER_SCOPED_TABLES - real
    assert not missing, f'USER_SCOPED_TABLES names tables that no longer exist: {sorted(missing)}'


def test_live_api_traffic_runs_under_the_guard(client):
    """The normal authenticated API path keeps working end to end."""
    headers, value = account(client)
    q = client.get('/api/v1/questions/next', headers=headers, params={'mode': 'practice'}).json()
    payload = {'question_id': q['id'], 'option_id': None, 'receipt': q['receipt'],
               'client_event_id': 'scope-smoke-1', 'elapsed_seconds': 1.0}
    # Not answered correctly -- the point is the read path, not the grade.
    assert client.post('/api/v1/attempts', headers=headers, json=payload).status_code in (200, 422)
    assert client.get('/api/v1/dashboard', headers=headers).status_code == 200
    assert value['user']['status'] == 'active'
