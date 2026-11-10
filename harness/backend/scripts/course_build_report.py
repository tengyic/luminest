"""Assemble the course-build report from the per-course verification JSON files.

Run:  python scripts/course_build_report.py

Reads ``outputs/course_verification_<id>.json`` (written by
``scripts/course_pipeline.py verify``) and writes one HTML + one JSON summary. No numbers
are typed in by hand: the table is the reports, so a course whose verification failed
cannot appear as green here.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'outputs'
BACKEND = Path(__file__).resolve().parents[1]

#: Display order: the maths ramp first, then the sciences, then the exam-prep courses.
ORDER = [
    'algebra_1', 'geometry', 'algebra_2', 'linear_algebra', 'precalculus',
    'ap_calculus_ab', 'ap_calculus_bc', 'ap_calculus',
    'chemistry', 'ap_chemistry', 'organic_chemistry',
    'biology', 'ap_biology', 'physics', 'astrophysics', 'earth_space_science',
    'act_math', 'act_english',
]


def load() -> list[dict]:
    rows = []
    for path in sorted(OUT.glob('course_verification_*.json')):
        report = json.loads(path.read_text(encoding='utf-8'))
        rows.append(report)
    order = {cid: i for i, cid in enumerate(ORDER)}
    rows.sort(key=lambda r: (order.get(r['course'], 999), r['course']))
    return rows


def esc(value) -> str:
    import html
    return html.escape(str(value))


def main() -> int:
    rows = load()
    total_concepts = sum((r.get('structure') or {}).get('concepts', 0) for r in rows)
    total_sections = sum((r.get('textbook') or {}).get('sections', 0) for r in rows)
    all_fail = [r for r in rows if r['summary']['failed']]
    no_anchor = [r for r in rows if (r.get('textbook') or {}).get('sections', 0) == 0]

    def status(r: dict) -> tuple[str, str]:
        s = r['summary']
        if s['failed']:
            return '#b42318', f"{s['failed']} FAIL"
        if s['skipped']:
            return '#b54708', f"{s['passed']}/{s['total']} · {s['skipped']} SKIP"
        return '#0a7a3d', f"{s['passed']}/{s['total']} PASS"

    table_rows = []
    for r in rows:
        colour, label = status(r)
        st = r.get('structure') or {}
        tb = r.get('textbook') or {}
        spine = tb.get('spine') or '— no CC BY textbook in the catalogue —'
        table_rows.append(f"""<tr>
  <td><code>{esc(r['course'])}</code></td>
  <td>{st.get('units', '')}</td><td>{st.get('topics', '')}</td><td>{st.get('concepts', '')}</td>
  <td>{esc(spine)}</td><td>{tb.get('sections', 0)}</td>
  <td style="color:{colour};font-weight:700">{esc(label)}</td>
</tr>""")

    gap_rows = []
    for r in rows:
        if (r.get('textbook') or {}).get('sections', 0):
            continue
        reason = ''
        for chk in r['checks']:
            if chk['check'] == 'textbook anchoring':
                reason = (chk['detail'] or {}).get('reason', '') if isinstance(chk['detail'], dict) else ''
        gap_rows.append(f"<tr><td><code>{esc(r['course'])}</code></td>"
                        f"<td>{esc((r.get('textbook') or {}).get('spine') or '—')}</td>"
                        f"<td>{esc(reason)}</td></tr>")

    html_doc = f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>Luminfest — Course Build &amp; Textbook Verification</title>
<style>
:root{{--ink:#1a1a1a;--muted:#666;--line:#e3e3e3;--bg:#fff;--panel:#fafafa}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);
 font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}}
.wrap{{max-width:1120px;margin:0 auto;padding:40px 28px 80px}}
h1{{font-size:26px;margin:0 0 6px}} h2{{font-size:17px;margin:34px 0 12px}}
.sub{{color:var(--muted);margin:0 0 22px}}
.banner{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 20px;margin:18px 0 26px}}
.banner b{{font-size:20px}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:14px}}
.cell{{background:#fff;border:1px solid var(--line);border-radius:8px;padding:10px 14px}}
.cell .k{{color:var(--muted);font-size:12px}} .cell .v{{font-size:18px;font-weight:600}}
table{{width:100%;border-collapse:collapse;border:1px solid var(--line);margin-top:8px}}
th,td{{border-bottom:1px solid var(--line);padding:9px 10px;text-align:left;vertical-align:top}}
th{{background:var(--panel);font-size:12px;letter-spacing:.03em;color:var(--muted)}}
code{{background:#f2f3f5;padding:1px 5px;border-radius:4px;font-size:12px}}
.note{{color:var(--muted);font-size:12.5px;margin-top:10px}}
.foot{{color:var(--muted);font-size:12px;margin-top:32px}}
</style></head><body><div class="wrap">
<h1>Course Build &amp; Textbook Verification</h1>
<p class="sub">Luminfest Learning Harness · every course built through one pipeline and checked against a licence-cleared textbook where one exists</p>
<div class="banner">
  <b>{len(rows)} courses · {total_concepts:,} concepts · {total_sections} verified textbook sections</b>
  <div class="grid">
    <div class="cell"><div class="k">Courses</div><div class="v">{len(rows)}</div></div>
    <div class="cell"><div class="k">Concepts</div><div class="v">{total_concepts:,}</div></div>
    <div class="cell"><div class="k">Textbook sections fetched</div><div class="v">{total_sections}</div></div>
    <div class="cell"><div class="k">Failed checks</div><div class="v" style="color:{'#b42318' if all_fail else '#0a7a3d'}">{len(all_fail)}</div></div>
  </div>
</div>

<h2>Every course</h2>
<table><thead><tr><th>Course</th><th>Units</th><th>Topics</th><th>Concepts</th>
<th>Textbook spine</th><th>Sections</th><th>Verification</th></tr></thead>
<tbody>{''.join(table_rows)}</tbody></table>
<p class="note">A section counts only if the verifier re-fetched it through the licence
gate and OpenStax's live API still reported CC BY for that book. “SKIP” on a course with zero
sections is the declared no-anchor path, not a pass it did not earn.</p>

<h2>Courses with no CC BY textbook — declared, not faked</h2>
<table><thead><tr><th>Course</th><th>Spine</th><th>Declared reason</th></tr></thead>
<tbody>{''.join(gap_rows) or '<tr><td colspan="3">none</td></tr>'}</tbody></table>
<p class="note">OpenStax's calculus volumes, organic chemistry and writing guide are
CC BY-NC-SA: link-only, never quoted. Earth Science and Linear Algebra have no OpenStax book
at all. Those courses state the absence in the pack metadata and the verifier reports it as
SKIP with the reason rather than borrowing an unrelated title.</p>

<h2>How each course was built</h2>
<pre style="background:#f6f7f9;border:1px solid var(--line);border-radius:6px;padding:12px;font-size:12px;overflow:auto">python scripts/course_pipeline.py build  --course &lt;id&gt;
python scripts/course_pipeline.py verify --course &lt;id&gt;   # live licence gate on every section
python scripts/course_build_report.py                      # this page</pre>
<p class="note">Outline data lives in <code>scripts/outlines/&lt;id&gt;.py</code>. Concept ids are
namespaced with the course id; prerequisites are authored within a topic and bridged once per
unit so the graph branches instead of chaining. Generated lesson and practice items are
materialised by <code>app/generated_curriculum.py</code>.</p>

<p class="foot">Generated {esc(time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))} from
{len(rows)} verification reports. The model is not involved in this page: it is the reports.</p>
</div></body></html>"""

    (OUT / 'course_build_report.html').write_text(html_doc, encoding='utf-8')
    summary = {
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'courses': [
            {'course': r['course'], 'summary': r['summary'],
             'structure': r.get('structure'), 'textbook': r.get('textbook')}
            for r in rows
        ],
        'totals': {'courses': len(rows), 'concepts': total_concepts,
                   'sections': total_sections, 'failed_courses': len(all_fail),
                   'courses_without_anchor': len(no_anchor)},
    }
    (OUT / 'course_build_report.json').write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')

    print(f'{len(rows)} courses, {total_concepts} concepts, {total_sections} sections, '
          f'{len(all_fail)} failed')
    for r in rows:
        print(f"  {r['course']:22s} {status(r)[1]}")
    print('HTML : ' + str(OUT / 'course_build_report.html'))
    return 1 if all_fail else 0


if __name__ == '__main__':
    raise SystemExit(main())
