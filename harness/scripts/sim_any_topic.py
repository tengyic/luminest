#!/usr/bin/env python3
"""Ask the harness to build simulations on unrelated subjects, then check they run.

The claim under test is "it can generate on any topic". One working permutation explorer
proves the permutation case; it says nothing about a canvas interference bench or a
supply-and-demand plane. Each topic here goes through the same path a teacher's tool call
takes -- creation gate, model, structural validation, storage -- and is then loaded in a
real browser, driven, and checked for console errors and non-empty output.

Usage: sim_any_topic.py [name ...]
"""
import json
import sys
import traceback
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / 'backend'
sys.path.insert(0, str(BACKEND))

from app.config import Settings                     # noqa: E402
from app import courses                             # noqa: E402
from app.harness import sims_store, toolbox         # noqa: E402

OUT = Path('/tmp/sim_topics')

TOPICS = {
    'physics': ('Wave Interference Bench',
                'Two draggable point sources on a canvas. Draw the interference pattern '
                'with adjustable wavelength, amplitude and source separation, show a '
                'vertical intensity cross-section beside it, and let the learner move a '
                'probe to read the path difference at that point.'),
    'economics': ('Supply and Demand Shock Lab',
                  'A price/quantity plane with supply and demand curves and a movable '
                  'equilibrium marker. Buttons apply a demand shock, a supply shock and a '
                  'binding price ceiling; the curves animate to the new equilibrium and a '
                  'readout explains the resulting surplus or shortage in words.'),
    'biology': ('Action Potential Scope',
                'An axon membrane model driven by Na+ and K+ conductance. Sliders set '
                'stimulus strength and extracellular Na+ concentration; a trace shows '
                'membrane potential over time with threshold, depolarisation, repolarisation '
                'and refractory period marked.'),
    'humanities': ('Argument Fallacy Spotter',
                   'A short passage with three claims; the learner clicks the sentence that '
                   'commits a named fallacy. Show the fallacy name and a one-line reason for '
                   'each choice, track attempts, and reveal the answer only after a click.'),
}


class Principal:
    def __init__(self, role='teacher'):
        self.id = 'probe-teacher'
        self.role = role
        self.email = 'tengyi@luminfest.local'


def context(settings):
    concept = 'permutations_and_combinations'
    graph = courses.graph_for_node(concept)
    spec = courses.course_for_node(concept)
    return toolbox.ToolContext(db=None, user=Principal(), settings=settings, graph=graph,
                               subject_kind=getattr(spec, 'subject_kind', 'mathematics'),
                               course_id=getattr(spec, 'id', 'integrated_math_1'))


def render(path: Path, shot: Path):
    """Load in Chromium, drive a control and the primary button, report console errors.

    Both matter: a slider-only probe leaves a "press Stimulate to fire" simulation looking
    empty, and a button-only probe misses a broken slider. The first button that is not
    a reset is the primary action in every artefact generated so far.
    """
    from playwright.sync_api import sync_playwright
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1280, 'height': 860})
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
        page.goto(path.as_uri())
        page.wait_for_timeout(800)
        page.evaluate("""() => {
            const el = document.querySelector('input[type=range]');
            if (!el) return;
            el.value = el.max || '5';
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
        }""")
        page.wait_for_timeout(300)
        clicked = page.evaluate("""() => {
            const btn = Array.from(document.querySelectorAll('button'))
                .find(b => !/reset|clear/i.test(b.textContent || ''));
            if (!btn) return null;
            btn.click();
            return (btn.textContent || '').trim();
        }""")
        page.wait_for_timeout(900)
        page.screenshot(path=str(shot))
        chars = len(page.inner_text('body').strip())
        browser.close()
    print(f'    clicked: {clicked!r}')
    return errors, chars


def main():
    wanted = sys.argv[1:] or list(TOPICS)
    settings = Settings.from_env()
    ctx = context(settings)
    if not OUT.exists():
        OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for name in wanted:
        title, spec = TOPICS[name]
        print(f'\n=== {name}: {title}')
        try:
            result = toolbox.invoke(ctx, 'write_simulation', {'title': title,
                                                              'description': spec})
        except Exception:                                  # noqa: BLE001 - report, keep going
            traceback.print_exc()
            rows.append((name, 'EXCEPTION', 0, 0, 'n/a'))
            continue
        if not result.ok:
            print(f'    refused: {result.refused or result.error}')
            print(f'    data   : {json.dumps(result.data, indent=2)[:900]}')
            rows.append((name, 'refused', 0, 0, (result.refused or result.error)[:60]))
            continue
        data = result.data
        html = sims_store.read_version(settings, data['artifact_id'])
        path = OUT / f'{name}.html'
        path.write_text(html, encoding='utf-8')
        errors, chars = render(path, OUT / f'{name}.png')
        print(f'    ok  bytes={data["bytes"]}  body_chars={chars}  console_errors={errors or "none"}')
        rows.append((name, 'ok', data['bytes'], chars, errors or 'none'))
    print('\n--- summary')
    for name, status, size, chars, note in rows:
        print(f'{name:12s} {status:10s} {size:>7} bytes  {chars:>6} body chars  {note}')
    return 0 if all(r[1] == 'ok' for r in rows) else 1


if __name__ == '__main__':
    sys.exit(main())
