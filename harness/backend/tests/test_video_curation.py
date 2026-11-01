"""Curating a video: the step that turns "no video" into "video".

A lesson refuses to promise a video that is not curated, which is right and leaves every
concept without one. Curation is what fills that gap, so the thing worth pinning is not
that it finds *a* video but that it refuses the wrong ones: an off-topic title, a
candidate that failed the embeddability probe, or a source the operator has withdrawn.

No network: search and probe are stubbed.
"""

from dataclasses import replace

from app.harness import video, video_search
from test_api import settings  # noqa: F401 - fixture

PERMUTATIONS = {'id': 'algebra_2_permutations_and_combinations',
                'title': 'Permutations and combinations',
                'keywords': ['permutation', 'combination', 'order', 'nPr', 'nCr']}


def _search_returning(monkeypatch, rows):
    monkeypatch.setattr(video_search, 'search_videos',
                        lambda ctx, query, limit=6: {'ok': True, 'query': query,
                                                     'path': 'stub', 'videos': rows})


def _card(video_id, title, verified=True, channel='ch'):
    card = {'video_id': video_id, 'title': title, 'channel': channel, 'verified': verified,
            'watch_url': f'https://www.youtube.com/watch?v={video_id}'}
    if verified:
        card['embed_url'] = f'https://www.youtube-nocookie.com/embed/{video_id}'
    return card


def test_an_on_topic_verified_video_is_curated_and_then_resolves(settings, monkeypatch):
    live = replace(settings, media_enabled=True)
    _search_returning(monkeypatch, [_card('aaaaaaaaaaa', 'Permutations and Combinations Tutorial')])

    out = video_search.curate_for_concept(live, PERMUTATIONS, 'algebra_2')

    assert out['curated'], out
    cards = video.resolve(live, 'algebra_2', PERMUTATIONS['id'], verify_remote=False)
    assert [card['title'] for card in cards] == ['Permutations and Combinations Tutorial']


def test_a_video_about_something_else_is_refused(settings, monkeypatch):
    """Matching nothing in the title is the signal; the model is not consulted."""
    live = replace(settings, media_enabled=True)
    _search_returning(monkeypatch, [_card('bbbbbbbbbbb', 'Quadratic Formula Song')])

    out = video_search.curate_for_concept(live, PERMUTATIONS, 'algebra_2')

    assert not out['curated']
    assert 'about this concept by title' in out['reason']
    assert video.resolve(live, 'algebra_2', PERMUTATIONS['id'], verify_remote=False) == []


def test_a_candidate_that_cannot_be_embedded_is_not_curated(settings, monkeypatch):
    live = replace(settings, media_enabled=True)
    _search_returning(monkeypatch, [_card('ccccccccccc', 'Permutations explained', verified=False)])

    out = video_search.curate_for_concept(live, PERMUTATIONS, 'algebra_2')

    assert not out['curated'], 'an unverified direction is never the permissive one'


def test_a_link_is_accepted_only_when_the_caller_asks_for_one(settings, monkeypatch):
    live = replace(settings, media_enabled=True)
    _search_returning(monkeypatch, [_card('ddddddddddd', 'Combinations explained', verified=False)])

    out = video_search.curate_for_concept(live, PERMUTATIONS, 'algebra_2', accept_links=True)

    assert out['curated']
    assert out['video']['verified'] is False


def test_the_closest_title_wins(settings, monkeypatch):
    live = replace(settings, media_enabled=True)
    _search_returning(monkeypatch, [
        _card('eeeeeeeeeee', 'Permutations explained'),
        _card('fffffffffff', 'Permutations and Combinations: Order Matters'),
    ])

    out = video_search.curate_for_concept(live, PERMUTATIONS, 'algebra_2')

    assert out['video']['video_id'] == 'fffffffffff'
    # permutations + combinations + order: "order" is one of the concept's keywords, and a
    # keyword is exactly what a title uses to say which idea it is about.
    assert out['score'] == 3


def test_curating_twice_writes_one_entry(settings, monkeypatch):
    """A TA may retry a job whose result it never saw."""
    live = replace(settings, media_enabled=True)
    _search_returning(monkeypatch, [_card('aaaaaaaaaaa', 'Permutations and Combinations Tutorial')])

    first = video_search.curate_for_concept(live, PERMUTATIONS, 'algebra_2')
    second = video_search.curate_for_concept(live, PERMUTATIONS, 'algebra_2')

    assert first['curated']
    assert not second['curated']
    assert second['reason'] == 'already curated'
    assert len(video.load_allowlist(live)['algebra_2']) == 1


def test_a_withdrawn_source_cannot_be_curated_back_in(settings):
    live = replace(settings, media_enabled=True)
    video.revoke(live, 'aaaaaaaaaaa')

    out = video.curate(live, 'algebra_2', PERMUTATIONS['id'], video_id='aaaaaaaaaaa',
                       title='Permutations and Combinations Tutorial')

    assert not out['added']
    assert 'revocation' in out['reason']


def test_relevance_ignores_the_words_every_lesson_title_has(settings):  # noqa: F811
    """'Explained' and 'tutorial' describe the format, not the subject."""
    assert video_search.relevance(PERMUTATIONS, 'Permutations Tutorial') == 1
    assert video_search.relevance(PERMUTATIONS, 'A Tutorial Video') == 0


# ------------------------------------------------------------- the neighbouring lesson
#
# A course is full of lessons one word apart. "One-step equations" and "Two-step equations"
# share every content word except the number, so a title that shares words with the concept
# is not enough evidence that it is about the concept.

TWO_STEP = {'id': 'two_step_equations', 'title': 'Two-step equations',
            'keywords': ['solve', 'inverse operations']}


def test_a_video_that_belongs_to_the_neighbouring_lesson_is_refused(settings, monkeypatch):
    live = replace(settings, media_enabled=True)
    _search_returning(monkeypatch, [
        _card('iiiiiiiiiii', 'How to Solve One-Step Equations'),
        _card('jjjjjjjjjjj', 'Solving Two-Step Equations'),
    ])

    out = video_search.curate_for_concept(
        live, TWO_STEP, 'integrated_math_1',
        siblings=['One-step equations', 'Two-step equations', 'Equations with variables on '
                  'both sides'])

    assert out['video']['video_id'] == 'jjjjjjjjjjj'


def test_the_neighbour_test_only_refuses_and_never_chooses(settings, monkeypatch):
    """With no siblings supplied the behaviour is exactly what it was, so a caller that
    does not know the course cannot be broken by the check."""
    live = replace(settings, media_enabled=True)
    _search_returning(monkeypatch, [_card('iiiiiiiiiii', 'How to Solve One-Step Equations')])

    assert video_search.curate_for_concept(live, TWO_STEP, 'integrated_math_1')['curated']
    assert video_search.closer_to_another('How to Solve One-Step Equations', TWO_STEP,
                                          ['One-step equations']) == 'One-step equations'
    assert video_search.closer_to_another('How to Solve One-Step Equations', TWO_STEP) == ''


def test_a_thin_match_from_an_unfamiliar_source_is_not_shipped(settings, monkeypatch):
    """The build raises the bar for sources a curator would not recognise: one shared word
    is not evidence, and the deck's published reason beats a half-matching video."""
    live = replace(settings, media_enabled=True)
    _search_returning(monkeypatch, [
        {'video_id': 'kkkkkkkkkkk', 'title': 'Equations', 'channel': 'bulbvibe',
         'verified': True, 'watch_url': 'https://www.youtube.com/watch?v=kkkkkkkkkkk'},
    ])

    lenient = video_search.curate_for_concept(live, TWO_STEP, 'integrated_math_1')
    assert lenient['curated'], 'the runtime tool keeps its old threshold'

    video.save_allowlist(live, {})
    strict = video_search.curate_for_concept(live, TWO_STEP, 'integrated_math_1',
                                             min_untrusted_score=3)
    assert not strict['curated']


def test_a_trusted_video_that_was_off_topic_does_not_suppress_the_retry(settings, monkeypatch):
    """The retry used to fire only when *no* candidate came from a preferred source. One
    irrelevant Khan video on the first page therefore suppressed it, and the best on-topic
    result left was a 4th-grade clip. What matters is whether a preferred source produced
    something usable, not whether one appeared at all."""
    live = replace(settings, media_enabled=True)
    calls = []

    def fake_search(ctx, query, limit=6):
        calls.append(query)
        if 'khan academy' in query.casefold():
            return {'ok': True, 'query': query, 'path': 'stub',
                    'videos': [_card('ttttttttttt', 'Two-step equations', channel='Khan Academy')]}
        return {'ok': True, 'query': query, 'path': 'stub',
                'videos': [_card('uuuuuuuuuuu', 'Equations made easy', channel='Doodle Math'),
                           _card('vvvvvvvvvvv', 'Quadratic formula song', channel='Khan Academy')]}

    monkeypatch.setattr(video_search, 'search_videos', fake_search)
    out = video_search.curate_for_concept(live, TWO_STEP, 'integrated_math_1',
                                          min_untrusted_score=2)

    assert out['video']['video_id'] == 'ttttttttttt'
    assert out['trusted'] is True
    assert any('khan academy' in query.casefold() for query in calls)


def test_an_equally_on_topic_video_from_a_preferred_source_wins(settings, monkeypatch):
    """Relevance ties are common — two channels both say "permutations and combinations".
    The tie goes to the source a curator would ship, not to whichever the page listed
    first, because an unknown presenter is a worse opening for a lesson."""
    live = replace(settings, media_enabled=True)
    _search_returning(monkeypatch, [
        {'video_id': 'ggggggggggg', 'title': 'Permutations and Combinations', 'channel': 'xXmathXx',
         'verified': True, 'watch_url': 'https://www.youtube.com/watch?v=ggggggggggg'},
        {'video_id': 'hhhhhhhhhhh', 'title': 'Permutations and combinations', 'channel': 'Khan Academy',
         'verified': True, 'watch_url': 'https://www.youtube.com/watch?v=hhhhhhhhhhh'},
    ])

    out = video_search.curate_for_concept(live, PERMUTATIONS, 'algebra_2')

    assert out['video']['video_id'] == 'hhhhhhhhhhh'
    assert out['trusted'] is True
    assert video_search.trusted_channel('Khan Academy') == 1
    assert video_search.trusted_channel('xXmathXx') == 0


# ---------------------------------------------------------------- where the list comes from
#
# Three sources, in this order: the operator's file, the seed the build ships, and the rows
# verified by hand while this module was written. The order matters in one direction only —
# an operator must be able to correct or withdraw without a release — and the shipped seed
# exists so that a bundle with outbound media off still has video at all.

def test_the_shipped_seed_is_read_when_the_operator_has_not_written_one(settings, monkeypatch, tmp_path):
    import json

    seed = tmp_path / 'seed.json'
    seed.write_text(json.dumps({'integrated_math_1': [
        {'concept_id': 'fractions', 'provider': 'youtube', 'video_id': 'seedseedsee',
         'title': 'Equivalent fractions', 'channel': 'Khan Academy'}]}), encoding='utf-8')
    monkeypatch.setattr(video, 'SEED_PACK', seed)

    live = replace(settings, data_dir=str(tmp_path / 'data'), media_cache_dir='')
    table = video.load_allowlist(live)

    assert [row['video_id'] for row in table['integrated_math_1']] == ['seedseedsee']


def test_an_operator_file_replaces_the_seed_without_losing_it(settings, monkeypatch, tmp_path):
    """Curating starts from whatever is loaded, so the operator's copy inherits the seed.
    The alternative — an operator file that silently hides every shipped row — would look
    like a bug the first time a school curated one extra video."""
    import json

    seed = tmp_path / 'seed.json'
    seed.write_text(json.dumps({'integrated_math_1': [
        {'concept_id': 'fractions', 'provider': 'youtube', 'video_id': 'seedseedsee'}]}),
        encoding='utf-8')
    monkeypatch.setattr(video, 'SEED_PACK', seed)
    live = replace(settings, data_dir=str(tmp_path / 'data'), media_cache_dir='')

    video.curate(live, 'integrated_math_1', 'ratios', video_id='operatorvid',
                 title='Ratios', channel='Khan Academy')

    table = video.load_allowlist(live)
    assert {row['video_id'] for row in table['integrated_math_1']} == {'seedseedsee',
                                                                      'operatorvid'}


def test_with_no_seed_and_no_operator_file_the_hand_verified_rows_still_answer(settings):
    live = replace(settings, data_dir=str(settings.data_dir), media_cache_dir='')
    table = video.load_allowlist(live)

    assert table, 'the in-code seed is the last resort, not dead code'
    assert all(row.get('video_id') for rows in table.values() for row in rows)
