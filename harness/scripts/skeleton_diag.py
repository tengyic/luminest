#!/usr/bin/env python3
"""Capture the blocking problems that make the skeleton pass refuse.

Runs the outline pass repeatedly for one topic and prints, for each attempt, the
blocking findings the validator returned. This is the evidence needed to decide
whether to relax a rule, strengthen the prompt, or raise the attempt count.
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

from app.config import Settings
from app.harness import provider
from app.harness.authoring import blueprint, draft, methodology


def one(settings, topic, profile, bounded, ceiling, rounds=6):
    system = draft._skeleton_system(profile, bounded)
    messages = [{'role': 'system', 'content': system},
                {'role': 'user', 'content': f'Design the course outline for: {topic}\n'
                                            f'Level: high school.'}]
    codes = Counter()
    accepted = 0
    for r in range(rounds):
        raw = draft._ask(settings, messages, max_tokens=ceiling, usage_out={})
        payload = draft._as_object(raw)
        if payload is None:
            print(f'  round {r}: no JSON object (raw len {len(raw or "")})')
            codes['no_json'] += 1
            messages.append({'role': 'user', 'content':
                             'That was not a JSON object. Reply with the JSON object only.'})
            continue
        candidate, problems = blueprint.parse(payload, author='model')
        blocking = blueprint.blocking(problems)
        if candidate is not None and not blocking:
            accepted += 1
            print(f'  round {r}: ACCEPTED ({len(candidate.units)} units, '
                  f'{len(candidate.concepts())} concepts)')
            return accepted, codes
        print(f'  round {r}: {len(blocking)} blocking')
        for p in blocking[:6]:
            codes[p.code] += 1
            print(f'      {p.code:24} {p.path}: {p.message[:90]}')
        messages.append({'role': 'assistant',
                         'content': json.dumps(payload, ensure_ascii=False)[:8000]})
        messages.append({'role': 'user', 'content': draft._feedback(
            blocking or problems)})
    return accepted, codes


def main():
    settings = Settings.from_env()
    profile = methodology.profile('default', {})
    bounded = max(profile.shape.min_units, min(3, profile.shape.max_units, draft.MAX_UNITS))
    ceiling = draft.skeleton_tokens(profile, bounded)
    topic = sys.argv[1] if len(sys.argv) > 1 else 'combinations and permutations'
    print(f'topic: {topic} | bounded units: {bounded} | ceiling: {ceiling}')
    accepted, codes = one(settings, topic, profile, bounded, ceiling)
    print()
    print('blocking codes seen:', dict(codes))


if __name__ == '__main__':
    main()
