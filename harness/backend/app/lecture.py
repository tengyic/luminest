"""A 45-minute auto-lecture: one storyboard, one board page per segment.

The lesson procedure answers "which activity next" for a self-paced lesson. This module
answers a different request: "teach me for forty-five minutes without making me drive".
It compiles a spoken storyboard from the concept's own material, then, at each segment,
applies that segment's vector drawing to the shared board and resolves one image or video.

The model is allowed to improve the prose, never to invent facts. If it is unavailable or
returns something that cannot be validated, the deterministic storyboard below is used.
Every segment is therefore playable offline: the client speaks the narration, shows the
media when one clears the licence gate, and the board is drawn through the normal board
mutation path (server-assigned ids, versioned writes).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from .harness import provider
from .harness import board as boards
from .harness import media, video, video_search

DEFAULT_MINUTES = 45
#: Fifteen ~three-minute segments fit a 45-minute lecture, give the learner a page turn
#: every few minutes, and leave a short "say it back" pause between them.
TARGET_SEGMENTS = 15
MAX_SEGMENTS = 18
CACHE_SECONDS = 7 * 24 * 3600
MAX_NARRATION_CHARS = 6000
MAX_SOURCE_CHARS = 9000


def _safe_concept(value: str) -> str:
    return re.sub(r'[^a-z0-9_.-]+', '-', (value or 'concept').casefold())[:80].strip('-')


def _cache_path(settings, concept_id: str, minutes: int) -> Path:
    return Path(settings.data_dir) / 'lectures' / f'{_safe_concept(concept_id)}-{minutes}.json'


def _read_cache(settings, concept_id: str, minutes: int) -> dict[str, Any] | None:
    path = _cache_path(settings, concept_id, minutes)
    try:
        if not path.exists() or time.time() - path.stat().st_mtime > CACHE_SECONDS:
            return None
        payload = json.loads(path.read_text(encoding='utf-8'))
        return payload if isinstance(payload, dict) and payload.get('segments') else None
    except (OSError, ValueError):
        return None


def _write_cache(settings, concept_id: str, minutes: int, payload: Mapping[str, Any]) -> None:
    path = _cache_path(settings, concept_id, minutes)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        staging = path.with_suffix('.json.part')
        staging.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        staging.replace(path)
    except OSError:
        # A read-only data dir must not make the lecture fail. The storyboard is still
        # returned; it simply will be recompiled on the next request.
        pass


def _lesson_text(lesson: Mapping[str, Any] | None) -> str:
    """Flatten the authored lesson into the prose a lecturer can speak.

    A block body is already the lesson's own wording; re-using it is what keeps the
    fallback from inventing content. Empty or malformed blocks are skipped rather than
    rendered as "None".
    """
    if not isinstance(lesson, Mapping):
        return ''
    parts: list[str] = []
    for block in lesson.get('blocks') or []:
        if not isinstance(block, Mapping):
            continue
        for key in ('title', 'body', 'text', 'prompt', 'explanation', 'caption'):
            value = block.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
        for item in block.get('bullets') or []:
            if isinstance(item, str) and item.strip():
                parts.append(item.strip())
        for item in block.get('rows') or []:
            if isinstance(item, str) and item.strip():
                parts.append(item.strip())
    joined = '\n\n'.join(parts).strip()
    if not joined:
        for key in ('summary', 'description'):
            value = lesson.get(key)
            if isinstance(value, str) and value.strip():
                joined = value.strip()
                break
    return joined[:MAX_SOURCE_CHARS]


def _sentences(text: str) -> list[str]:
    clean = re.sub(r'\s+', ' ', text or '').strip()
    if not clean:
        return []
    parts = re.split(r'(?<=[.!?])\s+', clean)
    return [p.strip() for p in parts if len(p.strip()) > 12]


def _page_ops(title: str, bullets: Sequence[str], index: int) -> list[dict[str, Any]]:
    """A readable whiteboard page in the board's 6000x4000 space.

    Each segment is its own page: the route clears the previous page before applying these
    ops. That is a page turn, not a lie about accumulation; the learner sees one idea at a
    time instead of nine overlapping diagrams.
    """
    y = 260
    ops: list[dict[str, Any]] = [
        {'type': 'text', 'text': title[:120], 'x': 360, 'y': y, 'w': 2600, 'h': 90,
         'size': 46},
        {'type': 'line', 'points': [[360, y + 110], [2960, y + 110]],
         'colour': '#2F5D50'},
        {'type': 'rect', 'x': 340, 'y': y + 150, 'w': 2700, 'h': 820,
         'colour': '#8AA79B'},
    ]
    for row, bullet in enumerate(list(bullets)[:4]):
        ops.append({'type': 'text', 'text': str(bullet)[:220],
                    'x': 410, 'y': y + 210 + row * 170, 'w': 2550, 'h': 130,
                    'size': 30})
    if index % 2 == 0:
        ops.append({'type': 'text', 'text': f'{index + 1}', 'x': 3160, 'y': y + 40,
                    'w': 180, 'h': 80, 'size': 28})
    return ops


def _fallback(concept: Mapping[str, Any], lesson: Mapping[str, Any] | None,
              minutes: int) -> dict[str, Any]:
    title = str(concept.get('title') or concept.get('id') or 'This topic').strip()
    source = _lesson_text(lesson)
    sentences = _sentences(source)
    summary = str(concept.get('summary') or (lesson or {}).get('summary') or '').strip()
    pool = sentences or _sentences(summary) or [
        f'This lesson introduces {title}.',
        'The authored material for this concept is brief; the lecture stays with what is written.',
    ]

    def excerpt(start: int, count: int) -> list[str]:
        if not pool:
            return []
        picked = []
        for offset in range(count):
            picked.append(pool[(start + offset) % len(pool)])
        return picked

    plan_titles = [
        ('The destination', 'What this lecture will make you able to do.'),
        ('The core idea', 'The definition the rest of the lecture rests on.'),
        ('Why it works', 'The relationship behind the rule, not just the rule.'),
        ('A worked example', 'One instance, followed step by step.'),
        ('The visual model', 'The same idea as a diagram on the board.'),
        ('Where learners slip', 'The mistake this concept is designed to catch.'),
        ('A second pass', 'The same idea seen from another angle.'),
        ('Your turn', 'A question to answer before the recap.'),
        ('Recap and next step', 'Three things to keep, and what comes next.'),
    ]
    n = len(plan_titles)
    per = max(120, (minutes * 60) // n)
    segments: list[dict[str, Any]] = []
    for i, (segment_title, focus) in enumerate(plan_titles):
        body = excerpt(i * 2, 3)
        quote = ' '.join(body) if body else f'The lesson material defines {title}.'
        narration = (
            f'{segment_title}. {focus}\n\n'
            f'From the lesson: {quote}\n\n'
            'Stay with that sentence for a moment. Say it back in your own words before '
            'we add the next piece; a definition you can restate is worth more than one '
            'you can only recognise. '
        )
        if i == 0:
            narration += (f'We will spend about {minutes} minutes on {title}. The plan is '
                          'definition, worked example, a diagram, the common error, then '
                          'practice and a recap.')
        elif i == 3:
            narration += ('Watch the moves rather than the answer: what is identified first, '
                          'what is substituted, and where the check happens.')
        elif i == 4:
            narration += ('The board now carries the structure: the title, the key terms, '
                          'and the relationship between them. Trace it with your eyes before '
                          'we speak about it.')
        elif i == 6:
            narration += ('A second pass is not repetition. It changes the surface while the '
                          'structure stays fixed, which is how you test whether you own it.')
        elif i == 7:
            narration += ('Pause the lecture here if you need to. Answer in your own words, '
                          'then resume; the next segment checks the answer against the idea.')
        elif i == 8:
            narration += ('Keep the definition, the example, and the error. Those three are '
                          'the minimum you need before practice.')
        bullets = body[:3] or [focus, f'Concept: {title}', 'Say it back in your own words.']
        media_kind = 'image' if i in (1, 4) else ('video' if i == 2 else 'none')
        query = ''
        if media_kind == 'image':
            query = f'{title} diagram' if i == 4 else title
        elif media_kind == 'video':
            query = f'{title} explained'
        segments.append({
            'index': i + 1,
            'title': segment_title,
            'narration': narration.strip(),
            'bullets': bullets,
            'board_ops': _page_ops(segment_title, bullets, i),
            'media': {'kind': media_kind, 'query': query},
            'duration_seconds': per,
            'speech_seconds': per,
            'pause_seconds': 0,
        })
    return {
        'title': f'{title} — a {minutes}-minute lecture',
        'concept_id': str(concept.get('id') or ''),
        'minutes': minutes,
        'segments': segments,
        'source': 'deterministic-fallback',
        'created_at': int(time.time()),
    }


def _prompt(concept: Mapping[str, Any], lesson: Mapping[str, Any] | None,
            minutes: int) -> list[dict[str, str]]:
    title = str(concept.get('title') or concept.get('id') or '')
    summary = str(concept.get('summary') or (lesson or {}).get('summary') or '')
    source = _lesson_text(lesson)
    system = (
        'You are designing a spoken lecture for one learner. Return strict JSON only, no '
        'markdown fence. The learner will hear the narration and watch a shared whiteboard; '
        'the board is drawn from board_ops, so each segment must be visual as well as spoken. '
        'Never invent a fact that is not in the supplied lesson material. If the material is '
        'thin, teach the definition, one worked example and one common error, and say plainly '
        'that the source is brief. Keep the tone of a patient teacher, not a textbook.'
    )
    user = (
        f'Concept: {title}\n'
        f'Summary: {summary}\n'
        f'Target length: {minutes} minutes.\n\n'
        f'Lesson material:\n{source or "(no authored lesson; use the summary only)"}\n\n'
        f'Produce exactly {TARGET_SEGMENTS} segments. Each segment must have:\n'
        '- "title": <= 8 words.\n'
        '- "narration": 300-360 words of spoken prose, no markdown, no bullet list. It must '
        'stand alone when read aloud; one idea, one worked move, one check for understanding.\n'
        '- "bullets": 2-4 short phrases for the slide.\n'
        '- "board_ops": 4-8 drawing ops. Allowed ops: '
        '{"type":"text","text":...,"x":...,"y":...,"w":...,"h":...,"size":...}, '
        '{"type":"rect","x":...,"y":...,"w":...,"h":...,"colour":"#2F5D50"}, '
        '{"type":"line","points":[[x,y],[x,y]],"colour":"#2F5D50"}. '
        'Coordinates live in a 6000x4000 space. One idea per op; build the diagram, do not '
        'write a paragraph on the board.\n'
        '- "media": {"kind":"image"|"video"|"none","query":"2-4 word noun phrase"}. '
        'The query is sent to an image/video search API, so use words a caption would '
        'contain: "fraction bar", "pizza fractions", "equivalent fractions number line". '
        'Do not write a sentence. Use at most two images and one video across the lecture.\n'
        '- "duration_seconds": integer, about 300 for five minutes.\n\n'
        'Return {"title": "...", "segments": [...]} only.'
    )
    return [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]


def _parse_json(text: str) -> dict[str, Any] | None:
    raw = (text or '').strip()
    if raw.startswith('```'):
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
    start, end = raw.find('{'), raw.rfind('}')
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(raw[start:end + 1])
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _normalise(raw: Mapping[str, Any], concept: Mapping[str, Any],
               lesson: Mapping[str, Any] | None, minutes: int) -> dict[str, Any] | None:
    rows = raw.get('segments')
    if not isinstance(rows, list):
        return None
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows[:MAX_SEGMENTS]):
        if not isinstance(row, Mapping):
            continue
        title = ' '.join(str(row.get('title') or '').split())[:120]
        narration = str(row.get('narration') or '').strip()
        if not title or len(narration) < 120:
            continue
        bullets = [str(b).strip()[:220] for b in (row.get('bullets') or [])
                   if str(b).strip()][:5]
        ops = row.get('board_ops')
        ops = [op for op in (ops if isinstance(ops, list) else [])
               if isinstance(op, Mapping) and op.get('type') in {'text', 'rect', 'line'}][:12]
        if not ops:
            ops = _page_ops(title, bullets or [title], i)
        media_row = row.get('media') if isinstance(row.get('media'), Mapping) else {}
        kind = str(media_row.get('kind') or 'none').lower()
        if kind not in {'image', 'video', 'none'}:
            kind = 'none'
        query = ' '.join(str(media_row.get('query') or '').split())[:180]
        out.append({
            'index': i + 1,
            'title': title,
            'narration': narration[:MAX_NARRATION_CHARS],
            'bullets': bullets,
            'board_ops': ops,
            'media': {'kind': kind, 'query': query},
            'duration_seconds': int(row.get('duration_seconds') or 0),
        })
    if len(out) < 6:
        return None
    # A lecture that never shows a picture is a podcast. Keep the model's choices when it
    # made them, but guarantee one image and one video slot so the player has something to
    # turn to; a slot whose search refuses still renders an honest reference card.
    concept_title = str(concept.get('title') or 'the concept')
    if not any(s['media']['kind'] == 'video' for s in out):
        out[min(3, len(out) - 1)]['media'] = {
            'kind': 'video', 'query': f'{concept_title} explained'}
    if not any(s['media']['kind'] == 'image' for s in out):
        out[min(1, len(out) - 1)]['media'] = {
            'kind': 'image', 'query': f'{concept_title} diagram'}
    total = max(5, int(minutes)) * 60
    # Speech time is estimated from the narration itself, not trusted from the model: a
    # model that writes 280 words for a five-minute slot leaves three minutes of silence.
    # The remainder becomes a deliberate "say it back" pause after the speech, so the
    # lecture still ends at the requested length without pretending the talking filled it.
    for segment in out:
        words = len(str(segment.get('narration') or '').split())
        segment['speech_seconds'] = max(45, round(words / 2.4))
    speech_total = sum(s['speech_seconds'] for s in out)
    pause_total = max(0, total - speech_total)
    pause_each = pause_total / max(1, len(out))
    for i, segment in enumerate(out):
        segment['pause_seconds'] = max(0, round(pause_each))
        segment['duration_seconds'] = max(45, segment['speech_seconds'] + segment['pause_seconds'])
        segment['index'] = i + 1
    # Push the rounding remainder into the last segment so the progress bar ends at 45:00.
    drift = total - sum(s['duration_seconds'] for s in out)
    out[-1]['duration_seconds'] = max(45, out[-1]['duration_seconds'] + drift)
    out[-1]['pause_seconds'] = max(0, out[-1]['pause_seconds'] + drift)
    return {
        'title': ' '.join(str(raw.get('title') or '').split())[:160]
                 or f'{concept.get("title") or "Lecture"} — a {minutes}-minute lecture',
        'concept_id': str(concept.get('id') or ''),
        'minutes': int(minutes),
        'segments': out,
        'source': 'model',
        'created_at': int(time.time()),
    }


def compile_lecture(settings, concept: Mapping[str, Any],
                    lesson: Mapping[str, Any] | None = None, *,
                    minutes: int = DEFAULT_MINUTES) -> dict[str, Any]:
    """Compile or load a lecture storyboard. Never raises: fallback is a real lecture."""
    minutes = max(5, min(90, int(minutes or DEFAULT_MINUTES)))
    concept_id = str(concept.get('id') or concept.get('concept_id') or '')
    cached = _read_cache(settings, concept_id, minutes)
    if cached:
        return cached

    try:
        text = provider.chat(
            settings, _prompt(concept, lesson, minutes),
            max_tokens=12000, temperature=0.4, reasoning='off',
            max_reply_chars=240_000,
        )
        raw = _parse_json(text or '')
        normalised = _normalise(raw, concept, lesson, minutes) if raw else None
    except Exception:  # noqa: BLE001 - a bad model turn must not break the lecture
        normalised = None
    if normalised:
        _write_cache(settings, concept_id, minutes, normalised)
        return normalised

    fallback = _fallback(concept, lesson, minutes)
    _write_cache(settings, concept_id, minutes, fallback)
    return fallback


def _op_node(op: Mapping[str, Any]) -> dict[str, Any] | None:
    kind = str(op.get('type') or '')
    if kind == 'text':
        text = ' '.join(str(op.get('text') or '').split())[:2000]
        if not text:
            return None
        size = max(9.0, min(96.0, float(op.get('size') or 16)))
        return {'kind': 'text', 'x': float(op.get('x') or 0), 'y': float(op.get('y') or 0),
                'w': float(op.get('w') or 1200), 'h': float(op.get('h') or 90),
                'payload': {'text': text, 'size': size}}
    if kind == 'rect':
        width, height = float(op.get('w') or 0), float(op.get('h') or 0)
        if width <= 0 or height <= 0:
            return None
        return {'kind': 'shape', 'x': float(op.get('x') or 0), 'y': float(op.get('y') or 0),
                'w': width, 'h': height,
                'payload': {'shape': 'rect', 'colour': str(op.get('colour') or '#2F5D50')[:32]}}
    if kind == 'line':
        points = op.get('points')
        if not isinstance(points, list) or len(points) < 2:
            return None
        clean = [[float(p[0]), float(p[1])] for p in points[:32]
                 if isinstance(p, (list, tuple)) and len(p) == 2]
        if len(clean) < 2:
            return None
        return {'kind': 'path', 'x': 0, 'y': 0, 'w': 0, 'h': 0,
                'payload': {'points': clean, 'colour': str(op.get('colour') or '#2F5D50')[:32]}}
    return None


def ensure_board(settings, board_id: str, owner_id: str, title: str) -> dict[str, Any]:
    doc = boards.load_owned(settings, board_id, owner_id)
    if doc is None:
        doc = boards.create(settings, owner_id=owner_id, board_id=board_id, title=title)
    return doc


def apply_board_page(settings, board_id: str, owner_id: str,
                     ops: Sequence[Mapping[str, Any]], *,
                     reset: bool = True) -> int:
    """Replace the board with one segment's page. Returns the new version.

    The delete + add batch is one versioned write, so the learner never sees a half-erased
    page. A stale base version is retried once against the refreshed document; a persistent
    conflict returns the current version instead of failing the lecture.
    """
    ensure_board(settings, board_id, owner_id, board_id)
    for _ in range(3):
        doc = boards.load_owned(settings, board_id, owner_id) or {}
        mutations: list[dict[str, Any]] = []
        if reset:
            mutations.extend({'action': 'delete', 'id': node['id']}
                             for node in doc.get('nodes', [])[:120])
        for op in list(ops)[:12]:
            node = _op_node(op)
            if node is not None:
                mutations.append({'action': 'add', 'node': node})
        if not mutations:
            return int(doc.get('version') or 1)
        base = int(doc.get('version') or 1)
        updated, reason = boards.apply_mutations(
            settings, board_id, owner_id=owner_id, base_version=base,
            mutations=mutations[:128], actor='lecture')
        if updated is not None:
            return int(updated.get('version') or base + 1)
        if reason != 'version':
            break
    return boards.latest_version(settings, board_id)


def _reference_rows(candidates: Sequence[Any], limit: int = 3) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        if getattr(candidate, 'rejected', ''):
            continue
        rows.append({
            'title': str(getattr(candidate, 'title', '') or '')[:160],
            'source': str(getattr(candidate, 'source', '') or '')[:40],
            'licence': str(getattr(candidate, 'licence_code', '') or '')[:60],
            'url': str(getattr(candidate, 'landing_page_url', '') or '')[:500],
            'thumb_url': str(getattr(candidate, 'thumb_url', '') or '')[:500],
        })
        if len(rows) >= limit:
            break
    return rows


def segment_media(settings, concept: Mapping[str, Any], segment: Mapping[str, Any],
                  course_id: str) -> dict[str, Any]:
    """Resolve one segment's media. A refusal returns references, never a fake file."""
    wanted = segment.get('media') if isinstance(segment.get('media'), Mapping) else {}
    kind = str(wanted.get('kind') or 'none').lower()
    query = ' '.join(str(wanted.get('query') or '').split())[:180]
    title = str(concept.get('title') or '')
    summary = str(concept.get('summary') or '')
    if kind == 'image':
        query = query or title
        try:
            found = media.find_image(settings, title, summary=summary,
                                     alt_text=f'Illustration of {title}', query=query)
        except Exception as exc:  # noqa: BLE001
            return {'kind': 'none', 'query': query,
                    'note': f'Image search failed: {type(exc).__name__}.'}
        asset = found.get('asset')
        if asset:
            payload = media.asset_payload(asset)
            payload.update(kind='image', query=query, outcome=found.get('outcome'))
            return payload
        references: list[dict[str, Any]] = []
        try:
            searched = media.search(settings, query, depth=8)
            references = _reference_rows(searched.get('candidates') or [])
        except Exception:  # noqa: BLE001
            pass
        return {'kind': 'image_reference', 'query': query,
                'outcome': found.get('outcome') or 'no_cleared_candidate',
                'references': references,
                'note': ('No image passed the licence, size and relevance gates. '
                         'The candidates below are references, not copied files.')}
    if kind == 'video':
        cards: list[dict[str, Any]] = []
        concept_row = {'id': concept.get('id') or '', 'title': title,
                       'keywords': list(concept.get('keywords') or [])}
        try:
            # Verify so the card carries a real embed URL. The allowlist already holds a
            # verified oEmbed result; this is usually a cache hit, not a new network call.
            cards = video.resolve(settings, course_id, str(concept.get('id') or ''),
                                  verify_remote=True)
            if not cards:
                video_search.curate_for_concept(settings, concept_row, course_id, limit=6)
                cards = video.resolve(settings, course_id, str(concept.get('id') or ''),
                                      verify_remote=True)
        except Exception:  # noqa: BLE001
            cards = []
        if cards:
            card = cards[0]
            return {'kind': 'video', 'query': query,
                    'title': card.get('title', ''), 'channel': card.get('channel', ''),
                    'embed_url': card.get('embed_url', ''),
                    'watch_url': card.get('watch_url', ''),
                    'thumbnail': card.get('thumbnail', ''),
                    'status': card.get('status', ''),
                    'licence': card.get('licence', ''),
                    'provider': card.get('provider', '')}
        return {'kind': 'video_reference', 'query': query,
                'note': 'No verified video is curated for this concept yet.'}
    return {'kind': 'none', 'query': query}
