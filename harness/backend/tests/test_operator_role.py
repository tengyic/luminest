"""Who may teach on this instance.

``User.role`` defaults to ``learner``. That is correct for a classroom and wrong for
the desktop app: there the person who installed it is the only account, and a learner
role fail-closes every teaching tool - ``whiteboard_*``, ``find_game``,
``search_videos``, ``browser_snapshot``, ``write_simulation``. The tutor is told "the
whiteboard is the classroom, teach on it" and then refused on every stroke, which
reads as a broken app rather than a permission boundary.

``main._ensure_operator`` and the first-registration branch fix that, scoped to
``development``: a hosted (``production``) deployment sets roles deliberately and must
never hand the instance to whoever signed up first. These tests pin both halves of
that rule - the promotion happens locally, and it cannot happen in production.
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import User
from app.main import _ensure_operator, create_app


@pytest.fixture
def dev(tmp_path, monkeypatch):
    """A local (development) instance with its own database."""
    monkeypatch.setenv('HARNESS_ENV', 'development')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.delenv('HARNESS_TUTOR_PROVIDER', raising=False)
    app = create_app(Settings.from_env())
    with TestClient(app) as client:
        yield app, client


def _add(app, email, role='learner'):
    with app.state.factory() as db:
        user = User(name=email.split('@')[0], email=email, password_hash='x', role=role)
        db.add(user)
        db.commit()
        return user.id


def _role(app, user_id):
    with app.state.factory() as db:
        return str(db.get(User, user_id).role)


def test_a_local_instance_promotes_its_only_learner_to_teacher(dev):
    """The desktop operator is the learner. Without this, the tutor cannot draw."""
    app, _ = dev
    user_id = _add(app, 'owner@local.test')
    with app.state.factory() as db:
        assert _ensure_operator(db, app.state.settings) is True
    assert _role(app, user_id) == 'teacher'
    # Idempotent: a second call changes nothing and reports no promotion.
    with app.state.factory() as db:
        assert _ensure_operator(db, app.state.settings) is False


def test_production_never_promotes_anybody(dev):
    """A hosted instance assigns roles deliberately; first signup must not own it."""
    app, _ = dev
    user_id = _add(app, 'first@hosted.test')
    with app.state.factory() as db:
        assert _ensure_operator(db, SimpleNamespace(environment='production')) is False
    assert _role(app, user_id) == 'learner'


def test_a_local_instance_leaves_an_existing_teacher_alone(dev):
    """The promotion fills a gap; it never demotes or second-guesses a real role."""
    app, _ = dev
    teacher_id = _add(app, 'teacher@local.test', role='teacher')
    learner_id = _add(app, 'learner@local.test')
    with app.state.factory() as db:
        assert _ensure_operator(db, app.state.settings) is False
    assert _role(app, teacher_id) == 'teacher'
    assert _role(app, learner_id) == 'learner'


def test_the_first_account_on_a_local_instance_registers_as_teacher(dev):
    """A fresh desktop install has no account to promote at boot, so the first
    registration must arrive able to teach. Later accounts stay learners."""
    _, client = dev
    first = client.post('/api/v1/auth/register', json={
        'name': 'Owner', 'email': 'owner@local.test', 'password': 'long-secret-password'})
    assert first.status_code == 201, first.text
    assert first.json()['user']['role'] == 'teacher'
    second = client.post('/api/v1/auth/register', json={
        'name': 'Friend', 'email': 'friend@local.test', 'password': 'long-secret-password'})
    assert second.status_code == 201, second.text
    assert second.json()['user']['role'] == 'learner'
