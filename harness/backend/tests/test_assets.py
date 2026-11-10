"""Asset review: does the harness's own output talk about the concept it was asked about?

The generators are deterministic, so "it produced something" was never the risk. The risk
is producing a well-formed figure for a *different* concept and shipping it under this
concept's name. That happened: "Permutations and combinations" was rendered as a binomial
sampling distribution, because the template table's probability rule claimed the word
"permutation". Nothing in the engine could notice, because it had succeeded.

So these tests pin two things: that the review catches that failure, and that the shipped
courses now pass it — every mathematics concept in every pack, not one example.
"""

import json
from pathlib import Path

import pytest

from app import figures
from app.courses import COURSES, MATHEMATICS
from app.harness.teaching import assets
from app.mathkit import build as build_simulation
from app.mathkit.templates import _probability, template_for

ROOT = Path(__file__).resolve().parents[1]
PACKS = ROOT / 'app' / 'curriculum_packs'

PERMUTATIONS = {'id': 'permutations_and_combinations',
                'title': 'Permutations and combinations',
                'topic': 'Conditional probability and counting',
                'keywords': ['combination', 'order', 'permutation', 'selection']}


class IsolatedGraph:
    """The minimum a concept map needs; these tests never depend on graph edges."""

    nodes: dict = {}

    def parents(self, node_id): return []
    def children(self, node_id): return []
    def siblings(self, node_id): return []
    def in_unit(self, node_id): return [node_id]
    def ancestors(self, node_id): return []
    def descendants(self, node_id): return []


def payload_of(concept, kind='mathematics'):
    return figures.figure_for(concept, IsolatedGraph(), {}, subject_kind=kind)


# ---------------------------------------------------------------- catching the failure

def test_a_figure_about_a_different_idea_is_off_topic():
    """The exact payload this concept used to receive must now be rejected."""
    review = assets.review_simulation(PERMUTATIONS,
                                      build_simulation(_probability('permutations_and_combinations')))
    assert review['verdict'] == 'off_topic'
    assert not review['usable']
    assert 'permutation' in review['why']


def test_the_review_names_what_it_looked_for():
    """A refusal a teacher cannot understand is indistinguishable from a bug."""
    review = assets.review_simulation(PERMUTATIONS,
                                      build_simulation(_probability('permutations_and_combinations')))
    assert review['concept_terms'] == ['combination', 'order', 'permutation', 'selection']


def test_the_topic_alone_is_not_evidence():
    """Every concept in a unit shares its topic, so a topic word proves nothing.

    The binomial payload mentions "probability", which is in this concept's topic. Counting
    the topic as identifying vocabulary made the wrong figure pass.
    """
    assert 'probability' not in assets.concept_terms(PERMUTATIONS)


def test_the_generic_probe_is_never_treated_as_a_figure():
    review = assets.review_simulation(PERMUTATIONS, {'kind': 'function_probe', 'title': 'Probing a rule'})
    assert review['verdict'] == 'off_topic'


def test_a_concept_map_is_a_fallback_not_a_success():
    review = assets.review_simulation(PERMUTATIONS, payload_of(PERMUTATIONS, kind='science'))
    assert review['verdict'] == 'fallback'
    assert review['usable'], 'a concept map is true, so it may still be shown'


def test_a_figure_with_no_controls_and_no_curve_is_broken():
    """It has to name the concept *and* have something to manipulate; naming is checked first."""
    review = assets.review_simulation(
        PERMUTATIONS, {'kind': 'arrangements', 'title': 'Permutations and combinations'})
    assert review['verdict'] == 'broken'


# ---------------------------------------------------------------- what the courses get

def test_permutations_get_a_counting_figure_not_a_distribution():
    """The regression that started this module."""
    payload = payload_of(PERMUTATIONS)
    assert payload['kind'] == 'arrangements'
    assert 'choose' in payload.get('title', '') or 'order' in payload.get('objective', '').casefold()
    assert assets.review_simulation(PERMUTATIONS, payload)['verdict'] == 'ok'


def _mathematics_concepts():
    seen = set()
    for course in COURSES:
        if course.subject_kind != MATHEMATICS or course.pack in seen:
            continue
        seen.add(course.pack)
        data = json.loads((PACKS / f'{course.pack}.json').read_text(encoding='utf-8'))
        for concept in data.get('concepts') or []:
            yield course.pack, concept


def test_every_mathematics_concept_gets_a_figure_about_itself():
    """Not a sample: every concept in every mathematics pack the product ships."""
    failures = []
    for pack, concept in _mathematics_concepts():
        review = assets.review_simulation(concept, payload_of(concept))
        if review['verdict'] in ('off_topic', 'broken', 'missing'):
            failures.append(f"{pack}/{concept['id']} -> {review['verdict']}: {review['why'][:90]}")
    assert not failures, '\n'.join(failures)


#: The concepts that genuinely have no figure in the symbolic engine: matrices are not "a
#: quantity as a function of one variable", so a plot of one would be a lie. They get the
#: concept map. Adding to this set is a decision, not an accident.
KNOWN_WITHOUT_A_SIMULATION = {
    'algebra_2_determinants',
    'algebra_2_inverse_matrices',
    'algebra_2_matrix_multiplication',
    'algebra_2_matrix_notation_and_operations',
    'algebra_2_solving_systems_with_matrices',
    # Unit cancellation is an operation on units, not a quantity varying with an input.
    'algebra_1_dimensional_analysis',
    'dimensional_analysis_and_unit_conversion',
    # ACT Math's matrix/vector concepts are matched by the existing matrix rule, which is
    # correct: neither is a quantity plotted against an input.
    'act_math_matrix_dimensions_and_products',
    'act_math_vector_addition_and_scalar_multiplication',
    'act_math_vector_components_and_magnitude',
}

#: Courses with no single-variable plot at all; see the same declaration in
#: ``tests/test_calculus_figures.py`` and ``app.mathkit.templates._NO_PLOT_COURSE_PREFIXES``.
NO_PLOT_COURSES = {'linear_algebra'}


def _declared_without_a_simulation() -> set[str]:
    """The declared no-figure set: static entries plus the engine's own declarations.

    Derived from ``templates._CONCEPT_TEMPLATES`` and the course-level prefix list so the
    expectation follows the code instead of being restated (and going stale) here.
    """
    from app import courses as _courses
    from app.mathkit import templates as _t

    ids = {concept_id for concept_id, builder in _t._CONCEPT_TEMPLATES.items()
           if builder is _t.no_figure}
    ids |= set(KNOWN_WITHOUT_A_SIMULATION)
    for course in COURSES:
        if course.id in NO_PLOT_COURSES:
            ids |= set(_courses.graph_for(course.id).nodes)
    return ids


def test_the_only_mathematics_concepts_without_a_simulation_are_the_matrices():
    """A concept map is the honest answer for these; a parabola would not be.

    Pinned so that a future template change cannot silently widen the gap, and so that
    closing it is a deliberate act rather than an accident.
    """
    fell_back = {concept['id'] for pack, concept in _mathematics_concepts()
                 if assets.review_simulation(concept, payload_of(concept))['verdict'] == 'fallback'}
    expected = _declared_without_a_simulation()
    assert fell_back == expected, sorted(fell_back ^ expected)


# ---------------------------------------------------------------- video and repair

def test_a_verified_video_is_an_embed_and_an_unverified_one_is_a_link():
    good = assets.review_video({'verified': True, 'embed_url': 'https://x/embed', 'watch_url': 'w'})
    bad = assets.review_video({'verified': False, 'verification': 'oembed_iframe_absent', 'watch_url': 'w'})
    assert good['verdict'] == 'ok' and good['usable']
    assert bad['verdict'] == 'unverified' and bad['usable']
    assert 'oembed_iframe_absent' in bad['why']


def test_an_image_without_a_licence_is_not_usable():
    assert assets.review_image({'sha256': 'abc'})['verdict'] == 'unverified'
    assert assets.review_image({'sha256': 'abc', 'licence': 'cc0'})['verdict'] == 'ok'


def test_repair_substitutes_before_it_fixes():
    """The teacher has to keep talking; the fix runs afterwards."""
    review = assets.review_simulation(PERMUTATIONS,
                                      build_simulation(_probability('permutations_and_combinations')))
    plan = assets.plan_repair([review], can_search_video=True)
    assert plan[0]['substitute'] == 'concept_map'
    assert plan[0]['fix'] == 'rebuild_simulation'
    assert 'permutation' in plan[0]['why']


def test_a_broken_interactive_hands_off_to_a_curated_video_when_there_is_one():
    """The in-class move the product is for: the interactive fails, the video explains it.

    A concept map is the fallback only because it is the one thing that always exists. When
    a verified video is already curated, showing it is a better answer to "the simulator is
    broken" - it teaches the same idea - and the TA still rebuilds the interactive, because
    a video is a stand-in, not a replacement.
    """
    review = assets.review_simulation(PERMUTATIONS,
                                      build_simulation(_probability('permutations_and_combinations')))
    assert review['verdict'] == 'off_topic'

    with_video = assets.plan_repair([review], can_search_video=True, video_available=True)
    assert with_video[0]['substitute'] == 'video'
    assert with_video[0]['fix'] == 'rebuild_simulation', 'the interactive is still repaired'

    # Without one, nothing is invented: the concept map stands and no video search is
    # smuggled in as a substitute.
    without = assets.plan_repair([review], can_search_video=True, video_available=False)
    assert without[0]['substitute'] == 'concept_map'

    # A *missing* interactive is a different problem: there is nothing to hand off from, so
    # the substitute stays a concept map even when a video exists.
    missing = assets.plan_repair([assets.review_simulation(PERMUTATIONS, None)],
                                 video_available=True)
    assert missing[0]['substitute'] == 'concept_map'


def test_an_offline_instance_is_not_given_a_video_search_job():
    """Planning a job that is guaranteed to refuse is worse than planning nothing."""
    unverified = assets.review_video({'verified': False, 'watch_url': 'w'})
    offline = assets.plan_repair([unverified], can_search_video=False)
    online = assets.plan_repair([unverified], can_search_video=True)
    assert offline[0]['fix'] == 'none'
    assert online[0]['fix'] == 'search_videos'


def test_a_clean_sweep_says_nothing():
    sweep = assets.sweep(PERMUTATIONS, {'simulation': payload_of(PERMUTATIONS)})
    assert sweep['clean'] and sweep['all_ok']
    assert assets.describe(sweep['reviews']) == ''


def test_a_sweep_separates_what_blocks_from_what_can_be_improved():
    """A concept map is shippable; an off-topic figure is not. They are not the same list."""
    sweep = assets.sweep(PERMUTATIONS, {
        'simulation': build_simulation(_probability('permutations_and_combinations')),
        'video': {'verified': False, 'watch_url': 'w'},
    })
    assert not sweep['clean']
    assert [problem['asset'] for problem in sweep['problems']] == ['simulation']
    assert [downgrade['asset'] for downgrade in sweep['downgrades']] == ['video']
    report = assets.describe(sweep['reviews'])
    assert 'blocking: simulation (off_topic)' in report
    assert 'usable but improvable: video (unverified)' in report
