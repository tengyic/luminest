"""Author a course from the command line, with no client and no external authoring tool.

Run::

    # what the foundry will enforce, before writing anything
    python scripts/author_course.py --methodology

    # plan and audit a blueprint without storing it
    python scripts/author_course.py --blueprint my_course.json --preview

    # build, audit, store and publish
    python scripts/author_course.py --blueprint my_course.json

    # author from a topic, using the configured model provider
    python scripts/author_course.py --topic "cell biology" --units 3

    # list what this deployment has authored, and what could not be loaded
    python scripts/author_course.py --list

    # withdraw a course from every registry and delete it
    python scripts/author_course.py --delete cell_biology

Why this exists
---------------
The HTTP surface is for a client and the toolbox tools are for a teaching turn. Neither
helps an operator on a box with a shell, and an authoring capability that only works
through the product's own UI is not fully migrated - it is one integration short. This
script is the third entrance to the same library calls, and it prints the audit rather
than hiding it: a refusal on the command line shows exactly what the HTTP route would
have returned as a 422.

Exit codes: 0 success, 1 refused (audit or unreadable blueprint), 2 usage or environment.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import courses, curriculum  # noqa: E402
from app.config import Settings  # noqa: E402
from app.harness.authoring import (audit as audit_module, blueprint,  # noqa: E402
                                   draft as draft_module, illustrate as illustrate_module,
                                   methodology, registry, synthesize)


def _settings() -> Settings:
    return Settings.from_env()


def _course_for(record: registry.Record) -> synthesize.AuthoredCourse | None:
    """Re-synthesize a stored course, for the commands that need its lesson blocks.

    The two record kinds are rebuilt by the function that built them: ``build`` derives a
    graph of its own, and calling it on an overlay's blueprint would produce a *second*
    course standing next to the pack instead of a patch on it. The branch matters for
    ``--rerender``, which exists precisely so that a change to the figure layer can be
    seen without paying a model to write the prose again.
    """
    plan, _ = blueprint.parse(dict(record.blueprint),
                              author=record.blueprint.get('author') or 'operator')
    if plan is None:
        return None
    if record.kind != 'overlay':
        return synthesize.build(plan)
    return synthesize.build_overlay(plan, course=courses.course(record.id),
                                    graph=courses.graph_for(record.id),
                                    base=curriculum.course_concepts(record.id))


def _print_illustration(report: illustrate_module.Illustration) -> None:
    print(f'illustration: {report.outcome} — {report.assigned}/{report.considered} '
          f'concept(s) carry a photograph')
    for row in report.concepts:
        if row.get('assigned'):
            for image in row.get('images') or []:
                print(f'  +  {row["id"]:28s} {image.get("licence") or "?"} · '
                      f'{(image.get("credit") or "")[:64]}')
        else:
            print(f'  -  {row["id"]:28s} {row.get("outcome")}: {row.get("why")}')
    for note in report.notes[:2]:
        print(f'  {note}')


def _print_audit(report: audit_module.Audit) -> None:
    print(f'audit: {"PASS" if report.ok else "REFUSED"} '
          f'({len(report.errors)} error(s), {len(report.warnings)} warning(s))')
    for finding in report.errors:
        print(f'  error   {finding.code:24s} {finding.path}: {finding.message}')
    for finding in report.warnings[:12]:
        print(f'  warning {finding.code:24s} {finding.path}: {finding.message}')
    print('stats: ' + json.dumps(report.stats, sort_keys=True))


def _print_course(course: synthesize.AuthoredCourse, problems) -> None:
    print(f'course: {course.course.title} ({course.plan.id})')
    print(f'  units {len(course.plan.units)}, concepts {course.concept_count}, '
          f'items {course.question_count}, digest {course.plan.digest()}')
    for problem in blueprint.blocking(problems):
        print(f'  blocking {problem.code}: {problem.path}: {problem.message}')


_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{title} — authored by the harness</title>
<style>
:root {{ --paper:#F7F5EF; --card:#fff; --ink:#22301F; --muted:#5C6B57; --line:#E5E7DB;
         --accent:#3F6B4A; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; padding:48px 24px; background:var(--paper); color:var(--ink);
  font:16px/1.6 ui-serif, Georgia, serif; }}
main {{ max-width:820px; margin:0 auto; }}
h1 {{ font-size:34px; line-height:1.2; margin:0 0 8px; letter-spacing:-.01em; }}
h2 {{ font-size:22px; margin:44px 0 6px; }}
h3 {{ font-size:18px; margin:28px 0 4px; }}
.meta {{ color:var(--muted); font-size:14px; margin-bottom:28px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:12px;
  padding:18px 20px; margin:12px 0; }}
.block {{ margin:10px 0 0; }}
.block b {{ display:block; font:600 13px/1.4 ui-sans-serif, system-ui, sans-serif;
  text-transform:uppercase; letter-spacing:.06em; color:var(--accent); margin-bottom:4px; }}
.block p {{ margin:0; white-space:pre-line; }}
ul {{ margin:6px 0 0; padding-left:20px; }}
li {{ margin:4px 0; }}
.correct {{ color:var(--accent); font-weight:600; }}
.tag {{ font:600 11px/1 ui-sans-serif, system-ui, sans-serif; text-transform:uppercase;
  letter-spacing:.06em; color:var(--muted); }}
.audit {{ border-radius:10px; padding:12px 16px; margin:18px 0 6px; font-size:14px;
  border:1px solid var(--line); background:var(--card); }}
.audit.pass {{ border-left:4px solid var(--accent); }}
.audit.fail {{ border-left:4px solid #A33A2B; }}
.audit ul {{ margin:8px 0 0; }}
.audit li {{ font:13px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; }}
figure {{ margin:16px 0 4px; padding:0; }}
figure img {{ display:block; width:100%; height:auto; border-radius:8px;
  border:1px solid var(--line); background:var(--paper); }}
figure.diagram {{ margin:14px 0 2px; }}
figure.diagram svg {{ display:block; width:100%; height:auto; border-radius:8px;
  border:1px solid var(--line); background:#fff; }}
figure.diagram figcaption {{ margin-top:8px; font-size:13px; color:var(--muted); }}
figcaption {{ margin-top:6px; font-size:13px; color:var(--muted); }}
figcaption .credit {{ display:block; font-size:12px; opacity:.85; }}
.nophoto {{ margin:14px 0 0; padding:10px 12px; border:1px dashed var(--line);
  border-radius:8px; font-size:13px; color:var(--muted); }}
.review {{ margin:0 0 22px; padding:10px 14px; border-left:4px solid #A33A2B;
  background:var(--card); border-radius:8px; font:13px/1.55 ui-sans-serif, system-ui,
  sans-serif; }}
</style></head><body><main>
<h1>{title}</h1>
<div class="meta">{subject} · {units} units · {concepts} concepts · {questions} items ·
blueprint digest {digest} · authored by the harness ({author})</div>
<p>{description}</p>
<div class="review">{review}</div>
{audit}
{body}
</main></body></html>
"""


#: A review copy is opened from disk, so a photograph that is only reachable over the
#: media route renders as a broken image. The bytes are already on this machine; inlining
#: them is what makes the file reviewable without a server.
_INLINE_PHOTO_LIMIT = 700_000

#: The served photographs are up to a couple of megabytes, which is right for a lesson and
#: wrong for a page that carries fifty of them. A review copy gets a copy scaled for
#: reading; the served bytes are untouched.
_INLINE_PHOTO_WIDTH = 900

#: How many times a refused overlay is sent back for correction. Two, because the second
#: round exists for the case where a rewrite fixes six of eight complaints, and a third has
#: never been the difference between a course and no course: a model that cannot satisfy a
#: length after two rounds of being told is not going to on the third.
REPAIR_ROUNDS = 2


def _shrink(data: bytes, ceiling: int) -> bytes:
    """A copy of the image small enough to inline, or ``b''`` if that is not possible.

    Resizing does not touch the licence: the credit line and the licence code travel with
    the row, not with the pixels. It does mean the review copy is not byte-identical to
    what a learner is served, which is why the page says the diagram parameters and the
    credit rather than implying it is the served asset.
    """
    try:
        from io import BytesIO

        from PIL import Image
    except ImportError:
        return b''
    try:
        with Image.open(BytesIO(data)) as picture:
            picture = picture.convert('RGB')
            picture.thumbnail((_INLINE_PHOTO_WIDTH, _INLINE_PHOTO_WIDTH))
            out = BytesIO()
            picture.save(out, format='JPEG', quality=82, optimize=True)
            blob = out.getvalue()
    except (OSError, ValueError):
        return b''
    return blob if len(blob) <= ceiling else b''


def _image_src(image: dict) -> str:
    """A ``src`` that resolves in a file the reviewer opened, not just over HTTP.

    ``media`` hands out ``/api/v1/media/images/<sha>/bytes``, which is right for the
    product and wrong for a document: beside a ``file://`` URL it is an absolute path on
    the root of the reviewer's disk. So the cached bytes are inlined as a data URL when
    they are present - scaled down first if the asset is large - and the route is kept as
    the fallback rather than silently dropped, so a reviewer with the server running still
    sees the photograph when the bytes are nowhere on this machine.
    """
    path = str(image.get('cache_path') or '')
    if path:
        try:
            data = Path(path).read_bytes()
        except OSError:
            data = b''
        if data and len(data) > _INLINE_PHOTO_LIMIT:
            data = _shrink(data, _INLINE_PHOTO_LIMIT)
        if data:
            mime = 'image/png' if data[:8] == b'\x89PNG\r\n\x1a\n' else 'image/jpeg'
            return f'data:{mime};base64,{base64.b64encode(data).decode()}'
    return str(image.get('src') or '')


def _render_blocks(entry: dict) -> str:
    """One lesson's blocks, with a diagram rendered as a diagram.

    A ``figure`` block carries an inline SVG produced by the deterministic economics
    templates. Rendering it as a paragraph would show a reviewer the caption of a diagram
    and call it a lesson, which is exactly the "looks complete" failure the audit exists
    to catch - so the SVG is embedded as-is (it is generated by our own code from stated
    parameters, never model output) and its caption is printed underneath.
    """
    chunks: list[str] = []
    for block in entry.get('blocks') or []:
        title = escape(str(block.get('title') or ''))
        body = escape(str(block.get('body') or ''))
        svg = str(block.get('svg') or '')
        if svg.startswith('<svg'):
            chunks.append(f'<div class="block"><b>{title}</b>'
                          f'<figure class="diagram">{svg}'
                          f'<figcaption>{body}</figcaption></figure></div>')
            continue
        chunks.append(f'<div class="block"><b>{title}</b><p>{body}</p></div>')
    return ''.join(chunks)


def render_html(course: synthesize.AuthoredCourse, report: audit_module.Audit,
                coverage: dict | None = None) -> str:
    """A standalone review copy of the course: lessons, items, answers and photographs.

    An authoring capability needs a surface where a human can *read* what was produced.
    The JSON is the record; this is the review. The audit verdict sits at the top
    because "did this pass, and what was flagged" is the first question a reviewer asks,
    and the photographs are shown with their credit line because that credit is a condition
    of the licence rather than a nicety.
    """
    photos: dict[str, list[dict]] = {}
    for row in (coverage or {}).get('rows') or []:
        photos[str(row.get('id') or '')] = list(row.get('images') or [])

    chunks: list[str] = []
    for unit in course.plan.units:
        chunks.append(f'<h2>{escape(unit.title)}</h2>'
                      f'<div class="meta">{escape(unit.objective)}</div>')
        for concept in unit.concepts:
            entry = course.concepts.get(concept.id) or {}
            node = course.graph.nodes.get(concept.id)
            difficulty = getattr(node, 'difficulty', '—')
            blocks = _render_blocks(entry)
            images = ''.join(
                f'<figure><img src="{escape(_image_src(image))}" '
                f'alt="{escape(str(image.get("alt") or ""))}" loading="lazy">'
                f'<figcaption>{escape(str(image.get("caption") or image.get("title") or ""))}'
                f'<span class="credit">{escape(str(image.get("credit") or ""))}</span>'
                f'</figcaption></figure>'
                for image in photos.get(str(entry.get('id') or concept.id), []))
            if not images:
                images = ('<div class="nophoto">No photograph: no candidate cleared the '
                          'licence and relevance gate.</div>')
            items = [item for item in course.questions.values()
                     if item.get('concept_id') == concept.id]
            rendered_items = []
            for item in sorted(items, key=lambda i: str(i.get('category'))):
                options = []
                for option in item.get('options') or []:
                    chosen = option.get('id') == item.get('answer_id')
                    options.append(
                        f'<li class="correct">{escape(str(option.get("text") or ""))}</li>'
                        if chosen else
                        f'<li>{escape(str(option.get("text") or ""))}</li>')
                rendered_items.append(
                    f'<div class="block"><span class="tag">'
                    f'{escape(str(item.get("category") or ""))}</span>'
                    f'<p>{escape(str(item.get("prompt") or ""))}</p>'
                    f'<ul>{"".join(options)}</ul></div>')
            chunks.append(
                f'<div class="card"><h3>{escape(concept.title)}</h3>'
                f'<div class="meta">difficulty {escape(str(difficulty))} · '
                f'{len(items)} items</div>{blocks}{images}'
                f'<h3 style="margin-top:22px">What it asks</h3>'
                f'{"".join(rendered_items)}</div>')
    # The review status goes above the lessons, not below them. A reviewer opening this
    # page is deciding whether to trust it, and the two facts that decide that are how
    # much of it is teaching material rather than a title with a paragraph, and who has
    # read it. Neither is visible by scrolling, and the second one is "nobody".
    with_depth = sum(1 for entry in course.concepts.values()
                     if any(str(block.get('kind')) == 'worked_example'
                            for block in entry.get('blocks') or ()))
    with_figure = sum(1 for entry in course.concepts.values() if entry.get('figure'))
    # The sentence about the audit has to match what the audit said. An earlier version
    # printed "passed a mechanical audit" on a file whose own header said REFUSED, which
    # is the exact failure this whole subsystem exists to prevent: a document that claims
    # a check it did not pass.
    if report.ok:
        verdict = ('The prose was written by a model and passed a mechanical audit that '
                   'checks every answer against the lesson it claims to come from.')
    else:
        errors = len(report.errors)
        verdict = (f'The prose was written by a model and the mechanical audit REFUSED it: '
                   f'{errors} error(s), listed below. The gaps those errors name are real '
                   f'and are visible in the lessons under them.')
    # The photograph count belongs in the same sentence as the figure count: "does this
    # lesson have a picture" is the question a reviewer actually asks, and a diagram is one.
    # Leaving it out let a page with 14 photographs read as if every lesson had one.
    with_photo = sum(1 for rows in photos.values() if rows)
    review = (f'{with_depth} of {course.concept_count} concepts carry a full lesson '
              f'(worked example and named misconception); {with_figure} carry a diagram '
              f'drawn from stated parameters, and {with_photo} also carry a licence-cleared '
              f'photograph with its credit. {verdict} Nobody has read it. It is a draft '
              f'for review, not reviewed material.')
    return _HTML.format(
        title=escape(course.course.title), subject=escape(course.course.subject),
        units=len(course.plan.units), concepts=course.concept_count,
        questions=course.question_count, digest=escape(course.plan.digest()),
        author=escape(course.plan.author), description=escape(course.course.description),
        review=escape(review),
        audit=_render_audit(report, escape), body=''.join(chunks))


def _render_audit(report: audit_module.Audit, escape) -> str:
    """The verdict banner. Errors block a store; warnings do not."""
    verdict = 'PASS' if report.ok else 'REFUSED'
    count = (f'{len(report.errors)} error(s), {len(report.warnings)} warning(s)')
    if not report.findings:
        return f'<div class="audit pass">audit: {verdict} — {count}</div>'
    rows = ''.join(
        f'<li>{escape(finding.severity)} · {escape(finding.code)} · '
        f'{escape(finding.path)}<br>{escape(finding.message)}</li>'
        for finding in report.findings)
    kind = 'pass' if report.ok else 'fail'
    return (f'<div class="audit {kind}">audit: {verdict} — {count}'
            f'<ul>{rows}</ul></div>')


def _run_rerender(args, settings) -> int:
    """Rebuild a stored course and write the review copy again, with no model call.

    The figure layer and the item builders are deterministic functions of the blueprint,
    so a change to either is invisible until the course is rebuilt - and rebuilding it by
    re-authoring would mean paying a model to produce the same prose. This rebuilds from
    the saved blueprint instead, which is the same code path a preview takes.
    """
    registry.hydrate(settings)
    record = registry.get(args.rerender)
    if record is None:
        print(f'no authored course {args.rerender!r}', file=sys.stderr)
        return 2
    course = _course_for(record)
    if course is None:
        print(f'the stored blueprint for {args.rerender!r} no longer parses', file=sys.stderr)
        return 1
    report = audit_module.audit(course, overlay=record.kind == 'overlay')
    _print_course(course, [])
    _print_audit(report)
    if args.illustrate:
        # The one network call this script makes. Kept here rather than in a flag of its own
        # because "rebuild the stored course" and "now attach the photographs to it" are the
        # same review step, and a separate command would need its own copy of the reload.
        _print_illustration(illustrate_module.illustrate(settings, course))
    if not args.render:
        print('nothing written: pass --render HTML to save a review copy')
        return 0
    args.render.parent.mkdir(parents=True, exist_ok=True)
    # The photographs are read from the local index, so this costs no network call: a
    # rebuild shows the same pictures the run that stored it had attached, which is what
    # makes it a faithful review of the stored course rather than of the blueprint alone.
    args.render.write_text(
        render_html(course, report, illustrate_module.coverage(settings, course)),
        encoding='utf-8')
    print(f'review copy -> {args.render}')
    return 0


def _run_overlay(args, settings) -> int:
    """Write lessons into a course that already ships.

    The difference from every other entry point in this script: the structure is not
    asked for. ``frame_from_entries`` takes the course's own concept ids, units, tiers and
    difficulties, and only the prose is generated. That is what makes the output land on
    the existing graph instead of standing next to it.
    """
    from app import courses, curriculum

    registry.hydrate(settings)
    try:
        spec = courses.course(args.overlay)
    except courses.UnknownCourse as exc:
        print(str(exc), file=sys.stderr)
        return 2
    base = curriculum.course_concepts(spec.id)
    if not base:
        print(f'{spec.id!r} declares no concepts; there is nothing to write into',
              file=sys.stderr)
        return 2
    document = blueprint.frame_from_entries(
        {'id': spec.id, 'title': spec.title, 'subject': spec.subject,
         'description': spec.description, 'expected_weeks': spec.expected_weeks,
         'level': 'intro'},
        list(base.values()))
    plan, problems = blueprint.parse(document, author='template')
    if plan is None:
        print('the course could not be framed into a blueprint:', file=sys.stderr)
        for problem in blueprint.blocking(problems):
            print(f'  {problem.code}: {problem.path}: {problem.message}', file=sys.stderr)
        return 1
    print(f'framed {len(plan.units)} unit(s), {len(plan.concepts())} concept(s) '
          f'from {spec.id!r}')
    writing_notes: list[str] = []
    try:
        written = draft_module.expand(settings, plan, notes_out=writing_notes,
                                      progress=lambda line: print(line, flush=True))
    except draft_module.DraftUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except draft_module.DraftRefused as exc:
        print(f'refused: {exc}', file=sys.stderr)
        for finding in exc.findings[:12]:
            print(f'  {finding.code} {finding.path}: {finding.message}', file=sys.stderr)
        return 1
    course = synthesize.build_overlay(written, course=spec,
                                      graph=courses.graph_for(spec.id), base=base)
    # ``overlay=True`` is not a convenience flag: without it the course-level shape rules
    # are applied to a patch and refuse it for having nine units when the patch has one.
    report = audit_module.audit(course, overlay=True)
    # A refusal that names lessons is a refusal about prose, and prose can be corrected by
    # telling the model what the validator said. Without this loop the audit's complaint
    # never reaches the only party able to act on it, and a run that wrote 57 lessons
    # stores none of them because nine summaries were three words short.
    for round_number in range(1, REPAIR_ROUNDS + 1):
        if report.ok:
            break
        complaints = draft_module.refused_prose(report)
        if not complaints:
            break
        print(f'repair round {round_number}: {len(complaints)} concept(s) refused, '
              f'asking for those again', flush=True)
        try:
            written = draft_module.repair(settings, written, complaints,
                                          progress=lambda line: print(line, flush=True))
        except draft_module.DraftUnavailable as exc:
            print(str(exc), file=sys.stderr)
            break
        course = synthesize.build_overlay(written, course=spec,
                                          graph=courses.graph_for(spec.id), base=base)
        report = audit_module.audit(course, overlay=True)
    # "covers 57 of 57 concepts" is true of every overlay, because the concepts come from
    # the pack: the object always has all of them. What a reader needs is how many came
    # back with teaching prose, which is the number the audit's thin-lesson findings are
    # about, so that is the number printed.
    with_prose = sum(1 for concept in written.concepts()
                     if concept.example or concept.misconception or concept.application)
    print(f'the writing pass returned prose for {with_prose} of '
          f'{len(plan.concepts())} concept(s)')
    if writing_notes:
        print(f'the writing pass left {len(writing_notes)} note(s); each one is prose the '
              f'model did not deliver on the first try:')
        for note in writing_notes[:20]:
            print(f'  note {note}')
    _print_course(course, [])
    _print_audit(report)
    if args.render:
        args.render.parent.mkdir(parents=True, exist_ok=True)
        args.render.write_text(render_html(course, report), encoding='utf-8')
        print(f'review copy -> {args.render}')
    if args.preview:
        print('preview only; nothing stored')
        return 0
    try:
        record = registry.store_overlay(settings, course, report, replace=args.replace)
    except audit_module.CourseRefused as refused:
        print(f'refused: {refused}', file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f'stored overlay {record.id} -> {registry.root(settings) / (record.id + ".json")}')
    if args.illustrate:
        illustrated = illustrate_module.illustrate(settings, course)
        _print_illustration(illustrated)
        if args.render:
            args.render.write_text(
                render_html(course, report,
                            illustrate_module.coverage(settings, course)), encoding='utf-8')
            print(f'review copy -> {args.render}')
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Author a course inside the harness.')
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--blueprint', type=Path,
                        help='path to a blueprint JSON document')
    source.add_argument('--topic', help='author from a topic with the configured model')
    source.add_argument('--methodology', action='store_true',
                        help='print the authoring profile and its limits')
    source.add_argument('--list', action='store_true', help='list authored courses')
    source.add_argument('--delete', metavar='COURSE_ID', help='withdraw and delete a course')
    parser.add_argument('--overlay', metavar='COURSE_ID',
                        help='write lessons into an existing shipped course instead of '
                             'creating a new one; the concept ids, units and prerequisite '
                             'edges are taken from that course\'s own pack')
    parser.add_argument('--units', type=int, default=3, help='units to draft (default 3)')
    parser.add_argument('--level', default='intro')
    parser.add_argument('--profile', default='default')
    parser.add_argument('--preview', action='store_true',
                        help='synthesize and audit; store nothing')
    parser.add_argument('--replace', action='store_true',
                        help='overwrite an existing authored course')
    parser.add_argument('--render', type=Path, metavar='HTML',
                        help='write a standalone review copy of the course to this path')
    parser.add_argument('--illustrate', action='store_true',
                        help='after storing, attach a real licence-cleared photograph to '
                             'each concept (needs HARNESS_MEDIA_ENABLED and a network)')
    parser.add_argument('--images', metavar='COURSE_ID',
                        help='print the photographs a stored course actually serves')
    parser.add_argument('--rerender', metavar='COURSE_ID',
                        help='rebuild a stored course from its saved blueprint and write a '
                             'fresh review copy; costs no model calls, so a change to the '
                             'figure layer can be seen without rewriting the prose')
    args = parser.parse_args(argv)

    settings = _settings()

    if args.rerender:
        return _run_rerender(args, settings)

    if args.overlay:
        return _run_overlay(args, settings)

    if args.methodology:
        print(json.dumps(methodology.describe(args.profile), indent=2))
        return 0

    if args.images:
        registry.hydrate(settings)
        record = registry.get(args.images)
        if record is None:
            print(f'no authored course {args.images!r}', file=sys.stderr)
            return 1
        course = _course_for(record)
        if course is None:
            print(f'the stored blueprint for {args.images!r} no longer parses', file=sys.stderr)
            return 1
        report = illustrate_module.coverage(settings, course)
        print(f'{record.id}: {report["illustrated"]}/{report["concepts"]} concepts carry a '
              f'photograph')
        for row in report['rows']:
            if not row['count']:
                print(f'  -  {row["id"]:28s} no photograph')
                continue
            for image in row['images']:
                print(f'  +  {row["id"]:28s} {image.get("licence") or "?"} · '
                      f'{(image.get("credit") or "")[:70]}')
        return 0

    if args.list:
        registry.hydrate(settings)
        for card in registry.listing():
            print(f'{card["id"]:24s} {card["concepts"]:3d} concepts  '
                  f'{card["questions"]:3d} items  audit={"ok" if card["audit_ok"] else "FAILED"}'
                  f'  {card["title"]}')
        for entry in registry.withheld():
            print(f'withheld {entry["file"]}: {entry["reason"]}')
        return 0

    if args.delete:
        if not registry.delete(settings, args.delete):
            print(f'no authored course {args.delete!r}', file=sys.stderr)
            return 1
        print(f'deleted {args.delete}')
        return 0

    if args.topic:
        try:
            drafted = draft_module.draft(settings, args.topic, units=args.units,
                                         level=args.level, profile_name=args.profile)
        except draft_module.DraftUnavailable as exc:
            print(str(exc), file=sys.stderr)
            return 2
        except draft_module.DraftRefused as exc:
            print(f'refused: {exc}', file=sys.stderr)
            for finding in exc.findings[:12]:
                print(f'  {finding.code} {finding.path}: {finding.message}', file=sys.stderr)
            return 1
        _print_course(drafted.course, [])
        _print_audit(drafted.report)
        if args.render:
            args.render.parent.mkdir(parents=True, exist_ok=True)
            args.render.write_text(render_html(drafted.course, drafted.report),
                                   encoding='utf-8')
            print(f'review copy -> {args.render}')
        if args.preview:
            print('preview only; nothing stored')
            return 0
        record = registry.store(settings, drafted.course, drafted.report,
                                replace=args.replace)
        print(f'stored {record.id} -> {registry.root(settings) / (record.id + ".json")}')
        if args.illustrate:
            illustrated = illustrate_module.illustrate(settings, drafted.course)
            _print_illustration(illustrated)
            if args.render:
                args.render.parent.mkdir(parents=True, exist_ok=True)
                args.render.write_text(
                    render_html(drafted.course, drafted.report,
                                illustrate_module.coverage(settings, drafted.course)),
                    encoding='utf-8')
                print(f'review copy -> {args.render}')
        return 0

    if args.blueprint:
        try:
            document = json.loads(args.blueprint.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            print(f'cannot read {args.blueprint}: {exc}', file=sys.stderr)
            return 1
        plan, problems = blueprint.parse(document, author='operator')
        if plan is None:
            print('the blueprint could not be read:', file=sys.stderr)
            for problem in blueprint.blocking(problems):
                print(f'  {problem.code}: {problem.path}: {problem.message}',
                      file=sys.stderr)
            return 1
        course = synthesize.build(plan)
        report = audit_module.audit(course)
        _print_course(course, problems)
        _print_audit(report)
        if args.render:
            args.render.parent.mkdir(parents=True, exist_ok=True)
            args.render.write_text(render_html(course, report), encoding='utf-8')
            print(f'review copy -> {args.render}')
        if args.preview:
            print('preview only; nothing stored')
            return 0
        try:
            record = registry.store(settings, course, report, replace=args.replace)
        except audit_module.CourseRefused as refused:
            print(f'refused: {refused}', file=sys.stderr)
            return 1
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f'stored {record.id} -> {registry.root(settings) / (record.id + ".json")}')
        if args.illustrate:
            illustrated = illustrate_module.illustrate(settings, course)
            _print_illustration(illustrated)
            if args.render:
                args.render.parent.mkdir(parents=True, exist_ok=True)
                args.render.write_text(
                    render_html(course, report,
                                illustrate_module.coverage(settings, course)),
                    encoding='utf-8')
                print(f'review copy -> {args.render}')
        return 0

    parser.print_help()
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
