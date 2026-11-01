#!/usr/bin/env python3
"""Diagnose why write_simulation gets no complete HTML from the model.

Runs the exact prompt pair the tool builds, with the exact token ceiling, and reports
what came back: length, head, tail, whether the reply hit the ceiling, whether
extract_html found a document, and what the provider's own accounting said.
"""
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / 'backend'
sys.path.insert(0, str(BACKEND))

from app.config import Settings                       # noqa: E402
from app.harness import creation_gate, provider       # noqa: E402
from app.harness.tools_creation import (              # noqa: E402
    MAX_SIM_TOKENS, _SIM_CAPABILITY_RULES, extract_html)

TITLE = 'Permutation vs Combination Explorer'
SPEC = ('A grid of n objects from which the learner picks r. Two live counters show '
        'P(n,r) = n!/(n-r)! and C(n,r) = n!/(r!(n-r)!) and update as picks change.')

#: Heavier and non-mathematical specs, to find out whether one ceiling covers
#: every topic rather than the one it was tuned on.
PRESETS = {
    'light': (TITLE, SPEC),
    'heavy': ('Wave Interference Bench',
              'Two draggable point sources on a grid. Render the interference pattern '
              'with adjustable wavelength, amplitude and source separation; show a '
              'vertical intensity cross-section, mark nodes and antinodes, and let the '
              'learner toggle path-difference readout for a movable probe.'),
    'humanities': ('Supply and Demand Shock Lab',
                   'Draggable supply and demand curves on a price/quantity plane with a '
                   'movable equilibrium marker. Buttons apply a demand shock, a supply '
                   'shock and a price ceiling; the plot animates to the new equilibrium '
                   'and a readout explains the surplus or shortage in words.'),
}


def main():
    budget = int(sys.argv[1]) if len(sys.argv) > 1 else MAX_SIM_TOKENS
    preset = sys.argv[2] if len(sys.argv) > 2 else 'light'
    title, spec = PRESETS[preset]
    # Measure the artefact itself, not the guard: raise the reply ceiling for this run
    # so an oversized-but-complete document can be seen rather than discarded.
    provider.MAX_REPLY_CHARS = 400_000
    settings = Settings.from_env()
    print(f'provider   : {provider.label(settings)}')
    print(f'max_tokens : {budget}')
    print(f'MAX_REPLY_CHARS (provider) : {provider.MAX_REPLY_CHARS}')
    decision = creation_gate.evaluate({'role': 'teacher', 'category': 'create',
                                       'note': f'{title}. {spec}'})
    print(f'gate       : approved={decision["approved"]} requirement={decision["requirement"]!r}')
    system = creation_gate.SIM_AUTHORING_SYSTEM_PROMPT
    user = (f'Create a new interactive teaching simulation.\n'
            f'Title: {title}\n'
            f'Spec: {spec}\n'
            f'Hard requirements:\n' +
            '\n'.join(f'- {rule}' for rule in _SIM_CAPABILITY_RULES) +
            f'\n\nFiled requirement (binding): {decision["requirement"]}')
    print(f'user chars : {len(user)}')
    usage = {}
    started = time.monotonic()
    text = provider.chat(settings, [{'role': 'system', 'content': system},
                                    {'role': 'user', 'content': user}],
                         max_tokens=budget, usage_out=usage)
    elapsed = time.monotonic() - started
    print(f'elapsed    : {elapsed:.1f}s')
    print(f'usage      : {usage}')
    if text is None:
        print('RESULT     : provider.chat returned None (error/timeout/oversize)')
        return 1
    print(f'chars      : {len(text)}  (ceiling {provider.MAX_REPLY_CHARS})')
    print(f'head       : {text[:180]!r}')
    print(f'tail       : {text[-180:]!r}')
    html = extract_html(text)
    print(f'extract    : {len(html)} chars')
    if html:
        print(f'html head  : {html[:120]!r}')
        print(f'html tail  : {html[-120:]!r}')
    else:
        print('RESULT     : extract_html found no document')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
