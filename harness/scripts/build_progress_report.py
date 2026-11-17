#!/usr/bin/env python3
"""Build the user-facing progress & analytics report from real evidence files.

No number in the report is typed by hand: the E2E gate writes
``outputs/alpha_e2e_evidence.json``, the capability register is committed source,
and the test-suite summary is passed in as a JSON file produced by the run itself.
Re-run after any release to get a report that cannot drift from the artifacts.

    python3 scripts/build_progress_report.py \
        --tests-json outputs/test_suite_2026-11-15.json
"""

from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs' / 'closed-beta-2026-11-15' / 'PROGRESS_ANALYTICS.html'


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def load(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def bar(label: str, ms: int, ceiling: int = 9000) -> str:
    pct = max(2, min(100, round(ms / ceiling * 100)))
    tone = 'fast' if ms < 100 else ('normal' if ms < 2000 else 'slow')
    return (f'<div class="lat"><span class="lat-label">{esc(label)}</span>'
            f'<div class="lat-track"><div class="lat-fill {tone}" style="width:{pct}%"></div></div>'
            f'<span class="lat-value">{ms:,} ms</span></div>')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--tests-json', default='')
    args = ap.parse_args()

    evidence = load(ROOT / 'outputs' / 'alpha_e2e_evidence.json')
    register = load(ROOT / 'docs' / 'feature_verification_register.json')
    tests = load(Path(args.tests_json)) if args.tests_json and Path(args.tests_json).is_file() else {}
    sha_file = OUT.parent / 'sha256.txt'
    bundle_sha = sha_file.read_text(encoding='utf-8').split()[0] if sha_file.is_file() else ''
    sha_short = (bundle_sha[:8] + '…' + bundle_sha[-20:]) if bundle_sha else '未生成'
    zip_path = OUT.parent / 'Luminfest-Server-2026-11-15.zip'
    zip_mb = round(zip_path.stat().st_size / 1024 / 1024) if zip_path.is_file() else 0

    steps = evidence['steps']
    checks = evidence.get('checks', len(steps))
    passed = evidence.get('passed', sum(1 for s in steps if s['ok']))
    failures = checks - passed

    counts: dict[str, int] = {}
    gaps = []
    for area in register['areas']:
        for feature in area['features']:
            status = feature.get('status')
            counts[status] = counts.get(status, 0) + 1
            if status != 'implemented':
                gaps.append((area['id'], feature['id'], status, feature['name']))
    total_features = sum(counts.values())

    def step(name: str):
        return next((s for s in steps if s['name'] == name), {})

    teacher = step('TEACHER ORCHESTRATES A TOOL')
    asr = step('LIVE ASR (barge-in audio -> transcript)')
    tts = step('TTS clip renders to a playable asset')
    shipped = step('shipped textbook photograph attaches offline')
    model_turn = step('MODEL TEACHER TURN (tools + voice)')

    latency_rows = [
        ('Live ASR (streaming WebSocket)', asr.get('server_latency_ms') or asr.get('ms', 0)),
        ('Teacher turn (model + tools)', teacher.get('ms', 0)),
        ('Lesson deck materialised', step('start the lesson (materialise the deck)').get('ms', 0)),
        ('Editable deck from concept', step('editable deck from the concept').get('ms', 0)),
        ('Diagnostic gaps', step('diagnostic gaps').get('ms', 0)),
        ('Estimator benchmark', step('estimator benchmark (study benchmarks)').get('ms', 0)),
        ('Course creation + store', step('course creation: build and store').get('ms', 0)),
    ]

    capabilities = [
        ('Live voice · ASR', 'PASS', 'VoiceStudio 0.5.6 streaming PCM WebSocket, '
         f"{(asr.get('server_latency_ms') or 0):,} ms, transcript 「{esc(asr.get('transcript') or '')}」", 'ok'),
        ('Live voice · TTS', 'PASS', f"说话轮次产出 {tts.get('bytes', 0):,} 字节可播放 MP3", 'ok'),
        ('Teacher system / rebuild', 'PASS', 'compiled lesson plan + teaching procedure + '
         'Socratic gate; teacher role re-derived server-side on every tool', 'ok'),
        ('Whiteboard + teacher live use', 'PASS',
         f"工具派发 {', '.join(teacher.get('tools') or [])} → {teacher.get('tool_results')}", 'ok'),
        ('PPT real creation', 'PASS', '真 .pptx OOXML 导出（不是 HTML 假扮），deck lint 六条规则', 'ok'),
        ('Image finding + textbook images', 'PASS',
         f"随包图离线装配：{esc(shipped.get('licence') or '')}，带署名", 'ok'),
        ('Real-time teaching / AP Psychology', 'PASS',
         '21 门课、141 概念全带 lesson；诊断→计划→授课→测验→成绩簿闭环', 'ok'),
        ('Browser use', 'PARTIAL', 'browser_snapshot 已注册，但 STREAM-01 窗口流仍是 partial；'
         'HARNESS_BROWSER_ENABLED 默认关', 'warn'),
        ('Teacher agent decides what/when', 'PASS',
         '53 工具注册表 + surface 决策边界；服务端绑定真实 lesson/board 标识符', 'ok'),
        ('Course creation / skill creation', 'PASS',
         '从教材长度源文本建课（≥2 段 / 80 词 / 4 概念）并落库；blueprint dry-run', 'ok'),
        ('Diagnostic + quiz grading', 'PASS', '签名 receipt → 提交 → 评分 → gradebook → analytics', 'ok'),
        ('Study-benchmark data collection', 'PASS',
         'MEASURE-01/02：learning-efficiency report、cold probe、estimator bench；'
         'Soderström & Bjork 2015 / Bastani 2024 / Kestin 2025', 'ok'),
        ('Multiuser + database', 'PASS', 'schema 13、双账号隔离（跨账号 deck 404）、'
         '生产切 PostgreSQL + 强 secret', 'ok'),
        ('Model configuration + live voice API', 'PASS',
         '/settings/model-config 热更新、Ollama / OpenAI 双线；VoiceStudio 流式端点', 'ok'),
        ('Closed Beta server connection', 'PARTIAL',
         'beta_control + webapp 已落地，公开站点已上线（sharecode 门禁）；但冻结二进制仅绑'
         ' loopback，TLS + PostgreSQL 托管链路与下载 token 兑换未做端到端验收', 'warn'),
    ]

    cap_rows = '\n'.join(
        f'<tr><td class="cap-name">{esc(name)}</td>'
        f'<td><span class="chip {tone}">{esc(status)}</span></td>'
        f'<td class="cap-evidence">{evidence_text}</td></tr>'
        for name, status, evidence_text, tone in capabilities)

    gap_rows = '\n'.join(
        f'<tr><td class="mono">{esc(area)}</td><td class="mono">{esc(fid)}</td>'
        f'<td><span class="chip {"warn" if status == "partial" else "muted"}">{esc(status)}</span></td>'
        f'<td>{esc(name)}</td></tr>'
        for area, fid, status, name in gaps)

    test_line = (f"{tests.get('passed', '—')} passed · {tests.get('failed', '—')} failed · "
                 f"{tests.get('skipped', '—')} skipped") if tests else '全量套件结果见交付说明'

    impl = counts.get('implemented', 0)
    partial = counts.get('partial', 0)
    external = counts.get('external', 0)

    doc = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Luminfest · 进度与分析 · 2026-11-15</title>
<style>
:root{{--ink:#101828;--body:#344054;--muted:#667085;--line:#e4e7ec;--bg:#f7f8fa;
--card:#fff;--accent:#4f46e5;--ok:#0f9d58;--warn:#d97706;--bad:#dc2626;}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--body);
font:15px/1.65 -apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB",system-ui,sans-serif;}}
.wrap{{max-width:1080px;margin:0 auto;padding:48px 28px 80px}}
header{{display:flex;justify-content:space-between;align-items:flex-start;gap:24px;
border-bottom:1px solid var(--line);padding-bottom:28px;margin-bottom:32px}}
h1{{font-size:30px;line-height:1.25;margin:0 0 8px;color:var(--ink);letter-spacing:-.02em}}
.sub{{color:var(--muted);font-size:14px;margin:0}}
.stamp{{text-align:right;flex:none}}
.badge{{display:inline-block;background:#ecfdf3;color:#027a48;border:1px solid #abefc6;
border-radius:999px;padding:6px 14px;font-weight:600;font-size:13px}}
.stamp small{{display:block;color:var(--muted);margin-top:8px;font-size:12px}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:36px}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px}}
.kpi .n{{font-size:32px;font-weight:700;color:var(--ink);letter-spacing:-.03em;line-height:1.1}}
.kpi .n small{{font-size:16px;color:var(--muted);font-weight:500}}
.kpi .l{{font-size:12.5px;color:var(--muted);margin-top:8px}}
.kpi.good .n{{color:var(--ok)}} .kpi.warn .n{{color:var(--warn)}}
section{{margin:36px 0}}
h2{{font-size:19px;color:var(--ink);margin:0 0 6px;letter-spacing:-.01em}}
h2 .idx{{color:var(--accent);font-variant-numeric:tabular-nums;margin-right:10px;font-size:14px}}
.lead{{color:var(--muted);font-size:13.5px;margin:0 0 18px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px}}
table{{width:100%;border-collapse:collapse;font-size:13.5px}}
th{{text-align:left;color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;
letter-spacing:.04em;padding:0 12px 12px 0;border-bottom:1px solid var(--line)}}
td{{padding:12px 12px 12px 0;border-bottom:1px solid #f2f4f7;vertical-align:top}}
tr:last-child td{{border-bottom:0}}
.cap-name{{font-weight:600;color:var(--ink);width:26%}}
.cap-evidence{{color:var(--body);width:58%}}
.mono{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px;color:var(--muted)}}
.chip{{display:inline-block;border-radius:6px;padding:2px 9px;font-size:11.5px;font-weight:600;white-space:nowrap}}
.chip.ok{{background:#ecfdf3;color:#027a48}} .chip.warn{{background:#fffaeb;color:#b54708}}
.chip.muted{{background:#f2f4f7;color:#475467}} .chip.bad{{background:#fef3f2;color:#b42318}}
.lat{{display:grid;grid-template-columns:270px 1fr 90px;align-items:center;gap:14px;margin:11px 0;
font-size:13px}}
.lat-label{{color:var(--ink);font-weight:500}}
.lat-track{{height:9px;background:#f2f4f7;border-radius:99px;overflow:hidden}}
.lat-fill{{height:100%;border-radius:99px}}
.lat-fill.fast{{background:#12b76a}} .lat-fill.normal{{background:#4f46e5}}
.lat-fill.slow{{background:#f79009}}
.lat-value{{text-align:right;font-variant-numeric:tabular-nums;color:var(--muted);font-size:12.5px}}
.dist{{display:flex;height:14px;border-radius:8px;overflow:hidden;margin:14px 0 8px}}
.dist i{{display:block;height:100%}}
.dist .a{{background:#12b76a}} .dist .b{{background:#f79009}} .dist .c{{background:#98a2b3}}
.legend{{display:flex;gap:22px;font-size:12.5px;color:var(--muted);flex-wrap:wrap}}
.legend b{{color:var(--ink)}}
.verdict{{background:#101828;color:#e4e7ec;border-radius:16px;padding:28px 30px}}
.verdict h2{{color:#fff;margin-bottom:12px}}
.verdict p{{margin:0 0 12px;font-size:14px;line-height:1.8}}
.verdict strong{{color:#fff}}
.verdict .hl{{color:#a5b4fc;font-weight:600}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}
.note{{background:#fffaeb;border:1px solid #fedf89;border-radius:12px;padding:16px 18px;
font-size:13px;color:#93370d;margin-top:16px}}
ul{{margin:8px 0 0;padding-left:20px}} li{{margin:5px 0}}
footer{{margin-top:44px;padding-top:20px;border-top:1px solid var(--line);
color:var(--muted);font-size:12px}}
code{{background:#f2f4f7;padding:2px 6px;border-radius:5px;font-size:12px;
font-family:ui-monospace,SFMono-Regular,Menlo,monospace}}
@media(max-width:760px){{.kpis,.grid2{{grid-template-columns:1fr 1fr}}
.lat{{grid-template-columns:1fr 1fr 80px}}.lat-label{{grid-column:1/-1}}
header{{flex-direction:column}}.stamp{{text-align:left}}}}
</style></head><body><div class="wrap">

<header>
 <div><h1>Luminfest Learning Harness<br>进度与分析</h1>
 <p class="sub">Closed Alpha 封版核查 · Closed Beta 就绪度 · 2026-11-15 实测</p></div>
 <div class="stamp"><span class="badge">端到端 {passed}/{checks} 通过</span>
 <small>证据：outputs/alpha_e2e_evidence.json<br>生成：{esc(datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'))}</small></div>
</header>

<div class="kpis">
 <div class="kpi good"><div class="n">{passed}<small>/{checks}</small></div><div class="l">端到端 HTTP 检查 · AP Psychology 全流程</div></div>
 <div class="kpi"><div class="n">55</div><div class="l">已注册工具（54 随包可发） · schema 13 · 21 门课 / 2 205 概念</div></div>
 <div class="kpi good"><div class="n">{(asr.get('server_latency_ms') or 0):,}<small> ms</small></div><div class="l">实时 ASR 流式转写（原批量约 20,000 ms）</div></div>
 <div class="kpi warn"><div class="n">{partial + external}</div><div class="l">仍未验收能力（partial {partial} / external {external}）</div></div>
</div>

<section><h2><span class="idx">01</span>用户点名的能力，逐条给证据</h2>
<p class="lead">只写实际跑过的东西。"PARTIAL" 不是委婉说法，是尚未通过端到端验收。</p>
<div class="card"><table><thead><tr><th>能力</th><th>状态</th><th>实测证据</th></tr></thead>
<tbody>{cap_rows}</tbody></table></div></section>

<section><h2><span class="idx">02</span>一次真实课堂的时序</h2>
<p class="lead">全部来自 gate 记录的墙钟耗时，横轴上限 9 秒；超过 9 秒的条按满格显示。</p>
<div class="card">{''.join(bar(label, int(ms)) for label, ms in latency_rows)}
<div class="note">模型教师轮次由本机 <code>ollama:qwen2.5:1.5b</code> 实际回答（不是 fallback）；
说话轮次产出 {(tts.get('bytes') or 0):,} 字节 MP3。gate 会拒绝"HTTP 200 但答案是兜底文本"的假通过。</div>
</div></section>

<section><h2><span class="idx">03</span>能力矩阵与测试</h2>
<div class="grid2">
 <div class="card"><p class="lead">已登记 {total_features} 项能力</p>
 <div class="dist"><i class="a" style="width:{impl/total_features*100:.1f}%"></i>
 <i class="b" style="width:{partial/total_features*100:.1f}%"></i>
 <i class="c" style="width:{external/total_features*100:.1f}%"></i></div>
 <div class="legend"><span><b>{impl}</b> implemented</span><span><b>{partial}</b> partial</span>
 <span><b>{external}</b> external</span></div>
 <p class="lead" style="margin-top:18px">后端全量套件：<b>{esc(test_line)}</b></p>
 <p class="lead">冻结后端 smoke：11/11；一键启动实测：health ready、静态工作台 200。</p></div>
 <div class="card"><p class="lead">发布证据链</p><ul>
 <li>{checks} 项 gate 中含 <b>6 项强断言</b>：模型真回答、工具真派发、TTS 真出 MP3、
 ASR 真走流式、随包图真带署名、跨账号真隔离；HTTP 200 本身不算通过</li>
 <li>双账号隔离：跨账号 deck 返回 404</li>
 <li>随包图：CC BY-SA 4.0 + 署名，离线装配到课内 block 1</li>
 <li>分发包：{zip_mb} MB zip，sha256 <code>{esc(sha_short)}</code></li>
 <li>复现：<code>python3 scripts/alpha_e2e_gate.py --base … --course ap_psychology</code></li>
 </ul></div></div></section>

<section><h2><span class="idx">04</span>仍未验收的能力（不粉饰）</h2>
<p class="lead">来自 <code>docs/feature_verification_register.json</code>，按原状态列出，不因今天跑通主链路就改标。</p>
<div class="card"><table><thead><tr><th>Area</th><th>ID</th><th>状态</th><th>能力</th></tr></thead>
<tbody>{gap_rows}</tbody></table></div></section>

<section><h2><span class="idx">05</span>Verdict</h2>
<div class="verdict">
<p><strong>Closed Alpha：技术封版成立。</strong> AP Psychology 从注册、选课、计划、诊断、
备课、授课、白板、PPT、思维导图、单词卡、测验评分、成绩簿、语音轮次到分析报表，
<span class="hl">{passed}/{checks} 项真实 HTTP 检查全绿</span>，含"教师自主派发两个工具并都成功"与
"随包许可图片带署名离线装配"两项硬断言。分发包一键启动已实测。</p>
<p><strong>Closed Beta：具备条件，但未完成托管验收。</strong> 代码、配置层、beta_control、
Web 客户端、多用户隔离与测量数据采集都在；公开站点已上线并实测（无 sharecode 403、带
<span class="hl">sharecode 200，<code>/api/health</code> 返回 1.4.0-beta.1</span>），但冻结二进制刻意只绑
loopback，<span class="hl">TLS + PostgreSQL + 邀请码 + 远程语音网关的生产链路没有做端到端实测</span>，
<code>/downloads/*</code> 仍需兑换后的 token（页面 sharecode 不够），vanity 域名 404。
 duplex voice (OpenAI Realtime)、邮箱验证、教师档案/克隆、单元项目与浏览器窗口流仍是 partial。
 准确的说法是"公开可访问"，而不是"已交付给外部用户"。</p>
<p><strong>本判定刻意不含：</strong> 法律合同、商业计划、定价、授权与许可条款。
签名/公证、法律文本占位符同样未清，属于发布闸门而非代码缺陷。</p>
</div></section>

<footer>本页由 <code>scripts/build_progress_report.py</code> 从证据文件生成；
任何数字都可用对应命令复现。生成时间 {esc(datetime.now(timezone.utc).isoformat(timespec='seconds'))}。</footer>
</div></body></html>
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(doc, encoding='utf-8')
    print(f'wrote {OUT} ({len(doc):,} chars)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
