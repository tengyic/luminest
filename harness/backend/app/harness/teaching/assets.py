"""Asset review: is this artefact actually about the concept it is attached to?

The generators are deterministic, which makes them reliable but not automatically
*relevant*. The template chooser matches a concept's title, topic and keywords against a
rule table, and when the table has no good rule the concept falls through to a neighbour
that is real content for a different idea. That is not hypothetical: before this module
existed, "Permutations and combinations" was rendered as a binomial sampling distribution
— a true figure, correctly drawn, about a concept the learner had not asked for. The
symbolic engine had no way to notice, because from its point of view it had succeeded.

So the review is not a lint pass over formatting. It asks one question the generator
cannot ask itself: **does this artefact talk about this concept?** The test is the
concept's own distinguishing vocabulary — its title and keywords, minus words that every
figure in the subject uses — appearing anywhere in the artefact's own prose (title,
objective, notes, steps, readout labels). An artefact that never names the idea is off
topic however well formed it is.

Three consequences, all deliberate:

* **A concept map is a fallback, not a success.** It is derived from the graph's edges, so
  it is always true, but it is not an exploration of the concept. It is reported as
  ``fallback`` so the caller can substitute something better while still shipping it.
* **Unverified is not verified.** A video card that failed the oEmbed probe keeps its
  watch link and loses its embed, exactly as :mod:`app.harness.video_search` decided; the
  review reports the position rather than re-deciding it.
* **Repair is a plan, not an action.** This module never writes, fetches or rebuilds. It
  says what is wrong and what would fix it, so the TA can act on it and the teacher can
  keep teaching in the meantime.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence

#: Verdicts, ordered from best to worst. ``fallback`` and ``off_topic`` are both "not the
#: thing that was asked for"; they differ in whether what arrived is still honest.
VERDICTS = ('ok', 'fallback', 'unverified', 'off_topic', 'broken', 'missing')

#: The verdicts a teacher can put in front of a learner without an apology.
USABLE = frozenset({'ok', 'fallback', 'unverified'})

#: Shorter tokens are grammar, not content ("the", "of", "and", "for", "with").
MIN_TERM_LENGTH = 4

#: Words that appear in the prose of almost every figure in a mathematics course. A match
#: on one of these proves nothing about relevance, so they are excluded from the evidence
#: rather than counted as a hit.
GENERIC_TERMS = frozenset({
    'value', 'values', 'number', 'numbers', 'figure', 'figures', 'graph', 'graphs',
    'change', 'changes', 'changing', 'shows', 'show', 'using', 'used', 'each', 'same',
    'different', 'total', 'first', 'second', 'third', 'given', 'find', 'found', 'move',
    'moving', 'slider', 'parameter', 'parameters', 'curve', 'point', 'points', 'left',
    'right', 'above', 'below', 'between', 'because', 'which', 'when', 'then', 'than',
    'that', 'this', 'these', 'those', 'from', 'into', 'with', 'without', 'more', 'less',
    'much', 'many', 'some', 'only', 'also', 'very', 'just', 'like', 'does', 'doesn',
    'here', 'there', 'where', 'what', 'your', 'you', 'the', 'and', 'for', 'are', 'was',
    'has', 'have', 'its', 'their', 'them', 'they', 'not', 'but', 'all', 'any', 'can',
})

_WORD = re.compile(r'[a-z]+')


def _terms(text: str) -> set[str]:
    """Content words in ``text``, crudely singularised.

    Plural stripping is intentionally shallow (``arrangements`` → ``arrangement``): the
    vocabularies being compared are short and curated, so a stemmer's false merges would
    cost more than they save.
    """
    out = set()
    for word in _WORD.findall((text or '').casefold()):
        if len(word) < MIN_TERM_LENGTH or word in GENERIC_TERMS:
            continue
        out.add(word[:-1] if len(word) > MIN_TERM_LENGTH + 1 and word.endswith('s') else word)
    return out


def concept_terms(concept: Mapping[str, Any]) -> set[str]:
    """The vocabulary that identifies this concept, from its title and keywords.

    The topic is deliberately **not** used. It is shared by every concept in the unit — the
    topic of "Permutations and combinations" is "Conditional probability and counting" — so
    a figure that only mentions the topic has said nothing about *this* concept. Including
    it made the binomial sampling distribution pass the review, because its notes contain
    the word "probability".
    """
    parts: list[str] = [str(concept.get('title') or '')]
    parts.extend(str(keyword) for keyword in concept.get('keywords') or ())
    return _terms(' '.join(parts))


def _artifact_text(payload: Mapping[str, Any]) -> str:
    """Everything the artefact says about itself, in the order a learner reads it."""
    chunks = [str(payload.get('title') or ''), str(payload.get('objective') or '')]
    chunks.extend(str(note) for note in payload.get('notes') or ())
    chunks.extend(str(step) for step in payload.get('steps') or ())
    for readout in payload.get('readouts') or ():
        if isinstance(readout, Mapping):
            chunks.append(str(readout.get('label') or ''))
            chunks.append(str(readout.get('detail') or ''))
    return ' '.join(chunks)


def _verdict(name: str, verdict: str, why: str, **extra: Any) -> dict[str, Any]:
    return {'asset': name, 'verdict': verdict, 'why': why, 'usable': verdict in USABLE, **extra}


def review_simulation(concept: Mapping[str, Any], payload: Mapping[str, Any] | None) -> dict:
    """Judge a generated figure/simulation against the concept it was generated for.

    ``payload`` is the dict the symbolic engine returns (``figures.build_simulation``),
    not the ``SimulationSpec``: the review is about what the learner would actually see.
    """
    if not payload:
        return _verdict('simulation', 'missing', 'No figure was generated for this concept.')

    kind = str(payload.get('kind') or '')
    if kind == 'concept_map':
        return _verdict(
            'simulation', 'fallback',
            'No template matched this concept, so the honest concept map was served instead '
            'of a simulation. It is true but it does not explore the idea.',
            kind=kind)

    if kind in ('function_probe', 'generic'):
        return _verdict(
            'simulation', 'off_topic',
            'The generic quadratic probe is drawn, which is only honest when the concept is a '
            'quantity as a function of one variable. It says nothing about this concept.',
            kind=kind)

    wanted = concept_terms(concept)
    said = _terms(_artifact_text(payload))
    shared = sorted(wanted & said)
    if wanted and not shared:
        return _verdict(
            'simulation', 'off_topic',
            f'The figure never names the concept: none of {sorted(wanted)} appears in its title, '
            'objective, notes or steps, so it is describing a different idea.',
            kind=kind, concept_terms=sorted(wanted))

    if not payload.get('parameters') and not payload.get('series'):
        return _verdict(
            'simulation', 'broken',
            'The figure has neither controls nor a sampled curve, so there is nothing for a '
            'learner to manipulate or read.', kind=kind)

    return _verdict('simulation', 'ok',
                    f'The figure is about this concept: it uses {shared or "its own vocabulary"}.',
                    kind=kind, shared_terms=shared)


def review_video(card: Mapping[str, Any]) -> dict:
    """A verified candidate is usable as an embed; an unverified one is a link only."""
    if not card:
        return _verdict('video', 'missing', 'No video was supplied.')
    if card.get('verified'):
        return _verdict('video', 'ok',
                        f'Embeddable per the oEmbed probe ({card.get("channel") or "unknown channel"}).',
                        embed_url=card.get('embed_url'), watch_url=card.get('watch_url'))
    return _verdict('video', 'unverified',
                    'The embeddability probe did not pass, so this is a plain outbound link: '
                    f'{card.get("verification") or "no reason recorded"}.',
                    watch_url=card.get('watch_url'))


def review_image(entry: Mapping[str, Any]) -> dict:
    """Photographs must carry a verified licence; a missing one is not usable."""
    if not entry:
        return _verdict('image', 'missing', 'No photograph was supplied.')
    licence = str(entry.get('licence') or entry.get('licence_class') or '').strip()
    if not licence:
        return _verdict('image', 'unverified',
                        'The image has no recorded licence, so it cannot be shown to a learner.')
    return _verdict('image', 'ok', f'Licence recorded as {licence}.', licence=licence)


def sweep(concept: Mapping[str, Any], assets: Mapping[str, Any]) -> dict[str, Any]:
    """Review every asset attached to a concept and summarise the position.

    ``assets`` may contain any of ``simulation`` (a payload), ``video`` (a card) and
    ``image`` (a media entry). Absent keys are not reviewed — "not generated" and
    "generated badly" are different problems and the caller usually knows which it has.

    Two lists, because they call for different behaviour. ``problems`` block the lesson and
    the teacher must be told *before* they reach for the asset. ``downgrades`` can be shown
    as they are — an unverified video is still a working link, a concept map is still true —
    and are reported so the TA can improve them without interrupting anything.
    """
    reviews: list[dict] = []
    if 'simulation' in assets:
        reviews.append(review_simulation(concept, assets['simulation']))
    if 'video' in assets:
        reviews.append(review_video(assets['video']))
    if 'image' in assets:
        reviews.append(review_image(assets['image']))
    return {
        'concept_id': str(concept.get('id') or ''),
        'reviews': reviews,
        'problems': [review for review in reviews if not review['usable']],
        'downgrades': [review for review in reviews if review['usable'] and review['verdict'] != 'ok'],
        'clean': all(review['usable'] for review in reviews),
        'all_ok': all(review['verdict'] == 'ok' for review in reviews),
    }


#: What a teacher can put on screen immediately when an asset fails, and what the TA should
#: do about the root cause. Substitution is always something the instance can already do
#: without a network: a concept map for a missing simulation, the watch link for an
#: unverified video. A video search is offered only as an *upgrade*, never as the fallback,
#: because a lesson must not stall on an outbound call.
#:
#: The one exception is a *curated* video: it is already verified and already local, so a
#: broken simulation can hand off to it instead of to a concept map. That is the difference
#: between "the interactive is broken, here is a picture of the ideas" and "the interactive
#: is broken, watch this explain it while the TA rebuilds the interactive" - and the second
#: is what a teacher actually does in a room. ``plan_repair`` applies it only when the caller
#: says a usable curated video exists; without one the concept map stands.
SUBSTITUTES = {
    'simulation': {'off_topic': 'concept_map', 'broken': 'concept_map', 'missing': 'concept_map'},
    'video': {'unverified': 'watch_link', 'missing': 'watch_link'},
    'image': {'unverified': 'drop', 'missing': 'drop'},
}

#: Substitutions that depend on something else already being available, in preference order.
#: Checked before ``SUBSTITUTES``; falling through leaves the plain table in charge.
CONDITIONAL_SUBSTITUTES = {
    'simulation': {'broken': 'video', 'off_topic': 'video'},
}

#: The repair that removes the cause, as opposed to covering for it.
FIXES = {
    'simulation': {'off_topic': 'rebuild_simulation', 'broken': 'rebuild_simulation',
                   'missing': 'build_figure'},
    'video': {'unverified': 'search_videos', 'missing': 'search_videos'},
    'image': {'unverified': 'find_image', 'missing': 'find_image'},
}


def plan_repair(reviews: Sequence[Mapping[str, Any]],
                can_search_video: bool = False,
                video_available: bool = False) -> list[dict[str, Any]]:
    """Turn reviews into an ordered plan the TA can execute.

    Everything that is not ``ok`` is planned, including the verdicts that are still usable.
    A concept map and a plain video link are both shippable, and both are what a TA is for:
    the lesson goes on while the better version is found.

    Each entry names three things separately, because conflating them is what makes an
    in-class repair feel like a stall: ``substitute`` is what the teacher shows *now*,
    ``fix`` is the background job, and ``why`` is the sentence the teacher can say out
    loud without claiming anything untrue.

    ``video_available`` is whether a *usable curated* video is already in hand for this
    concept. When it is, a broken or off-topic simulation hands off to that video rather
    than to a concept map - the substitute is a real explanation of the same idea instead of
    a picture of where it sits. The repair does not change: the TA still rebuilds the
    interactive, because the video is a stand-in, not a replacement.
    """
    plan: list[dict[str, Any]] = []
    for review in reviews:
        verdict = str(review.get('verdict') or '')
        if verdict == 'ok':
            continue
        asset = str(review.get('asset') or '')
        substitute = SUBSTITUTES.get(asset, {}).get(verdict, 'keep')
        if video_available and CONDITIONAL_SUBSTITUTES.get(asset, {}).get(verdict):
            substitute = CONDITIONAL_SUBSTITUTES[asset][verdict]
        fix = FIXES.get(asset, {}).get(verdict, 'none')
        # A video search is only worth planning when the instance can actually reach the
        # network; otherwise it is a job that is guaranteed to refuse.
        if fix == 'search_videos' and not can_search_video:
            fix = 'none'
        plan.append({
            'asset': asset,
            'verdict': verdict,
            'blocking': not review.get('usable'),
            'substitute': substitute,
            'fix': fix,
            'why': review.get('why', ''),
        })
    # Blocking substitutions first: the teacher needs to keep talking before the repair
    # finishes. Within that, the simulation leads because it is the centre of the lesson.
    plan.sort(key=lambda entry: (not entry['blocking'], entry['fix'] == 'none',
                                 entry['asset'] != 'simulation'))
    return plan


def describe(reviews: Iterable[Mapping[str, Any]]) -> str:
    """One sentence for the teacher's feed. Silent when there is nothing to report."""
    reviewed = list(reviews)
    blocking = [review for review in reviewed if not review.get('usable')]
    downgrades = [review for review in reviewed if review['usable'] and review['verdict'] != 'ok']
    if not blocking and not downgrades:
        return ''
    parts = []
    if blocking:
        parts.append('blocking: ' + ', '.join(f"{r['asset']} ({r['verdict']})" for r in blocking))
    if downgrades:
        parts.append('usable but improvable: ' +
                     ', '.join(f"{r['asset']} ({r['verdict']})" for r in downgrades))
    return 'Asset review — ' + '; '.join(parts) + '.'


__all__ = ['VERDICTS', 'USABLE', 'GENERIC_TERMS', 'concept_terms', 'review_simulation',
           'review_video', 'review_image', 'sweep', 'plan_repair', 'describe',
           'SUBSTITUTES', 'FIXES']
