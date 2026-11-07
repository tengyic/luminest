"""Internet images, licence-gated, downloaded, cached and attributed.

Until now this project had no photographs at all: a figure was always something the
symbolic engine or the concept map *computed*. That is honest for mathematics and useless
for the parts of a science course that are about what a cell, a rock or a nebula actually
looks like. This module adds real images without weakening the licence gate that every
other outside source already passes through.

Five commitments, in the order they apply.

1. **Search is not acquisition.** A candidate is a search result. Nothing is downloaded
   until its own licence has been classified and cleared for local storage, because a
   downloaded file is a copy and a copy is what an NC or ND licence restricts.

2. **The licence travels with the asset.** Every cached image carries its source, source
   id, author, licence code, licence class, licence URL and the attribution string the
   provider supplied. A cached image without its attribution is not a usable asset, so
   the attribution is stored in the manifest *and* returned on every read.

3. **An unknown licence is refused, not assumed.** Both providers are asked for what they
   know and neither is trusted to only ever emit codes this project has ruled on. An
   unrecognised code drops the candidate with a reason attached.

4. **Precision is enforced, not hoped for.** Full-text image search returns confident
   nonsense: a query for "prophase" returns a photograph of a theatre. Candidates are
   filtered on measurable properties - a minimum width, a sane aspect ratio, and token
   overlap between the query and the asset's own title/tags - and every rejection is
   recorded so the filter can be argued with rather than merely believed.

5. **Offline is a first-class outcome.** With the network unavailable or disabled by the
   operator, every entry point returns a refusal and a reason. Nothing raises, nothing
   blocks the lesson, and the deterministic figure remains available exactly as before.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlencode, urlparse

import httpx

from ..ingest import policy

#: Providers this module can search, in the order they are tried.
PROVIDERS = ('openverse', 'wikimedia', 'met', 'nasa')

#: Which source to prefer per course, best first. Derived from the reported coverage of each
#: collection rather than from taste: NASA holds public-domain earth and space imagery, the
#: Met and Commons hold the deepest historical and instrument material, and Openverse is the
#: broadest aggregator for everything else.
COURSE_SOURCE_ORDER = {
    'earth_space_science': ('nasa', 'wikimedia', 'met', 'openverse'),
    'physics': ('wikimedia', 'met', 'openverse', 'nasa'),
    'chemistry': ('wikimedia', 'openverse', 'met'),
    'biology': ('wikimedia', 'openverse', 'met', 'nasa'),
    'computer_science': ('openverse', 'wikimedia'),
    'integrated_math_1': ('openverse', 'wikimedia', 'met'),
}

#: Providers that cannot be used at all, with the reason. Kept as data because the reason
#: matters more than the name: these are not missing features, they are omissions forced by
#: terms that are incompatible with caching an image offline.
EXCLUDED_PROVIDERS = {
    'unsplash': ('The Unsplash API guidelines require hotlinking the image from their CDN and '
                 'prohibit storing or re-hosting a copy. That is the exact opposite of an '
                 'offline-first cache, so the source is excluded rather than used partially.'),
    'pixabay': ('Runtime hotlinking is prohibited and permanent hotlinking is discouraged, so a '
                'copy would have to be stored - but the terms also prohibit stand-alone '
                'redistribution of the media. Both halves cannot be satisfied at once.'),
    'nypl': ('The NYPL Digital Collections repository API was retired with no replacement, so '
             'there is nothing to call.'),
    'pexels': ('Permitted only with a per-photo credit and an explicit "Photos provided by '
               'Pexels" notice; held out of the default order because the same subject matter '
               'is available from a Tier-A public-domain source with no credit obligation.'),
}

#: User agent. Both APIs ask for an identifiable agent and a contact route, and sending one
#: is the difference between a tolerated client and a blocked one.
#:
#: The contact route is not decoration. Wikimedia's API policy refuses a ``User-Agent``
#: with no reachable contact with an HTTP 403 that arrives as an empty result set, which
#: reads exactly like "Commons has no photograph of this concept". Measured 2026-10-26:
#: the identifier line below with no contact returns 403, and the same line plus
#: ``contact: operator@example.invalid`` returns 200. ``example.invalid`` is the RFC 2606
#: reserved domain, so an unset operator is visible as a placeholder rather than
#: masquerading as a real mailbox; :func:`search` says so in its notes.
USER_AGENT_NAME = ('LuminfestLearningHarness/1.0 '
                   '(educational, offline-first textbook builder)')
#: Sent when the operator has not configured ``HARNESS_MEDIA_CONTACT``. Deliberately the
#: reserved TLD: a policy reviewer can see at once that nobody set this.
DEFAULT_MEDIA_CONTACT = 'contact: operator@example.invalid'


def user_agent(settings) -> str:
    """The UA this instance sends, with the operator's contact route when there is one.

    ``httpx`` builds its own default UA when none is passed, and that default is the one
    string both Wikimedia and Openverse name as a reason to block: no product, no contact,
    no way to ask the operator to stop.
    """
    contact = str(getattr(settings, 'media_contact', '') or '').strip()
    if not contact:
        return f'{USER_AGENT_NAME} {DEFAULT_MEDIA_CONTACT}'
    if '@' in contact or '://' in contact:
        return f'{USER_AGENT_NAME} contact: {contact}'
    return f'{USER_AGENT_NAME} ({contact})'


def contact_configured(settings) -> bool:
    return bool(str(getattr(settings, 'media_contact', '') or '').strip())


#: The module-level fallback, kept because ``voice`` imports it and a speech request has the
#: same problem: an agent with no contact route is an agent a provider may refuse. Media
#: requests themselves use :func:`user_agent`, which knows the operator's contact.
USER_AGENT = f'{USER_AGENT_NAME} {DEFAULT_MEDIA_CONTACT}'

#: Published anonymous limits for Openverse: 20 requests/minute and 200/day. Low enough that
#: an unauthenticated instance exhausts its day in one lesson, which is why credentials are
#: supported and their absence is reported rather than discovered by a 429.
OPENVERSE_ANON_LIMITS = {'per_minute': 20, 'per_day': 200}

#: Refuse anything narrower than this. A 240px thumbnail blown up in a lesson reads as a
#: broken image, and the learner cannot tell that from a broken lesson.
MIN_WIDTH = 800
MIN_HEIGHT = 500

#: Refuse extreme crops. A 4000x120 banner is a website header, not an illustration.
MIN_ASPECT = 0.4
MAX_ASPECT = 3.0

#: Stop before a runaway download. A lesson illustration has no reason to exceed this.
MAX_BYTES = 12 * 1024 * 1024

#: How many candidates to fetch before filtering. Search relevance is unreliable, so a
#: handful of results is not enough to find one usable asset.
SEARCH_DEPTH = 20

#: How many images one explicit fetch call may return. An image is a deliberate act with a
#: licence and an attribution attached, so a request that quietly downloads thirty
#: photographs is a bandwidth, review and rights problem at once. The cap is reported in
#: the payload rather than applied silently.
MAX_FETCH_PER_CALL = 6

#: How many images a lesson batch-fetch will look for. A lesson has a few places a real
#: photograph helps and many where the deterministic figure is the honest illustration, so
#: the cap is small and is stated in the response, never left implicit.
MAX_LESSON_IMAGES = 3

#: Words too common to prove a match. Deliberately tiny and derived from the query language
#: rather than from any curriculum vocabulary: this is a stop-word list, not a topic list.
_STOPWORDS = frozenset({
    'a', 'an', 'the', 'of', 'in', 'on', 'for', 'to', 'and', 'or', 'is', 'are', 'be',
    'what', 'which', 'how', 'why', 'with', 'by', 'at', 'as', 'it', 'its', 'from', 'that',
    'this', 'these', 'those', 'diagram', 'image', 'picture', 'photo', 'photograph',
})

#: MIME types a lesson can actually display.
IMAGE_MIMES = frozenset({'image/jpeg', 'image/png', 'image/webp', 'image/gif'})

#: Bare extensions -> MIME type. Providers disagree about which vocabulary they answer in:
#: Openverse's ``filetype`` field is a bare extension (``"jpg"``), Wikimedia's ``mime`` is a
#: real MIME type (``"image/jpeg"``), and a third provider will do something else again. The
#: check downstream is about *displayability*, so the extension has to be translated at the
#: provider boundary before it can be judged. Without this, every Openverse hit was rejected
#: as "Not a displayable image type (jpg)" - a correct-looking rejection reason attached to
#: the most common image format on the web.
EXTENSION_MIMES = {
    'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'jpe': 'image/jpeg', 'jfif': 'image/jpeg',
    'png': 'image/png', 'apng': 'image/png',
    'webp': 'image/webp',
    'gif': 'image/gif',
    'tif': 'image/tiff', 'tiff': 'image/tiff',
    'svg': 'image/svg+xml',
    'bmp': 'image/bmp',
    'avif': 'image/avif',
    'heic': 'image/heic', 'heif': 'image/heif',
}


def normalise_mime(value: str) -> str:
    """Return a MIME type for either a MIME type or a bare extension.

    Anything unrecognised is returned lowercased and stripped rather than emptied, so the
    rejection reason can still name what the provider actually said.
    """
    text = (value or '').strip().lower()
    if not text:
        return ''
    if '/' in text:
        return text
    return EXTENSION_MIMES.get(text.lstrip('.'), text)


@dataclass
class Candidate:
    """A search hit, before anything has been downloaded.

    ``rejected`` is set by the filter and is never cleared: a caller that receives an empty
    accepted list can still show exactly which candidates were seen and why each was
    dropped, which is the difference between a filter and a black box.
    """

    source: str
    source_id: str
    title: str
    creator: str = ''
    creator_url: str = ''
    licence_code: str = ''
    licence_url: str = ''
    attribution_text: str = ''
    landing_page_url: str = ''
    file_url: str = ''
    thumb_url: str = ''
    width: int = 0
    height: int = 0
    mime: str = ''
    description: str = ''
    tags: list[str] = field(default_factory=list)
    licence_class: str = ''
    locally_storable: bool = False
    rejected: str = ''

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ImageAsset:
    """A downloaded, licence-cleared image sitting in the local cache."""

    source: str
    source_id: str
    query: str
    title: str
    creator: str
    licence_code: str
    licence_class: str
    licence_url: str
    attribution_text: str
    landing_page_url: str
    file_url: str
    cache_path: str
    sha256: str
    bytes: int
    width: int
    height: int
    mime: str
    description: str
    fetched_at: float
    alt_text: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_block(self, *, caption: str = '') -> dict[str, Any]:
        """The shape a lesson block or slide uses.

        The attribution is not optional decoration here: it is a condition of the licence,
        so it is placed in the block the client renders rather than left to the caller to
        remember.
        """
        return {
            'type': 'image',
            'kind': 'photograph',
            # ``src`` is the URL the bytes route serves, not the cache path. The cache path
            # is a data-directory-relative file name that only the server can open; a client
            # handed it renders nothing, which is how a cleared image becomes an invisible
            # one. The path is kept alongside it for export, where a local file is correct.
            'src': f'/api/v1/media/images/{self.sha256}/bytes',
            'cache_path': self.cache_path,
            'cached': True,
            'title': self.title,
            'alt': self.alt_text,
            'caption': caption or self.description[:200],
            'credit': self.attribution_text,
            'licence': self.licence_code,
            'licence_class': self.licence_class,
            'licence_url': self.licence_url,
            'source': self.source,
            'source_url': self.landing_page_url,
            'creator': self.creator,
            'width': self.width,
            'height': self.height,
            'sha256': self.sha256,
        }


# --------------------------------------------------------------------- plumbing

def enabled(settings) -> bool:
    """Whether the operator has cleared this instance to reach the network for media."""
    return bool(settings and getattr(settings, 'media_enabled', False))


def _client(settings) -> httpx.Client:
    timeout = float(getattr(settings, 'media_timeout', 12.0) or 12.0)
    return httpx.Client(timeout=timeout, follow_redirects=True, trust_env=False,
                        headers={'User-Agent': user_agent(settings)})


def cache_root(settings) -> Path:
    """Where cached images live. Under the data directory, so export/delete covers them."""
    override = getattr(settings, 'media_cache_dir', None)
    base = Path(override) if override else Path(settings.data_dir) / 'media'
    return base / 'images'


def manifest_path(settings) -> Path:
    return Path(settings.data_dir) / 'media' / 'images.jsonl'


#: Images curated at build time and shipped inside the bundle.
#:
#: The desktop app runs with ``media_enabled`` off — that is what `privacy.md` promises — so
#: ``acquire`` returns ``network_disabled`` and every deck fell back to a decorative pattern.
#: A learner cannot tell a decorative pattern from a photograph, so a deck looked illustrated
#: when it was not, and a deck whose picture failed looked the same as one that had never
#: asked. Curation therefore happens once, at build time, with the network on
#: (``scripts/curate_images.py``), and the result travels as data — the same shape as the
#: video allowlist: shipped seed, nothing fetched at runtime.
SEED_PACK = Path(__file__).resolve().parents[1] / 'media_packs' / 'image_seed.json'
SEED_DIR = Path(__file__).resolve().parents[1] / 'media_packs' / 'images'


def shipped_pack() -> dict[str, dict[str, Any]]:
    """The shipped index: lesson id -> a complete manifest row.

    An absent or unreadable pack is an empty pack, not an error: a source checkout that has
    never run the curator must still boot, and its decks must still render as text.
    """
    try:
        data = json.loads(SEED_PACK.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): row for key, row in data.items()
            if isinstance(row, dict) and _valid_sha(row.get('sha256'))}


def shipped_for(settings, lesson_id: str) -> dict[str, Any] | None:
    """The shipped picture for a lesson, installed into this instance's cache on first ask.

    Installation is a copy plus one manifest line, so the rest of the app — the bytes route,
    the export bundle, the licence rollup — keeps reading one manifest and needs no special
    case for "shipped". Idempotent: a second call finds the sha already registered.
    """
    row = shipped_pack().get(str(lesson_id or ''))
    if not row:
        return None
    return _install_shipped(settings, row)


def _install_shipped(settings, row: Mapping[str, Any]) -> dict[str, Any] | None:
    sha = str(row.get('sha256') or '')
    suffix = Path(str(row.get('file') or '')).suffix or '.jpg'
    source = SEED_DIR / (sha + suffix)
    if not source.is_file():
        # The index names a file the pack does not carry. Refusing here is what keeps the
        # deck honest: a row whose bytes are missing is not a picture.
        return None
    root = cache_root(settings)
    root.mkdir(parents=True, exist_ok=True)
    target = root / (sha + suffix)
    if not target.is_file():
        shutil.copyfile(source, target)
    manifest = _load_manifest(settings)
    if sha in manifest:
        return manifest[sha]
    installed = {key: value for key, value in row.items() if key != 'file'}
    installed['cache_path'] = str(target.relative_to(Path(settings.data_dir)))
    installed.setdefault('shipped', True)
    with manifest_path(settings).open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(installed, ensure_ascii=False) + '\n')
    return installed


def asset_payload(asset: Mapping[str, Any]) -> dict[str, Any]:
    """The client-facing view of one manifest row.

    One builder, used by the deck, the narrated presentation and the textbook, so a shipped
    picture, a freshly downloaded one and one restored from a lesson bundle cannot drift
    apart in what the client is told about them. ``credit`` and ``attribution`` are the same
    sentence under two names because the two consumers already read different keys; keeping
    both here is cheaper than teaching either of them a new one, and neither can now ship
    without an attribution.
    """
    credit = str(asset.get('attribution_text') or '')[:300]
    sha = str(asset.get('sha256') or '')
    return {
        'sha256': sha,
        'url': f'/api/v1/media/images/{sha}/bytes',
        'alt': str(asset.get('alt_text') or '')[:300],
        'title': str(asset.get('title') or '')[:200],
        'credit': credit,
        'attribution': credit,
        'licence': str(asset.get('licence_code') or '')[:60],
        'licence_class': str(asset.get('licence_class') or '')[:40],
        'source_url': str(asset.get('landing_page_url') or '')[:500],
        'width': int(asset.get('width') or 0),
        'height': int(asset.get('height') or 0),
    }


def _signature(query: str, source: str, source_id: str) -> str:
    return hashlib.sha256(f'{source}\x00{source_id}\x00{query}'.encode()).hexdigest()[:24]


# --------------------------------------------------------------------- searching

def _search_openverse(settings, query: str, depth: int) -> list[Candidate]:
    url = 'https://api.openverse.org/v1/images/?' + urlencode({
        'q': query, 'page_size': max(1, min(depth, 50)), 'mature': 'false',
        'license_type': 'all-cc,commercial,modification',
    })
    headers = {'Accept': 'application/json'}
    # Registered credentials lift the anonymous ceiling from 200 requests a day to 10,000.
    # Used when present and reported when absent, so a throttled instance is a known state
    # rather than a mystery.
    client_id = getattr(settings, 'openverse_client_id', '') or ''
    client_secret = getattr(settings, 'openverse_client_secret', '') or ''
    with _client(settings) as client:
        if client_id and client_secret:
            try:
                token_response = client.post('https://api.openverse.org/v1/auth_tokens/token/',
                                             data={'client_id': client_id,
                                                   'client_secret': client_secret,
                                                   'grant_type': 'client_credentials'})
                token_response.raise_for_status()
                headers['Authorization'] = f"Bearer {token_response.json().get('access_token', '')}"
            except (httpx.HTTPError, ValueError, KeyError):
                headers.pop('Authorization', None)
        response = client.get(url, headers=headers)
        response.raise_for_status()
        payload = response.json()
    out: list[Candidate] = []
    for row in (payload.get('results') or []):
        if not isinstance(row, Mapping):
            continue
        tags = [str(t.get('name')) for t in (row.get('tags') or [])
                if isinstance(t, Mapping) and t.get('name')]
        licence = str(row.get('license') or '')
        version = str(row.get('license_version') or '')
        # Openverse's own attribution string is authoritative and already carries the
        # creator, the licence and the link, so it is stored verbatim rather than rebuilt.
        out.append(Candidate(
            source='openverse', source_id=str(row.get('id') or ''),
            title=str(row.get('title') or ''), creator=str(row.get('creator') or ''),
            creator_url=str(row.get('creator_url') or ''),
            licence_code=f'{licence} {version}'.strip(),
            licence_url=str(row.get('license_url') or licence or ''),
            attribution_text=str(row.get('attribution') or ''),
            landing_page_url=str(row.get('foreign_landing_url') or row.get('detail_url') or ''),
            file_url=str(row.get('url') or ''), thumb_url=str(row.get('thumbnail') or ''),
            width=int(row.get('width') or 0), height=int(row.get('height') or 0),
            mime=normalise_mime(str(row.get('filetype') or '')), tags=tags))
    return out


def _search_met(settings, query: str, depth: int) -> list[Candidate]:
    """The Met's Open Access API. CC0 where the object is flagged public domain, so it is
    cacheable with no attribution obligation - the cleanest licence position of any source
    here, which is why it is worth a second round trip for the object detail.

    ``/v1.1/search`` rather than ``/v1/search``: the v1 search endpoint was retired, and a
    mapping that still pointed at it would return nothing while looking correct.
    """
    base = 'https://collectionapi.metmuseum.org/public/collection/v1.1'
    with _client(settings) as client:
        search = client.get(f'{base}/search', params={
            'q': query, 'hasImages': 'true',
            'isPublicDomain': 'true', 'medium': 'Photographs'})
        search.raise_for_status()
        ids = [int(i) for i in (search.json().get('objectIDs') or [])][:max(1, min(depth, 20))]
        out: list[Candidate] = []
        for object_id in ids:
            try:
                detail = client.get(f'{base}/objects/{object_id}')
                detail.raise_for_status()
                row = detail.json()
            except (httpx.HTTPError, ValueError):
                continue
            if not row.get('isPublicDomain') or not row.get('primaryImage'):
                continue
            out.append(Candidate(
                source='met', source_id=str(object_id),
                title=str(row.get('title') or ''), creator=str(row.get('artistDisplayName') or ''),
                licence_code='CC0 1.0' if row.get('isPublicDomain') else '',
                licence_url='https://creativecommons.org/publicdomain/zero/1.0/',
                attribution_text='',
                landing_page_url=str(row.get('objectURL') or ''),
                file_url=str(row.get('primaryImage') or ''),
                thumb_url=str(row.get('primaryImageSmall') or ''),
                # The Met's search response does not carry pixel dimensions and a per-object
                # fetch for size alone would double the request count. Leaving them at 0
                # makes the size filter skip rather than reject, which is the honest
                # behaviour: an unknown dimension is unknown, not disqualifying.
                width=0, height=0, mime='image/jpeg',
                description=str(row.get('objectName') or ''),
                tags=[str(t) for t in (row.get('tags') or [])]))
    return out


def _search_nasa(settings, query: str, depth: int) -> list[Candidate]:
    """NASA's Image and Video Library. Public domain, so cacheable and no attribution due.

    Restricted to still images: the endpoint serves video too, and a video asset in an image
    slot would fail at render time rather than here.
    """
    url = 'https://images-api.nasa.gov/search?' + urlencode({
        'q': query, 'media_type': 'image',
        'page_size': max(1, min(depth, 50))})
    with _client(settings) as client:
        response = client.get(url, headers={'Accept': 'application/json'})
        response.raise_for_status()
        payload = response.json()
    items = ((payload.get('collection') or {}).get('items') or [])
    out: list[Candidate] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        data = (item.get('data') or [{}])[0]
        if not isinstance(data, Mapping):
            continue
        links = item.get('links') or []
        thumb = next((str(link.get('href')) for link in links
                      if isinstance(link, Mapping) and link.get('href')), '')
        out.append(Candidate(
            source='nasa', source_id=str(data.get('nasa_id') or ''),
            title=str(data.get('title') or ''),
            creator=str(data.get('photographer') or data.get('secondary_creator')
                        or data.get('center') or 'NASA'),
            licence_code='Public domain (NASA)',
            licence_url='https://www.nasa.gov/nasa-brand-center/images-and-media/',
            attribution_text='',
            landing_page_url=f"https://images.nasa.gov/details/{data.get('nasa_id') or ''}",
            file_url=thumb, thumb_url=thumb, mime='image/jpeg',
            description=str(data.get('description') or '')[:400],
            tags=[str(data.get('title') or '')] + str(data.get('keywords') or '').split(',')[:8]))
    return out


def _strip_html(value: str) -> str:
    import re
    return re.sub(r'<[^>]+>', '', value or '').strip()


def _search_wikimedia(settings, query: str, depth: int) -> list[Candidate]:
    url = 'https://commons.wikimedia.org/w/api.php?' + urlencode({
        'action': 'query', 'format': 'json', 'generator': 'search',
        'gsrsearch': f'filetype:bitmap {query}', 'gsrnamespace': 6,
        'gsrlimit': max(1, min(depth, 50)), 'prop': 'imageinfo',
        'iiprop': 'url|size|mime|extmetadata', 'iiurlwidth': 1280,
    })
    with _client(settings) as client:
        response = client.get(url, headers={'Accept': 'application/json'})
        response.raise_for_status()
        payload = response.json()
    pages = ((payload.get('query') or {}).get('pages') or {})
    out: list[Candidate] = []
    for page in pages.values():
        info = (page.get('imageinfo') or [{}])[0]
        meta = info.get('extmetadata') or {}

        def field(name: str, default: str = '') -> str:
            entry = meta.get(name) or {}
            return _strip_html(str(entry.get('value') or default))

        title = str(page.get('title') or '')
        if title.lower().startswith('file:'):
            title = title[5:]
        licence_name = (field('LicenseShortName') or field('License') or field('UsageTerms')
                        or field('Copyrighted'))
        out.append(Candidate(
            source='wikimedia', source_id=str(page.get('pageid') or title),
            title=title, creator=field('Artist') or field('Credit'),
            licence_code=licence_name,
            licence_url=field('LicenseUrl'),
            attribution_text='', landing_page_url=str(info.get('descriptionurl') or ''),
            file_url=str(info.get('url') or '').split('?')[0],
            thumb_url=str(info.get('thumburl') or '').split('?')[0],
            width=int(info.get('width') or 0), height=int(info.get('height') or 0),
            mime=str(info.get('mime') or ''),
            description=field('ImageDescription'),
            tags=[title] + field('ImageDescription').split()[:12]))
    return out


def _one_provider(settings, query: str, depth: int,
                  name: str) -> tuple[list[Candidate], dict[str, str]]:
    """Ask one provider. Returns its candidates and the report row, and never raises.

    Every failure mode is a report row, not an exception: one API being down is not a reason
    to tell a learner there are no photographs of photosynthesis.
    """
    try:
        if name == 'openverse':
            hits = _search_openverse(settings, query, depth)
        elif name == 'wikimedia':
            hits = _search_wikimedia(settings, query, depth)
        elif name == 'met':
            hits = _search_met(settings, query, depth)
        elif name == 'nasa':
            hits = _search_nasa(settings, query, depth)
        else:
            return [], {'provider': name, 'status': 'unknown provider'}
        return hits, {'provider': name, 'status': 'ok', 'results': str(len(hits))}
    except httpx.HTTPStatusError as exc:
        # Separate a *policy refusal* from a network failure. They used to arrive as the same
        # "unavailable", which sent a reviewer looking for a connection fault when the
        # provider had answered, promptly and correctly, that this client may not call it.
        # Wikimedia returns 403 for a User-Agent with no contact route.
        code = exc.response.status_code if exc.response is not None else 0
        status = ('refused_agent_policy' if code in {401, 403}
                  else f'unavailable: HTTP {code}')
        return [], {'provider': name, 'status': status}
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        return [], {'provider': name, 'status': f'unavailable: {type(exc).__name__}'}


def _search_all(settings, query: str, depth: int,
                providers: Sequence[str]) -> list[tuple[str, list[Candidate], dict[str, str]]]:
    """Run :func:`_one_provider` for every provider, concurrently, in the declared order.

    Concurrent because the providers are independent and one slow API must not be the price
    of every search. Ordered because the report is read by an operator comparing runs, and a
    payload whose row order depends on which API answered first is not comparable.
    """
    names = list(providers)
    if len(names) <= 1:
        out = []
        for name in names:
            hits, row = _one_provider(settings, query, depth, name)
            out.append((name, hits, row))
        return out
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=min(4, len(names)),
                            thread_name_prefix='media-search') as pool:
        futures = [pool.submit(_one_provider, settings, query, depth, name) for name in names]
        # An unexpected exception is *not* converted into a report row here. ``_one_provider``
        # already turns every failure it can name into one, and anything else means the search
        # did not happen - which ``fetch`` reports as ``unavailable``. Swallowing it here made
        # a broken transport look like "the search found nothing", the same false statement
        # the agent-policy fix had to remove.
        return [(name, *future.result()) for name, future in zip(names, futures)]


def search(settings, query: str, *, depth: int = SEARCH_DEPTH,
           providers: Sequence[str] = PROVIDERS) -> dict[str, Any]:
    """Search every requested provider and return candidates with their rights position.

    A provider that fails is reported and skipped rather than failing the whole search: one
    API being down is not a reason to tell a learner there are no images of photosynthesis.
    """
    query = ' '.join((query or '').split())
    if not query:
        return {'query': '', 'candidates': [], 'providers': [], 'notes': ['Empty query.']}
    if not enabled(settings):
        return {'query': query, 'candidates': [], 'providers': [],
                'notes': ['Network media is disabled for this instance. Set '
                          'HARNESS_MEDIA_ENABLED=1 to allow it. The deterministic figure '
                          'remains available with no network at all.']}
    candidates: list[Candidate] = []
    report: list[dict[str, str]] = []
    # Providers are asked in parallel. They are independent by construction - a search hit is
    # a search hit whichever collection it came from - and the sequential loop made one slow
    # collection the cost of every concept: a 57-concept illustration pass spent most of its
    # half hour waiting on whichever API was slowest at that moment. The request count is
    # unchanged, so no provider sees more traffic than before; only our idle time goes away.
    # Order is restored below from ``providers``, so the payload a caller reads is identical.
    results = _search_all(settings, query, depth, providers)
    for name, hits, status in results:
        report.append(status)
        candidates.extend(hits)
    notes = ['A candidate is a search hit, not a cleared asset. Nothing is downloaded until '
             'its own licence has been classified and cleared.']
    if not contact_configured(settings):
        notes.append(
            'HARNESS_MEDIA_CONTACT is unset, so this instance reports the reserved placeholder '
            f'contact {DEFAULT_MEDIA_CONTACT!r}. Wikimedia\'s API policy refuses a User-Agent '
            'with no reachable contact, and a refusal there looks exactly like "Commons has no '
            'photograph of this concept". Set it to the operator\'s real address.')
    blocked = [row for row in report if row.get('status', '') == 'refused_agent_policy']
    if any(row.get('provider') == 'wikimedia' for row in blocked):
        notes.append(
            'Wikimedia refused this client (agent policy). That is not an empty collection: '
            'it is the User-Agent contact being absent or unacceptable, and it looks exactly '
            'like "Commons has no photograph of this concept".')
    if 'openverse' in providers and not (getattr(settings, 'openverse_client_id', '')
                                         and getattr(settings, 'openverse_client_secret', '')):
        notes.append(
            f'Openverse is running unauthenticated, which its own documentation caps at '
            f'{OPENVERSE_ANON_LIMITS["per_minute"]} requests/minute and '
            f'{OPENVERSE_ANON_LIMITS["per_day"]} requests/day. Credentials lift that to '
            f'10,000/day; until then a heavy lesson can exhaust the daily allowance.')
    return {'query': query, 'candidates': [_classify(c) for c in candidates],
            'providers': report, 'notes': notes,
            'excluded_providers': dict(EXCLUDED_PROVIDERS)}


def _classify(candidate: Candidate) -> Candidate:
    """Attach this project's licence class and the local-storage verdict."""
    klass = policy.classify_licence(candidate.licence_code)
    candidate.licence_class = klass.value if klass else 'unknown'
    candidate.locally_storable = bool(klass and klass in policy.LOCALLY_STORABLE)
    if klass is None:
        candidate.rejected = (f'Licence {candidate.licence_code!r} is not a code this project '
                              f'has classified; an unknown licence is never assumed permissive.')
    elif not candidate.locally_storable:
        candidate.rejected = (f'Licence class {klass.value}: this project may link to or embed '
                              f'the asset but may not cache a copy of it.')
    return candidate


def _tokens(text: str) -> set[str]:
    import re
    words = re.split(r'[^a-z0-9]+', (text or '').casefold())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def lexical_overlap(query: str, *fields: str) -> float:
    """Fraction of the query's content words that appear in the asset's own metadata.

    The cheapest available defence against a confident wrong result. It is a *recall*
    measure, so the threshold is deliberately low: this filter exists to remove obvious
    nonsense, not to rank taste.

    Recall alone is not enough, which is what :func:`head_mentioned` adds: covering half of
    a two-word title is one word, and one shared word is what a coincidence looks like.
    """
    wanted = _tokens(query)
    if not wanted:
        return 1.0
    have = set()
    for value in fields:
        have |= _tokens(value)
    return len(wanted & have) / len(wanted)


#: Suffixes stripped before two words are compared, longest first. For this purpose
#: "taxation"/"tax", "externalities"/"external" and "curves"/"curve" are the same word: a
#: photograph captioned with the plural is a photograph of the concept. Without it, a whole
#: class of correct assets was refused for being inflected.
_SUFFIXES = ('ational', 'ations', 'ation', 'ities', 'ity', 'ions', 'ion', 'ings', 'ing',
             'ies', 'es', 'ed', 'al', 's', 'ly')


def _root(word: str) -> str:
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[:-len(suffix)]
    return word


def _same_term(left: str, right: str) -> bool:
    """Whether two stripped words name the same thing.

    Equality of roots, and nothing looser. A prefix rule was tried and removed the same day:
    it matched ``infographic`` against ``information``, so a chart captioned "Balance of
    power graph" - tagged *infographics* - was attached to a lesson on asymmetric
    information. Two words that merely start alike are not the same word.
    """
    return left == right


#: Pairs of phrases that cannot describe the same case. Measured, not imagined:
#:
#: * the long-run lesson on monopolistic competition was illustrated with a *short-run*
#:   equilibrium diagram, and entry and exit - the whole difference - are absent from it;
#: * the lesson on asymmetric information was illustrated with a graph whose own description
#:   says "Balance of Power with **Perfect** Information", i.e. the case the concept is
#:   defined against.
#:
#: Each entry is (what the query is about, the opposite a title may claim). A title that
#: claims the opposite *and not* the query's own phrase is refused.
_CONTRASTS = (('long run', 'short run'),
              ('asymmetric information', 'perfect information'),
              ('asymmetric information', 'symmetric information'),
              ('imperfect information', 'perfect information'))


def _normalised(text: str) -> str:
    return ' '.join(str(text or '').casefold().replace('-', ' ').replace('–', ' ').split())


def contradicts(query: str, *fields: str) -> tuple[str, str] | None:
    """The case the asset is on the wrong side of, as ``(asked, claimed)``, or ``None``.

    Separate from :func:`head_mentioned` because it is a different failure: the asset *is*
    about the concept's subject and is about the opposite case. A title that says "short run"
    under a question about the long run is not a relevance near-miss, it is a wrong answer
    with a credit line - and the more precise the asset, the more convincingly it teaches the
    wrong thing.
    """
    asked = _normalised(query)
    text = _normalised(' '.join(str(value or '') for value in fields))
    for mine, theirs in _CONTRASTS:
        if mine in asked and theirs in text and mine not in text:
            return mine, theirs
    return None


def _ordered_tokens(text: str) -> list[str]:
    import re
    words = re.split(r'[^a-z0-9]+', (text or '').casefold())
    return [w for w in words if len(w) > 2 and w not in _STOPWORDS]


def head_mentioned(query: str, *fields: str) -> bool:
    """Whether the asset's own words mention what the query is *about*.

    English noun phrases put their head last - "asymmetric **information**", "short-run cost
    **curves**", "tragedy of the **commons**" - so the last content word is the term the
    query cannot do without. Measured on the AP Microeconomics illustration pass, dropping
    this test let a photograph titled "Asymmetric Ashes (artist's impression)" illustrate
    asymmetric information and a 1907 gyroscope car illustrate short-run cost curves: both
    shared exactly one word with the concept and both carried a real credit line, which is
    what makes a wrong image worse than no image.

    A query with no content words has no head to check, and is left to the overlap score.
    """
    ordered = _ordered_tokens(query)
    if not ordered:
        return True
    head = _root(ordered[-1])
    haystack = ' '.join(str(value or '') for value in fields).casefold()
    if head in haystack:
        return True
    return any(_same_term(_root(word), head) for word in _tokens(haystack))


def filter_candidates(candidates: Iterable[Candidate], query: str, *,
                      min_width: int = MIN_WIDTH, min_height: int = MIN_HEIGHT,
                      min_overlap: float = 0.5,
                      support: str = '') -> tuple[list[Candidate], list[Candidate]]:
    """Split candidates into (accepted, rejected), annotating every rejection.

    Measurable rejection reasons only. "This looks wrong" is not a reason a reviewer can
    check, so it is not one this function is allowed to give.

    ``support`` is optional extra context - typically the concept's own summary - used only
    to *order* the accepted candidates, never to reject one. A candidate that mentions the
    summary's vocabulary is preferred over one that only matches the query, which is how a
    search for "osmosis" puts the biology above the power station without making the
    summary a requirement that a curated asset could fail. Empty ``support`` leaves the
    ordering exactly as it was.

    A **short query needs total coverage**. "Asymmetric information" has two content words,
    so half of it is one word, and a single word is what a coincidence looks like: a heritage
    photograph of "The Old Coach House" cleared it on the tag *information*. A long query
    cannot be covered completely and is judged by ``min_overlap`` as before, which is why the
    rule is graded rather than raised everywhere - demanding 100% of "long-run average total
    cost and economies of scale" would refuse the one asset that is exactly about it.
    """
    words = _tokens(query)
    required = 1.0 if len(words) <= 2 else min_overlap
    accepted, rejected = [], []
    for candidate in candidates:
        # Re-derive the verdict here from the licence *code*, not from a class a caller may
        # have supplied. The gate has to hold at the point of the decision, not only at the
        # earlier one: a caller that assembles candidates itself (a cache read, a test, a
        # future provider) must not be able to hand this function a candidate whose licence
        # was never classified - or was mis-classified - and have it pass on size grounds.
        candidate = _classify(candidate)
        if candidate.rejected:
            rejected.append(candidate)
            continue
        if not candidate.file_url:
            candidate.rejected = 'No direct file URL was supplied.'
        elif candidate.width and candidate.width < min_width:
            candidate.rejected = f'Too narrow for a lesson ({candidate.width}px < {min_width}px).'
        elif candidate.height and candidate.height < min_height:
            candidate.rejected = f'Too short for a lesson ({candidate.height}px < {min_height}px).'
        elif candidate.mime and normalise_mime(candidate.mime) not in IMAGE_MIMES and \
                not normalise_mime(candidate.mime).startswith('image/'):
            candidate.rejected = f'Not a displayable image type ({candidate.mime}).'
        else:
            aspect = (candidate.width / candidate.height) if candidate.height else 1.0
            if candidate.height and not (MIN_ASPECT <= aspect <= MAX_ASPECT):
                candidate.rejected = (f'Aspect ratio {aspect:.2f} is outside the range a lesson '
                                      f'layout can show ({MIN_ASPECT}..{MAX_ASPECT}).')
            else:
                words = (candidate.title, candidate.description, ' '.join(candidate.tags))
                # What the asset *is*, as opposed to what someone wrote about it: the title
                # and the tags. The description is deliberately absent from every test below
                # - see the note on the head-term check.
                identity = (candidate.title, ' '.join(candidate.tags))
                overlap = lexical_overlap(query, *words)
                opposed = contradicts(query, *identity)
                if overlap < required:
                    candidate.rejected = (
                        f'Only {overlap:.0%} of the query words appear in the asset\'s own '
                        f'title, description or tags; a full-text image search returns '
                        f'confident irrelevant hits and this one is not about {query!r}.')
                elif opposed:
                    candidate.rejected = (
                        f'The query is about {opposed[0]!r} and the asset\'s own words claim '
                        f'{opposed[1]!r} - the case the concept is defined against. That is a '
                        f'wrong answer with a credit line, not a near miss.')
                elif not head_mentioned(query, *identity):
                    # Deliberately *not* the description. Measured on the second AP Micro pass:
                    # a topographic map of Libya cleared "tragedy of the commons" because its
                    # Commons description says "commons.wikimedia.org", a photograph of a
                    # street cleared "price ceilings and floors" because the building has
                    # floors, and a 1907 aircraft cleared "perfect competition" on the word
                    # "characteristics" in a museum's cataloguing note. A free-text
                    # description mentions everything; the title and the tags say what the
                    # asset *is*, which is the question being asked.
                    candidate.rejected = (
                        f'The asset mentions some of {query!r} but not the term the concept '
                        f'turns on ({_ordered_tokens(query)[-1]!r}) in its title or tags; a '
                        f'coincidental word is how a confident irrelevant photograph gets a '
                        f'real credit line.')
        (rejected if candidate.rejected else accepted).append(candidate)
    if support:
        accepted.sort(key=lambda c: (-lexical_overlap(support, c.title, c.description,
                                                      ' '.join(c.tags)),
                                     -(c.width * c.height), c.source, c.source_id))
    else:
        accepted.sort(key=lambda c: (-(c.width * c.height), c.source, c.source_id))
    return accepted, rejected


# --------------------------------------------------------------------- acquiring

def _load_manifest(settings) -> dict[str, dict[str, Any]]:
    path = manifest_path(settings)
    if not path.exists():
        return {}
    out: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get('sha256'):
            out[str(row['sha256'])] = row
    return out


def _append_manifest(settings, asset: ImageAsset) -> None:
    path = manifest_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(asset.to_dict(), ensure_ascii=False) + '\n')


def cached_assets(settings) -> list[dict[str, Any]]:
    """Everything in the cache, newest first. Used by the transparency panel."""
    rows = list(_load_manifest(settings).values())
    rows.sort(key=lambda r: float(r.get('fetched_at') or 0), reverse=True)
    return rows


_MIME_MAGIC = (
    (b'\x89PNG\r\n\x1a\n', 'image/png', '.png'),
    (b'\xff\xd8\xff', 'image/jpeg', '.jpg'),
    (b'GIF8', 'image/gif', '.gif'),
)


def _sniff_mime(body: bytes) -> tuple[str, str]:
    for magic, mime, ext in _MIME_MAGIC:
        if body.startswith(magic):
            return mime, ext
    if len(body) > 12 and body[:4] == b'RIFF' and body[8:12] == b'WEBP':
        return 'image/webp', '.webp'
    return '', '.bin'


def store_bytes(settings, body: bytes, *, sha: str | None = None,
                title: str = '', source: str = 'lesson_bundle',
                licence_code: str = '', licence_class: str = '',
                attribution_text: str = '', creator: str = '') -> int:
    """Cache image bytes under their content hash and index them in the manifest.

    Used by the lesson-bundle import path: the bundle ships the bytes it was
    exported with, and this restores them as first-class cache entries so the
    bytes route serves them exactly like any licence-cleared download. A sha
    already in the manifest is a no-op (content addressing dedupes for free).
    Returns 1 when a new entry was stored, 0 otherwise.

    The licence fields exist for bytes this instance *produced* rather than
    fetched: a generated illustration has no third-party rights, and the manifest
    row is where that is said, so every surface that reads the manifest shows
    the same "generated, no third-party licence" line instead of a blank one.
    """
    digest = sha or hashlib.sha256(body).hexdigest()
    if len(digest) != 64 or not all(c in '0123456789abcdef' for c in digest):
        return 0
    manifest = _load_manifest(settings)
    if digest in manifest:
        return 0
    mime, ext = _sniff_mime(body)
    if not mime:
        return 0  # only images belong in this cache; anything else is refused
    root = cache_root(settings)
    root.mkdir(parents=True, exist_ok=True)
    target = root / f'{digest}{ext}'
    if not target.exists():
        target.write_bytes(body)
    asset = ImageAsset(
        source=source, source_id=digest[:24], query='', title=title or digest[:12],
        creator=creator, licence_code=licence_code, licence_class=licence_class,
        licence_url='',
        attribution_text=attribution_text, landing_page_url='', file_url='',
        cache_path=str(Path('media') / 'images' / target.name),
        sha256=digest, bytes=len(body), width=0, height=0, mime=mime,
        description='', fetched_at=time.time(),
        alt_text=title or 'Image restored from a lesson bundle')
    _append_manifest(settings, asset)
    return 1


def attribute(candidate: Candidate, title: str) -> str:
    """Build the attribution string when the provider did not supply one.

    Wikimedia gives the pieces rather than the sentence, so the sentence is assembled here
    in the order CC licences expect: work, author, licence.
    """
    if candidate.attribution_text:
        return candidate.attribution_text
    creator = candidate.creator or 'Unknown author'
    licence = candidate.licence_code or 'licence unspecified'
    parts = [f'"{title}"', f'by {creator}', f'— {licence}']
    if candidate.licence_url:
        parts.append(f'({candidate.licence_url})')
    if candidate.landing_page_url:
        parts.append(f'via {urlparse(candidate.landing_page_url).netloc or candidate.source}')
    return ' '.join(parts)


def _guess_extension(mime: str, url: str) -> str:
    table = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp',
             'image/gif': '.gif'}
    if mime in table:
        return table[mime]
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix if suffix in {'.jpg', '.jpeg', '.png', '.webp', '.gif'} else '.jpg'


def _download_bytes(settings, url: str) -> tuple[bytes, str]:
    """Stream one file into memory under the byte cap. Raises on any failure.

    Shared by ``acquire`` and ``fetch`` so the size guard and the redirect policy cannot
    drift apart between the single-image and multi-image paths.
    """
    with _client(settings) as client:
        with client.stream('GET', url) as response:
            response.raise_for_status()
            declared = int(response.headers.get('content-length') or 0)
            if declared and declared > MAX_BYTES:
                raise ValueError(f'Declared size {declared} exceeds the {MAX_BYTES} cap')
            chunks, total = [], 0
            for chunk in response.iter_bytes(65536):
                total += len(chunk)
                if total > MAX_BYTES:
                    raise ValueError(f'Download exceeded the {MAX_BYTES} byte cap')
                chunks.append(chunk)
            body = b''.join(chunks)
            mime = (response.headers.get('content-type') or '').split(';')[0].strip()
    return body, mime


def _cache_download(settings, candidate: Candidate, body: bytes, mime: str, query: str,
                    alt_text: str, root: Path, manifest: dict[str, dict[str, Any]],
                    *, title_fallback: str = '') -> tuple[dict[str, Any], str]:
    """Persist one downloaded body and index it. Returns ``(row, outcome)``.

    Content addressing dedupes for free: the same photograph is on Flickr, on Commons and
    in Openverse, and caching it three times is three times the disk for one visible
    picture. ``manifest`` is updated in place so a second identical body inside the same
    batch dedupes against the first rather than being written twice.
    """
    digest = hashlib.sha256(body).hexdigest()
    if digest in manifest:
        existing = manifest[digest]
        existing['query'] = query
        return existing, 'hit_deduplicated'
    title = candidate.title or title_fallback or query
    asset = ImageAsset(
        source=candidate.source, source_id=candidate.source_id, query=query, title=title,
        creator=candidate.creator, licence_code=candidate.licence_code,
        licence_class=candidate.licence_class, licence_url=candidate.licence_url,
        attribution_text=attribute(candidate, title),
        landing_page_url=candidate.landing_page_url, file_url=candidate.file_url,
        cache_path=str(Path('media') / 'images' /
                       f'{_signature(query, candidate.source, candidate.source_id)}'
                       f'{_guess_extension(mime or candidate.mime, candidate.file_url)}'),
        sha256=digest, bytes=len(body), width=candidate.width, height=candidate.height,
        mime=mime or candidate.mime, description=candidate.description,
        fetched_at=time.time(),
        alt_text=alt_text or f'Photograph illustrating {title}')
    target = Path(settings.data_dir) / asset.cache_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)
    _append_manifest(settings, asset)
    row = asset.to_dict()
    manifest[digest] = row
    return row, 'downloaded'


#: How far down the ranked list one fetch will walk before giving up.
#:
#: The ranking *is* the judgement about relevance: a candidate ten places down was not
#: chosen by it, it was left over. Walking the whole list is how a lesson came to be
#: illustrated with a photograph of a band called "The Cell Theory" - the eight better
#: candidates ahead of it had been rate-limited by the host, the loop skipped past them
#: silently, and the ninth was downloaded and credited as a biology figure. Four attempts
#: is enough to absorb one dead host or a couple of 404s and still stop before the ranking
#: has been abandoned.
MAX_DOWNLOAD_ATTEMPTS = 4


def _rate_limited(exc: Exception) -> bool:
    """Whether a failure means "this host is asking us to slow down" rather than "this file".

    The distinction matters: a 429 is about the instance, not the candidate, so trying the
    next nine files from the same host is both rude and futile.
    """
    response = getattr(exc, 'response', None)
    return getattr(response, 'status_code', None) == 429


def _download_ranked(settings, accepted: Sequence[Candidate], *, query: str, alt_text: str,
                     root: Path, manifest: dict[str, dict[str, Any]], limit: int,
                     title_fallback: str = '') -> tuple[list[dict[str, Any]],
                                                        list[dict[str, str]], str, int]:
    """Download from the top of the ranked list, and stop honestly.

    Returns ``(rows, skipped, stop, deduped)``. ``skipped`` is every candidate that was
    tried and failed, with its reason - reported even when the fetch succeeded, because "we
    took the fourth choice" is a fact the caller needs. ``stop`` is ``''``,
    ``'attempt_cap'`` or ``'rate_limited'``, and it is what turns an empty result into an
    argued one.
    """
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    stop = ''
    deduped = 0
    attempts = 0
    for candidate in accepted:
        if len(rows) >= limit:
            break
        if attempts >= MAX_DOWNLOAD_ATTEMPTS:
            stop = 'attempt_cap'
            break
        attempts += 1
        try:
            body, mime = _download_bytes(settings, candidate.file_url)
        except (httpx.HTTPError, ValueError) as exc:
            skipped.append({'title': candidate.title, 'source': candidate.source,
                            'why': f'{type(exc).__name__}: {str(exc)[:120]}'})
            if _rate_limited(exc):
                stop = 'rate_limited'
                break
            continue
        if not body:
            skipped.append({'title': candidate.title, 'source': candidate.source,
                            'why': 'empty response body'})
            continue
        row, outcome = _cache_download(settings, candidate, body, mime or candidate.mime,
                                       query, alt_text, root, manifest,
                                       title_fallback=title_fallback)
        if outcome == 'hit_deduplicated':
            deduped += 1
        rows.append(row)
    return rows, skipped, stop, deduped


def _stop_note(stop: str, skipped: Sequence[Mapping[str, str]]) -> str:
    """One sentence explaining why the fetch stopped where it did."""
    if stop == 'rate_limited':
        return (f'The image host rate-limited this instance (HTTP 429) after '
                f'{len(skipped)} attempt(s), so the remaining candidates were not tried. '
                f'A lower-ranked image is not used as a substitute.')
    if stop == 'attempt_cap':
        return (f'{len(skipped)} better-ranked candidate(s) could not be downloaded; the '
                f'fetch stopped after {MAX_DOWNLOAD_ATTEMPTS} attempts rather than '
                f'taking a lower-ranked image. The skips name each one.')
    return ''


def acquire(settings, query: str, *, providers: Sequence[str] = PROVIDERS,
            depth: int = SEARCH_DEPTH, min_width: int = MIN_WIDTH,
            min_height: int = MIN_HEIGHT, min_overlap: float = 0.5,
            alt_text: str = '', support: str = '') -> dict[str, Any]:
    """Search, clear, download and cache one image for a query.

    Returns a dict that always names an outcome. The failure modes are all *reported*, not
    raised, because a lesson that cannot get a photograph must still be able to render.
    """
    result = search(settings, query, depth=depth, providers=providers)
    accepted, rejected = filter_candidates(result['candidates'], result['query'],
                                           min_width=min_width, min_height=min_height,
                                           min_overlap=min_overlap, support=support)
    payload: dict[str, Any] = {
        'query': result['query'], 'providers': result['providers'], 'notes': list(result['notes']),
        'seen': len(result['candidates']), 'accepted': len(accepted), 'rejected': len(rejected),
        'rejections': [{'source': c.source, 'title': c.title, 'why': c.rejected}
                       for c in rejected][:12],
        'asset': None,
        'cached': False,
    }
    # The disabled check comes before the empty-result check on purpose. Both end with no
    # image, but they are different facts: "the operator turned this off" is not "the search
    # found nothing", and reporting the second when the first is true makes a configuration
    # state look like a content problem.
    if not enabled(settings):
        payload['outcome'] = 'network_disabled'
        payload['notes'].append('Network media is disabled for this instance, so no search was '
                                'made and nothing was downloaded.')
        return payload
    if not accepted:
        payload['outcome'] = 'no_cleared_candidate'
        payload['notes'].append(
            'No candidate both cleared the licence gate and matched the query. Nothing was '
            'downloaded, and no image is claimed for this concept.')
        return payload

    root = cache_root(settings)
    root.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest(settings)
    rows, skipped, stop, deduped = _download_ranked(
        settings, accepted, query=result['query'], alt_text=alt_text, root=root,
        manifest=manifest, limit=1, title_fallback=result['query'])
    payload['skipped'] = skipped
    payload['stop'] = stop
    if rows:
        payload['asset'] = rows[0]
        payload['cached'] = True
        payload['outcome'] = 'hit_deduplicated' if deduped else 'downloaded'
        if deduped:
            payload['notes'].append(
                'An identical image was already cached (same SHA-256); the existing copy and '
                'its original attribution were reused rather than stored again.')
            payload['duplicate_of'] = rows[0].get('source')
        return payload

    payload['outcome'] = 'rate_limited' if stop == 'rate_limited' else 'all_downloads_failed'
    note = _stop_note(stop, skipped)
    if note:
        payload['notes'].append(note)
    payload['notes'].append('No image is claimed for this concept; the deterministic figure '
                            'remains available.')
    return payload


def find_image(settings, concept_title: str, *, summary: str = '',
               alt_text: str = '') -> dict[str, Any]:
    """The concept-facing entry point: build a query from a concept, then acquire one image.

    The query is derived from the concept's own title and summary rather than hand-written,
    so a lesson for a concept nobody curated still has a chance of a real photograph - and
    the lexical filter above is what stops that generality from turning into noise.
    """
    title = ' '.join((concept_title or '').split())
    if not title:
        return {'outcome': 'no_concept', 'asset': None,
                'notes': ['No concept title supplied.']}
    query = _concept_query(title, summary)
    payload = acquire(settings, query, alt_text=alt_text or f'Photograph of {title}',
                      support=summary)
    payload['concept_title'] = title
    if payload.get('asset') is None and payload.get('outcome') == 'no_cleared_candidate':
        # One widening, and only after a refusal that means "the search ran and everything it
        # found was rejected" - never after ``network_disabled``, where a second attempt would
        # only refuse again, or after a download failure, where the picture exists.
        head = _head_phrase(title)
        if head:
            widened = acquire(settings, head, alt_text=alt_text or f'Photograph of {title}',
                              support=summary)
            widened['concept_title'] = title
            widened['queries'] = [query, head]
            widened['notes'] = [
                f'Nothing searchable was found for the whole title, so the search was widened '
                f'to its subject ({head!r}) - the part a photograph can show, rather than what '
                f'the lesson says about it.',
                *(widened.get('notes') or []),
            ]
            return widened
    return payload


# --------------------------------------------------------------------- explicit fetch

def _valid_sha(value: Any) -> bool:
    text = str(value or '')
    return len(text) == 64 and all(c in '0123456789abcdef' for c in text)


def _head_phrase(title: str) -> str:
    """The *subject* of a lesson title, without the qualifier that follows "and".

    Curriculum titles are often of the form "Blood vessels and their adaptation": the head is
    what a photograph can show, and the tail is what the lesson *says* about it. Searching the
    whole title fails in a way that looks like an empty library — measured on this lesson, 12
    candidates, 0 accepted, every rejection for the same reason: the relevance gate requires
    the term the concept turns on, and that term is "adaptation", which no photograph of a
    blood vessel says about itself. Searching "Blood vessels" returns 40 candidates, 11
    accepted, and the picture that lands is "Blood vessels structure.jpg".

    Two conditions keep the widening from making things worse:

    * **The head must still be a phrase** (two or more words). "Supply and demand" would reduce
      to "Supply", and a single generic word is exactly where full-text image search returns
      its most confident nonsense — the gate would then cheerfully accept a photograph of a
      supply ship for an economics lesson. A one-word head is left to the full title.
    * **It only runs when the full title found nothing**, so a title that already works is
      never rewritten and never costs a second search.

    Returns ``''`` when there is nothing to widen to.
    """
    stripped = ' '.join((title or '').split())
    head = re.split(r'\s+(?:and|&)\s+', stripped, maxsplit=1)[0].strip()
    if head == stripped or not head:
        return ''
    if len(_ordered_tokens(head)) < 2:
        return ''
    return head


def _concept_query(title: str, summary: str = '') -> str:
    """The search phrase for a concept: its own title, and nothing else.

    This used to append the summary's first clause to a single-word title, on the theory
    that "cytoplasm" alone is where full-text image search returns its most confident
    nonsense. Measured against the live providers, the theory was wrong in the way that
    matters: ``"Cytoplasm The aqueous interior of the cell where most metabolic reactions
    take place"`` returns **zero** candidates, while ``"Cytoplasm"`` returns 41 and
    ``"Mitosis"`` returns 41. A ten-word phrase is not a query these APIs answer.

    The disambiguation the clause was there to provide still happens, one layer down: the
    summary travels as ``support`` into :func:`filter_candidates`, where it *ranks*
    candidates that mention it above ones that do not, without being a requirement they
    must satisfy. "Osmosis" therefore still surfaces the biology before the power station,
    and a concept whose summary nobody wrote is not penalised for it.
    """
    return ' '.join((title or '').split())


def _support_words(summary: str, limit: int = 6) -> list[str]:
    """Distinctive words from a summary, for ranking rather than for querying."""
    words = _tokens(summary)
    return sorted(words)[:limit]


def fetch(settings, query: str, *, concept_id: str = '', course_id: str = '',
          count: int = 1, providers: Sequence[str] = PROVIDERS,
          alt_text: str = '', support: str = '') -> dict[str, Any]:
    """Search, clear, download and cache up to ``count`` images for one query.

    This is the acquisition entry point a *person* triggers, as distinct from
    ``find_image`` (one image derived from a concept). It always returns a dict naming an
    outcome -- ``downloaded``, ``hit_deduplicated``, ``no_cleared_candidate``,
    ``all_downloads_failed`` or ``network_disabled`` -- and never raises, because the
    module's contract is that an offline instance is a reported state, not a crash. Every
    rejection travels in ``rejections`` so an empty result can be argued with.

    ``support`` is context that *ranks* cleared candidates without gating them; see
    :func:`filter_candidates`.
    """
    wanted = max(1, min(int(count or 1), MAX_FETCH_PER_CALL))
    try:
        return _fetch(settings, query, concept_id=concept_id, course_id=course_id,
                      wanted=wanted, providers=providers, alt_text=alt_text,
                      support=support)
    except Exception as exc:  # noqa: BLE001 - the offline promise covers every provider
        # The docstring's promise is load-bearing: a lesson that cannot get a photograph
        # must still render, so an unexpected provider or transport failure becomes a
        # reported refusal rather than an exception the lesson route would have to catch.
        return {'query': ' '.join((query or '').split()), 'concept_id': str(concept_id or ''),
                'course_id': str(course_id or ''), 'outcome': 'unavailable', 'assets': [],
                'asset': None, 'cached': False, 'seen': 0, 'accepted': 0, 'rejected': 0,
                'rejections': [], 'providers': [], 'requested': wanted,
                'cap': MAX_FETCH_PER_CALL,
                'notes': [f'The image service could not be reached ({type(exc).__name__}); '
                          f'nothing was downloaded and no image is claimed.']}


def _fetch(settings, query: str, *, concept_id: str, course_id: str, wanted: int,
           providers: Sequence[str], alt_text: str,
           support: str = '') -> dict[str, Any]:
    result = search(settings, query, providers=providers)
    accepted, rejected = filter_candidates(result['candidates'], result['query'],
                                           support=support)
    payload: dict[str, Any] = {
        'query': result['query'], 'concept_id': str(concept_id or ''),
        'course_id': str(course_id or ''), 'providers': result['providers'],
        'notes': list(result['notes']), 'seen': len(result['candidates']),
        'accepted': len(accepted), 'rejected': len(rejected),
        'rejections': [{'source': c.source, 'title': c.title, 'why': c.rejected}
                       for c in rejected][:12],
        'assets': [], 'asset': None, 'cached': False, 'requested': wanted,
        'cap': MAX_FETCH_PER_CALL,
    }
    if not enabled(settings):
        payload['outcome'] = 'network_disabled'
        payload['notes'].append('Network media is disabled for this instance, so no search was '
                                'made and nothing was downloaded.')
        return payload
    if not accepted:
        payload['outcome'] = 'no_cleared_candidate'
        payload['notes'].append(
            'No candidate both cleared the licence gate and matched the query. Nothing was '
            'downloaded, and no image is claimed.')
        return payload

    root = cache_root(settings)
    root.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest(settings)
    assets, skipped, stop, deduped = _download_ranked(
        settings, accepted, query=result['query'], alt_text=alt_text, root=root,
        manifest=manifest, limit=wanted, title_fallback=result['query'])
    payload['assets'] = assets
    payload['asset'] = assets[0] if assets else None
    payload['cached'] = bool(assets)
    payload['skipped'] = skipped
    payload['stop'] = stop
    if assets:
        payload['outcome'] = 'hit_deduplicated' if deduped == len(assets) else 'downloaded'
        if deduped:
            payload['notes'].append(
                f'{deduped} of {len(assets)} images were already cached (identical SHA-256); '
                f'the existing copies and their original attributions were reused.')
        note = _stop_note(stop, skipped)
        if note:
            payload['notes'].append(note)
    else:
        payload['outcome'] = 'rate_limited' if stop == 'rate_limited' else 'all_downloads_failed'
        note = _stop_note(stop, skipped)
        if note:
            payload['notes'].append(note)
        payload['notes'].append('No candidate could be downloaded; nothing was cached and no '
                                'image is claimed.')
    return payload


# --------------------------------------------------------------------- lesson batch

#: Block kinds where a real photograph genuinely helps rather than competing with a
#: deterministic figure. A retrieval or reflection prompt is a question, and a photograph
#: beside a question is decoration; a core-idea or worked-example block is about something
#: that exists in the world and can be looked at.
_IMAGE_BEARING_KINDS = ('concept', 'worked_example')


def lesson_image_needs(*, title: str, summary: str = '', blocks: Sequence[Mapping[str, Any]] = (),
                       limit: int = MAX_LESSON_IMAGES) -> list[dict[str, Any]]:
    """Decide what photographs a lesson actually needs, keyed by block position.

    The lesson's own text is the only input: the concept title names the subject, and a
    block's title and body name the aspect of it that block is about. A block too thin to
    search on is skipped rather than given a generic query, because a generic query is
    exactly how an image search returns a confident wrong picture.
    """
    needs: list[dict[str, Any]] = []
    title = ' '.join(str(title or '').split())
    if not title:
        return needs
    # The concept photograph goes after the first block, so it illustrates the lesson
    # rather than pushing the core idea off the top of the page.
    needs.append({'slot': 'concept', 'block_index': 1,
                  'query': _concept_query(title, summary), 'support': summary,
                  'alt_text': f'Photograph illustrating {title}'})
    for index, block in enumerate(blocks or []):
        if len(needs) >= limit:
            break
        if not isinstance(block, Mapping):
            continue
        if str(block.get('kind') or '') not in _IMAGE_BEARING_KINDS:
            continue
        body = ' '.join(str(block.get('body') or '').split())
        if len(body.split()) < 8:
            continue
        # The query is the concept plus two *subject* words from the block's body. It used
        # to be the block's title, which for an authored lesson is "Core idea" or "Worked
        # example" - a pedagogical label, not something an image search can answer. The
        # whole body travels as support so the ranking prefers the aspect this block is
        # about.
        aspect = ' '.join(_support_words(body, 2))
        # The *query* stays the concept title, for the reason measured in
        # :func:`_concept_query`: these search APIs AND their terms, so appending words
        # lowers recall to zero rather than narrowing it. The block's own body travels as
        # ``support`` and does the narrowing where narrowing is safe - in the ranking.
        needs.append({'slot': str(block.get('kind')), 'block_index': index,
                      'query': _concept_query(title), 'support': body or summary,
                      'alt_text': f'{title}: {aspect}' if aspect else title})
    return needs[:limit]


def fetch_for_lesson(settings, *, concept_id: str, title: str, summary: str = '',
                     blocks: Sequence[Mapping[str, Any]] = (), course_id: str = '',
                     limit: int = MAX_LESSON_IMAGES) -> dict[str, Any]:
    """Fetch the images a lesson needs and remember where each one belongs.

    The assignment is recorded so the lesson payload can carry the image on the next read
    without searching again. A need that finds nothing is reported with its rejections and
    no assignment is written, so a lesson that gained no photograph says why rather than
    looking as if nobody asked.
    """
    concept_id = str(concept_id or '').strip()
    if not concept_id:
        return {'concept_id': '', 'outcome': 'no_concept', 'images': [],
                'assigned': 0, 'cap': MAX_LESSON_IMAGES,
                'notes': ['No concept id was supplied.']}
    wanted = max(1, min(int(limit or 1), MAX_LESSON_IMAGES))
    needs = lesson_image_needs(title=title, summary=summary, blocks=blocks, limit=wanted)
    if not needs:
        return {'concept_id': concept_id, 'outcome': 'nothing_to_illustrate', 'images': [],
                'assigned': 0, 'cap': MAX_LESSON_IMAGES,
                'notes': ['This lesson names no subject a photograph could illustrate; the '
                          'deterministic figure remains available.']}
    images: list[dict[str, Any]] = []
    assignments: list[dict[str, Any]] = []
    for need in needs:
        found = fetch(settings, need['query'], concept_id=concept_id, course_id=course_id,
                      count=1, alt_text=need['alt_text'],
                      support=need.get('support') or summary)
        found_assets = found.get('assets') or []
        images.append({'slot': need['slot'], 'block_index': need['block_index'],
                       'query': need['query'], 'outcome': found.get('outcome'),
                       # ``seen`` separates "the search returned nothing" from "the results
                       # were refused". Both used to arrive as one sentence about the licence
                       # and relevance filter, which sent a reviewer to argue with a filter
                       # that had never seen a candidate.
                       'seen': found.get('seen'),
                       'accepted': found.get('accepted'),
                       'asset': found_assets[0] if found_assets else None,
                       'rejections': found.get('rejections') or [],
                       'notes': found.get('notes') or []})
        if found_assets:
            asset = found_assets[0]
            assignments.append({'block_index': need['block_index'], 'slot': need['slot'],
                                'sha256': asset.get('sha256'),
                                'caption': str(asset.get('description') or '')[:200]})
    if assignments:
        record_lesson_images(settings, concept_id, assignments)
    return {'concept_id': concept_id, 'outcome': 'ok' if assignments else 'no_images',
            'images': images, 'assigned': len(assignments), 'cap': MAX_LESSON_IMAGES,
            'notes': ['Each image carries its own author, licence and attribution; an image '
                      'that did not clear the gate is reported with its reason and is not '
                      'attached to the lesson.']}


# --------------------------------------------------------------------- lesson index

def lesson_index_path(settings) -> Path:
    return Path(settings.data_dir) / 'media' / 'lesson_images.jsonl'


def record_lesson_images(settings, concept_id: str, assignments: Sequence[Mapping[str, Any]]) -> None:
    """Append concept -> block image assignments. The newest assignment for a slot wins."""
    concept_id = str(concept_id or '').strip()
    if not concept_id or not assignments:
        return
    path = lesson_index_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = round(time.time(), 3)
    with path.open('a', encoding='utf-8') as handle:
        for item in assignments:
            sha = str(item.get('sha256') or '')
            if not _valid_sha(sha):
                continue
            handle.write(json.dumps({
                'concept_id': concept_id, 'block_index': int(item.get('block_index') or 0),
                'slot': str(item.get('slot') or ''), 'sha256': sha,
                'caption': str(item.get('caption') or '')[:200], 'at': now,
            }, ensure_ascii=False) + '\n')


def withdraw_lesson_images(settings, concept_id: str) -> None:
    """Withdraw every photograph assigned to a lesson, as a recorded fact.

    Re-running illustration must be able to take a picture *away*. The index is append-only
    with "newest row wins", so a concept whose new search clears nothing used to keep the
    photograph an earlier pass had attached - which is how a second, stricter pass would
    leave the wrong image in place while reporting that the concept had none. A tombstone is
    a row like any other, so the withdrawal is as auditable as the assignment was.
    """
    concept_id = str(concept_id or '').strip()
    if not concept_id:
        return
    path = lesson_index_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps({'concept_id': concept_id, 'slot': '*', 'withdrawn': True,
                                 'block_index': -1, 'sha256': '', 'at': round(time.time(), 3)},
                                ensure_ascii=False) + '\n')


def _load_lesson_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def lesson_image_assignments(settings, concept_id: str) -> list[dict[str, Any]]:
    """The current assignment per (slot, position) for a concept, oldest superseded.

    A later fetch for the same slot replaces the earlier one rather than stacking a second
    photograph into the same place. A withdrawal row removes what it covers, so "no
    photograph" is a state the index can hold rather than something only the absence of a
    row can express.
    """
    concept_id = str(concept_id or '').strip()
    path = lesson_index_path(settings)
    if not concept_id or not path.exists():
        return []
    latest: dict[str, dict[str, Any]] = {}
    for row in _load_lesson_rows(path):
        if row.get('concept_id') != concept_id:
            continue
        if row.get('withdrawn'):
            if str(row.get('slot') or '') == '*':
                latest.clear()
            else:
                latest.pop(f"{row.get('slot')}:{row.get('block_index')}", None)
            continue
        if not _valid_sha(row.get('sha256')):
            continue
        latest[f"{row.get('slot')}:{row.get('block_index')}"] = row
    return sorted(latest.values(), key=lambda r: int(r.get('block_index') or 0))


def _photograph_block(row: Mapping[str, Any], item: Mapping[str, Any]) -> dict[str, Any]:
    """One lesson photograph block, resolved against the live manifest row."""
    sha = str(row.get('sha256') or '')
    return {
        'type': 'image', 'kind': 'photograph',
        # ``src`` is the URL the bytes route serves; ``cache_path`` is kept for export,
        # where a data-directory file is what a bundle needs.
        'src': f'/api/v1/media/images/{sha}/bytes',
        'cache_path': str(row.get('cache_path') or ''),
        'cached': True, 'sha256': sha,
        'title': str(row.get('title') or ''),
        'alt': str(row.get('alt_text') or ''),
        'caption': str(item.get('caption') or row.get('description') or '')[:200],
        'credit': str(row.get('attribution_text') or ''),
        'licence': str(row.get('licence_code') or ''),
        'licence_class': str(row.get('licence_class') or ''),
        'licence_url': str(row.get('licence_url') or ''),
        'source': str(row.get('source') or ''),
        'source_url': str(row.get('landing_page_url') or ''),
        'creator': str(row.get('creator') or ''),
        'width': row.get('width', 0), 'height': row.get('height', 0),
    }


def lesson_photograph_blocks(settings, concept_id: str) -> list[dict[str, Any]]:
    """The photograph blocks a lesson should carry, resolved against the live manifest.

    An assignment whose bytes are no longer cached is dropped rather than rendered as a
    missing image: the manifest is the index of what this instance may serve, and a sha
    missing from it was never cleared (or has been deleted since).
    """
    manifest = _load_manifest(settings)
    out: list[dict[str, Any]] = []
    for item in lesson_image_assignments(settings, concept_id):
        row = manifest.get(str(item.get('sha256') or ''))
        if row is None:
            continue
        out.append({'block_index': int(item.get('block_index') or 0),
                    'slot': str(item.get('slot') or ''),
                    'block': _photograph_block(row, item)})
    return out


# ------------------------------------------------------------- attaching a single image

#: Manifest rows that never passed a rights gate. A clipboard paste and a bundle-restored
#: file are both real images with no verified licence: correct on a learner's own board,
#: wrong in a textbook, because a textbook block prints the credit line and a credit line
#: reading "source/licence not verified" is a rights problem rendered on the page.
_UNVERIFIED_SOURCES = frozenset({'clipboard_paste', 'lesson_bundle'})


def licence_verified(row: Mapping[str, Any]) -> tuple[bool, str]:
    """Whether a manifest row may be published as textbook content, and why not.

    The manifest is the only index of what this instance holds, so this is the check that
    stands between "an image is cached" and "an image may be printed in a book". It is
    deliberately about the *rights position*, not the pixels: an unverified image is still
    servable to the account that pasted it.
    """
    if not row:
        return False, 'The image is not in the local cache.'
    source = str(row.get('source') or '')
    if source in _UNVERIFIED_SOURCES:
        return False, (f'This image came from {source!r}, which never passed a licence gate. '
                       f'A textbook must print a real credit line, so it cannot be used.')
    klass = str(row.get('licence_class') or '').strip()
    if not klass or klass == 'unknown':
        return False, ('This image names no licence this project has classified, so its '
                       'rights position is unknown and it cannot be published.')
    if not str(row.get('attribution_text') or '').strip():
        return False, ('This image carries no attribution string. The credit line is a '
                       'condition of the licence, not decoration, so the image is refused.')
    return True, ''


def attach_image(settings, concept_id: str, *, title: str = '', summary: str = '',
                 sha256: str = '', query: str = '', block_index: int = 1,
                 slot: str = 'concept', caption: str = '',
                 alt_text: str = '') -> dict[str, Any]:
    """Put one real photograph into a lesson, at a chosen position.

    This is the single primitive behind "the tutor illustrates the textbook". It has two
    modes and they exist for different reasons:

    * ``sha256`` - attach an image that is *already* cached. The tutor searched with
      ``image_search``, chose one, and names it. Nothing is downloaded again, and the
      asset must already have cleared the licence gate.
    * ``query`` (or the concept's own title) - acquire and attach in one step, for when the
      caller knows what the lesson needs but not which asset.

    Both modes write the same assignment row the batch fetch writes, so a lesson served by
    ``GET /lessons/{id}`` carries the image with no special case. A refusal is a reported
    outcome with a reason, never an exception: a lesson that cannot get a photograph must
    still render.
    """
    concept_id = str(concept_id or '').strip()
    if not concept_id:
        return {'concept_id': '', 'attached': False, 'outcome': 'no_concept',
                'block': None, 'asset': None,
                'notes': ['No concept id was supplied.']}
    manifest = _load_manifest(settings)
    asset_row: dict[str, Any] | None = None
    chosen_query = ' '.join(str(query or '').split())
    if sha256:
        asset_row = manifest.get(str(sha256))
        ok, why = licence_verified(asset_row or {})
        if not ok:
            return {'concept_id': concept_id, 'attached': False,
                    'outcome': 'not_cached' if not asset_row else 'unlicensed',
                    'block': None, 'asset': None, 'sha256': str(sha256),
                    'notes': [why]}
    else:
        if not chosen_query:
            chosen_query = _concept_query(title, summary)
        if not chosen_query:
            return {'concept_id': concept_id, 'attached': False, 'outcome': 'no_query',
                    'block': None, 'asset': None,
                    'notes': ['No query, no sha256 and no concept title: there is nothing '
                              'to search for.']}
        existing = lesson_image_assignments(settings, concept_id)
        if (len(existing) >= MAX_LESSON_IMAGES
                and int(block_index) not in {int(r.get('block_index') or 0) for r in existing}):
            return {'concept_id': concept_id, 'attached': False, 'outcome': 'at_cap',
                    'block': None, 'asset': None, 'cap': MAX_LESSON_IMAGES,
                    'notes': [f'This lesson already carries {len(existing)} photograph(s), '
                              f'which is the cap. Replace one instead of adding another.']}
        found = fetch(settings, chosen_query, concept_id=concept_id, count=1,
                      alt_text=alt_text or f'Photograph illustrating {title or concept_id}',
                      support=summary)
        assets = found.get('assets') or []
        if not assets:
            return {'concept_id': concept_id, 'attached': False,
                    'outcome': str(found.get('outcome') or 'no_image'), 'block': None,
                    'asset': None, 'query': chosen_query,
                    'rejections': found.get('rejections') or [],
                    'notes': list(found.get('notes') or [])}
        asset_row = assets[0]
    digest = str((asset_row or {}).get('sha256') or '')
    record_lesson_images(settings, concept_id, [{
        'block_index': int(block_index), 'slot': slot, 'sha256': digest,
        'caption': caption or str((asset_row or {}).get('description') or '')[:200]}])
    # Resolve the block from the index that was just written rather than from the row we
    # happen to hold, so the caller receives exactly what the lesson route will serve.
    served = next((item['block'] for item in lesson_photograph_blocks(settings, concept_id)
                   if int(item['block_index']) == int(block_index)
                   and item['slot'] == slot), None)
    return {'concept_id': concept_id, 'attached': served is not None,
            'outcome': 'attached' if served else 'not_cached', 'block': served,
            'asset': asset_row, 'query': chosen_query, 'block_index': int(block_index),
            'slot': slot,
            'notes': ['The lesson now carries this photograph, with its author, licence and '
                      'attribution. It appears on the next read of the lesson.']}


def forget_lesson_images(settings, concept_id: str) -> int:
    """Drop every image assignment for a concept. Returns how many rows were removed.

    Called when a course is withdrawn: the assignment file is keyed by concept id and has
    no notion of a course, so a deleted course would otherwise leave rows pointing at
    concepts no lesson can reach. The file is append-only for writes, so a removal is a
    rewrite through a sibling temp file - a crash mid-rewrite must not truncate the index
    for every other course.
    """
    concept_id = str(concept_id or '').strip()
    path = lesson_index_path(settings)
    if not concept_id or not path.exists():
        return 0
    rows = _load_lesson_rows(path)
    kept = [row for row in rows if row.get('concept_id') != concept_id]
    removed = len(rows) - len(kept)
    if not removed:
        return 0
    staging = path.with_suffix('.jsonl.part')
    with staging.open('w', encoding='utf-8') as handle:
        for row in kept:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    staging.replace(path)
    return removed



# --------------------------------------------------------------------- account library

def ownership_path(settings) -> Path:
    return Path(settings.data_dir) / 'media' / 'image_owners.jsonl'


def record_ownership(settings, user_id: str, shas: Iterable[str], *, query: str = '',
                     concept_id: str = '') -> None:
    """Record which account fetched which cached image.

    Without this the library route would list every image the *instance* holds, which is
    not the same thing as the images this learner asked for - and on a shared instance it
    would hand one account another's fetches.
    """
    user_id = str(user_id or '').strip()
    if not user_id:
        return
    path = ownership_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = round(time.time(), 3)
    with path.open('a', encoding='utf-8') as handle:
        for sha in shas:
            if not _valid_sha(sha):
                continue
            handle.write(json.dumps({'user_id': user_id, 'sha256': str(sha),
                                     'query': str(query or ''), 'concept_id': str(concept_id or ''),
                                     'at': now}, ensure_ascii=False) + '\n')


def _load_ownership(settings) -> list[dict[str, Any]]:
    path = ownership_path(settings)
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get('user_id') and _valid_sha(row.get('sha256')):
            out.append(row)
    return out


def owned_shas(settings, user_id: str) -> set[str]:
    user_id = str(user_id or '')
    return {str(row['sha256']) for row in _load_ownership(settings)
            if str(row.get('user_id')) == user_id}


def claims(settings, sha: str) -> set[str]:
    """Every account that has this image in its library."""
    sha = str(sha or '')
    return {str(row.get('user_id')) for row in _load_ownership(settings)
            if str(row.get('sha256')) == sha}


def lesson_references(settings, sha: str) -> bool:
    """Whether any lesson assignment still points at this image."""
    sha = str(sha or '')
    if not _valid_sha(sha):
        return False
    path = lesson_index_path(settings)
    if not path.exists():
        return False
    return any(str(row.get('sha256')) == sha for row in _load_lesson_rows(path))


def release_ownership(settings, user_id: str, sha: str) -> int:
    """Drop one account's claim on an image. Returns how many claims were removed."""
    user_id, sha = str(user_id or ''), str(sha or '')
    path = ownership_path(settings)
    if not user_id or not _valid_sha(sha) or not path.exists():
        return 0
    kept, removed = [], 0
    for line in path.read_text(encoding='utf-8').splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            row = json.loads(stripped)
        except ValueError:
            continue
        if str(row.get('user_id')) == user_id and str(row.get('sha256')) == sha:
            removed += 1
            continue
        kept.append(stripped)
    if removed:
        path.write_text('\n'.join(kept) + ('\n' if kept else ''), encoding='utf-8')
    return removed


def library(settings, user_id: str, *, query: str = '') -> list[dict[str, Any]]:
    """This account's cached images, newest first, optionally filtered by a text query."""
    owned = owned_shas(settings, user_id)
    rows = [row for row in cached_assets(settings) if str(row.get('sha256')) in owned]
    needle = ' '.join((query or '').split()).casefold()
    if needle:
        fields = ('title', 'query', 'attribution_text', 'description', 'creator', 'source')
        rows = [row for row in rows
                if needle in ' '.join(str(row.get(k) or '') for k in fields).casefold()]
    return rows


def attribution_for(settings, sha: str) -> dict[str, Any] | None:
    """The credit line for one cached image, or None when it was never cleared."""
    if not _valid_sha(sha):
        return None
    row = _load_manifest(settings).get(str(sha))
    if row is None:
        return None
    return {'sha256': str(sha), 'title': row.get('title', ''),
            'credit': row.get('attribution_text', ''),
            'licence': row.get('licence_code', ''),
            'licence_class': row.get('licence_class', ''),
            'licence_url': row.get('licence_url', ''),
            'source': row.get('source', ''),
            'source_url': row.get('landing_page_url', ''),
            'creator': row.get('creator', ''),
            'alt': row.get('alt_text', '')}


def _manifest_line_sha(line: str) -> str:
    try:
        row = json.loads(line)
    except ValueError:
        return ''
    return str(row.get('sha256') or '') if isinstance(row, dict) else ''


def remove_asset(settings, sha: str) -> bool:
    """Delete a cached image's bytes and its manifest line. True when something was removed.

    The manifest is an append-only log, so removal is a filtered rewrite; the file is
    rewritten whole rather than patched because a partially-written manifest would leave
    the index disagreeing with the cache it describes.
    """
    if not _valid_sha(sha):
        return False
    manifest = _load_manifest(settings)
    row = manifest.get(str(sha))
    if row is None:
        return False
    target = Path(settings.data_dir) / str(row.get('cache_path') or '')
    target.unlink(missing_ok=True)
    path = manifest_path(settings)
    kept = [line for line in path.read_text(encoding='utf-8').splitlines()
            if line.strip() and _manifest_line_sha(line) != str(sha)]
    path.write_text('\n'.join(kept) + ('\n' if kept else ''), encoding='utf-8')
    return True


def describe(settings=None) -> dict[str, Any]:
    """The pipeline's posture, for the health endpoint and the transparency panel."""
    return {
        'providers': list(PROVIDERS),
        'enabled': enabled(settings) if settings is not None else None,
        'cache_dir': str(cache_root(settings)) if settings is not None else '',
        'thresholds': {'min_width': MIN_WIDTH, 'min_height': MIN_HEIGHT,
                       'min_aspect': MIN_ASPECT, 'max_aspect': MAX_ASPECT,
                       'max_bytes': MAX_BYTES, 'search_depth': SEARCH_DEPTH,
                       'max_fetch_per_call': MAX_FETCH_PER_CALL,
                       'max_lesson_images': MAX_LESSON_IMAGES},
        'licences_cached': sorted(k.value for k in policy.LOCALLY_STORABLE),
        'licences_refused': sorted(k.value for k in set(policy.LicenceClass)
                                   - policy.LOCALLY_STORABLE),
        'guarantees': [
            'Nothing is downloaded before its own licence has been classified.',
            'An unclassified licence code drops the candidate; it is never assumed permissive.',
            'Every cached image stores its author, licence, licence URL and attribution string.',
            'A cached image without a source and a licence is refused by the manifest reader.',
            'With no network, every entry point returns a refusal and the deterministic '
            'figure is still available.',
        ],
    }
