"""Licence policy for curriculum ingestion.

The harness only ingests concept *structure* (titles, classification, prerequisite
order) from sources whose licence permits reuse. Restricted sources stay link-only:
we record that they exist, we never copy their text, and we never train on them.

This module is the single gate. Every ingestion source declares a
:class:`SourcePolicy`; :func:`assert_ingestible` refuses anything that is not
explicitly cleared. There is no *code* override flag on purpose - adding a source
means adding an evidence-backed policy entry, which is a reviewable change. What an
operator *may* do without a code change is supply a signed, evidence-backed
licence-override file (see :func:`load_overrides`): it is data, it is audited, it
defaults to absent, and it can never widen a ``PROHIBITED`` source.
"""

from __future__ import annotations

import json
import os
import re
import warnings
from dataclasses import asdict, dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

#: Environment variable holding the path to an owner-signed licence-override file.
#: Absent by default: with no file, every policy behaves exactly as declared in code.
OVERRIDE_ENV_VAR = 'LUMINFEST_LICENSE_OVERRIDES'

#: Schema accepted by :func:`load_overrides`. Bumped when the record shape changes.
OVERRIDE_SCHEMA = 'license_override/1'

#: Classes an override may *never* target (matched by enum value; ``LicenceClass``
#: is a ``str`` enum). A rights position the terms forbid outright is not the
#: operator's to widen: only the rights-holder can lift a prohibition.
NON_OVERRIDABLE = frozenset({'prohibited'})

_override_cache: dict[str, dict[str, Any]] | None = None


class LicenceClass(str, Enum):
    """How a source may be used. Ordered from most to least permissive."""

    #: No copyright (e.g. US federal government works). Safe for any reuse.
    PUBLIC_DOMAIN = 'public_domain'
    #: CC0 / equivalent dedication. Safe for any reuse, attribution optional.
    CC0 = 'cc0'
    #: Attribution required. Reuse and derivative works permitted.
    CC_BY = 'cc_by'
    #: Attribution + share-alike required on derivative works.
    CC_BY_SA = 'cc_by_sa'
    #: Attribution + non-commercial. We may display and link, but must not treat the
    #: asset as a redistributable project asset: NC forbids commercial reuse, and this
    #: application may be sold. Assets under this class are served from the provider,
    #: never copied into the build or into a learner export.
    CC_BY_NC = 'cc_by_nc'
    #: Non-commercial + share-alike.
    CC_BY_NC_SA = 'cc_by_nc_sa'
    #: No derivatives. We may display the asset unaltered and attribute it, and nothing more.
    CC_BY_ND = 'cc_by_nd'
    #: We may embed the provider's *own* player and name the work, and may not download,
    #: re-host, re-encode, transcribe or extract from it. The provider serves every byte,
    #: so nothing is reproduced by this application.
    EMBED_ONLY = 'embed_only'
    #: We may link to it and name it, but must not copy or ingest its content.
    LINK_ONLY = 'link_only'
    #: Explicitly forbidden (terms prohibit scraping / AI extraction).
    PROHIBITED = 'prohibited'


#: Classes that may be ingested into the knowledge graph.
INGESTIBLE = frozenset({LicenceClass.PUBLIC_DOMAIN, LicenceClass.CC0,
                        LicenceClass.CC_BY, LicenceClass.CC_BY_SA})

#: Classes that require the attribution string to be carried into node provenance.
REQUIRES_ATTRIBUTION = frozenset({LicenceClass.CC_BY, LicenceClass.CC_BY_SA,
                                  LicenceClass.CC_BY_NC, LicenceClass.CC_BY_NC_SA,
                                  LicenceClass.CC_BY_ND, LicenceClass.EMBED_ONLY})

#: Classes whose asset may be shown to a learner **because the provider serves it**.
#: ``EMBED_ONLY`` means an iframe pointed at the rights-holder's own player; it never
#: means a downloaded file, because a download is a reproduction and an embed is not.
EMBEDDABLE = frozenset({LicenceClass.EMBED_ONLY})

#: Classes whose asset may be copied into this project's own cache and shown offline.
#: Deliberately excludes every NC class and every ND class. A cache is a copy, and a
#: copy is exactly what a non-commercial or no-derivatives licence restricts.
LOCALLY_STORABLE = frozenset({LicenceClass.PUBLIC_DOMAIN, LicenceClass.CC0,
                              LicenceClass.CC_BY, LicenceClass.CC_BY_SA})

#: Licence codes as third-party APIs spell them, mapped onto this project's classes.
#: Both Openverse and Wikimedia Commons report a short code; neither is trusted to be
#: free of a code this project has not decided about, which is why an unknown code is
#: refused rather than defaulted to permissive.
LICENCE_CODES = {
    'cc0': LicenceClass.CC0, 'cc-zero': LicenceClass.CC0, 'cc0-1.0': LicenceClass.CC0,
    'pdm': LicenceClass.PUBLIC_DOMAIN, 'pd': LicenceClass.PUBLIC_DOMAIN,
    'publicdomain': LicenceClass.PUBLIC_DOMAIN, 'public-domain': LicenceClass.PUBLIC_DOMAIN,
    'cc-pd': LicenceClass.PUBLIC_DOMAIN, 'no-known-copyright': LicenceClass.PUBLIC_DOMAIN,
    'by': LicenceClass.CC_BY, 'cc-by': LicenceClass.CC_BY,
    'by-sa': LicenceClass.CC_BY_SA, 'cc-by-sa': LicenceClass.CC_BY_SA,
    'by-nc': LicenceClass.CC_BY_NC, 'cc-by-nc': LicenceClass.CC_BY_NC,
    'by-nc-sa': LicenceClass.CC_BY_NC_SA, 'cc-by-nc-sa': LicenceClass.CC_BY_NC_SA,
    'by-nd': LicenceClass.CC_BY_ND, 'cc-by-nd': LicenceClass.CC_BY_ND,
    'by-nc-nd': LicenceClass.CC_BY_ND, 'cc-by-nc-nd': LicenceClass.CC_BY_ND,
}


@dataclass(frozen=True)
class SourcePolicy:
    """The declared rights position for one ingestion source."""

    name: str
    url: str
    licence: str
    licence_class: LicenceClass
    scope: str
    attribution: str = ''
    evidence_id: str = ''
    #: Whether the licence tolerates use inside a paid offering. A non-commercial licence
    #: is defined by the *use*, not the user: incorporating NC content into a product the
    #: operator sells is not non-commercial, so the operator's own declaration of whether
    #: this instance is commercial is a hard gate rather than a disclaimer.
    commercial_ok: bool = True
    #: Text that must be displayed verbatim when the source is used, distinct from the
    #: per-asset credit. Khan Academy requires an exact notice, so it is stored as data
    #: rather than retyped at each call site where it could drift.
    attribution_notice: str = ''
    #: Whether the rights-holder may withdraw permission at any time. When set, the
    #: integration must be switchable off without a code change, so a revocation is a data
    #: edit rather than a release.
    revocable: bool = False

    @property
    def ingestible(self) -> bool:
        return self.licence_class in INGESTIBLE

    @property
    def needs_attribution(self) -> bool:
        return self.licence_class in REQUIRES_ATTRIBUTION

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload['licence_class'] = self.licence_class.value
        payload['ingestible'] = self.ingestible
        return payload


class IngestionRefused(RuntimeError):
    """Raised when a source is not cleared for ingestion."""


def assert_ingestible(policy: SourcePolicy) -> None:
    """Refuse ingestion for any source that is not explicitly cleared."""
    policy = apply_overrides(policy)
    if not policy.ingestible:
        raise IngestionRefused(
            f'{policy.name!r} is {policy.licence_class.value} and must stay link-only. '
            f'Declared licence: {policy.licence}. Scope: {policy.scope}')


class AssetRefused(RuntimeError):
    """Raised when a *media asset* may not be used the way the caller intends.

    Separate from :class:`IngestionRefused` on purpose. Copying text into the graph and
    displaying a provider-hosted player are different acts with different rights
    positions, and collapsing them into one exception is how a policy gate quietly stops
    describing what it actually checked.
    """


def classify_code(code: str) -> LicenceClass | None:
    """Map a third-party licence code onto a class, or ``None`` if undecided.

    ``None`` is the important return value. An API that starts emitting a code this
    project has never ruled on must not be silently treated as permissive, so the caller
    receives "unknown" and the asset is dropped with a reason.
    """
    return LICENCE_CODES.get((code or '').strip().casefold().lstrip('creativecommons-'))


def classify_licence(value: str) -> LicenceClass | None:
    """Best-effort classification of a licence *name* such as ``CC BY-SA 4.0``.

    Handles the shapes the image APIs actually emit: a bare code (``by``), a hyphenated code
    with a version (``cc-by-sa-4.0``), a display name (``CC BY-SA 4.0``), the spelled-out
    form (``Creative Commons Attribution-ShareAlike 4.0``) and the Wikimedia ``License``
    field. Version digits are dropped before lookup so a move from 4.0 to 5.0 does not
    silently unclassify a source.

    Anything unrecognised returns ``None``. That is the point of the function: a licence the
    project has never ruled on must not be rounded to the nearest permissive one.
    """
    text = ' '.join((value or '').split()).casefold()
    if not text:
        return None
    direct = classify_code(text)
    if direct is not None:
        return direct
    if 'public domain' in text or re.search(r'\bpdm\b', text):
        return LicenceClass.PUBLIC_DOMAIN
    if re.search(r'\bcc0\b|\bcc-zero\b', text):
        return LicenceClass.CC0

    # Reduce every spelling to the same element tokens. This is the step an earlier version of
    # this function got wrong: it prefixed "by" onto whatever it had reduced, so "CC BY-SA 4.0"
    # became "by-by-sa" and classified as unknown - a permissive licence silently downgraded to
    # unclassifiable, which fails closed but for the wrong reason and would have disabled
    # every CC BY work in the catalogue.
    work = text
    for word, token in (('attribution', ' by '), ('sharealike', ' sa '), ('share-alike', ' sa '),
                        ('share alike', ' sa '), ('noncommercial', ' nc '),
                        ('non-commercial', ' nc '), ('noderivatives', ' nd '),
                        ('no-derivatives', ' nd '), ('no derivatives', ' nd ')):
        work = work.replace(word, token)
    work = re.sub(r'creative\s+commons', ' ', work)
    work = re.sub(r'\b\d+(\.\d+)*\b', ' ', work)

    element = {'by', 'sa', 'nc', 'nd'}
    filler = {'cc', 'cc0', 'universal', 'unported', 'international', 'generic', 'licence',
              'license', 'public', 'domain'}
    parts: list[str] = []
    for token in re.split(r'[^a-z]+', work):
        if token in element and token not in parts:
            parts.append(token)
        elif token and token not in filler and token not in element:
            # An unexpected word means this is not a Creative Commons licence shape at all.
            return None
    if not parts:
        return None
    # "SA 4.0" and "NC 4.0" are not licences on their own; the CC family always carries BY.
    if parts[0] != 'by':
        parts.insert(0, 'by')
    return classify_code('-'.join(parts))


def reset_override_cache() -> None:
    """Forget the cached override file. Test and operator reload hook."""
    global _override_cache
    _override_cache = None


def _declared_policy(name: str) -> SourcePolicy | None:
    """The code-declared policy for ``name``, or ``None`` if no such source exists.

    Resolved lazily via ``globals()`` because the source collections are defined later
    in the file than the override machinery, but always before any call.
    """
    for collection in (globals().get('WIKIDATA'), globals().get('OPERATOR_SCOPE_SEQUENCE'),
                       *globals().get('TEXTBOOK_SOURCES', ()),
                       *globals().get('RESTRICTED', ()),
                       *globals().get('MEDIA_SOURCES', ())):
        if collection is not None and collection.name == name:
            return collection
    return None


def load_overrides() -> dict[str, dict[str, Any]]:
    """Load owner-signed licence overrides, keyed by policy name. Default: empty.

    The file (path in ``LUMINFEST_LICENSE_OVERRIDES``) is **data, not code**: widening a
    rights position is an operator decision that must carry its own evidence, approver
    and approval date, so the audit trail lives in the file rather than in a git diff.

    Fail-closed rules, in order of importance:

    * no file / unreadable file / invalid schema  ->  empty dict, warning emitted.
      A broken override mechanism must never widen a rights position by accident.
    * an override naming an unknown policy         ->  dropped. It would otherwise grant
      a phantom clearance to a typo or a renamed source.
    * an override targeting a ``PROHIBITED`` source ->  dropped. Only the rights-holder
      can lift a prohibition; an operator cannot sign that decision for them.
    * an unknown target ``licence_class``          ->  that record dropped.

    A valid record looks like::

        {"schema": "license_override/1", "overrides": [{
            "policy_name": "OpenStax Elementary Algebra 2e",
            "licence_class": "cc_by",
            "scope": "Attribution-preserving quotation only; no wholesale ingestion",
            "evidence_url": "https://openstax.org/license",
            "approved_by": "operator name", "approved_at": "2026-10-11"}]}
    """
    global _override_cache
    if _override_cache is not None:
        return _override_cache
    loaded: dict[str, dict[str, Any]] = {}
    path = os.environ.get(OVERRIDE_ENV_VAR, '')
    if path:
        try:
            data = json.loads(Path(path).read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            warnings.warn(f'{OVERRIDE_ENV_VAR} file unreadable; overrides ignored: {exc}')
            data = None
        if isinstance(data, dict) and data.get('schema') == OVERRIDE_SCHEMA:
            for record in data.get('overrides') or []:
                if not isinstance(record, dict):
                    continue
                name = str(record.get('policy_name') or '')
                target = str(record.get('licence_class') or '')
                if not name or not target:
                    continue
                declared = _declared_policy(name)
                if declared is None:
                    warnings.warn(f'licence override names unknown policy {name!r}; dropped '
                                  f'(a renamed or typoed source gets no phantom clearance)')
                    continue
                if declared.licence_class.value in NON_OVERRIDABLE:
                    warnings.warn(f'licence override for {name!r} targets a {declared.licence_class.value} '
                                  f'source; a prohibited source is never operator-overridable; dropped')
                    continue
                try:
                    klass = LicenceClass(target)
                except ValueError:
                    warnings.warn(f'licence override for {name!r}: unknown class {target!r}; dropped')
                    continue
                if klass.value in NON_OVERRIDABLE:
                    warnings.warn(f'licence override for {name!r} targets {klass.value}; '
                                  f'a prohibited source is never operator-overridable; dropped')
                    continue
                approved_by = str(record.get('approved_by') or '')
                approved_at = str(record.get('approved_at') or '')
                if not approved_by or not approved_at:
                    warnings.warn(f'licence override for {name!r} lacks approved_by/approved_at; dropped')
                    continue
                record['licence_class'] = klass.value
                loaded[name] = record
        elif data is not None:
            warnings.warn(f'{OVERRIDE_ENV_VAR} file has wrong schema; overrides ignored')
    _override_cache = loaded
    return _override_cache


def override_for(name: str) -> dict[str, Any] | None:
    """The override record for one policy name, if the operator supplied a valid one."""
    return load_overrides().get(name)


def apply_overrides(policy: SourcePolicy) -> SourcePolicy:
    """Return ``policy`` with the operator's signed override applied, or unchanged.

    The override replaces the *declaration* (class, licence text, scope, evidence) - it
    never touches the classification functions: an unknown licence code still refuses,
    and every other gate in this module keeps operating on the class it is given.
    """
    record = override_for(policy.name)
    if record is None or policy.licence_class.value in NON_OVERRIDABLE:
        return policy
    try:
        klass = LicenceClass(record['licence_class'])
    except ValueError:
        return policy
    if klass is policy.licence_class:
        return policy
    commercial_ok = bool(record.get('commercial_ok', klass not in
                                    (LicenceClass.CC_BY_NC, LicenceClass.CC_BY_NC_SA,
                                     LicenceClass.CC_BY_ND)))
    return replace(policy,
                   licence_class=klass,
                   licence=str(record.get('licence') or
                               f'Operator-approved override: {klass.value}'),
                   scope=str(record.get('scope') or policy.scope),
                   evidence_id=f'operator_override:{policy.evidence_id or policy.name}',
                   commercial_ok=commercial_ok,
                   attribution_notice=str(record.get('attribution_notice') or
                                          policy.attribution_notice))


def require_locally_storable(code: str, label: str) -> LicenceClass:
    """Allow a *downloaded* asset only when its licence permits redistribution."""
    klass = classify_licence(code)
    if klass is None:
        raise AssetRefused(
            f'{label}: unrecognised licence {code!r}. This project only copies an asset '
            f'whose licence it has explicitly classified; an unknown code is not treated '
            f'as permissive.')
    if klass not in LOCALLY_STORABLE:
        raise AssetRefused(
            f'{label}: licence {code!r} classifies as {klass.value}, which does not permit '
            f'this project to store or redistribute a copy. NC restricts commercial reuse and '
            f'ND forbids derivative works; neither is compatible with caching an asset into '
            f'a build that may be sold.')
    return klass


def require_embeddable(entry: SourcePolicy, label: str) -> None:
    """Allow an *embedded* asset (provider-hosted player) under an embed-only policy."""
    if entry.licence_class not in EMBEDDABLE and not entry.needs_attribution:
        raise AssetRefused(
            f'{label}: {entry.name!r} is {entry.licence_class.value}; embedding is not cleared.')


def require_commercial(entry: SourcePolicy, commercial: bool, label: str) -> None:
    """Refuse an NC source when the operator has declared this a paid offering.

    This is the gate that makes the NC clause real. Khan Academy's own guidance is that
    incorporating their content into a paid offering is not non-commercial use, so a
    product that decides to charge has to lose that source - and it must lose it by
    evaluation here rather than by somebody remembering to delete an entry.
    """
    if commercial and not entry.commercial_ok:
        raise AssetRefused(
            f'{label}: {entry.name!r} is non-commercial '
            f'({entry.licence_class.value}) but this instance is configured as a paid '
            f'offering. Non-commercial is decided by the use, not the user.')


def video_reference(course_id: str, *, commercial: bool = False) -> list[dict[str, Any]]:
    """The video hub cards for a course, with the rights position attached.

    A hub is a *destination*, not a playlist: this project cannot enumerate a provider's
    catalogue without scraping it, so the card names the hub and the licence rather than
    pretending to offer a curated lecture list it has not verified.
    """
    cards: list[dict[str, Any]] = []
    for source in COURSE_VIDEO_HUBS.get(course_id, ()):
        allowed = source.commercial_ok or not commercial
        card: dict[str, Any] = {
            'kind': 'video',
            'title': f'{source.name} — video, opens in the provider\'s player',
            'url': source.url, 'status': 'reference_link' if allowed else 'withheld',
            'integration_mode': 'embed_only' if allowed else 'unavailable',
            'licence': source.licence, 'licence_class': source.licence_class.value,
            'scope': source.scope, 'attribution': source.attribution,
            'revocable': source.revocable,
            'notice': source.attribution_notice,
            'policy_name': source.name,
            'commercial_ok': source.commercial_ok,
        }
        if not allowed:
            card['withheld_reason'] = (
                'Non-commercial licence, and this instance is configured as a paid offering. '
                'Khan Academy\'s guidance is that use inside a paid offering is not '
                'non-commercial use, so the source is withheld rather than silently kept.')
        cards.append(card)
    return cards


def provenance_for(policy: SourcePolicy) -> dict[str, str]:
    """The provenance block stamped onto every node a source contributes."""
    block = {'source': policy.name, 'url': policy.url, 'licence': policy.licence,
             'licence_class': policy.licence_class.value}
    if policy.evidence_id:
        block['evidence_id'] = policy.evidence_id
    if policy.needs_attribution and policy.attribution:
        block['attribution'] = policy.attribution
    return block


#: Rights positions already established by this project. ``evidence_id`` values
#: cross-reference ``harness/evidence.json``.
WIKIDATA = SourcePolicy(
    name='Wikidata',
    url='https://www.wikidata.org/',
    licence='CC0 1.0 Universal (public domain dedication)',
    licence_class=LicenceClass.CC0,
    scope='Concept labels, descriptions, aliases and hierarchy statements. CC0 permits '
          'reuse, redistribution and AI training without restriction.',
    attribution='Wikidata contributors (CC0; attribution not required, recorded as courtesy)',
)

OPERATOR_SCOPE_SEQUENCE = SourcePolicy(
    name='Operator-supplied scope and sequence',
    url='',
    licence='Declared per file; must be public_domain, CC0, CC BY or CC BY-SA',
    licence_class=LicenceClass.CC_BY,
    scope='A course outline supplied by the operator. The file must declare its own licence; '
          'only the outline structure (titles, unit order, prerequisite intent) is ingested.',
)

#: The sources named by the hand-authored mathematics course.
OPENSTAX_ELEMENTARY_ALGEBRA = SourcePolicy(
    name='OpenStax Elementary Algebra 2e',
    url='https://openstax.org/details/books/elementary-algebra-2e',
    licence='Current web notice: CC BY-NC-SA 4.0; AI ingestion/training requires prior written permission',
    licence_class=LicenceClass.LINK_ONLY,
    scope='External link only. No text, exercises, figures or embeddings are copied or ingested.',
    evidence_id='openstax_elementary_algebra_current_rights',
)
OPENSTAX_INTRODUCTORY_STATISTICS = SourcePolicy(
    name='OpenStax Introductory Statistics 2e',
    url='https://openstax.org/details/books/introductory-statistics-2e',
    licence='Exact current artifact rights not independently verified; no CC BY reuse assumption',
    licence_class=LicenceClass.LINK_ONLY,
    scope='External link only pending exact-version clearance.',
    evidence_id='openstax_license_transition',
)
#: The exception the licence transition left behind. OpenStax's own book API reports the
#: *first* edition of Algebra and Trigonometry as Creative Commons Attribution 4.0 (BY only:
#: no NC, no ND), while every current 2e edition reports CC BY-NC-SA 4.0 -- see
#: ``openstax_license_transition`` and ``openstax_elementary_algebra_current_rights`` for the
#: transition and the current NC position. CC BY is an ingestible class, so section text from
#: *this edition* may be fetched, stored with provenance, and quoted with attribution. The
#: fetcher (``app.ingest.sources.openstax``) re-classifies the licence from the publisher's
#: own API at fetch time and refuses to store text whenever the live data stops matching this
#: audited entry, so a rights change on OpenStax's side fails closed rather than sailing
#: through on a stale audit.
OPENSTAX_ALGEBRA_TRIG = SourcePolicy(
    name='OpenStax Algebra and Trigonometry (1e)',
    url='https://openstax.org/details/books/algebra-and-trigonometry',
    licence='Creative Commons Attribution 4.0, as reported by OpenStax\'s book API '
            '(license_name "Creative Commons Attribution License", license_version 4.0). '
            'Verified against the live API on 2026-10-11.',
    licence_class=LicenceClass.CC_BY,
    scope='Section text may be fetched, stored with provenance and quoted with attribution. '
          'The 2e successor books are CC BY-NC-SA 4.0 and remain link-only. OpenStax\'s own '
          'notices additionally prohibit ingesting its content into LLMs or generative-AI '
          'offerings, so a stored section is never sent to a model: the quote is composed '
          'deterministically into a block type the prose-rewriting pass never reads, and '
          'agent-loop tool results pass through generate.redact_textbook_quotes, which '
          'withholds the verbatim text while keeping the citation.',
    attribution='OpenStax Algebra and Trigonometry 1e, Jay Abramson et al., CC BY 4.0. '
                'Section URL and retrieval date are stored and displayed with every quote.',
    evidence_id='openstax_algebra_trig_1e_cc_by',
)
#: The current successor edition, audited in the same run as the 1e so the fetcher can
#: distinguish "audited link-only" (a deliberate rights position, refused with a reason that
#: names it) from "unaudited" (never reviewed at all). Both are refusals; only the wording
#: differs, and the wording is what an operator reads when a fetch withholds.
OPENSTAX_ALGEBRA_TRIG_2E = SourcePolicy(
    name='OpenStax Algebra and Trigonometry 2e',
    url='https://openstax.org/details/books/algebra-and-trigonometry-2e',
    licence='Current web notice and book API: CC BY-NC-SA 4.0; AI ingestion/training requires '
            'prior written permission',
    licence_class=LicenceClass.LINK_ONLY,
    scope='External link only. No text, exercises, figures or embeddings are copied or ingested.',
    evidence_id='openstax_license_transition',
)
KHAN_ACADEMY_TERMS = SourcePolicy(
    name='Khan Academy',
    url='https://www.khanacademy.org/about/tos',
    licence='No reuse or AI-training permission claimed; current guidance prohibits scraping and AI/ML extraction',
    licence_class=LicenceClass.PROHIBITED,
    scope='External link only. No lessons, transcripts, exercises, embeddings, logos or training content.',
    evidence_id='khan_academy_link_only',
)

_AUTHORED_RESTRICTED = (OPENSTAX_ELEMENTARY_ALGEBRA, OPENSTAX_INTRODUCTORY_STATISTICS, KHAN_ACADEMY_TERMS)


def _external_reference(name, url, licence, scope, evidence_id):
    """A link-only reference to material the learner may open elsewhere.

    Link-only is the operative word. These entries exist so a learner has somewhere real to
    read or watch more, and so the tutor has a citable curriculum reference that is not a
    fabrication -- the tutor is explicitly forbidden from claiming it retrieved external
    material. Nothing is fetched, copied, embedded or trained on, which is why every entry
    here is ``LINK_ONLY`` and therefore refused by :func:`assert_ingestible`.
    """
    return SourcePolicy(name=name, url=url, licence=licence, licence_class=LicenceClass.LINK_ONLY,
                        scope=scope, evidence_id=evidence_id)


#: Link-only reference books and hubs for the courses that are not hand-authored mathematics.
#: Every URL was checked to resolve before being added; a dead link would be worse than none.
OPENSTAX_COLLEGE_PHYSICS = _external_reference(
    'OpenStax College Physics 2e', 'https://openstax.org/details/books/college-physics-2e',
    'Current web notice: CC BY-NC-SA 4.0; AI ingestion/training requires prior written permission',
    'External link only. No text, exercises, figures or embeddings are copied or ingested.',
    'openstax_college_physics_current_rights')
OPENSTAX_CHEMISTRY = _external_reference(
    'OpenStax Chemistry 2e', 'https://openstax.org/details/books/chemistry-2e',
    'Current web notice: CC BY-NC-SA 4.0; AI ingestion/training requires prior written permission',
    'External link only. No text, exercises, figures or embeddings are copied or ingested.',
    'openstax_chemistry_current_rights')
OPENSTAX_BIOLOGY = _external_reference(
    'OpenStax Biology 2e', 'https://openstax.org/details/books/biology-2e',
    'Current web notice: CC BY-NC-SA 4.0; AI ingestion/training requires prior written permission',
    'External link only. No text, exercises, figures or embeddings are copied or ingested.',
    'openstax_biology_current_rights')
OPENSTAX_ASTRONOMY = _external_reference(
    'OpenStax Astronomy 2e', 'https://openstax.org/details/books/astronomy-2e',
    'Current web notice: CC BY-NC-SA 4.0; AI ingestion/training requires prior written permission',
    'External link only. No text, exercises, figures or embeddings are copied or ingested.',
    'openstax_astronomy_current_rights')
OPENSTAX_PSYCHOLOGY = _external_reference(
    'OpenStax Psychology 2e', 'https://openstax.org/details/books/psychology-2e',
    'Current web notice: CC BY-NC-SA 4.0; AI ingestion/training requires prior written permission',
    'External link only. No text, exercises, figures or embeddings are copied or ingested.',
    'openstax_psychology_current_rights')
KHAN_SCIENCE = _external_reference(
    'Khan Academy — Science', 'https://www.khanacademy.org/science',
    'No reuse or AI-training permission claimed; current guidance prohibits scraping and AI/ML extraction',
    'External link only. No lessons, transcripts, exercises, embeddings, logos or training content.',
    'khan_academy_link_only')
KHAN_COMPUTING = _external_reference(
    'Khan Academy — Computers and the Internet', 'https://www.khanacademy.org/computing/computers-and-the-internet',
    'No reuse or AI-training permission claimed; current guidance prohibits scraping and AI/ML extraction',
    'External link only. No lessons, transcripts, exercises, embeddings, logos or training content.',
    'khan_academy_link_only')

#: The reference set for the six courses the study harness was asked to ship. Each URL was
#: checked to resolve before being added. Khan Academy's own guidance permits linking while
#: prohibiting scraping and AI extraction, so every entry is a destination rather than a
#: source of content, exactly like the science hubs above.
OPENSTAX_CALCULUS = _external_reference(
    'OpenStax Calculus Volume 1', 'https://openstax.org/details/books/calculus-volume-1',
    'Current web notice: CC BY-NC-SA 4.0; AI ingestion/training requires prior written permission',
    'External link only. No text, exercises, figures or embeddings are copied or ingested.',
    'openstax_calculus_current_rights')
OPENSTAX_PRINCIPLES_ECONOMICS = _external_reference(
    'OpenStax Principles of Economics 3e', 'https://openstax.org/details/books/principles-economics-3e',
    'Creative Commons Attribution 4.0, but the publisher\'s own notice states the book may not '
    'be used in the training of large language models or otherwise ingested into them, so the '
    'operative position here is link-only rather than the CC BY class',
    'External link only. No text, exercises, figures or embeddings are copied, ingested or '
    'used for training, which is the restriction OpenStax states on the book itself.',
    'openstax_principles_economics_llm_restriction')
KHAN_ECONOMICS = _external_reference(
    'Khan Academy — Economics and Finance', 'https://www.khanacademy.org/economics-finance-domain',
    'No reuse or AI-training permission claimed; current guidance prohibits scraping and AI/ML extraction',
    'External link only. No lessons, transcripts, exercises, embeddings, logos or training content.',
    'khan_academy_link_only')
KHAN_ALGEBRA_2 = _external_reference(
    'Khan Academy — Algebra 2', 'https://www.khanacademy.org/math/algebra2',
    'No reuse or AI-training permission claimed; current guidance prohibits scraping and AI/ML extraction',
    'External link only. No lessons, transcripts, exercises, embeddings, logos or training content.',
    'khan_academy_link_only')
KHAN_CALCULUS = _external_reference(
    'Khan Academy — Calculus', 'https://www.khanacademy.org/math/calculus-1',
    'No reuse or AI-training permission claimed; current guidance prohibits scraping and AI/ML extraction',
    'External link only. No lessons, transcripts, exercises, embeddings, logos or training content.',
    'khan_academy_link_only')

#: The economics course's interactive resource. PhET carries no economics simulations, so
#: declaring PhET for an economics learner would send them to a physics catalogue. EconEdLink
#: is the Council for Economic Education's own free interactive economics library, and it is
#: linked, never embedded or copied.
ECONEDLINK = _external_reference(
    'EconEdLink (Council for Economic Education)', 'https://www.econedlink.org/',
    'Site content © Council for Economic Education; free interactive economics lessons and '
    'tools offered for educational use per the site notice',
    'Deep link only. No lesson text, interactives, data, figures or embeddings are copied, '
    'ingested or used for training.',
    'econedlink_link_only')

# ------------------------------------------------------------------- math game sources
#
# Interactive mathematics activities the tutor may *name and link* for a teacher. Every
# entry here is LINK_ONLY: the harness records that the activity exists and where to open
# it, and never copies its content, screenshots its problems into the app, or embeds it
# outside the rights-holder's own terms. Widening any of these to embed_only is a
# separate rights audit, not a code edit (see MediaEmbed.hosts on the Swift side, which
# is independently narrower and stays that way until an audit clears a host).

MATHIGON = _external_reference(
    'Mathigon', 'https://mathigon.org',
    'Site content © Mathigon Ltd; offered free for non-commercial educational use per the site notice',
    'Deep link only. No course text, courseware, Polypad assets or embeddings are copied or ingested.',
    'mathigon_link_only')
DESMOS_CLASSROOM = _external_reference(
    'Desmos Classroom', 'https://teacher.desmos.com',
    'Desmos Terms of Service; activity links are shared freely for classroom use per the site notice',
    'Deep link only. No activity screens, expressions or graphs are copied or ingested.',
    'desmos_classroom_link_only')
NRICH = _external_reference(
    'NRICH (University of Cambridge)', 'https://nrich.maths.org',
    '© University of Cambridge NRICH project; personal and educational use per site notice',
    'Deep link only. No task text, solutions or interactives are copied or ingested.',
    'nrich_link_only')
TRANSUM = _external_reference(
    'Transum Mathematics', 'https://www.transum.org',
    '© Transum Mathematics; free classroom use per site notice',
    'Deep link only. No activity content is copied or ingested.',
    'transum_link_only')
MATH_IS_FUN = _external_reference(
    'MathsIsFun', 'https://www.mathsisfun.com',
    '© MathsIsFun.com; content provided for personal and educational use per site notice',
    'Deep link only. No lesson text or interactives are copied or ingested.',
    'mathsisfun_link_only')

#: The audited game/interactive source list, in one place so ``find_game`` cannot drift
#: from the licence registry the way a hand-rolled list would. Prodigy and Brilliant are
#: deliberately absent: both gate content behind accounts/paywalls, and a resource the
#: learner cannot actually open is worse than an honest named gap.
GAME_SOURCES = (MATHIGON, DESMOS_CLASSROOM, NRICH, TRANSUM, MATH_IS_FUN)

#: The reference set offered per course. A course with no entry gets no reference links rather
#: than a generic hub that would tell a learner nothing about the subject they are studying.
COURSE_REFERENCES = {
    'physics': (OPENSTAX_COLLEGE_PHYSICS, KHAN_SCIENCE),
    'chemistry': (OPENSTAX_CHEMISTRY, KHAN_SCIENCE),
    'biology': (OPENSTAX_BIOLOGY, KHAN_SCIENCE),
    'earth_space_science': (OPENSTAX_ASTRONOMY, KHAN_SCIENCE),
    'computer_science': (KHAN_COMPUTING,),
    # Psychology reads as a science in the curriculum but has no PhET or Gizmos catalogue,
    # so it carries the OpenStax textbook and no simulation provider. See
    # COURSES_WITHOUT_SIMULATIONS.
    'ap_psychology': (OPENSTAX_PSYCHOLOGY,),
    # The six courses the study harness was asked to ship.
    'ap_macroeconomics': (OPENSTAX_PRINCIPLES_ECONOMICS, KHAN_ECONOMICS),
    'ap_microeconomics': (OPENSTAX_PRINCIPLES_ECONOMICS, KHAN_ECONOMICS),
    'ap_biology': (OPENSTAX_BIOLOGY, KHAN_SCIENCE),
    'ap_chemistry': (OPENSTAX_CHEMISTRY, KHAN_SCIENCE),
    'algebra_2': (OPENSTAX_ALGEBRA_TRIG_2E, KHAN_ALGEBRA_2),
    'ap_calculus': (OPENSTAX_CALCULUS, KHAN_CALCULUS),
}

# ------------------------------------------------------------------- media sources
#
# Images and video are governed here alongside text, because a licence gate that covers
# prose and not pictures is not a gate. Two distinctions do the work.
#
# **Cached vs embedded.** An image this project downloads is a *copy* and a *derivative
# distribution*, so only PUBLIC_DOMAIN / CC0 / CC BY / CC BY-SA qualify. A video served by
# the rights-holder's own player is not reproduced by us at all, so ``EMBED_ONLY`` is the
# correct and sufficient class there.
#
# **Text extraction is never granted.** Khan Academy's terms prohibit scraping and AI
# extraction of their content. This project therefore embeds their video *through YouTube's
# own player* and never fetches, transcribes, summarises or indexes the video or its
# captions. That is why ``KHAN_ACADEMY_TERMS`` above stays ``PROHIBITED`` and is *not*
# relaxed by the entry below: the prohibition is about copying content, and it still holds.

OPENVERSE = SourcePolicy(
    name='Openverse',
    url='https://openverse.org/',
    licence='Per asset; the API reports the underlying licence (CC0, CC BY, CC BY-SA, '
            'CC BY-NC, CC BY-ND, public domain mark).',
    licence_class=LicenceClass.CC_BY_SA,
    scope='Image search across openly-licensed collections. Assets are cached locally only '
          'when the per-asset licence permits redistribution; NC and ND assets are refused. '
          'The per-asset attribution string is stored and displayed with the image.',
    attribution='Attribution travels per asset, not per source; Openverse supplies a '
                'ready-made attribution string which this project stores verbatim.',
    evidence_id='openverse_aggregator_per_asset_licence',
)
WIKIMEDIA_COMMONS = SourcePolicy(
    name='Wikimedia Commons',
    url='https://commons.wikimedia.org/',
    licence='Per file; read from imageinfo extmetadata (LicenseShortName / License / '
            'LicenseUrl). Predominantly CC0, CC BY, CC BY-SA and public domain.',
    licence_class=LicenceClass.CC_BY_SA,
    scope='Freely-licensed media files. This project reads the file metadata API only, caches '
          'an asset only when its own licence permits redistribution, and records the '
          'required author credit from extmetadata.Artist.',
    attribution='Per file; the author and licence URL are taken from extmetadata and shown '
                'on the image card.',
    evidence_id='wikimedia_commons_free_media_per_file_licence',
)

#: Wikipedia, over its read-only HTTP API. Text under CC BY-SA: ingestion and quoting are
#: permitted with attribution, which the tool result carries. Read-only REST and Action
#: endpoints, descriptive user agent, no account, no edit path.
#:
#: Two endpoints are in scope and only two, because they are the two the harness
#: actually needs and both serve the same text under the same licence:
#: the REST *search* endpoint (to find a source, returning titles and excerpts) and the
#: Action API's ``prop=extracts&explaintext`` (to read one article as plain text, with
#: its section headings, which is the shape the concept extractor understands). The
#: plain-text endpoint is chosen over the REST HTML endpoint deliberately: article HTML
#: carries infoboxes, navboxes, reference lists, subscripted subscripts and no word
#: spacing, and running the extractor over it produces course concepts named
#: ``CO2carbon`` and ``electron``. The rights position is identical either way - the
#: provider serves its own text, read-only, under its own reuse notice.
WIKIPEDIA_REST = SourcePolicy(
    name='Wikipedia (REST API)',
    url='https://en.wikipedia.org/api/rest_v1/',
    licence='Text under Creative Commons Attribution-ShareAlike 4.0 (per Wikipedia\'s '
            'reuse notice); attribution travels with every fetched article.',
    licence_class=LicenceClass.CC_BY_SA,
    scope='Page search results, summaries and full-article plain text fetched read-only '
          'from the provider\'s REST API and its MediaWiki Action API, for grounding. '
          'Stored text carries the source URL and the CC BY-SA notice; the project does '
          'not mirror, bulk-download or train on the corpus.',
    attribution='"<Title>", Wikipedia, The Free Encyclopedia, <url>, CC BY-SA 4.0.',
    evidence_id='wikipedia_rest_cc_by_sa',
)

#: YouTube's own player. The embeddability of a specific video is not assumed: it is
#: verified per video against the provider's API before the reference is stored.
YOUTUBE_EMBED = SourcePolicy(
    name='YouTube (provider-hosted player)',
    url='https://www.youtube.com/',
    licence='Embedded under the YouTube Terms of Service via the provider\'s own iframe '
            'player. The video\'s own licence is set by its uploader and is reported per '
            'video; this project does not restate or upgrade it.',
    licence_class=LicenceClass.EMBED_ONLY,
    scope='Embedding the provider\'s player only. No download, no re-encoding, no re-hosting, '
          'no caption or transcript extraction, no summarisation of the audio. Embeddability '
          'is verified per video before the reference is stored.',
    attribution='Channel name and video title are stored and displayed next to the player.',
    evidence_id='youtube_oembed_embeddability_probe',
)

#: Khan Academy's own required notice. Their terms ask for a specific credit and permit
#: linking and embedding while prohibiting scraping, harvesting and AI extraction.
KHAN_ACADEMY_NOTICE = 'Note: All Khan Academy content is available for free at www.khanacademy.org'

KHAN_ACADEMY_VIDEO = SourcePolicy(
    name='Khan Academy (video, embedded via YouTube)',
    url='https://www.khanacademy.org/',
    licence='CC BY-NC-SA 4.0. The non-commercial clause is decided by the use, not the user: '
            'Khan\'s own guidance states that incorporating their content into a paid offering '
            'is not non-commercial use. Their terms also permit linking and embedding while '
            'prohibiting scraping, harvesting and use for AI training.',
    licence_class=LicenceClass.EMBED_ONLY,
    scope='Video embed and outbound link only. Text, transcripts, captions, exercises and '
          'logos are not copied, ingested, embedded as data or used for training. This does not '
          'relax KHAN_ACADEMY_TERMS, which continues to prohibit content extraction.',
    attribution='Khan Academy is named on the card and the required notice is displayed.',
    evidence_id='khan_academy_video_embed_no_extraction',
    commercial_ok=False,
    attribution_notice=KHAN_ACADEMY_NOTICE,
    revocable=True,
)
MIT_OCW_VIDEO = SourcePolicy(
    name='MIT OpenCourseWare (video, embedded via YouTube)',
    url='https://ocw.mit.edu/',
    licence='CC BY-NC-SA 4.0.',
    licence_class=LicenceClass.EMBED_ONLY,
    scope='Video embed and outbound link only; no download, re-host or transcript extraction.',
    evidence_id='mit_ocw_cc_by_nc_sa',
    commercial_ok=False,
)

#: The agent's research on this channel was specific and it corrects an earlier assumption:
#: 3Blue1Brown is **not** openly licensed. Their stated position permits brief clips in
#: educational contexts with on-screen attribution and a link, and prohibits re-uploading
#: their videos to other channels. So it is embed-only (which keeps the video on their own
#: channel) and it is explicitly not a redistribution grant.
THREE_BLUE_ONE_BROWN = SourcePolicy(
    name='3Blue1Brown (video, embedded via YouTube)',
    url='https://www.3blue1brown.com/',
    licence='Not openly licensed. The channel permits brief excerpts with on-screen '
            'attribution and a link, and prohibits re-uploading its videos elsewhere. There is '
            'no CC BY-SA grant; an earlier note in this file claimed one and was wrong.',
    licence_class=LicenceClass.EMBED_ONLY,
    scope='Embed via YouTube\'s own player only, with the channel named and linked. No '
          'download, no re-upload, no excerpting into project assets, no transcript '
          'extraction. Because no redistribution is taken, no share-alike obligation arises.',
    attribution='3Blue1Brown is named and linked on the card.',
    evidence_id='three_blue_one_brown_no_redistribution_grant',
    commercial_ok=True,
)

#: Simulations. Neither provider is copied or scraped.
PHET_SIMULATIONS = SourcePolicy(
    name='PhET Interactive Simulations (University of Colorado Boulder)',
    url='https://phet.colorado.edu/',
    licence='Regular HTML simulation files are CC BY-NC 4.0. PhET\'s own guidance states that '
            'commercial use includes "incorporating simulations into paid or subscription-based '
            'products", and that all commercial use requires a commercial licence from the '
            'University of Colorado Boulder. Many stale mirror pages still show CC BY 4.0; '
            'that is out of date and is not relied on here.',
    licence_class=LicenceClass.EMBED_ONLY,
    scope='Iframe embed of PhET\'s own hosted simulation, or an outbound link. Embedding is '
          'officially sanctioned through the Embed button on each simulation page. This project '
          'does not download, mirror, bundle or repackage simulations, and does not remove '
          'PhET attribution. Every slug is HTTP-verified before use, because an invented slug '
          'would present a dead iframe as a lesson resource.',
    attribution='PhET Interactive Simulations, University of Colorado Boulder, CC BY-NC 4.0.',
    evidence_id='phet_cc_by_nc_embed_only',
    commercial_ok=False,
)
GIZMOS_SIMULATIONS = SourcePolicy(
    name='ExploreLearning Gizmos (subscription)',
    url='https://gizmos.explorelearning.com/',
    licence='Proprietary, subscription-licensed per seat. Not open-licensed. Pass codes are '
            'non-shareable and may be used only by the administrators, teachers and students to '
            'whom they are assigned. No public content API exists; the documented integrations '
            'are institutional (LTI 1.3, OneRoster, Clever, ClassLink).',
    licence_class=LicenceClass.LINK_ONLY,
    scope='Deep-link only, into the signed-in subscriber\'s own session in their own browser. '
          'This project does not scrape, proxy, embed, cache or index Gizmos, and never handles '
          'another person\'s credentials. The operator\'s own subscription is what authorises '
          'access. The public catalogue is browsable without login, so titles are citable; a '
          'launch is not.',
    evidence_id='gizmos_proprietary_doc_link_only',
    commercial_ok=False,
)

COURSE_VIDEO_HUBS = {
    'integrated_math_1': (KHAN_ACADEMY_VIDEO, THREE_BLUE_ONE_BROWN),
    'physics': (KHAN_ACADEMY_VIDEO, MIT_OCW_VIDEO),
    'chemistry': (KHAN_ACADEMY_VIDEO,),
    'biology': (KHAN_ACADEMY_VIDEO,),
    'computer_science': (KHAN_ACADEMY_VIDEO,),
    'earth_space_science': (KHAN_ACADEMY_VIDEO,),
    'ap_macroeconomics': (KHAN_ACADEMY_VIDEO,),
    'ap_microeconomics': (KHAN_ACADEMY_VIDEO,),
    'ap_biology': (KHAN_ACADEMY_VIDEO,),
    'ap_chemistry': (KHAN_ACADEMY_VIDEO,),
    'ap_psychology': (KHAN_ACADEMY_VIDEO,),
    'algebra_2': (KHAN_ACADEMY_VIDEO,),
    'ap_calculus': (KHAN_ACADEMY_VIDEO, THREE_BLUE_ONE_BROWN),
}

#: Which simulation provider to try first for a course, in order.
#:
#: This is the *declared* preference. It is deliberately not the same thing as what the
#: frozen pack actually contains, and the two are compared rather than assumed equal --
#: see :func:`app.simulation_map.coverage`, which reports any declared provider that
#: contributed nothing for a course. ``computer_science`` lists Gizmos because the pack
#: carries Gizmos rows for it; ``physics`` lists Gizmos because Gizmos is strong there,
#: and the coverage report names the shortfall rather than letting a declared order imply
#: mappings that do not exist.
COURSE_SIMULATION_PROVIDERS = {
    'integrated_math_1': ('phet', 'gizmos'),
    'physics': ('phet', 'gizmos'),
    'chemistry': ('phet', 'gizmos'),
    'biology': ('phet', 'gizmos'),
    'earth_space_science': ('phet', 'gizmos'),
    'computer_science': ('phet', 'gizmos'),
    # The six courses the study harness was asked to ship. Biology, chemistry and the two
    # mathematics courses declare PhET because it genuinely carries simulations for them.
    # The economics courses declare EconEdLink instead: PhET has no economics catalogue, so
    # naming it would be a fabricated resource.
    'ap_macroeconomics': ('econedlink',),
    'ap_microeconomics': ('econedlink',),
    'ap_biology': ('phet',),
    'ap_chemistry': ('phet',),
    'algebra_2': ('phet',),
    'ap_calculus': ('phet',),
}

#: Courses that legitimately have no interactive simulation provider, with the reason.
#:
#: PhET and Gizmos both cover the physical and life sciences and neither carries a
#: psychology catalogue, so naming a provider here would be the fabricated-resource failure
#: this module exists to prevent. The absence is declared rather than left implicit, which
#: lets the media test assert *both* directions: no provider is required for these courses,
#: and none may appear either. ``app.simulation_map.coverage`` also reports the shortfall by
#: name, so a learner is never told a simulation exists when it does not.
COURSES_WITHOUT_SIMULATIONS = {
    'ap_psychology': 'PhET and Gizmos carry no psychology catalogue; the concept map and the '
                     'authored items are the practice surface for this course.',
}

#: Sources this project deliberately does NOT ingest. Composed here rather than inline so the
#: per-course reference books are part of the same audited list and appear in
#: :func:`registry` -- a reference link that skipped the audit would be exactly the kind of
#: quiet licence drift this module exists to prevent.
RESTRICTED = _AUTHORED_RESTRICTED + (OPENSTAX_ALGEBRA_TRIG_2E,
                                     OPENSTAX_COLLEGE_PHYSICS, OPENSTAX_CHEMISTRY, OPENSTAX_BIOLOGY,
                                     OPENSTAX_ASTRONOMY, OPENSTAX_PSYCHOLOGY, KHAN_SCIENCE,
                                     KHAN_COMPUTING, OPENSTAX_CALCULUS,
                                     OPENSTAX_PRINCIPLES_ECONOMICS,
                                     KHAN_ECONOMICS, KHAN_ALGEBRA_2, KHAN_CALCULUS)

#: Textbook sources cleared for actual text ingestion. A separate list from ``RESTRICTED``
#: because the two are opposite rights positions kept in the same audited registry: a book
#: is either in ``TEXTBOOK_SOURCES`` (text may be stored and quoted) or in ``RESTRICTED``
#: (link only), never both, and ``app.ingest.sources.openstax`` refuses any book slug that
#: appears in neither.
TEXTBOOK_SOURCES = (OPENSTAX_ALGEBRA_TRIG,)

#: Every media source, in the same audited list as the text sources. The game sources are
#: link-only references rather than media, but they ride the same registry so a stored
#: card stamped with their policy_name is re-evaluated against a live rights position
#: instead of silently trusted.
MEDIA_SOURCES = (OPENVERSE, WIKIMEDIA_COMMONS, WIKIPEDIA_REST, YOUTUBE_EMBED, KHAN_ACADEMY_VIDEO,
                 MIT_OCW_VIDEO, THREE_BLUE_ONE_BROWN, PHET_SIMULATIONS, GIZMOS_SIMULATIONS,
                 ECONEDLINK, *GAME_SOURCES)

#: Sources whose assets this project may cache locally.
CACHEABLE_IMAGE_SOURCES = (OPENVERSE, WIKIMEDIA_COMMONS)


def simulation_reference(course_id: str, *, commercial: bool = False) -> list[dict[str, Any]]:
    """The simulation provider cards for a course."""
    providers = {'phet': PHET_SIMULATIONS, 'gizmos': GIZMOS_SIMULATIONS,
                 'econedlink': ECONEDLINK}
    # How the resource may be opened. PhET sanctions an iframe embed through its own Embed
    # button; Gizmos is a signed-in per-seat deep link; EconEdLink is an ordinary outbound
    # link into a free public library. The mode is declared per provider rather than derived
    # from a single boolean, because "embed is allowed" and "a launch is possible" are
    # different facts about different providers.
    modes = {'phet': 'iframe_embed', 'gizmos': 'deep_link_authenticated',
             'econedlink': 'deep_link'}
    cards: list[dict[str, Any]] = []
    for key in COURSE_SIMULATION_PROVIDERS.get(course_id, ()):
        entry = providers[key]
        allowed = entry.commercial_ok or not commercial
        card: dict[str, Any] = {
            'kind': 'simulation', 'title': f'{entry.name} — interactive simulation',
            'url': entry.url, 'status': 'reference_link' if allowed else 'withheld',
            'provider': key,
            'integration_mode': (modes.get(key, 'deep_link') if allowed else 'unavailable'),
            'licence': entry.licence, 'licence_class': entry.licence_class.value,
            'scope': entry.scope, 'attribution': entry.attribution,
            'policy_name': entry.name, 'commercial_ok': entry.commercial_ok,
        }
        if not allowed:
            if key == 'phet':
                reason = ('Non-commercial licence, and this instance is configured as a paid '
                          'offering. PhET requires a commercial licence from the University of '
                          'Colorado Boulder for paid or subscription products.')
            elif key == 'gizmos':
                reason = ('Non-commercial licence, and this instance is configured as a paid '
                          'offering. Gizmos pass codes are non-shareable and licensed per seat.')
            else:
                reason = (f'{entry.name} is offered for non-commercial educational use and this '
                          f'instance is configured as a paid offering. Non-commercial is decided '
                          f'by the use, not the user, so the resource is withheld rather than '
                          f'silently kept.')
            card['withheld_reason'] = reason
        cards.append(card)
    return cards


def reference_entry(source: SourcePolicy, title: str | None = None) -> dict[str, str]:
    """One reference card, in the shape a lesson payload uses.

    The rights position travels with the card. A learner who opens an external reference
    should be able to see that it is a link rather than app content and what the source's
    licence says, instead of the app silently borrowing authority from somebody else's book.

    ``policy_name`` is stamped so a stored card can be re-evaluated against the live rights
    configuration later. Matching a card back to its policy by its display title would work
    until somebody edited a title.
    """
    return {'kind': 'reading',
            'title': title or f'{source.name} — external reference, not app content',
            'url': source.url, 'status': 'reference_link',
            'licence': source.licence, 'licence_class': source.licence_class.value,
            'scope': source.scope, 'policy_name': source.name,
            'commercial_ok': source.commercial_ok}


def reapply_media_policy(media: Sequence[Mapping[str, Any]],
                         commercial: bool) -> list[dict[str, Any]]:
    """Re-evaluate stored reference cards against the rights position in force *now*.

    Lesson media is materialised at import time, but whether this instance is a paid offering
    is a runtime setting. Materialising the commercial gate would freeze it at whatever the
    process saw first, so stored cards carry their policy name and are re-evaluated here.
    A card whose licence does not tolerate commercial use is marked withheld and given its
    reason rather than removed: an absent source and a withheld source are different facts,
    and the learner-facing surface should be able to say which one happened.

    A card whose ``policy_name`` does not resolve to a known source is also withheld. This is
    the fail-closed direction and it is the whole point of routing every card through here:
    a renamed policy, a typo in a stamp, or a card written before its source was audited
    would otherwise pass through as *cleared*, so a rights position that could not be
    established would be indistinguishable from a permissive one.
    """
    by_name = {entry.name: apply_overrides(entry) for entry in
               (WIKIDATA, OPERATOR_SCOPE_SEQUENCE, *RESTRICTED, *MEDIA_SOURCES)}
    out: list[dict[str, Any]] = []
    for card in media:
        name = str(card.get('policy_name') or '')
        entry = by_name.get(name)
        if entry is None:
            unknown = dict(card)
            unknown['status'] = 'withheld'
            unknown['withheld_reason'] = (
                f'No audited rights position is recorded for {name!r}, so this source cannot '
                f'be shown as cleared. A card whose policy name does not resolve is withheld '
                f'rather than assumed permissive.')
            out.append(unknown)
            continue
        if entry.commercial_ok or not commercial:
            # Every card leaves with an explicit status. A consumer that had to read
            # "status is absent, therefore ready" would be inferring a rights position
            # from a missing field, which is the same class of mistake as treating a
            # missing licence as a permissive one. ``ready`` is stamped rather than
            # assumed, and re-stamping an already-evaluated card is idempotent.
            cleared = dict(card)
            cleared.setdefault('status', 'ready')
            out.append(cleared)
            continue
        withheld = dict(card)
        withheld['status'] = 'withheld'
        withheld['withheld_reason'] = (
            f'{entry.name} is non-commercial ({entry.licence_class.value}) and this instance is '
            f'configured as a paid offering. Non-commercial is decided by the use, not the user, '
            f'so the source is withheld rather than silently kept.')
        out.append(withheld)
    return out


def course_media_extras(course_id: str, *, commercial: bool = False) -> list[dict[str, Any]]:
    """The course-level video and simulation cards, for a course that builds its own
    reading list and therefore does not go through :func:`reference_media`."""
    return [*video_reference(course_id, commercial=commercial),
            *simulation_reference(course_id, commercial=commercial)]


def reference_media(course_id: str, *, commercial: bool = False) -> list[dict[str, Any]]:
    """Every reference card shown for a course: readings, video hubs and simulation providers.

    Composed in one place so a course cannot end up with a video card that skipped the same
    rights evaluation the reading cards pass through.
    """
    return [*[reference_entry(source) for source in COURSE_REFERENCES.get(course_id, ())],
            *video_reference(course_id, commercial=commercial),
            *simulation_reference(course_id, commercial=commercial)]


def registry() -> list[dict[str, str]]:
    """Every declared source policy, ingestible first then restricted, for audit.

    Each entry carries the *effective* rights position (operator overrides applied) and
    an ``operator_override`` field naming the approval when one is in force, so an
    auditor never has to guess whether the position in code is the position in force.
    """
    ordered = [WIKIDATA, OPERATOR_SCOPE_SEQUENCE, *TEXTBOOK_SOURCES, *RESTRICTED, *MEDIA_SOURCES]
    out: list[dict[str, str]] = []
    for source in ordered:
        policy = apply_overrides(source)
        payload = policy.to_dict()
        record = override_for(policy.name)
        payload['operator_override'] = (
            {'approved_by': record.get('approved_by'), 'approved_at': record.get('approved_at'),
             'evidence_url': record.get('evidence_url'), 'scope': record.get('scope')}
            if record else None)
        out.append(payload)
    return out
