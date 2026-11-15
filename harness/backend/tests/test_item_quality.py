"""Whether an item can separate two mistakes, or only two topics.

The distinction is the difference between a mastery number and a vanity number. An item
whose every wrong option is another concept's summary is answerable by crossing out the
three statements about something else; its outcome still moves mastery, which is how the
harness becomes confident about something it never measured.
"""
from app.procedure_service import _item_quality


def item(*reasons: str) -> dict:
    return {'distractor_diagnoses': {f'o{index}': {'reason': reason}
                                     for index, reason in enumerate(reasons)}}


def test_an_item_with_no_diagnoses_is_unclassified():
    assert _item_quality({}) == 'none'
    assert _item_quality({'distractor_diagnoses': {}}) == 'none'


def test_every_option_naming_another_concept_is_topic_recognition():
    assert _item_quality(item('This is the statement for "Binomial expansion", not for '
                              '"Permutations and combinations".',
                              'This belongs to a different part of the course.')) \
        == 'topic_recognition'


def test_one_real_error_process_makes_the_item_diagnostic():
    """One diagnosed misconception is enough: the item can now separate two wrong ideas."""
    assert _item_quality(item('This is the statement for "Binomial expansion", not for '
                              '"Permutations".',
                              'Adds the denominators as though fractions could be added '
                              'term by term.')) == 'error_process'


def test_blank_reasons_do_not_count_as_diagnoses():
    assert _item_quality(item('', '')) == 'none'


def test_a_non_mapping_payload_is_unclassified_rather_than_raising():
    assert _item_quality({'distractor_diagnoses': ['not', 'a', 'mapping']}) == 'none'
