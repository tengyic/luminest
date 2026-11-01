"""Video search for teachers: find candidates, verify embeddability, never auto-trust.

Teacher-only by design (the gate lives in toolbox). The flow is candidates-not-content:

1. ``search.list`` via the optional YouTube Data API key when configured (authoritative,
   ~100 search-units/query), else a keyless chain: the provider's own results page first,
   a DuckDuckGo ``site:youtube.com`` scrape second.
2. Every candidate video id is pushed through :func:`app.harness.video.verify` -- the
   same fail-close oEmbed/embeddability probe the curated allowlist uses. A candidate
   that fails verification comes back as a plain link card, never as an embed card.
3. Nothing here *ships to a student*: landing in front of a learner requires the teacher
   to attach a verified video to a concept, which writes ``media/video_allowlist.json``
   through the existing curation path.

Quota note: Data API searches cost 100 units each against a 10,000/day default, so the
keyless chain exists and the tool reports which path served the results.

Why the provider's own page is the first keyless path: a SERP scrape is an indirection
that breaks whenever the SERP decides to block a client (mojeek answers 403 to a
non-browser request; DuckDuckGo's HTML endpoint is unreachable from some networks) even
though YouTube itself is perfectly reachable. Parsing the results page also yields the
provider's own titles, channel names and durations, which is better data than a SERP's
concatenated snippet text -- the exact defect this module was already bitten by.
"""

from __future__ import annotations

import json
import re
from typing import Any, Sequence
from urllib.parse import urlparse


_VIDEO_ID = re.compile(r'(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})')

#: A browser user-agent, because the results page is served differently to a bare client.
_BROWSER_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 '
               '(KHTML, like Gecko) Version/17.0 Safari/605.1.15')

#: A lesson block is a few minutes. Anything past this is a lecture, not an orientation,
#: and a Short is a clip; both are excluded rather than ranked low.
_MAX_SECONDS = 1800
_MIN_SECONDS = 60


def _video_id(url: str) -> str:
    match = _VIDEO_ID.search(url or '')
    return match.group(1) if match else ''


def _api_search(settings, query: str, limit: int) -> tuple[list[dict[str, Any]], str]:
    """YouTube Data API v3 search.list. Returns (hits, path-name)."""
    import httpx
    params = {'part': 'snippet', 'q': query, 'type': 'video', 'maxResults': limit,
              'key': settings.youtube_api_key, 'safeSearch': 'strict',
              'relevanceLanguage': 'en'}
    response = httpx.get('https://www.googleapis.com/youtube/v3/search', params=params,
                         timeout=settings.media_timeout, trust_env=False)
    response.raise_for_status()
    hits = []
    for item in response.json().get('items', []):
        video_id = (item.get('id') or {}).get('videoId') or ''
        snippet = item.get('snippet') or {}
        if video_id:
            hits.append({'video_id': video_id, 'title': snippet.get('title', ''),
                         'channel': snippet.get('channelTitle', ''),
                         'source': 'youtube_data_api'})
    return hits, 'youtube_data_api'


def _ddg_search(settings, query: str, limit: int) -> tuple[list[dict[str, Any]], str]:
    """Keyless fallback: DDG restricted to youtube.com, ids extracted from links."""
    from . import ddg_provider

    DDGS = ddg_provider.load()
    if DDGS is None:
        raise RuntimeError('No DuckDuckGo provider is installed (neither ddgs nor '
                           'duckduckgo_search).')
    raw = DDGS().text(f'site:youtube.com {query}', max_results=limit * 2)
    hits, seen = [], set()
    for row in raw or []:
        video_id = _video_id(str(row.get('href') or ''))
        if not video_id or video_id in seen:
            continue
        seen.add(video_id)
        hits.append({'video_id': video_id, 'title': str(row.get('title') or ''),
                     'channel': urlparse(str(row.get('href'))).hostname or 'youtube.com',
                     'source': 'ddg_fallback'})
        if len(hits) >= limit:
            break
    return hits, 'ddg_fallback'


def _duration_seconds(text: str) -> int:
    """``8:59`` / ``1:02:33`` -> seconds. Zero when the field is absent or unparseable."""
    parts = [part for part in str(text or '').strip().split(':')]
    if not parts or not all(part.isdigit() for part in parts):
        return 0
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + int(part)
    return seconds


def _page_hits(html: str, limit: int) -> list[dict[str, Any]]:
    """Parse a results page into candidates. Pure, so the contract is testable offline.

    ``ytInitialData`` is the page's own state blob. It is located by name rather than by
    a fixed offset because the surrounding script tags change; the blob itself is decoded
    with :meth:`json.JSONDecoder.raw_decode` so a trailing ``;</script>`` and the rest of
    the document are ignored.
    """
    marker = html.find('ytInitialData')
    if marker < 0:
        return []
    start = html.find('{', marker)
    if start < 0:
        return []
    try:
        data, _end = json.JSONDecoder().raw_decode(html, start)
    except ValueError:
        return []

    renderers: list[dict[str, Any]] = []
    stack = [data]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            renderer = node.get('videoRenderer')
            if isinstance(renderer, dict):
                renderers.append(renderer)
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)

    hits, seen = [], set()
    for renderer in renderers:
        video_id = str(renderer.get('videoId') or '')
        if not video_id or video_id in seen:
            continue
        title_block = renderer.get('title') or {}
        runs = title_block.get('runs') or [{}]
        title = str(runs[0].get('text') or title_block.get('simpleText') or '')
        if not title:
            continue
        channel_block = renderer.get('ownerText') or renderer.get('longBylineText') or {}
        channel_runs = channel_block.get('runs') or [{}]
        channel = str(channel_runs[0].get('text') or '')
        seconds = _duration_seconds((renderer.get('lengthText') or {}).get('simpleText', ''))
        if '#short' in title.casefold() or not _MIN_SECONDS <= seconds <= _MAX_SECONDS:
            # Zero means the row carried no duration at all: a live stream, an upcoming
            # premiere or a shelf, none of which is a lesson video. It fails the range
            # test with the out-of-range ones instead of needing its own branch.
            continue
        seen.add(video_id)
        hits.append({'video_id': video_id, 'title': title, 'channel': channel,
                     'seconds': seconds, 'source': 'youtube_page'})
        if len(hits) >= limit:
            break
    return hits


def _youtube_page_search(settings, query: str, limit: int) -> tuple[list[dict[str, Any]], str]:
    """Keyless discovery from the provider's own results page."""
    import httpx
    response = httpx.get('https://www.youtube.com/results',
                         params={'search_query': query, 'hl': 'en', 'gl': 'US'},
                         headers={'User-Agent': _BROWSER_UA,
                                  'Accept-Language': 'en-US,en;q=0.9'},
                         timeout=float(getattr(settings, 'media_timeout', 12.0) or 12.0),
                         follow_redirects=True, trust_env=False)
    response.raise_for_status()
    hits = _page_hits(response.text, limit)
    if not hits:
        raise RuntimeError('the results page carried no usable video rows')
    return hits, 'youtube_page'


def _keyless_search(settings, query: str, limit: int) -> tuple[list[dict[str, Any]], str]:
    """The keyless chain: the provider's own index, then a SERP scrape.

    Both are best-effort. The chain reports what failed rather than returning an empty
    list, because "no video is about this" and "the search could not run" are different
    facts and the caller prints one of them to a teacher.
    """
    failures: list[str] = []
    # Named here rather than read off ``provider.__name__``: the name is part of the
    # message a teacher reads, so it must not change when the function is replaced.
    for name, provider in (('youtube_page', _youtube_page_search),
                           ('ddg_fallback', _ddg_search)):
        try:
            hits, path = provider(settings, query, limit)
        except Exception as exc:                      # noqa: BLE001 - try the next provider
            failures.append(f'{name}: {type(exc).__name__}')
            continue
        if hits:
            return hits, path
        failures.append(f'{name}: no candidates')
    raise RuntimeError('; '.join(failures) or 'no keyless provider is available')


def search_videos(ctx, query: str, limit: int = 6) -> dict[str, Any]:
    """Teacher-facing video search. Every candidate is verified before it becomes an embed card."""
    settings = getattr(ctx, 'settings', None)
    if settings is None:
        return {'ok': False, 'error': 'No settings are bound to this call'}
    query = ' '.join((query or '').split())[:200]
    if not query:
        return {'ok': False, 'refused': 'No query supplied.'}
    if not getattr(settings, 'media_enabled', False):
        return {'ok': False,
                'refused': 'Video search requires network media, which is disabled for '
                           'this instance (HARNESS_MEDIA_ENABLED). No search was made.'}
    from . import video as video_module
    wanted = max(1, min(int(limit), 10))
    if getattr(settings, 'youtube_api_key', ''):
        try:
            hits, path = _api_search(settings, query, wanted)
        except Exception as exc:
            try:
                hits, path = _keyless_search(settings, query, wanted)
                path = f'{path} (api error: {type(exc).__name__})'
            except Exception as exc2:
                return {'ok': False, 'error': f'Both search paths failed: '
                         f'{type(exc).__name__}: {exc}; {type(exc2).__name__}: {exc2}'}
    else:
        try:
            hits, path = _keyless_search(settings, query, wanted)
        except Exception as exc:
            return {'ok': False,
                    'error': f'Keyless search failed: {type(exc).__name__}: {exc}',
                    'notes': ['No YouTube API key is configured; the keyless chain served '
                              'this request.']}

    verified, plain_links = [], []
    for hit in hits:
        result = video_module.verify(settings, hit['video_id'])
        # ``verify`` reports ``embeddable``/``method`` (see video.py); it has no ``ok`` key,
        # and reading one here silently demoted every verified video to a plain link.
        embeddable = bool(result.get('embeddable'))
        # oEmbed's title is authoritative. The keyless fallback scrapes a SERP and can come
        # back with several results' titles concatenated into one row, so the scraped title
        # is only a fallback for a video the probe could not describe.
        title = str(result.get('title') or '').strip() or hit.get('title', '')
        channel = str(result.get('channel') or '').strip() or hit.get('channel', '')
        card = {'video_id': hit['video_id'], 'title': title,
                'channel': channel,
                'search_path': hit['source'], 'verified': embeddable,
                'watch_url': f'https://www.youtube.com/watch?v={hit["video_id"]}'}
        if embeddable:
            card['embed_url'] = f'https://www.youtube-nocookie.com/embed/{hit["video_id"]}'
            card['licence'] = 'EMBED_ONLY (provider-hosted player)'
            card['licence_class'] = 'embed_only'
            verified.append(card)
        else:
            card['verification'] = str(result.get('method') or 'unknown')
            plain_links.append(card)
    return {'ok': bool(verified or plain_links), 'query': query, 'path': path,
            'videos': verified + plain_links,
            'notes': ['Embed cards were verified per video and fail closed; unverified '
                      'candidates are links only. Nothing reaches a learner until a '
                      'teacher attaches it to a concept via the curation flow.']}


#: Words that describe the *shape* of a lesson title rather than its subject. A candidate
#: matching only these has matched nothing, so they are excluded from relevance.
_STOPWORDS = frozenset("""
a an and the of for to in on with by from into your you what why how is are was were
explained explain introduction intro overview basics basic tutorial lesson lessons
video videos part full course math maths mathematics algebra learn learning
""".split())


def _terms(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9']+", str(text or '').casefold())
    return {word for word in words if len(word) >= 3 and word not in _STOPWORDS}


def _inflected(wanted: str, got: str) -> bool:
    """Whether two words are the same word under inflection.

    Lesson titles are plural and provider titles are not: "Linear functions and intercepts"
    against Khan's "Slope-intercept form". Exact set intersection scored that zero, which
    filtered out the best video for the lesson and left the deck to open. A shared stem of
    four characters is enough, and four is what keeps "line" from matching "linear".
    """
    if wanted == got:
        return True
    short, long_ = sorted((wanted, got), key=len)
    return len(short) >= 4 and long_.startswith(short)


def relevance(concept: dict[str, Any], title: str) -> int:
    """How many of the concept's own terms appear in a candidate's title.

    Deliberately crude and deliberately not a model: the job is to stop an obviously
    wrong video reaching a learner, and a shared content word is enough to prove a video
    is *about* the concept. Ranking by the count is what puts the closest one first.

    Counted over the *candidate's* words rather than the concept's, so a concept carrying
    both "permutation" and "permutations" in its keywords does not score twice for one
    word on the card.
    """
    wanted = _terms(' '.join([str(concept.get('title') or ''),
                              *(str(k) for k in concept.get('keywords') or ())]))
    return sum(1 for word in _terms(title)
               if any(_inflected(term, word) for term in wanted))


#: Channels a curator would ship. Relevance alone is not enough: the first page of results
#: for "Linear functions and intercepts" is mostly small tutoring channels, and a lesson
#: that opens with an unknown presenter is a worse lesson than one that opens with Khan
#: Academy even when both titles match. This is a preference, never a gate — an untrusted
#: channel still wins when nothing trusted is on topic, because a correct video from an
#: unfamiliar channel beats no video.
_TRUSTED_CHANNELS: tuple[str, ...] = (
    'khan academy', '3blue1brown', 'crash course', 'the organic chemistry tutor',
    'professor dave explains', 'bozeman science', 'amoeba sisters', 'ted-ed', 'ted ed',
    'mit opencourseware', 'math antics', 'brian mclogan', "mario's math tutoring",
    'nancypi', 'statquest', 'heimler', 'jacob clifford', 'melissa maribel',
    'tyler dewitt', 'simple learning pro', 'numberphile', 'veritasium', 'kurzgesagt',
    'marginal revolution university',
)


def trusted_channel(channel: str) -> int:
    """1 when the channel is one a curator would ship, else 0."""
    name = ' '.join(str(channel or '').casefold().split())
    return 1 if any(name == trusted or name.startswith(trusted)
                    for trusted in _TRUSTED_CHANNELS) else 0


#: Number words and digits, kept as distinguishing terms even though they are short: "one"
#: and "two" are the entire difference between two lessons in the same course.
_NUMERALS = frozenset('one two three four five six seven eight nine ten '
                      '1 2 3 4 5 6 7 8 9 10'.split())


def closer_to_another(title: str, concept: dict[str, Any],
                      siblings: Sequence[str] = ()) -> str:
    """The sibling lesson this title belongs to, or ``''``.

    Courses are full of lessons that differ by one word — "One-step equations" and
    "Two-step equations", "Parallel and perpendicular lines". A relevance test that only
    asks "does this title share words with the concept" answers yes to both, and the first
    page of results happily supplies the one-step video for the two-step lesson.

    So the test is not "does this share words with the concept" but "does this carry a word
    that belongs to a *neighbour* and not to the concept". The words the concept does not
    have are exactly the ones that make a sibling a different lesson; if the candidate has
    one of them, the candidate is about that lesson.
    """
    got = _terms(title)
    own = _terms(' '.join([str(concept.get('title') or ''),
                           *(str(k) for k in concept.get('keywords') or ())]))
    own_title = ' '.join(str(concept.get('title') or '').casefold().split())
    for sibling in siblings:
        other = ' '.join(str(sibling or '').casefold().split())
        if not other or other == own_title:
            continue
        distinctive = {word for word in _terms(other) - own
                       if len(word) >= 4 or word in _NUMERALS}
        if any(_inflected(word, seen) for word in distinctive for seen in got):
            return str(sibling)
    return ''


def _why_nothing_qualified(rejected: Mapping[str, int], min_untrusted_score: int) -> str:
    """The real reason, because "no video" has four different causes and they matter.

    A concept with no video because nothing on the first page was about it is a different
    fact from one with no video because every candidate belonged to the lesson next door,
    and both are different from "the videos are there and none of them may be embedded".
    The caller prints this to a teacher, so it says which.
    """
    causes = {
        'title': 'nothing on the first page was about this concept by title',
        'unverified': 'every candidate failed the embeddability probe',
        'neighbour': 'every candidate belonged to a neighbouring lesson',
        'source': (f'every candidate came from an unfamiliar channel on a thin title match '
                   f'(fewer than {min_untrusted_score} concept words)'),
    }
    parts = [causes[key] for key, count in rejected.items() if count and key in causes]
    if not parts:
        return 'No candidate passed the curation tests.'
    return 'No video was curated: ' + '; '.join(parts) + '.'


def _score_candidates(concept: dict[str, Any], candidates: Sequence[Mapping[str, Any]],
                      siblings: Sequence[str], accept_links: bool,
                      min_untrusted_score: int
                      ) -> tuple[list[tuple[int, int, int, Mapping[str, Any]]], dict[str, int]]:
    """The four tests, applied to every candidate, with a count of what each one stopped."""
    scored: list[tuple[int, int, int, Mapping[str, Any]]] = []
    rejected = {'title': 0, 'unverified': 0, 'neighbour': 0, 'source': 0}
    for card in candidates:
        score = relevance(concept, card.get('title', ''))
        if score <= 0:
            rejected['title'] += 1
            continue
        if not card.get('verified') and not accept_links:
            rejected['unverified'] += 1
            continue
        if closer_to_another(card.get('title', ''), concept, siblings):
            rejected['neighbour'] += 1
            continue
        trusted = trusted_channel(card.get('channel'))
        # The weaker the evidence that a video is *about* the concept, the better the source
        # has to be. A build that ships a list raises this, because an unfamiliar channel
        # whose title only half-matches is worse than no video: the lesson has a designed
        # fallback and a published reason, and "no video" is not a defect a learner sees.
        if not trusted and score < min_untrusted_score:
            rejected['source'] += 1
            continue
        scored.append((score, trusted, 1 if card.get('verified') else 0, card))
    return scored, rejected


def curate_for_concept(settings, concept: dict[str, Any], course_id: str, *,
                       limit: int = 6, accept_links: bool = False,
                       siblings: Sequence[str] = (),
                       min_untrusted_score: int = 1) -> dict[str, Any]:
    """Find the best video for a concept and attach it. The TA's curation job.

    A concept with no curated video has no video in its lesson -- the procedure refuses to
    promise one, which is correct but leaves a class without the thing a learner asked
    for. This closes that gap without loosening anything: the candidate still has to pass
    the same oEmbed embeddability probe, still has to be *about* the concept by title, and
    lands in the same allowlist a human curator writes. An embed is preferred; a plain
    link is only accepted when the caller says so, because an unverified direction is
    never the permissive one.
    """
    concept_id = str(concept.get('id') or '')
    query = str(concept.get('title') or '').strip()
    if not concept_id or not query:
        return {'curated': False, 'reason': 'A concept with an id and a title is required.'}

    # Two formulations, because the keyless fallback is a scraped search page: it comes
    # back empty often enough (rate limiting, no exact-phrase match) that one query is a
    # coin flip. The second is the one a teacher would type next.
    attempts = [query]
    subject = ' '.join(str(word) for word in (concept.get('keywords') or [])[:2])
    if subject:
        attempts.append(f'{query} {subject}')

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    state = {'path': '', 'failure': ''}

    def collect(queries: Sequence[str]) -> None:
        for attempt in queries:
            found = search_videos(_ctx(settings), attempt, limit=limit)
            if not found.get('ok'):
                state['failure'] = str(found.get('refused') or found.get('error')
                                       or 'no candidates')
                continue
            state['path'] = str(found.get('path') or state['path'])
            for card in found.get('videos') or []:
                if card.get('video_id') in seen:
                    continue
                seen.add(card.get('video_id'))
                candidates.append(card)
            if len(candidates) >= limit * 2:
                break

    collect(attempts)
    if not candidates:
        return {'curated': False, 'query': query,
                'reason': state['failure'] or 'no candidates'}

    scored, rejected = _score_candidates(concept, candidates, siblings, accept_links,
                                         min_untrusted_score)
    # Ask again, once, naming the provider a curator would have searched for by hand — but
    # only when nothing *usable* came from a preferred source. Testing the candidate pool
    # instead of the scored list was the bug here: one irrelevant Khan video on the first
    # page suppressed the retry and left a 4th-grade clip as the best on-topic result.
    if not any(row[1] for row in scored):
        before = len(candidates)
        collect([f'{query} {_TRUSTED_CHANNELS[0]}'])
        if len(candidates) > before:
            scored, rejected = _score_candidates(concept, candidates, siblings,
                                                 accept_links, min_untrusted_score)
    if not scored:
        return {'curated': False, 'query': query, 'path': state['path'],
                'reason': _why_nothing_qualified(rejected, min_untrusted_score),
                'rejected': rejected,
                'considered': len(candidates)}

    # Relevance first, then whether the source is one we would ship, then verification.
    scored.sort(key=lambda row: (row[0], row[1], row[2]), reverse=True)
    score, trusted, _verified, best = scored[0]
    path = state['path']
    from . import video as video_module
    written = video_module.curate(
        settings, course_id, concept_id, video_id=best['video_id'],
        title=best.get('title', ''), channel=best.get('channel', ''),
        why=(f'curated by the TA: {score} concept term(s) in the title, '
             f'{path}, embeddability {"verified" if best.get("verified") else "unverified"}, '
             f'source {"preferred" if trusted else "unfamiliar"}'))
    return {'curated': bool(written.get('added')), 'query': query,
            'path': path, 'score': score, 'trusted': bool(trusted),
            'considered': len(candidates),
            'video': {key: best.get(key) for key in
                      ('video_id', 'title', 'channel', 'verified', 'embed_url')},
            'reason': written.get('reason', '')}


def _ctx(settings):
    """``search_videos`` takes a context object; a settings instance is all it reads."""
    import types
    return types.SimpleNamespace(settings=settings, role='teacher')
