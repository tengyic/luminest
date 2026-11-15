"""A complete, hand-written unit: exponents, radicals and irrational numbers.

Why this module exists
----------------------
The review of 2026-11-13 was right: a graph with 2,205 nodes and 30 hand-written
lessons is breadth, not depth. Generated four-block lessons are honest about having
no worked example, but a learner whose course is *the default one* should meet real
teaching somewhere. This module adds one whole unit of the authored mathematics
course, written by hand and reviewed like any other source change.

Provenance rules, kept deliberately strict:

* Every concept here gets the same eight blocks as the original 30, including a
  ``worked_example`` with numbered steps and an independent check. There is no
  generated prose, no model draft, and no overlay flag. ``authored_share`` counts
  these as ``reviewed_concepts`` because they live in the source tree and went
  through review, not because a flag says so.
* Each concept maps to a real node in ``algebra_one_year.json`` via
  :data:`TARGETS`. Adding a lesson without a graph node would create depth that
  the course map cannot point at.
* Every worked example names its own verification step. A learner can check the
  claim without trusting the prose. That is the difference between a worked
  example and an assertion.
* The mathematics is original exposition. External readings stay link-only, as in
  the rest of the authored course; no source content is copied.

The unit is self-contained: :func:`register` is called from ``curriculum.py`` and
returns the specs, details, distractor rules, question builders and graph targets.
Nothing here imports ``curriculum``, so the module can be audited on its own.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any, Callable

#: The course this unit belongs to and the unit label used for source attribution.
COURSE_ID = 'integrated_math_1'
UNIT = 'Exponents, radicals and irrational numbers'

#: Reviewed join from each authored lesson id to the node it teaches in
#: ``app/curriculum_packs/algebra_one_year.json``. Verified against that pack.
TARGETS = {
    'integer_exponents': 'integer_exponents',
    'zero_and_negative_exponents': 'zero_and_negative_exponents',
    'power_of_a_power_and_power_of_a_product': 'power_of_a_power_and_power_of_a_product',
    'square_roots_and_perfect_squares': 'square_roots_and_perfect_squares',
    'simplifying_radical_expressions': 'simplifying_radical_expressions',
    'rational_exponents': 'rational_exponents',
    'estimating_and_locating_irrational_numbers': 'estimating_and_locating_irrational_numbers',
    'scientific_notation': 'scientific_notation',
}

#: Each spec is the 11-field tuple the authored curriculum builder consumes:
#: (id, title, unit, prerequisites, summary, formula, example, project,
#:  simulation kind, parameter label, hint).
SPECS: list[tuple] = [
    (
        'integer_exponents', 'Integer exponents', UNIT, ['exponents'],
        'A positive integer exponent counts repeated copies of a base. The exponent is a count of factors, not a multiplier.',
        'a^n = a * a * ... * a (n factors), n a positive integer',
        '2^5 = 32 because five copies of 2 multiply to 32; 2 * 5 = 10 is a different operation.',
        'Model repeated doubling over five rounds, write the total as a power, and explain why multiplying by five is wrong.',
        'expression', 'Probe base a', 'Count the factors before multiplying.'),
    (
        'zero_and_negative_exponents', 'Zero and negative exponents', UNIT, ['integer_exponents'],
        'Extending the quotient rule to all integer exponents forces a^0 = 1 and a^(-n) = 1/a^n. A negative exponent is a reciprocal, not a negative number.',
        'a^0 = 1 and a^(-n) = 1/a^n, for a != 0',
        '2^(-3) = 1/8. It is positive and smaller than 1; -2^3 = -8 is a different expression.',
        'Describe a quantity that halves each step, write later values with negative exponents, and convert one to a fraction.',
        'expression', 'Probe base a', 'Divide by the base as the exponent drops by one.'),
    (
        'power_of_a_power_and_power_of_a_product', 'Powers of powers and products', UNIT,
        ['integer_exponents'],
        'A power of a power multiplies exponents; a power of a product applies the exponent to every factor. Both follow from counting factors.',
        '(a^m)^n = a^(mn) and (ab)^n = a^n b^n',
        '(2^3)^2 = 2^6 = 64, and (2*3)^2 = 2^2 * 3^2 = 36.',
        'Write a square area whose side is a product, expand the power, and check the identity at two input values.',
        'expression', 'Probe base a', 'Count how many copies of each factor appear.'),
    (
        'square_roots_and_perfect_squares', 'Square roots and perfect squares', UNIT, ['exponents'],
        'The principal square root of a nonnegative number is the nonnegative number whose square is it. Perfect squares have integer roots.',
        'sqrt(a) = b means b >= 0 and b^2 = a',
        'sqrt(49) = 7 because 7^2 = 49; sqrt(50) lies between 7 and 8 and is not an integer.',
        'Find a square area, measure its side, and decide whether the root is exact or must be estimated.',
        'expression', 'Probe radicand', 'Square the candidate root to check it.'),
    (
        'simplifying_radical_expressions', 'Simplifying radical expressions', UNIT,
        ['square_roots_and_perfect_squares', 'factoring'],
        'Pull perfect-square factors out of a radicand using sqrt(ab) = sqrt(a)sqrt(b). A simplified radical has no square factor left inside.',
        'sqrt(a^2 b) = a sqrt(b) for a >= 0 and b >= 0',
        'sqrt(72) = sqrt(36 * 2) = 6 sqrt(2), and (6 sqrt(2))^2 = 72 confirms it.',
        'Simplify a measured area written as a radical, then square the result to verify it.',
        'expression', 'Probe square factor', 'Factor the radicand before moving anything outside.'),
    (
        'rational_exponents', 'Rational exponents', UNIT,
        ['zero_and_negative_exponents', 'simplifying_radical_expressions'],
        'A rational exponent combines a root and a power: a^(m/n) is the nth root of a^m. The integer exponent rules still apply.',
        'a^(m/n) = (nth root of a)^m = nth root of (a^m), a >= 0 for even n',
        '8^(2/3) = (cube root of 8)^2 = 2^2 = 4.',
        'Model growth over a fractional number of periods and evaluate by taking the root before the power.',
        'expression', 'Probe base a', 'Take the root indicated by the denominator first.'),
    (
        'estimating_and_locating_irrational_numbers', 'Estimating irrational numbers', UNIT,
        ['rational_exponents', 'signed_numbers'],
        'An irrational number cannot be written as a ratio of integers. Its decimal never terminates or repeats, but it can be bracketed between rationals as tightly as needed.',
        'if p^2 < a < q^2 then p < sqrt(a) < q for p, q >= 0',
        'sqrt(10) lies between 3 and 4 because 9 < 10 < 16; 3.16^2 = 9.9856 narrows it further.',
        'Bracket an irrational length between tenths, then hundredths, and explain why the process does not terminate.',
        'expression', 'Probe radicand', 'Square both bounds before comparing them to the radicand.'),
    (
        'scientific_notation', 'Scientific notation', UNIT,
        ['zero_and_negative_exponents', 'ratios'],
        'Scientific notation writes a number as a coefficient in [1, 10) times a power of ten. The exponent records how far the decimal point moved.',
        'a * 10^n with 1 <= |a| < 10 and n an integer',
        '0.0042 = 4.2 * 10^(-3), because the decimal point moved three places right.',
        'Express one very large and one very small measured quantity in scientific notation, then multiply them.',
        'expression', 'Probe coefficient', 'Keep exactly one nonzero digit before the decimal point.'),
]

#: The five prose fields behind each lesson: definitions and conditions, the
#: numbered worked example, the misconception and its counterexample, retrieval
#: without notes, and an independent cross-check.
DETAILS: dict[str, tuple[str, str, str, str, str]] = {
    'integer_exponents': (
        'The base is the repeated factor; the exponent is how many times it appears. a^1 = a. A power is one number, and the exponent alone is not a factor. Order matters: 2^3 = 8 while 3^2 = 9.',
        '1. Write 3^4 as four copies of 3: 3 * 3 * 3 * 3.\n'
        '2. Multiply left to right: 3 * 3 = 9, then 9 * 3 = 27, then 27 * 3 = 81.\n'
        '3. Check by grouping: (3 * 3)(3 * 3) = 9 * 9 = 81.\n'
        '4. Compare with 3 * 4 = 12 to confirm the exponent counts factors rather than multiplying.',
        '3^4 is not 12. The product rule also requires the same base: 2^3 * 3^2 is not 5^5, because the factors are different.',
        'Without notes, evaluate 4^3 and 2^5, then say which is larger and why. Report your confidence from 0 to 1 before checking.',
        'Verify 4^3 = 64 by repeated grouping (4, 16, 64) and by writing out all three factors. Explain why both routes must agree.'),
    'zero_and_negative_exponents': (
        'The base must be nonzero because dividing by zero is undefined. The pattern a^3, a^2, a^1 divides by a at each step, so a^0 = 1 and a^(-1) = 1/a are forced by consistency, not chosen by convention. The reciprocal is positive when a is positive.',
        '1. Start from 5^3 = 125, 5^2 = 25, 5^1 = 5; each step down divides by 5.\n'
        '2. Continue: 5^0 = 5/5 = 1.\n'
        '3. One step further gives 5^(-1) = 1/5 and 5^(-2) = 1/25.\n'
        '4. Check: 5^(-2) * 5^2 = (1/25) * 25 = 1, which matches a^(-n) * a^n = a^0.',
        'A negative exponent does not make the answer negative: 2^(-3) = 1/8, not -8. Also (a + b)^(-1) is not a^(-1) + b^(-1); at a = b = 1 the left side is 1/2 and the right side is 2.',
        'Without notes, write 3^(-2) as a fraction and explain why 3^0 = 1. Report confidence before checking.',
        'Verify 2^(-4) = 1/16 by multiplying it by 2^4 to recover 1, and independently by dividing 1 by 2 four times.'),
    'power_of_a_power_and_power_of_a_product': (
        '(ab)^n holds because each of the n factors contributes one a and one b. It does not extend to sums: (a + b)^n is not a^n + b^n. In (a^m)^n the base is a^m, so its n copies contain mn copies of a.',
        '1. Expand (3^2)^3 as (3^2)(3^2)(3^2): three groups of two 3s, so six 3s.\n'
        '2. That is 3^6 = 729.\n'
        '3. Separately, (2x)^3 = (2x)(2x)(2x) = 8x^3.\n'
        '4. Check at x = 2: 8 * 2^3 = 64, and (2 * 2)^3 = 4^3 = 64.',
        '(a + b)^2 = a^2 + b^2 is false: at a = b = 1 the left side is 4 and the right side is 2. Also (a^m)^n is a^(mn), not a^(m+n).',
        'Without notes, simplify (x^3)^4 and (3y)^2, then evaluate the second at y = 2. Report confidence before checking.',
        'Check (x^2)^3 = x^6 at x = -2 by evaluating both sides, and confirm (2y)^3 = 8y^3 at y = 3 and y = -1.'),
    'square_roots_and_perfect_squares': (
        'The radical sign asks for the principal (nonnegative) root, so sqrt(9) = 3, not plus or minus 3, even though x^2 = 9 has two solutions. Square roots of negative numbers are not real. sqrt(a^2) = |a|.',
        '1. To find sqrt(144), look for a nonnegative number whose square is 144.\n'
        '2. 12^2 = 144 and 12 >= 0, so sqrt(144) = 12.\n'
        '3. Check the candidate by squaring it: 12^2 = 144, so the root is verified.\n'
        '4. For sqrt(20), check the bounds 4^2 = 16 and 5^2 = 25; since 4.5^2 = 20.25, the root is slightly below 4.5 and is not an integer.',
        'sqrt(a + b) is not sqrt(a) + sqrt(b): sqrt(9 + 16) = 5 while 3 + 4 = 7. Also sqrt((-3)^2) = 3, because the principal root is nonnegative.',
        'Without notes, give sqrt(81) and name two integers that bracket sqrt(30). Report confidence before checking.',
        'Verify sqrt(196) = 14 by squaring 14, and bracket sqrt(30) by squaring 5 and 6. Say why the bracket is a bound, not an exact value.'),
    'simplifying_radical_expressions': (
        'The product rule for radicals needs nonnegative factors and does not apply to sums. A coefficient outside the radical multiplies the root, not the radicand. Leave sqrt(b) exact rather than rounding it.',
        '1. Factor 48 = 16 * 3, where 16 = 4^2 is a perfect square.\n'
        '2. sqrt(48) = sqrt(16) * sqrt(3) = 4 sqrt(3).\n'
        '3. Verify: (4 sqrt(3))^2 = 16 * 3 = 48.\n'
        '4. Check that 3 has no square factor, so the expression is fully simplified.',
        'sqrt(18) is not 9 sqrt(2): that would square to 162. Nor can sqrt(a + b) be split. Adding 2 sqrt(3) + 5 sqrt(3) gives 7 sqrt(3), not 7 sqrt(6).',
        'Without notes, simplify sqrt(75) and verify by squaring the result. Report confidence before checking.',
        'Simplify sqrt(98) by factoring out 49, then again by factoring out 2 before 49. Show both give 7 sqrt(2) and square it to confirm.'),
    'rational_exponents': (
        'The denominator n is the root index and the numerator m is the power. For a negative base, even roots are not real, so the domain is restricted to a >= 0 in that case. The rules (a^p)^q = a^(pq) and a^p a^q = a^(p+q) still hold.',
        '1. For 27^(2/3), take the cube root first: 27^(1/3) = 3.\n'
        '2. Square the result: 3^2 = 9.\n'
        '3. Check the other order: 27^2 = 729, and the cube root of 729 is 9.\n'
        '4. Confirm with the exponent rule: (27^(1/3))^2 = 27^(2/3).',
        '8^(2/3) is not 8 * 2/3, and it is not 8^2 / 3. Also a^(1/2) + a^(1/2) = 2 sqrt(a), not sqrt(2a).',
        'Without notes, evaluate 16^(3/4) and write sqrt(x^3) using a rational exponent. Report confidence before checking.',
        'Evaluate 32^(2/5) by taking the fifth root then squaring, and by squaring then taking the fifth root. Confirm both give 4.'),
    'estimating_and_locating_irrational_numbers': (
        'A rational number has a terminating or repeating decimal; an irrational one does not. Bracketing gives a rigorous bound without needing an exact decimal. Every irrational still has one definite position on the number line.',
        '1. To bracket sqrt(7), note 2^2 = 4 and 3^2 = 9, so 2 < sqrt(7) < 3.\n'
        '2. Try tenths: 2.6^2 = 6.76 and 2.7^2 = 7.29, so 2.6 < sqrt(7) < 2.7.\n'
        '3. Try hundredths: 2.64^2 = 6.9696 and 2.65^2 = 7.0225, so the root lies between them.\n'
        '4. Check the final bound by squaring 2.64 and 2.65 again; both squares straddle 7, so the bracketing is verified. The interval can be narrowed indefinitely, which is why the decimal never terminates.',
        'A long decimal display is not evidence that a number is irrational: 1/7 also has a long, repeating expansion. And sqrt(2) is not equal to 1.414; that is a bound, not an identity.',
        'Without notes, bracket sqrt(19) between consecutive integers and then between tenths. Report confidence before checking.',
        'Bracket sqrt(19) by squaring 4 and 5, then by squaring 4.3 and 4.4. Compare with a calculator estimate and say which of your bounds is rigorous.'),
    'scientific_notation': (
        'The coefficient keeps exactly one nonzero digit before the decimal point. A negative exponent means a magnitude smaller than 1, not a negative number. Multiplying powers of ten adds exponents; dividing subtracts them.',
        '1. To write 0.00075 in scientific notation, move the decimal four places right to get 7.5.\n'
        '2. Each move divides by 10, so compensate with 10^(-4): 0.00075 = 7.5 * 10^(-4).\n'
        '3. Check: 7.5 * 0.0001 = 0.00075.\n'
        '4. Multiply by 2 * 10^6: (7.5 * 2) * 10^(-4+6) = 15 * 10^2 = 1.5 * 10^3.',
        '35 * 10^4 is not scientific notation because the coefficient is at least 10. And 10^(-3) is 0.001, not -1000. Adding exponents when dividing is wrong.',
        'Without notes, write 0.000032 in scientific notation and give the value of 10^(-4). Report confidence before checking.',
        'Convert 6.0 * 10^(-3) back to a decimal by moving the point three places, then verify by multiplying 6.0 by 0.001. Check (3 * 10^5)(2 * 10^(-2)) = 6 * 10^3.'),
}

#: Three diagnosis rules per concept, one per distractor, in the same order the
#: question builder supplies them. Each names the error and a concrete next check.
RULES: dict[str, list[tuple[str, str, str]]] = {
    'integer_exponents': [
        ('conceptual', 'The exponent may have been treated as a multiplier rather than a count of factors.', 'Write out all n factors and multiply them.'),
        ('procedural', 'One factor too many may have been included.', 'Count the factors explicitly and compare with the exponent.'),
        ('calculation', 'The repeated product may have been compounded with an extra addition.', 'Recompute the product step by step with no additions.'),
    ],
    'zero_and_negative_exponents': [
        ('conceptual', 'The reciprocal may have been read as a negative number.', 'Check the sign: a positive base raised to any integer power stays positive.'),
        ('procedural', 'The exponent may have been reduced by one before taking the reciprocal.', 'Write a^(-n) as 1/a^n and count n.'),
        ('conceptual', 'The negative sign may have been applied to the value instead of the exponent.', 'Compare -2^3 with 2^(-3) on a number line.'),
    ],
    'power_of_a_power_and_power_of_a_product': [
        ('procedural', 'The outer exponent may have been ignored.', 'Write the base a^m exactly n times.'),
        ('procedural', 'The exponents may have been added instead of multiplied.', 'Count total copies of the base in the expansion.'),
        ('conceptual', 'The exponent may have been applied only to the numeric coefficient.', 'Expand (ab)^n and check that both a and b appear n times.'),
    ],
    'square_roots_and_perfect_squares': [
        ('procedural', 'The root may have been doubled instead of squared.', 'Square the candidate root and compare with the radicand.'),
        ('conceptual', 'The radicand may have been returned unchanged.', 'Ask what number squared gives the radicand.'),
        ('calculation', 'The lower neighbouring square may have been used.', 'Square the two neighbouring integers and compare bounds.'),
    ],
    'simplifying_radical_expressions': [
        ('procedural', 'The square factor may have been moved outside without taking its root.', 'Take sqrt of the square factor before writing the coefficient.'),
        ('conceptual', 'Only part of the square factor may have been extracted.', 'Factor the radicand completely into primes first.'),
        ('calculation', 'The radicand may have been left unsimplified.', 'Look for the largest perfect-square factor.'),
    ],
    'rational_exponents': [
        ('procedural', 'The root may have been taken without applying the numerator power.', 'Apply the root first, then raise to the numerator.'),
        ('conceptual', 'The base may have been returned unchanged.', 'Rewrite a^(m/n) as (nth root of a)^m.'),
        ('calculation', 'The numerator power may have been applied to the wrong value.', 'Compute the root as an integer before squaring it.'),
    ],
    'estimating_and_locating_irrational_numbers': [
        ('procedural', 'The lower square may have been used as the bracket.', 'Square both candidate bounds before comparing.'),
        ('procedural', 'The bracket may have been shifted upward by one.', 'Compare the radicand with both squared bounds.'),
        ('conceptual', 'The bound may have been widened without squaring.', 'Find two consecutive integers whose squares enclose the radicand.'),
    ],
    'scientific_notation': [
        ('conceptual', 'The sign of the exponent may have been reversed.', 'Check whether the magnitude is larger or smaller than 1.'),
        ('procedural', 'The coefficient may not have been normalised to [1, 10).', 'Move the decimal point until one nonzero digit remains before it.'),
        ('calculation', 'The decimal point may have moved one place too far.', 'Count the places and verify by multiplying back.'),
    ],
}


def build_questions(add: Callable[..., None]) -> None:
    """Register four hand-checked variants per concept through the shared ``add``.

    ``add`` raises on duplicate choices, so every variant is guaranteed to have
    four distinct options; the answers below were verified arithmetically.
    """
    for v in range(4):
        n = v + 2
        add('integer_exponents', v,
            f'Write 3^{n} as a repeated product and evaluate it.',
            3 ** n, [3 * n, 3 ** (n + 1), 3 ** n + 3 * n],
            f'3^{n} is n copies of 3 multiplied: {3 ** n}. The value 3 * {n} = {3 * n} is a different operation.',
            'exponent_count_cross_check')
        add('zero_and_negative_exponents', v,
            f'Write 2^(-{n}) as a fraction in lowest terms.',
            Fraction(1, 2 ** n), [-2 ** n, Fraction(1, 2 ** (n - 1)), -Fraction(1, 2 ** n)],
            f'2^(-{n}) = 1/2^{n} = {Fraction(1, 2 ** n)}. It is positive; -2^{n} = {-2 ** n} is different.',
            'reciprocal_cross_check')
        add('power_of_a_power_and_power_of_a_product', v,
            f'Simplify (2^{n})^2 to a single number.',
            2 ** (2 * n), [2 ** n, 2 ** (3 * n), 2 * 2 ** n],
            f'(2^{n})^2 has {2 * n} factors of 2, so it is 2^{2 * n} = {2 ** (2 * n)}.',
            'power_of_power_cross_check')
        k = n + 5
        add('square_roots_and_perfect_squares', v,
            f'Find the principal square root of {k * k}.',
            k, [2 * k, k * k, k - 1],
            f'sqrt({k * k}) = {k} because {k}^2 = {k * k} and {k} >= 0.',
            'principal_root_cross_check')
        s = n + 1
        add('simplifying_radical_expressions', v,
            f'Simplify sqrt({2 * s * s}) completely.',
            f'{s} sqrt(2)', [f'{s * s} sqrt(2)', f'{2 * s} sqrt(2)', str(2 * s * s)],
            f'sqrt({2 * s * s}) = sqrt({s}^2 * 2) = {s} sqrt(2); squaring gives {2 * s * s}.',
            'radical_cross_check')
        b = n
        add('rational_exponents', v,
            f'Evaluate {b ** 3}^(2/3).',
            b ** 2, [b, b ** 3, b ** 2 + b],
            f'The cube root of {b ** 3} is {b}, and {b}^2 = {b ** 2}.',
            'rational_exponent_cross_check')
        t = n + 1
        a = t * t + 3
        add('estimating_and_locating_irrational_numbers', v,
            f'Between which two consecutive integers does sqrt({a}) lie? Give the pair.',
            f'{t} and {t + 1}', [f'{t - 1} and {t}', f'{t + 1} and {t + 2}', f'{t} and {t + 2}'],
            f'{t}^2 = {t * t} < {a} < {(t + 1) ** 2} = {(t + 1) ** 2}, so {t} < sqrt({a}) < {t + 1}.',
            'bracket_cross_check', 90)
        decimal = '0.' + '0' * (n - 1) + str(n + 1)
        add('scientific_notation', v,
            f'Write {decimal} in scientific notation.',
            f'{n + 1} x 10^-{n}',
            [f'{n + 1} x 10^{n}', f'{10 * (n + 1)} x 10^-{n + 1}', f'{n + 1} x 10^-{n + 1}'],
            f'The decimal point moves {n} places right, so {decimal} = {n + 1} x 10^-{n}.',
            'notation_cross_check')


def register() -> dict[str, Any]:
    """Return everything ``curriculum.py`` needs, plus a self-check of the shape."""
    assert set(TARGETS) == {s[0] for s in SPECS} == set(DETAILS) == set(RULES)
    for cid, detail in DETAILS.items():
        assert len(detail) == 5 and all(isinstance(x, str) and x.strip() for x in detail), cid
        assert '1.' in detail[1] and '4.' in detail[1], f'{cid} worked example lacks numbered steps'
    return {'specs': SPECS, 'details': DETAILS, 'rules': RULES,
            'targets': TARGETS, 'build_questions': build_questions}
