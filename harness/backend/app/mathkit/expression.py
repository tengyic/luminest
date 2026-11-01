"""A small, safe symbolic expression engine.

Deliberately dependency-free. ``sympy`` would be more capable but it is a large
frozen-bundle cost for the operations this product actually needs: evaluate,
differentiate, simplify, solve, and plot. A hand-written engine also means the
supported surface is exactly the surface we can reason about, and there is no
``eval`` anywhere in the request path.

Grammar (lowest precedence first)::

    expression := term (('+' | '-') term)*
    term       := unary (('*' | '/') unary)*
    unary      := ('-' | '+') unary | power
    power      := atom ('^' unary)?          # right associative
    atom       := number | identifier | call | '(' expression ')'
    call       := identifier '(' expression (',' expression)* ')'

Implicit multiplication is supported (``2x``, ``3(x+1)``, ``x(x+2)``), because that
is how the curriculum writes formulas.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

#: AST node: a tuple whose first element is the node kind.
Node = tuple

MAX_NODES = 4000
MAX_DEPTH = 60

CONSTANTS: dict[str, float] = {'pi': math.pi, 'e': math.e, 'tau': math.tau}


def _whole(value: float) -> int | None:
    """``value`` as an int when it is a non-negative whole number, else ``None``.

    Counting functions are defined on the natural numbers only. Silently flooring
    ``3.7`` to ``3!`` would let a continuous slider produce a plausible-looking but
    meaningless count, which is worse than a gap in the curve.
    """
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    if value < 0 or abs(value - round(value)) > 1e-9:
        return None
    return int(round(value))


def _factorial(n: float) -> float:
    whole = _whole(n)
    return _nan() if whole is None else float(math.factorial(whole))


def _choose(n: float, r: float) -> float:
    """``nCr`` — 0 outside ``0 <= r <= n``, which is the counting convention."""
    top, bottom = _whole(n), _whole(r)
    if top is None or bottom is None:
        return _nan()
    if bottom > top:
        return 0.0
    return float(math.comb(top, bottom))


def _permute(n: float, r: float) -> float:
    """``nPr = n! / (n - r)!`` — 0 outside ``0 <= r <= n``."""
    top, bottom = _whole(n), _whole(r)
    if top is None or bottom is None:
        return _nan()
    if bottom > top:
        return 0.0
    return float(math.perm(top, bottom))


FUNCTIONS: dict[str, tuple[int, Any]] = {
    'fact': (1, _factorial),
    'choose': (2, _choose),
    'permute': (2, _permute),
    'sqrt': (1, lambda a: math.sqrt(a) if a >= 0 else _nan()),
    'abs': (1, abs),
    'exp': (1, math.exp),
    'ln': (1, lambda a: math.log(a) if a > 0 else _nan()),
    'log': (1, lambda a: math.log(a) if a > 0 else _nan()),
    'log10': (1, lambda a: math.log10(a) if a > 0 else _nan()),
    'log2': (1, lambda a: math.log2(a) if a > 0 else _nan()),
    'sin': (1, math.sin),
    'cos': (1, math.cos),
    'tan': (1, math.tan),
    'asin': (1, lambda a: math.asin(a) if -1 <= a <= 1 else _nan()),
    'acos': (1, lambda a: math.acos(a) if -1 <= a <= 1 else _nan()),
    'atan': (1, math.atan),
    'floor': (1, math.floor),
    'ceil': (1, math.ceil),
    'round': (1, lambda a: float(round(a))),
    'sign': (1, lambda a: (a > 0) - (a < 0)),
    'min': (2, min),
    'max': (2, max),
    'pow': (2, lambda a, b: a ** b),
    'hypot': (2, math.hypot),
}

#: Derivative rules for the single-argument functions above.
_DERIVATIVES: dict[str, str] = {
    'sqrt': '1/(2*sqrt(u))', 'abs': 'sign(u)', 'exp': 'exp(u)', 'ln': '1/u', 'log': '1/u',
    'log10': '1/(u*ln(10))', 'log2': '1/(u*ln(2))', 'sin': 'cos(u)', 'cos': '-sin(u)',
    'tan': '1/(cos(u)^2)', 'asin': '1/sqrt(1-u^2)', 'acos': '-1/sqrt(1-u^2)',
    'atan': '1/(1+u^2)', 'sign': '0', 'floor': '0', 'ceil': '0', 'round': '0',
    # Counting is defined on whole numbers only, so it is locally constant. Declaring the
    # zero derivative keeps it out of the generic fall-through in ``derivative``.
    'fact': '0',
}


class MathSyntaxError(ValueError):
    """The expression could not be parsed."""


def _nan() -> float:
    return float('nan')


# --------------------------------------------------------------------------- lexer

_TOKEN_NUMBER = 'number'
_TOKEN_NAME = 'name'
_TOKEN_OP = 'op'

#: Typographic characters that mean the same as an ASCII operator.
_OPERATOR_ALIASES: dict[str, str] = {
    '\u00b7': '*',   # middle dot
    '\u22c5': '*',   # dot operator
    '\u00d7': '*',   # multiplication sign
    '\u2212': '-',   # minus sign
    '\u2013': '-',   # en dash
    '\u2014': '-',   # em dash
    '\u00f7': '/',   # division sign
    '\u2044': '/',   # fraction slash
}


def tokenize(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    index, length = 0, len(text)
    while index < length:
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char.isdigit() or (char == '.' and index + 1 < length and text[index + 1].isdigit()):
            start = index
            while index < length and (text[index].isdigit() or text[index] == '.'):
                index += 1
            # Scientific notation: 1e-3, 2.5E6
            if index < length and text[index] in 'eE':
                probe = index + 1
                if probe < length and text[probe] in '+-':
                    probe += 1
                if probe < length and text[probe].isdigit():
                    index = probe
                    while index < length and text[index].isdigit():
                        index += 1
            tokens.append((_TOKEN_NUMBER, text[start:index]))
            continue
        if char.isalpha() or char == '_':
            start = index
            while index < length and (text[index].isalnum() or text[index] == '_'):
                index += 1
            tokens.append((_TOKEN_NAME, text[start:index]))
            continue
        if text.startswith('**', index):
            tokens.append((_TOKEN_OP, '^'))
            index += 2
            continue
        # Typographic operators. ``to_string`` renders a true minus sign and a middle
        # dot, so the engine has to be able to read back what it printed; the same
        # characters also arrive when a formula is pasted out of the UI or a document.
        folded = _OPERATOR_ALIASES.get(char)
        if folded is not None:
            tokens.append((_TOKEN_OP, folded))
            index += 1
            continue
        if char in '+-*/^(),':
            tokens.append((_TOKEN_OP, char))
            index += 1
            continue
        raise MathSyntaxError(f'Unexpected character {char!r} in expression')
    return tokens


# --------------------------------------------------------------------------- parser


class _Parser:
    def __init__(self, tokens: Sequence[tuple[str, str]], variables: Iterable[str] = ('x',)):
        self.tokens = list(tokens)
        self.position = 0
        self.variables = set(variables)
        self.count = 0

    def peek(self) -> tuple[str, str] | None:
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def take(self) -> tuple[str, str]:
        token = self.peek()
        if token is None:
            raise MathSyntaxError('Unexpected end of expression')
        self.position += 1
        return token

    def node(self, kind: str, *children: Any) -> Node:
        self.count += 1
        if self.count > MAX_NODES:
            raise MathSyntaxError('Expression is too large')
        return (kind, *children)

    def parse(self) -> Node:
        result = self.expression()
        if self.peek() is not None:
            raise MathSyntaxError(f'Unexpected token {self.peek()[1]!r}')
        return result

    def expression(self) -> Node:
        node = self.term()
        while True:
            token = self.peek()
            if token is None or token[0] != _TOKEN_OP or token[1] not in '+-':
                return node
            self.take()
            right = self.term()
            node = self.node('add' if token[1] == '+' else 'sub', node, right)

    def term(self) -> Node:
        node = self.unary()
        while True:
            token = self.peek()
            if token is None:
                return node
            if token[0] == _TOKEN_OP and token[1] in '*/':
                self.take()
                right = self.unary()
                node = self.node('mul' if token[1] == '*' else 'div', node, right)
                continue
            # Implicit multiplication: 2x, 3(x+1), x(x+2), 2sin(x)
            if token[0] == _TOKEN_NUMBER or (token[0] == _TOKEN_NAME) or (
                    token[0] == _TOKEN_OP and token[1] == '('):
                right = self.unary()
                node = self.node('mul', node, right)
                continue
            return node

    def unary(self) -> Node:
        token = self.peek()
        if token is not None and token[0] == _TOKEN_OP and token[1] in '+-':
            self.take()
            operand = self.unary()
            return self.node('neg', operand) if token[1] == '-' else operand
        return self.power()

    def power(self) -> Node:
        base = self.atom()
        token = self.peek()
        if token is not None and token[0] == _TOKEN_OP and token[1] == '^':
            self.take()
            exponent = self.unary()  # right associative
            return self.node('pow', base, exponent)
        return base

    def atom(self) -> Node:
        token = self.take()
        kind, value = token
        if kind == _TOKEN_NUMBER:
            return self.node('num', float(value))
        if kind == _TOKEN_NAME:
            if self.peek() is not None and self.peek()[1] == '(' and self.peek()[0] == _TOKEN_OP:
                return self.call(value)
            if value in CONSTANTS:
                return self.node('num', CONSTANTS[value])
            if value in self.variables:
                return self.node('var', value)
            raise MathSyntaxError(f'Unknown name {value!r}')
        if kind == _TOKEN_OP and value == '(':
            inner = self.expression()
            closing = self.take()
            if closing[1] != ')':
                raise MathSyntaxError('Missing closing parenthesis')
            return inner
        raise MathSyntaxError(f'Unexpected token {value!r}')

    def call(self, name: str) -> Node:
        if name not in FUNCTIONS:
            raise MathSyntaxError(f'Unknown function {name!r}')
        self.take()  # consume '('
        arguments: list[Node] = []
        if self.peek() is not None and self.peek()[1] != ')':
            arguments.append(self.expression())
            while self.peek() is not None and self.peek()[1] == ',':
                self.take()
                arguments.append(self.expression())
        closing = self.take()
        if closing[1] != ')':
            raise MathSyntaxError('Missing closing parenthesis in function call')
        arity, _ = FUNCTIONS[name]
        if len(arguments) != arity:
            raise MathSyntaxError(f'{name} expects {arity} argument(s), received {len(arguments)}')
        return self.node('call', name, tuple(arguments))


def parse(text: str, variables: Iterable[str] = ('x',)) -> Node:
    """Parse ``text`` into an AST, raising :class:`MathSyntaxError` if malformed."""
    if not isinstance(text, str) or not text.strip():
        raise MathSyntaxError('Expression is empty')
    if len(text) > 2000:
        raise MathSyntaxError('Expression is too long')
    return _Parser(tokenize(text), variables).parse()


def depth(node: Node, _seen: int = 0) -> int:
    if _seen > MAX_DEPTH:
        raise MathSyntaxError('Expression is nested too deeply')
    kind = node[0]
    if kind in ('num', 'var'):
        return 1
    children: Iterable[Node]
    if kind == 'call':
        children = node[2]
    else:
        children = node[1:]
    return 1 + max((depth(child, _seen + 1) for child in children), default=0)


# --------------------------------------------------------------------------- evaluate


def evaluate(node: Node, env: Mapping[str, float] | None = None) -> float:
    """Evaluate ``node`` in ``env``. Returns NaN where the expression is undefined."""
    env = env or {}
    kind = node[0]
    if kind == 'num':
        return float(node[1])
    if kind == 'var':
        value = env.get(node[1])
        if value is None:
            raise MathSyntaxError(f'No value supplied for {node[1]!r}')
        return float(value)
    if kind == 'neg':
        return -evaluate(node[1], env)
    if kind == 'add':
        return evaluate(node[1], env) + evaluate(node[2], env)
    if kind == 'sub':
        return evaluate(node[1], env) - evaluate(node[2], env)
    if kind == 'mul':
        return evaluate(node[1], env) * evaluate(node[2], env)
    if kind == 'div':
        numerator, denominator = evaluate(node[1], env), evaluate(node[2], env)
        return _nan() if denominator == 0 else numerator / denominator
    if kind == 'pow':
        base, exponent = evaluate(node[1], env), evaluate(node[2], env)
        try:
            result = base ** exponent
        except (OverflowError, ZeroDivisionError, ValueError):
            return _nan()
        return float(result) if isinstance(result, (int, float)) and math.isfinite(result) else _nan()
    if kind == 'call':
        name, arguments = node[1], node[2]
        values = [evaluate(argument, env) for argument in arguments]
        if any(not math.isfinite(value) for value in values):
            return _nan()
        try:
            return float(FUNCTIONS[name][1](*values))
        except (ValueError, ZeroDivisionError, OverflowError):
            return _nan()
    raise MathSyntaxError(f'Unknown node {kind!r}')


# --------------------------------------------------------------------------- simplify


def _number(value: float) -> Node:
    return ('num', float(value))


def simplify(node: Node) -> Node:
    """Constant-fold and apply the algebraic identities a learner would apply."""
    kind = node[0]
    if kind in ('num', 'var'):
        return node
    if kind == 'neg':
        inner = simplify(node[1])
        if inner[0] == 'num':
            return _number(-inner[1])
        if inner[0] == 'neg':
            return inner[1]
        return ('neg', inner)
    if kind == 'call':
        arguments = tuple(simplify(argument) for argument in node[2])
        if all(argument[0] == 'num' for argument in arguments):
            try:
                return _number(float(FUNCTIONS[node[1]][1](*[a[1] for a in arguments])))
            except (ValueError, ZeroDivisionError, OverflowError):
                return ('call', node[1], arguments)
        return ('call', node[1], arguments)

    left, right = simplify(node[1]), simplify(node[2])
    both_numbers = left[0] == 'num' and right[0] == 'num'
    if both_numbers:
        try:
            return _number(evaluate((kind, left, right)))
        except MathSyntaxError:
            return (kind, left, right)

    if kind == 'add':
        if left[0] == 'num' and left[1] == 0:
            return right
        if right[0] == 'num' and right[1] == 0:
            return left
    if kind == 'sub':
        if right[0] == 'num' and right[1] == 0:
            return left
        if left == right:
            return _number(0)
    if kind == 'mul':
        if (left[0] == 'num' and left[1] == 0) or (right[0] == 'num' and right[1] == 0):
            return _number(0)
        if left[0] == 'num' and left[1] == 1:
            return right
        if right[0] == 'num' and right[1] == 1:
            return left
        if left[0] == 'num' and right[0] == 'num':
            return _number(left[1] * right[1])
    if kind == 'div':
        if left[0] == 'num' and left[1] == 0:
            return _number(0)
        if right[0] == 'num' and right[1] == 1:
            return left
    if kind == 'pow':
        if right[0] == 'num' and right[1] == 0:
            return _number(1)
        if right[0] == 'num' and right[1] == 1:
            return left
    return (kind, left, right)


# --------------------------------------------------------------------------- derivative


def derivative(node: Node, variable: str = 'x') -> Node:
    """Symbolic derivative with respect to ``variable``."""
    kind = node[0]
    if kind == 'num':
        return _number(0)
    if kind == 'var':
        return _number(1) if node[1] == variable else _number(0)
    if kind == 'neg':
        return ('neg', derivative(node[1], variable))
    if kind == 'add':
        return ('add', derivative(node[1], variable), derivative(node[2], variable))
    if kind == 'sub':
        return ('sub', derivative(node[1], variable), derivative(node[2], variable))
    if kind == 'mul':
        left, right = node[1], node[2]
        return ('add',
                ('mul', derivative(left, variable), right),
                ('mul', left, derivative(right, variable)))
    if kind == 'div':
        numerator, denominator = node[1], node[2]
        return ('div',
                ('sub', ('mul', derivative(numerator, variable), denominator),
                        ('mul', numerator, derivative(denominator, variable))),
                ('pow', denominator, _number(2)))
    if kind == 'pow':
        base, exponent = node[1], node[2]
        if exponent[0] == 'num':
            return ('mul',
                    ('mul', _number(exponent[1]), ('pow', base, _number(exponent[1] - 1))),
                    derivative(base, variable))
        # General case: d/dx u^v = u^v (v' ln u + v u'/u)
        return ('mul', ('pow', base, exponent),
                ('add',
                 ('mul', derivative(exponent, variable), ('call', 'ln', (base,))),
                 ('div', ('mul', exponent, derivative(base, variable)), base)))
    if kind == 'call':
        name, arguments = node[1], node[2]
        inner = arguments[0]
        inner_derivative = derivative(inner, variable)
        if name in _DERIVATIVES and len(arguments) == 1:
            outer = parse(_DERIVATIVES[name].replace('u', '(_inner)'), variables=('_inner',))
            substituted = _substitute(outer, '_inner', inner)
            return ('mul', substituted, inner_derivative)
        if name == 'min' or name == 'max':
            return ('mul', derivative(arguments[0], variable), _number(0))
    raise MathSyntaxError(f'Cannot differentiate node {kind!r}')


def _substitute(node: Node, name: str, replacement: Node) -> Node:
    kind = node[0]
    if kind == 'var':
        return replacement if node[1] == name else node
    if kind in ('num',):
        return node
    if kind == 'call':
        return ('call', node[1], tuple(_substitute(a, name, replacement) for a in node[2]))
    return (kind, *[_substitute(child, name, replacement) for child in node[1:]])


def substitute(node: Node, values: Mapping[str, float], keep: Iterable[str] = ()) -> Node:
    """Replace names by constants and fold the result.

    This is what turns a template's ``a*x^2 + b*x + c`` into a concrete
    ``x^2 + 3x - 10``. Without it, a template could declare a slider for a coefficient
    and the slider would be inert: the analysis layer only understands expressions
    whose coefficients are numbers, and an unknown name makes it give up and fall back
    to a generic description. Names in ``keep`` (normally the plot variable) survive.
    """
    frozen = set(keep)
    result = node
    for name, value in values.items():
        if name not in frozen:
            result = _substitute(result, name, _number(float(value)))
    return simplify(result)


# --------------------------------------------------------------------------- printing


def to_string(node: Node, _parent: str = '') -> str:
    """Render back to a plain-text expression, parenthesising where required.

    Parenthesisation is not cosmetic: without it ``1/(2·sqrt(x))`` would print as
    ``1/2·sqrt(x)``, which reads as a different expression.
    """
    kind = node[0]
    if kind == 'num':
        value = node[1]
        return str(int(value)) if float(value).is_integer() else f'{value:g}'
    if kind == 'var':
        return node[1]
    if kind == 'neg':
        inner = to_string(node[1], 'unary')
        return '-' + (f'({inner})' if node[1][0] in ('add', 'sub') else inner)
    if kind == 'call':
        return f'{node[1]}(' + ', '.join(to_string(a) for a in node[2]) + ')'
    if kind == 'pow':
        base = to_string(node[1], 'pow')
        # A negative base must be bracketed: "-0.5^n" reads as "-(0.5^n)", which is a
        # different function (it differs in sign at every odd exponent).
        if node[1][0] in ('add', 'sub', 'mul', 'div', 'neg') or (
                node[1][0] == 'num' and node[1][1] < 0):
            base = f'({base})'
        exponent = to_string(node[2], 'pow')
        return f'{base}^{exponent}'
    if kind == 'div':
        left = to_string(node[1], 'div')
        right = to_string(node[2], 'div')
        # A product or sum in the denominator must be bracketed.
        if node[2][0] in ('add', 'sub', 'mul', 'div'):
            right = f'({right})'
        return f'{left}/{right}'
    if kind == 'mul':
        left, right = node[1], node[2]
        # Render children without inherited context so a single explicit wrap is applied.
        left_text = to_string(left)
        right_text = to_string(right)
        if left[0] in ('add', 'sub', 'div'):
            left_text = f'({left_text})'
        if right[0] in ('add', 'sub', 'div'):
            right_text = f'({right_text})'
        if left[0] == 'num' and right[0] in ('var', 'call'):
            return f'{left_text}{right_text}'
        return f'{left_text}·{right_text}'
    if kind in ('add', 'sub'):
        # A signed second term is a subtraction: "x + -3" is written "x − 3".
        right = node[2]
        signed = (right[0] == 'num' and right[1] < 0) or right[0] == 'neg'
        if signed:
            magnitude = _number(-right[1]) if right[0] == 'num' else right[1]
            symbol = ' − ' if kind == 'add' else ' + '
            text = f'{to_string(node[1], kind)}{symbol}{to_string(magnitude, kind)}'
            return f'({text})' if _parent in ('mul', 'div', 'pow') else text
    symbol = {'add': ' + ', 'sub': ' − '}[kind]
    text = f'{to_string(node[1], kind)}{symbol}{to_string(node[2], kind)}'
    return f'({text})' if _parent in ('mul', 'div', 'pow') else text


def to_latex(node: Node, _parent: str = '') -> str:
    """Render to a compact LaTeX subset the native client can draw."""
    kind = node[0]
    if kind == 'num':
        value = node[1]
        return str(int(value)) if float(value).is_integer() else f'{value:g}'
    if kind == 'var':
        return node[1]
    if kind == 'neg':
        return '-' + to_latex(node[1], 'unary')
    if kind == 'call':
        arguments = ', '.join(to_latex(a) for a in node[2])
        if node[1] == 'sqrt':
            return f'\\sqrt{{{arguments}}}'
        if node[1] in ('abs',):
            return f'\\left|{arguments}\\right|'
        return f'\\mathrm{{{node[1]}}}\\left({arguments}\\right)'
    if kind == 'mul':
        left, right = node[1], node[2]
        if left[0] == 'num' and right[0] in ('var', 'call'):
            return f'{to_latex(left)}{to_latex(right)}'
        return f'{to_latex(left, kind)} \\cdot {to_latex(right, kind)}'
    if kind == 'div':
        return f'\\frac{{{to_latex(node[1])}}}{{{to_latex(node[2])}}}'
    if kind == 'pow':
        base = node[1]
        rendered = to_latex(base, 'pow')
        # Same reason as ``to_string``: a negative or compound base must be bracketed.
        if base[0] in ('add', 'sub', 'mul', 'div', 'neg') or (
                base[0] == 'num' and base[1] < 0):
            rendered = f'\\left({rendered}\\right)'
        return f'{rendered}^{{{to_latex(node[2])}}}'
    if kind in ('add', 'sub'):
        right = node[2]
        signed = (right[0] == 'num' and right[1] < 0) or right[0] == 'neg'
        if signed:
            magnitude = _number(-right[1]) if right[0] == 'num' else right[1]
            symbol = ' - ' if kind == 'add' else ' + '
            text = f'{to_latex(node[1], kind)}{symbol}{to_latex(magnitude, kind)}'
            return f'\\left({text}\\right)' if _parent in ('mul', 'div', 'pow') else text
    symbol = {'add': ' + ', 'sub': ' - '}[kind]
    text = f'{to_latex(node[1], kind)}{symbol}{to_latex(node[2], kind)}'
    return f'\\left({text}\\right)' if _parent in ('mul', 'div', 'pow') else text


def variables_in(node: Node) -> set[str]:
    """Every variable name appearing in ``node``."""
    kind = node[0]
    if kind == 'var':
        return {node[1]}
    if kind == 'num':
        return set()
    if kind == 'call':
        found: set[str] = set()
        for argument in node[2]:
            found |= variables_in(argument)
        return found
    found = set()
    for child in node[1:]:
        found |= variables_in(child)
    return found
