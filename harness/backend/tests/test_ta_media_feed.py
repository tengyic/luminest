"""What the TA feed is allowed to show as an image.

The TA produces images three different ways, and each way arrives in a different shape:
``image_search`` embeds URLs it never downloaded, ``find_image`` downloads one cleared
copy into this instance's cache, and ``image_generate`` writes its own pixels. The feed
is presentation over the finished event trace, so these tests pin exactly that: which
shape becomes a card, what credit line it carries, and that a candidate a teacher cannot
actually open never becomes a card at all.

``main.media_from_events`` is deliberately module-level rather than a closure inside
``create_app`` so this can be pinned without standing up the whole API.
"""

from pathlib import Path
from types import SimpleNamespace

from app.main import media_from_events, ta_cards_from_events


def tool_result(data: dict, ok: bool = True, name: str = 'find_image') -> dict:
    return {'type': 'tool_result', 'ok': ok, 'tool': name,
            'data': {'tool': name, 'ok': ok, 'data': data}}


def settings_for(tmp_path) -> SimpleNamespace:
    return SimpleNamespace(data_dir=str(tmp_path))


# ---------------------------------------------------------------- search results

def test_a_search_result_keeps_its_url_and_licence(tmp_path):
    events = [tool_result({'images': [
        {'thumb_url': 'https://example.test/hippocampus.jpg', 'title': 'Hippocampus',
         'licence': 'CC BY 4.0', 'landing_page_url': 'https://example.test/a',
         'sha256': 'a' * 64}]}, name='image_search')]

    media = media_from_events(events, settings_for(tmp_path))

    assert len(media) == 1
    assert media[0]['thumb_url'] == 'https://example.test/hippocampus.jpg'
    assert media[0]['licence'] == 'CC BY 4.0'
    assert media[0]['sha'] == 'a' * 64
    # Nothing was downloaded, so there is no local copy to claim.
    assert media[0]['local_path'] == ''


def test_a_search_result_without_a_url_is_not_a_card(tmp_path):
    """A title with no URL and no file is a card the teacher cannot open."""
    events = [tool_result({'images': [{'title': 'Ghost image', 'licence': 'CC BY 4.0'}]},
                          name='image_search')]
    assert media_from_events(events, settings_for(tmp_path)) == []


# ---------------------------------------------------------------- downloaded assets

def test_a_downloaded_asset_prefers_its_local_copy(tmp_path):
    events = [tool_result({'asset': {
        'title': 'Hippocampus (mouse)', 'cache_path': 'media/images/abc.png',
        'file_url': 'https://example.test/original.png', 'licence_code': 'cc-by-sa-4.0',
        'landing_page_url': 'https://example.test/landing', 'sha256': 'b' * 64}})]

    media = media_from_events(events, settings_for(tmp_path))

    assert len(media) == 1
    assert media[0]['local_path'] == str(tmp_path / 'media/images/abc.png')
    assert media[0]['licence'] == 'cc-by-sa-4.0'
    assert media[0]['source_page'] == 'https://example.test/landing'


# ---------------------------------------------------------------- generated images

def test_a_generated_illustration_says_so_instead_of_borrowing_a_licence(tmp_path):
    """Generated pixels have no third-party rights; a blank credit line reads as a bug."""
    events = [tool_result({'path': 'media/generated/abc.png', 'sha256': 'c' * 64,
                           'prompt': 'a hand-drawn diagram of hindsight bias',
                           'provider': 'pollinations', 'mime': 'image/png'},
                          name='image_generate')]

    media = media_from_events(events, settings_for(tmp_path))

    assert len(media) == 1
    assert media[0]['local_path'] == str(tmp_path / 'media/generated/abc.png')
    assert 'Generated' in media[0]['licence']
    assert media[0]['licence'].strip()  # never empty
    assert media[0]['title'].startswith('a hand-drawn diagram')
    assert media[0]['sha'] == 'c' * 64


def test_a_generated_path_without_a_provider_is_not_claimed(tmp_path):
    """``path`` alone is also what other tools return; only image_generate may claim it."""
    events = [tool_result({'path': 'media/generated/abc.png', 'sha256': 'c' * 64},
                          name='write_simulation')]
    assert media_from_events(events, settings_for(tmp_path)) == []


# ---------------------------------------------------------------- the trace itself

def test_a_failed_tool_result_never_becomes_a_card(tmp_path):
    events = [tool_result({'images': [{'thumb_url': 'https://example.test/x.jpg',
                                       'title': 'X'}]}, ok=False, name='image_search')]
    assert media_from_events(events, settings_for(tmp_path)) == []


def test_the_same_image_twice_is_one_card(tmp_path):
    candidate = {'thumb_url': 'https://example.test/x.jpg', 'title': 'X',
                 'licence': 'CC0'}
    events = [tool_result({'images': [candidate]}, name='image_search'),
              tool_result({'images': [dict(candidate)]}, name='image_search')]
    assert len(media_from_events(events, settings_for(tmp_path))) == 1


def test_the_feed_is_capped_at_eight_images(tmp_path):
    """A turn that searches twice must not turn the panel into an image dump."""
    events = [tool_result({'images': [
        {'thumb_url': f'https://example.test/{i}.jpg', 'title': f'Image {i}'}
        for i in range(12)]}, name='image_search')]
    assert len(media_from_events(events, settings_for(tmp_path))) == 8


def test_the_three_shapes_together_keep_their_call_order(tmp_path):
    events = [
        tool_result({'images': [{'thumb_url': 'https://example.test/1.jpg',
                                 'title': 'Searched'}]}, name='image_search'),
        tool_result({'asset': {'title': 'Downloaded', 'cache_path': 'media/images/d.png',
                               'sha256': 'd' * 64}}),
        tool_result({'path': 'media/generated/g.png', 'sha256': 'e' * 64,
                     'prompt': 'Generated', 'provider': 'pollinations'},
                    name='image_generate'),
    ]

    media = media_from_events(events, settings_for(tmp_path))

    assert [m['title'] for m in media] == ['Searched', 'Downloaded', 'Generated']
    assert all(Path(m['local_path']).is_absolute() or m['thumb_url'] for m in media)


# ---------------------------------------------------------------- the manifest row

PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 64


def test_generated_bytes_are_indexed_with_a_generated_licence(tmp_path):
    """The bytes route serves the manifest, so a generated image must be in it — with a
    credit line that says what it is rather than an empty one that reads as an oversight."""
    import hashlib

    from app.harness import media

    settings = settings_for(tmp_path)
    sha = hashlib.sha256(PNG).hexdigest()

    stored = media.store_bytes(settings, PNG, sha=sha, source='generated',
                               title='hindsight bias diagram',
                               licence_class='generated', licence_code='generated',
                               creator='this instance',
                               attribution_text='Generated by this instance; no rights.')

    assert stored == 1
    row = media._load_manifest(settings)[sha]
    assert row['source'] == 'generated'
    assert row['licence_code'] == 'generated'
    assert row['creator'] == 'this instance'
    assert row['attribution_text']
    # The bytes themselves are on disk under their content hash, which is what the
    # ordinary media route reads.
    assert (media.cache_root(settings) / f'{sha}.png').read_bytes() == PNG
    # Content addressing still dedupes: re-indexing the same pixels is a no-op.
    assert media.store_bytes(settings, PNG, sha=sha, source='generated') == 0



# ---------------------------------------------------------------- cards must agree

def test_a_generated_image_gets_a_card_not_just_a_media_row(tmp_path):
    """The panel renders cards. A generated diagram that only exists in `media` is an
    asset the teacher can never see — that was the bug this pins."""
    events = [tool_result({'path': 'media/generated/g.png', 'sha256': 'e' * 64,
                           'prompt': 'a hand-drawn chart of the overconfidence effect',
                           'provider': 'pollinations'}, name='image_generate')]

    cards = ta_cards_from_events(events)
    media = media_from_events(events, settings_for(tmp_path))

    assert len(cards) == 1
    assert cards[0]['kind'] == 'image'
    assert cards[0]['sha'] == 'e' * 64
    assert cards[0]['title'].startswith('a hand-drawn chart')
    assert cards[0]['source'] == ''          # nothing to link to; it is not a download
    assert 'Generated' in cards[0]['licence']
    assert cards[0]['sha'] == media[0]['sha']


def test_a_downloaded_image_card_links_its_source_page(tmp_path):
    events = [tool_result({'asset': {'title': 'Hippocampus', 'sha256': 'f' * 64,
                                     'licence_code': 'cc-by-4.0',
                                     'landing_page_url': 'https://example.test/l',
                                     'file_url': 'https://example.test/f.png'}})]

    card = ta_cards_from_events(events)[0]

    assert card['kind'] == 'image'
    assert card['sha'] == 'f' * 64
    assert card['licence'] == 'cc-by-4.0'
    assert card['source'] == 'https://example.test/l'


def test_a_search_card_carries_the_sha_when_the_instance_has_the_bytes(tmp_path):
    events = [tool_result({'images': [{'thumb_url': 'https://example.test/t.jpg',
                                       'title': 'T', 'licence': 'CC0',
                                       'sha256': 'g' * 64}]}, name='image_search')]

    card = ta_cards_from_events(events)[0]

    assert card['kind'] == 'image'
    assert card['url'] == 'https://example.test/t.jpg'
    assert card['sha'] == 'g' * 64


def test_a_deck_is_an_artifact_card():
    events = [tool_result({'artifact_id': 'deck-abc', 'title': 'Overconfidence'},
                          name='generate_slides')]
    card = ta_cards_from_events(events)[0]
    assert card['kind'] == 'artifact'
    assert card['artifact_id'] == 'deck-abc'
    assert card['title'] == 'Overconfidence'


def test_the_card_list_ignores_failed_turns():
    assert ta_cards_from_events([
        tool_result({'path': 'media/generated/g.png', 'sha256': 'e' * 64,
                     'provider': 'pollinations'}, ok=False, name='image_generate')]) == []


def test_a_deck_revised_in_the_same_turn_is_one_card():
    """Draft, then a revision after the lint pass: two tool results, one artifact."""
    events = [
        tool_result({'artifact_id': 'deck-abc', 'title': 'Overconfidence'},
                    name='generate_slides'),
        tool_result({'artifact_id': 'deck-abc', 'title': 'Overconfidence'},
                    name='generate_slides'),
    ]
    cards = ta_cards_from_events(events)
    assert len(cards) == 1
    assert cards[0]['artifact_id'] == 'deck-abc'


def test_two_different_decks_stay_two_cards():
    events = [tool_result({'artifact_id': 'deck-a', 'title': 'A'}, name='generate_slides'),
              tool_result({'artifact_id': 'deck-b', 'title': 'B'}, name='generate_slides')]
    assert [c['artifact_id'] for c in ta_cards_from_events(events)] == ['deck-a', 'deck-b']


def test_the_same_picture_twice_is_one_card():
    events = [tool_result({'path': 'media/generated/g.png', 'sha256': 'e' * 64,
                           'prompt': 'chart', 'provider': 'pollinations'},
                          name='image_generate'),
              tool_result({'path': 'media/generated/g.png', 'sha256': 'e' * 64,
                           'prompt': 'chart, revised', 'provider': 'pollinations'},
                          name='image_generate')]
    cards = ta_cards_from_events(events)
    assert len(cards) == 1
    assert cards[0]['title'] == 'chart, revised'   # the newest wording wins
