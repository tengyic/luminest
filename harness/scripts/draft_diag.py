#!/usr/bin/env python3
"""Diagnose why draft_course refuses: run the skeleton pass by hand and print
exactly what the model returned and why the validator rejected it."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

from app.config import Settings
from app.harness.authoring import blueprint, draft, methodology


def main():
    settings = Settings.from_env()
    profile = methodology.profile('default', {})
    units = 3
    bounded = max(profile.shape.min_units,
                  min(units, profile.shape.max_units, draft.MAX_UNITS))
    ceiling = draft.skeleton_tokens(profile, bounded)

    system = draft._skeleton_system(profile, bounded)
    user = 'Design the course outline for: combinations and permutations\nLevel: high school.'
    messages = [{'role': 'system', 'content': system},
                {'role': 'user', 'content': user}]

    print('bounded units:', bounded, '| skeleton ceiling:', ceiling)
    print('=== SYSTEM PROMPT (first 1800 chars) ===')
    print(system[:1800])
    print()

    for attempt in range(1, 4):
        print(f'=== ATTEMPT {attempt} ===')
        raw = draft._ask(settings, messages, max_tokens=ceiling,
                         usage_out={})
        print('raw type:', type(raw))
        text = raw if isinstance(raw, str) else json.dumps(raw)[:200]
        print('raw (first 1200):', str(text)[:1200])
        print()

        payload = draft._as_object(raw)
        print('parsed as object:', type(payload).__name__ if payload is not None else None)
        if payload is None:
            messages.append({'role': 'user', 'content':
                             'That was not a JSON object. Reply with the JSON object only.'})
            continue

        candidate, problems = blueprint.parse(payload, author='model')
        blocking = blueprint.blocking(problems)
        print('candidate is None:', candidate is None)
        print('problems:', len(problems), '| blocking:', len(blocking))
        for p in (blocking or problems)[:10]:
            print('   -', str(p)[:220])
        if candidate is not None and not blocking:
            print('>>> SKELETON ACCEPTED')
            print('units:', len(candidate.units))
            for u in candidate.units:
                print(f'   {u.id}: {u.title} ({len(u.concepts)} concepts)')
            return
        messages.append({'role': 'assistant',
                         'content': json.dumps(payload, ensure_ascii=False)[:8000]})
        messages.append({'role': 'user', 'content': draft._feedback(
            blocking or problems or [blueprint.Problem('empty', 'units', 'no units found')])})
        print()

    print('>>> ALL ATTEMPTS REFUSED')


if __name__ == '__main__':
    main()
