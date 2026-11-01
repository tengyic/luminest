"""Render every bundled playground game to a JSON bundle for the behavioural verifier.

`playground_verify.mjs` deliberately knows nothing about the playground: it takes a list
of `{slug, archetype, scored, html}` and drives whatever handlers the page registered.
This script is the other half - it imports the real catalogue, renders each game through
the real pipeline, and writes that list out.

Keeping the two apart is what makes the verifier trustworthy: it cannot be tempted to
special-case a game it helped render.

    python scripts/playground_render_pages.py /tmp/pages.json
    node scripts/playground_verify.mjs /tmp/pages.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.harness.playground import catalogue  # noqa: E402
from app.harness.playground.archetypes import get as get_archetype  # noqa: E402
from app.harness.playground.pipeline import page_args, render_game  # noqa: E402


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/playground_pages.json')
    games = catalogue.all_games()
    pages = []
    for game in games:
        spec = game['spec']
        archetype = get_archetype(game['archetype'])
        if archetype is None:
            pages.append({'slug': game['slug'], 'archetype': game['archetype'],
                          'scored': True, 'commits_on': 'check', 'html': '',
                          'render_error': 'archetype is not registered'})
            continue
        # `scored` and `commits_on` are properties of the archetype, not of the content.
        # Reading them off the spec would silently default every game to scored-on-check.
        scored, commits_on = archetype.scored, archetype.commits_on
        try:
            # Render through the *production* entry point with the *production*
            # arguments (`page_args`), not through `render()` with only the spec.
            # `render()` falls back to the archetype's first subject for the eyebrow and
            # to the spec's instruction for the header, so three shared archetypes were
            # labelled MATHEMATICS and several pages printed the same sentence twice -
            # in the artifacts, while the app itself was correct. The audit has to see
            # the page a learner plays or it is measuring the wrong thing.
            html = render_game(archetype_id=game['archetype'], spec=spec,
                               **page_args(game, archetype))
        except Exception as exc:  # a render failure is itself a finding
            pages.append({'slug': game['slug'], 'archetype': game['archetype'],
                          'scored': scored, 'commits_on': commits_on, 'html': '',
                          'render_error': f'{type(exc).__name__}: {exc}'})
            continue
        pages.append({'slug': game['slug'], 'archetype': game['archetype'],
                      'scored': scored, 'commits_on': commits_on, 'html': html})
    out.write_text(json.dumps(pages), encoding='utf-8')
    withheld = catalogue.withheld()
    print(f'rendered {len(pages)} pages -> {out}')
    print(f'withheld {len(withheld)}')
    for problem in withheld:
        print('  WITHHELD', problem)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
