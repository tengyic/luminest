"""The runtime smoke check, and the tool that exposes it to the TA.

Structural validation answers "is this safe and well-formed"; these answer "does it run".
The distinction is not academic: a generated action-potential scope passed every structural
rule and then printed ``peak Infinity mV`` the moment its Stimulate button was pressed.

The browser tests skip when playwright is not installed, because the desktop bundle does not
carry it -- and the tool's behaviour in that case is itself pinned below, since "could not
verify" must never read as "verified".
"""

import pytest

from app.harness import sims_check, sims_store, toolbox


@pytest.fixture
def settings(tmp_path):
    """Only what the artifact store reads: where the data directory is."""
    return type('S', (), {'data_dir': tmp_path / 'data', 'sims_dir': ''})()


GOOD = """<!doctype html>
<html><head><meta charset="utf-8"><title>Counter</title></head>
<body>
<h1>Counter</h1>
<svg><polyline data-series="line" points="0,10 90,90" /></svg>
<label>n <input type="range" id="n" min="1" max="5" value="2"></label>
<p>Value: <output id="out">2</output></p>
<button onclick="go()">Double</button>
<script>
  function go() {
    const n = Number(document.getElementById('n').value);
    document.getElementById('out').textContent = String(n * 2);
  }
</script>
</body></html>"""

#: Structurally perfect, and divides by a zero step the moment it is driven -- the failure
#: mode that validation cannot see.
NON_FINITE = GOOD.replace('String(n * 2)', 'String(n / (n - n))')

THROWING = GOOD.replace('String(n * 2)', 'String(missingFunction(n))')

needs_browser = pytest.mark.skipif(not sims_check.available(),
                                   reason='playwright is not installed in this environment')


def test_an_empty_artifact_is_not_checked():
    report = sims_check.check('')
    assert report['checked'] is False
    assert report['problems'] == ['The artifact is empty.']


def test_a_missing_browser_reports_unverified_never_a_pass(monkeypatch):
    """The dangerous default would be silence: an unrun check that looks like a clean one."""
    monkeypatch.setattr(sims_check, 'available', lambda: False)
    report = sims_check.check(GOOD)
    assert report['checked'] is False
    assert report['problems'] == []
    assert 'playwright' in report['reason']
    assert 'unknown' in report['reason'].casefold()


@needs_browser
def test_a_working_artifact_passes():
    report = sims_check.check(GOOD)
    assert report['checked'] is True
    assert report['problems'] == [], report['problems']


@needs_browser
def test_a_non_finite_value_is_caught_after_the_page_is_driven():
    """The measured failure: valid HTML, correct axes, and Infinity once Stimulate is pressed."""
    report = sims_check.check(NON_FINITE)
    assert report['checked'] is True
    assert any('non-finite' in problem for problem in report['problems']), report['problems']


@needs_browser
def test_a_throwing_script_is_caught():
    report = sims_check.check(THROWING)
    assert report['checked'] is True
    assert any('threw' in problem for problem in report['problems']), report['problems']


# ------------------------------------------------------------ the tool surface

def _ctx(settings):
    class Principal:
        role = 'teacher'
        id = 'p'
        email = 'p@example.test'
    return toolbox.ToolContext(settings=settings, user=Principal(), now=1_700_000_000.0)


def _stored(settings, html):
    entry = sims_store.create_artifact(settings, kind='simulation', title='T', html=html)
    return entry['id']


def test_check_simulation_is_registered_and_offered_to_the_ta():
    from app.harness import ta
    assert 'check_simulation' in toolbox.REGISTRY
    assert 'check_simulation' in ta.TA_TOOLS


def test_the_tool_says_unverified_rather_than_broken_without_a_browser(settings, monkeypatch):
    """A missing browser must not send the TA to rebuild a simulation that may be fine."""
    monkeypatch.setattr(sims_check, 'available', lambda: False)
    artifact_id = _stored(settings, GOOD)
    result = toolbox.invoke(_ctx(settings), 'check_simulation', {'artifact_id': artifact_id})
    assert not result.ok
    assert result.data['checked'] is False
    assert 'could not be verified' in result.refused.casefold()
    assert 'not the same as broken' in result.refused.casefold()


def test_the_tool_reports_an_unknown_artifact(settings):
    result = toolbox.invoke(_ctx(settings), 'check_simulation', {'artifact_id': 'sim-nope'})
    assert not result.ok
    assert 'unknown artifact' in result.error.casefold()
