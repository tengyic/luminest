"""Video lessons: curated, verified, embedded, never copied.

The harness previously had no video. Locally chosen files could be played with AVPlayer,
and Khan Academy was named only as a link. This module adds real curated video without
turning the application into a scraper, and the constraints below are the whole design.

**Why a curated allowlist rather than search.** A search call is not only a quota cost; it
is a decision about somebody else's content taken automatically and at scale. The research
for this module found a cold YouTube Data API search costs 100 units against a 10,000
unit daily default, so a search-per-question over a 524-concept catalogue would exhaust a
day's quota in about a hundred queries - and it would surface whatever the ranking
algorithm returned rather than what the course needs. So: a per-concept allowlist that an
operator maintains, and search available only as an explicit, quota-metered operator tool.

**Why embeddability is verified per video.** A stored video id is a claim that a lesson
works. Owners disable embedding, videos are deleted, and regions are blocked. Verification
calls YouTube's oEmbed endpoint and requires an ``<iframe>`` in the returned markup. When a
key is configured the authoritative check is the Data API's own ``status.embeddable`` flag,
because oEmbed can return 401 for a video that is in fact embeddable. The fallback
direction is deliberately conservative: an unverifiable video is downgraded to a plain
outbound link rather than embedded on an unproven assumption.

**What this module will never do.** It does not download a video, re-encode one, re-host
one, fetch captions, fetch transcripts, summarise audio, or send any part of a video to a
model. ``assert_extraction_allowed`` exists so that a future caller has to argue with a
named refusal instead of quietly adding the fourth thing.

**Non-commercial is a use, not a user.** Khan Academy's own guidance says incorporating
their content into a paid offering is not non-commercial use. So when the operator declares
this instance commercial, NC sources are withheld by evaluation - the card says so - rather
than by anybody remembering to delete an entry.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlencode

import httpx

from ..ingest import policy

USER_AGENT = ('Luminfest/1.0 (educational, offline-first; '
              'local single-learner instance)')

#: How long a verification result is trusted before it is re-checked.
VERIFY_TTL_SECONDS = 14 * 24 * 3600

#: Data API cost of one search.list call, and the default daily allowance. Kept as named
#: constants because "how many searches can this afford" is a question the code should be
#: able to answer rather than a number buried in a request.
DATA_API_SEARCH_COST = 100
DATA_API_DAILY_UNITS = 10_000

#: Providers whose reference is a video. Each maps onto a declared policy entry above.
PROVIDER_POLICY = {
    'khan': policy.KHAN_ACADEMY_VIDEO,
    'mit_ocw': policy.MIT_OCW_VIDEO,
    'three_blue_one_brown': policy.THREE_BLUE_ONE_BROWN,
    'youtube': policy.YOUTUBE_EMBED,
}

#: Seeds that were verified live while this module was written. They are examples of the
#: shape an operator entry takes, not a curated curriculum: four videos across three
#: concepts. Every one of them was probed with YouTube oEmbed (HTTP 200 + the title and
#: channel below returned verbatim on 2026-10-11) and can be re-probed with
#: :func:`verify_all`. Candidate IDs that failed the probe were discarded, not shipped:
#: fCn8zs912OE resolved to a Vsauce video with no curricular fit, and IlU_FDU7I8k /
#: jvGhXLWwJGs returned no oEmbed payload at all.
SEED_ALLOWLIST: dict[str, list[dict[str, str]]] = {
    'integrated_math_1': [
        {'concept_id': 'linear_functions', 'provider': 'three_blue_one_brown',
         'video_id': 'kYB8IZa5AuE', 'title': 'Linear transformations and matrices',
         'channel': '3Blue1Brown',
         'why': 'Shows a linear map as the thing that moves the whole plane, which is the '
                'picture a slope-only treatment of linear functions never supplies.'},
        {'concept_id': 'linear_functions', 'provider': 'three_blue_one_brown',
         'video_id': 'kjBOesZCoqc', 'title': 'Essence of linear algebra preview',
         'channel': '3Blue1Brown',
         'why': 'A short geometric overview of what "linear" means visually - straight lines '
                'preserved under transformations - so the course has a picture to anchor '
                'slope and rate-of-change language. oEmbed-verified 2026-10-11.'},
        {'concept_id': 'coordinates', 'provider': 'three_blue_one_brown',
         'video_id': 'fNk_zzaMoSs', 'title': 'Vectors | Chapter 1, Essence of linear algebra',
         'channel': '3Blue1Brown',
         'why': 'Presents coordinates as data for arrows with direction and magnitude, which '
                'is the geometric picture behind slope as a directed rate. oEmbed-verified '
                '2026-10-11.'},
        {'concept_id': 'systems', 'provider': 'three_blue_one_brown',
         'video_id': 'k7RM-ot2NWY', 'title': 'Linear combinations, span, and basis vectors',
         'channel': '3Blue1Brown',
         'why': 'Linear combination is exactly the operation elimination performs on two '
                'equations; this video gives that operation a visual meaning before the '
                'algebra. oEmbed-verified 2026-10-11.'},
    ],
}


class ExtractionRefused(RuntimeError):
    """Raised when a caller asks for something a video licence forbids."""


def assert_extraction_allowed(purpose: str) -> None:
    """The fourth thing this module does not do.

    Khan Academy's terms prohibit AI/ML extraction, and every video provider here is
    governed by terms that forbid storing a copy. Transcription, caption harvesting,
    audio summarisation and model ingestion of a video are all extraction, so the refusal
    is a named function rather than an absence of code.
    """
    raise ExtractionRefused(
        f'Refused: {purpose!r} would require extracting content from a video. Every video '
        f'reference in this project is EMBED_ONLY: the provider serves the bytes, we never '
        f'hold a copy, captions and transcripts are never fetched, and no part of a video is '
        f'sent to a model. This is not a configuration flag.')


# --------------------------------------------------------------------- allowlist

def allowlist_path(settings) -> Path:
    """Operator-maintained curation. Data, so a revocation is not a release."""
    override = getattr(settings, 'media_cache_dir', '') or ''
    base = Path(override) if override else Path(settings.data_dir)
    return base / 'media' / 'video_allowlist.json'


def revocation_path(settings) -> Path:
    return Path(settings.data_dir) / 'media' / 'video_revocations.json'


#: The curated list this build ships, written by ``scripts/curate_videos.py``. It exists
#: because the desktop build runs with outbound media off: a lesson that needs a search to
#: find its video has no video at all, and the alternative — leaving the flag on — is the
#: privacy contradiction the audit indicted. Curation happens once at build time; this file
#: is read at runtime with no network, no quota and no decision taken on somebody else's
#: content after the build.
SEED_PACK = Path(__file__).resolve().parents[1] / 'media_packs' / 'video_allowlist_seed.json'


def _read_allowlist(path: Path) -> dict[str, list[dict[str, Any]]]:
    """One allowlist file, or an empty map. A malformed file is not an error."""
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, OSError):
        return {}
    if not isinstance(raw, Mapping):
        return {}
    return {str(key): [dict(row) for row in rows if isinstance(row, Mapping)]
            for key, rows in raw.items() if isinstance(rows, list)}


def load_allowlist(settings) -> dict[str, list[dict[str, Any]]]:
    """The curated concept -> video map, in precedence order.

    The operator's file wins, because a revocation or a correction must not require a
    release. The packaged seed is next, and the in-code table last: it is the small set of
    rows verified by hand while this module was written, kept so a checkout with no curated
    file still has something real rather than a fabricated link.
    """
    for path in (allowlist_path(settings), SEED_PACK):
        data = _read_allowlist(path)
        if data:
            return data
    return {course: [dict(entry) for entry in entries]
            for course, entries in SEED_ALLOWLIST.items()}


def save_allowlist(settings, data: Mapping[str, Sequence[Mapping[str, Any]]]) -> str:
    """Write the curation file so an operator can maintain it without editing source."""
    path = allowlist_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({k: list(v) for k, v in data.items()}, indent=2,
                               ensure_ascii=False), encoding='utf-8')
    return str(path)


def curate(settings, course_id: str, concept_id: str, *, video_id: str, title: str = '',
           channel: str = '', why: str = '',
           provider: str = 'youtube') -> dict[str, Any]:
    """Attach one video to one concept. This is the only way a video reaches a learner.

    Idempotent, because a TA may retry a job it never saw finish, and refusing a
    revocation *before* writing means a withdrawal cannot be undone by re-curating the
    same id. Nothing here verifies embeddability: that is the caller's job (and the
    delivery path's, via ``verify_on_open``), because curating during a lesson must not
    depend on the network being up.
    """
    video_id = str(video_id or '').strip()
    if not video_id:
        return {'added': False, 'reason': 'A video id is required.'}
    if _is_revoked(load_revocations(settings), provider, video_id):
        return {'added': False,
                'reason': 'This source is on the operator revocation list; it cannot be '
                          'curated back in.'}
    table = load_allowlist(settings)
    rows = table.setdefault(course_id, [])
    for row in rows:
        if (str(row.get('concept_id')) == concept_id
                and str(row.get('video_id')) == video_id):
            return {'added': False, 'reason': 'already curated', 'concept_id': concept_id,
                    'video_id': video_id, 'path': str(allowlist_path(settings))}
    rows.append({'concept_id': concept_id, 'provider': provider, 'video_id': video_id,
                 'title': str(title)[:200], 'channel': str(channel)[:120],
                 'why': str(why)[:400]})
    return {'added': True, 'concept_id': concept_id, 'video_id': video_id,
            'path': save_allowlist(settings, table)}


def load_revocations(settings) -> set[str]:
    """Withdrawals. A rightsholder may pull permission at any time, so revocation must be
    a data edit on an operator's side rather than a code change on ours.

    Entries may be a provider name (``khan``), a video id, or ``provider:video_id``.
    """
    path = revocation_path(settings)
    if not path.exists():
        return set()
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, OSError):
        return set()
    if isinstance(raw, Mapping):
        raw = raw.get('revoked') or []
    return {str(item).strip().casefold() for item in raw if str(item).strip()}


def revoke(settings, item: str) -> dict[str, Any]:
    """Add a withdrawal and return the new set."""
    revoked = sorted(load_revocations(settings) | {item.strip().casefold()})
    path = revocation_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'revoked': revoked}, indent=2), encoding='utf-8')
    return {'revoked': revoked, 'path': str(path)}


def _is_revoked(revoked: set[str], provider: str, video_id: str) -> bool:
    provider = provider.casefold()
    return (provider in revoked or video_id.casefold() in revoked
            or f'{provider}:{video_id}'.casefold() in revoked)


# --------------------------------------------------------------------- verification

@dataclass
class VideoRef:
    """One curated video, with its verification state attached."""

    course_id: str
    concept_id: str
    provider: str
    video_id: str
    title: str = ''
    channel: str = ''
    why: str = ''
    duration_seconds: int = 0
    embeddable: bool = False
    integration_mode: str = 'deep_link'
    verified_at: float = 0.0
    verify_method: str = ''
    verify_note: str = ''
    licence: str = ''
    licence_class: str = ''
    attribution_text: str = ''
    notice: str = ''
    withheld_reason: str = ''
    thumb_url: str = ''

    @property
    def watch_url(self) -> str:
        return f'https://www.youtube.com/watch?v={self.video_id}'

    @property
    def embed_url(self) -> str:
        """The provider's player. ``youtube-nocookie`` is used so a lesson does not hand a
        tracking cookie to the video host before the learner presses play."""
        return f'https://www.youtube-nocookie.com/embed/{self.video_id}'

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload['watch_url'] = self.watch_url
        payload['embed_url'] = self.embed_url if self.embeddable else ''
        payload['allow_download'] = False
        payload['allow_transcript_extraction'] = False
        payload['allow_model_ingestion'] = False
        return payload

    @property
    def withheld(self) -> bool:
        """A card is withheld exactly when it carries a reason for being withheld."""
        return bool(self.withheld_reason)

    def to_media_card(self) -> dict[str, Any]:
        """The shape the lesson ``media`` list already uses, extended for video.

        The three ``allow_*`` false flags travel with the card rather than living only on
        ``VideoRef``. A client rendering the card, and a test asserting the guarantee, both
        read the card, so the prohibition has to be legible there - a guarantee that exists
        only on an internal dataclass is a guarantee nobody can check.

        A withheld card is *unavailable*, not merely unverified. The two are different
        facts and previously collapsed into one: a revoked video reported
        ``status='link_only'``, so a client would render it as an ordinary outbound link
        and a learner could still be sent to a source the rightsholder had withdrawn.
        Withholding now blanks the actionable URL and says so in the status.
        """
        withheld = self.withheld
        return {
            'kind': 'video',
            'title': self.title or f'Video for {self.concept_id}',
            'url': '' if withheld else (self.embed_url if self.embeddable else self.watch_url),
            # ``watch_url`` is retained even when withheld: the operator needs to know which
            # video was withdrawn, and a revocation that hid its own subject could not be
            # audited or reversed.
            'watch_url': self.watch_url,
            'embed_url': '' if withheld else (self.embed_url if self.embeddable else ''),
            'thumbnail': self.thumb_url,
            'status': ('withheld' if withheld
                       else ('verified_embed' if self.embeddable else 'link_only')),
            'integration_mode': 'unavailable' if withheld else self.integration_mode,
            'channel': self.channel,
            'provider': self.provider,
            'video_id': self.video_id,
            'why_this_video': self.why,
            'licence': self.licence,
            'licence_class': self.licence_class,
            'attribution': self.attribution_text,
            'notice': self.notice,
            'verified_at': self.verified_at,
            'verify_method': self.verify_method,
            'verify_note': self.verify_note,
            'withheld_reason': self.withheld_reason,
            'allow_download': False,
            'allow_transcript_extraction': False,
            'allow_model_ingestion': False,
        }


def _oembed_probe(client: httpx.Client, video_id: str) -> tuple[bool, str, dict[str, Any]]:
    """Ask the provider whether this video may be embedded.

    oEmbed returns the iframe markup only when embedding is permitted, which makes the
    presence of an ``<iframe>`` a usable signal without an API key. It is not perfect: a
    401 can also mean rate-limiting or a deleted video, which is why a negative result
    downgrades the card to a plain link instead of pretending the video does not exist.
    """
    url = 'https://www.youtube.com/oembed?' + urlencode(
        {'url': f'https://www.youtube.com/watch?v={video_id}', 'format': 'json'})
    response = client.get(url, headers={'Accept': 'application/json'})
    if response.status_code == 401:
        return False, 'oembed_401_not_embeddable', {}
    response.raise_for_status()
    payload = response.json()
    markup = str(payload.get('html') or '')
    return ('iframe' in markup), 'oembed_iframe_present' if 'iframe' in markup \
        else 'oembed_html_without_iframe', payload


def _data_api_probe(client: httpx.Client, video_id: str, key: str) -> tuple[bool, dict[str, Any]]:
    """The authoritative embeddability answer, when an operator has supplied a key.

    ``status.embeddable`` is the field the research identified as authoritative; oEmbed is
    the keyless approximation used otherwise.
    """
    url = 'https://www.googleapis.com/youtube/v3/videos?' + urlencode(
        {'part': 'status,contentDetails,snippet', 'id': video_id, 'key': key})
    response = client.get(url, headers={'Accept': 'application/json'})
    response.raise_for_status()
    payload = response.json()
    items = payload.get('items') or []
    if not items:
        return False, {}
    return bool(items[0].get('status', {}).get('embeddable')), items[0]


def verify(settings, video_id: str, *, use_cache: bool = True) -> dict[str, Any]:
    """Verify one video's embeddability, with a TTL cache.

    Cached because the answer changes slowly and a lesson should not wait on a network
    round trip it already made; TTL'd because the answer does change.
    """
    cache_file = Path(settings.data_dir) / 'media' / 'video_verification.json'
    cache: dict[str, Any] = {}
    if cache_file.exists():
        try:
            cache = json.loads(cache_file.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            cache = {}
    entry = cache.get(video_id) if isinstance(cache, dict) else None
    now = time.time()
    if use_cache and isinstance(entry, Mapping) and \
            now - float(entry.get('checked_at') or 0) < VERIFY_TTL_SECONDS:
        return {**entry, 'cached': True}

    key = getattr(settings, 'youtube_api_key', '') or ''
    result: dict[str, Any] = {'video_id': video_id, 'checked_at': now, 'cached': False}
    timeout = float(getattr(settings, 'media_timeout', 12.0) or 12.0)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, trust_env=False,
                          headers={'User-Agent': USER_AGENT}) as client:
            if key:
                embeddable, item = _data_api_probe(client, video_id, key)
                result.update({
                    'embeddable': embeddable, 'method': 'youtube_data_api_v3_status',
                    'title': item.get('snippet', {}).get('title', ''),
                    'channel': item.get('snippet', {}).get('channelTitle', ''),
                    'duration': item.get('contentDetails', {}).get('duration', ''),
                    'thumbnail': (item.get('snippet', {}).get('thumbnails', {})
                                  .get('medium', {}).get('url', '')),
                })
            else:
                embeddable, why, payload = _oembed_probe(client, video_id)
                result.update({
                    'embeddable': embeddable, 'method': why,
                    'title': str(payload.get('title') or ''),
                    'channel': str(payload.get('author_name') or ''),
                    'thumbnail': str(payload.get('thumbnail_url') or ''),
                })
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        # Unverifiable is not embeddable. The conservative direction costs an embed; the
        # permissive direction would assert a licence position nobody checked.
        result.update({'embeddable': False, 'method': f'unverifiable:{type(exc).__name__}',
                       'title': '', 'channel': ''})
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(cache, dict):
        cache[video_id] = result
        try:
            cache_file.write_text(json.dumps(cache, indent=2), encoding='utf-8')
        except OSError:
            pass
    return result


# --------------------------------------------------------------------- retrieval

def resolve(settings, course_id: str, concept_id: str, *, commercial: bool | None = None,
            verify_remote: bool = True) -> list[dict[str, Any]]:
    """The curated, verified, licence-cleared videos for one concept.

    Returns cards in the shape a lesson already renders, so wiring video into a lesson is a
    concatenation rather than a new rendering path. A withheld card is returned with its
    reason rather than dropped, because an empty list and a withheld source are different
    facts and a learner-facing feature should be able to say which one happened.
    """
    if commercial is None:
        commercial = bool(getattr(settings, 'commercial_use', False))
    revoked = load_revocations(settings)
    table = load_allowlist(settings)
    rows = [row for row in table.get(course_id, []) if str(row.get('concept_id')) == concept_id]
    cards: list[dict[str, Any]] = []
    for row in rows:
        provider = str(row.get('provider') or 'youtube')
        video_id = str(row.get('video_id') or '')
        entry = PROVIDER_POLICY.get(provider)
        if entry is None or not video_id:
            continue
        ref = VideoRef(course_id=course_id, concept_id=concept_id, provider=provider,
                       video_id=video_id, title=str(row.get('title') or ''),
                       channel=str(row.get('channel') or ''), why=str(row.get('why') or ''),
                       licence=entry.licence, licence_class=entry.licence_class.value,
                       attribution_text=entry.attribution or entry.name,
                       notice=entry.attribution_notice)
        if _is_revoked(revoked, provider, video_id):
            # A revocation is absolute and is checked before anything else, so it cannot be
            # defeated by a later branch that happens to succeed.
            ref.withheld_reason = (
                'Withdrawn: this source or video appears in the operator revocation list. '
                'A rightsholder may withdraw permission at any time, so withdrawal takes '
                'effect without a code change.')
            cards.append(ref.to_media_card())
            continue
        if commercial and not entry.commercial_ok:
            ref.withheld_reason = (
                f'Withheld: {entry.name} is non-commercial and this instance is configured as '
                f'a paid offering. Non-commercial is decided by the use, not the user.')
            cards.append(ref.to_media_card())
            continue
        if verify_remote:
            probe = verify(settings, video_id)
            ref.embeddable = bool(probe.get('embeddable'))
            ref.verified_at = float(probe.get('checked_at') or 0)
            ref.verify_method = str(probe.get('method') or '')
            ref.title = ref.title or str(probe.get('title') or '')
            ref.channel = ref.channel or str(probe.get('channel') or '')
            ref.thumb_url = str(probe.get('thumbnail') or '')
            if not ref.embeddable:
                ref.verify_note = (
                    'Embedding could not be verified for this video, so it is offered as a '
                    'plain outbound link instead. The unverified direction is never the '
                    'permissive one.')
        ref.integration_mode = 'iframe_embed' if ref.embeddable else 'deep_link'
        cards.append(ref.to_media_card())
    return cards


def verify_all(settings, *, limit: int = 200) -> dict[str, Any]:
    """Re-probe every curated video. The operator-facing maintenance action."""
    table = load_allowlist(settings)
    checked, dead = 0, []
    for course_id, rows in table.items():
        for row in rows[:limit]:
            video_id = str(row.get('video_id') or '')
            if not video_id:
                continue
            probe = verify(settings, video_id, use_cache=False)
            checked += 1
            if not probe.get('embeddable'):
                dead.append({'course_id': course_id, 'video_id': video_id,
                             'method': probe.get('method')})
    return {'checked': checked, 'not_embeddable': dead,
            'note': 'A video that fails verification is downgraded to a link, never embedded '
                    'on an unverified assumption.'}


def search_quota(searches: int) -> dict[str, Any]:
    """What a number of searches costs against the default Data API allowance."""
    cost = searches * DATA_API_SEARCH_COST
    return {'searches': searches, 'units': cost, 'daily_units': DATA_API_DAILY_UNITS,
            'fraction_of_daily_allowance': round(cost / DATA_API_DAILY_UNITS, 4),
            'searches_affordable_per_day': DATA_API_DAILY_UNITS // DATA_API_SEARCH_COST,
            'recommendation': 'Curate an allowlist keyed by concept id and spend quota on '
                              'verification, not discovery. A search-per-question over a '
                              '524-concept catalogue would exhaust a day of quota in about '
                              'a hundred queries.'}


def describe(settings=None) -> dict[str, Any]:
    """The module's posture, for the transparency panel."""
    curated = 0
    if settings is not None:
        try:
            curated = sum(len(v) for v in load_allowlist(settings).values())
        except OSError:
            curated = 0
    return {
        'providers': sorted(PROVIDER_POLICY),
        'curated_videos': curated,
        'verify_ttl_days': round(VERIFY_TTL_SECONDS / 86400, 1),
        'authoritative_check': 'youtube data api v3 status.embeddable when a key is '
                               'configured; oembed iframe presence otherwise',
        'commercial_use': bool(getattr(settings, 'commercial_use', False))
        if settings is not None else None,
        'search_quota': search_quota(1),
        'guarantees': [
            'Embeds go through the provider\'s own player; no video is downloaded, '
            're-encoded or re-hosted.',
            'Embeddability is verified per video and fails closed.',
            'Captions, transcripts and audio are never fetched, and no part of a video is '
            'sent to a model.',
            'Khan Academy\'s required notice is stored as data and displayed with the card.',
            'Non-commercial sources are withheld automatically on a paid instance.',
            'A revocation list withdraws any source or video without a code change.',
        ],
    }
