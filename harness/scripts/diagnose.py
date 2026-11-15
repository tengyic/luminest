"""Write a diagnostics report a learner can actually read.

The data already exists: ``GET /api/v1/procedure/{concept}`` returns evidence beside the
plan. Nothing ever said it out loud, which is why the system could claim to measure mastery
while the learner had no idea where they stood.

This produces a self-contained HTML file with the numbers embedded, so it opens with no
server, no CORS and no token. It is deliberately read-only: it never starts a run, because
a report that changes the thing it reports is not a report.

    backend/.venv/bin/python -u scripts/diagnose.py
    backend/.venv/bin/python -u scripts/diagnose.py --concept algebra_2_permutations_and_combinations --course algebra_2

Wording rule, borrowed from the harness itself: report *evidence*, never a verdict. "3 of 4
attempts chose the unordered formula" is re-readable when the belief turns out wrong; "you
do not understand this" is not.
"""
from __future__ import annotations

import argparse
import html
import json
import secrets
import sys
import urllib.error
import urllib.request
from pathlib import Path


def call(base: str, path: str, payload=None, token: str | None = None,
         method: str | None = None, timeout: float = 60.0):
    url = base.rstrip('/') + path
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method or ('POST' if data else 'GET'))
    request.add_header('content-type', 'application/json')
    if token:
        request.add_header('authorization', 'Bearer ' + token)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b'{}')
    except urllib.error.HTTPError as error:
        body = error.read()
        try:
            return error.code, json.loads(body or b'{}')
        except ValueError:
            return error.code, {'detail': body.decode('utf-8', 'replace')[:300]}
    except (urllib.error.URLError, ConnectionError, TimeoutError) as error:
        return 0, {'detail': f'not reachable: {error}'}


def sentences(evidence: dict, plan: dict) -> list[str]:
    """The four things a learner is entitled to know, in plain language."""
    out: list[str] = []
    attempts = int(evidence.get('attempts') or 0)
    mastery = float(evidence.get('mastery') or 0.0)
    accuracy = evidence.get('recent_accuracy')
    if attempts == 0:
        out.append(
            f'目前没有作答记录。显示的 {mastery:.2f} 是先验值（表示"还不知道"），'
            f'不是对你能力的测量——它会在你做完第一组题之后被替换。')
    else:
        out.append(f'基于 {attempts} 次作答，掌握度估计为 {mastery:.2f}。')
        if accuracy is not None:
            out.append(f'最近的正确率是 {float(accuracy) * 100:.0f}%（不是总正确率，只看最近）。')
    top_error = str(evidence.get('top_error') or '').strip()
    if top_error:
        out.append(f'最常出现的错误类型是「{top_error}」——这比总正确率更能说明下一步该练什么。')
    if evidence.get('frustrated'):
        out.append('系统判断你上一次的状态是受挫。按设计，这不会扣分，只会改变这节课的节奏。')
    session = evidence.get('session_minutes')
    if session:
        out.append(f'你上一次在这门课上连续停留了 {float(session):.0f} 分钟。')
    skipped = plan.get('skipped') or []
    for block in plan.get('blocks') or []:
        quality = ((block.get('artifact') or {}).get('item_quality')) or {}
        if not quality:
            continue
        process = int(quality.get('error_process') or 0)
        topic = int(quality.get('topic_recognition') or 0)
        total = process + topic + int(quality.get('none') or 0)
        if total:
            out.append(
                f'这次检查的 {total} 道题里，{process} 道能区分"错误过程"，'
                f'{topic} 道只能区分主题。后者靠排除法就能答对，所以它的结果说明'
                f'"你认得这个主题"，而不是"你掌握了没有"。')
    if skipped:
        out.append(f'这节课主动放弃了 {len(skipped)} 个活动，每个都有理由——理由本身就是'
                   f'"为什么这节是这样"的答案，见下表。')
    return out


def render(concept: str, plan: dict, evidence: dict, deck: dict, notes: list[str]) -> str:
    blocks = plan.get('blocks') or []
    skipped = plan.get('skipped') or []
    minutes = plan.get('total_minutes') or plan.get('budget_minutes') or '?'

    rows = ''.join(
        f'<tr><td>{i + 1}</td><td><b>{html.escape(str(b.get("kind") or ""))}</b></td>'
        f'<td>{html.escape(str(b.get("title") or ""))[:90]}</td>'
        f'<td>{b.get("minutes")} 分钟</td></tr>'
        for i, b in enumerate(blocks))
    skip_rows = ''.join(
        f'<tr><td>{html.escape(str(s.get("kind") or ""))}</td>'
        f'<td>{html.escape(str(s.get("reason") or ""))[:220]}</td></tr>'
        for s in skipped)

    slides = deck.get('slides') or []
    pictures = []
    for slide in slides:
        for element in slide.get('elements') or []:
            if str(element.get('kind') or '') == 'image':
                pictures.append((slide.get('layout'), (element.get('image') or {})))

    cards = ''.join(f'<p>{html.escape(line)}</p>' for line in sentences(evidence, plan))
    pic_rows = ''.join(
        f'<tr><td>{html.escape(str(layout))}</td><td><code>{html.escape(str((img or {}).get("sha256") or ""))[:16]}</code></td>'
        f'<td>{html.escape(str((img or {}).get("attribution") or ""))[:80]}</td></tr>'
        for layout, img in pictures)
    note_items = ''.join(f'<li>{html.escape(n)}</li>' for n in notes)

    return f"""<!doctype html>
<html lang="zh"><meta charset="utf-8">
<title>诊断 · {html.escape(concept)}</title>
<style>
 body{{font:15px/1.65 -apple-system,BlinkMacSystemFont,"Helvetica Neue",sans-serif;
      color:#1c1c1e;background:#faf9f7;margin:0;padding:40px 24px}}
 main{{max-width:820px;margin:0 auto}}
 h1{{font-size:22px;font-weight:600;margin:0 0 4px}}
 .sub{{color:#6b6b70;font-size:13px;margin-bottom:28px}}
 h2{{font-size:14px;font-weight:600;margin:32px 0 10px;color:#3a3a3c}}
 .card{{background:#fff;border:1px solid #e6e4df;border-radius:12px;padding:18px 20px}}
 .card p{{margin:0 0 10px}} .card p:last-child{{margin:0}}
 table{{width:100%;border-collapse:collapse;font-size:13px;background:#fff;
        border:1px solid #e6e4df;border-radius:12px;overflow:hidden}}
 th{{text-align:left;font-weight:600;color:#6b6b70;padding:10px 12px;border-bottom:1px solid #e6e4df}}
 td{{padding:10px 12px;border-bottom:1px solid #f1efea;vertical-align:top}}
 tr:last-child td{{border-bottom:0}}
 code{{font:12px ui-monospace,SFMono-Regular,Menlo,monospace;color:#3a3a3c}}
 .empty{{color:#8e8e93;font-size:13px}}
 ul{{margin:0;padding-left:18px;font-size:13px;color:#3a3a3c}}
</style>
<main>
 <h1>{html.escape(concept)}</h1>
 <div class="sub">{len(blocks)} 个环节 · 约 {minutes} 分钟 · 教材 {len(slides)} 页 · 图 {len(pictures)} 张</div>

 <h2>你现在在哪</h2>
 <div class="card">{cards}</div>

 <h2>这节课怎么安排的</h2>
 <table><tr><th>#</th><th>类型</th><th>标题</th><th>时长</th></tr>{rows}</table>

 <h2>它放弃做了什么，以及为什么</h2>
 <table><tr><th>活动</th><th>理由</th></tr>{skip_rows or '<tr><td colspan=2 class=empty>没有跳过任何环节</td></tr>'}</table>

 <h2>教材里的图</h2>
 <table><tr><th>页</th><th>sha256</th><th>署名</th></tr>{pic_rows or '<tr><td colspan=3 class=empty>这份教材没有图</td></tr>'}</table>

 <h2>生成说明</h2>
 <ul>{note_items}</ul>
</main>
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://127.0.0.1:8877')
    parser.add_argument('--concept', default='biology_active_transport_against_a_gradient')
    parser.add_argument('--course', default='biology')
    parser.add_argument('--out', default='')
    parser.add_argument('--token', default='',
                        help='a bearer token for an existing learner; without it a fresh '
                             'account is created, and the report then honestly says that no '
                             'attempts exist yet')
    args = parser.parse_args()

    notes: list[str] = []
    status, health = call(args.base, '/health')
    if status != 200:
        print(f'the backend is not answering on {args.base}: {health}')
        return 2
    notes.append(f'后端 {args.base} · 模型状态 '
                 f'{(health.get("tutor") or {}).get("state")}')

    if args.token:
        token = args.token
        notes.append('使用你提供的 token 读取（报告反映这个账号的真实作答记录）')
    else:
        email = f'diagnose-{secrets.token_hex(4)}@report.test'
        status, body = call(args.base, '/api/v1/auth/register',
                            {'name': 'diagnose', 'email': email,
                             'password': 'long-secret-password'})
        if status != 201:
            print(f'registration failed: {status} {body}')
            return 2
        token = body['token']
        role = (body.get('user') or {}).get('role')
        notes.append(f'以新建的 {role} 身份读取：掌握度来自证据，所以这份报告首先告诉你'
                     f'"还没有证据"，而不是假装有')
    call(args.base, '/api/v1/me', {'course_id': args.course}, token, method='PATCH')

    status, preview = call(args.base, '/api/v1/procedure/' + args.concept, token=token)
    if status != 200:
        print(f'the plan did not compile: {status} {preview}')
        return 2
    plan = preview.get('plan') or {}
    evidence = preview.get('evidence') or {}
    notes.append(f'计划 hash {str(plan.get("hash") or "")[:12]}（同一份证据应得到同一个 hash）')

    status, deck = call(args.base, '/api/v1/deck/from-concept/' + args.concept,
                        token=token, timeout=180.0)
    if status != 200:
        print(f'deck: {status} {deck}')
        deck = {}

    out = Path(args.out) if args.out else Path('outputs') / 'diagnostics.html'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(args.concept, plan, evidence, deck, notes), encoding='utf-8')

    print(f'report: {out.resolve()}')
    for line in sentences(evidence, plan):
        print(' -', line)
    return 0


if __name__ == '__main__':
    sys.exit(main())
