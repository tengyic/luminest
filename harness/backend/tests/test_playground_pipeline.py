"""The model-driven draft path: the retry loop, the safety property, and injection.

``draft()`` is the arm of the playground that produces *more* games without a human
writing each one, so it is the part where the playground stops being a fixed set of
templates and becomes a system. The two trivial branches - "no model is configured"
and "unknown archetype" - are covered in ``test_playground.py``. What is covered here
is everything that happens once a model actually answers:

* a valid completion is composed and stored, through the same validator and artifact
  store as a hand-authored game;
* an invalid one is retried **with the validator's own complaint attached**, which is
  the entire reason a second attempt is worth making - a retry that re-asks the same
  question without the error is not a retry, it is a second coin flip;
* a model that never satisfies the schema gets an honest failure and stores nothing;
* the attempt budget is a real bound on how many times the model is asked;
* and the model is untrusted input, so a completion containing ``</script>`` must not
  be able to break out of the script block it is embedded in.

The last one is the test that would catch a future refactor quietly removing the
``<`` -> ``\\u003c`` escape in ``runtime._js_literal``. Nothing else in the suite would
notice: the page would still render, still validate, and still look correct in a
browser until a model hallucinated the wrong string.
"""

from __future__ import annotations

import copy
import json
import re
import subprocess
from pathlib import Path

import pytest

from app.config import Settings
from app.harness import provider, sims_store
from app.harness.playground import get, pipeline, validate_spec


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """A hermetic harness pointed at a throwaway data dir.

    Copied rather than imported from ``test_playground.py``: that module is being
    edited concurrently, and a test file that cannot run on its own is not evidence.
    """
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.delenv('HARNESS_TUTOR_PROVIDER', raising=False)
    return Settings.from_env()


#: A real, valid ``curve_shift`` spec. ``curve_shift`` is the reference archetype, so a
#: schema change there is a change to the pattern every other archetype copies, and it
#: is the right canary.
VALID_SPEC = {
    'title': 'Shifting Markets',
    'instruction': 'Drag the curve the shock affects, then press Check.',
    'x_max': 10,
    'y_max': 10,
    'curves': [
        {'id': 'demand', 'label': 'Demand D', 'colour': 'a',
         'intercept': 10, 'slope': -1, 'shifts': True},
        {'id': 'supply', 'label': 'Supply S', 'colour': 'b',
         'intercept': 1, 'slope': 1, 'shifts': False},
    ],
    'shocks': [
        {'id': 'income-up', 'text': 'Household incomes rise.', 'shift': 'demand',
         'direction': 'right', 'price': 'up', 'quantity': 'up',
         'why': 'Demand rises, so the equilibrium moves up the supply curve.'},
    ],
}


def test_the_spec_this_file_tests_against_is_actually_valid():
    """A guard, so a schema change fails here with a clear message instead of as six
    confusing failures in the tests below."""
    problems = validate_spec(VALID_SPEC, get('curve_shift'))
    assert problems == [], problems


def _fake_model(monkeypatch, replies):
    """Install a scripted model on ``app.harness.provider``.

    ``pipeline`` reaches the provider through the module reference (``from .. import
    provider``), so patching attributes on the module intercepts every call.

    ``replies`` is consumed one per call and the last one repeats. The returned list
    records, per call, a deep copy of the messages the model was given - which is what
    lets the retry test assert on the *second* call's prompt rather than guessing.
    """
    calls = []

    def fake_chat_json(settings, messages, *, max_tokens=1200, usage_out=None):
        calls.append({'messages': copy.deepcopy(list(messages)), 'max_tokens': max_tokens})
        index = min(len(calls) - 1, len(replies) - 1)
        return replies[index]

    monkeypatch.setattr(provider, 'available', lambda settings: True)
    monkeypatch.setattr(provider, 'label', lambda settings: 'scripted:model')
    monkeypatch.setattr(provider, 'chat_json', fake_chat_json)
    return calls


def _stored(settings):
    return sims_store.list_artifacts(settings, kind='simulation')


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


NODE = _node_binary()


# --------------------------------------------------------------- 1. the happy path


def test_draft_stores_a_valid_spec_the_model_returns(settings, monkeypatch):
    calls = _fake_model(monkeypatch, [copy.deepcopy(VALID_SPEC)])

    result = pipeline.draft(settings, archetype_id='curve_shift',
                            topic='shifting supply and demand')

    assert result['ok'] is True, result
    assert result['stage'] == 'stored'
    assert result['attempts'] == [{'attempt': 1, 'problems': []}]
    assert result['archetype'] == 'curve_shift'
    assert result['provider'] == 'scripted:model'
    assert result['spec'] == VALID_SPEC

    # Exactly one call: a valid first answer must not be asked for again.
    assert len(calls) == 1
    assert calls[0]['max_tokens'] == 3000

    stored = result['artifact']
    assert stored['id']
    assert stored['raw_url'] == sims_store.raw_url(stored['id'])

    # It went through the real artifact store, and it is marked as machine-authored so
    # an operator can tell a drafted game from a bundled one.
    entries = _stored(settings)
    assert [entry['id'] for entry in entries] == [stored['id']]
    assert entries[0]['meta']['source'] == 'model-drafted'
    assert entries[0]['meta']['archetype'] == 'curve_shift'

    # And the stored bytes are the real rendered page, not a placeholder.
    html = sims_store.latest_html(settings, stored['id'])
    assert html and '<script>' in html and 'curve_shift' in html


# -------------------------------------------- 2. the retry carries the complaint


def test_draft_feeds_the_validators_complaint_back_to_the_model(settings, monkeypatch):
    """The load-bearing property. Attempt two must be told *what was wrong*, verbatim.

    Without this the retry is just a second draw from the same distribution, and the
    docstring's claim that "the validator is the error channel" is false.
    """
    broken = copy.deepcopy(VALID_SPEC)
    broken['x_max'] = 500                      # outside the declared maximum of 100
    calls = _fake_model(monkeypatch, [broken, copy.deepcopy(VALID_SPEC)])

    result = pipeline.draft(settings, archetype_id='curve_shift', topic='shifting markets')

    assert result['ok'] is True, result
    assert result['stage'] == 'stored'
    assert len(calls) == 2, 'the model must be asked a second time after a rejection'

    first = result['attempts'][0]
    assert first['attempt'] == 1
    assert first['problems'], 'the first attempt must have recorded why it was rejected'
    # The complaint names the offending field and the bound it broke.
    assert first['problems'] == ['x_max must be at most 100 (got 500)']
    assert 'x_max' in first['problems'][0] and '100' in first['problems'][0]

    assert result['attempts'][1] == {'attempt': 2, 'problems': []}

    # --- the assertion that proves the loop is a feedback loop -------------------
    second_prompt = calls[1]['messages']
    user_text = '\n'.join(m['content'] for m in second_prompt if m['role'] == 'user')
    assert 'That spec was rejected. Fix exactly these problems' in user_text
    assert first['problems'][0] in user_text, (
        'the retry did not carry the validator\'s specific complaint:\n' + user_text)

    # The original request is still there - the retry adds to the conversation rather
    # than replacing it, so the model has not lost the task.
    assert any('shifting markets' in m['content'] for m in second_prompt
               if m['role'] == 'user')
    assert any(m['role'] == 'system' for m in second_prompt)


def test_the_retry_conversation_grows_instead_of_being_replaced(settings, monkeypatch):
    """Each rejection appends exactly one user turn, so the model sees the whole history."""
    broken = copy.deepcopy(VALID_SPEC)
    broken['shocks'] = []                      # fails minimum_items
    calls = _fake_model(monkeypatch, [broken, copy.deepcopy(VALID_SPEC)])

    pipeline.draft(settings, archetype_id='curve_shift', topic='markets')

    assert len(calls) == 2
    assert len(calls[0]['messages']) == 2      # system + the task
    assert len(calls[1]['messages']) == 3      # system + task + the rejection
    assert calls[1]['messages'][-1]['role'] == 'user'


# ------------------------------------- 3. nothing is stored unless a spec validated


def test_draft_stores_nothing_when_the_model_never_produces_a_valid_spec(settings, monkeypatch):
    """The safety property the docstring claims, asserted rather than trusted."""
    before = _stored(settings)
    assert before == []

    broken = copy.deepcopy(VALID_SPEC)
    broken['y_max'] = 999                      # out of bounds on every attempt
    calls = _fake_model(monkeypatch, [copy.deepcopy(broken)])

    result = pipeline.draft(settings, archetype_id='curve_shift', topic='markets')

    assert result['ok'] is False
    assert result['stage'] == 'validation'
    assert len(result['attempts']) == pipeline.DRAFT_ATTEMPTS
    assert all(attempt['problems'] for attempt in result['attempts'])
    assert 'nothing was stored' in result['problems'][0]

    assert len(calls) == pipeline.DRAFT_ATTEMPTS
    after = _stored(settings)
    assert after == before == [], f'the failed draft left {len(after)} artifact(s) behind'


def test_a_rejected_spec_does_not_store_then_a_valid_one_does(settings, monkeypatch):
    """Only the attempt that validated is stored - and only once."""
    broken = copy.deepcopy(VALID_SPEC)
    broken['x_max'] = 0                        # below the declared minimum
    calls = _fake_model(monkeypatch, [broken, copy.deepcopy(VALID_SPEC)])

    result = pipeline.draft(settings, archetype_id='curve_shift', topic='markets')

    assert result['ok'] is True
    assert len(calls) == 2
    entries = _stored(settings)
    assert len(entries) == 1, f'expected exactly one stored game, got {len(entries)}'
    assert entries[0]['id'] == result['artifact']['id']


# ------------------------------------------- 4. a non-object return is not a crash


@pytest.mark.parametrize('reply', [['a', 'list', 'of', 'things'], 'a bare string',
                                   '{"not": "closed"'],
                         ids=['list', 'string', 'unparseable-ish'])
def test_draft_reports_a_non_object_return_instead_of_crashing(settings, monkeypatch, reply):
    calls = _fake_model(monkeypatch, [reply])

    result = pipeline.draft(settings, archetype_id='curve_shift', topic='markets')

    assert result['ok'] is False
    assert result['stage'] == 'validation'
    assert result['attempts'][0]['problems'] == ['The model did not return a JSON object.']
    assert len(result['attempts']) == pipeline.DRAFT_ATTEMPTS
    assert len(calls) == pipeline.DRAFT_ATTEMPTS

    follow_up = [m['content'] for m in calls[1]['messages'] if m['role'] == 'user']
    assert 'That was not a JSON object. Return only the JSON object.' in follow_up

    assert _stored(settings) == []


def test_a_non_object_return_is_retried_before_giving_up(settings, monkeypatch):
    """A list on attempt one, a real object on attempt two: the draft recovers."""
    calls = _fake_model(monkeypatch, [[1, 2, 3], copy.deepcopy(VALID_SPEC)])

    result = pipeline.draft(settings, archetype_id='curve_shift', topic='markets')

    assert result['ok'] is True and result['stage'] == 'stored'
    assert result['attempts'][0]['problems'] == ['The model did not return a JSON object.']
    assert len(calls) == 2
    assert len(_stored(settings)) == 1


# ------------------------------------------------------- 5. the attempt budget


def test_the_model_is_asked_once_when_the_first_answer_is_valid(settings, monkeypatch):
    calls = _fake_model(monkeypatch, [copy.deepcopy(VALID_SPEC)])
    pipeline.draft(settings, archetype_id='curve_shift', topic='markets')
    assert len(calls) == 1
    assert len(calls) <= pipeline.DRAFT_ATTEMPTS


def test_the_model_is_asked_exactly_the_budget_when_it_always_fails(settings, monkeypatch):
    broken = copy.deepcopy(VALID_SPEC)
    broken['x_max'] = 500
    calls = _fake_model(monkeypatch, [broken])
    pipeline.draft(settings, archetype_id='curve_shift', topic='markets')
    assert len(calls) == pipeline.DRAFT_ATTEMPTS


def test_the_budget_constant_is_two_and_is_what_the_code_uses():
    """Asserted against the constant, not a hardcoded 2, so the test follows the code -
    but the value itself is a deliberate product decision worth pinning down."""
    assert pipeline.DRAFT_ATTEMPTS == 2


# --------------------------------- 6. the model is untrusted input (injection)


#: What a hallucinating model might emit into any free-text field. If it reached the
#: page unescaped it would close the script element and open its own.
BREAKOUT = '</script><script>window.__pwned=1</script>'


def _spec_carrying(payload):
    spec = copy.deepcopy(VALID_SPEC)
    spec['title'] = 'Shifting Markets ' + payload
    spec['instruction'] = 'Drag the curve. ' + payload
    spec['shocks'][0]['text'] = payload
    spec['shocks'][0]['why'] = payload
    return spec


def test_a_model_authored_spec_cannot_break_out_of_the_script_block(settings):
    """The spec is embedded in the page as JSON. ``runtime._js_literal`` escapes ``<``
    as ``\\u003c`` precisely so a spec cannot terminate the script element - and a spec
    is exactly where a model could smuggle one in."""
    spec = _spec_carrying(BREAKOUT)

    page = pipeline.render_game(archetype_id='curve_shift', spec=spec)

    # The payload did not create a second script element: there is exactly one
    # terminator, the page's own.
    assert page.count('</script>') == 1, 'the payload closed the script block'
    assert '</script><script>' not in page
    assert page.count('<script>') == 1

    # The payload is still present, as data, in its escaped form. `_js_literal` escapes
    # only the `<`, which is the character that would start a tag - so the terminator
    # reads `\u003c/script>` and the trailing `>` is untouched, exactly as intended.
    assert '\\u003c/script>' in page, 'the payload vanished instead of being escaped'
    assert '__pwned' in page

    scripts = re.findall(r'<script>(.*?)</script>', page, re.S)
    assert len(scripts) == 1, 'the page has more than one script block'

    # And the artifact store still accepts it - the escape is not a trick that makes the
    # validator unhappy, it is the supported path.
    problems = sims_store.validate_html(page, kind='simulation')
    assert problems == [], problems

    # The stored page is the same one, so nothing un-escapes on the way to disk.
    stored = pipeline.compose(settings, archetype_id='curve_shift', spec=spec,
                              title=spec['title'])
    stored_html = sims_store.latest_html(settings, stored['id'])
    assert stored_html.count('</script>') == 1
    assert '\\u003c/script>' in stored_html


@pytest.mark.skipif(NODE is None, reason='node is not available, so the script cannot be parsed')
def test_the_injected_page_script_still_parses(settings, tmp_path):
    """Escaping that produced syntactically broken JavaScript would be no escape at all."""
    spec = _spec_carrying(BREAKOUT)
    page = pipeline.render_game(archetype_id='curve_shift', spec=spec)
    script = re.findall(r'<script>(.*?)</script>', page, re.S)[0]

    target = tmp_path / 'injected.js'
    target.write_text(script, encoding='utf-8')
    completed = subprocess.run([NODE, '--check', str(target)],
                               capture_output=True, text=True, timeout=60)
    assert completed.returncode == 0, completed.stderr
