"""The teacher-assistant card merge, exercised without a browser.

The bug this pins: ``app.js`` built its result rows with

    for (const item of payload.cards || []) {
      if (item.kind === 'image' && !item.sha && shaByUrl.has(item.url)) {
        item = { ...item, sha: shaByUrl.get(item.url) };   // TypeError
      }

Reassigning a ``const`` raises ``TypeError: Assignment to constant variable`` the
first time an image card has a cached sha - and because the throw happens inside
the render loop, every card after that one is lost too. A plain ``node --check``
never sees it: the syntax is fine.

The merge now lives in ``web/cards.js`` as a pure function precisely so it can be
run here, and so the failure mode is a test rather than a blank panel. ``app.js``
loads that file via a second ``<script>`` tag (asserted below) and calls
``window.LuminfestCards.mergeCachedSha``.

These tests shell out to ``node`` because the module is browser-facing JavaScript;
there is no Python build of it to import. If ``node`` is absent the file is
skipped rather than failing, so a Python-only machine still gets a green suite -
but a machine that has node always runs them.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[2]
CARDS_JS = HARNESS / 'web' / 'cards.js'
APP_JS = HARNESS / 'web' / 'app.js'
INDEX_HTML = HARNESS / 'web' / 'index.html'

NODE = shutil.which('node')
pytestmark = pytest.mark.skipif(NODE is None, reason='node is not installed here')

PROBE = r"""
const cards = require(process.env.LUMINFEST_CARDS_JS);

const withSha = cards.mergeCachedSha(
  [{ kind: 'image', url: 'https://x/a.png' }, { kind: 'text', text: 'kept' }],
  new Map([['https://x/a.png', 'abc123']])
);
const withoutSha = cards.mergeCachedSha(
  [{ kind: 'image', url: 'https://x/b.png' }],
  new Map([['https://x/other.png', 'zzz']])
);
const empty = cards.mergeCachedSha(undefined, undefined);
const media = cards.shaMapFromMedia([
  { sha: 'abc123', thumb_url: 'https://x/a.png' },
  { sha: 'nosha', thumb_url: '' },
  null,
]);
const original = [{ kind: 'image', url: 'https://x/a.png' }];
cards.mergeCachedSha(original, new Map([['https://x/a.png', 'abc123']]));

console.log(JSON.stringify({
  merged_sha: withSha[0].sha,
  merged_kind_kept: withSha[1].kind,
  merged_length: withSha.length,
  no_match_sha: withoutSha[0].sha === undefined,
  empty_length: empty.length,
  map_size: media.size,
  map_value: media.get('https://x/a.png'),
  input_not_mutated: original[0].sha === undefined,
}));
"""


def _probe():
    import os

    env = dict(os.environ, LUMINFEST_CARDS_JS=str(CARDS_JS))
    result = subprocess.run([NODE, '-e', PROBE],
                            capture_output=True, text=True, timeout=30, env=env)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_the_merge_attaches_a_cached_sha_and_keeps_every_other_card():
    """The exact case that used to throw: an image card plus a non-image card."""
    out = _probe()
    assert out['merged_sha'] == 'abc123'
    assert out['merged_kind_kept'] == 'text'
    assert out['merged_length'] == 2, 'a throw here is what lost the remaining cards'


def test_a_card_without_a_cached_media_row_is_left_alone():
    out = _probe()
    assert out['no_match_sha'] is True


def test_an_empty_payload_does_not_throw():
    """``payload.cards`` is optional; ``undefined`` must not be a crash."""
    out = _probe()
    assert out['empty_length'] == 0


def test_the_sha_map_requires_both_a_sha_and_a_url():
    out = _probe()
    assert out['map_size'] == 1
    assert out['map_value'] == 'abc123'


def test_the_merge_does_not_mutate_its_input():
    out = _probe()
    assert out['input_not_mutated'] is True


def test_app_js_uses_the_helper_instead_of_reassigning_a_const():
    """The regression guard: the inline loop must not come back."""
    source = APP_JS.read_text(encoding='utf-8')
    assert 'LuminfestCards' in source
    assert 'mergeCachedSha' in source
    assert 'for (const item of payload.cards' not in source, \
        'the const-reassigning loop is back; see web/cards.js'


def test_index_html_loads_cards_js_before_app_js():
    """Load order is the whole contract: app.js reads the global at call time."""
    html = INDEX_HTML.read_text(encoding='utf-8')
    cards_at = html.find('/web/cards.js')
    app_at = html.find('/web/app.js')
    assert cards_at != -1 and app_at != -1
    assert cards_at < app_at
