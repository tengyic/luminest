"""The warm-up script's ``--force`` replaces a concept's row, never multiplies it.

``video.curate()`` is append-only and keyed by (concept_id, video_id), so a
second run that finds a different winner would leave two rows for one concept
and ``video.resolve()`` would hand the lesson both. The script prunes older
rows *after* a new winner has been written. These tests pin both halves of that
bound: a successful re-curation replaces, and a failed one deletes nothing.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
COURSE = 'algebra_1'


def _load_script():
    path = SCRIPTS / 'populate_video_allowlist.py'
    spec = importlib.util.spec_from_file_location('lf_populate_video_allowlist', path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _install(monkeypatch, rows, outcome):
    """Wire the script to an in-memory allowlist and a canned curation result."""
    script = _load_script()
    settings = SimpleNamespace(media_enabled=True, data_dir='/tmp/unused')
    store = {COURSE: list(rows)}

    monkeypatch.setattr(script.Settings, 'from_env', classmethod(lambda cls: settings))
    monkeypatch.setattr(script.chromium_search, 'available', lambda: (True, 'Chromium OK'))
    monkeypatch.setattr(script.courses, 'DEFAULT_COURSE_ID', COURSE)
    monkeypatch.setattr(script, 'concept_rows',
                        lambda _course: [{'id': 'ratios', 'title': 'Ratios',
                                          'keywords': ['ratio']}])
    monkeypatch.setattr(script.video, 'load_allowlist', lambda _s: {COURSE: list(store[COURSE])})
    monkeypatch.setattr(script.video, 'allowlist_path', lambda _s: '/tmp/unused/list.json')

    def save(_settings, table):
        store[COURSE] = list(table.get(COURSE, []))
        return '/tmp/unused/list.json'

    monkeypatch.setattr(script.video, 'save_allowlist', save)

    def curate(*_a, **_k):
        if outcome.get('curated'):
            # What video.curate() actually does on a new winner: append a row.
            winner = outcome['video']['video_id']
            store[COURSE].append({'concept_id': 'ratios', 'video_id': winner,
                                  'provider': 'youtube'})
        return dict(outcome)

    monkeypatch.setattr(script.video_search, 'curate_for_concept', curate)
    return script, store


def _ratios(store):
    return [r['video_id'] for r in store[COURSE] if r['concept_id'] == 'ratios']


def _run(script, capsys, *extra):
    code = script.main(['ratios', '--force', '--pause', '0', '--json', *extra])
    out = json.loads(capsys.readouterr().out)
    return code, out


def test_force_replaces_older_rows_after_a_new_winner(monkeypatch, capsys):
    script, store = _install(monkeypatch, [
        {'concept_id': 'ratios', 'video_id': 'OLD-ONE', 'provider': 'youtube'},
        {'concept_id': 'ratios', 'video_id': 'OLD-TWO', 'provider': 'youtube'},
        {'concept_id': 'fractions', 'video_id': 'KEEP-ME', 'provider': 'youtube'},
    ], {'curated': True, 'video': {'video_id': 'NEW-WINNER'},
        'path': 'youtube_page', 'reason': ''})

    code, out = _run(script, capsys)
    assert code == 0
    assert _ratios(store) == ['NEW-WINNER'], 'the two older rows must be pruned'
    assert 'KEEP-ME' in [r['video_id'] for r in store[COURSE]]
    assert out['replaced'] == 2
    assert out['curated'] == 1


def test_a_failed_recuration_deletes_nothing(monkeypatch, capsys):
    script, store = _install(monkeypatch, [
        {'concept_id': 'ratios', 'video_id': 'OLD-ONE', 'provider': 'youtube'},
        {'concept_id': 'ratios', 'video_id': 'OLD-TWO', 'provider': 'youtube'},
    ], {'curated': False, 'reason': 'no on-topic candidate'})

    code, out = _run(script, capsys)
    assert code == 0
    assert _ratios(store) == ['OLD-ONE', 'OLD-TWO'], 'no new winner => keep both'
    assert out['replaced'] == 0


def test_without_force_an_existing_concept_is_skipped_entirely(monkeypatch, capsys):
    script, store = _install(monkeypatch, [
        {'concept_id': 'ratios', 'video_id': 'OLD-ONE', 'provider': 'youtube'},
    ], {'curated': True, 'video': {'video_id': 'SHOULD-NOT-RUN'}, 'reason': ''})
    monkeypatch.setattr(script.video_search, 'curate_for_concept',
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError('curated')))

    code = script.main(['ratios', '--pause', '0', '--json'])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out['skipped'] == 1 and out['curated'] == 0
    assert _ratios(store) == ['OLD-ONE']
