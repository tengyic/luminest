"""The curated image pack is keyed by short slugs; every caller holds a long course id.

This is the join that was missing: ``shipped_for`` looked the pack up with
``physics_acceleration_as_the_rate_of_change_of_velocity`` while the curator had written
``acceleration``, so the entire shipped pack was unreachable.

The first version of ``_concept_keys`` derived its candidates *from* the pack, so a pack
that failed to load yielded no candidates and reproduced the exact bug it was written to
fix. These tests therefore assert against ids alone, with no pack on disk.
"""
from app.harness import media


def test_long_course_id_reaches_the_shipped_slug():
    keys = media._concept_keys('physics_acceleration_as_the_rate_of_change_of_velocity')
    assert 'acceleration' in keys


def test_two_token_slug_is_reachable_inside_a_qualified_id():
    keys = media._concept_keys('biology_active_transport_across_a_membrane')
    assert 'active_transport' in keys


def test_five_token_slug_is_reachable_inside_a_qualified_id():
    """A curator's multi-word slug is not truncated by the window width."""
    keys = media._concept_keys('biology_active_transport_across_a_membrane')
    assert 'active_transport_across_a_membrane' in keys


def test_exact_slug_is_tried_before_any_shorter_key():
    keys = media._concept_keys('active_transport')
    assert keys[0] == 'active_transport'


def test_keys_are_ordered_longest_first():
    keys = media._concept_keys('physics_acceleration_as_the_rate_of_change_of_velocity')
    assert keys == sorted(keys, key=len, reverse=True)


def test_a_supplied_pack_key_with_other_tokenisation_is_admitted():
    keys = media._concept_keys('biology_transport_of_ions', {'transport_of_ions'})
    assert 'transport_of_ions' in keys


def test_no_concept_id_yields_no_keys():
    assert media._concept_keys('') == []
    assert media._concept_keys('   ') == []
