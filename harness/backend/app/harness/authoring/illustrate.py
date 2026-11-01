"""Real photographs in an authored textbook.

The foundry could write a whole course and every lesson in it would be text. That was a
real gap rather than a stylistic one: a lesson about a phospholipid bilayer that never
shows one is asking the learner to build the picture from a sentence, and the parts of a
subject that are about what something *looks like* were exactly the parts a text-only
pipeline served worst.

The image machinery already existed (``app/harness/media.py``: search, licence gate, cache,
manifest, attribution, lesson assignments, and ``GET /lessons/{id}`` already inserts the
photograph blocks). What did not exist was any way for authoring - or for the tutor - to
reach it. This module is that connection, and nothing else:

* :func:`illustrate` walks a course that has just been built and attaches the photograph
  each concept needs, one per concept by default.
* :func:`attach` puts a *named* image into one lesson, which is the move a tutor makes
  after searching: "that one, next to the definition".
* :func:`coverage` reports what a textbook currently carries, for the review page.

Four commitments, inherited from the media module and from the foundry.

**Nothing is fabricated.** An image is a real asset with a source, an author, a licence
code and an attribution string. There is no placeholder, no generated illustration
standing in for a photograph, and no "image pending" block: a concept that found nothing
is reported as a concept with no photograph and the reasons its candidates were dropped.

**Offline is a normal outcome.** An instance with ``HARNESS_MEDIA_ENABLED`` off, or with
no network, produces a text-only textbook and a report saying so. It does not fail the
build, and it does not silently pretend the images were attached.

**The assignment is the unit of work.** Attaching writes the same row the batch fetch
writes, so the lesson route needs no branch of its own. The images are deliberately *not*
stored inside the authored record: they are content-addressed files with a manifest, and
copying a sha list into the course JSON would let a record claim an image whose bytes had
since been deleted. The index is the truth, and the lesson resolves against it every read.

**A refusal says which rule refused.** A clipboard paste has no verified licence; a cached
asset with no attribution cannot satisfy a CC licence; a lesson at its photograph cap
cannot take another. Each comes back as a named outcome with a sentence, because the
caller is usually a model that has to choose a different move.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .. import media
from . import synthesize

#: How many photographs one concept may carry. Re-exported from the media module rather
#: than restated: two caps that disagree is one cap too many.
MAX_PER_CONCEPT = media.MAX_LESSON_IMAGES

#: One photograph per concept by default. A lesson has one place where a photograph
#: illustrates and several where the deterministic concept map is the honest picture, so
#: the default is the concept itself rather than a photo album per lesson.
DEFAULT_LIMIT = 1


@dataclass
class Illustration:
    """What one illustration pass did, concept by concept.

    ``outcome`` is the coarse answer a caller branches on; ``concepts`` is the detail a
    human reads when the answer is ``partial`` and they want to know which concept missed.
    """

    course_id: str
    outcome: str
    considered: int = 0
    assigned: int = 0
    concepts: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {'course_id': self.course_id, 'outcome': self.outcome,
                'considered': self.considered, 'assigned': self.assigned,
                'concepts': self.concepts, 'notes': self.notes,
                'cap_per_concept': MAX_PER_CONCEPT}

    def summary(self) -> dict[str, Any]:
        """The compact form for a tool payload: counts and the concepts that missed."""
        missed = [{'id': item.get('id'), 'title': item.get('title'),
                   'outcome': item.get('outcome'), 'why': item.get('why')}
                  for item in self.concepts if not item.get('assigned')]
        return {'course_id': self.course_id, 'outcome': self.outcome,
                'concepts_considered': self.considered, 'images_attached': self.assigned,
                'concepts_without_image': missed[:12], 'notes': self.notes}


def _entry(course: synthesize.AuthoredCourse, concept_id: str) -> dict[str, Any] | None:
    return course.concepts.get(str(concept_id or '').strip())


def _why(result: Mapping[str, Any]) -> str:
    """One sentence for a concept that gained no photograph."""
    images = result.get('images') or []
    if not images:
        return str((result.get('notes') or ['No image need was identified.'])[0])
    first = images[0]
    outcome = str(first.get('outcome') or '')
    if outcome == 'network_disabled':
        return ('Network media is disabled for this instance, so nothing was searched for. '
                'The lesson keeps its deterministic figure.')
    if outcome == 'no_cleared_candidate':
        # Three different facts used to share this sentence. A reviewer can act on them,
        # but only if they are told which one happened: nothing came back for the title,
        # things came back and the licence refused them, or things came back and they were
        # not about the concept.
        seen = first.get('seen')
        rejections = first.get('rejections') or []
        refused = [r for r in rejections if 'Licence' in str(r.get('why') or '')
                   or 'may not cache' in str(r.get('why') or '')]
        query = str(first.get('query') or '')
        if seen == 0:
            return (f'The image search returned nothing at all for {query!r}. That is a '
                    f'fact about the query, not about the filter: no candidate existed to '
                    f'refuse. The lesson keeps its deterministic figure.')
        if refused and len(refused) == len(rejections):
            return (f'All {len(rejections)} candidate(s) were refused on licence grounds; '
                    f'none could be cached. The lesson keeps its deterministic figure.')
        return (f'{len(rejections)} candidate(s) came back and none was about {query!r} '
                f'enough to show. The lesson keeps its deterministic figure.')
    if outcome == 'all_downloads_failed':
        return 'Candidates cleared the gate but none could be downloaded.'
    if outcome in {'unavailable'}:
        return 'The image service could not be reached.'
    rejections = first.get('rejections') or []
    if rejections:
        return f'{len(rejections)} candidate(s) were rejected: ' \
               f'{rejections[0].get("why") or "no reason recorded"}'
    return f'No image was attached (outcome {outcome or "unknown"}).'


def illustrate(settings, course: synthesize.AuthoredCourse, *, limit: int = DEFAULT_LIMIT,
               only: Iterable[str] | None = None) -> Illustration:
    """Attach a real photograph to each concept of a freshly built course.

    Runs after the course has passed its audit and been stored, never before: the audit
    decides whether the *content* may ship, and a network call must not sit in the path
    that decides that. An instance that cannot reach the network therefore still publishes
    a complete, audited, text-only textbook.
    """
    course_id = str(course.plan.id)
    if not media.enabled(settings):
        return Illustration(
            course_id=course_id, outcome='offline',
            considered=0, assigned=0,
            notes=['Network media is disabled for this instance (HARNESS_MEDIA_ENABLED). '
                   'The textbook was published without photographs; every lesson keeps its '
                   'deterministic concept map. Set the flag and re-run to illustrate it.'])
    wanted = max(1, min(int(limit or DEFAULT_LIMIT), MAX_PER_CONCEPT))
    wanted_ids = {str(item).strip() for item in only} if only else None
    concepts: list[dict[str, Any]] = []
    assigned = 0
    for unit in course.plan.units:
        for concept in unit.concepts:
            entry = _entry(course, concept.id)
            if entry is None:
                continue
            if wanted_ids is not None and concept.id not in wanted_ids:
                continue
            result = media.fetch_for_lesson(
                settings, concept_id=str(entry.get('id') or concept.id),
                title=str(entry.get('title') or concept.title),
                summary=str(entry.get('summary') or ''),
                blocks=entry.get('blocks') or [], course_id=course_id, limit=wanted)
            count = int(result.get('assigned') or 0)
            if not count:
                # Nothing cleared this time, so whatever an earlier pass attached has to go:
                # a stricter gate that silently leaves the old picture in place would make
                # the report ("no photograph") and the lesson disagree, and the lesson is
                # what a learner reads.
                media.withdraw_lesson_images(settings, str(entry.get('id') or concept.id))
            assigned += count
            row = {'id': str(entry.get('id') or concept.id), 'title': concept.title,
                   'unit': unit.title, 'assigned': count,
                   'outcome': 'attached' if count else str(result.get('outcome') or 'no_images'),
                   'why': '' if count else _why(result)}
            if count:
                row['images'] = [
                    {'sha256': (image.get('asset') or {}).get('sha256'),
                     'title': (image.get('asset') or {}).get('title'),
                     'licence': (image.get('asset') or {}).get('licence_code'),
                     'credit': (image.get('asset') or {}).get('attribution_text'),
                     'source': (image.get('asset') or {}).get('source')}
                    for image in result.get('images') or [] if image.get('asset')]
            concepts.append(row)
    considered = len(concepts)
    if not considered:
        outcome = 'nothing_to_illustrate'
    elif assigned == 0:
        outcome = 'refused'
    elif assigned < considered:
        outcome = 'partial'
    else:
        outcome = 'ok'
    notes = [
        f'{assigned} photograph(s) attached across {considered} concept(s); the cap is '
        f'{wanted} per concept and {MAX_PER_CONCEPT} at most.',
        'Each photograph carries its author, licence and attribution, and is served by the '
        'lesson route like any other block. Nothing was generated: an image that did not '
        'clear the licence gate is reported and not attached.',
    ]
    if outcome in {'refused', 'partial'}:
        notes.append('Concepts without a photograph are listed with the reason, not filled '
                     'with a placeholder. Their deterministic figure is unchanged.')
    return Illustration(course_id=course_id, outcome=outcome, considered=considered,
                        assigned=assigned, concepts=concepts, notes=notes)


def attach(settings, course: synthesize.AuthoredCourse, concept_id: str, *,
           query: str = '', sha256: str = '', block_index: int = 1,
           caption: str = '') -> dict[str, Any]:
    """Put one chosen image into one lesson of an authored course.

    The tutor's move after a search: it has a query, or a ``sha256`` from an earlier
    ``image_search``/``find_image``, and it wants that image next to the definition. The
    concept must belong to this course - an id from another course would write an
    assignment no lesson of this book could ever resolve.
    """
    entry = _entry(course, concept_id)
    if entry is None:
        return {'concept_id': str(concept_id or ''), 'attached': False,
                'outcome': 'unknown_concept',
                'notes': [f'{course.plan.id!r} has no concept {concept_id!r}.']}
    result = media.attach_image(
        settings, str(entry.get('id') or concept_id),
        title=str(entry.get('title') or ''), summary=str(entry.get('summary') or ''),
        sha256=str(sha256 or ''), query=str(query or ''),
        block_index=int(block_index or 1), caption=str(caption or ''),
        alt_text=f'Photograph illustrating {entry.get("title") or concept_id}')
    result['course_id'] = str(course.plan.id)
    result['concept_title'] = str(entry.get('title') or '')
    return result


def _absolute(settings, path: Any) -> str:
    """A cached-photograph path that means the same thing from any working directory.

    The manifest stores ``media/images/<sha>.jpg`` relative to the data directory. A
    review page or an export reads it while standing somewhere else, so the relative form
    silently points at nothing and the photograph is dropped from the artifact that was
    supposed to prove the licence was cleared.
    """
    text = str(path or '')
    if not text:
        return ''
    candidate = Path(text)
    if candidate.is_absolute():
        return str(candidate)
    return str(Path(str(settings.data_dir)) / candidate)


def coverage(settings, course: synthesize.AuthoredCourse) -> dict[str, Any]:
    """What this textbook currently carries: per-concept photographs and credits.

    Read from the live index, not from the record, so the answer is what a learner would
    actually be served. Used by the review page and by ``--list``.
    """
    rows: list[dict[str, Any]] = []
    illustrated = 0
    for unit in course.plan.units:
        for concept in unit.concepts:
            entry = _entry(course, concept.id)
            if entry is None:
                continue
            blocks = media.lesson_photograph_blocks(settings, str(entry.get('id') or concept.id))
            photos = [item['block'] for item in blocks]
            if photos:
                illustrated += 1
            rows.append({'id': str(entry.get('id') or concept.id), 'title': concept.title,
                         'unit': unit.title, 'count': len(photos),
                         'images': [{'title': photo.get('title'),
                                     'licence': photo.get('licence'),
                                     'credit': photo.get('credit'),
                                     'source': photo.get('source'),
                                     'src': photo.get('src'),
                                     'sha256': photo.get('sha256'),
                                     # Absolute, so an export or a review page opened from
                                     # disk can read the bytes. The manifest stores it
                                     # relative to the data directory, and a relative path
                                     # in a standalone HTML resolves against whatever
                                     # directory the reviewer happened to open it from.
                                     'cache_path': _absolute(settings, photo.get('cache_path')),
                                     'alt': photo.get('alt'),
                                     'caption': photo.get('caption')}
                                    for photo in photos]})
    total = len(rows)
    return {'course_id': str(course.plan.id), 'concepts': total,
            'illustrated': illustrated, 'bare': total - illustrated,
            'rows': rows,
            'notes': [] if illustrated else
            ['No concept in this textbook carries a photograph yet.']}


__all__ = ['DEFAULT_LIMIT', 'MAX_PER_CONCEPT', 'Illustration', 'attach', 'coverage',
           'illustrate']
