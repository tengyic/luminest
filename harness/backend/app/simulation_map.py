"""Concept to simulation mapping, with the rights position and the evidentiary limit.

The harness can build a *mathematical* simulation for a mathematics concept, because the
symbolic engine can evaluate it. For physics, chemistry, biology and earth science there is
nothing to evaluate: a concept map is honest but it is not an experiment. This module fills
that gap by mapping concepts onto real external simulations, and it is careful about three
things that are easy to get wrong.

**An embedded simulation is not evidence.** The research behind this module found that the
free CC BY-NC PhET simulations expose no telemetry interface, and PhET's interoperable
event stream (PhET-iO) is separately licensed. A third-party page therefore cannot observe
what a learner did inside a simulation. So a simulation card is marked
``observable: false`` and the harness's evidence-based loop is told, in the prompt, not to
treat time spent in a simulated environment as an attempt. Without this the loop would be
free to infer mastery from a resource it cannot see, which is exactly the kind of confident
fabrication the rest of this system exists to prevent.

**A slug is a claim until it is checked.** PhET slugs are taken verbatim from PhET's own
browse pages, and every slug is then re-verified over HTTP at runtime with a TTL cache. An
invented slug would present a dead iframe to a learner under a heading that promises an
experiment, and an invented slug is the single most likely way for a mapping like this to go
wrong. Verification is not optional and a failed slug is withheld with its reason.

**Gizmos is deep-link only.** It is proprietary and licensed per seat, its pass codes are
non-shareable, and it returns 403 to non-browser clients. The operator has their own
subscription, so the correct integration is a deep link into their own signed-in session -
never an embed, never a proxy, never a scrape.
"""

from __future__ import annotations

import json
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import httpx

USER_AGENT = ('LuminfestLearningHarness/1.0 (educational, offline-first; '
              'local single-learner instance)')

PACK = Path(__file__).resolve().parent / 'media_packs' / 'simulations.json'

#: Where a Gizmos card sends a learner when the specific Gizmo's id could not be resolved.
#: The catalogue root, because a per-resource URL with an unresolved id is a 404 presented
#: as a working link.
GIZMOS_CATALOGUE = 'https://gizmos.explorelearning.com/find-gizmos/topic'

#: How long a slug verification is trusted.
VERIFY_TTL_SECONDS = 30 * 24 * 3600

#: Content words too common to prove a concept match.
_STOPWORDS = frozenset({
    'the', 'and', 'for', 'with', 'from', 'into', 'that', 'this', 'are', 'was', 'has',
    'its', 'their', 'how', 'why', 'what', 'when', 'where', 'using', 'use', 'used',
    'basics', 'intro', 'introduction', 'explore', 'exploring', 'model', 'models',
})


@lru_cache(maxsize=1)
def pack() -> dict[str, Any]:
    """The frozen mapping. Cached: it is read on every lesson and never changes at runtime."""
    return json.loads(PACK.read_text(encoding='utf-8'))


def providers() -> dict[str, Any]:
    return dict(pack().get('providers') or {})


def mappings() -> list[dict[str, Any]]:
    return list(pack().get('mappings') or [])


def uncovered() -> list[dict[str, Any]]:
    """Concepts the research could not map to any credible simulation.

    Published rather than hidden. A gap list is what turns "we support simulations" into a
    statement a reviewer can check.
    """
    return list(pack().get('uncovered') or [])


# --------------------------------------------------------------------- verification

def _verification_cache_path(settings) -> Path:
    return Path(settings.data_dir) / 'media' / 'simulation_verification.json'


def _load_cache(settings) -> dict[str, Any]:
    path = _verification_cache_path(settings)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def verify_slug(settings, slug: str, *, use_cache: bool = True) -> dict[str, Any]:
    """Check that a PhET simulation URL actually resolves, with a TTL cache.

    The probe is a GET of the embed URL the lesson would use, not a HEAD of the landing
    page, because the thing being asserted is that *the iframe target resolves*.
    """
    url = providers()['phet']['embed_url_pattern'].format(slug=slug)
    cache = _load_cache(settings)
    now = time.time()
    entry = cache.get(slug)
    if use_cache and isinstance(entry, Mapping) and \
            now - float(entry.get('checked_at') or 0) < VERIFY_TTL_SECONDS:
        return {**entry, 'cached': True, 'url': url}
    result: dict[str, Any] = {'slug': slug, 'url': url, 'checked_at': now, 'cached': False}
    timeout = float(getattr(settings, 'media_timeout', 12.0) or 12.0)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, trust_env=False,
                          headers={'User-Agent': USER_AGENT}) as client:
            response = client.get(url)
            result['status'] = response.status_code
            result['resolves'] = response.status_code == 200
    except (httpx.HTTPError, ValueError) as exc:
        # Unreachable is not verified. With no network the slug is withheld rather than
        # embedded on an assumption, which keeps the offline build honest.
        result.update({'status': None, 'resolves': False,
                       'method': f'unreachable:{type(exc).__name__}'})
    cache[slug] = result
    path = _verification_cache_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(json.dumps(cache, indent=2), encoding='utf-8')
    except OSError:
        pass
    return result


def verify_all(settings, *, limit: int = 200) -> dict[str, Any]:
    """Re-probe every distinct slug. The operator-facing maintenance action."""
    slugs = sorted({str(m['sim_slug_or_id']) for m in mappings() if m['provider'] == 'phet'})
    alive, dead = [], []
    for slug in slugs[:limit]:
        probe = verify_slug(settings, slug, use_cache=False)
        (alive if probe.get('resolves') else dead).append(slug)
    return {'checked': len(slugs[:limit]), 'resolving': len(alive), 'not_resolving': dead,
            'note': 'A slug that does not resolve is withheld from the lesson with its '
                    'reason rather than embedded.'}


# --------------------------------------------------------------------- matching

def _tokens(text: str) -> set[str]:
    """Content words, with a light plural fold.

    The fold is a morphological normaliser, not a vocabulary: it strips a trailing plural so
    "electron" and "electrons" are the same token. Without it a mapping whose label reads
    "Build atoms: protons/neutrons/electrons" cannot match a curriculum concept that says
    "electron configuration", because no token is identical - the pack and the curriculum
    simply inflect differently. The stopword set below is a closed function-word list, not a
    topical one; no subject vocabulary is hardcoded anywhere in this module.
    """
    import re
    words = re.split(r'[^a-z0-9]+', (text or '').casefold())
    out: set[str] = set()
    for word in words:
        if len(word) <= 2 or word in _STOPWORDS:
            continue
        if len(word) > 4 and word.endswith('ies'):
            word = word[:-3] + 'y'
        elif len(word) > 4 and word.endswith('es') and word[:-2] not in _STOPWORDS:
            word = word[:-2]
        elif len(word) > 3 and word.endswith('s') and not word.endswith('ss'):
            word = word[:-1]
        if len(word) > 2 and word not in _STOPWORDS:
            out.add(word)
    return out


def _affinity(a: str, b: str) -> float:
    """How much of the shorter phrase is covered by the longer one.

    The overlap coefficient rather than the Jaccard index, because the two sides are not
    comparable in length: a curriculum concept is a terse phrase and a mapping label is a
    descriptive one. Jaccard punishes that length difference so hard that a correct mapping
    scores near zero, which would leave every concept looking uncovered while the mapping
    sat right there in the pack.
    """
    left, right = _tokens(a), _tokens(b)
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def match(course_id: str, concept: str, *, limit: int = 4,
          threshold: float = 0.34) -> list[dict[str, Any]]:
    """The best simulation mappings for a concept.

    Scored on the mapping's concept label, its simulation title and - at a discount - its
    unit, because all three are real signals: a unit called "Atomic structure" is evidence
    even when the concept phrasing differs from the sim's own blurb.

    A threshold rather than "top N always". Handing a learner the least-bad simulation for a
    concept that no simulation covers is worse than admitting the gap, so a weak match
    returns nothing and :func:`for_concept` reports the gap instead.

    The unit is a *tie-breaker only*. An earlier version let it count at full weight, and
    "torque and angular momentum" then matched a collision simulation on the strength of
    sharing a unit - the exact least-bad-match failure this threshold exists to prevent. A
    match must be earned on the concept label or the simulation's own title; the unit can
    only order two matches that are already earned.
    """
    rows = [m for m in mappings() if m['course_id'] == course_id]
    scored: list[tuple[float, Mapping[str, Any]]] = []
    for row in rows:
        earned = max(_affinity(concept or '', str(row.get('concept') or '')),
                     _affinity(concept or '', str(row.get('sim_title') or '')))
        if earned < threshold:
            continue
        bonus = 0.15 * _affinity(concept or '', str(row.get('unit') or ''))
        scored.append((earned + bonus, row))
    scored.sort(key=lambda pair: (-pair[0], str(pair[1].get('sim_title'))))
    return [{**row, 'match_score': round(score, 3)} for score, row in scored[:limit]]


# --------------------------------------------------------------------- presentation

def _card(item: Mapping[str, Any], provider_meta: Mapping[str, Any], *,
          commercial: bool, verified: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """One launchable simulation card, with its rights position and its evidentiary limit."""
    provider = str(item.get('provider') or '')
    meta = provider_meta.get(provider) or {}
    card: dict[str, Any] = {
        'kind': 'simulation',
        'provider': provider,
        'title': item.get('sim_title') or '',
        'concept': item.get('concept') or '',
        'unit': item.get('unit') or '',
        'why_this_sim': item.get('why') or '',
        'licence': item.get('license') or '',
        'attribution': meta.get('attribution') or '',
        'integration_mode': item.get('integration_mode') or '',
        'confidence': item.get('confidence') or '',
        'match_score': item.get('match_score'),
        # The honest limit. The harness decides from evidence; a simulation it cannot
        # observe is a resource, not an observation.
        'observable': False,
        'telemetry_note': (
            'This simulation reports nothing back to the harness. Free PhET simulations '
            'expose no telemetry interface and PhET-iO is separately licensed, so time '
            'spent here is not an attempt and must not be treated as evidence of mastery.'),
    }
    if provider == 'phet':
        if commercial:
            card.update({
                'status': 'withheld',
                'launch_url': '',
                'withheld_reason': (
                    'PhET simulations are CC BY-NC 4.0 and PhET requires a commercial '
                    'licence from the University of Colorado Boulder for paid or '
                    'subscription products. This instance is configured as a paid offering.'),
            })
            return card
        slug = str(item.get('sim_slug_or_id') or '')
        if verified is not None and not verified.get('resolves'):
            card.update({
                'status': 'withheld',
                'launch_url': '',
                'withheld_reason': (
                    f'The simulation URL did not resolve when checked '
                    f'(status {verified.get("status")!r}). A dead iframe under a heading '
                    f'that promises an experiment is worse than no simulation.'),
            })
            return card
        card.update({
            'status': 'ready',
            'launch_url': meta['embed_url_pattern'].format(slug=slug),
            'public_url': meta['public_url_pattern'].format(slug=slug),
            'slug': slug,
            'embed_allowed': True,
            'open_mode': 'embed_in_lesson',
        })
        return card
    # Gizmos: licensed per seat, no embed, no scrape, no proxy. A deep link into the
    # operator's own signed-in session is the only permitted integration.
    public = str(item.get('public_url') or '')
    resolvable = bool(public) and '<resolve>' not in public
    card.update({
        'status': 'ready',
        # The catalogue root, not the URL pattern with an unresolved placeholder. Shipping a
        # '<resolve>' into a learner's browser would produce a 404 dressed as a launch.
        'launch_url': public if resolvable else GIZMOS_CATALOGUE,
        'open_mode': 'open_in_browser_signed_in',
        'link_verified': resolvable,
        'gizmo_title_search': item.get('sim_slug_or_id') or '',
        'embed_allowed': False,
        'note': ('Gizmos is proprietary and licensed per seat, so this opens in your own '
                 'signed-in session rather than embedding. Search the catalogue for the '
                 'title above.'),
    })
    if resolvable:
        card['public_url'] = public
    return card


def for_concept(settings, course_id: str, concept: str, *, commercial: bool | None = None,
                verify_remote: bool = True, limit: int = 4) -> dict[str, Any]:
    """Every simulation worth offering for one concept, plus the gap if there is none."""
    if commercial is None:
        commercial = bool(getattr(settings, 'commercial_use', False))
    meta = providers()
    hits = match(course_id, concept, limit=limit)
    cards: list[dict[str, Any]] = []
    for item in hits:
        probe = None
        if verify_remote and item.get('provider') == 'phet' and not commercial:
            probe = verify_slug(settings, str(item.get('sim_slug_or_id') or ''))
        cards.append(_card(item, meta, commercial=commercial, verified=probe))
    payload: dict[str, Any] = {
        'course_id': course_id, 'concept': concept, 'simulations': cards,
        'observable': False,
        'notes': [
            'A simulation is a resource the harness cannot observe. It is offered so a '
            'learner can experiment; it is not scored and it is not evidence.',
            'PhET launches are embeds of PhET\'s own hosted simulation. Gizmos launches open '
            'in the learner\'s own signed-in session.',
        ],
    }
    if not cards:
        payload['gap'] = _gap_note(course_id, concept)
    return payload


def _gap_note(course_id: str, concept: str) -> str:
    """What to say when no simulation matches. Named, not silent."""
    for row in uncovered():
        if row.get('course_id') == course_id and _affinity(concept, str(row.get('concept'))) >= 0.25:
            return str(row.get('note') or 'No simulation covers this concept.')
    return (f'No verified simulation covers {concept!r} in this course. The research '
            f'published alongside this mapping found no credible PhET or Gizmos match for '
            f'it, so none is offered rather than the least-bad one.')


def for_course(settings, course_id: str, *, commercial: bool | None = None,
               verify_remote: bool = False) -> dict[str, Any]:
    """The whole course's simulation map, grouped by unit, with coverage accounting."""
    if commercial is None:
        commercial = bool(getattr(settings, 'commercial_use', False))
    meta = providers()
    rows = [m for m in mappings() if m['course_id'] == course_id]
    units: dict[str, list[dict[str, Any]]] = {}
    for item in rows:
        probe = None
        if verify_remote and item.get('provider') == 'phet' and not commercial:
            probe = verify_slug(settings, str(item.get('sim_slug_or_id') or ''))
        units.setdefault(str(item.get('unit') or 'Uncategorised'), []).append(
            _card(item, meta, commercial=commercial, verified=probe))
    gaps = [row for row in uncovered() if row.get('course_id') == course_id]
    return {
        'course_id': course_id,
        'units': [{'unit': unit, 'simulations': cards}
                  for unit, cards in sorted(units.items())],
        'mapped': len(rows),
        'providers': sorted({m['provider'] for m in rows}),
        'uncovered': gaps,
        'observable': False,
        'verification': ('Slugs are verified over HTTP on demand; this listing is from the '
                         'frozen pack and reports what the pack claims, not what has just '
                         'been probed.'),
    }


def coverage() -> dict[str, Any]:
    """How much of the mapped catalogue has a simulation, per course.

    Also compares the *declared* provider preference per course against the providers that
    actually contributed a mapping. A course that declares Gizmos but has no Gizmos row is
    a real shortfall, and one that is invisible if only the mapped totals are reported --
    a declared order reads like coverage. Publishing the shortfall is what makes the
    difference between "we support Gizmos" and "we said we would".
    """
    from .ingest import policy  # local: keeps the policy package off this module's import path

    by_course: dict[str, int] = {}
    per_course_providers: dict[str, set[str]] = {}
    for item in mappings():
        course_id = item['course_id']
        by_course[course_id] = by_course.get(course_id, 0) + 1
        per_course_providers.setdefault(course_id, set()).add(str(item.get('provider') or ''))

    gaps: dict[str, int] = {}
    for row in uncovered():
        gaps[row['course_id']] = gaps.get(row['course_id'], 0) + 1

    declared = getattr(policy, 'COURSE_SIMULATION_PROVIDERS', {}) or {}
    provider_gaps: dict[str, list[str]] = {}
    for course_id, order in declared.items():
        contributed = per_course_providers.get(course_id, set())
        absent = [p for p in order if p not in contributed]
        if absent:
            provider_gaps[course_id] = absent

    return {'mapped_by_course': by_course, 'uncovered_by_course': gaps,
            'providers_by_course': {k: sorted(v) for k, v in sorted(per_course_providers.items())},
            'declared_providers_by_course': {k: list(v) for k, v in sorted(declared.items())},
            'provider_gaps': provider_gaps,
            'total_mapped': len(mappings()), 'total_uncovered': len(uncovered()),
            'pack_generated': pack().get('generated')}


def describe(settings=None) -> dict[str, Any]:
    """The module's posture, for the transparency panel."""
    return {
        'providers': providers(),
        'counts': coverage(),
        'verify_ttl_days': round(VERIFY_TTL_SECONDS / 86400, 1),
        'guarantees': [
            'Every PhET slug is HTTP-verified before it is embedded; a failed slug is '
            'withheld with its reason.',
            'Free PhET simulations expose no telemetry, so a simulation is marked '
            'unobservable and never counted as an attempt.',
            'Gizmos is reached by deep link into the operator\'s own signed-in session; '
            'never embedded, proxied or scraped.',
            'Non-commercial providers are withheld automatically on a paid instance.',
            'Concepts with no credible simulation are published as gaps rather than filled '
            'with the least-bad match.',
        ],
    }
