"""The lesson procedure: what the harness decides, and that the decision is followed.

``test_teacher_core.py`` proves the *move* policy is right for one turn. This file proves
the layer above it - the run of show a turn sits inside - and it is written around the
four rules the compiler claims to obey, because those four are the whole feature:

1. **An activity is chosen by what it does to evidence, not by what it looks like.**
   Practice produces a scored observation, so it is always present; a deck produces none,
   so it is skipped for a learner who is already answering above the bar.
2. **One input per lesson.** Deck, video, explain and worked example are alternatives,
   never a sequence. A lesson that shows a video *and* a deck has spent the budget twice
   on the same job.
3. **Only artifacts that exist may be promised.** A missing simulation is a published
   reason, not an empty block, and a video is never a generic provider link.
4. **The budget is a contract.** A short session is a *smaller* lesson, not a truncated
   one, and every refusal says which rule refused it.

Then it proves the decision is *delivered*: the compiled block reaches the system prompt
the provider actually receives, on both the prose and the agent path, and the progress
record moves when a block is advanced.

Nothing in the first half needs a database - the compiler is a pure function, which is
what makes it reviewable. The second half drives a real app.
"""

import httpx
import pytest
from sqlalchemy import select

from app import procedure_service
from app import tutor as tutor_module
from app.config import Settings
from app.curriculum import CONCEPTS
from app.db import Attempt, ProcedureRun, State, User
from app.harness.teaching import (ACTIVITIES, INPUT_KINDS, ConceptFacts, ProcedureAssets,
                                  build_evidence, compile_procedure, default_profile,
                                  procedure_hash, render_procedure_block)
from app.main import create_app

CONCEPT = 'fractions'

#: Every activity the vocabulary allows, in the order the compiler may emit them.
ALL_KINDS = ('diagnostic', 'deck', 'video', 'explain', 'worked_example', 'simulation',
             'practice', 'discussion', 'recap', 'close')


# --------------------------------------------------------------------- helpers

def facts(**overrides) -> ConceptFacts:
    """A mathematics concept with an authored lesson, a figure and a prerequisite."""
    base = dict(id='algebra.fractions', title='Fractions', strand='Algebra', tier='core',
                depth=1, prerequisite_count=1, dependant_count=2, has_lesson=True,
                has_figure=True, has_video=False, subject_kind='mathematics',
                concept_type='quantitative_relation', keywords=('fraction', 'denominator'))
    base.update(overrides)
    return ConceptFacts(**base)


def assets(**overrides) -> ProcedureAssets:
    """Everything this instance can deliver, by default: the generous case."""
    base = dict(
        concept_id='algebra.fractions', concept_title='Fractions',
        course_id='integrated_math_1',
        deck_sections=({'heading': 'Fractions', 'bullets': ['A fraction is parts of a whole.'],
                        'notes': 'A fraction is parts of a whole.'},
                       {'heading': 'Check yourself', 'bullets': ['Add 2/3 and 1/4.'],
                        'notes': 'Add 2/3 and 1/4.'}),
        simulation={'mode': 'playground', 'slug': 'fraction-bars', 'title': 'Fraction bars',
                    'observable': True, 'play_url': '/api/v1/playground/games/fraction-bars/html',
                    'objective': 'Rename fractions over a common denominator.',
                    'prompt': 'Predict which bar is longer.', 'minutes': 5},
        video={'provider': 'youtube', 'title': 'Fractions, explained',
               'channel': 'Curated', 'watch_url': 'https://example.test/watch',
               'embed_url': 'https://example.test/embed', 'licence_class': 'embed_only',
               'attribution': 'Curated', 'why': 'Concept-specific.'},
        worked_example={'body': 'To add 2/3 and 1/4, choose twelfths.', 'block_index': 2},
        practice_prompts=('Add 2/3 and 1/4.', 'Are 2/6 and 1/3 the same?'),
        practice_count=4, prerequisites=('Place value',), dependants=('Ratios',))
    base.update(overrides)
    return ProcedureAssets(**base)


def evidence(facts_=None, state=None, **kw):
    profile = kw.pop('profile', None) or default_profile()
    return build_evidence(facts_ or facts(), state or {},
                          mastery_threshold=profile.difficulty.mastery_threshold, **kw)


def lesson(facts_=None, assets_=None, budget=20, recent=(), **evidence_kw):
    """Compile with defaults a caller would actually have."""
    return compile_procedure(facts_ or facts(), evidence(facts_, **evidence_kw),
                             assets_ if assets_ is not None else assets(),
                             default_profile(), minutes_budget=budget,
                             recent_kinds=recent)


def kinds_of(procedure):
    return tuple(block.kind for block in procedure.blocks)


def skipped_kinds(procedure):
    return tuple(row['kind'] for row in procedure.skipped)


def reason_for(procedure, kind):
    return next((row['reason'] for row in procedure.skipped if row['kind'] == kind), '')


# ------------------------------------------------------- 1. the input rules

def test_exactly_one_input_block_is_ever_emitted():
    """Deck, video, explain and worked example are alternatives, not a sequence.

    Swept across the evidence states that select each of them in turn: first exposure with
    no video curated (deck), first exposure with one (video), a procedural error (worked
    example), a concept with nothing but prose (explain), and a capable learner (none). The
    invariant holds in every one.
    """
    seen = set()
    cases = [
        lesson(assets_=assets(video=None)),
        lesson(facts_=facts(subject_kind='science')),
        lesson(top_error='procedural'),
        lesson(assets_=assets(deck_sections=(), video=None, simulation=None)),
        lesson(state={'mastery': 0.9, 'attempts': 6, 'correct_count': 6}),
        lesson(budget=6),
        lesson(budget=45),
    ]
    for procedure in cases:
        inputs = [kind for kind in kinds_of(procedure) if kind in INPUT_KINDS]
        assert len(inputs) <= 1, (inputs, kinds_of(procedure))
        seen.update(inputs)
    # The sweep must actually have exercised more than one branch, or the invariant above
    # is being proved on a single code path.
    assert len(seen) >= 3, seen


def test_a_capable_learner_is_not_shown_an_input_at_all():
    """Mastery above the bar means practice teaches them; a deck would spend the budget
    on what they already know."""
    procedure = lesson(state={'mastery': 0.92, 'attempts': 8, 'correct_count': 8})
    assert not [kind for kind in kinds_of(procedure) if kind in INPUT_KINDS]
    assert 'practice' in kinds_of(procedure)
    # The refusal is published with the measurement that caused it and the bar it crossed,
    # not a shrug: a learner asking "why no deck?" gets an answer.
    reason = reason_for(procedure, 'deck')
    assert '1.00' in reason and '0.80 bar' in reason


def test_a_procedural_error_prefers_the_worked_example_over_the_deck():
    """A wrong *process* is repaired by a solved instance, not by an ordered overview."""
    procedure = lesson(top_error='procedural')
    assert 'worked_example' in kinds_of(procedure)
    assert 'deck' not in kinds_of(procedure)
    assert 'procedural' in reason_for(procedure, 'deck')


def test_first_exposure_to_a_science_concept_opens_with_the_curated_video():
    """A video orients a phenomenon well and repairs a specific error badly, so it opens
    only on first exposure and only where the subject is a phenomenon."""
    procedure = lesson(facts_=facts(subject_kind='science'))
    assert kinds_of(procedure)[:2] == ('diagnostic', 'video')

    # The same concept, same video, but already attempted: the video is no longer the
    # right opener, because the learner's error points at a representation instead.
    attempted = lesson(facts_=facts(subject_kind='science'),
                       state={'mastery': 0.4, 'attempts': 3, 'correct_count': 1})
    assert 'video' not in kinds_of(attempted)


def test_first_exposure_opens_with_the_video_whatever_the_subject():
    """The subject no longer decides the opener; whether a curated video exists does.

    This reverses an earlier rule that admitted only science, social science and computing,
    on the grounds that a mathematics concept with an authored deck is better served by the
    deck. A curated, embed-verified video is now the default opener on first exposure for
    every subject, and the deck becomes consolidation. The gate that remains is existence:
    no curated video still means the deck opens, and nothing invents one.
    """
    for kind in ('mathematics', 'science', 'social_science', 'computing'):
        procedure = lesson(facts_=facts(subject_kind=kind))
        assert kinds_of(procedure)[:2] == ('diagnostic', 'video'), kind
        # The deck is skipped *because* the video replaced it, and says so.
        assert 'video' in reason_for(procedure, 'deck')

    without = lesson(assets_=assets(video=None))
    assert kinds_of(without)[:2] == ('diagnostic', 'deck')


def test_a_video_is_never_invented_when_none_is_curated():
    """No video means the deck opens, and the skip says why rather than implying one
    exists."""
    procedure = lesson(assets_=assets(video=None))
    assert 'video' not in kinds_of(procedure)
    assert 'deck' in kinds_of(procedure)
    assert reason_for(procedure, 'video')


def test_the_same_deck_is_not_served_twice_in_a_day():
    """Repetition of an *input* is the one form of repetition that produces no evidence."""
    procedure = lesson(recent=('deck',))
    assert 'deck' not in kinds_of(procedure)
    assert 'deck' in skipped_kinds(procedure)


def test_a_concept_with_no_assets_still_teaches_by_explanation():
    """The floor: nothing but prose exists, and the lesson still runs - with the reason
    each missing asset is missing."""
    procedure = lesson(assets_=assets(deck_sections=(), video=None, simulation=None,
                                      worked_example=None))
    assert 'explain' in kinds_of(procedure)
    assert 'practice' in kinds_of(procedure)
    for kind in ('deck', 'video', 'simulation', 'worked_example'):
        assert reason_for(procedure, kind), kind


# ----------------------------------------------------- 2. the simulation gate

def test_the_interactive_is_gated_by_a_mastery_band():
    """Below the floor there is nothing to predict with; above the ceiling the mechanic is
    already fluent. Both refusals state the measurement."""
    low = lesson(state={'mastery': 0.10, 'attempts': 2, 'correct_count': 1})
    assert 'simulation' not in kinds_of(low)
    assert '0.10' in reason_for(low, 'simulation')

    middle = lesson(state={'mastery': 0.45, 'attempts': 3, 'correct_count': 2})
    assert 'simulation' in kinds_of(middle)

    high = lesson(state={'mastery': 0.93, 'attempts': 8, 'correct_count': 8})
    assert 'simulation' not in kinds_of(high)
    assert '0.93' in reason_for(high, 'simulation')


def test_a_first_lesson_may_open_with_the_interactive_because_the_diagnostic_measures():
    """The gate has one exception, and it is reasoned: after a diagnostic the learner has
    just been measured, so the floor no longer applies."""
    procedure = lesson()
    assert kinds_of(procedure)[0] == 'diagnostic'
    assert 'simulation' in kinds_of(procedure)


def test_an_interactive_already_used_this_session_is_not_repeated():
    procedure = lesson(simulation_touched=True, state={'mastery': 0.5, 'attempts': 4,
                                                       'correct_count': 3})
    assert 'simulation' not in kinds_of(procedure)
    assert 'already used' in reason_for(procedure, 'simulation')


def test_an_absent_interactive_is_a_reason_not_an_empty_block():
    """The resolver refuses a generic figure for a non-mathematics subject; the compiler
    must publish that refusal rather than emit a block with nothing in it."""
    procedure = lesson(assets_=assets(simulation=None))
    assert 'simulation' not in kinds_of(procedure)
    assert reason_for(procedure, 'simulation')


# ------------------------------------------------------ 3. the budget contract

@pytest.mark.parametrize('budget', range(6, 46, 2))
def test_the_plan_never_exceeds_its_budget(budget):
    """The budget is a contract, and a lesson that overruns it is the defect the whole
    allocation step exists to prevent."""
    procedure = lesson(budget=budget)
    assert procedure.total_minutes <= procedure.budget_minutes
    assert procedure.total_minutes == sum(block.minutes for block in procedure.blocks)
    assert kinds_of(procedure), 'an empty lesson is not a lesson'


def test_a_short_session_is_a_smaller_lesson_not_a_truncated_one():
    """Six minutes buys a check and a question - not a deck with the practice cut off.

    This is the specific failure the first implementation had: it built a rich lesson and
    trimmed it, which removed the *first* thing (the diagnostic) and kept the last. A
    budget ladder has to drop whole activities from the bottom of the priority list.
    """
    short = lesson(budget=6)
    assert kinds_of(short) == ('diagnostic', 'practice')
    assert short.blocks[-1].kind == 'practice'

    rich = lesson(budget=20)
    # Which input opens is the video-or-deck rule's business, not this test's: what matters
    # here is that a bigger budget buys the interactive and the practice as well.
    assert {'diagnostic', 'simulation', 'practice'} <= set(kinds_of(rich))
    assert len([kind for kind in kinds_of(rich) if kind in INPUT_KINDS]) == 1
    assert rich.total_minutes > short.total_minutes


def test_practice_survives_every_budget_because_it_is_the_only_evidence():
    for budget in (6, 8, 10, 12, 20, 30, 45):
        assert 'practice' in kinds_of(lesson(budget=budget)), budget


def test_an_unobservable_interactive_earns_an_extra_question():
    """The harness saw nothing inside an exploratory figure, so a scored item is the only
    honest way to learn something from that block.

    Tested on the sizing rule itself rather than through a compiled lesson, because a
    generous budget legitimately grows practice to its cap in both cases - which would
    hide the difference the rule exists to make.
    """
    from app.harness.teaching.procedure import _practice_size
    cfg = default_profile().procedure
    state = {'mastery': 0.5, 'attempts': 4, 'correct_count': 3}
    observable = assets(simulation={**assets().simulation, 'observable': True})
    exploratory = assets(simulation={**assets().simulation, 'mode': 'exploratory',
                                     'observable': False})
    seen = evidence(state=state)
    assert (_practice_size(seen, exploratory, cfg)
            == _practice_size(seen, observable, cfg) + 1)


def test_practice_size_follows_mastery_and_the_bank():
    from app.harness.teaching.procedure import _practice_size
    cfg = default_profile().procedure
    floor = _practice_size(evidence(state={'mastery': 0.3, 'attempts': 3,
                                           'correct_count': 1}), assets(), cfg)
    assert floor == cfg.practice_min_items

    # A concept with a single item in the bank cannot promise four.
    thin = lesson(assets_=assets(practice_count=1))
    assert next(b for b in thin.blocks if b.kind == 'practice').artifact['count'] == 1


def test_overload_ends_the_session_instead_of_shrinking_it():
    """Fast and wrong is the signature of overload; a shorter version of the thing that is
    failing is still the thing that is failing."""
    procedure = lesson(state={'mastery': 0.2, 'attempts': 4, 'correct_count': 1},
                       recent_accuracy=0.2, elapsed_trend='much_faster')
    assert kinds_of(procedure) == ('close',)
    assert procedure.blocks[0].artifact['reason'] == 'overload'
    assert set(ALL_KINDS) - {'close'} == set(skipped_kinds(procedure))
    # And the reason is the overload, not the budget: the two stop conditions are
    # different facts and the learner is told which one happened.
    assert 'fast and wrong' in procedure.blocks[0].why


# --------------------------------------------------- 4. the published reasons

def test_every_refusal_carries_a_sentence_and_appears_once():
    """``skipped`` is the audit trail. One entry per activity, never two, and never an
    empty reason."""
    procedure = lesson()
    kinds = skipped_kinds(procedure)
    assert len(kinds) == len(set(kinds))
    assert set(kinds) <= set(ALL_KINDS)
    for row in procedure.skipped:
        assert len(row['reason']) > 20, row
        assert row['label'], row


def test_every_block_names_a_purpose_and_a_reason():
    """A block without a 'why' is an activity the learner cannot question."""
    for block in lesson().blocks:
        assert block.kind in ACTIVITIES
        assert block.title
        assert block.purpose
        assert len(block.why) > 30, block.kind
        assert block.minutes >= 1
        assert block.artifact.get('kind'), block.kind


def test_the_practice_block_promises_the_items_the_bank_actually_holds():
    """The count in the title and the count in the artifact must agree, because a card
    that says '4 example questions' while the artifact says 2 is a lie in the UI."""
    procedure = lesson()
    practice = next(block for block in procedure.blocks if block.kind == 'practice')
    assert str(practice.artifact['count']) in practice.title
    assert practice.artifact['count'] <= procedure.assets['questions']


# ------------------------------------------------ 5. determinism and the hash

def test_the_same_evidence_compiles_the_same_lesson():
    """Nothing reads the clock, the database or the network: same inputs, same bytes."""
    first = lesson()
    second = lesson()
    assert kinds_of(first) == kinds_of(second)
    assert procedure_hash(first) == procedure_hash(second)
    assert [b.to_dict() for b in first.blocks] == [b.to_dict() for b in second.blocks]


def test_the_hash_moves_when_the_lesson_moves_and_not_otherwise():
    base = lesson()
    assert procedure_hash(base) != procedure_hash(lesson(budget=30))
    assert procedure_hash(base) != procedure_hash(
        lesson(state={'mastery': 0.5, 'attempts': 4, 'correct_count': 3}))
    # A different *title* on the same activity is not a different lesson: the hash is
    # over the run of show, so re-rendering copy must not orphan a learner's progress.
    same_shape = lesson(assets_=assets(concept_title='Equivalent fractions'))
    assert procedure_hash(base) == procedure_hash(same_shape)


def test_the_procedure_can_be_switched_off_from_configuration():
    """The teacher is data: one flag in the profile turns the whole layer off."""
    from dataclasses import replace
    profile = replace(default_profile(),
                      procedure=replace(default_profile().procedure, enabled=False))
    procedure = compile_procedure(facts(), evidence(), assets(), profile,
                                  minutes_budget=20)
    assert procedure.blocks == ()
    assert procedure.enabled is False
    assert render_procedure_block(procedure) == ''


# ---------------------------------------------------------- 6. the prompt text

def test_the_rendered_block_names_the_current_activity_and_forbids_substitution():
    procedure = lesson()
    block = render_procedure_block(procedure.to_dict())
    assert 'You may not add, remove, reorder or substitute an activity' in block
    assert '[NOW]' in block
    # The first block is the one marked current, and only it.
    assert block.count('[NOW]') == 1
    first = procedure.blocks[0]
    assert f'1. [NOW] {first.kind}' in block
    for other in procedure.blocks[1:]:
        assert f'{other.order}. [next] {other.kind}' in block


def test_the_rendered_block_marks_completed_activities():
    procedure = lesson()
    done = (procedure.blocks[0].order,)
    block = render_procedure_block(procedure.to_dict(), completed=done)
    assert f'{procedure.blocks[0].order}. [done]' in block
    assert f'{procedure.blocks[1].order}. [NOW]' in block


def test_the_rendered_block_publishes_the_refusals_as_prohibitions():
    procedure = lesson()
    block = render_procedure_block(procedure.to_dict())
    assert 'Do not offer' in block
    assert 'video' in block


def test_the_rendered_block_binds_the_artifact_rather_than_describing_it():
    """The model is told which deck to present, not to make a deck - that is the
    difference between a lesson and a model improvising one."""
    # No curated video, so the deck is the input and the thing to bind.
    procedure = lesson(assets_=assets(video=None))
    block = render_procedure_block(procedure.to_dict())
    assert 'Bound artifact:' in block
    assert 'do not write your own slides' in block


def test_an_empty_procedure_renders_nothing_rather_than_a_placeholder():
    assert render_procedure_block(None) == ''
    assert render_procedure_block({}) == ''
    assert tutor_module._procedure_section(None) == ''


# ------------------------------------------------------------- 7. the wiring

@pytest.fixture
def wired(tmp_path, monkeypatch):
    """A real app whose provider is configured but never reached over the network."""
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('HARNESS_TUTOR_PROVIDER', 'openai')
    monkeypatch.setenv('HARNESS_TUTOR_URL', 'https://provider.example.test/v1')
    monkeypatch.setenv('HARNESS_TUTOR_MODEL', 'test-model')
    monkeypatch.setenv('HARNESS_TUTOR_KEY', 'test-key-not-real')
    from fastapi.testclient import TestClient
    with TestClient(create_app(Settings.from_env())) as client:
        yield client


def _capture(monkeypatch):
    captured = {}

    class FakeResponse:
        content = b'{}'

        def raise_for_status(self):
            pass

        def json(self):
            return {'choices': [{'message': {'content': 'Here is the next step.'}}]}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, json=None, headers=None):
            captured['messages'] = [dict(message) for message in json['messages']]
            return FakeResponse()

    monkeypatch.setattr(tutor_module.httpx, 'Client', FakeClient)
    return captured


def _system_of(captured):
    return next(message['content'] for message in captured['messages']
                if message['role'] == 'system')


def _account(client, label='one'):
    response = client.post('/api/v1/auth/register', json={
        'name': label, 'email': f'{label}@example.test',
        'password': 'long-secret-password'})
    assert response.status_code == 201, response.text
    return {'Authorization': 'Bearer ' + response.json()['token']}, response.json()


def test_the_procedure_reaches_the_system_prompt_the_provider_receives(wired, monkeypatch):
    """The block is rendered *and delivered*. A compiled lesson that never reaches the
    prompt is the same defect as no lesson at all, with better plumbing."""
    captured = _capture(monkeypatch)
    headers, _ = _account(wired, 'prompt')
    response = wired.post('/api/v1/chat', headers=headers,
                          json={'concept_id': CONCEPT, 'message': 'Where do I start?'})
    assert response.status_code == 200, response.text
    system = _system_of(captured)
    assert 'lesson procedure compiled by the harness' in system
    assert '[NOW]' in system
    assert 'Bound artifact:' in system
    # The move policy's own block is still there: the two are complementary.
    assert "This turn's teaching decision" in system


def test_the_agent_loop_carries_the_procedure_to_its_tool_registry(wired, monkeypatch):
    """The agent path is where the simulation and whiteboard tools actually run, so it is
    where an unconstrained model would otherwise pick its own sequence."""
    from app.harness import provider
    captured = {}

    def fake_chat_tools(settings, messages, **kwargs):
        captured['messages'] = [dict(message) for message in messages]
        return {'content': 'Here is the first block.', 'tool_calls': [],
                'finish_reason': 'stop', 'usage': {}, 'reasoning': None}

    monkeypatch.setattr(provider, 'chat_tools', fake_chat_tools)
    headers, _ = _account(wired, 'agentic')
    response = wired.post('/api/v1/agent/chat', headers=headers, json={
        'session_id': 's1', 'message': 'Teach me fractions',
        'context': {'concept_id': CONCEPT}})
    assert response.status_code == 200, response.text
    system = _system_of(captured)
    assert 'lesson procedure compiled by the harness' in system
    assert "This turn's teaching decision" in system


def test_progress_shapes_the_next_turn(wired, monkeypatch):
    """The prompt must move with the learner, not be a constant that merely looks
    dynamic."""
    captured = _capture(monkeypatch)
    headers, _ = _account(wired, 'progress')
    started = wired.post(f'/api/v1/procedure/{CONCEPT}/start', headers=headers)
    assert started.status_code == 200, started.text
    run = started.json()
    first = run['blocks'][0]

    assert wired.post(f"/api/v1/procedure/runs/{run['run_id']}/advance", headers=headers,
                      json={'order': first['order']}).status_code == 200
    wired.post('/api/v1/chat', headers=headers,
               json={'concept_id': CONCEPT, 'message': 'Next?'})
    system = _system_of(captured)
    assert f'{first["order"]}. [done]' in system
    assert f'{run["blocks"][1]["order"]}. [NOW]' in system


def test_the_sequence_is_frozen_once_the_lesson_begins(wired, monkeypatch):
    """The plan must not re-shuffle between turns.

    The tutor is told it may not add, remove or reorder an activity. If the sequence were
    recompiled from fresh evidence on every turn, it would do exactly that behind the
    model's back: turn 1 says "block 2 of 4: the deck", the learner reads the deck, and
    turn 2 says "block 2 of 3: the simulation" because the deck no longer qualifies. So
    the first turn starts the run and later evidence shapes the *next* lesson.
    """
    captured = _capture(monkeypatch)
    headers, _ = _account(wired, 'frozen')
    wired.post('/api/v1/chat', headers=headers,
               json={'concept_id': CONCEPT, 'message': 'Where do I start?'})
    first = _system_of(captured)

    # Evidence that would definitely change a fresh compile: this learner is now
    # answering well above the input-skip bar.
    with wired.app.state.factory() as db:
        user = db.scalar(select(User).where(User.email == 'frozen@example.test'))
        db.add(State(user_id=user.id, concept_id='fraction_equivalence',
                     data={'mastery': 0.95, 'attempts': 9, 'correct_count': 9}))
        db.commit()

    wired.post('/api/v1/chat', headers=headers,
               json={'concept_id': CONCEPT, 'message': 'What next?'})
    second = _system_of(captured)

    def sequence(system):
        start = system.index('lesson procedure compiled by the harness')
        end = system.find('This turn runs block', start)
        body = system[start:end if end > 0 else len(system)]
        return [line.split('] ', 1)[-1].split(' (', 1)[0]
                for line in body.splitlines() if line[:1].isdigit()]

    assert sequence(first) == sequence(second), (sequence(first), sequence(second))
    assert sequence(second), 'the prompt carried no blocks at all'


# ------------------------------------------------------------ 8. the run record

def test_starting_the_same_lesson_twice_returns_the_same_run(wired):
    """A retried request must not leave the learner with two half-finished lessons."""
    headers, _ = _account(wired, 'idempotent')
    first = wired.post(f'/api/v1/procedure/{CONCEPT}/start', headers=headers).json()
    second = wired.post(f'/api/v1/procedure/{CONCEPT}/start', headers=headers).json()
    assert first['run_id'] == second['run_id']
    with wired.app.state.factory() as db:
        user = db.scalar(select(User).where(User.email == 'idempotent@example.test'))
        rows = list(db.scalars(select(ProcedureRun).where(ProcedureRun.user_id == user.id)))
    assert len(rows) == 1


def test_advancing_every_block_completes_the_run(wired):
    headers, _ = _account(wired, 'finish')
    run = wired.post(f'/api/v1/procedure/{CONCEPT}/start', headers=headers).json()
    assert run['status'] == 'active' and run['current'] is not None
    for block in run['blocks']:
        response = wired.post(f"/api/v1/procedure/runs/{run['run_id']}/advance",
                              headers=headers, json={'order': block['order']})
        assert response.status_code == 200, response.text
    final = response.json()
    assert final['status'] == 'completed'
    assert final['progress'] == 1.0
    assert final['current'] is None
    assert len(final['completed']) == len(final['blocks'])


def test_a_double_tap_is_refused_rather_than_recorded_twice(wired):
    """The progress record is what the next prompt is built from; a block recorded twice
    would make the tutor repeat it."""
    headers, _ = _account(wired, 'double')
    run = wired.post(f'/api/v1/procedure/{CONCEPT}/start', headers=headers).json()
    order = run['blocks'][0]['order']
    url = f"/api/v1/procedure/runs/{run['run_id']}/advance"
    assert wired.post(url, headers=headers, json={'order': order}).status_code == 200
    again = wired.post(url, headers=headers, json={'order': order})
    assert again.status_code == 409
    assert 'already complete' in again.json()['detail']


def test_an_unknown_block_is_refused(wired):
    headers, _ = _account(wired, 'unknown')
    run = wired.post(f'/api/v1/procedure/{CONCEPT}/start', headers=headers).json()
    url = f"/api/v1/procedure/runs/{run['run_id']}/advance"
    # In range, but not in this lesson: a stale client, and a 409 rather than a silent
    # no-op that would leave the progress record wrong.
    response = wired.post(url, headers=headers, json={'order': 9})
    assert response.status_code == 409
    assert 'No block 9' in response.json()['detail']
    # Out of range entirely: refused by the schema before any lookup happens.
    assert wired.post(url, headers=headers, json={'order': 999}).status_code == 422


def test_abandoning_frees_the_concept_for_a_new_lesson(wired):
    headers, _ = _account(wired, 'abandon')
    run = wired.post(f'/api/v1/procedure/{CONCEPT}/start', headers=headers).json()
    stopped = wired.post(f"/api/v1/procedure/runs/{run['run_id']}/abandon", headers=headers)
    assert stopped.status_code == 200
    assert stopped.json()['status'] == 'abandoned'
    # The completed blocks survive, which is how the next lesson knows what already ran.
    assert wired.get(f"/api/v1/procedure/runs/{run['run_id']}",
                     headers=headers).json()['status'] == 'abandoned'


def test_another_learners_run_is_a_404_not_a_403(wired):
    """A 403 would confirm the run exists."""
    owner, _ = _account(wired, 'owner')
    other, _ = _account(wired, 'intruder')
    run = wired.post(f'/api/v1/procedure/{CONCEPT}/start', headers=owner).json()
    assert wired.get(f"/api/v1/procedure/runs/{run['run_id']}",
                     headers=other).status_code == 404
    assert wired.post(f"/api/v1/procedure/runs/{run['run_id']}/advance",
                      headers=other, json={'order': 1}).status_code == 404
    assert wired.post(f"/api/v1/procedure/runs/{run['run_id']}/abandon",
                      headers=other).status_code == 404


def test_a_concept_outside_the_learners_course_is_a_404(wired):
    headers, _ = _account(wired, 'scope')
    assert wired.get('/api/v1/procedure/not_a_concept', headers=headers).status_code == 404
    assert wired.post('/api/v1/procedure/not_a_concept/start',
                      headers=headers).status_code == 404


def test_advancing_writes_no_evidence(wired):
    """The plan is not the evidence. Tapping through a lesson must not move mastery, or a
    learner could raise their own estimate without answering anything."""
    headers, _ = _account(wired, 'noevidence')
    run = wired.post(f'/api/v1/procedure/{CONCEPT}/start', headers=headers).json()
    for block in run['blocks']:
        wired.post(f"/api/v1/procedure/runs/{run['run_id']}/advance", headers=headers,
                   json={'order': block['order']})
    with wired.app.state.factory() as db:
        user = db.scalar(select(User).where(User.email == 'noevidence@example.test'))
        assert list(db.scalars(select(State).where(State.user_id == user.id))) == []
        assert list(db.scalars(select(Attempt).where(Attempt.user_id == user.id))) == []
        stored = db.scalar(select(ProcedureRun).where(ProcedureRun.user_id == user.id))
        assert stored.status == 'completed'


def test_the_exam_guard_covers_the_whole_lesson(wired):
    """A lesson plan names a deck, a simulation and a video for the concept under
    examination. It is help, whatever it is called, so every route refuses."""
    headers, _ = _account(wired, 'exam')
    run = wired.post(f'/api/v1/procedure/{CONCEPT}/start', headers=headers).json()
    # Open an exam the way the real route does.
    from app.db import Assessment, now_ts
    with wired.app.state.factory() as db:
        user = db.scalar(select(User).where(User.email == 'exam@example.test'))
        db.add(Assessment(id='exam-1', user_id=user.id, mode='exam', complete=False,
                          total=8, answered=0, correct=0,
                          expires_at=now_ts() + 3600))
        db.commit()
    assert wired.get(f'/api/v1/procedure/{CONCEPT}', headers=headers).status_code == 403
    assert wired.post(f'/api/v1/procedure/{CONCEPT}/start', headers=headers).status_code == 403
    assert wired.get(f"/api/v1/procedure/runs/{run['run_id']}",
                     headers=headers).status_code == 403
    assert wired.post(f"/api/v1/procedure/runs/{run['run_id']}/advance", headers=headers,
                      json={'order': 1}).status_code == 403
    # And nothing was written: the guard runs before the write, not after it.
    with wired.app.state.factory() as db:
        stored = db.scalar(select(ProcedureRun).where(ProcedureRun.id == run['run_id']))
        assert stored.completed == []


def test_the_deck_is_materialised_and_its_twin_is_downloadable(wired):
    """The block promises a deck; the promise has to resolve to bytes, including the
    .pptx twin the builder writes beside the HTML."""
    headers, _ = _account(wired, 'deck')
    run = wired.post(f'/api/v1/procedure/{CONCEPT}/start', headers=headers).json()
    deck = next((block for block in run['blocks'] if block['kind'] == 'deck'), None)
    if deck is None:
        pytest.skip('this concept does not open with a deck')
    artifact = deck['artifact']
    assert artifact['artifact_id'], artifact
    assert artifact['materialized'] is True
    assert wired.get(artifact['raw_url'], headers=headers).status_code == 200
    twin = wired.get(artifact['pptx_url'], headers=headers)
    assert twin.status_code == 200
    assert twin.content[:2] == b'PK'


def test_a_pptx_download_cannot_escape_the_artifact_directory(wired):
    """The name is matched against a pattern, so there is no traversal to get wrong."""
    headers, _ = _account(wired, 'traversal')
    run = wired.post(f'/api/v1/procedure/{CONCEPT}/start', headers=headers).json()
    deck = next((block for block in run['blocks'] if block['kind'] == 'deck'), None)
    if deck is None:
        pytest.skip('this concept does not open with a deck')
    artifact_id = deck['artifact']['artifact_id']
    for name in ('../v1.html', '..%2Fv1.html', 'v1.html', 'passwd'):
        response = wired.get(f'/api/v1/sims/{artifact_id}/download/{name}', headers=headers)
        assert response.status_code == 404, (name, response.status_code)


# ------------------------------------- 5. the artifact a client can open
#
# The four rules above decide *what* the lesson does. These prove the decision is
# *openable*: a block that names an artifact has to carry enough of it for a client to
# present, play or read it. This is not cosmetic. The app decides whether to offer its
# "Present", "Watch" or "Read" button from the artifact's own contents, so a block that
# stopped carrying them would silently become a row naming something nobody can open - the
# exact failure this whole layer exists to prevent.

def test_the_deck_block_carries_the_slides_a_client_can_present():
    """The deck arrives as sections, not as a promise of sections.

    The slides are rendered natively from these, which is also why the deck works with no
    session: the HTML and the ``.pptx`` sit behind the bearer token, but the content does
    not. ``notes`` travels because it is the only copy of the authored body the bullets
    were drawn from - the presenter's source text.
    """
    # Without a curated video the deck is the input, which is the case this test is about.
    procedure = lesson(assets_=assets(video=None))
    block = next(block for block in procedure.blocks if block.kind == 'deck')
    sections = block.artifact['sections']
    assert sections, block.artifact
    assert block.artifact['slide_count'] == len(sections)
    for section in sections:
        assert section['heading'].strip(), section
        assert section['bullets'], section
        assert all(isinstance(bullet, str) and bullet.strip()
                   for bullet in section['bullets']), section
    assert block.artifact['concept_title'] == 'Fractions'


def test_the_video_block_carries_a_url_a_player_can_actually_use():
    """A curated video arrives with the provider's own embed and watch URLs.

    The app plays the embed and falls back to the provider's page, so both have to be real
    provider URLs over HTTPS. An empty ``embed_url`` is deliberate - it means the provider
    refuses to embed this title, which the client reports instead of offering a player that
    will not play.
    """
    procedure = lesson(
        facts_=facts(subject_kind='science'),
        assets_=assets(video={'provider': 'youtube', 'title': 'Plate boundaries',
                              'channel': 'Curated', 'licence_class': 'embed_only',
                              'attribution': 'Curated',
                              'watch_url': 'https://www.youtube.com/watch?v=abc123',
                              'embed_url': 'https://www.youtube-nocookie.com/embed/abc123'}))
    block = next(block for block in procedure.blocks if block.kind == 'video')
    artifact = block.artifact
    assert artifact['provider'] == 'youtube'
    assert artifact['watch_url'].startswith('https://www.youtube.com/')
    assert artifact['embed_url'].startswith('https://www.youtube-nocookie.com/embed/')
    assert artifact['licence_class'] == 'embed_only'
    assert artifact['attribution']


def test_the_simulation_block_carries_what_the_app_needs_to_open_it():
    """An exploratory interactive has to arrive with the payload the app draws from.

    The app opens it with `SimulationLab`, which re-asks the engine for the bound concept -
    so `concept_id` is the field that makes the opened interactive the bound one, and
    `expression`/`prompt` are what the sheet shows around it. An interactive with none of
    these is a block that names an artifact nothing can reach.
    """
    procedure = lesson(
        state={'mastery': 0.5, 'attempts': 4, 'correct_count': 3},
        assets_=assets(simulation={'mode': 'exploratory', 'observable': False,
                                   'title': 'Adding with unlike denominators',
                                   'expression': '1/4 + n/3',
                                   'parameters': [{'id': 'n', 'label': 'Numerator',
                                                   'min': 1, 'max': 2, 'value': 1}],
                                   'objective': 'A denominator names the size of a part.',
                                   'prompt': 'Predict, then change it and check.'}))
    block = next(block for block in procedure.blocks if block.kind == 'simulation')
    artifact = block.artifact
    assert artifact['mode'] == 'exploratory'
    assert artifact['observable'] is False
    assert artifact['concept_id'] == 'algebra.fractions'
    assert artifact['expression']
    assert artifact['prompt']
    assert artifact['parameters']


def test_the_started_run_still_carries_what_the_preview_promised(wired):
    """Starting a lesson must not slim the payload a client renders from.

    Only the run is stored and re-served, so this is where a serialiser that dropped
    ``sections`` would show up: the deck would still materialise and the card would still
    name it, but there would be nothing to present.
    """
    headers, _ = _account(wired, 'payload')
    preview = wired.get(f'/api/v1/procedure/{CONCEPT}', headers=headers).json()['plan']
    run = wired.post(f'/api/v1/procedure/{CONCEPT}/start', headers=headers).json()
    preview_deck = next((b for b in preview['blocks'] if b['kind'] == 'deck'), None)
    if preview_deck is None:
        pytest.skip('this concept does not open with a deck')
    deck = next(block for block in run['blocks'] if block['kind'] == 'deck')
    assert deck['artifact']['sections'] == preview_deck['artifact']['sections']
    # Materialising adds to the artifact; it must not replace what was promised.
    assert deck['artifact']['artifact_id']
    assert deck['artifact']['pptx_file']
    assert deck['artifact']['slide_count'] == len(deck['artifact']['sections'])


def test_the_plan_preview_persists_nothing(wired):
    """Previewing a lesson must not create a run or build a deck: a learner who looks and
    leaves causes no write."""
    headers, _ = _account(wired, 'preview')
    preview = wired.get(f'/api/v1/procedure/{CONCEPT}', headers=headers)
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body['plan']['blocks']
    assert body['active'] is None
    assert body['evidence']['attempts'] == 0
    with wired.app.state.factory() as db:
        user = db.scalar(select(User).where(User.email == 'preview@example.test'))
        assert list(db.scalars(select(ProcedureRun).where(ProcedureRun.user_id == user.id))) == []


def test_the_plan_is_reproducible_from_the_endpoint(wired):
    """Two previews of the same learner return the same fingerprint, which is what makes
    the hash usable as an idempotency key."""
    headers, _ = _account(wired, 'stable')
    first = wired.get(f'/api/v1/procedure/{CONCEPT}', headers=headers).json()['plan']
    second = wired.get(f'/api/v1/procedure/{CONCEPT}', headers=headers).json()['plan']
    assert first['hash'] == second['hash']
    assert first['blocks'] == second['blocks']


def test_the_run_payload_carries_the_authored_concept_title(wired):
    """A card headed "Fraction Equivalence" for a lesson the course calls "Fractions and
    equivalent quantities" is a small lie about which lesson the learner is in.

    The run row stores an id - a title is curriculum content and a stored copy would go
    stale on a rename - so the title is resolved at serialisation time. Every route goes
    through one helper for exactly this reason: six call sites is six chances to forget.
    """
    headers, _ = _account(wired, 'titled')
    run = wired.post(f'/api/v1/procedure/{CONCEPT}/start', headers=headers).json()
    authored = CONCEPTS[CONCEPT]['title']
    assert run['concept_title'] == authored
    assert wired.get(f"/api/v1/procedure/runs/{run['run_id']}",
                     headers=headers).json()['concept_title'] == authored
    assert wired.get('/api/v1/procedure', headers=headers).json()['runs'][0]['concept_title'] == authored
    # And the preview, which resolves it the same way for the proposal.
    preview = wired.get(f'/api/v1/procedure/{CONCEPT}', headers=headers).json()
    assert preview['plan']['concept_title'] == authored
    assert preview['active']['concept_title'] == authored


def test_a_shorter_budget_from_the_client_produces_a_shorter_lesson(wired):
    """The budget is a parameter, not a constant: a client that knows the learner has ten
    minutes gets a ten-minute lesson rather than an overrun."""
    headers, _ = _account(wired, 'budget')
    short = wired.get(f'/api/v1/procedure/{CONCEPT}', headers=headers,
                      params={'minutes': 8}).json()['plan']
    long = wired.get(f'/api/v1/procedure/{CONCEPT}', headers=headers,
                     params={'minutes': 30}).json()['plan']
    assert short['total_minutes'] <= 8
    assert short['total_minutes'] < long['total_minutes']
    assert short['hash'] != long['hash']


# ------------------------------------------------- 9. the resolver's honesty

def test_the_resolver_refuses_a_symbolic_figure_for_a_non_mathematics_subject():
    """``mathkit.template_for`` will return a generic parabola for any concept. Presenting
    that as 'acceleration' is the confident fabrication this project exists to prevent."""
    simulation, reason = procedure_service._simulation(
        {'title': 'Acceleration', 'keywords': ['acceleration'], 'blocks': []},
        'physics', 'science')
    assert simulation is None
    assert 'mathematics' in reason


def test_the_resolver_never_promises_a_video_that_is_not_curated():
    from app.config import Settings
    settings = Settings.from_env()
    video, reason = procedure_service._video('physics', 'acceleration', settings)
    assert video is None
    assert reason


def test_the_game_matcher_prefers_containment_over_overlap():
    """Two different concepts share two words; a lesson that opens the wrong simulation is
    worse than one that opens none."""
    lesson_row = {'title': 'Determinants of supply and demand',
                  'keywords': ['supply', 'demand', 'determinants']}
    game = procedure_service._match_game(lesson_row, 'ap_macroeconomics')
    if game is not None:
        text = (str(game.get('concept') or '') + ' '
                + ' '.join(str(tag) for tag in (game.get('tags') or []))).lower()
        assert 'elasticity' not in text, game


# ------------------------------------------------- 9. the deck carries a real picture

def _fake_acquire(*, sha='a' * 64, outcome='downloaded'):
    """The one media pipeline, stubbed at its seam. Every field the deck section
    copies is here, so a renderer that reads a key the resolver never fills is a
    test failure rather than a blank frame."""
    def acquire(settings, query, **kwargs):
        return {'outcome': outcome,
                'query': query,
                'notes': [],
                'asset': {'sha256': sha, 'title': 'Air mass over a front',
                          'attribution_text': 'Photo: Example (CC BY 4.0)',
                          'licence_code': 'cc_by', 'licence_class': 'cc_by',
                          'landing_page_url': 'https://example.test/photo',
                          'width': 1600, 'height': 900,
                          'alt_text': f'Illustration for {query}',
                          'cache_path': 'media/ab/cd.jpg'}}
    return acquire


def _deck_block(run):
    return next(block for block in run['blocks'] if block['kind'] == 'deck')


def test_the_deck_opening_slide_carries_a_licence_cleared_image(wired, monkeypatch):
    """A deck of headings and bullets is a mock-up. The picture comes from the one
    media pipeline - licence gate, content-addressed cache - and rides on the
    section the client renders, with its credit attached."""
    monkeypatch.setattr('app.harness.media.acquire', _fake_acquire())
    headers, _ = _account(wired, 'deckpic')
    run = wired.post(f'/api/v1/procedure/{CONCEPT}/start', headers=headers).json()
    sections = _deck_block(run)['artifact']['sections']
    assert sections, 'the deck had no sections at all'
    image = sections[0].get('image')
    assert image, 'the opening slide carried no picture'
    assert image['sha256'] == 'a' * 64
    assert image['url'] == '/api/v1/media/images/' + 'a' * 64 + '/bytes'
    assert 'CC BY 4.0' in image['credit']
    assert image['licence'] == 'cc_by'
    assert image['width'] == 1600 and image['height'] == 900
    # Only the opening slide carries it: one picture per deck, not one per bullet.
    assert all('image' not in section for section in sections[1:])


def test_a_deck_without_a_cleared_picture_ships_without_one(wired, monkeypatch):
    """Offline, disabled, or nothing cleared: the deck is still a deck, and the
    reason is published on the opening section - where the picture would have
    been - rather than an empty frame or a substitute image.

    The reason belongs on the section, not in ``run['skipped']``: ``skipped`` is the
    activity-level record ("why no video?"), and the deck was *not* skipped - only
    its picture was. A client renders sections, so that is where it can act on it.
    """
    monkeypatch.setattr('app.harness.media.acquire',
                        _fake_acquire(outcome='network_disabled'))
    headers, _ = _account(wired, 'decknopic')
    run = wired.post(f'/api/v1/procedure/{CONCEPT}/start', headers=headers).json()
    sections = _deck_block(run)['artifact']['sections']
    assert sections, 'a missing picture must not cost the learner the deck'
    assert all('image' not in section for section in sections)
    reason = str(sections[0].get('image_unavailable') or '')
    assert reason, 'the missing picture was not published as a reason'
    assert 'network_disabled' in reason, reason


def test_the_concept_board_can_be_created_at_the_id_the_client_addresses(wired):
    """The learner's strokes need a document to land in. Before this, the client's
    first drawing hit a board that did not exist and was silently dropped."""
    headers, _ = _account(wired, 'boardowner')
    first = wired.post('/api/v1/boards', headers=headers,
                       json={'title': 'Air masses and fronts', 'board_id': 'board-air_masses'})
    assert first.status_code == 201, first.text
    assert first.json()['board']['id'] == 'board-air_masses'
    # Re-opening is idempotent: the same owner gets the same document back.
    again = wired.post('/api/v1/boards', headers=headers,
                       json={'title': 'Air masses and fronts', 'board_id': 'board-air_masses'})
    assert again.status_code == 201, again.text
    assert again.json()['board']['version'] == first.json()['board']['version']
    # And a stroke now persists, which is the whole point.
    patched = wired.patch('/api/v1/boards/board-air_masses', headers=headers,
                          json={'base_version': 1,
                                'mutations': [{'action': 'add',
                                               'node': {'kind': 'text', 'x': 10, 'y': 10,
                                                        'payload': {'text': 'front', 'size': 16}}}]})
    assert patched.status_code == 200, patched.text
    assert len(patched.json()['board']['nodes']) == 1


# --------------------------------------------- 10. the tutor can move the deck

def _invoke_deck(client, email, **kwargs):
    """Call ``deck_control`` the way the agent loop does, as an ordinary account.

    The account is a learner here on purpose: moving the deck is a hand on the learner's
    own view, not a teaching privilege, and gating it is the bug this tool exists to fix.
    """
    from app.harness.toolbox import ToolContext, invoke
    app = client.app
    with app.state.factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        ctx = ToolContext(db=db, user=user, settings=app.state.settings)
        result = invoke(ctx, 'deck_control', kwargs)
        db.commit()
        return result


def test_the_deck_cursor_starts_on_the_opening_slide(wired):
    """A started lesson reports a real deck length, so the client has something to move."""
    headers, _ = _account(wired, 'cursorstart')
    wired.post(f'/api/v1/procedure/{CONCEPT}/start', headers=headers)
    cursor = wired.get(f'/api/v1/procedure/{CONCEPT}/deck-cursor', headers=headers).json()
    assert cursor['slide'] == 0
    assert cursor['count'] >= 1, 'a started lesson with a deck must report its length'


def test_the_tutor_can_advance_the_deck_the_learner_is_watching(wired):
    """The tutor's "next slide" reaches the sheet. Without this it could only talk about
    a slide the learner had to find themselves."""
    headers, account = _account(wired, 'cursortutor')
    run = wired.post(f'/api/v1/procedure/{CONCEPT}/start', headers=headers).json()
    count = len(_deck_block(run)['artifact']['sections'])
    result = _invoke_deck(wired, account['user']['email'], action='next')
    assert result.ok, result.refused
    assert result.data['slide'] == 1
    assert result.data['count'] == count
    # The client polls this route, so the move has to be visible there too.
    seen = wired.get(f'/api/v1/procedure/{CONCEPT}/deck-cursor', headers=headers).json()
    assert seen['slide'] == 1


def test_the_learner_moving_the_deck_reaches_the_tutor(wired):
    """The cursor is shared, not one-way. A learner who taps ahead and then asks "next"
    must be moved from the slide they are on, not from the server's last guess."""
    headers, account = _account(wired, 'cursorlearner')
    run = wired.post(f'/api/v1/procedure/{CONCEPT}/start', headers=headers).json()
    count = len(_deck_block(run)['artifact']['sections'])
    moved = wired.put(f'/api/v1/procedure/{CONCEPT}/deck-cursor', headers=headers,
                      json={'slide': count - 1})
    assert moved.status_code == 200, moved.text
    assert moved.json()['slide'] == count - 1
    # "next" from the last slide stays put rather than wrapping to the first.
    result = _invoke_deck(wired, account['user']['email'], action='next')
    assert result.ok, result.refused
    assert result.data['slide'] == count - 1


def test_the_prompt_tells_the_tutor_it_can_move_an_open_deck():
    """The tool existed and was never mentioned at the moment it was needed, so a tutor
    that wanted to turn the page could only describe the page it could not turn."""
    procedure = {
        'enabled': True, 'concept_id': 'fractions', 'concept_title': 'Fractions',
        'course_id': 'integrated_math_1', 'budget_minutes': 20, 'total_minutes': 12,
        'blocks': [
            {'order': 1, 'kind': 'diagnostic', 'minutes': 3, 'title': 'Quick check',
             'purpose': 'Measure where the learner is.', 'why': 'No evidence yet.',
             'artifact': {'kind': 'questions'}},
            {'order': 2, 'kind': 'deck', 'minutes': 5, 'title': 'Lesson deck',
             'purpose': 'Present the concept.', 'why': 'First exposure.',
             'artifact': {'kind': 'slides',
                          'sections': [{'heading': 'Halves', 'bullets': ['one of two']}]}},
        ],
        'skipped': [],
    }
    # Once the deck is the block being run, the tutor is told it can move it.
    assert 'deck_control' in render_procedure_block(procedure, completed=[1])
    # Before that, it is not: a tutor told to flip a deck that is not current would
    # move the learner's screen during the diagnostic.
    assert 'deck_control' not in render_procedure_block(procedure, completed=[])


def test_the_cursor_is_clamped_to_the_deck_that_exists(wired):
    """An out-of-range position would store a slide the client cannot render, and the
    next move would compute from a slide that is not on screen."""
    headers, _ = _account(wired, 'cursorclamp')
    run = wired.post(f'/api/v1/procedure/{CONCEPT}/start', headers=headers).json()
    count = len(_deck_block(run)['artifact']['sections'])
    far = wired.put(f'/api/v1/procedure/{CONCEPT}/deck-cursor', headers=headers,
                    json={'slide': 60})
    assert far.status_code == 200, far.text
    assert far.json()['slide'] == count - 1


def test_a_board_id_owned_by_somebody_else_is_not_silently_reused(wired):
    headers, _ = _account(wired, 'mine')
    other, _ = _account(wired, 'theirs')
    assert wired.post('/api/v1/boards', headers=other,
                      json={'board_id': 'board-shared'}).status_code == 201
    clash = wired.post('/api/v1/boards', headers=headers,
                       json={'board_id': 'board-shared'})
    assert clash.status_code == 409
