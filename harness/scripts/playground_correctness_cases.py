"""Build a JSON bundle of correctness cases for `playground_correctness.mjs`.

The behavioural verifier (`playground_verify.mjs`) proves that a playground game commits
*honestly*. It cannot prove that a game is *right*, because it does not know the answer.
This script is the other half of the correctness oracle: for each archetype it derives a
concrete answer from the game's own **spec**, expresses the learner's route to committing
it as a list of concrete DOM actions, and writes those cases out. `playground_correctness.mjs`
then drives the rendered pages and asserts that the right answer is scored right and the
wrong answer is scored wrong.

Where an answer is a plain field of the spec the derivation is a lookup. Where it is not -
a balanced equation, an elasticity coefficient, a phenotype ratio, a sorting trace, the
observed proportion of a seeded simulation - it is **re-derived here, independently of the
archetype's own JavaScript**, from the same subject-matter model. That is the whole point:
an oracle that read the engine's private state would agree with the engine by construction
and would prove nothing.

Geometry-bound archetypes are reachable too, and are covered the same way: the engine's
own coordinate mapping is read out of the archetype source, and the pixel to drop on is
computed from the **spec's declared axis bounds** (or declared coordinates) through that
mapping - never by guessing, and never by reading the engine's private state. In the stub
DOM `getBoundingClientRect()` reports exactly the box the page's `#scene` declares in its
`viewBox`, so the runtime's `point()` and the engines' own `sp()` are the identity on
clientX/clientY whatever height the archetype declares: a computed viewBox coordinate is
the clientX to dispatch. (Before the stub honoured the viewBox it hard-coded 860x460, and
`point()` - which letterboxes by the *smaller* axis - rescaled and re-centred every drag
on the four archetypes that declare a taller canvas, so `number_line` and `plot_points`
failed the oracle while looking perfectly fine on screen.) Where a tray's contents are
dealt by the
runtime's seeded `shuffle`, that deal is reproduced here from the spec's `seed` (the same
re-derivation as the seeded probability simulation), because the drop target of a tile is
its dealt position.

    python scripts/playground_correctness_cases.py /tmp/cases.json
    node scripts/playground_correctness.mjs /tmp/cases.json
"""

from __future__ import annotations

import json
import math
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.harness.playground import catalogue, render  # noqa: E402
from app.harness.playground.archetypes import get as get_archetype  # noqa: E402

#: Archetypes this oracle does not cover, with the reason. A gap that is stated is worth
#: more than a guess that is not: a mis-placed drag would be reported as a scoring bug.
SKIPPED = {
    'curve_shift': 'no bundled game uses this archetype',
}


# --------------------------------------------------------------------------- actions


def _check():
    return {'type': 'click', 'id': 'check'}


def _click(node_id):
    return {'type': 'click', 'id': node_id}


def _next():
    return {'type': 'click', 'id': 'next'}


def _set(field, value):
    return {'type': 'set', 'id': field, 'value': value}


def _set_aria(label, value):
    return {'type': 'set_aria', 'aria': label, 'value': value}


def _select(field, value):
    return {'type': 'select', 'id': field, 'value': value}


def _text(text, cls=None):
    action = {'type': 'click_text', 'text': text}
    if cls:
        action['cls'] = cls
    return action


def _text_not(text, cls):
    return {'type': 'click_not_text', 'text': text, 'cls': cls}


def _value(value):
    return {'type': 'click_value', 'value': str(value)}


def _aria(label):
    return {'type': 'click_aria', 'label': label}


def _key(aria):
    return {'type': 'key', 'aria': aria}


def _case(label, actions, expect_correct, expect_gave_up):
    return {
        'label': label,
        'actions': actions,
        'expect_correct': expect_correct,
        'expect_gave_up': expect_gave_up,
    }


def _drag(start, end, on=None):
    """A pointer drag from one viewBox point to another.

    ``on='last'`` grabs the last draggable layer the page registered rather than the
    first; an archetype that wires two drags (``ppf_frontier``: the point along the
    frontier, and the handle that grows it) needs this to reach the second one.
    """
    action = {'type': 'drag',
              'from': [float(start[0]), float(start[1])],
              'to': [float(end[0]), float(end[1])]}
    if on:
        action['on'] = on
    return action


# ------------------------------------------------------------------ number helpers


def _round_half_up(x: float) -> int:
    """JavaScript's ``Math.round``: half rounds towards +infinity, not to even."""
    return math.floor(x + 0.5)


def _fmt(value: float, places: int = 2) -> str:
    """JavaScript's ``fmt(v, places)`` from the runtime: ``toFixed``, with 0 for -0."""
    if not math.isfinite(value):
        return '--'
    x = 0.0 if abs(value) < 1e-9 else value
    return f'{x:.{places}f}'


def _whole(value: float) -> str:
    return str(int(value))


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _round(value: float) -> int:
    """JavaScript's ``Math.round``: halves go *up*, where Python's ``round`` goes to even.

    Only matters for a value landing exactly on .5, which the tray geometry can produce -
    and a half-unit difference between this file and the engine is a drop that misses.
    """
    return int(math.floor(value + 0.5))


def _scale(domain, rng):
    """The runtime's ``scale(domain, range)``, with the ``.invert`` the engines use."""
    d0, d1 = float(domain[0]), float(domain[1])
    r0, r1 = float(rng[0]), float(rng[1])
    span = (d1 - d0) or 1.0

    def fn(value: float) -> float:
        return r0 + (r1 - r0) * (value - d0) / span

    def invert(pixel: float) -> float:
        return d0 + (pixel - r0) / ((r1 - r0) or 1.0) * span

    fn.invert = invert
    return fn


def _shuffle(items, seed: int):
    """The runtime's ``shuffle(list, seed)``: Fisher-Yates over the runtime PRNG.

    A tray dealt by ``shuffle`` has its drop targets at the dealt positions, so the deal
    is re-derived here from the spec's ``seed`` - the same re-derivation as the seeded
    probability run, not a read of the page.
    """
    out = list(items)
    draw = _rand(int(seed))
    for i in range(len(out) - 1, 0, -1):
        j = math.floor(draw() * (i + 1))
        out[i], out[j] = out[j], out[i]
    return out


def _first_scorable(challenges):
    for index, challenge in enumerate(challenges):
        if challenge.get('kind') != 'sandbox':
            return index
    raise ValueError('this game has no scorable challenge')


def _lead_in(challenges, index):
    """The ``Next`` presses needed to walk past any sandbox challenges before ``index``."""
    return [_next() for challenge in challenges[:index] if challenge.get('kind') == 'sandbox']


# ------------------------------------------------------- particle_sandbox (gas laws)


def _factor_label(value: float) -> str:
    """The runtime's ``factorLabel``, which is what the option buttons read."""
    if abs(value - 1) < 1e-9:
        return 'no change (x1)'
    if value > 1:
        return 'x ' + (_whole(value) if _round_half_up(value) == value else _fmt(value, 2))
    inverse = 1.0 / value
    return '/ ' + (_whole(inverse) if _round_half_up(inverse) == inverse else _fmt(inverse, 2))


def build_particle_sandbox(game, html):
    spec = game['spec']
    task = spec['tasks'][0]
    answer = float(task['answer'])
    right = _factor_label(answer)
    wrong = None
    for option in task['options']:
        label = _factor_label(float(option))
        if abs(float(option) - answer) > 1e-9 and label != right:
            wrong = label
            break
    if wrong is None:
        raise ValueError('no option with a distinct wrong label')
    return [
        _case('choose the factor the gas law gives', [_text(right), _check()], [True], [False]),
        _case('choose a wrong factor three times', [_text(wrong), _check(), _check(), _check()],
              [False], [True]),
    ]


# --------------------------------------------------------- circuit_builder (Ohm's law)


def build_circuit_builder(game, html):
    spec = game['spec']
    task = spec['tasks'][0]
    if task['kind'] == 'voltage_drop':
        wanted = task['answer_resistor']
        good = next(r for r in spec['resistors'] if r['id'] == wanted)
        bad = next(r for r in spec['resistors'] if r['id'] != wanted)
        return [
            _case('pick the resistor with the largest drop',
                  [_text(good['label']), _check()], [True], [False]),
            _case('pick the wrong resistor three times',
                  [_text(bad['label']), _check(), _check(), _check()], [False], [True]),
        ]
    answer = float(task['answer'])
    return [
        _case('commit the value Ohm\u2019s law gives',
              [_set('ans', answer), _check()], [True], [False]),
        _case('commit a wrong value three times',
              [_set('ans', answer + 100.0), _check(), _check(), _check()], [False], [True]),
    ]


# ------------------------------------------------------ balance_equation (stoichiometry)


def _parse_formula(text: str) -> dict:
    """A recursive-descent formula parser, the same shape as the engine's own.

    Handles nested groups (``Ca(OH)2`` -> Ca1 O2 H2), which is what the AP Chemistry
    set needs. Re-derived here rather than read from the page, so a parser bug in the
    archetype would surface as a mismatch instead of being mirrored.
    """
    source = ''.join(str(text).split())
    cursor = [0]

    def number() -> int:
        start = cursor[0]
        while cursor[0] < len(source) and source[cursor[0]].isdigit():
            cursor[0] += 1
        return 1 if start == cursor[0] else int(source[start:cursor[0]])

    def group() -> dict:
        out: dict = {}
        while cursor[0] < len(source):
            ch = source[cursor[0]]
            if ch in '([':
                cursor[0] += 1
                inner = group()
                if cursor[0] < len(source) and source[cursor[0]] in ')]':
                    cursor[0] += 1
                mult = number()
                for element, count in inner.items():
                    out[element] = out.get(element, 0) + count * mult
            elif ch in ')]':
                break
            elif 'A' <= ch <= 'Z':
                start = cursor[0]
                cursor[0] += 1
                while cursor[0] < len(source) and 'a' <= source[cursor[0]] <= 'z':
                    cursor[0] += 1
                element = source[start:cursor[0]]
                out[element] = out.get(element, 0) + number()
            else:
                cursor[0] += 1
        return out

    return group()


def _split_side(text: str) -> list:
    return [part.strip() for part in str(text).split('+') if part.strip()]


def solve_equation(text: str, max_coefficient: int):
    """Return ``(species, coefficients)`` for the lowest whole-number balance.

    Enumerates in the same lexicographic order the engine does, so "the lowest whole
    numbers" means the same thing to both.
    """
    normalised = str(text).replace('\u2192', '->').replace('\u21cc', '->').replace('=', '->')
    sides = normalised.split('->')
    if len(sides) < 2:
        raise ValueError(f'no arrow in {text!r}')
    species = [{'formula': f, 'side': 0, 'atoms': _parse_formula(f)} for f in _split_side(sides[0])]
    species += [{'formula': f, 'side': 1, 'atoms': _parse_formula(f)} for f in _split_side(sides[1])]
    elements = sorted({element for sp in species for element in sp['atoms']})

    def balanced(coefficients) -> bool:
        left: dict = {}
        right: dict = {}
        for sp, coefficient in zip(species, coefficients):
            target = left if sp['side'] == 0 else right
            for element, count in sp['atoms'].items():
                target[element] = target.get(element, 0) + count * coefficient
        return all(left.get(element, 0) == right.get(element, 0) for element in elements)

    def gcd_all(coefficients) -> int:
        accumulator = 0
        for coefficient in coefficients:
            accumulator = math.gcd(accumulator, coefficient)
        return accumulator or 1

    coefficients = [1] * len(species)
    found: list | None = None

    def recurse(index: int) -> None:
        nonlocal found
        if found is not None:
            return
        if index == len(species):
            if balanced(coefficients) and gcd_all(coefficients) == 1:
                found = list(coefficients)
            return
        for value in range(1, max_coefficient + 1):
            coefficients[index] = value
            recurse(index + 1)
            if found is not None:
                return

    recurse(0)
    if found is None:
        raise ValueError(f'no minimal balance found for {text!r}')
    return [sp['formula'] for sp in species], found


def build_balance_equation(game, html):
    spec = game['spec']
    equation = spec['equations'][0]
    species, coefficients = solve_equation(equation['equation'],
                                           int(spec.get('max_coefficient') or 8))
    actions = []
    for formula, coefficient in zip(species, coefficients):
        for _ in range(coefficient - 1):
            actions.append(_aria('increase the coefficient of ' + formula))
    actions.append(_check())
    return [
        _case('balance at the lowest whole numbers', actions, [True], [False]),
        _case('leave every coefficient at one, three tries',
              [_check(), _check(), _check()], [False], [True]),
    ]


# ------------------------------------------------------------------ titration_curve


def build_titration_curve(game, html):
    spec = game['spec']
    answer = float(spec['tasks'][0]['answer'])
    return [
        _case('commit the answer the curve gives',
              [_set('ans', answer), _check()], [True], [False]),
        _case('commit a wrong answer three times',
              [_set('ans', answer + 20.0), _check(), _check(), _check()], [False], [True]),
    ]


# ------------------------------------------------------------- calc_choice (economics)


def _opportunity_cost(question, parties):
    party = next(p for p in parties if p['id'] == question['party'])
    x_intercept = float(party['x_intercept'])
    y_intercept = float(party['y_intercept'])
    if question['per_good'] == 'y':
        return x_intercept / y_intercept
    return y_intercept / x_intercept


def build_calc_choice(game, html):
    spec = game['spec']
    question = spec['questions'][0]
    cost = _opportunity_cost(question, spec['parties'])
    right_choice = question['choice_answer']
    wrong_choice = next(c for c in question['choices'] if c != right_choice)
    return [
        _case('right opportunity cost, then the right party',
              [_set('num', cost), _check(), _select('choice', right_choice), _check()],
              [True], [False]),
        _case('right cost, then the wrong party three times',
              [_set('num', cost), _check(), _select('choice', wrong_choice),
               _check(), _check(), _check()],
              [False], [True]),
    ]


# --------------------------------------------------------- elasticity_probe (economics)


def _elasticity(spec):
    points = spec['points']
    p1, q1 = float(points[0]['price']), float(points[0]['quantity'])
    p2, q2 = float(points[1]['price']), float(points[1]['quantity'])
    delta_p, delta_q = p2 - p1, q2 - q1
    ratio = delta_q / (delta_p if delta_p else 1e-9)
    if spec['method'] == 'midpoint':
        return ratio * ((p1 + p2) / (q1 + q2))
    return ratio * (p1 / q1)


def _elasticity_class(value: float) -> str:
    magnitude = abs(value)
    if magnitude > 1.0000001:
        return 'elastic'
    if magnitude < 0.9999999:
        return 'inelastic'
    return 'unit elastic'


def build_elasticity_probe(game, html):
    spec = game['spec']
    coefficient = _elasticity(spec)
    classification = _elasticity_class(coefficient)
    right_sign = spec['sign_answer']
    wrong_sign = next(c for c in spec['sign_choices'] if c != right_sign)
    return [
        _case('coefficient, classification and sign all right',
              [_set('num', coefficient), _check(),
               _select('class', classification), _check(),
               _select('sign', right_sign), _check()],
              [True], [False]),
        # A wrong coefficient is given away after three tries; the classification and the
        # sign are then answered correctly, so the committed outcome is plainly wrong.
        _case('wrong coefficient, then the rest answered right',
              [_set('num', coefficient + 5.0), _check(), _check(), _check(),
               _select('class', classification), _check(),
               _select('sign', right_sign), _check()],
              [False], [False]),
        # The coefficient and the classification are right; only the sign is wrong, three
        # times. This is the case that asks whether a give-up can be scored correct.
        _case('right coefficient and class, wrong sign three times',
              [_set('num', coefficient), _check(),
               _select('class', classification), _check(),
               _select('sign', wrong_sign), _check(), _check(), _check()],
              [False], [True]),
    ]


# --------------------------------------------------------- function_machine (algebra)


def _rule_text(m: float, c: float) -> str:
    """The runtime's ``ruleText``: how the machine writes ``y = mx + c``."""
    if m == 0:
        return 'y = ' + _fmt(c, 0)
    out = 'y = '
    if m == 1:
        out += 'x'
    elif m == -1:
        out += '\u2212x'
    else:
        out += _fmt(m, 0) + 'x'
    if c > 0:
        out += ' + ' + _fmt(c, 0)
    elif c < 0:
        out += ' \u2212 ' + _fmt(abs(c), 0)
    return out


def build_function_machine(game, html):
    spec = game['spec']
    m, c = float(spec['m']), float(spec['c'])
    feeds = [_text('Feed x = ' + _fmt(float(x), 0)) for x in spec['inputs'][:2]]
    if spec['answer_mode'] == 'slope_intercept':
        good = feeds + [_set('in_m', m), _set('in_c', c), _check()]
        bad = feeds + [_set('in_m', m + 1), _set('in_c', c + 1), _check(), _check(), _check()]
    else:
        label = _rule_text(m, c)
        good = feeds + [_text(label, cls='choice'), _check()]
        bad = feeds + [_text_not(label, 'choice'), _check(), _check(), _check()]
    return [
        _case('name the rule the machine is using', good, [True], [False]),
        _case('name a wrong rule three times', bad, [False], [True]),
    ]


# ------------------------------------------------------------- balance_scale (algebra)


def build_balance_scale(game, html):
    spec = game['spec']
    coefficient = int(spec['coefficient'])
    left_constant = int(spec['constant_left'])
    actions = []
    for _ in range(left_constant):
        actions.append({'type': 'click', 'id': 'l_minus'})
    for _ in range(left_constant):
        actions.append({'type': 'click', 'id': 'r_minus'})
    if coefficient > 1:
        actions.append({'type': 'click', 'id': 'l_div'})
        actions.append({'type': 'click', 'id': 'r_div'})
    actions.append(_check())
    return [
        _case('subtract from both pans, then divide both', actions, [True], [False]),
        _case('check without isolating x, three tries',
              [_check(), _check(), _check()], [False], [True]),
    ]


# ---------------------------------------------------------------- area_model (maths)


def _factor_pair(area: int):
    """The engine's ``factorPair``: the factor pair closest to a square, within 24 x 24."""
    pairs = [(a, area // a) for a in range(1, 25) if area % a == 0 and area // a <= 24 and a <= area // a]
    if not pairs:
        return (1, area)
    return min(pairs, key=lambda pair: abs(pair[0] - pair[1]))


def build_area_model(game, html):
    spec = game['spec']
    if spec['mode'] == 'multiply':
        width, height = int(spec['width']), int(spec['height'])
        area = width * height
        return [
            _case('enter the area of the whole rectangle',
                  [_set('answer', area), _check()], [True], [False]),
            _case('enter a wrong area three times',
                  [_set('answer', area + 7), _check(), _check(), _check()], [False], [True]),
        ]
    target = int(spec['area'])
    good_w, good_h = _factor_pair(target)
    bad_w, bad_h = next(((w, h) for w in range(1, 25) for h in range(1, 25) if w * h != target),
                        (1, 1))
    return [
        _case('build a rectangle of the target area',
              [_set('w', good_w), _set('h', good_h), _check()], [True], [False]),
        _case('build the wrong rectangle three times',
              [_set('w', bad_w), _set('h', bad_h), _check(), _check(), _check()],
              [False], [True]),
    ]


# ----------------------------------------------------------- pattern_sequence (maths)


def build_pattern_sequence(game, html):
    spec = game['spec']
    first = int(spec['first'])
    step = int(spec['step'])
    shown = int(spec['shown'])
    next_term = first + shown * step
    return [
        _case('next term, then the rule',
              [_set('nextterm', next_term), _check(),
               _set('aval', first), _set('dval', step), _check()],
              [True, True], [False, False]),
        _case('wrong next term three times',
              [_set('nextterm', next_term + 1), _check(), _check(), _check()], [False], [True]),
    ]


# ------------------------------------------------------------ probability_lab (maths)


def _rand(seed: int):
    """The runtime's ``rand(seed)`` - a mulberry32, reproduced exactly.

    The prediction the game scores is the proportion observed in a *separate seeded run*,
    not the theoretical probability, so this is the only way to know the truth from the
    spec. Reproducing the generator is re-deriving the model, not reading the engine.
    """
    state = (int(seed) & 0xFFFFFFFF) or 1

    def imul(a: int, b: int) -> int:
        return (a * b) & 0xFFFFFFFF

    def next_value() -> float:
        nonlocal state
        state = (state + 0x6D2B79F5) & 0xFFFFFFFF
        t = state
        t = imul(t ^ (t >> 15), t | 1)
        t = (t ^ ((t + imul(t ^ (t >> 7), t | 61)) & 0xFFFFFFFF)) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0

    return next_value


def _observed_proportion(spec) -> float:
    outcomes = spec['outcomes'][:6]
    raw = [max(0.0, float(o['p'])) for o in outcomes]
    total = sum(raw) or 1.0
    probabilities = [value / total for value in raw]
    trials = max(1, _round_half_up(float(spec['predict_trials'])))
    draw = _rand(_round_half_up(float(spec['seed'])) + 999983)
    hits = 0
    for _ in range(trials):
        r = draw()
        accumulator = 0.0
        pick = len(probabilities) - 1
        for index, probability in enumerate(probabilities):
            accumulator += probability
            if r < accumulator:
                pick = index
                break
        if pick == 0:
            hits += 1
    return hits / trials


def build_probability_lab(game, html):
    spec = game['spec']
    observed = _observed_proportion(spec)
    wrong = 0.0 if observed > 0.5 else 1.0
    return [
        _case('predict the proportion the seeded run will show',
              [_set('answer', repr(observed)), _check()], [True], [False]),
        _case('predict a proportion that is far off, three times',
              [_set('answer', wrong), _check(), _check(), _check()], [False], [True]),
    ]


# --------------------------------------------------------------- step_algorithm (CS)


def _bubble_frames(source):
    """The engine's ``bubbleFrames``: one frame per comparison, plus start and end."""
    array = list(source)
    frames = [{'arr': list(array), 'cmp': 0}]
    comparisons = 0
    m = len(array)
    for i in range(m - 1):
        for j in range(m - 1 - i):
            comparisons += 1
            if array[j] > array[j + 1]:
                array[j], array[j + 1] = array[j + 1], array[j]
            frames.append({'arr': list(array), 'cmp': comparisons})
    frames.append({'arr': list(array), 'cmp': comparisons})
    return frames


def _insertion_frames(source):
    """The engine's ``insertionFrames``: a frame per comparison and per placement."""
    array = list(source)
    frames = [{'arr': list(array), 'cmp': 0}]
    comparisons = 0
    m = len(array)
    for i in range(1, m):
        key = array[i]
        j = i - 1
        frames.append({'arr': list(array), 'cmp': comparisons})
        while j >= 0:
            comparisons += 1
            if array[j] > key:
                array[j + 1] = array[j]
                frames.append({'arr': list(array), 'cmp': comparisons})
                j -= 1
            else:
                frames.append({'arr': list(array), 'cmp': comparisons})
                break
        array[j + 1] = key
        frames.append({'arr': list(array), 'cmp': comparisons})
    return frames


def build_step_algorithm(game, html):
    spec = game['spec']
    array = [int(v) for v in spec['array']]
    frames = _bubble_frames(array) if spec['algorithm'] == 'bubble' else _insertion_frames(array)
    if spec['predict'] == 'comparisons':
        answer = frames[-1]['cmp']
        return [
            _case('predict the total comparison count',
                  [_set('answer', answer), _check()], [True], [False]),
            _case('predict a wrong comparison count three times',
                  [_set('answer', answer + 3), _check(), _check(), _check()], [False], [True]),
        ]
    index = min(int(spec.get('k') or 0), len(frames) - 1)
    state = frames[index]['arr']
    answer = ', '.join(str(v) for v in state)
    wrong = ', '.join(str(v) for v in reversed(state))
    if wrong == answer:
        wrong = ', '.join(str(v + 1) for v in state)
    return [
        _case(f'predict the array after {index} steps',
              [_set('answer', answer), _check()], [True], [False]),
        _case('predict a wrong array three times',
              [_set('answer', wrong), _check(), _check(), _check()], [False], [True]),
    ]


# --------------------------------------------------------------------- wave_lab


def _wrap_pi(radians: float) -> float:
    two_pi = math.pi * 2
    value = radians % two_pi
    if value > math.pi:
        value = two_pi - value
    return value


def _wave_category(l1, l2, p1, p2) -> str:
    """The engine's ``category``: how the two waves combine."""
    if abs(l1 - l2) > 1e-6:
        return 'partial'
    difference = _wrap_pi((p2 - p1) * math.pi / 180.0)
    if difference < math.pi / 6:
        return 'constructive'
    if difference > 5 * math.pi / 6:
        return 'destructive'
    return 'partial'


def build_wave_lab(game, html):
    spec = game['spec']
    challenges = spec['challenges']
    index = _first_scorable(challenges)
    lead = _lead_in(challenges, index)
    challenge = challenges[index]
    if challenge['kind'] == 'classify':
        category = _wave_category(float(challenge['l1']), float(challenge['l2']),
                                  float(challenge['p1']), float(challenge['p2']))
        wrong = next(kind for kind in ('constructive', 'destructive', 'partial')
                     if kind != category)
        return [
            _case('predict how the two waves combine',
                  lead + [_value(category), _check()], [True], [False]),
            _case('predict the wrong interference three times',
                  lead + [_value(wrong), _check(), _check(), _check()], [False], [True]),
        ]
    target = 180.0 if challenge['target'] == 'destructive' else 0.0
    other = 0.0 if target == 180.0 else 180.0
    phase1 = float(challenge['p1'])
    right_phase = (phase1 + target) % 360.0
    wrong_phase = (phase1 + other) % 360.0
    return [
        _case('set the phase to hit the interference target',
              lead + [_set_aria('Phase 2', right_phase), _check()], [True], [False]),
        _case('set the wrong phase three times',
              lead + [_set_aria('Phase 2', wrong_phase), _check(), _check(), _check()],
              [False], [True]),
    ]


# --------------------------------------------------------------------- projectile


def _range(speed: float, angle: float, g: float) -> float:
    return speed * speed * math.sin(2.0 * angle * math.pi / 180.0) / g


def build_projectile(game, html):
    spec = game['spec']
    challenges = spec['challenges']
    index = _first_scorable(challenges)
    lead = _lead_in(challenges, index)
    challenge = challenges[index]
    g = float(spec['g'])
    speed = float(challenge['speed'])
    if challenge['kind'] == 'predict_range':
        distance = _range(speed, float(challenge['angle']), g)
        return [
            _case('predict the range from R = v^2 sin(2 theta) / g',
                  lead + [_set('rangeInput', distance), _check()], [True], [False]),
            _case('predict a range that is far too short, three times',
                  lead + [_set('rangeInput', distance * 0.4), _check(), _check(), _check()],
                  [False], [True]),
        ]
    base = _range(speed, float(challenge['angle']), g)
    options = challenge['options']
    best = min(options, key=lambda option: abs(_range(speed, float(option), g) - base))
    worst = max(options, key=lambda option: abs(_range(speed, float(option), g) - base))
    return [
        _case('pick the angle with the same range',
              lead + [_value(best), _check()], [True], [False]),
        _case('pick the wrong angle three times',
              lead + [_value(worst), _check(), _check(), _check()], [False], [True]),
    ]


# ----------------------------------------------------------------------- punnett


def _pair_order(a: str, b: str) -> str:
    if a == b:
        return a + b
    a_upper, b_upper = a.isupper(), b.isupper()
    if a_upper != b_upper:
        return a + b if a_upper else b + a
    return a + b if a < b else b + a


def _punnett_model(traits, parent1, parent2):
    """Gametes, the square, the phenotype counts and the genotype counts."""
    count = len(traits)

    def alleles(genotype, trait):
        return [genotype[2 * trait], genotype[2 * trait + 1]]

    def gametes(genotype):
        out = ['']
        for trait in range(count):
            first, second = alleles(genotype, trait)
            out = [prefix + suffix for prefix in out for suffix in (first, second)]
        return out

    def combine(a, b):
        return ''.join(_pair_order(a[trait], b[trait]) for trait in range(count))

    def rank(trait, a, b):
        dominant = trait['dominant_letter']
        recessive = trait['recessive_letter']
        if trait['mode'] == 'incomplete':
            if a == dominant and b == dominant:
                return 0
            if a == recessive and b == recessive:
                return 2
            return 1
        return 2 if (a == recessive and b == recessive) else 0

    def phenotype_key(genotype):
        return ''.join(str(rank(traits[trait], *alleles(genotype, trait)))
                       for trait in range(count))

    left, right = gametes(parent1), gametes(parent2)
    phenotypes: dict = {}
    genotypes: dict = {}
    for a in left:
        for b in right:
            cell = combine(a, b)
            key = phenotype_key(cell)
            phenotypes[key] = phenotypes.get(key, 0) + 1
            genotypes[cell] = genotypes.get(cell, 0) + 1
    return {
        'phenotypes': phenotypes,
        'genotypes': genotypes,
        'total': len(left) * len(right),
    }


def _ratio_text(phenotypes: dict) -> str:
    keys = sorted(phenotypes)
    counts = [phenotypes[key] for key in keys]
    divisor = 0
    for value in counts:
        divisor = math.gcd(divisor, value)
    divisor = divisor or 1
    return ':'.join(str(value // divisor) for value in counts)


def _fraction_text(numerator: int, denominator: int) -> str:
    divisor = math.gcd(numerator, denominator) or 1
    numerator, denominator = numerator // divisor, denominator // divisor
    return str(numerator) if denominator == 1 else f'{numerator}/{denominator}'


def _canonical_genotype(traits, genotype: str) -> str:
    return ''.join(_pair_order(genotype[2 * trait], genotype[2 * trait + 1])
                   for trait in range(len(traits)))


def build_punnett(game, html):
    spec = game['spec']
    challenges = spec['challenges']
    index = _first_scorable(challenges)
    lead = _lead_in(challenges, index)
    challenge = challenges[index]
    model = _punnett_model(spec['traits'], challenge['parent1'], challenge['parent2'])
    if challenge['kind'] == 'ratio':
        answer = _ratio_text(model['phenotypes'])
        wrong = next(option for option in challenge['options'] if option != answer)
        return [
            _case('read the phenotype ratio off the square',
                  lead + [_value(answer), _check()], [True], [False]),
            _case('choose the wrong ratio three times',
                  lead + [_value(wrong), _check(), _check(), _check()], [False], [True]),
        ]
    if challenge['kind'] == 'probability':
        wanted = _canonical_genotype(spec['traits'], challenge['ask'])
        hits = model['genotypes'].get(wanted, 0)
        answer = _fraction_text(hits, model['total'])
        wrong = next(option for option in challenge['options'] if option != answer)
        return [
            _case('read the genotype probability off the square',
                  lead + [_value(answer), _check()], [True], [False]),
            _case('choose the wrong probability three times',
                  lead + [_value(wrong), _check(), _check(), _check()], [False], [True]),
        ]
    raise ValueError(f'unsupported punnett challenge kind {challenge["kind"]!r}')


# ------------------------------------------------------------------ orbit_gravity


def _orbit_classify(mass: float, speed_kms: float, orbit_radius: float, body_radius: float) -> str:
    """The engine's ``classify``: escape / crash / closed, from the orbit's energy."""
    mu = 6.674e-11 * mass * 1e24
    velocity = speed_kms * 1000.0
    energy = velocity * velocity / 2.0 - mu / orbit_radius
    if energy >= 0:
        return 'escape'
    semi_major = -mu / (2.0 * energy)
    angular = orbit_radius * velocity
    eccentricity = math.sqrt(max(0.0, 1.0 + 2.0 * energy * angular * angular / (mu * mu)))
    periapsis = semi_major * (1.0 - eccentricity)
    if periapsis < body_radius:
        return 'crash'
    return 'closed'


def build_orbit_gravity(game, html):
    spec = game['spec']
    challenges = spec['challenges']
    index = _first_scorable(challenges)
    lead = _lead_in(challenges, index)
    challenge = challenges[index]
    orbit_radius = float(spec['orbit_radius'])
    body_radius = float(spec['body_radius'])
    if challenge['kind'] == 'classify':
        fate = _orbit_classify(float(challenge['mass']), float(challenge['speed']),
                               orbit_radius, body_radius)
        wrong = next(kind for kind in ('closed', 'crash', 'escape') if kind != fate)
        return [
            _case('predict the fate of the satellite',
                  lead + [_value(fate), _check()], [True], [False]),
            _case('predict the wrong fate three times',
                  lead + [_value(wrong), _check(), _check(), _check()], [False], [True]),
        ]
    mass = float(challenge['mass'])
    mu = 6.674e-11 * mass * 1e24
    if challenge['target'] == 'escape':
        speed = math.sqrt(2.0 * mu / orbit_radius) / 1000.0 * 1.05
    elif challenge['target'] == 'crash':
        speed = math.sqrt(mu / orbit_radius) / 1000.0 * 0.5
    else:
        speed = math.sqrt(mu / orbit_radius) / 1000.0
    return [
        _case(f'set the speed the {challenge["target"]} target needs',
              lead + [_set_aria('Launch speed', speed), _check()], [True], [False]),
        _case('set a speed that misses the target three times',
              lead + [_set_aria('Launch speed', speed * 0.2 + 0.5), _check(), _check(), _check()],
              [False], [True]),
    ]


# ---------------------------------------------------------------- matching_pairs


def build_matching_pairs(game, html):
    spec = game['spec']
    pairs = spec['pairs']
    good = []
    for pair in pairs:
        good.append(_key('Item: ' + pair['left']))
        good.append(_key('Partner: ' + pair['right']))
    bad = []
    for _ in range(3):
        bad.append(_key('Item: ' + pairs[0]['left']))
        bad.append(_key('Partner: ' + pairs[1]['right']))
    for pair in pairs[1:]:
        bad.append(_key('Item: ' + pair['left']))
        bad.append(_key('Partner: ' + pair['right']))
    return [
        _case('match every pair (the board is the commit)', good, [True], [False]),
        _case('one pair revealed after three tries, then the rest matched',
              bad, [False], [True]),
    ]


# --------------------------------------------------- number_line (marker on a line)


def build_number_line(game, html):
    """Drag the boundary marker to the value the spec declares, then commit.

    The engine maps a value to a pixel with ``scale([min, max], [78, 812])``; the value
    comes straight from the task, so the drop point is the spec's own arithmetic.
    """
    spec = game['spec']
    vmin, vmax = float(spec['min']), float(spec['max'])
    X0, X1, LY = 78.0, 812.0, 250.0
    to_x = _scale([vmin, vmax], [X0, X1])
    task = spec['tasks'][0]
    value = float(task['value'])

    def place(v):
        return _drag([(X0 + X1) / 2.0, LY], [to_x(v), LY])

    if task.get('kind') == 'inequality':
        good_dir = task['direction']
        bad_dir = 'left' if good_dir == 'right' else 'right'
        return [
            _case('place the boundary and shade the way the inequality runs',
                  [place(value), _click(good_dir), _check()], [True], [False]),
            _case('right boundary, shading the wrong way, three times',
                  [place(value), _click(bad_dir), _check(), _check(), _check()],
                  [False], [True]),
        ]
    return [
        _case('place the marker exactly on the value the task names',
              [place(value), _check()], [True], [False]),
        _case('place the marker away from the value, three times',
              [place(vmin), _check(), _check(), _check()], [False], [True]),
    ]


# ----------------------------------------------------- plot_points (points on a line)


def build_plot_points(game, html):
    """Drag grid points onto ``y = mx + c``.

    The rule (``m``, ``c``) and the axis bounds are spec fields, so a point that satisfies
    the rule is exact arithmetic; the engine's ``scale`` gives the pixel.
    """
    spec = game['spec']
    xmin, xmax = float(spec['x_min']), float(spec['x_max'])
    ymin, ymax = float(spec['y_min']), float(spec['y_max'])
    X0, X1, Y0, Y1 = 78.0, 812.0, 388.0, 44.0
    to_x = _scale([xmin, xmax], [X0, X1])
    to_y = _scale([ymin, ymax], [Y0, Y1])
    m, c = float(spec['m']), float(spec['c'])
    need = int(spec['required_points'])
    mode = spec.get('mode', 'line')
    tray_x0, tray_y, tray_gap = 300.0, 424.0, 46.0

    def put(index, x, y):
        return _drag([tray_x0 + index * tray_gap, tray_y], [to_x(x), to_y(y)])

    on_line = []
    if mode == 'intercept_and_point':
        on_line.append((0.0, c))
    x = float(math.ceil(xmin))
    while len(on_line) < need and x <= xmax:
        y = m * x + c
        if ymin <= y <= ymax and not any(px == x for px, _ in on_line):
            on_line.append((x, y))
        x += 1.0
    if len(on_line) < need:
        raise ValueError('no grid intersections of the rule lie inside the axes')

    # Three points deliberately off the rule - placed, so the commit is a real wrong answer.
    off_line = []
    for index in range(need):
        x = float(index)
        y = 0.0 if abs(m * x + c) > 1e-9 else 1.0
        off_line.append((x, y))

    good = [put(i, x, y) for i, (x, y) in enumerate(on_line)] + [_check()]
    bad = [put(i, x, y) for i, (x, y) in enumerate(off_line)] + [_check(), _check(), _check()]
    return [
        _case('plot points that all satisfy the rule', good, [True], [False]),
        _case('plot points off the rule, three times', bad, [False], [True]),
    ]


# ------------------------------------------------- order_sequence (drag steps in order)


def _order_deal(spec):
    """The engine's deal: ``shuffle(answer, seed)``, re-dealt with ``seed + 1`` if equal."""
    items = spec['items']
    answer = [item['id'] for item in items]
    seed = spec.get('seed')
    seed = 11 if seed in (None, 0) else int(seed)
    dealt = _shuffle(answer, seed)
    if len(answer) > 1 and dealt == answer:
        dealt = _shuffle(answer, seed + 1)
    return answer, dealt


def _order_rows(n):
    """The engine's ``fitRows``: rows share the stage height instead of a fixed 38px.

    Mirrored here for the same reason the label_diagram tray is mirrored: the drop
    point is geometry, and a case that guessed it would report a layout change as a
    scoring bug. Keep in step with ``_ENGINE_ORDER``'s ``fitRows``.
    """
    top = 48.0
    band = 434.0 - top
    row_h = _clamp((band - (n - 1) * 22.0) / n, 38.0, 74.0)
    gap = _clamp((band - n * row_h) / (n - 1), 8.0, 22.0) if n > 1 else 0.0
    used = n * row_h + (n - 1) * gap
    return row_h, gap, top + max(0.0, (band - used) / 2.0)


def build_order_sequence(game, html):
    spec = game['spec']
    items = spec['items']
    answer, dealt = _order_deal(spec)
    pool_x, slot_x = 26.0, 392.0
    row_h, row_gap, top = _order_rows(len(items))

    def row_y(index):
        return top + index * (row_h + row_gap)

    def plan(sequence):
        """Drags that place ``sequence[k]`` into slot ``k``, tracking the shrinking pool."""
        pool = list(dealt)
        actions = []
        for k, tile_id in enumerate(sequence):
            p = pool.index(tile_id)
            actions.append(_drag([pool_x + 150.0, row_y(p) + row_h / 2.0],
                                 [slot_x + 20.0, row_y(k) + row_h / 2.0]))
            pool.remove(tile_id)
        return actions

    good = plan(answer) + [_check()]
    swapped = list(answer)
    swapped[0], swapped[1] = swapped[1], swapped[0]
    bad = plan(swapped) + [_check(), _check(), _check()]
    return [
        _case('drag every step into the order the spec declares', good, [True], [False]),
        _case('swap two steps, then commit three times', bad, [False], [True]),
    ]


# ------------------------------------------------ label_diagram (labels onto hotspots)


def _pill_width(text) -> float:
    """The engine's ``pillW``: a tray pill sized from its text."""
    return _clamp(30.0 + len(str(text)) * 6.4, 78.0, 190.0)


_DEF_R = 40.0


def _diagram_bounds(shapes, labels):
    """The engine's ``diagramBounds()``: the box the spec's parts occupy, in spec units."""
    xs, ys = [], []
    for s in shapes:
        kind = s.get('kind')
        if kind == 'line':
            xs += [float(s['x']), float(s['w'])]
            ys += [float(s['y']), float(s['h'])]
        elif kind == 'circle':
            r = max(2.0, float(s['w']) / 2.0)
            xs += [float(s['x']) - r, float(s['x']) + r]
            ys += [float(s['y']) - r, float(s['y']) + r]
        else:
            xs += [float(s['x']), float(s['x']) + max(1.0, float(s['w']))]
            ys += [float(s['y']), float(s['y']) + max(1.0, float(s['h']))]
    for lb in labels:
        r = float(lb.get('radius') or _DEF_R)
        xs += [float(lb['x']) - r, float(lb['x']) + r]
        ys += [float(lb['y']) - r, float(lb['y']) + r]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    return x0, y0, x1 - x0, y1 - y0


def _label_layout(shapes, labels, order):
    """The engine's tray placement *and* diagram fit, which are one decision.

    The tray is a row under a wide diagram and a column beside a tall one, and the
    diagram is fitted into whatever is left - so a case cannot compute one without the
    other. Returns ``(dx, dy, tray)`` with ``tray[i] = (x, y, w)`` in viewBox units.

    This mirrors the engine exactly, including the clamps and the rounding, because a
    mismatch of one unit puts the drop outside the hotspot and the case reports a false
    failure. The archetype scales the *coordinates* rather than wrapping the diagram in
    a group transform precisely so that hit-testing and drawing share one space; this
    function is the price of that, and it is cheaper than the alternative, which is a
    hit test that silently disagrees with what is drawn.
    """
    x, y, w, h = _diagram_bounds(shapes, labels)
    n = len(labels)
    gap = 10.0
    widest = max((_pill_width(lb['text']) for lb in labels), default=120.0)
    side = (w / max(1.0, h)) < 1.5
    col_w = float(_round(_clamp(widest + 4.0, 120.0, 210.0))) if side else 0.0
    col_x = 860.0 - 16.0 - col_w
    top = 8.0
    bottom = 452.0 if side else 398.0 - 30.0
    left = 16.0
    right = (col_x - 20.0) if side else 860.0 - 16.0
    avail_w, avail_h = right - left, bottom - top
    k = _clamp(min(avail_w / max(1.0, w), avail_h / max(1.0, h)), 0.2, 2.6)
    ox = left + (avail_w - w * k) / 2.0 - x * k
    oy = top + (avail_h - h * k) / 2.0 - y * k

    tray = {}
    if side:
        stack_h = n * 34.0 + (n - 1) * gap
        sy = float(_round((460.0 - stack_h) / 2.0))
        for slot, i in enumerate(order):
            tray[i] = (col_x, sy + slot * (34.0 + gap), col_w)
    else:
        per = math.floor((860.0 - 48.0 - (n - 1) * gap) / n)
        widths = [min(_pill_width(labels[i]['text']), per) for i in order]
        total = sum(widths) + (n - 1) * gap
        tx = max(24.0, float(_round((860.0 - total) / 2.0)))
        for i, pill in zip(order, widths):
            tray[i] = (tx, 398.0, pill)
            tx += pill + gap
    return (lambda v: ox + v * k), (lambda v: oy + v * k), tray


def build_label_diagram(game, html):
    """Drag each label onto the hotspot the spec gives it coordinates for."""
    spec = game['spec']
    labels = spec['labels']
    n = len(labels)
    seed = spec.get('seed')
    seed = 3 if seed in (None, 0) else int(seed)
    order = _shuffle(list(range(n)), seed)
    dx, dy, tray = _label_layout(spec.get('shapes') or [], labels, order)

    def drop(label_index, hotspot_index):
        x, y, w = tray[label_index]
        return _drag([x + w / 2.0, y + 17.0],
                     [dx(float(labels[hotspot_index]['x'])), dy(float(labels[hotspot_index]['y']))])

    good = [drop(i, i) for i in range(n)]
    wrong_hotspot = 1 if n > 1 else 0
    bad = [drop(0, wrong_hotspot) for _ in range(3)] + [drop(i, i) for i in range(1, n)]
    return [
        _case('drag every label onto its own hotspot', good, [True], [False]),
        _case('drop one label on the wrong hotspot three times, then place the rest',
              bad, [False], [True]),
    ]


# ------------------------------------------------------- sort_columns (sort by column)


def build_sort_columns(game, html):
    """Sort tiles by keyboard: the tray tile carries its text, the column its label.

    The commit is completion (``commits_on='completion'``): there is no Check, so every
    tile must be placed for the outcome to fire.
    """
    spec = game['spec']
    columns = spec['columns']
    labels = {column['id']: column['label'] for column in columns}
    tiles = spec['tiles']

    def put(tile, column_id):
        return [_key('Tile: ' + tile['text']),
                _key('Place the selected tile in ' + labels[column_id])]

    good = []
    for tile in tiles:
        good += put(tile, tile['column'])
    wrong_column = next(c['id'] for c in columns if c['id'] != tiles[0]['column'])
    bad = put(tiles[0], wrong_column) * 3
    for tile in tiles[1:]:
        bad += put(tile, tile['column'])
    return [
        _case('sort every tile into the column the spec declares', good, [True], [False]),
        _case('one tile in the wrong column three times, then sort the rest',
              bad, [False], [True]),
    ]


# ------------------------------------------------------- ppf_frontier (point on a PPF)


def build_ppf_frontier(game, html):
    """Move the point along the bowed frontier, and (where a task asks) grow the frontier.

    The frontier is ``(x/a)^bow + (y/b)^bow = 1`` with the spec's intercepts, so the
    point at a target output and its opportunity cost are exact; the engine's ``scale``
    gives the pixel for each.
    """
    spec = game['spec']
    x_max, y_max = float(spec['x_max']), float(spec['y_max'])
    x_int, y_int = float(spec['x_intercept']), float(spec['y_intercept'])
    bow = float(spec['bow'])
    X0, X1, Y0, Y1 = 78.0, 812.0, 388.0, 44.0
    to_x = _scale([0.0, x_max], [X0, X1])
    to_y = _scale([0.0, y_max], [Y0, Y1])
    tasks = spec['tasks']

    def y_at(u):
        u = _clamp(u, 0.0, 1.0)
        return y_int * (1.0 - u ** bow) ** (1.0 / bow)

    def u_of(t, key):
        return _clamp(float(t.get(key, 0)) / x_int, 0.0, 1.0)

    def move_along(t):
        u = u_of(t, 'target_x')
        actions = [_drag([(X0 + X1) / 2.0, 200.0], [to_x(x_int * u), 200.0])]
        if t.get('ask_cost'):
            actions.append(_set('cost', repr(y_at(u_of(t, 'from_x')) - y_at(u))))
        return actions + [_check()]

    def grow(t):
        want = float(t['target_scale'])
        axis = t.get('grow_axis', 'both')
        norm = math.sqrt(x_int * x_int + y_int * y_int)
        if axis == 'x':
            xd, yd = want * x_int, 0.0
        elif axis == 'y':
            xd, yd = 0.0, want * y_int
        else:
            reach = want * norm
            xd = yd = reach / math.sqrt(2.0)
        return [_drag([to_x(x_int), to_y(y_int)], [to_x(xd), to_y(yd)], on='last'),
                _check()]

    first = tasks[0]
    good = move_along(first)
    # A wrong answer: stop short of the required output and commit three times.
    short = _clamp(u_of(first, 'target_x') - 0.25, 0.0, 1.0)
    bad = [_drag([(X0 + X1) / 2.0, 200.0], [to_x(x_int * short), 200.0]),
           _check(), _check(), _check()]

    cases = [
        _case('move the point to the output the task names and read the cost',
              good, [True], [False]),
        _case('stop short of the required output, three times', bad, [False], [True]),
    ]

    grow_index = next((i for i, t in enumerate(tasks) if t.get('kind') == 'grow'), None)
    if grow_index is not None:
        # Each task commits its own outcome, so reaching the growth task and clearing it
        # produces one outcome per task walked past - here, two.
        lead = []
        for t in tasks[:grow_index]:
            lead += move_along(t)
        cases.append(_case('walk to the growth task and drag the frontier out to the '
                           'capacity the spec names',
                           lead + [_next()] + grow(tasks[grow_index]),
                           [True] * (grow_index + 1), [False] * (grow_index + 1)))
    return cases


# ------------------------------------------------------------------------ registry

BUILDERS = {
    'particle_sandbox': build_particle_sandbox,
    'circuit_builder': build_circuit_builder,
    'balance_equation': build_balance_equation,
    'titration_curve': build_titration_curve,
    'calc_choice': build_calc_choice,
    'elasticity_probe': build_elasticity_probe,
    'function_machine': build_function_machine,
    'balance_scale': build_balance_scale,
    'area_model': build_area_model,
    'pattern_sequence': build_pattern_sequence,
    'probability_lab': build_probability_lab,
    'step_algorithm': build_step_algorithm,
    'wave_lab': build_wave_lab,
    'projectile': build_projectile,
    'punnett': build_punnett,
    'orbit_gravity': build_orbit_gravity,
    'matching_pairs': build_matching_pairs,
    'number_line': build_number_line,
    'plot_points': build_plot_points,
    'order_sequence': build_order_sequence,
    'label_diagram': build_label_diagram,
    'sort_columns': build_sort_columns,
    'ppf_frontier': build_ppf_frontier,
}


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/playground_correctness_cases.json')

    cases = []
    covered: dict = {}
    problems: list = []
    games_seen: dict = {}

    for game in catalogue.all_games():
        archetype_id = game['archetype']
        games_seen[archetype_id] = games_seen.get(archetype_id, 0) + 1
        builder = BUILDERS.get(archetype_id)
        if builder is None:
            continue
        archetype = get_archetype(archetype_id)
        if archetype is None:
            problems.append(f'{game["slug"]}: archetype {archetype_id!r} is not registered')
            continue
        try:
            html = render(archetype, game['spec'])
        except Exception as exc:  # a render failure is itself a finding
            problems.append(f'{game["slug"]}: render failed: {type(exc).__name__}: {exc}')
            continue
        try:
            built = builder(game, html)
        except Exception as exc:
            problems.append(f'{game["slug"]}: case builder failed: {type(exc).__name__}: {exc}')
            traceback.print_exc()
            continue
        for case in built:
            cases.append({**case, 'slug': game['slug'], 'archetype': archetype_id, 'html': html})
        covered[archetype_id] = covered.get(archetype_id, 0) + len(built)

    out.write_text(json.dumps(cases), encoding='utf-8')

    # ---- coverage table ------------------------------------------------------
    registered = sorted(a.id for a in __import__('app.harness.playground.archetypes',
                                                 fromlist=['x']).all_archetypes())
    print(f'wrote {len(cases)} cases over {len(covered)} archetypes -> {out}')
    print('')
    print(f'{"ARCHETYPE":<22} {"GAMES":>5} {"CASES":>5}  STATUS')
    print('-' * 78)
    for archetype_id in registered:
        games = games_seen.get(archetype_id, 0)
        count = covered.get(archetype_id, 0)
        if count:
            status = f'covered ({count} case(s))'
        elif archetype_id in SKIPPED:
            status = 'skipped: ' + SKIPPED[archetype_id]
        else:
            status = 'NOT COVERED'
        print(f'{archetype_id:<22} {games:>5} {count:>5}  {status}')
    print('-' * 78)
    print(f'{"TOTAL":<22} {sum(games_seen.values()):>5} {len(cases):>5}')
    if problems:
        print('')
        print('PROBLEMS')
        for problem in problems:
            print('  ' + problem)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
