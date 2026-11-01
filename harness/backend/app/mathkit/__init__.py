"""A symbolic mathematics engine for generated interactive content.

Modules
-------
``expression``  parse, evaluate, simplify and differentiate an expression safely
``polynomial``  normalise to coefficients, exact roots, factoring
``simulate``    turn a declarative spec into a complete renderable payload
``templates``   derive a spec for any concept from its classification

Nothing here calls ``eval`` or ``exec``. Expressions are parsed into an AST whose
node kinds are a closed set, so a curriculum author (or a generated template) can
supply a formula without gaining any ability to run code.
"""

from .expression import (MathSyntaxError, Node, derivative, evaluate, parse, simplify,
                         substitute, to_latex, to_string)
from .polynomial import Poly, from_ast, from_expression, real_roots, to_ast
from .simulate import SCENE_KINDS, Mark, Parameter, Part, SimulationSpec, build
from .templates import available_templates, template_for

__all__ = ['MathSyntaxError', 'Node', 'parse', 'evaluate', 'simplify', 'substitute', 'derivative',
           'to_string', 'to_latex', 'Poly', 'from_ast', 'from_expression', 'real_roots',
           'to_ast', 'Parameter', 'Part', 'Mark', 'SimulationSpec', 'SCENE_KINDS', 'build',
           'template_for', 'available_templates']
