"""The web interaction channel, exercised without a browser.

Three properties matter more than coverage here, because the channel exists to
observe a learner and that is exactly where a learning product can leak:

1. **The grammar is the server's.** ``app/harness/telemetry.py`` closes the
   vocabulary (``click|tap|key|blur|focus``; fields ``kind``/``target``; target
   ``^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$``) and ``POST /events`` answers 422 for
   anything else. A client that sent a free-form name would produce rows the
   summary cannot use, so ``sanitizeTarget`` must always yield either a legal
   target or nothing.
2. **No content.** ``key`` records that a key was pressed, never which one, and
   a password or email field is not named at all.
3. **A blur/focus carries no target**, because the grammar forbids one.

If ``node`` is absent the JS tests skip; a Python-only machine still gets a green
suite, and a machine with node always runs them.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[2]
TELEMETRY_JS = HARNESS / 'web' / 'telemetry.js'
APP_JS = HARNESS / 'web' / 'app.js'
INDEX_HTML = HARNESS / 'web' / 'index.html'

NODE = shutil.which('node')
pytestmark = pytest.mark.skipif(NODE is None, reason='node is not installed here')

PROBE = r"""
const t = require(process.env.LUMINFEST_TELEMETRY_JS);

const sent = [];
let seq = 0;
const nextId = () => 'e' + (seq++);
const now = () => '2026-01-01T00:00:00.000Z';

const q = t.createQueue({ max: 3, now: now, id: nextId, send: (b) => sent.push(b) });

const clickOk = q.record('click', 'stage.tab.deck');
const spaceOk = t.sanitizeTarget('has a space');
const emptyTarget = q.record('click', '');
const badKind = q.record('nope', 'x');
const blurOk = q.record('blur');
const keyOk = q.record('key', 'web.token-input');

const capped = t.createQueue({ max: 2, now: now, id: nextId, send: (b) => sent.push(b) });
capped.record('click', 'web.a');
capped.record('click', 'web.b');

const longTarget = t.sanitizeTarget('a'.repeat(200));
const leadingJunk = t.sanitizeTarget('!!!');
const grammar = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$/;

console.log(JSON.stringify({
  click_ok: clickOk,
  empty_target_refused: emptyTarget === false,
  bad_kind_refused: badKind === false,
  blur_ok: blurOk,
  key_ok: keyOk,
  space_sanitised: spaceOk,
  space_matches_grammar: grammar.test(spaceOk),
  long_capped: longTarget.length,
  long_matches_grammar: grammar.test(longTarget),
  leading_junk_empty: leadingJunk,
  batches: sent.length,
  last_batch_len: sent.length ? sent[sent.length - 1].length : 0,
  shapes: sent.length ? sent[0].map((e) => Object.keys(e).sort().join(',')) : [],
  payload_keys: sent.length ? sent[0].map((e) => Object.keys(e.payload).sort().join(',')) : [],
  unique_ids: (() => {
    let u = 0;
    const qq = t.createQueue({ max: 99, now: now, id: () => 'u' + (u++), send: () => {} });
    qq.record('click', 'web.a'); qq.record('click', 'web.b');
    return new Set(qq.flush().map((e) => e.id)).size;
  })(),
}));
"""


def _probe():
    import os

    env = dict(os.environ, LUMINFEST_TELEMETRY_JS=str(TELEMETRY_JS))
    result = subprocess.run([NODE, '-e', PROBE],
                            capture_output=True, text=True, timeout=30, env=env)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_legal_events_are_accepted_and_illegal_ones_are_refused():
    out = _probe()
    assert out['click_ok'] is True
    assert out['blur_ok'] is True
    assert out['key_ok'] is True
    assert out['bad_kind_refused'] is True
    assert out['empty_target_refused'] is True


def test_every_target_that_is_sent_matches_the_server_grammar():
    out = _probe()
    assert out['space_matches_grammar'] is True
    assert out['long_matches_grammar'] is True
    assert out['long_capped'] <= 64
    assert out['leading_junk_empty'] == ''


def test_a_blur_carries_no_target_and_an_event_carries_only_the_four_fields():
    out = _probe()
    assert out['shapes'], 'no batch was sent'
    for shape in out['shapes']:
        assert shape == 'id,occurred_at,payload,type'
    # click/key name a target; blur does not. No payload ever carries a third key.
    assert all(keys in ('kind', 'kind,target') for keys in out['payload_keys'])


def test_the_batch_flushes_at_the_size_limit():
    out = _probe()
    assert out['batches'] >= 2, 'the size trigger did not fire'
    assert out['last_batch_len'] == 2


def test_ids_are_unique_so_the_server_can_deduplicate():
    """`POST /events` dedupes on `client_id`; two identical ids would drop events."""
    out = _probe()
    assert out['unique_ids'] == 2


def test_app_js_arms_the_channel_only_through_the_server_flag():
    source = APP_JS.read_text(encoding='utf-8')
    assert 'loadTelemetryConsent' in source
    assert 'telemetry_consent' in source
    assert "/api/v1/events" in source
    assert 'isSensitive' in source, 'password/email fields must never be named'
    assert "record('blur')" in source and "record('focus')" in source


def test_index_html_loads_telemetry_before_app():
    html = INDEX_HTML.read_text(encoding='utf-8')
    assert '/web/telemetry.js' in html
    assert html.find('/web/telemetry.js') < html.find('/web/app.js')
    assert 'telemetry-toggle' in html, 'the consent control must exist in the markup'
