"""Find a source, take one the learner supplied, and turn it into a course.

The harness ships six courses. A learner whose syllabus is not one of them has always
been able to paste their own material and get a course (``app.course_builder``); what
they could not do is *find* the material. This module closes that: type a topic, get
candidates with their rights position attached, pick one, and the course is built and
personalised to the learner in the same motion.

Three rules shape everything here, and they are the same three the rest of the
ingest path is built on.

1. **The licence gate decides what may become a course.** A candidate is offered with
   its licence class and an ``ingestible`` flag, and building a course from one that
   is not ingestible is refused with a reason that names the class. A learner is never
   shown a source they may read but not use as though it were the same as one they
   may: OpenStax's current books are link-only, Khan Academy is prohibited, and
   Wikipedia's text is CC BY-SA and therefore usable with attribution. All three are
   offered. Only one of them can be built from, and the learner can see which.

2. **Nothing is invented.** Every candidate's URL comes from a real provider call or
   from the audited source registry in ``app.ingest.policy``. There is no synthetic
   result, no plausible-looking placeholder, and no search that returns a made-up
   link when the network is down - it returns fewer candidates and says why.

3. **Personalised means derived from the learner, not decorative.** The level, the
   session length, the number of concepts to front-load and the estimate of how long
   the course will take all come from the learner's own recorded goal and pace. The
   concepts themselves are not rewritten for them: ``app.course_builder`` does not
   invent content, and neither does this module.

Every network call is a seam (``WIKIPEDIA_SEARCH``, ``WIKIPEDIA_ARTICLE``) so the
whole feature is testable with no network and behaves identically with no API key.
With no network the offline providers still work: a learner can find their own
curated material and the audited references; they just cannot search Wikipedia.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import quote

from . import course_builder, planner
from .course_builder import CoursePlan
from .curriculum import course_concepts
from .ingest import policy as ingest_policy

# --------------------------------------------------------------------- constants

#: How many candidates a search returns. A learner choosing a source reads a list;
#: past this the list stops being read and starts being scrolled.
SEARCH_LIMIT = 8

#: Kill switch for the only network provider. Default on: a learner asking for a
#: source should get one. An operator with an egress policy can turn it off, and the
#: feature degrades to the offline providers rather than failing.
SEARCH_ENV = 'HARNESS_SOURCE_SEARCH'

#: Networks hang longer than this in practice than any API timeout worth setting.
SEARCH_TIMEOUT_SECONDS = 20

#: Descriptive user agent, per the same rule the URL fetcher follows. Wikipedia's own
#: guidance asks for a contact and a purpose; an opaque agent is how projects get
#: blocked.
USER_AGENT = ('Luminfest-Learning-Harness/1.0 '
              '(learner-requested source lookup; +https://luminfest.local)')

_WIKIPEDIA_SEARCH_URL = 'https://en.wikipedia.org/w/rest.php/v1/search/page'
_WIKIPEDIA_ARTICLE_URL = 'https://en.wikipedia.org/w/api.php'

#: ``explaintext`` marks sections with ``== Heading ==``. The concept extractor reads
#: markdown ``#`` headings and its own stop-title list, so the two dialects have to be
#: reconciled somewhere; doing it here keeps it a property of the source rather than
#: a second dialect bolted onto the extractor.
_WIKI_HEADING = re.compile(r'^(={2,6})[ \t]*(.+?)[ \t]*\1[ \t]*$', re.MULTILINE)

#: How many candidates a process remembers. Candidates are resolved by id so a
#: learner can pick one from a list and build a course from it two requests later;
#: the cache is what makes the id mean anything. It is a cache, not a store, and a
#: miss is a refusal, not an error.
RECENT_LIMIT = 256
RECENT_TTL_SECONDS = 3600

#: Words that carry no signal when matching a learner's goal against a concept. Kept
#: small on purpose: this is a heuristic for ordering, not a parser, and an
#: aggressive stop list would silently drop the one word that mattered.
_STOP = frozenset("""
a an and are as at be been but by can could did do does for from get got had has have
he her hers his how i if in into is it its just me my no not of on one or our out over
she should so some than that the their them then there these they this those to too up
us very was we were what when where which who why will with would you your about more
most much many really want needs need make made using use
""".split())

#: The four kinds of match a goal can make, strongest first...
_LEVEL_HINTS: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (('exam', 'test', 'final', 'quiz', 'ap', 'sat', 'act', 'certification', 'certified'),
     'exam_preparation',
     'Your goal names an assessment, so the course is ordered to build toward one rather than to wander.'),
    (('understand', 'why', 'intuition', 'conceptual', 'curious', 'explain', 'grasp', 'make sense'),
     'conceptual',
     'Your goal is about understanding rather than recall, so depth is preferred over coverage.'),
    (('review', 'refresh', 'revise', 'again', 'brush up', 'forgot', 'recall'),
     'revision',
     'Your goal is revisiting material you have met, so the course starts from what you already said was shaky.'),
    (('fast', 'quickly', 'crash', 'week', 'days', 'asap', 'cram'),
     'accelerated',
     'Your goal names a short deadline, so the course is front-loaded with the ideas that carry the most.'),
    (('project', 'build', 'make', 'present', 'presentation', 'portfolio'),
     'project_led',
     'Your goal is building something, so the course keeps the ideas needed to finish a piece of work.'),
)


class SourceRefused(RuntimeError):
    """The source may not be turned into a course. Carries the reason and the class."""

    def __init__(self, reason: str, *, code: str = 'source_not_ingestible',
                 licence_class: str = '', detail: str = ''):
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.licence_class = licence_class
        self.detail = detail


# --------------------------------------------------------------------- candidates

@dataclass(frozen=True)
class Candidate:
    """One place material could come from, with its rights position attached.

    ``can_build_course`` is not a duplicate of ``ingestible``: it is the question a
    learner is actually asking. A source may be ingestible and still unable to yield a
    course - a search *index* is ingestible and contains no teachable text. Conversely
    a link-only source is never buildable, and says so, so a learner is not told they
    can study a book the harness is forbidden to read.
    """

    id: str
    title: str
    url: str
    provider: str                 # 'curriculum' | 'registry' | 'wikipedia'
    summary: str
    licence: str
    licence_class: str
    ingestible: bool
    can_build_course: bool
    attribution: str
    why: str
    topics: tuple[str, ...] = ()
    concepts: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            'id': self.id, 'title': self.title, 'url': self.url, 'provider': self.provider,
            'summary': self.summary, 'licence': self.licence, 'licence_class': self.licence_class,
            'ingestible': self.ingestible, 'can_build_course': self.can_build_course,
            'attribution': self.attribution, 'why': self.why, 'topics': list(self.topics),
            'concepts': list(self.concepts),
        }


@dataclass(frozen=True)
class SearchResult:
    """What a search found, and what it could not check."""

    query: str
    candidates: list[Candidate]
    notes: list[str]
    providers: dict[str, bool]

    def to_dict(self) -> dict[str, Any]:
        return {'query': self.query, 'results': [c.to_dict() for c in self.candidates],
                'notes': list(self.notes), 'providers': dict(self.providers),
                'count': len(self.candidates)}


def _tokens(value: str) -> set[str]:
    return {word for word in re.findall(r"[A-Za-z][A-Za-z'-]*", (value or '').casefold())
            if len(word) > 2 and word not in _STOP}


def _candidate_id(provider: str, key: str) -> str:
    return hashlib.sha256(f'{provider}|{key}'.encode('utf-8')).hexdigest()[:20]


#: Recently produced candidates, keyed by id. Bounded by :data:`RECENT_LIMIT` with a
#: soft TTL, and trimmed on insert rather than by a background job - a candidate that
#: expires between the search and the build is a refusal the learner can act on, not
#: a crash.
_RECENT: dict[str, tuple[float, Candidate]] = {}


def _remember(candidate: Candidate) -> Candidate:
    _RECENT[candidate.id] = (time.time(), candidate)
    if len(_RECENT) > RECENT_LIMIT:
        cutoff = time.time() - RECENT_TTL_SECONDS
        for key, stamp in [(k, v[0]) for k, v in _RECENT.items() if v[0] < cutoff]:
            _RECENT.pop(key, None)
        while len(_RECENT) > RECENT_LIMIT:
            _RECENT.pop(next(iter(_RECENT)))
    return candidate


def find(candidate_id: str) -> Candidate | None:
    """A candidate recently returned by :func:`search`, or ``None``.

    ``None`` is the honest answer for an expired or unknown id, and the caller must
    translate it into a refusal that tells the learner to search again rather than
    into a 500. A candidate id is not a durable reference: it is a handle for the
    thing a learner is looking at right now.
    """
    entry = _RECENT.get((candidate_id or '').strip())
    if entry is None:
        return None
    stamp, candidate = entry
    if time.time() - stamp > RECENT_TTL_SECONDS:
        _RECENT.pop(candidate.id, None)
        return None
    return candidate


def forget(candidate_id: str) -> None:
    """Drop one remembered candidate. Used by tests, and by a learner who withdraws."""
    _RECENT.pop((candidate_id or '').strip(), None)


# --------------------------------------------------------------------- providers

def _curriculum_candidates(query: str, wanted: set[str], limit: int) -> list[Candidate]:
    """The harness's own courses that already cover what was asked for.

    This is the offline provider and the one that answers the most common question
    after a search: *the learner already has this*. Offering it as a candidate rather
    than as a footnote matters, because a learner who searches "Newton's laws" and is
    handed a Wikipedia article they then have to build a course from is worse served
    than one who learns their Physics course already covers it.
    """
    from . import courses
    out: list[Candidate] = []
    for spec in courses.COURSES:
        concepts = course_concepts(spec.id)
        if not concepts:
            continue
        hits, topics = [], []
        for concept_id, entry in concepts.items():
            title = str(entry.get('title') or '')
            unit = str(entry.get('unit') or '')
            overlap = wanted & (_tokens(title) | _tokens(unit))
            if overlap:
                hits.append(concept_id)
                topics.extend(sorted(overlap))
        if not hits:
            continue
        out.append(_remember(Candidate(
            id=_candidate_id('curriculum', spec.id),
            title=spec.title,
            url='',
            provider='curriculum',
            summary=spec.description,
            licence='This harness\'s own original curriculum',
            licence_class='original',
            # Not ingestible and not buildable: this *is* the harness's material. The
            # candidate points at a course to enrol in rather than a source to copy.
            ingestible=False,
            can_build_course=False,
            attribution='',
            why=(f'{len(hits)} of its {len(concepts)} concepts match '
                 f'{", ".join(sorted(set(topics))[:4])}.'),
            topics=tuple(sorted(set(topics))[:6]),
            concepts=tuple(hits[:limit * 2]),
        )))
    return out


def _registry_candidates(query: str, wanted: set[str], limit: int) -> list[Candidate]:
    """Sources this project has already audited, offered as references.

    Every entry here carries a real licence class, read from the single gate in
    ``app.ingest.policy``. A candidate from this provider is almost always
    ``can_build_course: False`` - OpenStax's current books are link-only and Khan
    Academy is prohibited - and *that is the point of offering it*. A learner searching
    "kinetic energy" who is told where to read more deserves to be told which of the
    answers the harness is allowed to turn into a course.
    """
    out: list[Candidate] = []
    for entry in ingest_policy.registry():
        name = str(entry.get('name') or '')
        url = str(entry.get('url') or '')
        if not url:
            continue
        haystack = ' '.join([name, str(entry.get('scope') or ''), str(entry.get('licence') or '')])
        overlap = wanted & _tokens(haystack)
        if not overlap:
            continue
        ingestible = bool(entry.get('ingestible'))
        out.append(_remember(Candidate(
            id=_candidate_id('registry', name),
            title=name,
            url=url,
            provider='registry',
            summary=str(entry.get('scope') or '')[:300],
            licence=str(entry.get('licence') or ''),
            licence_class=str(entry.get('licence_class') or ''),
            ingestible=ingestible,
            # Buildable only when the licence clears both ingestion *and* there is
            # teachable text to take. Wikidata is CC0 and holds labels, not lessons.
            can_build_course=False,
            attribution=str(entry.get('attribution') or ''),
            why=f'Matches on {", ".join(sorted(overlap)[:4])}.',
            topics=tuple(sorted(overlap)[:6]),
        )))
    return out


#: The search seam. Replaced in tests and by an operator with its own egress policy.
WIKIPEDIA_SEARCH: Callable[[str, int], list[dict[str, Any]]] = lambda query, limit: []


def _default_wikipedia_search(query: str, limit: int) -> list[dict[str, Any]]:
    """Wikipedia REST page search. Read-only, descriptive user agent, no account."""
    target = (f'{_WIKIPEDIA_SEARCH_URL}?q={quote(query)}&limit={max(1, min(limit, 20))}'
              f'&prefer.mostlypages=true')
    request = urllib.request.Request(target, headers={'User-Agent': USER_AGENT,
                                                      'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=SEARCH_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode('utf-8'))
    pages = payload.get('pages') if isinstance(payload, dict) else None
    if not isinstance(pages, list):
        return []
    out: list[dict[str, Any]] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        title = str(page.get('title') or '').strip()
        key = str(page.get('key') or title).strip()
        if not title or not key or '(disambiguation)' in title.casefold():
            continue
        out.append({'title': title, 'key': key,
                    'description': str(page.get('description') or ''),
                    'excerpt': _strip_markup(str(page.get('excerpt') or '')),
                    'url': f'https://en.wikipedia.org/wiki/{quote(key.replace(" ", "_"))}'})
    return out[:max(1, limit)]


def _strip_markup(value: str) -> str:
    """Remove the ``<span class="searchmatch">`` tags a search excerpt is served with."""
    return re.sub(r'<[^>]+>', '', value or '').strip()


def _wikipedia_candidates(query: str, wanted: set[str], limit: int,
                          enabled: bool) -> tuple[list[Candidate], list[str]]:
    """The only network provider. Fails soft, and says so.

    A failed search returns an empty list and a note, never an exception and never a
    fabricated result. The learner can still search their own curriculum and the
    audited references, which is the honest degradation.
    """
    notes: list[str] = []
    if not enabled:
        notes.append(f'Source search is switched off (set {SEARCH_ENV}=1 to enable it). '
                     f'Your own courses and the audited references are still searched.')
        return [], notes
    entry = ingest_policy.apply_overrides(ingest_policy.WIKIPEDIA_REST)
    try:
        pages = WIKIPEDIA_SEARCH(query, limit)
    except Exception:  # noqa: BLE001 - any provider failure degrades, never crashes
        notes.append(f'Wikipedia search could not be reached right now, so only your own '
                     f'courses and the audited references are offered.')
        return [], notes
    out: list[Candidate] = []
    for page in pages:
        title = str(page.get('title') or '')
        overlap = wanted & _tokens(' '.join([title, str(page.get('description') or ''),
                                             str(page.get('excerpt') or '')]))
        out.append(_remember(Candidate(
            id=_candidate_id('wikipedia', str(page.get('key') or title)),
            title=title,
            url=str(page.get('url') or ''),
            provider='wikipedia',
            summary=str(page.get('description') or '') or _excerpt(str(page.get('excerpt') or '')),
            licence=entry.licence,
            licence_class=entry.licence_class.value,
            ingestible=entry.ingestible,
            can_build_course=entry.ingestible,
            attribution=entry.attribution,
            why=(f'Matches on {", ".join(sorted(overlap)[:4])}.' if overlap else
                 'A Wikipedia article whose subject matches what you typed.'),
            topics=tuple(sorted(overlap)[:6]),
        )))
    if not out:
        notes.append('Wikipedia found no article for that search. Try a broader term, or '
                     'paste your own material.')
    return out, notes


def _excerpt(value: str, limit: int = 180) -> str:
    value = re.sub(r'\s+', ' ', value or '').strip()
    return value if len(value) <= limit else value[:limit].rstrip() + '…'


def search_enabled() -> bool:
    """Whether the network provider may run. Default on; one env var turns it off."""
    raw = os.environ.get(SEARCH_ENV, '1').strip().casefold()
    return raw not in ('0', 'false', 'no', 'off')


def search(query: str, *, limit: int = SEARCH_LIMIT,
           enabled: bool | None = None) -> SearchResult:
    """Find candidate sources for a topic, from every provider available.

    Providers are consulted in the order a learner most likely wants them: the
    material they can build from, then what they already have, then what they may
    only read. Every returned candidate carries the rights position it came with, so
    the list is a decision aid rather than a menu of things that all work the same.
    """
    query = (query or '').strip()
    wanted = _tokens(query)
    limit = max(1, min(int(limit or SEARCH_LIMIT), SEARCH_LIMIT))
    notes: list[str] = []

    wikipedia, wikipedia_notes = _wikipedia_candidates(
        query, wanted, limit, search_enabled() if enabled is None else enabled)
    notes.extend(wikipedia_notes)
    curriculum_hits = _curriculum_candidates(query, wanted, limit)
    registry_hits = _registry_candidates(query, wanted, limit)

    # Two slots are held back from the network provider. A Wikipedia search for a
    # common phrase fills the whole list, and without the hold-back the two offline
    # providers - the courses this learner already has, and the audited references -
    # would never appear on a popular query at all. That is the opposite of the
    # ordering the docstring promises: a learner who already owns the material should
    # be told so before they are handed an article to copy.
    offline = [*curriculum_hits, *registry_hits]
    candidates = [*wikipedia[:max(1, limit - 2)], *offline][:limit]
    if not candidates:
        notes.append('Nothing matched that search. Try a broader term, a different '
                     'subject name, or paste your own material.')
    return SearchResult(query=query, candidates=candidates, notes=notes,
                        providers={'wikipedia': bool(wikipedia),
                                   'own_courses': bool(curriculum_hits),
                                   'audited_references': bool(registry_hits)})


# ----------------------------------------------------------------- fetching text

#: The article-text seam. The default implementation asks the MediaWiki Action API for
#: a plain-text extract, which is the same text the REST API serves and the shape the
#: concept extractor understands. Replaced in tests.
WIKIPEDIA_ARTICLE: Callable[[str], str] = lambda title: ''


def _default_wikipedia_article(title: str) -> str:
    """One article as plain text, section headings included, read-only."""
    target = (_WIKIPEDIA_ARTICLE_URL
              + '?action=query&prop=extracts&explaintext=1&redirects=1&format=json'
              + '&formatversion=2&titles=' + quote(title))
    request = urllib.request.Request(target, headers={'User-Agent': USER_AGENT,
                                                      'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=SEARCH_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode('utf-8'))
    pages = (payload.get('query') or {}).get('pages') or []
    for page in pages:
        if isinstance(page, dict):
            text = str(page.get('extract') or '')
            if text.strip():
                return text
    return ''


def normalise_wiki_text(text: str) -> str:
    """Translate ``== Heading ==`` into ``## Heading``.

    ``course_builder`` already reads markdown headings and already carries a stop-title
    list containing ``overview``, ``contents`` and ``summary``. Leaving Wikipedia's
    dialect in place would produce a course whose first concept is titled
    ``== Overview ==`` and would let real headings through the stop list that the
    cleaned version is caught by. This is a property of the source, so it lives here
    rather than being taught to the extractor.
    """
    return _WIKI_HEADING.sub(lambda match: '#' * len(match.group(1)) + ' ' + match.group(2),
                             text or '')


def policy_for(candidate: Candidate) -> Any:
    """The rights position a candidate may be built under, refusing when it may not."""
    if candidate.provider != 'wikipedia':
        raise SourceRefused(
            f'{candidate.title!r} is {candidate.provider} material, so there is no text for '
            f'this harness to read. A source must be licence-cleared for ingestion before '
            f'a course can be built from it.',
            code='source_not_buildable', licence_class=candidate.licence_class or 'none')
    entry = ingest_policy.apply_overrides(ingest_policy.WIKIPEDIA_REST)
    if not entry.ingestible:
        raise SourceRefused(
            f'{entry.name!r} is {entry.licence_class.value}, which is not cleared for '
            f'ingestion: {entry.scope} It can be offered as a reference and nothing more.',
            code='source_not_ingestible', licence_class=entry.licence_class.value)
    return entry


def intake_for(candidate: Candidate, *, article_fetcher: Callable[[str], str] | None = None,
               max_chars: int = 2_000_000) -> Any:
    """Read a candidate's text and wrap it as an intake.

    The provenance is not invented here: the licence, the licence class and the
    attribution all come from the policy entry, so a course built from a CC BY-SA
    article is stamped as coming from that article rather than from the learner.
    That distinction is the whole reason :func:`course_builder.build_graph` takes a
    ``source``.
    """
    entry = policy_for(candidate)
    fetcher = article_fetcher or WIKIPEDIA_ARTICLE
    try:
        raw = fetcher(candidate.title)
    except Exception:  # noqa: BLE001 - a failed read is a refusal, never a crash
        raise SourceRefused(
            f'{candidate.title!r} could not be read just now, so no course was built from it.',
            code='fetch_failed', licence_class=entry.licence_class.value)
    text = normalise_wiki_text(raw)
    if len(text) > max_chars:
        raise SourceRefused(
            f'{candidate.title!r} is {len(text)} characters, above the {max_chars}-character '
            f'ceiling for one source. Paste a section of it instead.',
            code='source_too_large', licence_class=entry.licence_class.value)
    if not text.strip():
        raise SourceRefused(
            f'{candidate.title!r} returned no readable text, so a course built from it '
            f'would have nothing in it.',
            code='empty_source', licence_class=entry.licence_class.value)
    return course_builder.Intake(text=text, source_kind='url', label=candidate.title,
                                 url=candidate.url, byte_size=len(text), format='text')


# ----------------------------------------------------------------- personalising

@dataclass(frozen=True)
class Personalisation:
    """The part of a course that is about *this* learner.

    Everything here is derived from the learner's own recorded goal and pace, and every
    field is arithmetic on numbers the learner set - no estimate here is dressed up as a
    prediction about them. The ``concepts`` themselves are not rewritten for them, and
    that is deliberate: ``app.course_builder`` does not invent content, and a harness
    that paraphrased a source to sound personal would be quietly inventing it.
    """

    goal: str
    level: str
    level_reason: str
    daily_minutes: int
    concepts: int
    practice_items: int
    sessions_to_finish: int
    weeks_to_finish: int
    first_session: tuple[str, ...]
    goal_matches: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            'goal': self.goal, 'level': self.level, 'level_reason': self.level_reason,
            'daily_minutes': self.daily_minutes, 'concepts': self.concepts,
            'practice_items': self.practice_items, 'sessions_to_finish': self.sessions_to_finish,
            'weeks_to_finish': self.weeks_to_finish, 'first_session': list(self.first_session),
            'goal_matches': list(self.goal_matches),
        }


def _field(user: Any, name: str, default: Any) -> Any:
    """One field off a user row or a mapping, without assuming which one it is."""
    if isinstance(user, Mapping):
        value = user.get(name, default)
    else:
        value = getattr(user, name, default)
    return default if value is None else value


def _goal_words(goal: str) -> set[str]:
    """Every word in a goal, short ones kept.

    The stop list used for matching a *source* would strip words a goal actually turns
    on - ``ap``, ``asap``, ``why`` - so goals get their own tokeniser rather than the
    shared one.
    """
    return {word for word in re.findall(r"[A-Za-z][A-Za-z'-]*", (goal or '').casefold())
            if len(word) > 1}


def level_for(goal: str) -> tuple[str, str]:
    """The level a learner's own goal implies, and the reason it was chosen.

    ``custom`` is the honest default, not a gap: a goal that names no assessment, no
    deadline and no kind of understanding gives the harness nothing to infer from, and
    guessing would put words in the learner's mouth.
    """
    words = _goal_words(goal)
    for hints, level, reason in _LEVEL_HINTS:
        if words & set(hints):
            return level, reason
    return 'custom', ('Your goal does not name an assessment, a deadline or a kind of '
                      'understanding, so no level was assumed. You can set one when you '
                      'enrol.')


def personalise(user: Any, plan: CoursePlan, candidate: Candidate | None = None) -> Personalisation:
    """Shape a plan around one learner: pace, level and what to start with.

    The arithmetic is the planner's own, so the estimate a learner sees here is the same
    one the Today surface will use when it schedules their sessions. Two harnesses with
    two different sums would make the plan and the estimate disagree, and the learner
    would have no way to know which to trust.
    """
    goal = str(_field(user, 'goal', '') or '')
    minutes = int(_field(user, 'daily_minutes', 20) or 20)
    minutes = max(1, min(480, minutes))
    level, reason = level_for(goal)

    concepts = len(plan.concepts)
    practice_items = concepts * planner.ITEMS_PER_CONCEPT
    total_minutes = practice_items * planner.SECONDS_PER_ITEM * planner.FEEDBACK_OVERHEAD / 60
    sessions = max(1, -(-int(total_minutes) // minutes))
    # Five scheduled sessions a week, so the calendar estimate matches the rhythm the
    # planner actually plans to rather than assuming the learner will practise daily.
    # ``daily_minutes`` sets how long one session is, and the number of sessions follows
    # from that; the weeks follow from how many sessions fit in a week.
    weeks = max(1, -(-sessions // planner.SESSIONS_PER_WEEK))

    per_session = max(1, min(planner.MAX_TODAY, round(minutes / 15)))
    ordered = list(plan.concepts.values())
    first_session = tuple(str(entry.get('title') or entry.get('id') or '') for entry in ordered[:per_session])

    goal_words = _goal_words(goal)
    matches: list[str] = []
    if goal_words:
        for entry in ordered:
            haystack = f"{entry.get('title')} {entry.get('summary')}"
            if goal_words & _tokens(str(haystack)):
                matches.append(str(entry.get('title') or entry.get('id') or ''))
    return Personalisation(
        goal=goal, level=level, level_reason=reason, daily_minutes=minutes,
        concepts=concepts, practice_items=practice_items, sessions_to_finish=sessions,
        weeks_to_finish=weeks, first_session=first_session, goal_matches=tuple(matches[:8]))


# ------------------------------------------------------------------ building one

@dataclass(frozen=True)
class BuiltCourse:
    """A planned course, plus the candidate it came from and who it is for."""

    plan: CoursePlan
    candidate: Candidate | None
    personalisation: Personalisation

    def to_dict(self) -> dict[str, Any]:
        payload = self.plan.to_preview()
        payload['personalisation'] = self.personalisation.to_dict()
        payload['candidate'] = self.candidate.to_dict() if self.candidate else None
        return payload


def _subject_for(candidate: Candidate | None, subject: str) -> str:
    """The subject line a built course gets. Never invented; the candidate's own words."""
    if subject:
        return subject
    if candidate and candidate.topics:
        return ', '.join(word.capitalize() for word in candidate.topics[:3])
    return ''


def _supplied(url: str = '', text: str = ''):
    """The learner's own material, as an intake and the rights it came in under.

    Nothing was fetched from a third party, so the source is the learner's own and
    the policy says so - which is why a course built from pasted notes is stamped
    ``learner_supplied`` and one built from a Wikipedia article is not.

    An :class:`IntakeRefused` is re-raised as a :class:`SourceRefused` rather than
    being allowed to escape: both are structured refusals with a code and a reason,
    but a caller handling this module's feature should have exactly one type to catch.
    """
    try:
        if url.strip():
            return course_builder.intake_url(url), course_builder.LEARNER_SOURCE
        return course_builder.intake_text(text), course_builder.LEARNER_SOURCE
    except course_builder.IntakeRefused as exc:
        raise SourceRefused(exc.refusal.reason, code=exc.refusal.code,
                            detail=getattr(exc.refusal, 'detail', '') or '') from exc


def build_course(user: Any, *, query: str = '', candidate_id: str = '', text: str = '',
                 url: str = '', title: str = '', subject: str = '', level: str = '',
                 fetcher: Callable[[str], str] | None = None) -> BuiltCourse:
    """Turn a source - found by search, or supplied - into a planned course.

    Resolution order, first match wins:

    1. an explicit ``candidate_id``, for a learner who picked one off a search;
    2. a ``query``, searching and taking the most promising *buildable* candidate;
    3. a ``url``, which the learner pasted and the builder fetches itself;
    4. pasted ``text``;
    5. nothing, refused with the reason and the ways to supply one.

    The level defaults to what the learner's goal implies and can always be overridden:
    a harness that silently chose a level from a keyword would be making a claim about
    the learner it cannot support.
    """
    candidate: Candidate | None = None
    notes: list[str] = []

    if candidate_id:
        candidate = find(candidate_id)
        if candidate is None:
            raise SourceRefused(
                'That source is no longer remembered. Search again and pick it from the '
                'results, or paste the material yourself.',
                code='candidate_expired')
        if not candidate.can_build_course:
            raise SourceRefused(
                f'{candidate.title!r} cannot be turned into a course: it is '
                f'{candidate.licence_class or "a reference"} rather than licence-cleared for '
                f'ingestion, so this harness may link to it and read nothing from it. Paste '
                f'the material yourself if you have the right to use it.',
                code='source_not_buildable', licence_class=candidate.licence_class)
    elif query.strip():
        found = search(query)
        notes.extend(found.notes)
        candidate = next((item for item in found.candidates if item.can_build_course), None)
        if candidate is None:
            raise SourceRefused(
                f'No source that this harness may build a course from matched {query!r}. '
                f'The candidates below are offered as references; paste your own material '
                f'to build a course from it.',
                code='no_buildable_source', detail='; '.join(notes))
    elif url.strip() or text.strip():
        intake, source = _supplied(url=url, text=text)
        return _finish(user, intake, source, None, title=title, subject=subject, level=level)
    else:
        raise SourceRefused('Supply a search query, a source to search for, pasted text, or an '
                            'https URL.', code='missing_source')

    intake = intake_for(candidate, article_fetcher=fetcher)
    source = policy_for(candidate)
    return _finish(user, intake, source, candidate, title=title or candidate.title,
                   subject=_subject_for(candidate, subject), level=level)


def _finish(user: Any, intake: Any, source: Any, candidate: Candidate | None, *,
            title: str, subject: str, level: str) -> BuiltCourse:
    """Plan, then personalise. Two steps, in that order, always.

    The plan is built before personalisation reads it because the personalisation
    reports the learner's pace against the *actual* concept count rather than an
    estimate of it, and a course refused for having too few concepts must never
    produce a personalised plan to go with it.

    The level is settled *before* the plan is built, and defaults to what the
    learner's own goal implies (``level_for``) unless they stated one. It has to be
    settled here rather than after: the level is a field of the plan the learner
    reads, so a course built for an exam goal is labelled as one rather than being
    labelled custom and told about the exam in a side channel. ``personalise`` then
    reports the same level with its reason, and both read the same function, so the
    two can never disagree about what the learner asked for.
    """
    goal = str(_field(user, 'goal', '') or '')
    chosen_level = (level or '').strip() or level_for(goal)[0]
    try:
        plan = course_builder.plan_course(intake, title=title, subject=subject,
                                          level=chosen_level, source=source)
    except course_builder.BuildRefused as exc:
        raise SourceRefused(exc.refusal.reason, code=exc.refusal.code,
                            detail=getattr(exc.refusal, 'detail', '') or '') from exc
    personalisation = personalise(user, plan, candidate)
    return BuiltCourse(plan=plan, candidate=candidate, personalisation=personalisation)


WIKIPEDIA_SEARCH = _default_wikipedia_search
WIKIPEDIA_ARTICLE = _default_wikipedia_article

__all__ = ['BuiltCourse', 'Candidate', 'Personalisation', 'SEARCH_LIMIT', 'SearchResult',
           'SourceRefused', 'WIKIPEDIA_ARTICLE', 'WIKIPEDIA_SEARCH', 'build_course', 'find',
           'forget', 'intake_for', 'level_for', 'normalise_wiki_text', 'personalise',
           'policy_for', 'search', 'search_enabled']
