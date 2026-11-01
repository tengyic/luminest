"""Polynomial normalisation, exact roots and factoring.

Normalising an expression to coefficients does two things the raw AST cannot:
it collects like terms (``x + 3 + x + 2`` becomes ``2x + 5``), and it makes exact
roots available for linear and quadratic equations instead of numeric guesses.

A polynomial is represented as ``{exponent: coefficient}`` with zero coefficients
dropped. ``None`` means "this expression is not a polynomial in the variable",
which is the honest answer for ``sin(x)`` or ``1/x``.
"""

from __future__ import annotations

import math
from fractions import Fraction
from typing import Iterable, Mapping

from .expression import MathSyntaxError, Node, _number, parse, to_string

Poly = dict[int, float]


def _clean(poly: Poly) -> Poly:
    return {power: coefficient for power, coefficient in poly.items() if coefficient != 0}


def constant(value: float) -> Poly:
    return _clean({0: float(value)})


def variable() -> Poly:
    return {1: 1.0}


def from_ast(node: Node, name: str = 'x') -> Poly | None:
    """Convert ``node`` to a polynomial in ``name``, or ``None`` if it is not one."""
    kind = node[0]
    if kind == 'num':
        return constant(node[1])
    if kind == 'var':
        return variable() if node[1] == name else None
    if kind == 'neg':
        inner = from_ast(node[1], name)
        return None if inner is None else _clean({p: -c for p, c in inner.items()})
    if kind in ('add', 'sub', 'mul'):
        left, right = from_ast(node[1], name), from_ast(node[2], name)
        if left is None or right is None:
            return None
        if kind == 'add':
            return add(left, right)
        if kind == 'sub':
            return sub(left, right)
        return multiply(left, right)
    if kind == 'div':
        left, right = from_ast(node[1], name), from_ast(node[2], name)
        if left is None or right is None:
            return None
        # Only division by a nonzero constant stays polynomial.
        if set(right) - {0}:
            return None
        divisor = right.get(0, 0.0)
        if divisor == 0:
            return None
        return _clean({p: c / divisor for p, c in left.items()})
    if kind == 'pow':
        base, exponent = from_ast(node[1], name), node[2]
        if base is None or exponent[0] != 'num':
            return None
        power = exponent[1]
        if power != int(power) or power < 0 or power > 12:
            return None
        result = constant(1.0)
        for _ in range(int(power)):
            result = multiply(result, base)
        return result
    return None


def add(left: Poly, right: Poly) -> Poly:
    result = dict(left)
    for power, coefficient in right.items():
        result[power] = result.get(power, 0.0) + coefficient
    return _clean(result)


def sub(left: Poly, right: Poly) -> Poly:
    return add(left, {p: -c for p, c in right.items()})


def multiply(left: Poly, right: Poly) -> Poly:
    result: Poly = {}
    for power_a, coefficient_a in left.items():
        for power_b, coefficient_b in right.items():
            power = power_a + power_b
            result[power] = result.get(power, 0.0) + coefficient_a * coefficient_b
    return _clean(result)


def scale(poly: Poly, factor: float) -> Poly:
    return _clean({p: c * factor for p, c in poly.items()})


def derivative(poly: Poly) -> Poly:
    return _clean({p - 1: c * p for p, c in poly.items() if p > 0})


def degree(poly: Poly) -> int:
    return max(poly) if poly else -1


def leading(poly: Poly) -> float:
    return poly.get(degree(poly), 0.0)


def coefficients(poly: Poly, descending: bool = True) -> list[float]:
    """Coefficients including zeros, highest degree first by default."""
    top = degree(poly)
    if top < 0:
        return [0.0]
    powers = range(top, -1, -1) if descending else range(0, top + 1)
    return [poly.get(power, 0.0) for power in powers]


def evaluate(poly: Poly, value: float) -> float:
    total = 0.0
    for power, coefficient in poly.items():
        total += coefficient * (value ** power)
    return total


def to_ast(poly: Poly) -> Node:
    """Render a polynomial back to an AST, highest degree first."""
    if not poly:
        return _number(0)
    terms: Node | None = None
    for power in sorted(poly, reverse=True):
        coefficient = poly[power]
        if coefficient == 0:
            continue
        if power == 0:
            term: Node = _number(abs(coefficient))
        else:
            magnitude = abs(coefficient)
            base: Node = ('var', 'x') if power == 1 else ('pow', ('var', 'x'), _number(power))
            term = base if magnitude == 1 else ('mul', _number(magnitude), base)
        if terms is None:
            terms = ('neg', term) if coefficient < 0 else term
        else:
            terms = ('add' if coefficient > 0 else 'sub', terms, term)
    return terms if terms is not None else _number(0)


def describe(poly: Poly) -> str:
    return to_string(to_ast(poly))


# --------------------------------------------------------------------------- roots


def real_roots(poly: Poly) -> list[float]:
    """Exact real roots for degree <= 2, numeric roots for higher degrees."""
    top = degree(poly)
    if top <= 0:
        return []
    if top == 1:
        a, b = poly.get(1, 0.0), poly.get(0, 0.0)
        return [-b / a] if a else []
    if top == 2:
        a, b, c = poly.get(2, 0.0), poly.get(1, 0.0), poly.get(0, 0.0)
        discriminant = b * b - 4 * a * c
        if discriminant < 0:
            return []
        if discriminant == 0:
            return [-b / (2 * a)]
        root = math.sqrt(discriminant)
        return sorted([(-b - root) / (2 * a), (-b + root) / (2 * a)])
    return _numeric_roots(poly)


def complex_roots(poly: Poly) -> list[complex]:
    top = degree(poly)
    if top == 2:
        a, b, c = poly.get(2, 0.0), poly.get(1, 0.0), poly.get(0, 0.0)
        discriminant = b * b - 4 * a * c
        if discriminant >= 0:
            root = math.sqrt(discriminant)
            return [(-b - root) / (2 * a), (-b + root) / (2 * a)]
        imaginary = math.sqrt(-discriminant) / (2 * a)
        return [complex(-b / (2 * a), -imaginary), complex(-b / (2 * a), imaginary)]
    return [complex(root) for root in real_roots(poly)]


def discriminant(poly: Poly) -> float | None:
    if degree(poly) != 2:
        return None
    return poly.get(1, 0.0) ** 2 - 4 * poly.get(2, 0.0) * poly.get(0, 0.0)


def vertex(poly: Poly) -> tuple[float, float] | None:
    """Vertex of a quadratic, or ``None`` when the degree is not 2."""
    if degree(poly) != 2:
        return None
    a, b, c = poly.get(2, 0.0), poly.get(1, 0.0), poly.get(0, 0.0)
    if a == 0:
        return None
    x = -b / (2 * a)
    return x, evaluate(poly, x)


def _numeric_roots(poly: Poly, samples: int = 2000, span: float = 50.0) -> list[float]:
    """Scan for sign changes then refine with bisection. Reports real roots only."""
    found: list[float] = []
    previous_x, previous_y = -span, evaluate(poly, -span)
    step = (2 * span) / samples
    for index in range(1, samples + 1):
        x = -span + index * step
        y = evaluate(poly, x)
        if y == 0:
            found.append(x)
        elif previous_y == 0:
            found.append(previous_x)
        elif previous_y * y < 0:
            found.append(_bisect(poly, previous_x, x))
        previous_x, previous_y = x, y
    unique: list[float] = []
    for root in sorted(found):
        if not unique or abs(root - unique[-1]) > 1e-7:
            unique.append(root)
    return unique


def _bisect(poly: Poly, low: float, high: float, iterations: int = 80) -> float:
    low_value = evaluate(poly, low)
    for _ in range(iterations):
        middle = (low + high) / 2
        middle_value = evaluate(poly, middle)
        if middle_value == 0:
            return middle
        if low_value * middle_value < 0:
            high = middle
        else:
            low, low_value = middle, middle_value
    return (low + high) / 2


# --------------------------------------------------------------------------- factoring


def factor_quadratic(poly: Poly) -> tuple[float, float] | None:
    """Return the two real roots of a quadratic, or ``None`` when none are real."""
    if degree(poly) != 2:
        return None
    roots = real_roots(poly)
    return (roots[0], roots[1]) if len(roots) == 2 else None


def integer_factorisation(a: int, b: int, c: int) -> tuple[int, int] | None:
    """Find integers r, s with r + s = b and r·s = c for a monic quadratic."""
    if a != 1:
        return None
    for candidate in range(-abs(c) - 1, abs(c) + 2):
        if candidate == 0:
            if b == 0 and c == 0:
                return (0, 0)
            continue
        if c % candidate == 0 and candidate + c // candidate == b:
            return (candidate, c // candidate)
    return None


def exact_coefficients(poly: Poly) -> list[Fraction]:
    """Coefficients as exact fractions when they are rational."""
    return [Fraction(value).limit_denominator(10000) for value in coefficients(poly)]


def from_expression(text: str, name: str = 'x') -> Poly | None:
    """Parse ``text`` and normalise it to a polynomial, if possible."""
    try:
        return from_ast(parse(text, variables=(name,)), name)
    except MathSyntaxError:
        return None


def like_terms(node: Node, name: str = 'x') -> Node:
    """Normalise an AST to collected like terms, falling back to the original."""
    poly = from_ast(node, name)
    return to_ast(poly) if poly is not None else node
