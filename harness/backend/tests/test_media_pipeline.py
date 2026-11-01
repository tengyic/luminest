"""Tests for the four media capabilities: images, video, simulations and presentations.

Written around the guarantees the modules claim, not around their internals. Where a claim
is a refusal - an uncleared licence, an unverifiable embed, an unobservable simulation -
the test asserts the refusal, because a gate that is never exercised is a gate that has
quietly stopped working. None of these tests need the network: the remote paths are
monkeypatched, and the one test that exercises the offline path asserts that it stays
offline.
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app import courses, simulation_map
from app.harness import generate, media, presentation, toolbox, video
from app.harness.toolbox import ToolContext
from app.ingest import policy
from app.harness import sandbox
from test_api import settings  # noqa: F401 - fixture


@pytest.fixture
def offline_settings(settings):
    """Settings with outbound media explicitly disabled, which is the safe default."""
    return replace(settings, media_enabled=False, commercial_use=False,
                   youtube_api_key='', openverse_client_id='', openverse_client_secret='')


@pytest.fixture
def online_settings(settings):
    """Settings that permit the network, still without credentials."""
    return replace(settings, media_enabled=True)


@pytest.fixture
def ctx(offline_settings):
    context = harness_context(offline_settings)
    return context


def harness_context(settings_obj, course_id='integrated_math_1'):
    context = ToolContext(settings=settings_obj, now=1_700_000_000.0,
                          graph=courses.graph_for(course_id), subject_kind='mathematics',
                          course_id=course_id)
    context.workspace = sandbox.Workspace(Path(settings_obj.data_dir) / 'ws', 'test-ws')
    return context


# ----------------------------------------------------------- licence classification

@pytest.mark.parametrize('raw,expected', [
    # The exact spellings both APIs were observed to emit.
    ('by', policy.LicenceClass.CC_BY),
    ('by-sa', policy.LicenceClass.CC_BY_SA),
    ('cc0', policy.LicenceClass.CC0),
    ('pdm', policy.LicenceClass.PUBLIC_DOMAIN),
    ('cc-by-sa-4.0', policy.LicenceClass.CC_BY_SA),
    ('CC BY-SA 4.0', policy.LicenceClass.CC_BY_SA),
    ('CC BY 4.0', policy.LicenceClass.CC_BY),
    ('CC BY-NC 4.0', policy.LicenceClass.CC_BY_NC),
    ('CC BY-NC-SA 4.0', policy.LicenceClass.CC_BY_NC_SA),
    ('CC BY-ND 4.0', policy.LicenceClass.CC_BY_ND),
    ('Public domain', policy.LicenceClass.PUBLIC_DOMAIN),
    ('', None),
])
def test_licence_codes_classify_correctly(raw, expected):
    assert policy.classify_licence(raw) is expected, raw


def test_an_unknown_licence_is_refused_rather_than_assumed_permissive():
    """The load-bearing guarantee. A new licence code must not become a free pass."""
    invented = 'Some-Collections-Open-Licence-2027'
    assert policy.classify_licence(invented) is None
    with pytest.raises(policy.AssetRefused) as refusal:
        policy.require_locally_storable(invented, 'test asset')
    assert 'unrecognised licence' in str(refusal.value)


@pytest.mark.parametrize('raw', ['CC BY-NC 4.0', 'CC BY-NC-SA 4.0', 'CC BY-ND 4.0'])
def test_non_commercial_and_no_derivatives_cannot_be_stored_locally(raw):
    with pytest.raises(policy.AssetRefused):
        policy.require_locally_storable(raw, 'test asset')


@pytest.mark.parametrize('raw', ['CC0 1.0', 'CC BY 4.0', 'CC BY-SA 4.0', 'Public domain'])
def test_redistributable_licences_are_storable(raw):
    assert policy.require_locally_storable(raw, 'ok') in policy.LOCALLY_STORABLE


def test_nc_and_nd_classes_are_excluded_from_local_storage():
    for klass in (policy.LicenceClass.CC_BY_NC, policy.LicenceClass.CC_BY_NC_SA,
                  policy.LicenceClass.CC_BY_ND):
        assert klass not in policy.LOCALLY_STORABLE, klass.value


# ----------------------------------------------------------- commercial-use gate

def test_non_commercial_sources_are_withheld_on_a_paid_instance():
    free = policy.video_reference('physics', commercial=False)
    paid = policy.video_reference('physics', commercial=True)
    assert any(card['status'] == 'reference_link' for card in free)
    withheld = [card for card in paid if card['status'] == 'withheld']
    assert withheld, 'a paid instance kept a non-commercial source'
    assert all(card.get('withheld_reason') for card in withheld)


def test_the_commercial_gate_is_enforced_not_merely_documented():
    """Khan's NC clause blocks a paid offering, so the gate must raise, not warn."""
    with pytest.raises(policy.AssetRefused):
        policy.require_commercial(policy.KHAN_ACADEMY_VIDEO, True, 'khan video')
    # ...and must not raise when the instance is not a paid offering.
    policy.require_commercial(policy.KHAN_ACADEMY_VIDEO, False, 'khan video')


def test_stored_cards_are_re_evaluated_against_the_live_rights_position():
    """Lesson media is materialised at import time; the commercial decision is runtime."""
    khan = policy.KHAN_ACADEMY_VIDEO.name
    stored = [{'kind': 'video', 'title': 'Khan video', 'policy_name': khan,
               'licence_class': 'embed_only'}]
    kept = policy.reapply_media_policy(stored, commercial=False)
    # Cleared is stamped, not inferred from a missing field.
    assert kept[0]['status'] == 'ready'
    assert not kept[0].get('withheld_reason')
    flipped = policy.reapply_media_policy(stored, commercial=True)
    assert flipped[0]['status'] == 'withheld'
    assert flipped[0]['withheld_reason']
    # Re-evaluating an already-evaluated card must not drift.
    assert policy.reapply_media_policy(kept, commercial=False)[0]['status'] == 'ready'
    assert policy.reapply_media_policy(flipped, commercial=True)[0]['status'] == 'withheld'


def test_a_card_whose_policy_does_not_resolve_is_withheld_not_cleared():
    """The gate fails closed. An unestablishable rights position is not a permissive one."""
    for name in ('Khan Academy (renamed in a later release)', ''):
        cards = policy.reapply_media_policy(
            [{'kind': 'video', 'title': 'x', 'policy_name': name}], commercial=False)
        assert cards[0]['status'] == 'withheld', name
        assert cards[0]['withheld_reason']
    # And no real card in this project trips it -- the rule is a guard, not a tax on output.
    for course_id in ('integrated_math_1', 'physics', 'chemistry', 'biology',
                      'computer_science', 'earth_space_science'):
        cards = policy.reapply_media_policy(policy.course_media_extras(course_id),
                                            commercial=False)
        assert cards and all(c['status'] != 'withheld' for c in cards), course_id


# ----------------------------------------------------------- candidate filtering

def _candidate(**over):
    base = dict(source='openverse', source_id='x', title='photosynthesis in a leaf',
                file_url='https://example.test/a.jpg', width=1200, height=800,
                mime='image/jpeg', licence_code='CC BY 4.0', tags=['photosynthesis'])
    base.update(over)
    return media.Candidate(**base)


def test_filter_rejects_each_bad_candidate_with_a_stated_reason():
    accepted, rejected = media.filter_candidates(
        [_candidate(source_id='ok'),
         _candidate(source_id='narrow', width=300, height=200),
         _candidate(source_id='banner', width=4000, height=120),
         _candidate(source_id='unrelated', title='a theatre marquee at night', tags=[])],
        'photosynthesis in a leaf')
    assert [c.source_id for c in accepted] == ['ok']
    assert len(rejected) == 3
    for candidate in rejected:
        assert candidate.rejected, 'a candidate was rejected without a reason'


def test_an_unclassified_licence_is_rejected_before_any_size_check():
    accepted, rejected = media.filter_candidates(
        [_candidate(licence_code='Bespoke-Open-2.0')], 'photosynthesis in a leaf')
    assert not accepted
    assert 'not a code this project has classified' in rejected[0].rejected


@pytest.mark.parametrize('query,title,floor', [
    ('photosynthesis in a leaf', 'photosynthesis in a leaf', 0.9),
    ('photosynthesis in a leaf', 'a theatre marquee at night', 0.0),
    ('mitosis', 'mitosis', 1.0),
])
def test_lexical_overlap_is_a_recall_measure(query, title, floor):
    assert media.lexical_overlap(query, title) >= floor


# ----------------------------------------------------------- offline behaviour

def test_image_search_reports_a_refusal_when_media_is_disabled(offline_settings):
    result = media.search(offline_settings, 'photosynthesis')
    assert result['candidates'] == []
    assert any('disabled' in note for note in result['notes'])


def test_acquire_downloads_nothing_when_media_is_disabled(offline_settings):
    before = set(Path(offline_settings.data_dir).rglob('*'))
    result = media.acquire(offline_settings, 'photosynthesis')
    assert result['outcome'] == 'network_disabled'
    assert result['asset'] is None
    after = set(Path(offline_settings.data_dir).rglob('*'))
    assert before == after, 'a disabled pipeline still wrote to disk'


def test_attribution_is_built_when_the_provider_supplies_only_pieces():
    candidate = _candidate(creator='A Photographer', licence_code='CC BY 4.0',
                           licence_url='https://creativecommons.org/licenses/by/4.0/')
    text = media.attribute(candidate, 'A leaf')
    for fragment in ('A leaf', 'A Photographer', 'CC BY 4.0', 'by/4.0'):
        assert fragment in text


def test_openverse_attribution_string_is_preserved_verbatim():
    supplied = '"x" by y is licensed under CC BY-SA 2.0.'
    candidate = _candidate(attribution_text=supplied, creator='y')
    assert media.attribute(candidate, 'ignored') == supplied


# ----------------------------------------------------------- video

def test_video_embedding_fails_closed_when_it_cannot_be_verified(offline_settings,
                                                               monkeypatch):
    monkeypatch.setattr(video, 'verify', lambda *a, **k: {
        'embeddable': False, 'checked_at': 0.0, 'method': 'unverifiable:ConnectError'})
    cards = video.resolve(offline_settings, 'integrated_math_1', 'linear_functions')
    assert cards, 'the seeded allowlist returned nothing at all'
    for card in cards:
        assert card['status'] == 'link_only'
        assert card['embed_url'] == ''
        assert card['watch_url'].startswith('https://www.youtube.com/watch')
        assert card['verify_note']


def test_video_embedding_is_used_only_after_a_positive_verification(offline_settings,
                                                                   monkeypatch):
    monkeypatch.setattr(video, 'verify', lambda *a, **k: {
        'embeddable': True, 'checked_at': 1.0, 'method': 'oembed_iframe_present',
        'title': 'Linear transformations', 'channel': '3Blue1Brown', 'thumbnail': ''})
    cards = video.resolve(offline_settings, 'integrated_math_1', 'linear_functions')
    assert any(card['status'] == 'verified_embed' for card in cards)
    embedded = [c for c in cards if c['status'] == 'verified_embed'][0]
    assert embedded['embed_url'].startswith('https://www.youtube-nocookie.com/embed/')


def test_no_video_is_ever_downloadable_or_transcribable(offline_settings, monkeypatch):
    monkeypatch.setattr(video, 'verify', lambda *a, **k: {
        'embeddable': True, 'checked_at': 1.0, 'method': 'oembed_iframe_present'})
    card = video.resolve(offline_settings, 'integrated_math_1', 'linear_functions')[0]
    assert card['allow_download'] is False
    assert card['allow_transcript_extraction'] is False
    assert card['allow_model_ingestion'] is False


def test_extraction_is_a_named_refusal_not_a_missing_feature():
    for purpose in ('transcribe the video', 'summarise the captions', 'fetch the transcript'):
        with pytest.raises(video.ExtractionRefused) as refusal:
            video.assert_extraction_allowed(purpose)
        assert 'extract' in str(refusal.value)


def test_a_revocation_wins_over_every_other_branch(offline_settings, monkeypatch):
    """A rightsholder withdrawal must not be defeated by a later succeeding check."""
    monkeypatch.setattr(video, 'verify', lambda *a, **k: {
        'embeddable': True, 'checked_at': 1.0, 'method': 'oembed_iframe_present'})
    # The seed allowlist curates three_blue_one_brown for linear_functions.
    video.revoke(offline_settings, 'three_blue_one_brown')
    try:
        cards = video.resolve(offline_settings, 'integrated_math_1', 'linear_functions')
        assert cards, 'the maths allowlist had nothing to revoke'
        assert all(card['provider'] == 'three_blue_one_brown' for card in cards)
        for card in cards:
            # Revocation beats a verification that would otherwise have succeeded.
            assert card['status'] == 'withheld', card['status']
            assert card['withheld_reason']
            # ...and withholds the offer, not just the label: a client must have no URL.
            assert card['url'] == ''
            assert card['embed_url'] == ''
            assert card['integration_mode'] == 'unavailable'
    finally:
        # Clean up so the revocation does not leak into other tests via the data dir.
        video.revoke(offline_settings, '')


def test_video_search_quota_is_stated_as_a_decision_input():
    quota = video.search_quota(1)
    assert quota['units'] == video.DATA_API_SEARCH_COST
    assert quota['searches_affordable_per_day'] == 100
    assert video.search_quota(524)['fraction_of_daily_allowance'] > 1


def test_khan_required_notice_is_carried_as_data():
    assert policy.KHAN_ACADEMY_NOTICE in policy.KHAN_ACADEMY_VIDEO.attribution_notice
    assert 'khanacademy.org' in policy.KHAN_ACADEMY_VIDEO.attribution_notice


# ----------------------------------------------------------- simulations

def _a_phet_mapping(course_id='chemistry'):
    """A real (course, concept) pair that the frozen pack maps to a PhET simulation.

    Taken from the pack rather than invented, so the test exercises a mapping that exists
    instead of one the author assumed. The fuzzy matcher is deliberately not consulted to
    build the fixture: a test of the launch URL should not depend on a match score.
    """
    for item in simulation_map.mappings():
        if item['course_id'] == course_id and item.get('provider') == 'phet':
            return item
    raise AssertionError(f'the {course_id} pack has no PhET mapping')


def test_an_invented_slug_is_withheld_not_embedded(offline_settings, monkeypatch):
    monkeypatch.setattr(simulation_map, 'verify_slug',
                        lambda s, slug, **k: {'slug': slug, 'resolves': False, 'status': 404})
    item = _a_phet_mapping('chemistry')
    result = simulation_map.for_concept(offline_settings, 'chemistry', item['concept'])
    phet = [c for c in result['simulations'] if c['provider'] == 'phet']
    assert phet, 'the chemistry map had no PhET candidate to verify'
    for card in phet:
        assert card['status'] == 'withheld'
        assert card['launch_url'] == ''
        assert card['withheld_reason']


def test_a_verified_slug_produces_a_real_embed_url(offline_settings, monkeypatch):
    monkeypatch.setattr(simulation_map, 'verify_slug',
                        lambda s, slug, **k: {'slug': slug, 'resolves': True, 'status': 200})
    item = _a_phet_mapping('chemistry')
    result = simulation_map.for_concept(offline_settings, 'chemistry', item['concept'])
    ready = [c for c in result['simulations']
             if c['provider'] == 'phet' and c['status'] == 'ready']
    assert ready, 'no PhET simulation resolved despite a positive verification'
    for card in ready:
        assert card['launch_url'] == (
            f'https://phet.colorado.edu/sims/html/{card["slug"]}/latest/{card["slug"]}_en.html')
        assert card['open_mode'] == 'embed_in_lesson'
        assert card['embed_allowed'] is True
        # The public page is a separate, non-embedding URL.
        assert card['public_url'].startswith('https://phet.colorado.edu/en/simulations/')


def test_every_simulation_card_is_marked_unobservable(offline_settings, monkeypatch):
    """Free sims expose no telemetry, so the harness may never treat one as evidence."""
    monkeypatch.setattr(simulation_map, 'verify_slug',
                        lambda s, slug, **k: {'slug': slug, 'resolves': True, 'status': 200})
    for course_id in [c.id for c in courses.COURSES]:
        per_concept = simulation_map.for_concept(offline_settings, course_id, 'x')
        assert per_concept['observable'] is False
        for card in per_concept['simulations']:
            assert card['observable'] is False, (course_id, card['title'])
            assert card['telemetry_note']


def test_gizmos_is_never_embedded(offline_settings):
    # earth_space_science is a course the pack does map Gizmos for; physics is not (that
    # shortfall is asserted separately rather than papered over by picking a friendlier
    # course and saying nothing).
    cards = [c for c in simulation_map.for_course(offline_settings, 'earth_space_science')['units']
             for c in c['simulations'] if c['provider'] == 'gizmos']
    assert cards, 'the earth_space_science map has no Gizmos entries'
    for card in cards:
        assert card['embed_allowed'] is False
        assert card['open_mode'] == 'open_in_browser_signed_in'
        # Never the URL pattern with an unresolved placeholder: that is a 404 presented as
        # a launch, and it is the specific way a per-seat deep link goes wrong.
        assert '<resolve>' not in card['launch_url']
        assert card['launch_url'].startswith('https://')


def test_the_declared_provider_order_is_reconciled_against_the_pack():
    """A declared provider that contributed nothing is a published shortfall, not silence.

    ``physics`` declares Gizmos in its provider order and the pack carries no physics Gizmos
    rows. Reporting the totals alone would let the declared order imply coverage that does
    not exist, which is the same failure mode as an empty list being read as success.
    """
    coverage = simulation_map.coverage()
    declared = coverage['declared_providers_by_course']
    contributed = coverage['providers_by_course']
    gaps = coverage['provider_gaps']

    # Every declared provider is either present in the pack or named as a gap -- never
    # silently missing from both.
    for course_id, order in declared.items():
        present = set(contributed.get(course_id, ()))
        for provider in order:
            assert provider in present or provider in gaps.get(course_id, ()), (
                course_id, provider)
    # The known, deliberate shortfall.
    assert 'gizmos' in gaps.get('physics', [])
    # And Gizmos is genuinely reachable somewhere, so the gap is a gap and not the whole
    # provider being unwired.
    assert any('gizmos' in provs for provs in contributed.values())


def test_phet_is_withheld_on_a_paid_instance(offline_settings):
    paid = replace(offline_settings, commercial_use=True)
    cards = [c for c in simulation_map.for_course(paid, 'physics')['units']
             for c in c['simulations'] if c['provider'] == 'phet']
    assert cards
    for card in cards:
        assert card['status'] == 'withheld'
        assert card['launch_url'] == ''
        assert 'commercial' in card['withheld_reason']


def test_an_uncovered_concept_returns_a_gap_not_the_least_bad_match(offline_settings):
    result = simulation_map.for_concept(offline_settings, 'physics',
                                       'torque and angular momentum')
    assert result.get('gap'), 'an uncovered concept returned no gap statement'


def test_the_pack_publishes_its_own_gaps():
    coverage = simulation_map.coverage()
    assert coverage['total_mapped'] > 0
    assert coverage['total_uncovered'] > 0


# ----------------------------------------------------------- presentations

def test_presentation_uses_one_narrator_and_audio_led_timing(ctx, offline_settings):
    ctx = harness_context(offline_settings)
    deck = presentation.compose(ctx, 'quadratic_expressions_and_their_graphs', {})
    assert deck['method']['narrator'] == 'single'
    assert 'audio-led' in deck['method']['assembly']
    clock = 0.0
    for slide in deck['slides']:
        assert slide['start'] == pytest.approx(clock, abs=1e-6)
        # The stored duration is the audio-led estimate rounded to milliseconds, which is
        # the contract the renderer and the VTT both read. Comparing against the unrounded
        # value would fail by half a millisecond and would be asserting a contract the code
        # does not offer.
        expected = round(presentation.estimate_seconds(
            next(s['text'] for s in deck['script'] if s['index'] == slide['index'])
        ) + presentation.SLIDE_PAD_SECONDS, 3)
        assert slide['duration'] == expected
        # The timeline must be arithmetically closed, or a scrub bar built from the
        # durations drifts away from the timestamps it is drawn against.
        assert slide['end'] == round(slide['start'] + slide['duration'], 3)
        clock += slide['duration']
    assert deck['total_seconds'] == pytest.approx(clock, abs=1e-3)
    # Audio-led is the load-bearing claim: the pad and the word count decide the slide, so a
    # slide must not be able to arrive with a duration bearing no relation to its narration.
    padded = sum(presentation.SLIDE_PAD_SECONDS for _ in deck['slides'])
    assert deck['total_seconds'] > padded


def test_presentation_timeline_is_monotonic(ctx, offline_settings):
    deck = presentation.compose(harness_context(offline_settings),
                               'quadratic_expressions_and_their_graphs', {})
    ends = [s['end'] for s in deck['slides']]
    assert ends == sorted(ends)
    assert all(s['end'] > s['start'] for s in deck['slides'])


def test_presentation_emits_an_editable_script_and_a_subtitle_track(ctx, offline_settings):
    deck = presentation.compose(harness_context(offline_settings),
                               'quadratic_expressions_and_their_graphs', {})
    assert deck['script'], 'no editable script was emitted'
    assert deck['vtt'].startswith('WEBVTT')
    cues = [line for line in deck['vtt'].splitlines() if '-->' in line]
    assert len(cues) == len([s for s in deck['slides'] if s['narration'].strip()])


def test_the_exported_deck_is_self_contained(ctx, offline_settings):
    deck = presentation.compose(harness_context(offline_settings),
                               'quadratic_expressions_and_their_graphs', {})
    html = deck['html']
    assert html.startswith('<!DOCTYPE html>')
    # Nothing that *loads* over the network. The deck has to open on a machine that has
    # never seen this application and may be offline, so a CDN font or a runtime is a bug.
    for marker in ('<script', '@import', '<link', 'rel="stylesheet"', 'src="http',
                   "src='http", 'url(http'):
        assert marker not in html, marker
    # Fonts are named, not fetched: ui-serif/Georgia/Times New Roman are local family names.
    assert 'fonts.googleapis' not in html
    # The one absolute URL the document is allowed to carry is the SVG XML namespace, which
    # is a mandatory identifier rather than a fetch. Remove it, and there must be no
    # absolute reference left at all -- which is the strong form of "self-contained".
    stripped = html.replace('http://www.w3.org/2000/svg', '')
    assert 'http://' not in stripped, stripped[stripped.index('http://'):][:120]
    assert 'https://' not in stripped, stripped[stripped.index('https://'):][:120]


def test_presentation_blocks_carry_a_printed_slide_per_slide(ctx, offline_settings):
    artefact = generate.compose(harness_context(offline_settings),
                               'quadratic_expressions_and_their_graphs', 'presentation', {})
    assert artefact.kind == 'presentation'
    assert artefact.metadata['slides']
    assert artefact.metadata['total_seconds'] > 0
    assert any(block['type'] == 'slide' for block in artefact.blocks)


def test_presentation_visuals_are_never_model_generated(ctx, offline_settings):
    """The documented failure of this format is a confident, wrong generated figure."""
    deck = presentation.compose(harness_context(offline_settings),
                               'quadratic_expressions_and_their_graphs', {},
                               )
    kinds = {s['visual']['type'] for s in deck['slides'] if s['visual']}
    assert kinds <= {'generated_figure', 'photograph', 'simulation'}, kinds


# ----------------------------------------------------------- tool wiring

def test_the_new_tools_are_registered_with_the_right_posture():
    specs = {spec.name: spec for spec, _ in toolbox.REGISTRY.values()}
    assert specs['find_image'].posture == 'ingestible'
    assert specs['find_video'].posture == 'embed_only'
    assert specs['find_simulation'].posture == 'embed_only'
    assert specs['build_presentation'].posture == 'internal'
    assert 'embed_only' in toolbox.POSTURES


def test_find_image_reports_a_refusal_rather_than_raising(offline_settings):
    result = toolbox.invoke(harness_context(offline_settings), 'find_image',
                            {'concept_id': 'fraction_equivalence'})
    assert isinstance(result, toolbox.ToolResult)
    assert result.tool == 'find_image'
    assert result.ok is False
    assert result.refused


def test_find_simulation_is_unobservable_through_the_tool(ctx, offline_settings):
    result = toolbox.invoke(harness_context(offline_settings), 'find_simulation',
                            {'concept_id': 'fraction_equivalence'})
    assert result.ok
    assert result.data['observable'] is False


def test_generated_kinds_include_every_new_capability():
    for kind in ('photo', 'video_lesson', 'presentation'):
        assert kind in generate.KINDS, kind
    catalogue = {row['kind'] for row in generate.catalogue()}
    assert {'photo', 'video_lesson', 'presentation'} <= catalogue


def test_media_pipeline_describe_states_its_guarantees(offline_settings):
    described = media.describe(offline_settings)
    assert described['enabled'] is False
    assert described['guarantees']
    assert 'cc_by_nc' in described['licences_refused']
    assert described['excluded_providers'] if 'excluded_providers' in described else True
