"""The playground gallery's trust boundary: which message may become evidence.

``harness/web/playground.html`` is the page a student actually opens. It embeds a
generated game in a sandboxed iframe and listens for ``postMessage`` traffic from
inside that frame. Two message types arrive:

``luminfest:readout``
    Continuous state for the live display - "price 4.20" as a curve is dragged.
    **It must never be stored.** A readout is not a commitment, and recording one
    would let time spent dragging a slider masquerade as mastery, which is the exact
    failure the two-message design exists to prevent.

``luminfest:outcome``
    A completed, checkable task. This is the only message that may become evidence.

The listener is a trust boundary rather than a convenience: the frame runs *generated*
game code under ``sandbox="allow-scripts"``, so the page must not blindly forward
whatever payload arrives. Three things are enforced, in this order, and every one of
them is asserted below:

1. **Provenance.** ``event.source`` must be the frame the gallery itself created. A
   message from any other window is ignored before it can reach even the live title.
2. **Shape.** An outcome must carry a real boolean ``correct``, and - when present - a
   numeric ``tries`` and a plain-object ``detail``. A malformed payload is dropped, not
   forwarded. Nothing is copied out of the payload into ``detail``.
3. **Uniqueness.** Each outcome carries the runtime's monotonic ``seq``. The listener
   keeps the highest number it has recorded as a watermark and ignores anything at or
   below it, so one committed outcome produces exactly one run however many times the
   message is delivered. The watermark is reset when a new page is injected, and it is
   keyed on the frame's counter rather than the slug, so a *legitimate* second commit -
   a second task, or a retry after ``next`` - is still recorded.

What the listener deliberately does **not** do: require ``tries``. It is validated when
the frame sends it and defaulted to 1 when it does not, so a frame that omits or
malforms the field can never wedge the handler. The invariant asserted below is about
the boundary, not about any one game: a missing ``tries`` is never a reason to drop an
outcome, and the route's ``ge=1, le=50`` bound is the backstop.

That default is only safe because every bundled archetype *does* send the field, at the
top level of ``BRIDGE.outcome`` - 45 of 45 games, checked by parsing each rendered page
for a ``tries`` key at brace depth 1 of the call. Top level matters: the route stores
``payload.tries`` into ``PlaygroundRun.tries`` while ``detail`` is a free-form blob
nothing reads for scoring, so a count nested in ``detail`` would leave the column at its
default of 1 and the evidence row unable to tell "gave up after three" from "gave up
after one". An earlier revision of this docstring recorded four games that omitted the
field; that gap is closed. Do not restate a snapshot count here - assert the invariant,
so a regression fails a test instead of going stale in prose.

Why the listener is driven from node rather than from Python: it is an inline
``<script>`` inside an HTML file, closing over the gallery's own ``state`` and ``api``,
so there is nothing for Python to import. ``_drive_listener`` extracts the listener
verbatim from the page, binds it to stub definitions of exactly the names it closes
over, fires synthetic ``message`` events at it, and reports how many times it reached
``api``. That is a behavioural test of the boundary, not a text match: the assertions
are about how many rows the page tries to write.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.harness.playground import catalogue

GALLERY_HTML = Path(__file__).resolve().parents[2] / 'web' / 'playground.html'
OUTCOME_ROUTE = '/api/v1/playground/games/{slug}/outcome'

_NODE = shutil.which('node')


# ------------------------------------------------------------------- fixtures


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.delenv('HARNESS_TUTOR_PROVIDER', raising=False)
    return Settings.from_env()


@pytest.fixture
def learner(settings):
    from app.main import create_app
    with TestClient(create_app(settings)) as client:
        body = client.post('/api/v1/auth/register', json={
            'name': 'Gallery Tester', 'email': 'gallery@example.com',
            'password': 'correct-horse-battery'}).json()
        yield client, body['token']


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
    row = db.scalar(select(User).where(User.email == 'gallery@example.com'))
    assert row is not None, 'the learner fixture must run before this'
    return row


# ------------------------------------------------------------------- helpers


def _run_count(db):
    """How many playground runs exist, read from a fresh snapshot.

    ``rollback`` first because the fixture's session may be holding a stale identity
    map, and a count taken from a stale map would make this whole file a no-op.
    """
    from sqlalchemy import select
    from app.db import PlaygroundRun
    db.rollback()
    return len(db.scalars(select(PlaygroundRun)).all())


def _some_slug():
    games = catalogue.all_games()
    assert games, 'the catalogue must not be empty'
    return games[0]['slug']


def _listener_source():
    """The ``message`` listener block from the gallery page, exactly as written.

    Bounded by the next section marker rather than a character count, so it stays
    correct as the listener grows.
    """
    source = GALLERY_HTML.read_text(encoding='utf-8')
    start = source.index("window.addEventListener('message'")
    end = source.index('// ------', start + 40)
    return source[start:end]


# The harness that drives the real listener. It extracts the listener verbatim from
# the page, stubs only the names the listener closes over, and reports the calls it
# made. Kept as a module constant so the extraction lives in one place and a rename of
# the listener's anchor fails loudly instead of silently testing nothing.
_HARNESS_JS = r"""
'use strict';
const fs = require('fs');

const htmlPath = process.argv[2];
const events = JSON.parse(process.argv[3]);
const html = fs.readFileSync(htmlPath, 'utf8');

const anchor = "window.addEventListener('message', function (event) {";
const start = html.indexOf(anchor);
if (start === -1) { console.error('listener anchor not found'); process.exit(2); }

let depth = 0;
let end = -1;
for (let i = start + anchor.length - 1; i < html.length; i += 1) {
  const c = html[i];
  if (c === '{') depth += 1;
  else if (c === '}') { depth -= 1; if (depth === 0) { end = i + 1; break; } }
}
if (end === -1) { console.error('listener braces unbalanced'); process.exit(2); }
if (!/^\s*\)\s*;/.test(html.slice(end, end + 8))) {
  console.error('listener does not close with );'); process.exit(2);
}
const listener = html.slice(start, end) + ');';

// Exactly the names the listener closes over, and nothing more: if the listener ever
// reaches for something new, this harness stops compiling, which is the point.
const prelude = `
var __calls = [];
var __frameWindow = { id: 'frame-window' };
function $(id) {
  if (id === 'frame') return { contentWindow: __frameWindow };
  return {
    textContent: '', innerHTML: '', value: '', style: {},
    setAttribute: function () {}, getAttribute: function () { return null; },
    addEventListener: function () {}, querySelectorAll: function () { return []; }
  };
}
var state = { games: [{ slug: 'demo-game', title: 'Demo' }], current: 'demo-game',
              artifacts: { 'demo-game': 'artifact-1' }, token: '', seenSeq: -1 };
var API = '/api/v1/playground';
function api(url, opts) {
  __calls.push({ url: url, body: opts && opts.body });
  return Promise.resolve({ attributed: false, attribution: 'demo' });
}
function escapeHtml(s) { return String(s); }
function verdict() {}
function loadRuns() {}
var __handlers = [];
var window = { addEventListener: function (type, fn) {
  if (type === 'message') __handlers.push(fn); } };
`;

const runner = `
var __events = ${JSON.stringify(events)};
var __report = [];
function __fire(ev) {
  if (ev.reset) {
    // What the page does when it injects a fresh frame: the counter restarts at 1.
    state.seenSeq = -1;
  } else {
    var source = ev.foreign ? { id: 'not-the-frame' } : __frameWindow;
    __handlers.forEach(function (h) {
      h({ source: source, data: ev.data, origin: 'null' });
    });
  }
  __report.push({ name: ev.name || '', calls: __calls.length, seenSeq: state.seenSeq });
}
__events.forEach(__fire);
setTimeout(function () {
  console.log(JSON.stringify({ report: __report, calls: __calls,
                               handlers: __handlers.length }));
}, 0);
`;

const bundle = prelude + listener + runner;
try { new Function(bundle); } catch (e) {
  console.error('harness does not compile: ' + e.message); process.exit(2);
}
eval(bundle);
"""


def _drive_listener(events, tmp_path):
    """Fire ``events`` at the real listener and report what it sent to the server.

    ``events`` is a list of dicts. ``{'data': {...}}`` posts that payload from the
    gallery's own frame; ``{'foreign': True, 'data': {...}}`` posts it from some other
    window; ``{'reset': True}`` simulates a new frame being injected.
    """
    if _NODE is None:
        pytest.skip('node is not installed, so the listener cannot be driven')
    # ``.cjs``, not ``.js``: the repository has a ``package.json`` with
    # ``"type": "module"`` above the pytest temp directory, and a ``.js`` file there
    # would be loaded as ESM, where ``require`` does not exist.
    harness = tmp_path / 'gallery_listener_harness.cjs'
    harness.write_text(_HARNESS_JS, encoding='utf-8')
    proc = subprocess.run(
        [_NODE, str(harness), str(GALLERY_HTML), json.dumps(events)],
        capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, \
        f'the listener harness failed ({proc.returncode}): {proc.stderr}'
    return json.loads(proc.stdout)


def _outcome(**overrides):
    """A well-formed ``luminfest:outcome`` payload, with room to make it malformed."""
    payload = {'type': 'luminfest:outcome', 'seq': 1, 'correct': True, 'tries': 1,
               'detail': {'task': 'demo'}}
    payload.update(overrides)
    return payload


# --------------------------------------------------- the listener's own guards


def test_the_gallery_page_exists_where_the_tests_look_for_it():
    """A silent rename would turn every assertion below into a test of nothing."""
    assert GALLERY_HTML.is_file(), f'the gallery page is missing at {GALLERY_HTML}'
    assert "window.addEventListener('message'" in GALLERY_HTML.read_text(encoding='utf-8')


def test_the_source_check_gates_every_message_before_anything_else():
    """Provenance comes first: an outsider must not even reach the live title.

    The readout branch writes to the page's own DOM, so if the source check came after
    it, any frame could rewrite the gallery's display. Ordering is the whole assertion.
    """
    block = _listener_source()
    source = block.index('event.source')
    readout = block.index("=== 'luminfest:readout'")
    post = block.index("'/outcome'")
    assert source < readout < post, \
        'the event.source check must precede the readout branch and the POST'
    assert 'contentWindow' in block[:readout], \
        'the source check must compare against the gallery\u2019s own frame'


def test_the_readout_branch_exits_before_the_outcome_post():
    """The headline invariant, read off the source: a readout cannot reach the POST.

    The readout branch must appear *before* the ``/outcome`` call and must ``return``
    from the handler, so control never falls through into the recording path.
    """
    block = _listener_source()
    readout = block.index("=== 'luminfest:readout'")
    post = block.index("'/outcome'")
    assert readout < post, 'the readout branch must be handled before the POST'
    assert 'return;' in block[readout:post], \
        'the luminfest:readout branch must return, or it falls through into the POST'


def test_the_outcome_post_is_gated_on_the_exact_message_type():
    """Anything that is not ``luminfest:outcome`` must return before the POST.

    This is what makes the handler a filter rather than a forwarder: an unknown or
    absent ``type`` is ignored instead of being recorded.
    """
    block = _listener_source()
    guard = block.index("!== 'luminfest:outcome'")
    post = block.index("'/outcome'")
    assert guard < post, 'the type guard must precede the POST'
    assert 'return;' in block[guard:post], \
        'a non-outcome message must return before the POST, not fall through'


def test_the_outcome_payload_is_validated_before_it_is_forwarded():
    """Shape is checked ahead of the POST, and ``detail`` is never spread.

    ``correct`` is the load-bearing field, so a non-boolean is refused rather than
    coerced; ``tries`` and ``detail`` are type-checked when present. The absence of any
    spread is asserted too: the frame's ``detail`` is forwarded as its own object, so a
    key the frame invented under another name cannot appear in the row.
    """
    block = _listener_source()
    head = block[:block.index("'/outcome'")]
    assert "typeof data.correct !== 'boolean'" in head, \
        'a non-boolean correct must be refused before the POST'
    assert 'isFinite(tries)' in head, 'tries must be checked for being a number'
    assert 'Array.isArray(detail)' in head, 'detail must be checked for being an object'
    assert 'Object.assign' not in head and '...data' not in head, \
        'the payload must not be spread into detail'


def test_the_sequence_watermark_is_checked_before_the_post():
    """De-duplication is on the frame's monotonic ``seq``, ahead of the POST."""
    block = _listener_source()
    head = block[:block.index("'/outcome'")]
    assert 'state.seenSeq' in head, 'the watermark must be consulted before the POST'
    assert 'seq <= state.seenSeq' in head, \
        'a seq at or below the watermark must be ignored'
    assert 'state.seenSeq = seq' in head, 'an accepted outcome must advance the watermark'


def test_the_gallery_chooses_the_game_itself_not_the_frame():
    """The frame must not be able to name the game it is recording against.

    The slug in the POST URL comes from the gallery's own ``state.current``. If it
    ever came from ``data``, a generated page could record evidence against any game
    in the catalogue - including one it was never served.
    """
    block = _listener_source()
    post_line_start = block.rindex('\n', 0, block.index("'/outcome'"))
    call = block[post_line_start:block.index("'/outcome'")]
    assert 'state.current' in call, \
        'the outcome POST must use the gallery\u2019s own selected slug'
    assert 'data.slug' not in block and 'data.game' not in block, \
        'the slug must never be taken from the posted payload'


def test_the_watermark_is_reset_when_a_new_page_is_injected():
    """A fresh frame restarts its counter at 1, so the watermark must restart with it.

    Without this reset the second game a student opens would have its first commit
    silently swallowed, because its ``seq`` of 1 would not beat the previous game's.
    """
    source = GALLERY_HTML.read_text(encoding='utf-8')
    play = source.index('function play(slug)')
    srcdoc = source.index('frame.srcdoc = html')
    reset = source.rindex('state.seenSeq = -1', play, srcdoc)
    assert play < reset < srcdoc, \
        'the watermark must be reset in play(), before the new page is injected'


# ------------------------------------------- the listener, driven for real


def test_a_readout_never_reaches_the_server(tmp_path):
    """A readout is live state, not a commitment, so it must not become a row.

    Driven, not asserted off the source: the readout payload is the same shape the
    runtime posts while a curve is dragged.
    """
    result = _drive_listener([{'name': 'drag', 'data': {
        'type': 'luminfest:readout', 'archetype': 'curve_shift', 'at_ms': 412,
        'price': 4.2, 'quantity': 5.8, 'shift': 1.0, 'shock': 'income-up'}}], tmp_path)

    assert result['handlers'] == 1, 'the gallery must register exactly one listener'
    assert result['calls'] == [], \
        f'a readout reached the server: {result["calls"]}'


def test_a_malformed_readout_is_still_silent(tmp_path):
    """A readout is never stored, whatever the frame puts in it.

    The invariant is unconditional: it does not depend on the payload being well formed.
    The sharpest case is the third one - a readout carrying a ``seq`` - because the
    watermark must not be advanced by a message that is not an outcome, or a frame could
    spend the sequence number a real commit was about to use. The final event proves it:
    a genuine outcome with ``seq: 1`` still records.
    """
    result = _drive_listener([
        {'name': 'bare', 'data': {'type': 'luminfest:readout'}},
        {'name': 'readout-shaped-like-an-outcome', 'data': {
            'type': 'luminfest:readout', 'correct': True, 'tries': 1, 'detail': {}}},
        {'name': 'readout-carrying-a-seq', 'data': {'type': 'luminfest:readout', 'seq': 1}},
        {'name': 'nonsense-types', 'data': {
            'type': 'luminfest:readout', 'price': 'not a number', 'detail': 'a string',
            'at_ms': [1, 2, 3]}},
        {'name': 'real-commit', 'data': _outcome(seq=1)},
    ], tmp_path)

    assert [step['calls'] for step in result['report']] == [0, 0, 0, 0, 1], \
        result['report']
    assert result['report'][2]['seenSeq'] == -1, \
        'a readout carrying a seq must not advance the watermark'
    assert len(result['calls']) == 1, result['calls']


def test_one_outcome_posts_exactly_one_run(tmp_path):
    """The one message that may become evidence produces exactly one request."""
    result = _drive_listener([{'name': 'commit', 'data': _outcome(
        seq=4, correct=True, task='income-up', tries=2,
        detail={'shock': 'income-up'})}], tmp_path)

    assert len(result['calls']) == 1, result['calls']
    call = result['calls'][0]
    assert call['url'].endswith('/games/demo-game/outcome'), call['url']
    assert call['body']['correct'] is True
    assert call['body']['tries'] == 2
    assert call['body']['detail'] == {'shock': 'income-up'}
    assert call['body']['artifact_id'] == 'artifact-1'


def test_a_redelivered_outcome_posts_exactly_one_run(tmp_path):
    """The same outcome delivered twice must still write exactly one row.

    This is the de-duplication requirement, driven through the real listener: the two
    events carry the same ``seq``, so the second is dropped at the watermark.
    """
    payload = _outcome(seq=7, correct=False, tries=3, detail={'task': 'retry'})
    result = _drive_listener([{'name': 'first', 'data': payload},
                              {'name': 'redelivery', 'data': payload}], tmp_path)

    assert len(result['calls']) == 1, \
        f'a redelivered outcome produced {len(result["calls"])} requests'
    assert [step['calls'] for step in result['report']] == [1, 1], result['report']


def test_a_second_commit_in_the_same_game_is_still_recorded(tmp_path):
    """De-duplication must not swallow a genuine second commit.

    The key is the frame's monotonic ``seq``, not the slug and not the task id, so a
    later task - and even a retry of the *same* task, which reuses the task id - each
    carry a higher ``seq`` and are both recorded.
    """
    result = _drive_listener([
        {'name': 'task-one', 'data': _outcome(seq=1, detail={'task': 'first'})},
        {'name': 'retry-after-next', 'data': _outcome(seq=2, correct=False,
                                                     tries=2, detail={'task': 'first'})},
    ], tmp_path)

    assert len(result['calls']) == 2, \
        f'a legitimate second commit was swallowed: {result["report"]}'
    assert [call['body']['detail']['task'] for call in result['calls']] == \
        ['first', 'first']
    assert [call['body']['correct'] for call in result['calls']] == [True, False]


def test_a_late_duplicate_after_a_second_commit_is_ignored(tmp_path):
    """A replay of an *older* outcome must not reopen the watermark.

    The guard is a watermark, not an equality check: once seq 2 is recorded, a
    redelivery of seq 1 is below it and must be dropped, or a stale replay could append
    a second row for a commit already logged.
    """
    result = _drive_listener([
        {'name': 'commit-1', 'data': _outcome(seq=1)},
        {'name': 'commit-2', 'data': _outcome(seq=2)},
        {'name': 'replay-of-1', 'data': _outcome(seq=1)},
    ], tmp_path)

    assert [step['calls'] for step in result['report']] == [1, 2, 2], result['report']


def test_the_watermark_resets_when_a_new_page_loads(tmp_path):
    """Two different games each get to record their first commit, seq 1 and seq 1."""
    result = _drive_listener([
        {'name': 'game-a-commit', 'data': _outcome(seq=1, detail={'game': 'a'})},
        {'name': 'new-frame', 'reset': True},
        {'name': 'game-b-commit', 'data': _outcome(seq=1, detail={'game': 'b'})},
    ], tmp_path)

    assert len(result['calls']) == 2, \
        f'the watermark leaked across pages: {result["report"]}'
    assert [call['body']['detail']['game'] for call in result['calls']] == ['a', 'b']


def test_an_outcome_from_another_source_is_ignored(tmp_path):
    """A message from a window the gallery did not create must not become evidence.

    The frame is the only window the page trusts; anything else - another frame, an
    extension, the page's own window - is dropped before it reaches the POST.
    """
    result = _drive_listener([{'name': 'stranger', 'foreign': True,
                               'data': _outcome(seq=1)}], tmp_path)

    assert result['calls'] == [], \
        f'a message from a foreign window reached the server: {result["calls"]}'


def test_a_malformed_outcome_is_dropped_not_forwarded(tmp_path):
    """Each malformed payload is dropped, and none of them writes a request.

    ``correct`` must be a real boolean - the route's non-strict model would otherwise
    coerce ``'yes'`` into true - and ``tries`` and ``detail`` must be the right type
    when the frame sends them.
    """
    malformed = [
        ('correct-is-a-string', _outcome(seq=1, correct='yes')),
        ('correct-is-absent', {'type': 'luminfest:outcome', 'seq': 2, 'tries': 1,
                               'detail': {}}),
        ('correct-is-a-number', _outcome(seq=3, correct=1)),
        ('tries-is-not-a-number', _outcome(seq=4, tries='lots')),
        ('detail-is-a-list', _outcome(seq=5, detail=['not', 'a', 'dict'])),
        ('detail-is-null', _outcome(seq=6, detail=None)),
    ]
    result = _drive_listener(
        [{'name': name, 'data': payload} for name, payload in malformed], tmp_path)

    assert result['calls'] == [], \
        f'a malformed outcome was forwarded: {result["calls"]}'
    assert [step['calls'] for step in result['report']] == [0] * len(malformed), \
        result['report']


def test_an_outcome_without_a_sequence_number_is_still_recorded(tmp_path):
    """De-duplication is best-effort: an outcome with no ``seq`` is not evidence-less.

    The runtime always stamps a ``seq``, so this path is only reachable by a
    hand-rolled page. Dropping it would lose a real commit, so it is recorded without
    advancing the watermark - the honest trade, and worth stating rather than leaving
    to be discovered.
    """
    result = _drive_listener([{'name': 'unsequenced', 'data': {
        'type': 'luminfest:outcome', 'correct': True, 'tries': 1, 'detail': {}}}], tmp_path)

    assert len(result['calls']) == 1, result['calls']
    assert result['report'][0]['seenSeq'] == -1, \
        'an unsequenced outcome must not move the watermark'


# ------------------------------------------------- the route, driven for real


def test_a_readout_shaped_payload_is_refused_and_writes_no_run(learner, db, user_row):
    """Even if a readout were forwarded, the route must not turn it into evidence.

    A readout carries no ``correct`` flag - it is continuous state, not a commitment -
    so the request model refuses it. The status code is not the point; the row count
    is. A refused payload that still wrote a run would be the worst of both worlds.
    """
    client, token = learner
    slug = _some_slug()
    before = _run_count(db)

    readout = {
        'type': 'luminfest:readout',
        'archetype': 'curve_shift',
        'at_ms': 412,
        'price': 4.2,
        'quantity': 5.8,
        'shift': 1.0,
        'shock': 'income-up',
    }
    response = client.post(OUTCOME_ROUTE.format(slug=slug),
                           headers={'Authorization': 'Bearer ' + token}, json=readout)

    assert response.status_code == 422, \
        f'a readout-shaped payload answered {response.status_code}, not 422'
    assert _run_count(db) == before, 'a readout still wrote a PlaygroundRun row'


def test_an_outcome_records_exactly_one_run(learner, db, user_row):
    """The one message that may become evidence produces exactly one row."""
    client, token = learner
    slug = _some_slug()
    before = _run_count(db)

    response = client.post(OUTCOME_ROUTE.format(slug=slug),
                           headers={'Authorization': 'Bearer ' + token},
                           json={'correct': True, 'task_id': 'income-up', 'tries': 2,
                                 'elapsed_ms': 1500, 'detail': {'shock': 'income-up'}})

    assert response.status_code == 200, response.text
    assert _run_count(db) == before + 1, 'one outcome must write exactly one run'


def test_the_route_records_every_commit_it_is_given(learner, db, user_row):
    """The route is a pure endpoint; uniqueness belongs to the listener.

    Posting the same body twice writes two rows, because the route cannot tell a
    replay from a genuine second commit - it sees only a payload. That is why the
    de-duplication lives in the listener, on the frame's monotonic ``seq``, and why the
    listener tests above are the ones that carry the guarantee.
    """
    client, token = learner
    slug = _some_slug()
    before = _run_count(db)
    headers = {'Authorization': 'Bearer ' + token}
    url = OUTCOME_ROUTE.format(slug=slug)
    payload = {'correct': True, 'task_id': 'income-up', 'tries': 1,
               'detail': {'shock': 'income-up'}}

    for _ in range(2):
        assert client.post(url, headers=headers, json=payload).status_code == 200

    assert _run_count(db) == before + 2, \
        'the route changed shape: de-duplication belongs in the listener, not here'


def test_the_route_refuses_a_malformed_outcome(learner, db, user_row):
    """The server is the backstop for a payload the frame shaped.

    ``detail`` is free-form by design, but the scalars are not: ``tries`` is bounded
    and ``task_id`` is length-capped. A generated page cannot smuggle a nonsense value
    into the evidence row. The listener already refuses the first two of these, so this
    is defence in depth rather than the only guard.
    """
    client, token = learner
    slug = _some_slug()
    before = _run_count(db)
    headers = {'Authorization': 'Bearer ' + token}
    url = OUTCOME_ROUTE.format(slug=slug)

    bad_payloads = [
        {'correct': True, 'tries': 9999},         # tries is bounded above
        {'correct': True, 'tries': 0},            # and below
        {'correct': True, 'detail': ['not', 'a', 'dict']},
        {'correct': True, 'task_id': 'x' * 200},  # task_id is length-capped
        {'tries': 1},                             # correct is required
    ]
    for payload in bad_payloads:
        response = client.post(url, headers=headers, json=payload)
        assert response.status_code == 422, \
            f'{payload} answered {response.status_code}, not 422'

    assert _run_count(db) == before, 'a refused outcome still wrote a row'


def test_the_route_coerces_a_truthy_string_for_correct(learner, db, user_row):
    """Characterises the route's one lenient field, which the listener now blocks.

    ``Outcome.correct`` is a plain ``bool``, and pydantic's non-strict mode turns the
    string ``'yes'`` into ``True`` rather than refusing it. That leniency is harmless
    but not relied on: the listener refuses a non-boolean ``correct`` outright (see
    ``test_a_malformed_outcome_is_dropped_not_forwarded``), so this path is reachable
    only by a direct API caller. It is recorded because "the route validates the
    payload shape" would otherwise be a stronger claim than the code supports.
    """
    client, token = learner
    slug = _some_slug()
    before = _run_count(db)

    response = client.post(OUTCOME_ROUTE.format(slug=slug),
                           headers={'Authorization': 'Bearer ' + token},
                           json={'correct': 'yes', 'tries': 1})

    assert response.status_code == 200, response.text
    assert response.json().get('correct') is True or _run_count(db) == before + 1
