#!/usr/bin/env python3
"""Teacher capability probe: drive the agent loop as a teacher and report
which of the six harness surfaces actually produce artefacts.

Each probe is one agent turn with a narrow instruction, so the result reflects
what the *harness* can do, not what I can author by hand.
"""
import json
import sys
import urllib.request

BASE = 'http://127.0.0.1:8766'
CONCEPT = 'permutations_and_combinations'


def login(email, password):
    req = urllib.request.Request(
        BASE + '/api/v1/auth/login',
        data=json.dumps({'email': email, 'password': password}).encode(),
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)['token']


def chat(token, message, context=None, speak=False, interrupted=False, timeout=900):
    body = {'message': message, 'developer_mode': True, 'speak': speak,
            'interrupted': interrupted}
    if context:
        body['context'] = context
    req = urllib.request.Request(
        BASE + '/api/v1/agent/chat', data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json',
                 'Authorization': 'Bearer ' + token})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def summarise(label, d):
    print(f'\n===== {label} =====')
    reply = str(d.get('reply') or d.get('message') or '')
    print('reply  :', reply[:400].replace('\n', ' '))
    evs = d.get('events', [])
    names = []
    for e in evs:
        t = e.get('type') or e.get('event') or ''
        n = e.get('name') or e.get('tool') or ''
        if n:
            names.append(n)
    print('tools  :', names)
    for key in ('artifacts', 'figures', 'media', 'speech', 'notice', 'error',
                'whiteboard', 'board', 'simulation', 'deck', 'slides'):
        if key in d and d[key]:
            print(f'{key:11}:', json.dumps(d[key])[:500])
    return d


if __name__ == '__main__':
    token = login('tengyi@luminfest.local', 'Luminfest-2026!')
    which = sys.argv[1] if len(sys.argv) > 1 else 'figure'

    if which == 'figure':
        d = chat(token,
                 'Use build_figure to make a diagram that contrasts permutations '
                 'and combinations for this concept. Report what the figure shows.',
                 {'concept_id': CONCEPT})
        summarise('build_figure (diagram)', d)

    elif which == 'video':
        d = chat(token,
                 'Use find_video to locate a teaching video about permutations and '
                 'combinations for this concept. Report the title and link.',
                 {'concept_id': CONCEPT})
        summarise('find_video (video)', d)

    elif which == 'sim':
        d = chat(token,
                 'Use write_simulation to build an interactive simulation that lets a '
                 'learner explore permutations and combinations for this concept.',
                 {'concept_id': CONCEPT})
        summarise('write_simulation (simulation)', d)

    elif which == 'ppt':
        d = chat(token,
                 'Use build_presentation to build a short slide deck introducing '
                 'permutations and combinations for this concept.',
                 {'concept_id': CONCEPT})
        summarise('build_presentation (PPT)', d)

    elif which == 'board':
        d = chat(token,
                 'Use whiteboard_write to draw a worked example of counting '
                 'permutations of 3 items from 5 on the whiteboard, then use '
                 'whiteboard_read to confirm what is on it.',
                 {'concept_id': CONCEPT})
        summarise('whiteboard (draw + read)', d)

    elif which == 'quiz':
        d = chat(token,
                 'Use check_understanding to ask me one diagnostic question about '
                 'permutations versus combinations.',
                 {'concept_id': CONCEPT})
        summarise('check_understanding (quiz)', d)

    elif which == 'tts':
        d = chat(token,
                 'Teach me in one short spoken paragraph what a permutation is. '
                 'Keep it to three sentences, written to be heard.',
                 {'concept_id': CONCEPT}, speak=True, timeout=240)
        summarise('text_to_speech / speak=True', d)

    elif which == 'interrupt':
        d = chat(token,
                 'Wait - why does order matter here but not for combinations?',
                 {'concept_id': CONCEPT}, speak=True, interrupted=True, timeout=240)
        summarise('interrupted turn', d)

    elif which == 'browser':
        d = chat(token,
                 'Use browser_snapshot to capture a reference page about the '
                 'permutation formula for teacher review.',
                 {'concept_id': CONCEPT})
        summarise('browser_snapshot (browser)', d)

    elif which == 'textbook':
        d = chat(token,
                 'Use read_concept to read the lesson block for this concept and '
                 'summarise what the textbook says about permutations.',
                 {'concept_id': CONCEPT})
        summarise('read_concept (textbook)', d)

    elif which == 'draft':
        d = chat(token,
                 'Use draft_course to author a complete new course on the topic '
                 '"combinations and permutations" at the high-school level, with 2 units. '
                 'Report the course id, how many concepts it produced, and whether the '
                 'audit passed.',
                 {}, timeout=1500)
        summarise('draft_course (authoring)', d)

    elif which == 'ta':
        d = chat(token,
                 'Dispatch the TA to prepare teaching assets for this concept: ask it to '
                 'build a figure contrasting permutations and combinations, and to find a '
                 'curated video. Report what the TA returned.',
                 {'concept_id': CONCEPT}, timeout=900)
        summarise('TA dispatch', d)
