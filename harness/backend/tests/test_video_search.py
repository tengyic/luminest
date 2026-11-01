"""Video search: candidates, verification, and the two ways it silently lied.

Both bugs this file pins were invisible from the outside, which is why they survived:
the search returned results and the results were real videos. What went wrong was the
*card*.

1. ``video.verify`` reports ``embeddable`` (see ``app/harness/video.py``). ``search_videos``
   read ``result.get('ok')``, which is never present, so **every** verified video was
   demoted to a plain outbound link and no embed was ever offered.
2. The keyless DuckDuckGo fallback scrapes a results page and can return several results'
   titles concatenated into one row. Preferring the scraped title put that garbage on the
   card even when the oEmbed probe had returned the authoritative one.

No network here: the search and the probe are both stubbed, so the tests assert the
contract rather than the internet.
"""

from dataclasses import replace
from types import SimpleNamespace

from app.harness import video, video_search
from test_api import settings  # noqa: F401 - fixture


def _ctx(settings_obj):
    return SimpleNamespace(settings=settings_obj, role='teacher')


def _hits(*ids):
    return [{'video_id': video_id, 'title': f'scraped {video_id}',
             'channel': 'www.youtube.com', 'source': 'ddg_fallback'} for video_id in ids]


def test_a_verified_candidate_becomes_an_embed_card(settings, monkeypatch):
    monkeypatch.setattr(video_search, '_keyless_search',
                        lambda *a, **k: (_hits('aaaaaaaaaaa', 'bbbbbbbbbbb'), 'ddg_fallback'))
    monkeypatch.setattr(video, 'verify', lambda s, vid: {
        'video_id': vid, 'embeddable': True, 'method': 'oembed_iframe_present',
        'title': 'Permutations and Combinations Tutorial', 'channel': 'The Organic Chemistry Tutor'})

    out = video_search.search_videos(_ctx(replace(settings, media_enabled=True)), 'permutations', limit=2)

    assert out['ok']
    assert all(card['verified'] for card in out['videos'])
    assert out['videos'][0]['embed_url'] == 'https://www.youtube-nocookie.com/embed/aaaaaaaaaaa'
    assert out['videos'][0]['licence_class'] == 'embed_only'


def test_an_unverifiable_candidate_keeps_its_link_and_loses_its_embed(settings, monkeypatch):
    monkeypatch.setattr(video_search, '_keyless_search', lambda *a, **k: (_hits('ccccccccccc'), 'ddg_fallback'))
    monkeypatch.setattr(video, 'verify', lambda s, vid: {
        'video_id': vid, 'embeddable': False, 'method': 'oembed_iframe_absent',
        'title': '', 'channel': ''})

    out = video_search.search_videos(_ctx(replace(settings, media_enabled=True)), 'permutations', limit=1)

    card = out['videos'][0]
    assert out['ok'], 'a plain link is still a result'
    assert not card['verified']
    assert 'embed_url' not in card
    assert card['watch_url'] == 'https://www.youtube.com/watch?v=ccccccccccc'
    assert card['verification'] == 'oembed_iframe_absent'


def test_the_probes_title_wins_over_the_scraped_one(settings, monkeypatch):
    """The fallback's row title can be several results concatenated together."""
    concatenated = ('Permutations and Combinations Tutorial - YouTubePermutations and Combinations '
                    '- YouTubeIntroduction to Permutations and Combinations - YouTube')
    monkeypatch.setattr(video_search, '_keyless_search', lambda *a, **k: (
        [{'video_id': 'ddddddddddd', 'title': concatenated, 'channel': 'www.youtube.com',
          'source': 'ddg_fallback'}], 'ddg_fallback'))
    monkeypatch.setattr(video, 'verify', lambda s, vid: {
        'video_id': vid, 'embeddable': True, 'method': 'oembed_iframe_present',
        'title': 'Permutations and Combinations Tutorial', 'channel': 'The Organic Chemistry Tutor'})

    card = video_search.search_videos(_ctx(replace(settings, media_enabled=True)), 'permutations',
                                      limit=1)['videos'][0]

    assert card['title'] == 'Permutations and Combinations Tutorial'
    assert card['channel'] == 'The Organic Chemistry Tutor'


def test_the_scraped_title_survives_when_the_probe_has_none(settings, monkeypatch):
    """A video that cannot be embedded is still described by whatever the search knew."""
    monkeypatch.setattr(video_search, '_keyless_search', lambda *a, **k: (_hits('eeeeeeeeeee'), 'ddg_fallback'))
    monkeypatch.setattr(video, 'verify', lambda s, vid: {
        'video_id': vid, 'embeddable': False, 'method': 'unverifiable:HTTPError',
        'title': '', 'channel': ''})

    card = video_search.search_videos(_ctx(replace(settings, media_enabled=True)), 'x', limit=1)['videos'][0]
    assert card['title'] == 'scraped eeeeeeeeeee'


def test_media_off_refuses_before_searching(settings, monkeypatch):
    """The gate is asserted by its refusal, and it must not make a network call to decide."""
    called = []
    monkeypatch.setattr(video_search, '_keyless_search', lambda *a, **k: called.append(1) or ([], ''))

    out = video_search.search_videos(_ctx(replace(settings, media_enabled=False)), 'permutations')

    assert not out['ok']
    assert 'HARNESS_MEDIA_ENABLED' in out['refused']
    assert not called


# ------------------------------------------------------------------- the keyless chain
#
# Discovery used to be one SERP scrape, and that scrape is the fragile part: mojeek
# answers 403 to a non-browser client and DuckDuckGo's HTML endpoint is unreachable from
# some networks, so a machine that can reach YouTube perfectly well could not find a
# single video on it. The provider's own results page carries the same first page of
# results as ``ytInitialData``, with better metadata than a SERP gives.

_PAGE = """<!DOCTYPE html><html><head><title>slope - YouTube</title></head><body>
<script nonce="abc">var ytInitialData = %s;</script>
<script>var ytInitialPlayerResponse = null;</script>
</body></html>"""


def _renderer(video_id, title, channel, length, **extra):
    row = {'videoId': video_id,
           'title': {'runs': [{'text': title}]},
           'ownerText': {'runs': [{'text': channel}]}}
    if length is not None:
        row['lengthText'] = {'simpleText': length}
    row.update(extra)
    return row


def _page(*renderers):
    import json
    data = {'contents': {'twoColumnSearchResultsRenderer': {'primaryContents': {
        'sectionListRenderer': {'contents': [{'itemSectionRenderer': {'contents': [
            {'videoRenderer': row} for row in renderers]}}]}}}}}
    return _PAGE % json.dumps(data)


def test_the_results_page_yields_its_rows():
    html = _page(_renderer('aaaaaaaaaaa', 'Slope-intercept form | Algebra I', 'Khan Academy', '8:59'))

    hits = video_search._page_hits(html, limit=6)

    assert hits == [{'video_id': 'aaaaaaaaaaa', 'title': 'Slope-intercept form | Algebra I',
                     'channel': 'Khan Academy', 'seconds': 539, 'source': 'youtube_page'}]


def test_a_lecture_a_short_and_a_live_row_are_not_candidates():
    """A lesson block is minutes. A three-hour lecture and a clip are both the wrong shape,
    and a live row carries no duration at all, which is why zero fails the same test."""
    html = _page(_renderer('bbbbbbbbbbb', 'Linear algebra full course', 'Somewhere', '3:14:07'),
                 _renderer('ccccccccccc', 'this trick #shorts', 'Clips', '0:42'),
                 _renderer('ddddddddddd', 'Live now', 'News', None),
                 _renderer('eeeeeeeeeee', 'Intro to slope', 'Khan Academy', '6:55'))

    assert [hit['video_id'] for hit in video_search._page_hits(html, limit=6)] == ['eeeeeeeeeee']


def test_a_page_without_the_state_blob_is_empty_rather_than_an_error():
    assert video_search._page_hits('<html><body>consent</body></html>', limit=6) == []


def test_the_chain_prefers_the_provider_and_falls_back_to_the_serp(settings, monkeypatch):
    def broken(*_a, **_k):
        raise RuntimeError('403')

    monkeypatch.setattr(video_search, '_ddg_search',
                        lambda *a, **k: (_hits('fffffffffff'), 'ddg_fallback'))
    monkeypatch.setattr(video_search, '_youtube_page_search', broken)
    hits, path = video_search._keyless_search(settings, 'slope', 2)
    assert path == 'ddg_fallback' and hits

    monkeypatch.setattr(video_search, '_youtube_page_search',
                        lambda *a, **k: ([{'video_id': 'aaaaaaaaaaa'}], 'youtube_page'))
    hits, path = video_search._keyless_search(settings, 'slope', 2)
    assert path == 'youtube_page'


def test_both_keyless_paths_failing_is_reported_not_swallowed(settings, monkeypatch):
    def broken(*_a, **_k):
        raise RuntimeError('403')

    monkeypatch.setattr(video_search, '_youtube_page_search', broken)
    monkeypatch.setattr(video_search, '_ddg_search', broken)

    out = video_search.search_videos(_ctx(replace(settings, media_enabled=True)), 'slope')

    assert not out['ok']
    assert 'youtube_page' in out['error'] and 'ddg_fallback' in out['error']


def test_inflection_does_not_hide_the_right_video():
    """"Linear functions and intercepts" vs "Slope-intercept form": the plural was the
    whole difference, and exact matching scored it zero."""
    concept = {'id': 'linear_functions', 'title': 'Linear functions and intercepts',
               'keywords': ['slope', 'intercept', 'graph']}

    assert video_search.relevance(concept, 'Slope-intercept form | Algebra I') == 2
    assert video_search.relevance(concept, 'Quadratic formula song') == 0
