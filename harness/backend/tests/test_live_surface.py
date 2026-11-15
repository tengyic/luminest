"""The live-course surface decision and the routes that serve it.

This file pins four things the feature claims, separately from the rest of the suite:

1. **The layers stay separate.** ``teaching/surface.py`` decides *what the learner is
   looking at* and nothing else: it receives an already-compiled activity and its bound
   artifact, and cannot change the kind, order, budget or mastery of a lesson.
2. **A plan is a promise.** The surface is compiled into each block and into
   ``procedure_hash``; a surface whose artifact does not exist degrades to a *declared*
   fallback with a reason, never to an empty player or an imaginary deck.
3. **An interruption does not advance the deck.** A barge-in holds the surface in front
   of the learner; the only exception is an explicit draw intent, which records the
   surface to resume to.
4. **The decision is enforced, not advisory.** ``toolbox.invoke`` refuses a presentation
   tool belonging to another surface, and ``stage_surface`` is the one legal way to
   change it. Raw microphone audio reaches ``/asr`` through the JSON-only boundary.

Most of the decision tests are pure: no database, no model, no clock. Only the route
tests build a real app, and those never touch the network.
"""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.harness import toolbox, voice
from app.harness.teaching import (ConceptFacts, ProcedureAssets, build_evidence,
                                  compile_procedure, default_profile, procedure_hash,
                                  render_procedure_block)
from app.harness.teaching import surface as surface_router
from app.main import create_app

CONCEPT = 'fractions'


# --------------------------------------------------------------------- helpers

def facts(**overrides) -> ConceptFacts:
    base = dict(id='algebra.fractions', title='Fractions', strand='Algebra', tier='core',
                depth=1, prerequisite_count=1, dependant_count=2, has_lesson=True,
                has_figure=True, has_video=False, subject_kind='mathematics',
                concept_type='quantitative_relation', keywords=('fraction', 'denominator'))
    base.update(overrides)
    return ConceptFacts(**base)


def assets(**overrides) -> ProcedureAssets:
    base = dict(
        concept_id='algebra.fractions', concept_title='Fractions',
        course_id='integrated_math_1',
        deck_sections=({'heading': 'Fractions', 'bullets': ['A fraction is parts of a whole.'],
                        'notes': 'A fraction is parts of a whole.'},
                       {'heading': 'Check yourself', 'bullets': ['Add 2/3 and 1/4.'],
                        'notes': 'Add 2/3 and 1/4.'}),
        video={'provider': 'youtube', 'title': 'Fractions, explained',
               'channel': 'Curated', 'watch_url': 'https://example.test/watch',
               'embed_url': 'https://example.test/embed', 'licence_class': 'embed_only',
               'attribution': 'Curated', 'why': 'Concept-specific.'},
        worked_example={'body': 'To add 2/3 and 1/4, choose twelfths.', 'block_index': 2},
        practice_prompts=('Add 2/3 and 1/4.',), practice_count=2,
        prerequisites=('Place value',), dependants=('Ratios',))
    base.update(overrides)
    base.setdefault('practice_items', tuple(f'item-{n}' for n in range(base['practice_count'])))
    return ProcedureAssets(**base)


def lesson(**evidence_kw):
    profile = default_profile()
    ev = build_evidence(facts(), {}, mastery_threshold=profile.difficulty.mastery_threshold,
                        **evidence_kw)
    return compile_procedure(facts(), ev, assets(), profile, minutes_budget=20)


def ready(**overrides):
    return {'deck': True, 'video': True, 'whiteboard': True, 'chat': True,
            'reasons': {}, **overrides}


def _account(client, label='surface'):
    response = client.post('/api/v1/auth/register', json={
        'name': label, 'email': f'{label}@example.test',
        'password': 'long-secret-password'})
    assert response.status_code == 201, response.text
    return {'Authorization': 'Bearer ' + response.json()['token']}


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """Standalone settings for the pure ``voice.transcribe`` unit test."""
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.delenv('HARNESS_TUTOR_PROVIDER', raising=False)
    return Settings.from_env()


@pytest.fixture
def wired(tmp_path, monkeypatch):
    """A real app with a configured-but-never-reached provider."""
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'openai')
    monkeypatch.setenv('HARNESS_TUTOR_URL', 'https://provider.example.test/v1')
    monkeypatch.setenv('HARNESS_TUTOR_MODEL', 'test-model')
    monkeypatch.setenv('HARNESS_TUTOR_KEY', 'test-key-not-real')
    with TestClient(create_app(Settings.from_env())) as client:
        yield client


# ------------------------------------------------- the decision layer is pure

def test_the_surface_set_is_bounded_and_publishes_its_rules():
    posture = surface_router.describe()
    assert posture['surfaces'] == ['deck', 'video', 'whiteboard', 'chat']
    assert 'an interruption never advances the deck' in posture['invariants']
    assert 'only a bound artifact may be promised' in posture['invariants']
    assert posture['decision_tool'] == 'stage_surface'
    # A self-reported learning style is explicitly excluded: the meshing hypothesis
    # fails its crossover test, and a display decision must not be dressed up as one.
    assert 'learning style' in posture['excluded']
    for name, tools in posture['tools'].items():
        assert isinstance(tools, list) and all(isinstance(t, str) for t in tools)
        for tool in tools:
            assert surface_router.tool_surface(tool) == name


def test_presentation_tools_have_one_owner_and_neutral_tools_have_none():
    assert surface_router.tool_surface('deck_control') == 'deck'
    assert surface_router.tool_surface('build_presentation') == 'deck'
    assert surface_router.tool_surface('find_video') == 'video'
    assert surface_router.tool_surface('whiteboard_apply') == 'whiteboard'
    assert surface_router.tool_surface('draw_diagram') == 'whiteboard'
    # Neutral tools are unrestricted by construction; adding a tool cannot silently
    # bypass the boundary because it has no surface until one is deliberately assigned.
    assert surface_router.tool_surface('read_concept') is None
    assert surface_router.tool_surface('check_understanding') is None
    assert surface_router.tool_surface('stage_surface') is None


def test_available_surfaces_reports_a_reason_for_every_missing_artifact():
    inventory = surface_router.available_surfaces({
        'deck': {'slides': 3}, 'video': None,
        'unavailable': {'video': 'No verified video is curated for this course.'}})
    assert inventory['deck'] is True and inventory['video'] is False
    assert inventory['whiteboard'] is True and inventory['chat'] is True
    assert 'curated' in inventory['reasons']['video']
    assert 'deck' not in inventory['reasons']
    assert surface_router.available_surfaces(board_available=False)['whiteboard'] is False


def test_the_decision_is_deterministic_and_reviewable():
    block = {'kind': 'deck', 'artifact': {'kind': 'slides', 'slide_count': 5}}
    first = surface_router.choose_surface(block=block, available=ready()).to_dict()
    second = surface_router.choose_surface(block=block, available=ready()).to_dict()
    assert first == second
    assert first['surface'] == 'deck' and first['source'] == 'compiled'
    assert first['why'] and first['tools'] and first['alternatives']
    assert {row['surface'] for row in first['alternatives']} == {
        'video', 'whiteboard', 'chat'}


def test_a_deck_block_chooses_the_deck_and_a_video_block_the_browser_video():
    deck = surface_router.choose_surface(
        block={'kind': 'deck', 'artifact': {'kind': 'slides', 'slide_count': 3}},
        available=ready())
    video = surface_router.choose_surface(
        block={'kind': 'video', 'artifact': {'kind': 'video'}},
        available=ready())
    assert deck.surface == 'deck' and 'slide deck' in deck.why
    assert video.surface == 'video' and 'browser' in video.why
    assert video.tools == surface_router.PRESENTATION_TOOLS['video']


def test_a_missing_artifact_degrades_to_a_declared_fallback_never_a_fake():
    no_deck = surface_router.choose_surface(
        block={'kind': 'deck'}, available=ready(deck=False))
    assert no_deck.surface == 'chat' and no_deck.source == 'ceiling'
    assert 'not available' in no_deck.why and 'Declared fallback' in no_deck.why
    # A video with no embed falls back to the bound deck, not to prose about a video.
    no_video = surface_router.choose_surface(
        block={'kind': 'video'}, available=ready(video=False))
    assert no_video.surface == 'deck'
    assert no_video.fallback == {} or 'fallback' in no_video.to_dict()
    for name in ('deck', 'video', 'whiteboard'):
        fallback = surface_router.declared_fallback(name, ready())
        assert fallback['kind'] == 'declared_fallback'
        assert fallback['reason'] and fallback['surface'] in surface_router.SURFACES


def test_an_interruption_holds_the_surface_and_does_not_switch_or_advance():
    held = surface_router.choose_surface(
        block={'kind': 'deck'}, available=ready(), current='deck', interrupted=True)
    assert held.surface == 'deck' and held.switch is False
    assert held.source == 'interruption' and 'must not advance the deck' in held.why
    # The same holds when the compiled activity wanted a video: the learner is
    # looking at the deck and their question refers to it.
    held_b = surface_router.choose_surface(
        block={'kind': 'video'}, available=ready(), current='deck', interrupted=True)
    assert held_b.surface == 'deck' and held_b.switch is False


def test_a_drawn_interruption_records_the_surface_to_resume_to():
    drawn = surface_router.choose_surface(
        block={'kind': 'deck'}, available=ready(), current='deck',
        interrupted=True, intent='draw')
    assert drawn.surface == 'whiteboard' and drawn.source == 'interruption'
    assert drawn.resume_surface == 'deck' and 'cursor does not move' in drawn.why


def test_explicit_draw_and_conceptual_errors_use_the_board_but_frustration_does_not():
    explicit = surface_router.choose_surface(
        block={'kind': 'discussion'}, available=ready(), intent='draw')
    assert explicit.surface == 'whiteboard' and explicit.source == 'teacher'
    conceptual = surface_router.choose_surface(
        block={'kind': 'discussion'}, available=ready(),
        evidence={'top_error': 'conceptual', 'mastery': 0.3, 'attempts': 4})
    assert conceptual.surface == 'whiteboard'
    frustrated = surface_router.choose_surface(
        block={'kind': 'discussion'}, available=ready(),
        evidence={'top_error': 'conceptual', 'frustrated': True, 'attempts': 4})
    assert frustrated.surface == 'chat' and 'load' in frustrated.why


def test_a_switched_off_surface_degrades_in_a_fixed_order():
    decision = surface_router.choose_surface(
        block={'kind': 'deck'}, available=ready(), allowed=('chat', 'deck'))
    assert decision.surface == 'deck'
    off = surface_router.choose_surface(
        block={'kind': 'deck'}, available=ready(), allowed=('chat',))
    assert off.surface == 'chat' and off.source == 'ceiling'
    assert 'switched off' in off.why


# ------------------------------------------- the surface is part of the plan

def test_every_compiled_block_carries_its_surface_decision():
    procedure = lesson()
    assert procedure.blocks
    for block in procedure.blocks:
        assert block.surface in surface_router.SURFACES
        assert block.surface_why
        assert block.surface_decision['surface'] == block.surface
        row = block.to_dict()
        assert row['surface'] == block.surface and row['surface_decision']['why']
    kinds = {block.kind for block in procedure.blocks}
    # A compiled input owns its artifact's surface; it is never a display whim.
    for block in procedure.blocks:
        if block.kind == 'deck':
            assert block.surface == 'deck'


def test_the_surface_is_part_of_the_plan_hash():
    """A plan that shows the same lesson on a different surface is a different plan."""
    from dataclasses import replace

    procedure = lesson()
    original = procedure_hash(procedure)
    # Change one real block's surface - the compiler chooses video or deck depending
    # on the bound assets, so the test must not assume which input it picked.
    first = procedure.blocks[0]
    alternative = 'whiteboard' if first.surface != 'whiteboard' else 'chat'
    changed = replace(procedure, blocks=(
        replace(first, surface=alternative), *procedure.blocks[1:]))
    assert procedure_hash(changed) != original
    assert procedure_hash(lesson()) == original, 'the compiler must be deterministic'


def test_the_prompt_names_only_the_live_surface_tools():
    """The invariant that a diagnostic must never hear about flipping a deck."""
    procedure = {
        'enabled': True, 'concept_id': 'fractions', 'concept_title': 'Fractions',
        'course_id': 'integrated_math_1', 'budget_minutes': 20, 'total_minutes': 12,
        'blocks': [
            {'order': 1, 'kind': 'diagnostic', 'minutes': 3, 'title': 'Quick check',
             'purpose': 'Measure where the learner is.', 'why': 'No evidence yet.',
             'artifact': {'kind': 'questions'}, 'surface': 'chat'},
            {'order': 2, 'kind': 'deck', 'minutes': 5, 'title': 'Lesson deck',
             'purpose': 'Present the concept.', 'why': 'First exposure.',
             'artifact': {'kind': 'slides', 'sections': [{'heading': 'Halves'}]},
             'surface': 'deck'},
        ],
        'skipped': [],
    }
    diagnostic = render_procedure_block(procedure, completed=[])
    assert 'deck_control' not in diagnostic
    assert 'live surface for this turn is chat' in diagnostic
    deck = render_procedure_block(procedure, completed=[1])
    assert 'deck_control' in deck
    assert 'Tools for the deck surface' in deck
    assert 'find_video' not in deck


# ------------------------------------- the boundary is enforced, not advisory

def test_the_toolbox_refuses_a_tool_from_another_surface_with_a_decision_hint():
    ctx = toolbox.ToolContext(surface='deck')
    result = toolbox.invoke(ctx, 'find_video', {'concept_id': 'fractions'})
    assert result.ok is False and result.refused
    assert 'stage_surface' in result.refused
    assert result.data['active_surface'] == 'deck'
    assert result.data['tool_surface'] == 'video'
    assert result.data['decision_tool'] == 'stage_surface'


def test_neutral_tools_and_the_decision_tool_work_on_every_surface(monkeypatch):
    called = {}

    def fake(ctx, **kwargs):
        called['args'] = kwargs
        return toolbox.ToolResult('probe', True, {'ok': True})

    spec = toolbox.ToolSpec('probe', 'A neutral probe.', '', 'internal', '{}')
    monkeypatch.setitem(toolbox.REGISTRY, 'probe', (spec, fake))
    for active in surface_router.SURFACES:
        ctx = toolbox.ToolContext(surface=active)
        assert toolbox.invoke(ctx, 'probe', {'x': active}).ok is True
        assert called['args'] == {'x': active}
    # stage_surface is neutral too: it is how a teacher changes the surface, so it
    # must be callable from every one of them.
    monkeypatch.setitem(toolbox.REGISTRY, 'stage_surface', (spec, fake))
    ctx = toolbox.ToolContext(surface='video')
    assert toolbox.invoke(ctx, 'stage_surface', {'surface': 'deck'}).ok is True


def test_no_boundary_applies_when_no_live_lesson_is_running(monkeypatch):
    """Plan execution, authoring and offline probes stay unrestricted."""
    def fake(ctx, **kwargs):
        return toolbox.ToolResult('probe', True, {})

    spec = toolbox.ToolSpec('probe', 'A neutral probe.', '', 'internal', '{}')
    monkeypatch.setitem(toolbox.REGISTRY, 'probe', (spec, fake))
    # An empty surface is the default for every non-live context.
    assert toolbox.ToolContext().surface == ''
    ctx = toolbox.ToolContext(surface='')
    assert toolbox.invoke(ctx, 'probe').ok is True


# ------------------------------------------------------- the live HTTP routes

def test_the_live_catalog_publishes_the_contract(wired):
    headers = _account(wired)
    response = wired.get('/api/v1/live/catalog', headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['version'] == '1' and body['decision_tool'] == 'stage_surface'
    assert set(body['surfaces']) == set(surface_router.SURFACES)
    assert '/{concept_id}/asr' in body['endpoints']
    assert 'interrupted' in body['teaching_turn']


def test_live_state_is_one_document_a_client_can_render_from(wired):
    headers = _account(wired)
    started = wired.post(f'/api/v1/procedure/{CONCEPT}/start', headers=headers)
    assert started.status_code == 200, started.text
    response = wired.get(f'/api/v1/live/{CONCEPT}/state', headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['run_id'] and body['concept_id'] == CONCEPT
    assert body['surface']['compiled_surface'] in surface_router.SURFACES
    assert body['surface']['surface'] in surface_router.SURFACES
    assert 'available' in body['surface'] and 'fallback' in body['surface']
    for key in ('deck', 'video', 'whiteboard', 'voice', 'turn'):
        assert key in body, key
    assert body['voice']['asr'] == f'/api/v1/live/{CONCEPT}/asr'
    assert body['turn']['teach'] == '/api/v1/agent/stream'
    assert body['turn']['body']['context']['concept_id'] == CONCEPT


def test_a_surface_switch_is_a_recorded_decision_with_a_reason(wired):
    headers = _account(wired)
    wired.post(f'/api/v1/procedure/{CONCEPT}/start', headers=headers)
    # Unknown surface -> refused, not an exception.
    unknown = wired.post(f'/api/v1/live/{CONCEPT}/surface', headers=headers,
                         json={'surface': 'hologram', 'reason': 'why not'}).json()
    assert unknown['ok'] is False and 'Unknown surface' in unknown['refused']
    # Deviating from the compiled surface without a reason -> refused.
    no_reason = wired.post(f'/api/v1/live/{CONCEPT}/surface', headers=headers,
                           json={'surface': 'whiteboard'}).json()
    assert no_reason['ok'] is False and 'needs a reason' in no_reason['refused']
    # A reason makes it a decision, and the decision is persisted.
    switched = wired.post(f'/api/v1/live/{CONCEPT}/surface', headers=headers,
                          json={'surface': 'whiteboard',
                                'reason': 'Sketch the relationship live.'}).json()
    assert switched['ok'] is True and switched['surface'] == 'whiteboard'
    assert switched['switch'] is True and switched['source'] == 'teacher'
    state = wired.get(f'/api/v1/live/{CONCEPT}/state', headers=headers).json()
    assert state['surface']['surface'] == 'whiteboard'
    assert state['surface']['compiled_surface'] != 'whiteboard'


def test_an_unavailable_surface_is_refused_with_a_declared_fallback(wired):
    headers = _account(wired)
    wired.post(f'/api/v1/procedure/{CONCEPT}/start', headers=headers)
    state = wired.get(f'/api/v1/live/{CONCEPT}/state', headers=headers).json()
    if state['surface']['available']['video']:
        pytest.skip('this lesson bound a video; nothing is unavailable to test')
    refused = wired.post(f'/api/v1/live/{CONCEPT}/surface', headers=headers,
                         json={'surface': 'video', 'reason': 'first exposure'}).json()
    assert refused['ok'] is False and 'cannot be shown' in refused['refused']
    assert refused['fallback']['kind'] == 'declared_fallback'


def test_advance_clears_a_recorded_switch_so_the_next_block_re_decides(wired):
    headers = _account(wired)
    run = wired.post(f'/api/v1/procedure/{CONCEPT}/start', headers=headers).json()
    wired.post(f'/api/v1/live/{CONCEPT}/surface', headers=headers,
               json={'surface': 'whiteboard', 'reason': 'Draw this block.'})
    before = wired.get(f'/api/v1/live/{CONCEPT}/state', headers=headers).json()
    assert before['surface']['surface'] == 'whiteboard'
    order = before['surface']['block_order']
    advanced = wired.post(f'/api/v1/live/{CONCEPT}/advance', headers=headers,
                          json={'order': order, 'outcome': 'skipped'})
    assert advanced.status_code == 200, advanced.text
    assert advanced.json()['advanced']['order'] == order
    after = wired.get(f'/api/v1/live/{CONCEPT}/state', headers=headers).json()
    assert after['surface']['surface'] == after['surface']['compiled_surface']
    assert after['surface']['switch'] is False


def test_raw_microphone_audio_reaches_asr_and_never_raises(wired, monkeypatch):
    """The JSON-only boundary admits audio on the ASR path and nowhere else."""
    headers = _account(wired)
    wired.post(f'/api/v1/procedure/{CONCEPT}/start', headers=headers)

    def no_backend(settings, *, read_timeout):
        raise httpx.ConnectError('test backend is not listening')

    monkeypatch.setattr(voice, '_client', no_backend)
    response = wired.post(f'/api/v1/live/{CONCEPT}/asr',
                          headers={**headers, 'Content-Type': 'audio/webm'},
                          content=b'RIFF-fake-utterance')
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['fallback'] == 'declared' and body['ok'] is False
    assert body['reason'] and body['next_action']
    assert body['surface']['hold'] is True
    assert body['turn']['path'] == '/api/v1/agent/stream'
    assert body['turn']['body']['interrupted'] is True
    # The widening is scoped: another live path still refuses a non-JSON payload.
    other = wired.post(f'/api/v1/live/{CONCEPT}/surface',
                       headers={**headers, 'Content-Type': 'audio/webm'}, content=b'x')
    assert other.status_code == 415


def test_asr_turns_a_transcript_into_an_interrupted_turn(wired, monkeypatch):
    headers = _account(wired)
    wired.post(f'/api/v1/procedure/{CONCEPT}/start', headers=headers)

    class _Response:
        status_code = 200

        text = ''

        def json(self):
            return {'text': '  why is a point inside the curve inefficient?  '}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def post(self, url, **kwargs):
            assert url.endswith('/v1/audio/transcriptions')
            assert kwargs['data']['model'] == voice.TRANSCRIPTION_MODEL
            assert 'file' in kwargs['files']
            return _Response()

    monkeypatch.setattr(voice, '_client', lambda settings, *, read_timeout: _Client())
    response = wired.post(f'/api/v1/live/{CONCEPT}/asr',
                          headers={**headers, 'Content-Type': 'audio/mpeg'},
                          content=b'ID3-real-audio')
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['ok'] is True
    assert body['text'] == 'why is a point inside the curve inefficient?'
    assert body['turn']['body']['message'] == body['text']
    assert body['turn']['body']['interrupted'] is True
    assert body['turn']['body']['speak'] is True


def test_transcribe_never_raises_and_never_fakes_a_transcript(settings, monkeypatch):
    """Unit-level: every failure mode is a declared fallback with a next action."""
    from dataclasses import replace

    off = replace(settings, voice_enabled=False)
    live = replace(settings, voice_enabled=True)
    disabled = voice.transcribe(off, b'audio')
    assert disabled['ok'] is False and disabled['reason'] == 'voice-disabled'
    assert disabled['text'] == '' and disabled['next_action']
    assert voice.transcribe(live, b'')['reason'] == 'empty-audio'
    assert voice.transcribe(live, b'x' * (voice.MAX_ASR_BYTES + 1))['reason'] == 'audio-too-large'

    class _Response:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self.text = ''
            self._payload = payload

        def json(self):
            if self._payload is None:
                raise ValueError('not json')
            return self._payload

    class _Client:
        response = _Response(200, {'text': ''})

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def post(self, url, **kwargs):
            return self.response

    monkeypatch.setattr(voice, '_client', lambda s, *, read_timeout: _Client())
    assert voice.transcribe(live, b'audio')['reason'] == 'no-speech'
    _Client.response = _Response(500, None)
    assert voice.transcribe(live, b'audio')['reason'] == 'voice-http-500'
    _Client.response = _Response(200, {'text': 'a real question'})
    good = voice.transcribe(live, b'audio', content_type='audio/mpeg')
    assert good['ok'] is True and good['text'] == 'a real question'
