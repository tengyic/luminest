"""On-demand video curation: it runs once, remembers a miss, never invents a card.

An ordinary lesson used to render ``videos: []`` forever when the allowlist had
no row for its concept. ``find_video`` now runs the teacher's curation job on the
first open. These tests pin the *bounds* of that behaviour: which switches arm
it, that a success re-reads the allowlist, and that a failure is not retried on
every subsequent request (which would launch a browser per lesson view).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from app.harness import toolbox

CARD = {
    'provider': 'youtube', 'title': 'Intro to equivalent fractions',
    'channel': 'Khan Academy', 'watch_url': 'https://www.youtube.com/watch?v=N1X0vf5PUz4',
    'licence': 'YOUTUBE_EMBED', 'licence_class': 'embed_only',
}


def _ctx(tmp_path, **overrides):
    switches = dict(data_dir=str(tmp_path), video_auto_curate=True,
                    media_enabled=True, chromium_search_enabled=True)
    switches.update(overrides)
    return SimpleNamespace(settings=SimpleNamespace(**switches),
                           course_id='algebra_1')


def test_a_miss_is_remembered_and_a_success_clears_it(tmp_path):
    settings = _ctx(tmp_path).settings
    assert toolbox._curation_recently_failed(settings, 'algebra_1', 'fractions') is False
    toolbox._remember_curation(settings, 'algebra_1', 'fractions', False)
    assert toolbox._curation_recently_failed(settings, 'algebra_1', 'fractions') is True
    path = tmp_path / 'media' / 'video_curation_attempts.json'
    assert 'algebra_1:fractions' in json.loads(path.read_text())
    toolbox._remember_curation(settings, 'algebra_1', 'fractions', True)
    assert toolbox._curation_recently_failed(settings, 'algebra_1', 'fractions') is False


def test_a_stale_attempt_does_not_suppress_a_retry(tmp_path, monkeypatch):
    settings = _ctx(tmp_path).settings
    toolbox._remember_curation(settings, 'algebra_1', 'fractions', False)
    real_now = toolbox.time.time()
    monkeypatch.setattr(toolbox.time, 'time',
                        lambda: real_now + toolbox.VIDEO_CURATE_RETRY_SECONDS + 10)
    assert toolbox._curation_recently_failed(settings, 'algebra_1', 'fractions') is False


def test_a_corrupt_attempts_file_is_an_absence_not_an_error(tmp_path):
    settings = _ctx(tmp_path).settings
    path = tmp_path / 'media' / 'video_curation_attempts.json'
    path.parent.mkdir(parents=True)
    path.write_text('{not json', encoding='utf-8')
    assert toolbox._curation_recently_failed(settings, 'algebra_1', 'fractions') is False


def test_an_empty_allowlist_triggers_curation_and_re_reads_it(monkeypatch, tmp_path):
    calls = {'resolve': 0, 'curate': 0}

    def fake_resolve(_settings, _course, _concept):
        calls['resolve'] += 1
        return [] if calls['resolve'] == 1 else [CARD]

    monkeypatch.setattr('app.harness.video.resolve', fake_resolve)
    monkeypatch.setattr(toolbox, '_curate_video_for_lesson',
                        lambda *a: calls.__setitem__('curate', calls['curate'] + 1)
                        or {'curated': True, 'path': 'youtube_page',
                            'video': {'video_id': 'N1X0vf5PUz4'}})
    result = toolbox.find_video(_ctx(tmp_path), 'fractions').to_dict()
    assert calls == {'resolve': 2, 'curate': 1}
    assert len(result['data']['videos']) == 1
    assert result['citations'][0]['source'] == 'Khan Academy'
    assert any('On-demand curation attached' in note for note in result['notes'])


def test_a_failed_curation_is_reported_and_suppressed_for_a_day(monkeypatch, tmp_path):
    monkeypatch.setattr('app.harness.video.resolve', lambda *a: [])
    monkeypatch.setattr(toolbox, '_curate_video_for_lesson',
                        lambda *a: {'curated': False, 'reason': 'no on-topic candidate'})

    first = toolbox.find_video(_ctx(tmp_path), 'fractions').to_dict()
    assert first['data']['videos'] == []
    assert any('no on-topic candidate' in note for note in first['notes'])

    calls = []
    monkeypatch.setattr(toolbox, '_curate_video_for_lesson',
                        lambda *a: calls.append(1) or {'curated': True})
    second = toolbox.find_video(_ctx(tmp_path), 'fractions').to_dict()
    assert calls == [], 'a 24h negative cache must stop a browser launch per request'
    assert second['data']['videos'] == []


def test_the_switches_are_all_required_before_a_browser_is_used(monkeypatch, tmp_path):
    monkeypatch.setattr('app.harness.video.resolve', lambda *a: [])
    monkeypatch.setattr(toolbox, '_curate_video_for_lesson',
                        lambda *a: (_ for _ in ()).throw(AssertionError('curated')))
    for switch in ('video_auto_curate', 'media_enabled', 'chromium_search_enabled'):
        result = toolbox.find_video(_ctx(tmp_path, **{switch: False}), 'fractions').to_dict()
        assert result['data']['videos'] == []
        assert not any('On-demand curation' in note for note in result['notes'])


def test_a_curation_exception_becomes_a_note_not_a_500(monkeypatch, tmp_path):
    def boom(*_a, **_k):
        raise RuntimeError('browser exploded')

    monkeypatch.setattr('app.harness.video_search.curate_for_concept', boom)
    ctx = _ctx(tmp_path)
    out = toolbox._curate_video_for_lesson(ctx, ctx.settings, 'fractions')
    assert out['curated'] is False
    assert 'RuntimeError' in out['reason'] and 'browser exploded' in out['reason']
