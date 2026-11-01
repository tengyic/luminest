"""The playground: the template contract, the bundled content, and the evidence path.

The tests here are written against the *rules* the playground claims to follow, not
against whatever it currently happens to produce. The ones that matter most are:

* every bundled game renders a page the artifact store accepts, because a game that
  cannot be stored cannot be played, and the failure would otherwise be discovered by
  a learner;
* no page can reach the network or evaluate dynamic code, because a lesson that phones
  home is a privacy defect and the store's validator is the only thing standing between
  a generated page and a learner's browser;
* a run moves mastery only when its concept is attributable, because the alternative is
  silently crediting the wrong concept.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import courses, feature_routers
from app.config import Settings
from app.harness import sims_store
from app.harness.playground import (all_archetypes, catalogue, evidence, get, pipeline,
                                    render, validate_spec)


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'offline')
    return Settings.from_env()


@pytest.fixture
def learner(settings):
    from app.main import create_app
    with TestClient(create_app(settings)) as client:
        body = client.post('/api/v1/auth/register', json={
            'name': 'Playground Tester', 'email': 'play@example.com',
            'password': 'correct-horse-battery'}).json()
        yield client, body['token']


# ------------------------------------------------------------------ the catalogue


def test_the_playground_ships_at_least_twenty_games():
    """The stated bar. A number in a README is not the same as a number in the pack."""
    games = catalogue.all_games()
    assert len(games) >= 20, f'only {len(games)} games are bundled'


def test_the_bundled_games_span_several_subjects():
    """A maths-only playground would not meet the brief, so it is asserted, not assumed."""
    subjects = set(catalogue.subjects())
    for expected in ('mathematics', 'science', 'economics'):
        assert expected in subjects, f'{expected} has no games; found {sorted(subjects)}'


def test_no_bundled_game_is_withheld():
    """A withheld game is a content bug. This is the test that catches it at build time.

    The catalogue publishes withheld entries rather than dropping them precisely so
    that this assertion can exist: without it, a typo in one spec would silently reduce
    the gallery and nobody would notice until a learner asked where the game went.
    """
    withheld = catalogue.withheld()
    assert not withheld, '\n'.join(f'{row["slug"]}: {row["reason"]}' for row in withheld)


def test_every_game_names_a_registered_archetype():
    for game in catalogue.all_games():
        assert get(str(game['archetype'])) is not None, game['slug']


def test_every_game_declares_an_objective_and_a_prompt():
    """A game with no stated objective cannot be scheduled, and one with no prompt
    cannot be played. Both are cheap to assert and easy to omit when authoring."""
    for game in catalogue.all_games():
        assert str(game['learning_objective']).strip(), game['slug']
        assert len(str(game['prompt']).strip()) >= 15, game['slug']


def test_archetype_ids_are_unique_and_registration_is_guarded():
    ids = [a.id for a in all_archetypes()]
    assert len(ids) == len(set(ids))
    with pytest.raises(ValueError):
        from app.harness.playground import register
        register(all_archetypes()[0])


# ---------------------------------------------------------------- rendered pages


def test_every_bundled_game_renders_a_page_the_store_accepts():
    """The end-to-end content test: spec -> page -> the validator that guards storage."""
    failures = []
    for game in catalogue.all_games():
        archetype = get(str(game['archetype']))
        try:
            page = render(archetype, game['spec'], title=game['title'],
                          instruction=game['prompt'])
        except ValueError as exc:
            failures.append(f'{game["slug"]}: render refused: {exc}')
            continue
        problems = sims_store.validate_html(page, kind='simulation')
        if problems:
            failures.append(f'{game["slug"]}: {" | ".join(problems)}')
    assert not failures, '\n'.join(failures)


def test_a_page_is_deterministic_for_one_spec():
    """The same spec must render byte-identically, or the artifact store would mint a
    new version on every request and 'the same game' would mean nothing."""
    game = catalogue.all_games()[0]
    archetype = get(str(game['archetype']))
    first = render(archetype, game['spec'])
    second = render(archetype, game['spec'])
    assert first == second
    assert pipeline.spec_hash(archetype.id, game['spec']) == \
        pipeline.spec_hash(archetype.id, dict(reversed(list(game['spec'].items()))))


def test_no_page_can_load_anything_from_the_network():
    """Self-containment is a privacy property, not a packaging preference."""
    for game in catalogue.all_games():
        page = render(get(str(game['archetype'])), game['spec'])
        for forbidden in ('<script src=', '<link rel="stylesheet"', 'fetch("http',
                          'fetch(\'http', 'XMLHttpRequest', 'WebSocket', 'EventSource',
                          '@import url(http'):
            assert forbidden not in page, f'{game["slug"]} contains {forbidden!r}'


def test_no_page_uses_dynamic_code_evaluation():
    """A generated page is data-driven by construction. Anything that compiles a string
    is either a bug or an attempt to get round the store's validator."""
    for game in catalogue.all_games():
        page = render(get(str(game['archetype'])), game['spec'])
        assert 'eval(' not in page, game['slug']
        assert 'new Function' not in page, game['slug']
        assert 'Function(' not in page.replace('function (', ''), game['slug']


def test_every_page_carries_the_series_convention_and_the_bridge():
    """The workbench's hover-to-inspect convention and the outcome bridge are what make
    a page part of the product rather than a standalone web page."""
    for game in catalogue.all_games():
        page = render(get(str(game['archetype'])), game['spec'])
        assert 'data-series' in page, game['slug']
        assert 'luminfest:outcome' in page, game['slug']
        assert 'luminfest:readout' in page, game['slug']


def test_a_scored_game_offers_a_way_to_commit_an_answer():
    """A scored archetype that never posts an outcome would be a sandbox wearing a
    score, so every scored game's page must contain the call that reports one."""
    for game in catalogue.all_games():
        archetype = get(str(game['archetype']))
        if not archetype.scored:
            continue
        page = render(archetype, game['spec'])
        assert 'UI.score(' in page or 'BRIDGE.outcome(' in page, game['slug']


def test_no_page_calls_a_runtime_helper_that_does_not_exist():
    """The bug this test exists for, found in review rather than by a learner.

    An earlier revision of the reference archetype called ``UI.outcome(...)``. No such
    method exists - the runtime exposes ``BRIDGE.outcome`` and ``UI.score`` - so every
    game built from it rendered perfectly and threw the instant a learner pressed
    Check. Byte-level checks cannot see that; this one can, because it compares the
    calls a page makes against the helpers the runtime actually defines.
    """
    from app.harness.playground import runtime
    # The helpers the runtime *defines* are the ``name: function`` members of its UI
    # and BRIDGE objects. Scanning for helper *calls* instead - the previous form -
    # only ever found the helpers the runtime happens to call itself, so 'readout',
    # which the runtime defines and every archetype uses, was absent from the set and
    # the assertion below could never hold.
    defined = set(re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*:\s*function\b',
                             runtime.RUNTIME_JS))
    assert defined, 'the runtime defines no helpers; the scan below would be vacuous'
    assert {'outcome', 'readout'} <= defined, sorted(defined)

    offenders = []
    for game in catalogue.all_games():
        page = render(get(str(game['archetype'])), game['spec'])
        script = page.rsplit('<script>', 1)[-1]
        for helper in re.findall(r'\b(UI|BRIDGE)\.([A-Za-z_][A-Za-z0-9_]*)\s*\(', script):
            if helper[1] not in defined:
                offenders.append(f'{game["slug"]}: {helper[0]}.{helper[1]}()')
    assert not offenders, 'pages call helpers the runtime does not define:\n' + \
        '\n'.join(sorted(set(offenders)))


# ------------------------------------------------------- headless behaviour


def _node_binary():
    import shutil
    found = shutil.which('node')
    if found:
        return found
    for candidate in ('/Users/tengyi/.workbuddy-ai/binaries/node/versions/22.22.2-6/bin/node',
                      '/usr/local/bin/node', '/opt/homebrew/bin/node'):
        if Path(candidate).exists():
            return candidate
    return None


def test_every_game_survives_a_headless_click_and_drag(tmp_path):
    """Execute every rendered page, against the driver that can speak to each claim.

    Two drivers run the games and neither can answer the other's question:

    * ``playground_dom_smoke.js`` answers "does it run?". It loads the page in a stub DOM,
      runs ``build()``, and fires every handler the page registered. That catches a page
      that throws on load or inside a handler - which the byte-level tests cannot see -
      and that is all it claims to do. It deliberately knows no archetype's geometry, so
      it cannot know the right answer and must not be asked to.
    * ``playground_verify.mjs`` answers "does it behave like a scored game?" - no outcome
      on load, none while exploring, exactly one per Check, a give-up flagged as wrong.
      It already reports the cases it *cannot* test as ``undriven`` rather than as
      failures, and it honours ``commits_on`` (an archetype that commits on completion,
      not on Check, is not a bug). Its own ``SUMMARY`` is therefore the authority on what
      counts as broken; this test reads that summary and does not re-implement the rules.

    Keeping the assertions apart is the point. An earlier revision asked the smoke driver
    to prove a scored game *commits*; no blind driver can do that for a geometry-bound
    archetype, so the assertion was unachievable and only ever reported itself as a
    failure. Crash-freedom and behaviour are different claims, tested by the tools built
    to test them.
    """
    node = _node_binary()
    if node is None:
        pytest.skip('node is not available, so the pages cannot be executed')
    scripts = Path(__file__).resolve().parents[2] / 'scripts'
    smoke = scripts / 'playground_dom_smoke.js'
    verifier = scripts / 'playground_verify.mjs'
    producer = scripts / 'playground_render_pages.py'
    for script in (smoke, verifier, producer):
        assert script.exists(), f'missing script: {script}'

    import subprocess

    # The smoke driver takes HTML files, so render each game the way the catalogue serves
    # it. The verifier instead takes a JSON bundle - produced below by its sibling script.
    pages = []
    for game in catalogue.all_games():
        page = render(get(str(game['archetype'])), game['spec'],
                      title=game['title'], instruction=game['prompt'])
        target = tmp_path / f'{game["slug"]}.html'
        target.write_text(page, encoding='utf-8')
        pages.append(target)

    # --- crash-freedom: does every page load and every handler survive a blind gesture? ---
    completed = subprocess.run([node, str(smoke)] + [str(p) for p in pages],
                               capture_output=True, text=True, timeout=180)
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    summary = next((line for line in reversed(lines) if line.startswith('SUMMARY ')), None)
    assert summary, f'the smoke driver produced no summary.\nstdout:\n{completed.stdout}\n' \
                    f'stderr:\n{completed.stderr}'
    report = json.loads(summary[len('SUMMARY '):])
    assert report['files'] == len(pages)
    if report['failed']:
        broken = [json.loads(line) for line in lines if not line.startswith('SUMMARY ')]
        detail = '\n'.join(
            f'{row["file"]}: {row.get("load_error") or row.get("handler_errors")}'
            for row in broken if not row['ok'])
        pytest.fail(f'{report["failed"]} game(s) threw on load or in a handler:\n{detail}')

    # --- behaviour: the verifier, whose input the producer renders from the real catalogue
    # (the verifier itself renders nothing, so it cannot special-case a game it helped build).
    bundle = tmp_path / 'pages.json'
    produced = subprocess.run([sys.executable, str(producer), str(bundle)],
                              capture_output=True, text=True, timeout=180)
    assert produced.returncode == 0 and bundle.exists(), \
        f'render_pages failed.\nstdout:\n{produced.stdout}\nstderr:\n{produced.stderr}'
    verified = subprocess.run([node, str(verifier), str(bundle)],
                              capture_output=True, text=True, timeout=600)
    vlines = [line for line in verified.stdout.splitlines() if line.strip()]
    vsummary = next((line for line in reversed(vlines) if line.startswith('SUMMARY ')), None)
    assert vsummary, f'the verifier produced no summary.\nstdout:\n{verified.stdout}\n' \
                     f'stderr:\n{verified.stderr}'
    vreport = json.loads(vsummary[len('SUMMARY '):])
    assert vreport['files'] == len(pages)
    if vreport['failed']:
        rows = [json.loads(line) for line in vlines if not line.startswith('SUMMARY ')]
        detail = '\n'.join(
            f'{row["slug"]} [{row["archetype"]}]: '
            f'{row.get("load_error") or row.get("notes")}'
            for row in rows if not row['ok'])
        pytest.fail(f'{vreport["failed"]} game(s) broke a behavioural contract:\n{detail}')


# ------------------------------------------------------------------- validation


def test_validation_names_the_field_and_the_bound():
    archetype = get('curve_shift')
    spec = {'title': 'x', 'instruction': 'y', 'x_max': -1, 'y_max': 10,
            'curves': [], 'shocks': []}
    problems = validate_spec(spec, archetype)
    joined = ' | '.join(problems)
    assert 'x_max must be at least 1' in joined
    assert 'curves needs at least 2' in joined
    assert 'shocks needs at least 1' in joined


def test_validation_refuses_a_value_outside_a_declared_vocabulary():
    """'sideways' is not a direction. Catching it here is the difference between a
    refused spec and a game whose correct answer can never be reached."""
    archetype = get('curve_shift')
    spec = {'title': 'x', 'instruction': 'y', 'x_max': 10, 'y_max': 10,
            'curves': [{'id': 'd', 'label': 'D', 'colour': 'a', 'intercept': 10,
                        'slope': -1, 'shifts': True},
                       {'id': 's', 'label': 'S', 'colour': 'b', 'intercept': 0,
                        'slope': 1, 'shifts': False}],
            'shocks': [{'id': 'k', 'text': 't', 'shift': 'd', 'direction': 'sideways',
                        'price': 'up', 'quantity': 'up'}]}
    problems = validate_spec(spec, archetype)
    assert any("must be one of ['left', 'right']" in p for p in problems), problems


def test_validation_refuses_a_field_the_schema_does_not_declare():
    archetype = get('curve_shift')
    problems = validate_spec({'title': 'x', 'instruction': 'y', 'x_max': 10, 'y_max': 10,
                              'curves': [], 'shocks': [], 'nonsense': 1}, archetype)
    assert any("'nonsense' is not part of" in p for p in problems), problems


def test_an_invalid_game_is_withheld_with_its_reason(tmp_path, monkeypatch):
    """The catalogue's failure mode must be visible, not silent."""
    (tmp_path / 'playground_games_zz.json').write_text(json.dumps([{
        'slug': 'zz-broken', 'archetype': 'curve_shift', 'title': 'Broken',
        'course_id': 'physics', 'concept': 'x', 'prompt': 'p',
        'learning_objective': 'o', 'subjects': ['science'],
        'spec': {'title': 'x', 'instruction': 'y', 'x_max': -5, 'y_max': 1,
                 'curves': [], 'shocks': []}}]), encoding='utf-8')
    monkeypatch.setattr(catalogue, 'PACK_DIR', tmp_path)
    catalogue.refresh()
    try:
        slugs = {row['slug'] for row in catalogue.withheld()}
        assert 'zz-broken' in slugs
        row = next(r for r in catalogue.withheld() if r['slug'] == 'zz-broken')
        assert 'x_max must be at least 1' in row['reason']
        assert all(g['slug'] != 'zz-broken' for g in catalogue.all_games())
    finally:
        monkeypatch.undo()
        catalogue.refresh()


def test_an_unknown_archetype_is_withheld_rather_than_dropped(tmp_path, monkeypatch):
    (tmp_path / 'playground_games_zz.json').write_text(json.dumps([{
        'slug': 'zz-nosuch', 'archetype': 'not_an_archetype', 'title': 'X',
        'course_id': 'physics', 'concept': 'x', 'prompt': 'p',
        'learning_objective': 'o', 'subjects': ['science'], 'spec': {}}]), encoding='utf-8')
    monkeypatch.setattr(catalogue, 'PACK_DIR', tmp_path)
    catalogue.refresh()
    try:
        row = next(r for r in catalogue.withheld() if r['slug'] == 'zz-nosuch')
        assert 'unknown archetype' in row['reason']
    finally:
        monkeypatch.undo()
        catalogue.refresh()


# --------------------------------------------------------------------- pipeline


def test_compose_stores_a_game_and_reuses_it_for_the_same_revision(settings):
    """Idempotence is what stops a replay filling the store with identical copies."""
    game = catalogue.all_games()[0]
    first = pipeline.compose(settings, archetype_id=str(game['archetype']),
                             spec=game['spec'], title='Idempotence probe',
                             slug='test-idempotent')
    second = pipeline.compose(settings, archetype_id=str(game['archetype']),
                              spec=game['spec'], title='Idempotence probe',
                              slug='test-idempotent')
    assert first['reused'] is False
    assert second['reused'] is True
    assert first['id'] == second['id']
    assert first['raw_url'].endswith(f'/{first["id"]}/raw')
    stored = sims_store.latest_html(settings, first['id'])
    assert stored and 'data-series' in stored


def test_compose_refuses_a_spec_that_does_not_match_the_schema(settings):
    with pytest.raises(ValueError) as caught:
        pipeline.compose(settings, archetype_id='curve_shift', spec={'title': 'only'})
    assert 'schema' in str(caught.value)
    assert not [a for a in sims_store.list_artifacts(settings, kind='simulation')]


def test_instantiate_is_idempotent_and_serves_the_same_revision(settings):
    game = catalogue.all_games()[0]
    first = pipeline.instantiate(settings, str(game['slug']))
    second = pipeline.instantiate(settings, str(game['slug']))
    assert second['reused'] is True
    assert first['id'] == second['id']


def test_draft_without_a_model_stores_nothing_and_says_so(settings):
    """'No model is configured' is an ordinary outcome, not a crash, and it must not
    leave a half-built game behind."""
    result = pipeline.draft(settings, archetype_id='curve_shift',
                            topic='anything at all', course_id='physics')
    assert result['ok'] is False
    assert result['stage'] == 'provider'
    assert 'No language model is configured' in result['problems'][0]
    assert not [a for a in sims_store.list_artifacts(settings, kind='simulation')]


def test_draft_refuses_an_unknown_archetype_before_asking_a_model(settings):
    result = pipeline.draft(settings, archetype_id='not_real', topic='anything')
    assert result['ok'] is False and result['stage'] == 'lookup'


# --------------------------------------------------------------------- evidence


def _concepts_for(course_id: str):
    from app.curriculum import course_concepts
    return course_concepts(course_id)


@pytest.fixture
def db(settings):
    """A session against the same database the ``learner`` fixture registered into."""
    from app.db import Base, make_database
    engine, factory = make_database(settings)
    Base.metadata.create_all(engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def user_row(db):
    from sqlalchemy import select
    from app.db import User
    row = db.scalar(select(User).where(User.email == 'play@example.com'))
    assert row is not None, 'the learner fixture must run before this'
    return row


def test_attribution_prefers_an_explicit_concept_id():
    concepts = _concepts_for(courses.DEFAULT_COURSE_ID)
    if not concepts:
        pytest.skip('default course has no authored concepts')
    concept_id = sorted(concepts)[0]
    resolved, why = evidence.resolve_concept({'concept_id': concept_id}, concepts)
    assert resolved == concept_id
    assert 'explicitly' in why


def test_attribution_refuses_a_game_whose_concept_is_not_in_the_course():
    """The case that matters: a physics game played by an algebra learner."""
    concepts = _concepts_for(courses.DEFAULT_COURSE_ID)
    resolved, why = evidence.resolve_concept(
        {'concept': 'The Krebs cycle and oxidative phosphorylation'}, concepts)
    assert resolved is None
    assert 'does not move mastery' in why


def test_attribution_matches_an_exact_title():
    concepts = _concepts_for(courses.DEFAULT_COURSE_ID)
    if not concepts:
        pytest.skip('default course has no authored concepts')
    concept_id, entry = sorted(concepts.items())[0]
    resolved, why = evidence.resolve_concept({'concept': entry['title']}, concepts)
    assert resolved == concept_id
    assert 'exact title match' in why


def test_a_run_moves_mastery_and_records_the_before_and_after(learner, db, user_row):
    """The claim 'playground play counts' has to be checkable in the database.

    ``mastery_before`` is deliberately ``None`` on the first observation, and
    ``mastery_delta`` with it. The estimator's baseline for a concept nobody has measured
    is ``learning.PRIOR = 0.15`` (see ``_mastery_update``), not zero: a first observation
    moves mastery *from that prior*, so a ``before`` of 0.0 would fabricate a baseline the
    model never used and overstate the gain by exactly the prior. ``None`` is the honest
    record - no prior *measured* estimate existed - and the second observation is where a
    real before/after pair first exists. Do not "fix" this back to a zero baseline: the
    before/after pair exists so the movement is auditable, and a fabricated zero makes it
    assert something untrue.
    """
    concepts = _concepts_for(courses.DEFAULT_COURSE_ID)
    if not concepts:
        pytest.skip('default course has no authored concepts')
    concept_id = sorted(concepts)[0]

    first = evidence.record(db, user_row, slug='test-game', artifact_id='sim-x',
                            archetype='curve_shift', concept_id=concept_id,
                            correct=True, tries=1, elapsed_ms=4000)
    assert first['mastery_before'] is None, 'a first observation has no measured baseline'
    assert first['mastery_delta'] is None, 'a delta needs a measured before'
    assert first['mastery_after'] is not None and first['mastery_after'] > 0

    second = evidence.record(db, user_row, slug='test-game', artifact_id='sim-x',
                             archetype='curve_shift', concept_id=concept_id,
                             correct=False, tries=3, elapsed_ms=9000)
    # The estimator is the same one the question route uses, so the second observation
    # must build on the first rather than restart from nothing.
    assert second['mastery_before'] == first['mastery_after']
    assert second['mastery_delta'] is not None
    assert second['mastery_delta'] < 0, 'a wrong answer must lower the estimate'

    assert len(evidence.recent(db, user_row)) == 2
    summary = evidence.summary(db, user_row)
    assert summary['runs'] == 2
    assert summary['by_game'][0]['runs'] == 2 and summary['by_game'][0]['correct'] == 1


def test_an_unattributed_run_is_recorded_but_does_not_move_mastery(learner, db, user_row):
    result = evidence.record(db, user_row, slug='physics-game', artifact_id='sim-y',
                             archetype='projectile', concept_id='', correct=True,
                             tries=1, elapsed_ms=2000, feed_mastery=False)
    assert result['mastery_after'] is None
    assert result['mastery_delta'] is None
    assert evidence.summary(db, user_row)['runs'] == 1


# ---------------------------------------------------------------------- routing


def test_the_playground_router_is_declared_to_the_packager():
    """The frozen-bundle regression. A router missing from this tuple ships as 404s in
    the desktop app while the source tree serves them - which has already happened once
    in this project, to four routers at once."""
    assert 'playground_routes' in feature_routers.FEATURE_ROUTERS


def test_the_gallery_route_serves_the_catalogue(learner):
    client, token = learner
    response = client.get('/api/v1/playground',
                          headers={'Authorization': 'Bearer ' + token})
    assert response.status_code == 200
    body = response.json()
    assert body['total'] >= 20
    assert body['archetypes'] >= 20
    assert body['withheld'] == []
    assert {'mathematics', 'science', 'economics'} <= set(body['subjects'])


def test_the_archetype_route_publishes_the_schemas(learner):
    """An authoring model has to be able to discover the schema, so it must be served."""
    client, token = learner
    body = client.get('/api/v1/playground/archetypes',
                      headers={'Authorization': 'Bearer ' + token}).json()
    assert body['total'] >= 20
    sample = next(a for a in body['archetypes'] if a['id'] == 'curve_shift')
    assert sample['schema'] and sample['scored'] is True and sample['telemetry']


def test_a_game_page_is_served_as_html(learner):
    client, token = learner
    slug = catalogue.all_games()[0]['slug']
    response = client.get(f'/api/v1/playground/games/{slug}/html',
                          headers={'Authorization': 'Bearer ' + token})
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/html')
    assert 'data-series' in response.text
    assert response.headers['content-security-policy'].startswith("default-src 'none'")


def test_the_playground_needs_a_token(learner):
    client, _ = learner
    assert client.get('/api/v1/playground').status_code == 401


def test_an_unknown_game_is_a_404(learner):
    client, token = learner
    response = client.get('/api/v1/playground/games/no-such-game/html',
                          headers={'Authorization': 'Bearer ' + token})
    assert response.status_code == 404


# -------------------------------------------------------------------- exam guard


def _insert_exam(db, user_row, *, expires_in=3600, complete=False):
    """Put one exam row on the learner. ``expires_in`` is seconds from now, so a
    negative value is an exam that has already lapsed."""
    from app.db import Assessment, now_ts
    row = Assessment(user_id=user_row.id, mode='exam', total=10, complete=complete,
                     expires_at=now_ts() + expires_in)
    db.add(row)
    db.commit()
    return row


#: The five playground routes that must be refused mid-exam, each with a *valid* body
#: for the POSTs. The bodies are deliberately well-formed: the guard has to refuse the
#: request on its own, not because pydantic rejected the payload before it was reached.
_BLOCKED_DURING_EXAM = (
    ('get', '/api/v1/playground/games/{slug}/html', None),
    ('post', '/api/v1/playground/games/{slug}/instantiate', None),
    ('post', '/api/v1/playground/games/{slug}/outcome', {'correct': True, 'tries': 1}),
    ('post', '/api/v1/playground/compose', {'archetype': 'curve_shift', 'spec': {}}),
    ('post', '/api/v1/playground/draft', {'archetype': 'curve_shift', 'topic': 'anything'}),
)

#: The routes that stay open. Knowing which games exist is not help, so listing and
#: reading are not blocked - asserted here so that widening the guard later is a
#: deliberate act rather than a silent accident.
_OPEN_DURING_EXAM = (
    '/api/v1/playground',
    '/api/v1/playground/archetypes',
    '/api/v1/playground/posture',
    '/api/v1/playground/summary',
    '/api/v1/playground/runs',
    '/api/v1/playground/games/{slug}',
)


def test_an_active_exam_blocks_every_play_surface(learner, db, user_row):
    """The guard's own docstring says the playground is the surface that gets
    forgotten. This is the assertion that stops it being forgotten."""
    client, token = learner
    headers = {'Authorization': 'Bearer ' + token}
    slug = catalogue.all_games()[0]['slug']
    _insert_exam(db, user_row)
    for method, template, body in _BLOCKED_DURING_EXAM:
        url = template.format(slug=slug)
        kwargs = {'json': body} if body is not None else {}
        response = getattr(client, method)(url, headers=headers, **kwargs)
        assert response.status_code == 403, \
            f'{method.upper()} {url} answered {response.status_code}, not 403'


def test_a_refused_outcome_writes_no_run(learner, db, user_row):
    """Guarding the route is worthless if the row lands anyway. The count is what
    matters, not the status code."""
    from sqlalchemy import select
    from app.db import PlaygroundRun
    client, token = learner
    headers = {'Authorization': 'Bearer ' + token}
    slug = catalogue.all_games()[0]['slug']
    _insert_exam(db, user_row)

    db.rollback()
    before = len(db.scalars(select(PlaygroundRun)).all())

    response = client.post(f'/api/v1/playground/games/{slug}/outcome',
                           headers=headers, json={'correct': True, 'tries': 1})
    assert response.status_code == 403

    db.rollback()
    after = len(db.scalars(select(PlaygroundRun)).all())
    assert after == before, 'a refused outcome still wrote a PlaygroundRun row'


def test_an_active_exam_leaves_listing_and_reading_alone(learner, db, user_row):
    """Not every route is help. Listing the catalogue and reading one game's spec are
    exactly what a learner does *before* an exam, and blocking them would be a bug of
    its own."""
    client, token = learner
    headers = {'Authorization': 'Bearer ' + token}
    slug = catalogue.all_games()[0]['slug']
    _insert_exam(db, user_row)
    for template in _OPEN_DURING_EXAM:
        url = template.format(slug=slug)
        response = client.get(url, headers=headers)
        assert response.status_code == 200, f'GET {url} answered {response.status_code}'
    page = client.get('/playground')
    assert page.status_code == 200
    assert page.headers['content-type'].startswith('text/html')


def test_an_exam_that_is_over_does_not_block(learner, db, user_row):
    """The guard matches on ``expires_at > now_ts()`` and ``complete.is_(False)``, so
    an expired exam and a finished one must both stop blocking."""
    client, token = learner
    headers = {'Authorization': 'Bearer ' + token}
    slug = catalogue.all_games()[0]['slug']
    url = f'/api/v1/playground/games/{slug}/html'

    _insert_exam(db, user_row, expires_in=-60)          # already lapsed
    assert client.get(url, headers=headers).status_code == 200

    _insert_exam(db, user_row, complete=True)           # unexpired but finished
    assert client.get(url, headers=headers).status_code == 200


# -------------------------------------------------------------- the commit contract


def test_every_archetype_declares_a_known_commit_state():
    """``commits_on`` is what tells the verifier when an outcome is allowed to appear,
    so an archetype that declares a value the verifier does not know about would either
    wave through a stray commit or condemn a correct one."""
    from app.harness.playground.archetypes import COMMIT_STATES
    assert COMMIT_STATES, 'the vocabulary is empty; the scan below would be vacuous'
    for archetype in all_archetypes():
        assert archetype.commits_on in COMMIT_STATES, \
            f'{archetype.id} declares commits_on={archetype.commits_on!r}'


def test_the_commit_state_is_published_to_the_api():
    """It is read by the verifier off the archetype listing, so it has to survive
    ``describe()`` - a field that exists on the dataclass but not on the wire is not
    declared at all."""
    sample = get('curve_shift').describe()
    assert sample['commits_on'] == 'check'


def test_registration_refuses_an_unknown_commit_state():
    from dataclasses import replace
    from app.harness.playground import register
    probe = replace(get('curve_shift'), id='probe_bad_commit', commits_on='sideways')
    with pytest.raises(ValueError, match='commits_on'):
        register(probe)


def test_registration_refuses_completion_commit_on_an_unscored_sandbox():
    """An unscored sandbox must never post an outcome, so it cannot be one that commits
    on completion - the two declarations contradict each other."""
    from dataclasses import replace
    from app.harness.playground import register
    probe = replace(get('curve_shift'), id='probe_unscored_commit',
                    commits_on='completion', scored=False)
    with pytest.raises(ValueError, match='unscored'):
        register(probe)
