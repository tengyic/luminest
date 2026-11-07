"""Widening a lesson title to its subject when the whole title finds nothing.

The defect these pin: a deck slide showed a decorative pattern labelled like a figure instead
of a photograph, and the reason was not that no picture existed. ``"Blood vessels and their
adaptation"`` returned 12 candidates and the relevance gate rejected all 12, because the term
the concept turns on is "adaptation" and no photograph of a blood vessel says so about itself.
``"Blood vessels"`` returned 40 candidates and accepted 11.

The widening is deliberately narrow: it runs once, only after a search that actually ran and
rejected everything, and only when the head is still a phrase. A title that already works is
never rewritten, and "Supply and demand" is not reduced to "Supply" — a single generic word is
where full-text image search returns its most confident nonsense, and the gate would then
accept a photograph of a supply ship for an economics lesson.

No network: ``acquire`` is replaced, so these assert the decision, not the providers.
"""

import pytest

from app.config import Settings
from app.harness import media


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('HARNESS_MEDIA_ENABLED', '1')
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    return Settings.from_env()


def test_the_head_of_a_lesson_title_is_the_part_a_photograph_can_show():
    assert media._head_phrase('Blood vessels and their adaptation') == 'Blood vessels'
    assert media._head_phrase('Air masses and fronts') == 'Air masses'
    assert media._head_phrase('Air pollution and its chemistry') == 'Air pollution'


def test_a_one_word_head_is_left_alone():
    """``Supply`` is not a subject, it is a word. Widening to it would hand the gate a
    generic term and let a photograph of anything "supply" pass for an economics lesson."""
    assert media._head_phrase('Supply and demand') == ''


def test_a_title_without_a_conjunction_is_not_widened():
    assert media._head_phrase('Mitosis') == ''
    assert media._head_phrase('Conservation of mechanical energy') == ''
    assert media._head_phrase('') == ''


def _stub_acquire(monkeypatch, answers):
    """Answer per query, recording what was asked."""
    asked = []

    def fake(_settings, query, *, alt_text='', support=''):
        asked.append(query)
        answer = answers.get(query)
        if answer is None:
            return {'outcome': 'no_cleared_candidate', 'asset': None, 'notes': ['nothing']}
        return {'outcome': 'downloaded', 'asset': answer, 'notes': []}

    monkeypatch.setattr(media, 'acquire', fake)
    return asked


def test_the_whole_title_is_tried_first_and_the_subject_second(settings, monkeypatch):
    asked = _stub_acquire(monkeypatch, {'Blood vessels': {'sha256': 'a' * 64}})
    result = media.find_image(settings, 'Blood vessels and their adaptation')
    assert asked == ['Blood vessels and their adaptation', 'Blood vessels']
    assert result['asset']['sha256'] == 'a' * 64
    assert result['queries'] == ['Blood vessels and their adaptation', 'Blood vessels']
    # The learner-facing record says what was searched, so a wrong picture is traceable to
    # the query that produced it rather than looking like an editorial choice.
    assert 'widened' in result['notes'][0]


def test_a_title_that_works_is_never_searched_twice(settings, monkeypatch):
    asked = _stub_acquire(monkeypatch, {
        'Air masses and fronts': {'sha256': 'b' * 64}})
    result = media.find_image(settings, 'Air masses and fronts')
    assert asked == ['Air masses and fronts']
    assert 'queries' not in result
    assert result['asset']['sha256'] == 'b' * 64


def test_a_network_refusal_is_not_retried(settings, monkeypatch):
    """``network_disabled`` means the search never ran. Asking again would produce the same
    refusal and cost the learner a second timeout for nothing."""
    asked = []

    def fake(_settings, query, *, alt_text='', support=''):
        asked.append(query)
        return {'outcome': 'network_disabled', 'asset': None, 'notes': ['off']}

    monkeypatch.setattr(media, 'acquire', fake)
    result = media.find_image(settings, 'Blood vessels and their adaptation')
    assert asked == ['Blood vessels and their adaptation']
    assert result['outcome'] == 'network_disabled'
