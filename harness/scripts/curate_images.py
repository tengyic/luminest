"""Curate the shipped image seed: one pass, at build time, so runtime stays offline.

The desktop build runs with ``media_enabled`` off — ``privacy.md`` says outbound media is off
by default and the audit indicted the bundle for contradicting it. But ``media.acquire`` is
the only way a deck gets a picture, and with the network off it can only ever answer
``network_disabled``. The deck then fell back to ``LuminfestArt.image(deterministicFrom:)``: a
decorative pattern that looks like an illustration and is not one. That is worse than a blank
frame, because a learner cannot tell the difference — and neither could the screenshots that
raised this: a slide captioned "FIGURE 1 · DETERMINISTIC" was drawn as if it were a figure.

Curation therefore happens here, once, with the network available. The result is data the
bundle ships (``backend/app/media_packs/image_seed.json`` plus the bytes in
``image_seed/``), and ``media.shipped_for`` installs it into an instance's cache on first ask
with no network at all. Every candidate still has to clear the same licence gate, the same
lexical relevance test and the same minimum dimensions a live fetch does — this is a faster
curator, not a weaker gate. A lesson the pack does not cover keeps its honest reason.

**Keys are lesson ids, not graph node ids.** ``procedure_service.assets_for`` resolves the
authored lesson id and passes *that* to ``_deck_image``, so curating by graph node id writes
rows nothing ever reads.

Run from ``harness/``::

    ui-tests/.venv/bin/python scripts/curate_images.py --courses integrated_math_1
    ui-tests/.venv/bin/python scripts/curate_images.py --per-course 3
    ui-tests/.venv/bin/python scripts/curate_images.py --dry-run --courses physics

The seed is rewritten after every lesson, so an interrupted pass keeps what it already
curated and the same command resumes instead of starting over. Re-running merges into the
existing seed; ``--refresh`` re-curates lessons that already have a row.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS / 'backend'))

PACK_DIR = HARNESS / 'backend' / 'app' / 'media_packs'
DEFAULT_OUT = PACK_DIR / 'image_seed.json'
DEFAULT_BYTES = PACK_DIR / 'images'


def _is_sha(value: str) -> bool:
    """A content address, as ``shipped_pack`` will require it on the way back in."""
    return len(value) == 64 and all(char in '0123456789abcdef' for char in value)


#: Long edge of a curated picture, in pixels.
#:
#: Provider downloads are print-sized: the first sixteen curated pictures came to 48 MB, one
#: of them 12 MB, because the media pipeline asks for at least 1200x800 and takes what it is
#: given. The pack travels *inside the bundle*, so a hundred of those is a download nobody
#: agreed to. A slide is 190 pt tall and a textbook column is narrower than a page; 1600 px
#: is more than either can use at 2x.
MAX_EDGE = 1600
JPEG_QUALITY = 82


def _shrink(body: bytes, suffix: str) -> tuple[bytes, str, int, int]:
    """Re-encode one curated picture to a size that belongs in an application bundle.

    Returns ``(bytes, suffix, width, height)``. The bytes are re-hashed by the caller and the
    row is rebuilt around the new digest, so the index still names its own content: a pack
    that kept the provider's digest next to re-encoded bytes would be a pack whose names lie,
    and every integrity check downstream would have to be taught to distrust them.

    Pillow is a declared runtime dependency (``requirements.txt``), so using it here adds
    nothing to the build. If it is somehow absent the original bytes travel unchanged and the
    pack is merely large — a big picture is a cost, not a correctness problem.
    """
    try:
        from PIL import Image
    except ImportError:
        return body, suffix, 0, 0
    import io

    try:
        with Image.open(io.BytesIO(body)) as opened:
            image = opened.convert('RGB')
            image.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=JPEG_QUALITY, optimize=True,
                       progressive=True)
            return buffer.getvalue(), '.jpg', image.width, image.height
    except Exception:      # noqa: BLE001 - an image we cannot re-encode still ships as-is
        return body, suffix, 0, 0


def _write_atomically(target: Path, body: bytes) -> None:
    """Write ``body`` to ``target`` without ever exposing a half-written file.

    The name is the content hash, so a file already sitting at ``target`` is the same fact as
    one this call would have written. That matters because ``os.replace`` here goes through the
    host's file-operation broker, which has been seen to move the staging file and *then* report
    it missing; without this tolerance a single such hiccup ends a pass that has already spent
    minutes on the network. A genuinely missing result still raises.
    """
    staged = target.with_suffix(target.suffix + '.tmp')
    try:
        staged.write_bytes(body)
        os.replace(staged, target)
    except FileNotFoundError:
        if not target.is_file():
            raise
    finally:
        staged.unlink(missing_ok=True)


def _lesson_summary(lesson: dict) -> str:
    """The prose a relevance filter can rank on, taken from the authored lesson blocks.

    Only used as ``support`` (ranking), never as the query: a ten-word phrase is not a query
    these APIs answer. Empty is fine — a concept with no written summary is not penalised.
    """
    for key in ('summary', 'description', 'objective'):
        text = str(lesson.get(key) or '').strip()
        if text:
            return text[:400]
    return ''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--per-course', type=int, default=0,
                        help='curate only the first N lessons of each course; 0 means all')
    parser.add_argument('--courses', default='',
                        help='comma-separated course ids; default is every course')
    parser.add_argument('--out', default=str(DEFAULT_OUT))
    parser.add_argument('--bytes-dir', default=str(DEFAULT_BYTES))
    parser.add_argument('--pause', type=float, default=0.4,
                        help='seconds between lessons, so the provider is not hammered')
    parser.add_argument('--refresh', action='store_true',
                        help='re-curate lessons that already have a row')
    parser.add_argument('--dry-run', action='store_true',
                        help='report what would be curated, write nothing')
    parser.add_argument('--repack', action='store_true',
                        help='re-encode the pictures already in the pack, with no network')
    args = parser.parse_args()

    # A throwaway data directory: the download path writes a real manifest and real bytes as
    # it goes, and this must not touch the operator's data directory. Bytes are copied out of
    # it into the pack once each lesson is settled.
    state = Path(tempfile.mkdtemp(prefix='curate-images-'))
    for key in list(os.environ):
        if key.startswith('HARNESS_'):
            del os.environ[key]
    os.environ.update({
        'HARNESS_ENV': 'development',
        'HARNESS_MEDIA_ENABLED': '1',      # the whole point: the network is available *here*
        'HARNESS_DATA_DIR': str(state),
        'HARNESS_TUTOR_PROVIDER': 'offline',
        'HARNESS_ALLOWED_HOSTS': 'localhost,127.0.0.1',
    })

    import app.config as cfg
    cfg.load_dotenv = lambda path=None: {}       # an operator .env must not steer this
    settings = cfg.Settings.from_env()
    print(f'state: {state}')

    from app import courses
    from app.curriculum import course_concepts
    from app.harness import media

    wanted = {name.strip() for name in args.courses.split(',') if name.strip()}
    specs = [spec for spec in courses.COURSES if not wanted or spec.id in wanted]
    if not specs:
        raise SystemExit(f'no such course: {args.courses}')

    out = Path(args.out)
    bytes_dir = Path(args.bytes_dir)

    merged: dict[str, dict] = {}
    if out.is_file():
        try:
            merged = {str(k): dict(v) for k, v in json.loads(out.read_text()).items()
                      if isinstance(v, dict)}
        except ValueError:
            merged = {}

    curated = skipped = failed = 0
    started = time.time()

    def save() -> None:
        """Merge what has been curated so far into the seed file and write it.

        Called after every lesson, not once at the end. A full pass is hundreds of network
        searches and runs for a long time, so an interrupted pass has to leave the work it
        already did in the file. Because ``merged`` is also what decides what is still
        ``todo``, the same command afterwards resumes instead of starting over.
        """
        ordered = {key: merged[key] for key in sorted(merged) if merged[key]}
        out.parent.mkdir(parents=True, exist_ok=True)
        # Written to a sibling and renamed: this file is rewritten after every lesson, and a
        # reader that opens it mid-write would find truncated JSON — which ``shipped_pack``
        # treats as "no pack at all", i.e. every deck silently loses its picture.
        staged = out.with_suffix('.json.tmp')
        staged.write_text(json.dumps(ordered, indent=2, ensure_ascii=False) + '\n',
                          encoding='utf-8')
        os.replace(staged, out)

    if args.repack:
        # Re-encode what the pack already carries, with no network at all. The original bytes
        # are still in the pack, so shrinking them is a local transformation — this is how a
        # pack curated before the size cap existed becomes shippable without paying for every
        # search a second time.
        def total() -> int:
            return sum((bytes_dir / str(row.get('file'))).stat().st_size
                       for row in merged.values()
                       if (bytes_dir / str(row.get('file'))).is_file())

        before = total()
        changed = 0
        for lesson_id, row in list(merged.items()):
            source = bytes_dir / str(row.get('file') or '')
            if not source.is_file():
                continue
            body, suffix, width, height = _shrink(source.read_bytes(), source.suffix or '.jpg')
            sha = hashlib.sha256(body).hexdigest()
            target = bytes_dir / f'{sha}{suffix}'
            if target != source:
                _write_atomically(target, body)
                source.unlink(missing_ok=True)
                changed += 1
            row.update({'sha256': sha, 'bytes': len(body), 'file': f'{sha}{suffix}'})
            if suffix == '.jpg':
                row['mime'] = 'image/jpeg'
            if width and height:
                row.update({'width': width, 'height': height})
        save()
        print(f'repacked {changed} of {len(merged)} picture(s): '
              f'{before / 1e6:.1f} MB -> {total() / 1e6:.1f} MB')
        return 0

    for spec in specs:
        lessons = course_concepts(spec.id)
        ids = list(lessons)
        if args.per_course:
            ids = ids[:args.per_course]
        have = set(merged)
        todo = [lesson_id for lesson_id in ids if args.refresh or lesson_id not in have]
        print(f'\n=== {spec.id} ({len(todo)} of {len(lessons)} lessons to curate)')
        for lesson_id in todo:
            lesson = lessons[lesson_id]
            title = str(lesson.get('title') or '').strip()
            if not title:
                skipped += 1
                print(f'  - {lesson_id[:38]:40} no title to search for')
                continue
            try:
                result = media.find_image(settings, title,
                                          summary=_lesson_summary(lesson),
                                          alt_text=f'Photograph illustrating {title}')
            except Exception as error:                  # one bad lesson must not stop the pass
                failed += 1
                print(f'  ! {lesson_id}: {type(error).__name__}: {error}')
                continue

            asset = result.get('asset') or {}
            sha = str(asset.get('sha256') or '')
            source = Path(settings.data_dir) / str(asset.get('cache_path') or '')
            if not _is_sha(sha) or not source.is_file():
                skipped += 1
                print(f'  - {lesson_id[:38]:40} {str(result.get("outcome"))[:34]:36} '
                      f'{str((result.get("notes") or [""])[-1])[:40]}')
                time.sleep(args.pause)
                continue

            body = source.read_bytes()
            # The name is the content hash, so the same photograph curated for two lessons is
            # one file. It also means the index cannot point at bytes that are not the bytes:
            # a mismatch here is a corrupt pack, and shipping it would serve the wrong picture
            # under the right attribution.
            if hashlib.sha256(body).hexdigest() != sha:
                failed += 1
                print(f'  ! {lesson_id}: downloaded bytes do not hash to the recorded sha')
                time.sleep(args.pause)
                continue

            suffix = source.suffix or '.jpg'
            if not args.dry_run:
                # Shrink first, then name: the digest in the index is the digest of the bytes
                # the bundle carries, never of the provider's original.
                body, suffix, width, height = _shrink(body, suffix)
                sha = hashlib.sha256(body).hexdigest()
                bytes_dir.mkdir(parents=True, exist_ok=True)
                target = bytes_dir / f'{sha}{suffix}'
                if not target.is_file():
                    _write_atomically(target, body)
                row = {key: value for key, value in asset.items() if key != 'cache_path'}
                row.update({'sha256': sha, 'bytes': len(body), 'file': f'{sha}{suffix}',
                            'mime': 'image/jpeg' if suffix == '.jpg' else str(asset.get('mime'))})
                if width and height:
                    row.update({'width': width, 'height': height})
                merged[lesson_id] = row
            curated += 1
            print(f'  = {lesson_id[:38]:40} {str(asset.get("title"))[:40]:42} '
                  f'{str(asset.get("licence_code"))[:16]}')
            if not args.dry_run:
                save()
            time.sleep(args.pause)

    if args.dry_run:
        print(f'\ndry run: curated {curated} · no picture {skipped} · errors {failed}'
              f' · {time.time() - started:.0f}s · nothing written')
        return 0

    save()

    # Integrity pass: drop any row whose bytes are absent or do not hash to their own name.
    # ``_install_shipped`` already refuses a missing file, so this is not what keeps the deck
    # honest — it is what keeps the *pack* honest, so the build fails loudly here rather than
    # a lesson quietly reverting to a decorative pattern on someone else's machine.
    broken = []
    for lesson_id, row in list(merged.items()):
        path = bytes_dir / str(row.get('file') or '')
        if not path.is_file():
            broken.append((lesson_id, 'bytes missing'))
            del merged[lesson_id]
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != str(row.get('sha256') or ''):
            broken.append((lesson_id, 'bytes do not match sha256'))
            del merged[lesson_id]
    if broken:
        save()
        for lesson_id, why in broken:
            print(f'  ! dropped {lesson_id}: {why}')

    total_bytes = sum((bytes_dir / str(row.get('file'))).stat().st_size
                      for row in merged.values()
                      if (bytes_dir / str(row.get('file'))).is_file())
    print(f'\ncurated this pass: {curated} · no picture: {skipped} · errors: {failed}'
          f' · {time.time() - started:.0f}s')
    print(f'seed now holds {len(merged)} row(s), {total_bytes / 1e6:.1f} MB of bytes: {out}')
    return 0 if curated else 1


if __name__ == '__main__':
    sys.exit(main())
