"""Attribution: a stored page must belong to the slug *and* the spec that made it.

The playground stores generated games in the same artifact store as hand-authored
simulations. ``pipeline._find_artifact`` decides whether a request is a *replay* of
something already stored or a *new* revision, by matching two things at once::

    meta.get('playground_slug') == slug and meta.get('spec_hash') == revision

Both halves are load-bearing, and they fail in opposite directions:

* Drop ``spec_hash`` and an edited game silently serves its **stale** page. The
  learner sees the old content while the author believes the change shipped - and
  because ``spec_hash`` is also what makes instantiation idempotent, the failure is
  invisible: the store is full of one artifact, the request succeeds, the URL works.
* Drop ``playground_slug`` and two different games collide onto one artifact whenever
  their specs happen to hash the same, which for two games built from the same
  template and the same numbers is not a hypothetical.

So this file tests the pair. The sharpest case is (3): a page generated from spec A
must never be served for spec B. That is the attribution bug worth guarding, because
every other symptom of it looks like success.

``curve_shift`` is the reference archetype - the pattern every other archetype
copies - so it is the right canary for a schema or rendering change.
"""

from __future__ import annotations

import copy

import pytest

from app.config import Settings
from app.harness import sims_store
from app.harness.playground import get, pipeline, validate_spec

#: A real, valid ``curve_shift`` spec. Defined here rather than imported from
#: ``test_playground_pipeline`` so this file runs on its own - a test that only works
#: when another test module has been imported is not evidence.
SPEC_A = {
    'title': 'Attribution Canary A',
    'instruction': 'Drag the curve the shock affects, then press Check.',
    'x_max': 10,
    'y_max': 10,
    'curves': [
        {'id': 'demand', 'label': 'Demand D', 'colour': 'a',
         'intercept': 10, 'slope': -1, 'shifts': True},
        {'id': 'supply', 'label': 'Supply S', 'colour': 'b',
         'intercept': 1, 'slope': 1, 'shifts': False},
    ],
    'shocks': [
        {'id': 'income-up', 'text': 'CANARY-ALPHA household incomes rise.',
         'shift': 'demand', 'direction': 'right', 'price': 'up', 'quantity': 'up',
         'why': 'Demand rises, so the equilibrium moves up the supply curve.'},
    ],
}

#: The same shape with different content, so the two render differently but stay
#: schema-valid. The distinct marker strings are what the assertions look for.
SPEC_B = {
    **SPEC_A,
    'title': 'Attribution Canary B',
    'shocks': [
        {'id': 'input-cost', 'text': 'CANARY-BETA input costs fall.',
         'shift': 'supply', 'direction': 'right', 'price': 'down', 'quantity': 'up',
         'why': 'Cheaper inputs shift supply right, so price falls and quantity rises.'},
    ],
}


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """A hermetic harness pointed at a throwaway data dir."""
    monkeypatch.setenv('HARNESS_ENV', 'test')
    monkeypatch.setenv('HARNESS_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HARNESS_DATABASE_URL', raising=False)
    monkeypatch.delenv('HARNESS_SECRET', raising=False)
    monkeypatch.delenv('HARNESS_TUTOR_PROVIDER', raising=False)
    return Settings.from_env()


def test_the_specs_this_file_uses_are_valid():
    """A guard, so a schema change fails here with a clear message instead of as
    several confusing failures below. An attribution test built on invalid specs
    would be testing the validator, not attribution."""
    archetype = get('curve_shift')
    assert validate_spec(SPEC_A, archetype) == []
    assert validate_spec(SPEC_B, archetype) == []


def test_the_two_specs_really_do_differ():
    """The whole file rests on A and B being different content. If they hashed the
    same, every 'forces a new revision' assertion below would pass vacuously."""
    assert pipeline.spec_hash('curve_shift', SPEC_A) != pipeline.spec_hash('curve_shift', SPEC_B)


# --------------------------------------------------------------- (a) replay reuses


def test_recomposing_an_unchanged_spec_reuses_the_stored_artifact(settings):
    """Replaying a game must not mint a second copy. The store is an audit trail, so
    identical duplicates would make 'how many games exist' unanswerable."""
    first = pipeline.compose(settings, archetype_id='curve_shift', spec=SPEC_A,
                             title='Attribution Canary A', slug='canary-reuse')
    assert first['reused'] is False

    second = pipeline.compose(settings, archetype_id='curve_shift', spec=SPEC_A,
                              title='Attribution Canary A', slug='canary-reuse')

    assert second['reused'] is True
    assert second['id'] == first['id']
    assert len(sims_store.list_artifacts(settings, kind='simulation')) == 1


def test_the_hash_ignores_key_order(settings):
    """``spec_hash`` canonicalises with ``sort_keys=True``. Without that, a spec that
    differs only in dict ordering would look like new content and mint a version on
    every request - the idempotence above would hold only by luck of construction."""
    reordered = {k: SPEC_A[k] for k in reversed(list(SPEC_A))}
    assert list(reordered) != list(SPEC_A), 'the reorder did not actually reorder'
    assert pipeline.spec_hash('curve_shift', reordered) == pipeline.spec_hash('curve_shift', SPEC_A)


# ------------------------------------------------- (b) a changed spec is a new one


def test_changing_the_spec_forces_a_new_revision(settings):
    first = pipeline.compose(settings, archetype_id='curve_shift', spec=SPEC_A,
                             title='Attribution Canary A', slug='canary-revision')
    second = pipeline.compose(settings, archetype_id='curve_shift', spec=SPEC_B,
                              title='Attribution Canary B', slug='canary-revision')

    assert second['reused'] is False
    assert second['id'] != first['id']
    assert len(sims_store.list_artifacts(settings, kind='simulation')) == 2


# ------------------------------------------- (c) the attribution bug worth guarding


def test_a_page_from_spec_a_is_never_served_for_spec_b(settings):
    """The one that matters.

    Same slug, different content. If ``_find_artifact`` matched on the slug alone,
    the second compose would return the first artifact and every assertion except
    the content check would still pass - the call succeeds, a URL comes back, the
    page loads. Only reading the served HTML catches it.
    """
    a = pipeline.compose(settings, archetype_id='curve_shift', spec=SPEC_A,
                         title='Attribution Canary A', slug='canary-attribution')
    b = pipeline.compose(settings, archetype_id='curve_shift', spec=SPEC_B,
                         title='Attribution Canary B', slug='canary-attribution')

    assert b['id'] != a['id'], 'the second spec was served the first spec\'s artifact'

    html_b = sims_store.latest_html(settings, b['id'])
    html_a = sims_store.latest_html(settings, a['id'])
    assert html_b and html_a

    assert 'CANARY-BETA' in html_b
    assert 'CANARY-ALPHA' not in html_b, 'spec B served a page rendered from spec A'
    assert 'CANARY-ALPHA' in html_a
    assert 'CANARY-BETA' not in html_a


def test_the_stored_metadata_records_the_spec_that_produced_it(settings):
    """The attribution link is the ``spec_hash`` in the artifact's meta. Assert it is
    the real fingerprint rather than a constant or a copy of the slug."""
    entry = pipeline.compose(settings, archetype_id='curve_shift', spec=SPEC_A,
                             title='Attribution Canary A', slug='canary-meta')
    meta = entry['meta']
    assert meta['playground_slug'] == 'canary-meta'
    assert meta['archetype'] == 'curve_shift'
    assert meta['spec_hash'] == pipeline.spec_hash('curve_shift', SPEC_A)
    # A slug is not a fingerprint: the two must not be interchangeable.
    assert meta['spec_hash'] != meta['playground_slug']


def test_the_same_spec_under_a_different_slug_is_a_different_artifact(settings):
    """The mirror of the case above. Two teachers authoring identical content should
    each own their artifact, because the slug is what a course links to."""
    one = pipeline.compose(settings, archetype_id='curve_shift', spec=SPEC_A,
                           title='Attribution Canary A', slug='canary-one')
    two = pipeline.compose(settings, archetype_id='curve_shift', spec=SPEC_A,
                           title='Attribution Canary A', slug='canary-two')

    assert one['id'] != two['id']
    assert two['reused'] is False
    assert len(sims_store.list_artifacts(settings, kind='simulation')) == 2


def test_a_mutation_of_a_stored_spec_is_detected(settings):
    """A shallow-copied spec handed back to ``compose`` after being mutated must not
    be mistaken for the original. This is the realistic authoring slip: edit the
    object you already have, re-submit it, and get the old page back."""
    stored = copy.deepcopy(SPEC_A)
    pipeline.compose(settings, archetype_id='curve_shift', spec=stored,
                     title='Attribution Canary A', slug='canary-mutation')

    stored['shocks'][0]['text'] = 'CANARY-GAMMA the shock was edited in place.'
    again = pipeline.compose(settings, archetype_id='curve_shift', spec=stored,
                             title='Attribution Canary A', slug='canary-mutation')

    assert again['reused'] is False
    assert 'CANARY-GAMMA' in (sims_store.latest_html(settings, again['id']) or '')
