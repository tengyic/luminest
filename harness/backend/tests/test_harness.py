"""Tests for the harness layer: memory, toolbox, sandbox, generation and the loop.

These tests are written around claims the product makes, not around implementation
details. Where a claim is about safety (a licence gate, a sandbox boundary) the test
asserts the refusal, because a gate that is never exercised is a gate that has quietly
stopped working.
"""

import json
import tempfile
from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree

import pytest
from sqlalchemy import select

from app import harness
from app.config import Settings
from app.curriculum import GRAPH_TO_LESSON, KNOWLEDGE_GRAPH, LESSON_TARGETS
from app.db import Base, HarnessRun, MemoryNote, SCHEMA_VERSION, State, User, make_database
from app.harness import generate, loop, memory, prompt, render, sandbox, toolbox
from app.main import create_app
from test_api import account, answer, client, next_q, settings  # noqa: F401 - fixtures

#: A concept with an authored lesson and a curve figure.
CURVE = 'quadratic_expressions_and_their_graphs'
#: A concept whose figure is a scene, not a function.
SCENE = 'fraction_equivalence'
LESSON = 'fractions'


# --------------------------------------------------------------------- fixtures

@pytest.fixture
def database(settings):
    engine, factory = make_database(settings)
    Base.metadata.create_all(engine)
    with factory() as db:
        yield db
    engine.dispose()


@pytest.fixture
def learner(database):
    user = User(name='Ada', email='ada@example.test', password_hash='x')
    database.add(user)
    database.commit()
    return user


def tool_ctx(database=None, user=None, settings=None, workspace=True):
    ctx = harness.ToolContext(db=database, user=user, settings=settings, now=1_700_000_000.0)
    if workspace:
        ctx.workspace = sandbox.Workspace(Path(tempfile.mkdtemp()) / 'ws', 'test-ws')
    return ctx


# ----------------------------------------------------------------- memory

def test_memory_reinforcement_and_decay_are_separate_signals(database, learner):
    first = memory.remember(database, learner.id, 'semantic', 'Sign error when distributing.',
                            concept_id=CURVE, confidence=0.4)
    assert first.reinforcements == 1
    again = memory.remember(database, learner.id, 'semantic', 'Sign error when distributing.',
                            concept_id=CURVE)
    assert again.reinforcements == 2 and again.confidence > first.confidence
    # A note is never deleted by decay; only how strongly it is believed changes.
    aged = again.aged(again.last_seen + memory.HALF_LIFE)
    assert aged < again.confidence
    assert aged >= memory.FLOOR
    long_gap = again.aged(again.last_seen + 400 * memory.HALF_LIFE)
    assert long_gap == pytest.approx(memory.FLOOR, abs=1e-6)
    assert database.scalar(select(MemoryNote).where(MemoryNote.id == again.id)) is not None


def test_memory_confidence_is_bounded_and_never_reaches_certainty(database, learner):
    for _ in range(40):
        note = memory.remember(database, learner.id, 'semantic', 'Repeated observation.',
                               concept_id=CURVE)
    assert note.confidence <= memory.CEILING
    assert note.reinforcements == 40


def test_memory_relevance_prefers_this_concept_over_a_distant_one(database, learner):
    memory.remember(database, learner.id, 'semantic', 'Nearby belief.', concept_id=CURVE)
    memory.remember(database, learner.id, 'semantic', 'Distant belief.', concept_id='unrelated_topic')
    ranked = memory.recall(database, learner.id, concept_id=CURVE, limit=5)
    assert ranked[0].concept_id == CURVE


def test_memory_digest_is_citable_and_hedged(database, learner):
    assert 'No prior observations' in memory.digest(database, learner.id, concept_id=CURVE)
    memory.remember(database, learner.id, 'semantic', 'Confuses the sign when distributing.',
                    concept_id=CURVE)
    digest = memory.digest(database, learner.id, concept_id=CURVE)
    assert 'semantic' in digest and 'belief' in digest and 'observed once' in digest


def test_memory_forget_and_wipe_are_exact(database, learner):
    keep = memory.remember(database, learner.id, 'episodic', 'Kept.', concept_id=CURVE)
    drop = memory.remember(database, learner.id, 'episodic', 'Dropped.', concept_id=SCENE)
    assert memory.forget(database, learner.id, drop.id) is True
    assert memory.forget(database, learner.id, drop.id) is False
    assert memory.wipe(database, learner.id) == 1
    assert database.scalar(select(MemoryNote).where(MemoryNote.id == keep.id)) is None
    assert memory.summarise([])['total'] == 0


def test_memory_rejects_an_unknown_kind_and_empty_text(database, learner):
    with pytest.raises(ValueError):
        memory.remember(database, learner.id, 'vibes', 'Nope.')
    with pytest.raises(ValueError):
        memory.remember(database, learner.id, 'semantic', '   ')


# ----------------------------------------------------------------- toolbox

def test_tool_catalogue_is_internally_consistent():
    catalogue = toolbox.catalogue()
    assert len(catalogue) >= 14
    assert {entry['name'] for entry in catalogue} == set(toolbox.REGISTRY)
    assert all(entry['posture'] in toolbox.POSTURES for entry in catalogue)
    assert all(entry['summary'] and entry['arguments'] is not None for entry in catalogue)
    assert toolbox.postures()['sandboxed'] >= 4
    # Every entry states its own availability, so the complete catalogue doubles as the
    # answer to "what can this build do" without a second list to keep in step.
    assert all(isinstance(entry['available'], bool) for entry in catalogue)
    assert all(entry['available'] or entry['requires'] for entry in catalogue)


def test_a_tool_whose_optional_package_is_absent_is_registered_but_not_offered():
    """The general contract behind ``browser_snapshot``.

    A tool that is listed to the model but can only ever refuse is worse than one that is
    not listed: the model spends a turn on a guaranteed refusal, and the failure reads as
    a bug rather than as a build decision. So a tool declares the modules it needs,
    availability is reported, and only available tools are offered - while the registry
    stays complete so an operator can still audit what the build contains.
    """
    gated = toolbox.ToolSpec('needs_a_unicorn', 'A tool with an impossible dependency.',
                             'x: str', 'internal', 'y',
                             requires=('unicorn_horn_that_does_not_exist',))
    toolbox._register(gated, lambda ctx, **kwargs: toolbox.ToolResult('needs_a_unicorn', True))
    try:
        assert toolbox.available(gated) is False
        assert gated.name not in [spec.name for spec in toolbox.available_specs()]
        assert gated.name in [spec.name for spec in toolbox.unavailable_specs()]
        # Still registered and still dispatchable: the gate governs advertising, not the
        # dispatch table, so a name that arrives anyway is answered rather than dropped.
        assert gated.name in toolbox.REGISTRY
        entry = next(item for item in toolbox.catalogue() if item['name'] == gated.name)
        assert entry['available'] is False
        assert entry['requires'] == ['unicorn_horn_that_does_not_exist']
        # And it never reaches the model, which is the point of the whole exercise.
        assert gated.name not in prompt.build('Ada', 'Quadratics')
    finally:
        toolbox.REGISTRY.pop(gated.name, None)


def test_unknown_tool_and_bad_arguments_are_refusals_not_exceptions():
    ctx = tool_ctx()
    missing = toolbox.invoke(ctx, 'summon_demon')
    assert not missing.ok and 'Unknown tool' in missing.refused
    wrong = toolbox.invoke(ctx, 'search_concepts', {'nonsense': 1})
    assert not wrong.ok and 'Bad arguments' in wrong.refused


def test_material_search_returns_links_only_for_restricted_sources():
    ctx = tool_ctx()
    result = toolbox.search_material(ctx, 'openstax')
    assert result.ok
    external = {entry['name']: entry for entry in result.data['external']}
    assert external, 'the declared source registry should be reachable by search'
    for entry in external.values():
        assert entry['text_returned'] is False
        if not entry['ingestible']:
            assert entry['mode'] == 'link_only'
            assert entry['refusal_reason']


def test_fetch_material_text_refuses_restricted_sources_and_allows_cleared_ones():
    ctx = tool_ctx()
    refused = toolbox.fetch_material_text(ctx, 'Khan Academy')
    assert refused.ok is False and 'prohibited' in refused.refused
    assert refused.data['source']['licence_class'] == 'prohibited'
    cleared = toolbox.fetch_material_text(ctx, 'Wikidata')
    assert cleared.ok is True
    assert cleared.data['provenance']['licence_class'] == 'cc0'
    assert toolbox.fetch_material_text(ctx, 'Some Blog').ok is False


def test_no_generated_artifact_puts_restricted_text_in_front_of_the_learner():
    """The licence gate is only meaningful if it holds for what the harness emits.

    Naming a source as a link is allowed and necessary. Reproducing its text is not, so
    the assertion is on learner-facing block text rather than on the whole payload.
    """
    ctx = tool_ctx()
    for concept in (CURVE, SCENE, LESSON):
        for kind in generate.KINDS:
            artifact = generate.compose(ctx, concept, kind, {'count': 4})
            for block in artifact.blocks:
                text = ' '.join(str(block.get(field, '')) for field in ('text', 'caption', 'title'))
                lowered = text.casefold()
                assert 'khan academy' not in lowered, (concept, kind)
                assert 'openstax' not in lowered, (concept, kind)
                for item in block.get('items', []) if isinstance(block.get('items'), list) else []:
                    if isinstance(item, dict):
                        assert 'openstax' not in str(item).casefold(), (concept, kind)
            for citation in artifact.citations:
                if citation.get('source', '').casefold().find('openstax') >= 0:
                    assert citation['licence_class'] in {'link_only', 'prohibited'}


def test_every_tool_returns_a_typed_result():
    ctx = tool_ctx()
    calls = [('search_concepts', {'query': 'slope'}), ('read_concept', {'concept_id': CURVE}),
             ('inspect_prerequisites', {'concept_id': CURVE}),
             ('recall_learner_memory', {'concept_id': CURVE}),
             ('read_learner_evidence', {'concept_id': CURVE}),
             ('search_material', {'query': 'quadratic'}),
             ('prepare_case_study', {'concept_id': CURVE}),
             ('build_figure', {'concept_id': CURVE}),
             ('check_understanding', {'concept_id': LESSON}),
             ('compose_content', {'concept_id': CURVE, 'kind': 'flashcards'}),
             ('list_workspace', {}),
             ('write_workspace_file', {'path': 'a.txt', 'content': 'hi'}),
             ('read_workspace_file', {'path': 'a.txt'}),
             ('run_in_workspace', {'language': 'python', 'code': 'print(1)'})]
    for name, arguments in calls:
        result = toolbox.invoke(ctx, name, arguments)
        assert isinstance(result, toolbox.ToolResult), name
        assert result.tool == name
        if name == 'check_understanding':
            # Serving an answerable item now requires a signed-in account, a live
            # database and receipt signing. A bare harness context must refuse with a
            # named reason rather than invent an unanswerable question; the success path
            # (signed receipt -> /attempts -> Attempt row) is covered end to end in
            # tests/test_tool_access_receipts.py.
            assert not result.ok and 'signed-in account' in result.refused, (name, result)
            assert result.data is None
            continue
        assert result.ok, (name, result.refused or result.error)


def test_build_figure_is_real_executable_content_for_a_curve_and_a_scene():
    ctx = tool_ctx()
    curve = toolbox.build_figure(ctx, CURVE)
    assert curve.ok and curve.data['figure'] == 'curve'
    assert curve.data['series'] and curve.data['parameters']
    assert curve.data['expression']['substituted']
    assert curve.data['variable'] == 'x'
    scene = toolbox.build_figure(ctx, SCENE)
    assert scene.ok and scene.data['figure'] == 'scene'
    assert scene.data['parts'] and scene.data['series'] == []


def test_case_study_is_grounded_in_the_authored_lesson():
    ctx = tool_ctx()
    result = toolbox.prepare_case_study(ctx, LESSON)
    assert result.ok
    assert result.data['tasks'] and result.data['rubric']
    assert result.data['core_idea']
    assert any(citation['kind'] == 'authored_lesson' for citation in result.citations)


def test_workspace_tools_are_confined():
    ctx = tool_ctx()
    escaped = toolbox.invoke(ctx, 'write_workspace_file', {'path': '../outside.txt', 'content': 'x'})
    assert escaped.ok is False and 'traversal' in escaped.refused.lower()
    absolute = toolbox.invoke(ctx, 'write_workspace_file', {'path': '/etc/hosts', 'content': 'x'})
    assert absolute.ok is False and 'Absolute' in absolute.refused
    written = toolbox.invoke(ctx, 'write_workspace_file', {'path': 'deck.json', 'content': '{}'})
    assert written.ok and written.data['bytes'] == 2
    assert toolbox.invoke(ctx, 'read_workspace_file', {'path': 'missing.json'}).ok is False


# ----------------------------------------------------------------- sandbox

def test_sandbox_runs_ordinary_python_and_writes_inside_the_workspace():
    workspace = sandbox.Workspace(Path(tempfile.mkdtemp()) / 'ws', 'test')
    run = workspace.run('python', 'open("out.txt", "w").write("ok")\nprint(open("out.txt").read())')
    assert run['ok'] and run['stdout'].strip() == 'ok'
    assert 'path-confinement' in run['boundaries']
    assert 'runtime-audit-hook' in run['boundaries']
    assert run['boundary']


def test_sandbox_refuses_network_process_and_import_capabilities():
    workspace = sandbox.Workspace(Path(tempfile.mkdtemp()) / 'ws', 'test')
    for code in ('import socket', 'import subprocess', 'import ctypes',
                 'import os\nos.system("echo hi")', 'import builtins'):
        with pytest.raises(sandbox.SandboxRefused):
            workspace.run('python', code)
    with pytest.raises(sandbox.SandboxRefused):
        workspace.run('python', 'def (')


def test_sandbox_runtime_hook_catches_what_static_analysis_cannot():
    """A dynamic import passes the syntax check, so the runtime hook has to stop it."""
    workspace = sandbox.Workspace(Path(tempfile.mkdtemp()) / 'ws', 'test')
    code = ('b = __builtins__\n'
            'f = b["__import__"] if isinstance(b, dict) else b.__dict__["__import__"]\n'
            'print(f("socket"))')
    run = workspace.run('python', code)
    assert run['ok'] is False
    assert 'importing socket is not permitted' in run['stderr']


def test_sandbox_refuses_writes_outside_and_reads_of_the_home_tree():
    workspace = sandbox.Workspace(Path(tempfile.mkdtemp()) / 'ws', 'test')
    outside = workspace.run('python', 'open("/tmp/harness-should-not-exist.txt", "w").write("x")')
    assert outside['ok'] is False
    assert 'outside the workspace is not permitted' in outside['stderr']
    home = workspace.run('python', f'print(open("{Path.home()}/.zshrc").read()[:10])')
    assert home['ok'] is False


def test_sandbox_bounds_time_output_and_language():
    workspace = sandbox.Workspace(Path(tempfile.mkdtemp()) / 'ws', 'test')
    timed = workspace.run('python', 'while True: pass', timeout=1.0)
    assert timed['ok'] is False and 'Timed out' in timed['stderr']
    with pytest.raises(sandbox.SandboxRefused):
        workspace.run('bash', 'echo hi')
    with pytest.raises(sandbox.SandboxRefused):
        workspace.run('python', '   ')


def test_sandbox_path_resolution_refuses_escapes_and_reports_boundaries():
    workspace = sandbox.Workspace(Path(tempfile.mkdtemp()) / 'ws', 'test')
    for bad in ('../x', '/etc/passwd', 'a/../../b', ''):
        with pytest.raises(sandbox.SandboxRefused):
            workspace.resolve(bad)
    posture = sandbox.describe()
    assert posture['boundaries'][:3] == ['path-confinement', 'static-guard', 'runtime-audit-hook']
    assert posture['max_timeout_seconds'] <= 60


def test_sandbox_denies_data_directory_reads_but_not_the_learner_workspace():
    """verify-2b hardening: the data directory holds the textbook store and other
    learners' workspaces, and OpenStax's notices prohibit ingesting its content into
    generative-AI offerings -- so generated code must not read it and print it back to
    the model. The learner's own workspace stays readable."""
    from types import SimpleNamespace
    data_dir = Path(tempfile.mkdtemp())
    store = data_dir / 'textbook' / 'sections.json'
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text('VERBATIM-OPENSTAX-EXCERPT-MARKER', encoding='utf-8')

    workspace = sandbox.workspace_for(SimpleNamespace(data_dir=data_dir), 'learner-a')
    assert any(str(store.resolve()).startswith(p + '/') or p == str(data_dir.resolve())
               for p in workspace.deny_reads)

    denied = workspace.run('python', f'print(open({str(store)!r}).read())')
    assert denied['ok'] is False
    assert 'reading outside the sandbox is not permitted' in denied['stderr'], \
        'the runtime hook must deny with PermissionError, not crash with a TypeError'

    neighbour = workspace.run('python',
                              f'print(open({str(data_dir / "workspaces" / "learner-b" / "x.txt")!r}).read())')
    assert neighbour['ok'] is False

    workspace.write('mine.txt', 'hello learner')
    own = workspace.run('python', 'print(open("mine.txt").read())')
    assert own['ok'] is True and 'hello learner' in own['stdout']


# ----------------------------------------------------------------- generation

def test_every_artifact_kind_composes_for_a_curve_and_a_scene_concept():
    ctx = tool_ctx()
    for concept in (CURVE, SCENE, LESSON):
        for kind in generate.KINDS:
            artifact = generate.compose(ctx, concept, kind, {'count': 5})
            assert artifact.kind == kind and artifact.title
            assert artifact.blocks, (concept, kind)
            assert artifact.citations, (concept, kind)
            assert artifact.mode == 'grounded-offline'
            assert 'no language model was used' in ' '.join(artifact.notes).lower()


def test_generated_quiz_items_name_the_error_process_behind_each_distractor():
    ctx = tool_ctx()
    artifact = generate.compose(ctx, CURVE, 'quiz', {'count': 8})
    items = artifact.blocks[0]['items']
    assert items
    assert any(item['origin'] == 'authored' for item in items)
    generated = [item for item in items if item['origin'] == 'generated']
    assert generated, 'a curve concept should yield generated numeric items'
    for item in generated:
        assert item['review_required'] is True
        assert item['options'] and item['answer_id']
        assert item['error_processes'], item
        assert all(process['reason'] for process in item['error_processes'].values())
        assert item['answer_id'] not in item['error_processes']


def test_generated_numeric_items_are_mathematically_correct():
    """The answer key is computed by the engine, so it must agree with the expression."""
    ctx = tool_ctx()
    artifact = generate.compose(ctx, CURVE, 'quiz', {'count': 12})
    checked = 0
    for item in artifact.blocks[0]['items']:
        if item['origin'] != 'generated' or 'Evaluate' not in item['stem']:
            continue
        expression = item['stem'].split('Evaluate ', 1)[1].rsplit(' at ', 1)[0]
        variable, raw = item['stem'].rsplit(' at ', 1)[1].rstrip('.').split(' = ')
        from app.mathkit import evaluate, parse
        tree = parse(expression, variables=(variable,))
        expected = evaluate(tree, {variable: float(raw)})
        chosen = next(o['text'] for o in item['options'] if o['id'] == item['answer_id'])
        assert abs(float(chosen) - expected) < 1e-6, item['stem']
        checked += 1
    assert checked >= 2


def test_quiz_falls_back_to_a_concept_item_when_no_numeric_item_applies():
    ctx = tool_ctx()
    artifact = generate.compose(ctx, SCENE, 'quiz', {'count': 8})
    stems = [item['stem'] for item in artifact.blocks[0]['items']]
    assert any('Which statement describes' in stem for stem in stems)


def test_slide_deck_carries_speaker_notes_and_a_real_figure():
    ctx = tool_ctx()
    deck = generate.compose(ctx, CURVE, 'slide_deck', {})
    slides = deck.blocks[0]['slides']
    assert len(slides) >= 6
    assert all(slide.get('title') for slide in slides)
    assert any('speaker_notes' in slide and slide['speaker_notes'] for slide in slides)
    figure_slides = [slide for slide in slides if slide.get('figure')]
    assert figure_slides and figure_slides[0]['figure']['series']


def test_deck_renders_to_a_self_contained_svg_for_print_and_export():
    ctx = tool_ctx()
    deck = generate.compose(ctx, CURVE, 'slide_deck', {'include_svg_preview': True})
    preview = [block for block in deck.blocks if block['type'] == 'figure']
    assert preview and preview[0]['caption'] == 'Title slide'
    tree = ElementTree.fromstring(preview[0]['svg'])
    assert tree.attrib['width'] == '640'
    # The figure is embedded, so a printed slide and the live figure cannot disagree.
    assert len(list(tree.iter())) > 10


def test_svg_renderer_escapes_text_so_a_concept_title_cannot_inject_markup():
    svg = render.figure_svg({'figure': 'scene', 'parts': [
        {'label': '<script>alert(1)</script>', 'denominator': 2, 'shaded': 1}]},
        title='<b>x</b>')
    ElementTree.fromstring(svg)
    assert '<script>' not in svg and '&lt;script&gt;' in svg


def test_figure_svg_is_valid_and_draws_a_scene_as_bars_not_a_line():
    ctx = tool_ctx()
    curve = generate.compose(ctx, CURVE, 'figure', {}).blocks[0]['svg']
    ElementTree.fromstring(curve)
    assert '<polyline' in curve
    scene = generate.compose(ctx, SCENE, 'figure', {}).blocks[0]['svg']
    ElementTree.fromstring(scene)
    assert '<rect' in scene and '<polyline' not in scene


def test_image_brief_always_ships_a_deterministic_fallback():
    ctx = tool_ctx()
    brief = generate.compose(ctx, CURVE, 'image_brief', {})
    assert brief.metadata['requires_api'] == 'image-generation-api'
    assert brief.metadata['must_avoid'] and brief.metadata['alt_text']
    assert brief.metadata['fallback_svg'].startswith('<svg')


def test_flashcards_include_cards_built_from_the_learner_record(database, learner):
    memory.remember(database, learner.id, 'semantic',
                    'On quadratics, selected the option consistent with a sign error.',
                    concept_id=CURVE)
    ctx = tool_ctx(database, learner)
    cards = generate.compose(ctx, CURVE, 'flashcards', {'count': 12}).blocks[0]['items']
    assert any('personal' in card['tags'] for card in cards)
    assert len(cards) <= 12


def test_generation_rejects_an_unknown_kind_and_concept():
    ctx = tool_ctx()
    with pytest.raises(ValueError):
        generate.compose(ctx, CURVE, 'hologram', {})
    with pytest.raises(ValueError):
        generate.compose(ctx, 'not_a_concept', 'explanation', {})


def test_a_failing_model_degrades_to_the_deterministic_artifact():
    """The harness must not become unavailable because a provider is misconfigured."""
    settings = replace(Settings.from_env(), provider='openai', provider_url='http://127.0.0.1:1',
                       provider_key='k', provider_model='m', provider_timeout=0.4)
    ctx = tool_ctx(settings=settings)
    artifact = generate.compose(ctx, CURVE, 'explanation', {})
    assert artifact.blocks and artifact.citations
    assert artifact.mode == 'grounded-offline'
    assert any('unavailable' in note or 'deterministically' in note for note in artifact.notes)


# ----------------------------------------------------------------- loop

def base_evidence(**overrides):
    evidence = {'concept_id': CURVE, 'title': 'Quadratics', 'has_lesson': True, 'has_figure': True,
                'mastery': 0.4, 'attempts': 3, 'due': False, 'due_in_seconds': 900,
                'last_correct': True, 'sample': 4, 'recent_accuracy': 0.5, 'recent_errors': [],
                'top_error': '', 'mean_elapsed': 40.0, 'elapsed_trend': 'flat',
                'mean_confidence': 0.7, 'reasoning_written': 0, 'weak_prerequisites': [],
                'prerequisite_count': 1, 'dependant_count': 3, 'unit_mastered': 1, 'unit_size': 8,
                'project_status': 'not_started', 'simulation_touched': False,
                'memory': {'count': 0, 'notes': [], 'digest': ''}, 'history': {},
                'recent_moves': [], 'active_minutes_today': 10.0}
    evidence.update(overrides)
    return evidence


def test_scoring_covers_every_move_and_is_deterministic():
    evidence = base_evidence()
    first = loop.score_moves(evidence)
    second = loop.score_moves(evidence)
    assert [c.move for c in first] == [c.move for c in second]
    assert {c.move for c in first} == set(loop.MOVES)
    assert all(0.0 <= c.score <= 1.0 for c in first)
    assert all(c.reason for c in first)
    assert first == sorted(first, key=lambda c: (-c.score, loop.MOVES.index(c.move)))


def test_an_unattempted_concept_is_taught_or_oriented_not_drilled():
    assert loop.choose(base_evidence(attempts=0, sample=0, mastery=0.15)).move in {'explain', 'orient'}
    assert loop.choose(base_evidence(attempts=0, sample=0, mastery=0.15, has_lesson=False)).move == 'orient'


def test_a_due_concept_is_retrieved():
    chosen = loop.choose(base_evidence(mastery=0.75, attempts=5, sample=5, recent_accuracy=0.8,
                                       due=True, last_correct=True))
    assert chosen.move == 'retrieve'


def test_a_conceptual_error_prefers_a_change_of_representation():
    chosen = loop.choose(base_evidence(mastery=0.45, top_error='conceptual', sample=4,
                                       recent_accuracy=0.25, simulation_touched=False))
    assert chosen.move in {'simulate', 'explain'}


def test_fast_wrong_attempts_are_treated_as_overload_not_as_a_reason_to_drill():
    chosen = loop.choose(base_evidence(mastery=0.3, sample=4, recent_accuracy=0.0,
                                       elapsed_trend='much_faster', active_minutes_today=50.0))
    assert chosen.move in {'rest', 'simulate'}


def test_strong_mastery_opens_applied_work():
    chosen = loop.choose(base_evidence(mastery=0.9, attempts=6, sample=6, recent_accuracy=0.9,
                                       reasoning_written=3, unit_mastered=5, due=False))
    assert chosen.move in {'project', 'discuss', 'consolidate'}


def test_repetition_is_itself_a_reason_to_change_format():
    chosen = loop.choose(base_evidence(recent_moves=['retrieve', 'retrieve', 'retrieve'],
                                       mastery=0.5))
    assert chosen.move != 'retrieve'
    generate_candidate = next(c for c in loop.score_moves(
        base_evidence(recent_moves=['retrieve'] * 3)) if c.move == 'generate')
    assert 'variety' in generate_candidate.reason


def test_a_concept_with_no_figure_cannot_be_simulated():
    candidates = {c.move: c for c in loop.score_moves(base_evidence(has_figure=False))}
    assert candidates['simulate'].score <= 0.05
    assert 'no generated figure' in candidates['simulate'].reason


def test_measured_progress_shifts_the_next_decision(database, learner):
    evidence = base_evidence(mastery=0.55, attempts=4, sample=4, recent_accuracy=0.6)
    baseline = {c.move: c.score for c in loop.score_moves(evidence)}
    for _ in range(3):
        row = HarnessRun(id=f'run-{_}', user_id=learner.id, concept_id=CURVE, move='simulate',
                         reason='seed', evidence={}, chosen=True, outcome={'progress': 0.2})
        database.add(row)
    database.commit()
    assert loop.effectiveness(database, learner.id)['simulate']['positive'] == 3
    evidence['history'] = loop.effectiveness(database, learner.id)
    boosted = {c.move: c.score for c in loop.score_moves(evidence)}
    assert boosted['simulate'] > baseline['simulate']


def test_evidence_counts_only_incorrect_responses_as_errors(database, learner, settings):
    """A correct response has a category too; it must not be reported as an error."""
    from app.db import Attempt, Receipt
    from app.db import now_ts as stamp
    # An attempt is stored against the authored lesson, because that is what a question
    # belongs to. The graph node id is the other namespace, and the loop resolves either.
    lesson = GRAPH_TO_LESSON[CURVE]
    rows = [(True, 'supported_correct'), (False, 'conceptual'), (False, 'conceptual'),
            (False, 'calculation')]
    for index, _ in enumerate(rows):
        database.add(Receipt(id=f'r{index}', user_id=learner.id, question_id='q', mode='practice',
                             issued_at=0, expires_at=stamp() + 600))
    database.flush()
    for index, (correct, category) in enumerate(rows):
        database.add(Attempt(id=f'a{index}', user_id=learner.id, receipt_id=f'r{index}',
                             client_event_id=f'e{index}', question_id='q', concept_id=lesson,
                             mode='practice', correct=correct, elapsed_seconds=20.0,
                             category=category, payload={}, payload_hash='h', response={}))
    database.commit()
    ctx = tool_ctx(database, learner, settings)
    # The loop is asked in the node namespace; the tool is asked in the node namespace too.
    # Both must find the same rows.
    evidence = loop.gather(ctx, CURVE)
    assert evidence['recent_accuracy'] == pytest.approx(0.25)
    assert evidence['top_error'] == 'conceptual'
    assert {row['category'] for row in evidence['recent_errors']} == {'conceptual', 'calculation'}
    tool_view = toolbox.read_learner_evidence(ctx, CURVE)
    assert tool_view.data['correct'] == 1 and tool_view.data['incorrect'] == 3
    assert all(row['category'] != 'supported_correct'
               for row in tool_view.data['error_categories'])


def test_plan_records_the_decision_and_the_outcome_feeds_back(database, learner, settings):
    ctx = tool_ctx(database, learner, settings)
    decision = loop.plan(ctx, CURVE)
    stored = database.scalar(select(HarnessRun).where(HarnessRun.id == decision.run_id))
    assert stored is not None and stored.chosen is True
    assert stored.evidence['concept_id'] == CURVE
    result = loop.record_outcome(ctx, decision.run_id, {'progress': 0.3, 'mastery_after': 0.7})
    assert result['outcome']['progress'] == 0.3
    notes = memory.recall(database, learner.id, kinds=['procedural'])
    assert notes and 'followed by progress' in notes[0].text
    with pytest.raises(ValueError):
        loop.record_outcome(ctx, 'no-such-run', {'progress': 0.1})


def test_an_active_exam_suppresses_teaching_moves(database, learner, settings):
    ctx = tool_ctx(database, learner, settings)
    decision = loop.plan(ctx, CURVE, exam_active=True)
    assert decision.move == 'rest'
    assert any('stands down' in note for note in decision.constraints)
    excluded = [c for c in decision.candidates if c.move != 'rest']
    assert excluded and all(c.score == 0.0 for c in excluded)
    assert all('unavailable' in c.reason for c in excluded)


def test_gather_reads_real_learner_state(database, learner, settings):
    # Learner state is keyed by the authored lesson, because that is what a question
    # belongs to; the graph node is the other namespace.
    lesson = GRAPH_TO_LESSON[CURVE]
    database.add(State(user_id=learner.id, concept_id=lesson,
                       data={'mastery': 0.62, 'attempts': 4, 'due_at': 0.0, 'last_correct': True}))
    database.commit()
    ctx = tool_ctx(database, learner, settings)
    evidence = loop.gather(ctx, CURVE)
    assert evidence['mastery'] == pytest.approx(0.62)
    assert evidence['attempts'] == 4
    assert evidence['due'] is True
    assert evidence['concept_id'] == CURVE
    # Asking with the lesson id must reach the same evidence.
    assert loop.gather(ctx, lesson)['concept_id'] == CURVE
    assert loop.gather(ctx, lesson)['mastery'] == pytest.approx(0.62)


def test_explain_decision_is_reviewable():
    decision = loop.Decision(run_id='r', move='explain', reason='because', evidence=base_evidence(),
                             candidates=loop.score_moves(base_evidence()), tool_plan=[], constraints=[],
                             concept_id=CURVE, created_at=0.0)
    account_view = loop.explain(decision)
    assert account_view['chosen'] == 'explain'
    assert account_view['runner_up']['move'] != 'explain'
    assert account_view['scored'] and account_view['top_signals']


# ----------------------------------------------------------------- prompt

def test_system_prompt_carries_the_contract_and_the_live_tool_list():
    rendered = prompt.build('Ada', 'Quadratics', '- [semantic · quadratics · observed 2x] sign error')
    assert 'Ada' in rendered and 'Quadratics' in rendered
    assert 'sign error' in rendered
    # Every tool this build can actually run is listed, and nothing else is: the section
    # opens by promising that an unlisted tool is unavailable to the model, so listing one
    # whose optional package is missing would make that sentence false and cost the model
    # a turn discovering it. browser_snapshot needs playwright, which the desktop bundle
    # excludes on purpose, so it is registered without being offered.
    for spec in toolbox.available_specs():
        assert spec.name in rendered
    for spec in toolbox.unavailable_specs():
        assert spec.name not in rendered
        assert spec.requires, 'an unavailable tool must name the module it is missing'
    assert {spec.name for spec in toolbox.available_specs()} | \
           {spec.name for spec in toolbox.unavailable_specs()} == set(toolbox.REGISTRY)
    for move in loop.MOVES:
        assert f'- {move}:' in rendered
    assert 'certified grade' in rendered
    assert 'cognitive attention' in rendered
    assert 'link-only' in rendered
    payload = prompt.payload('Ada', 'Quadratics', 'digest')
    assert payload['tools'] and payload['moves'] and payload['sandbox']['languages'] == ['python']
    # The transparency panel reports the same list the rendered prompt carries, so it can
    # never show a tool the model was not told about.
    assert [entry['name'] for entry in payload['tools']] == \
           [spec.name for spec in toolbox.available_specs()]
    assert payload['rendered'] == prompt.build('Ada', 'Quadratics', 'digest')


def test_harness_status_is_self_describing():
    status = harness.status()
    assert status['moves'] == list(loop.MOVES)
    assert status['memory_half_life_days'] == pytest.approx(21.0, abs=0.1)
    assert set(status['memory_kinds']) == {'episodic', 'semantic', 'procedural'}
    assert status['sandbox']['boundaries']


# ----------------------------------------------------------------- API

def test_harness_endpoints_require_authentication(client):
    for path in ('/api/v1/harness/status', '/api/v1/harness/tools', '/api/v1/harness/memory',
                 '/api/v1/harness/runs', '/api/v1/harness/workspace'):
        assert client.get(path).status_code == 401
    assert client.post('/api/v1/harness/generate',
                       json={'concept_id': CURVE, 'kind': 'quiz'}).status_code == 401


def test_harness_status_and_tools_endpoints(client):
    headers, _ = account(client)
    status = client.get('/api/v1/harness/status', headers=headers)
    assert status.status_code == 200
    body = status.json()
    assert body['moves'] and body['tools'] and body['artefacts']
    tools = client.get('/api/v1/harness/tools', headers=headers).json()
    assert tools['postures']['sandboxed'] >= 4
    assert tools['sandbox']['max_timeout_seconds'] <= 60
    assert any(entry['kind'] == 'slide_deck' for entry in tools['artefacts'])


def test_harness_prompt_endpoint_exposes_what_the_model_is_told(client):
    headers, _ = account(client)
    response = client.get('/api/v1/harness/prompt', headers=headers, params={'concept_id': LESSON})
    assert response.status_code == 200
    body = response.json()
    assert body['concept'] == KNOWLEDGE_GRAPH.nodes[LESSON_TARGETS[LESSON]].title
    assert body['rendered'] and body['tools'] and body['refusals']
    assert client.get('/api/v1/harness/prompt', headers=headers,
                      params={'concept_id': 'nope'}).status_code == 404


def test_harness_plan_endpoint_accepts_a_lesson_id_and_can_execute(client):
    headers, _ = account(client)
    response = client.get('/api/v1/harness/plan', headers=headers,
                          params={'concept_id': LESSON, 'execute': True})
    assert response.status_code == 200
    body = response.json()
    assert body['decision']['move'] in loop.MOVES
    assert body['decision']['run_id']
    assert body['decision']['concept_id'] == LESSON_TARGETS[LESSON]
    assert body['explanation']['chosen'] == body['decision']['move']
    assert body['results'], 'execute=true should run the planned tools'
    assert all(entry['ok'] for entry in body['results'])
    assert client.get('/api/v1/harness/plan', headers=headers,
                      params={'concept_id': 'nope'}).status_code == 404


def test_attempts_write_memory_that_the_api_then_reports(client):
    headers, registered = account(client)
    question = next_q(client, headers)
    result = client.post('/api/v1/attempts', headers=headers, json=answer(question, correct=False))
    assert result.status_code == 200
    notes = client.get('/api/v1/harness/memory', headers=headers).json()
    assert notes['notes'], 'a scored attempt must leave a durable record'
    kinds = {note['kind'] for note in notes['notes']}
    assert 'episodic' in kinds
    assert all(note['confidence'] <= memory.CEILING for note in notes['notes'])
    assert notes['summary']['total'] == len(notes['notes'])
    assert 'three-week half-life' in notes['scope']


def test_memory_can_be_deleted_by_note_and_wholesale(client):
    headers, _ = account(client)
    question = next_q(client, headers)
    client.post('/api/v1/attempts', headers=headers, json=answer(question, correct=False))
    notes = client.get('/api/v1/harness/memory', headers=headers).json()['notes']
    assert len(notes) >= 2, 'an incorrect answer leaves both an episodic and a semantic note'
    assert client.delete(f"/api/v1/harness/memory/{notes[0]['id']}", headers=headers).status_code == 204
    assert client.delete('/api/v1/harness/memory/does-not-exist', headers=headers).status_code == 404
    wiped = client.delete('/api/v1/harness/memory', headers=headers)
    assert wiped.status_code == 200 and wiped.json()['deleted'] == len(notes) - 1
    assert client.get('/api/v1/harness/memory', headers=headers).json()['notes'] == []
    assert client.delete('/api/v1/harness/memory', headers=headers).json()['deleted'] == 0


def test_outcome_endpoint_closes_the_learning_loop(client):
    headers, _ = account(client)
    planned = client.get('/api/v1/harness/plan', headers=headers,
                         params={'concept_id': LESSON}).json()
    run_id = planned['decision']['run_id']
    recorded = client.post(f'/api/v1/harness/plan/{run_id}/outcome', headers=headers,
                           json={'progress': 0.4, 'mastery_after': 0.75, 'note': 'worked'})
    assert recorded.status_code == 200
    assert recorded.json()['outcome']['progress'] == 0.4
    runs = client.get('/api/v1/harness/runs', headers=headers).json()
    assert any(run['id'] == run_id for run in runs['runs'])
    assert 'unmeasured move is unknown' in runs['note']
    assert client.post('/api/v1/harness/plan/nope/outcome', headers=headers,
                       json={'progress': 0.1}).status_code == 404
    assert client.post(f'/api/v1/harness/plan/{run_id}/outcome', headers=headers,
                       json={'progress': 5}).status_code == 422


def test_generate_endpoint_returns_a_grounded_artifact(client):
    headers, _ = account(client)
    response = client.post('/api/v1/harness/generate', headers=headers,
                           json={'concept_id': LESSON, 'kind': 'slide_deck', 'count': 4})
    assert response.status_code == 200
    body = response.json()
    assert body['kind'] == 'slide_deck'
    assert body['citations'] and body['blocks']
    assert body['mode'] == 'grounded-offline'
    assert client.post('/api/v1/harness/generate', headers=headers,
                       json={'concept_id': LESSON, 'kind': 'hologram'}).status_code == 422
    assert client.post('/api/v1/harness/generate', headers=headers,
                       json={'concept_id': 'nope', 'kind': 'quiz'}).status_code == 404


def test_workspace_endpoints_write_read_list_and_delete(client):
    headers, _ = account(client)
    created = client.post('/api/v1/harness/workspace/files', headers=headers,
                          json={'path': 'decks/quadratics.json', 'content': '{"slides": 8}'})
    assert created.status_code == 201 and created.json()['bytes'] == 13
    listing = client.get('/api/v1/harness/workspace', headers=headers).json()
    assert any(entry['path'] == 'decks/quadratics.json' for entry in listing['files'])
    assert listing['root'].startswith('workspaces/')
    read = client.get('/api/v1/harness/workspace/files/decks/quadratics.json', headers=headers)
    assert read.status_code == 200 and read.json()['content'] == '{"slides": 8}'
    assert client.get('/api/v1/harness/workspace/files/missing', headers=headers).status_code == 404
    assert client.delete('/api/v1/harness/workspace/files/decks/quadratics.json',
                         headers=headers).status_code == 204
    assert client.delete('/api/v1/harness/workspace/files/decks/quadratics.json',
                         headers=headers).status_code == 404
    escaped = client.post('/api/v1/harness/workspace/files', headers=headers,
                          json={'path': '../../escape.txt', 'content': 'x'})
    assert escaped.status_code == 422


def test_workspace_run_endpoint_executes_and_refuses(client):
    headers, _ = account(client)
    ok = client.post('/api/v1/harness/workspace/run', headers=headers,
                     json={'language': 'python', 'code': 'print(6 * 7)'})
    assert ok.status_code == 200
    body = ok.json()
    assert body['ok'] and body['stdout'].strip() == '42'
    assert body['boundaries'] and body['boundary']
    # A failing script is a successful run that reported a failure.
    failed = client.post('/api/v1/harness/workspace/run', headers=headers,
                         json={'language': 'python', 'code': 'raise SystemExit(3)'})
    assert failed.status_code == 200 and failed.json()['ok'] is False
    refused = client.post('/api/v1/harness/workspace/run', headers=headers,
                          json={'language': 'python', 'code': 'import socket'})
    assert refused.status_code == 422
    assert 'not permitted' in refused.json()['detail']


def test_export_and_delete_cover_the_harness_records(client):
    headers, registered = account(client)
    question = next_q(client, headers)
    client.post('/api/v1/attempts', headers=headers, json=answer(question, correct=False))
    client.get('/api/v1/harness/plan', headers=headers, params={'concept_id': LESSON})
    exported = client.get('/api/v1/export', headers=headers).json()
    assert exported['schema_version'] == SCHEMA_VERSION
    assert SCHEMA_VERSION >= 3, 'the harness tables require at least schema v3'
    assert exported['memory_notes'], 'export must include the harness beliefs'
    assert exported['harness_runs'], 'export must include the harness decisions'
    assert all('evidence' in note for note in exported['memory_notes'])
    assert client.request('DELETE', '/api/v1/me', headers=headers,
                          json={'confirmation': 'DELETE MY ACCOUNT'}).status_code == 204
    with client.app.state.factory() as db:
        assert db.scalars(select(MemoryNote).where(MemoryNote.user_id == registered['user']['id'])).all() == []
        assert db.scalars(select(HarnessRun).where(HarnessRun.user_id == registered['user']['id'])).all() == []


def test_health_reports_the_harness_posture(client):
    body = client.get('/api/v1/health').json()
    assert body['harness']['moves'] == len(loop.MOVES)
    assert body['harness']['tools'] >= 14
    assert body['harness']['memory_half_life_days'] == pytest.approx(21.0, abs=0.1)
    assert body['harness']['sandbox_boundaries']
    assert body['harness']['generation_mode'] == 'grounded-offline'


def test_harness_help_is_withheld_during_an_active_exam(client):
    headers, _ = account(client)
    client.get('/api/v1/questions/next', headers=headers, params={'mode': 'exam'})
    blocked = client.post('/api/v1/harness/generate', headers=headers,
                          json={'concept_id': LESSON, 'kind': 'quiz'})
    assert blocked.status_code == 403
    plan = client.get('/api/v1/harness/plan', headers=headers, params={'concept_id': LESSON})
    assert plan.status_code == 200
    assert plan.json()['decision']['move'] == 'rest'
    assert 'stands down' in plan.json()['decision']['reason']
    unavailable = {c['move']: c for c in plan.json()['decision']['candidates']}
    assert unavailable['explain']['score'] == 0.0
    assert 'exam is active' in unavailable['explain']['reason']


# ----------------------------------------------------------------- migration

def test_schema_v2_migrates_to_v3_without_losing_data(settings):
    from sqlalchemy import inspect, text
    from scripts.init_db import initialize
    engine, factory = make_database(settings)
    with engine.begin() as connection:
        connection.execute(text(
            'CREATE TABLE users (id VARCHAR(36) PRIMARY KEY, name VARCHAR(100) NOT NULL, '
            'email VARCHAR(254) UNIQUE NOT NULL, password_hash TEXT NOT NULL, goal VARCHAR(500) NOT NULL, '
            'daily_minutes INTEGER NOT NULL, telemetry_consent BOOLEAN NOT NULL, '
            'training_consent BOOLEAN NOT NULL DEFAULT FALSE, created_at FLOAT NOT NULL, '
            'last_heartbeat FLOAT)'))
        connection.execute(text(
            "INSERT INTO users VALUES ('v2-user', 'Existing', 'v2@example.test', 'hash', 'Learn', "
            '20, FALSE, FALSE, 1, NULL)'))
        connection.execute(text('CREATE TABLE schema_version (id INTEGER PRIMARY KEY, version INTEGER NOT NULL)'))
        connection.execute(text('INSERT INTO schema_version VALUES (1, 2)'))
    initialize(engine)
    inspector = inspect(engine)
    assert {'memory_notes', 'harness_runs'} <= set(inspector.get_table_names())
    with factory() as db:
        assert db.get(User, 'v2-user').name == 'Existing'
        assert db.execute(text('SELECT version FROM schema_version WHERE id = 1')).scalar() == SCHEMA_VERSION
    engine.dispose()


def test_a_database_from_the_future_is_refused(settings):
    from sqlalchemy import text
    from scripts.init_db import initialize
    engine, _ = make_database(settings)
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE schema_version (id INTEGER PRIMARY KEY, version INTEGER NOT NULL)'))
        connection.execute(text('INSERT INTO schema_version VALUES (1, 99)'))
    with pytest.raises(ValueError):
        initialize(engine)
    engine.dispose()


def test_the_dialogue_ladder_is_attached_to_every_decision(database, learner, settings):
    """The ladder is a policy, not a decoration: every decision carries the next dialogue
    move, and a learner with no failed cycle is pumped rather than told."""
    ctx = tool_ctx(database, learner, settings)
    decision = loop.plan(ctx, CURVE)
    assert decision.dialogue is not None
    assert decision.dialogue['move'] == 'pump'
    assert decision.dialogue['reveal_answer'] is False
    assert decision.to_dict()['dialogue']['move'] == 'pump'


def test_two_failed_cycles_escalate_the_ladder_without_revealing_the_answer(
        database, learner, settings):
    from app.db import Attempt, Receipt
    from app.db import now_ts as stamp

    lesson = GRAPH_TO_LESSON[CURVE]
    for index in range(2):
        database.add(Receipt(id=f'dr{index}', user_id=learner.id, question_id='q',
                             mode='practice', issued_at=0, expires_at=stamp() + 600))
    database.flush()
    for index in range(2):
        database.add(Attempt(id=f'da{index}', user_id=learner.id, receipt_id=f'dr{index}',
                             client_event_id=f'de{index}', question_id='q',
                             concept_id=lesson, mode='practice', correct=False,
                             elapsed_seconds=20.0, category='conceptual', payload={},
                             payload_hash='h', response={}))
    database.commit()

    ctx = tool_ctx(database, learner, settings)
    decision = loop.plan(ctx, CURVE)
    assert decision.evidence['consecutive_failures'] == 2
    assert decision.dialogue['move'] == 'prompt'
    # Two failures is not yet enough to hand over the step; that is the assertion rung.
    assert decision.dialogue['reveal_answer'] is False
