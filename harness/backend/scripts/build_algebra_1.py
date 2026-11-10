"""Build the Algebra 1 course: outline, textbook alignment, pack.

Run:  python scripts/build_algebra_1.py

The outline follows the twelve-unit Algebra 1 tutoring framework (372 skills across
12 units) as an *original* scope and sequence, dedicated to the public domain under
CC0, exactly like the other bundled outlines. No third-party curriculum text is
reproduced: unit names and topic names follow the published framework, and every
summary below is written for this project.

Textbook alignment is the part that makes the claim checkable. Each unit carries the
OpenStax sections that actually teach it, and every slug was read from the publisher's
own table of contents or verified by fetching it (HTTP 200) before being written here --
none is guessed. Only CC BY books are used as text anchors:

* ``elementary-algebra`` (1e, CC BY 4.0) -- the spine: equations, inequalities, graphing,
  systems, polynomials, factoring, rational expressions, roots, quadratics.
* ``algebra-and-trigonometry`` (1e, CC BY 4.0) -- function notation, domain and range,
  exponential functions, arithmetic and geometric sequences, quadratic functions.
* ``introductory-statistics`` (1e, CC BY 4.0) -- one-variable data, two-way tables,
  scatter plots and regression, sampling, probability.

``algebra-1`` exists in OpenStax's catalogue but reports CC BY-NC-SA 4.0, so it is
*link-only* in this project: named as a study reference, never stored or quoted.

The pack is built through the ordinary ``app.ingest.pipeline`` (the same path every
other course uses) and concept ids are namespaced with ``algebra_1_`` because concept
ids are global and several titles here also appear in the shipped courses.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND / 'scripts'))

from build_requested_courses import (  # noqa: E402
    ATTRIBUTION, MAX_ID, PACK_DIR, SCOPE, build_pack, seed_document, write_seed,
)

COURSE_ID = 'algebra_1'
TITLE = 'Algebra 1'
DESCRIPTION = (
    'A full Algebra 1 course: algebraic expression language, linear equations and '
    'inequalities, linear functions and modelling, statistics and data, systems, '
    'functions, exponents and radicals, exponential functions, polynomials and '
    'factoring, quadratic functions and quadratic equations.')

# --------------------------------------------------------------------------- outline
#
# Each unit: name, the OpenStax sections that teach it (verified slugs), and topics.
# Each topic: name and its concepts as (title, summary, keywords). Within a topic the
# concepts are ordered, and each later concept declares the previous one as a
# prerequisite; topics inside a unit are parallel entry points, and units are bridged by
# a unit-level prerequisite (see ``_course``). That keeps the graph branching instead of
# collapsing into one chain of 157 links.

UNITS: list[dict] = [
    {
        'unit': 'Foundations for Algebra 1',
        'about': ('The on-ramp: the language of algebraic expressions, evaluating them, '
                  'equivalent linear expressions, the arithmetic everything else rests on, '
                  'and unit reasoning.'),
        'sections': [
            ('elementary-algebra', '1-2-use-the-language-of-algebra'),
            ('elementary-algebra', '1-8-the-real-numbers'),
            ('elementary-algebra', '1-9-properties-of-real-numbers'),
            ('elementary-algebra', '1-10-systems-of-measurement'),
        ],
        'topics': [
            ('Algebraic Expression Language', [
                ('Variables and Expressions',
                 'A variable names a quantity that can change, and an expression combines '
                 'variables, numbers and operations without an equals sign.',
                 ['variable', 'expression', 'algebraic language']),
                ('Terms, Coefficients, and Constants',
                 'A term is a product of a number and variables; its coefficient is that '
                 'number, and a constant term contains no variable at all.',
                 ['term', 'coefficient', 'constant']),
                ('Translating Words into Expressions',
                 'A phrase such as five more than twice a number becomes 2x + 5, one '
                 'operation at a time, with order words deciding the grouping.',
                 ['translate', 'phrase', 'operation words']),
            ]),
            ('Evaluating Expressions', [
                ('Substitution and Order of Operations',
                 'Evaluating replaces each variable with a value and then applies the order '
                 'of operations, so the same expression always produces one value.',
                 ['substitution', 'order of operations', 'evaluate']),
                ('Negative and Rational Inputs',
                 'Parentheses around a substituted negative protect its sign, which is why '
                 '(-3)^2 and -3^2 are different quantities.',
                 ['negative', 'parentheses', 'substitution']),
            ]),
            ('Equivalent Linear Expressions', [
                ('Combining Like Terms',
                 'Like terms carry identical variable factors, so only their coefficients '
                 'add and the variable part is unchanged.',
                 ['like terms', 'simplify', 'coefficient']),
                ('The Distributive Property',
                 'a(b + c) = ab + ac lets a factor outside parentheses multiply every term '
                 'inside, which is the move that removes grouping.',
                 ['distributive property', 'expand', 'factor']),
                ('Testing Equivalence',
                 'Two expressions are equivalent when every substitution gives the same '
                 'value, and simplifying one into the other proves it structurally.',
                 ['equivalent expressions', 'justify', 'simplify']),
            ]),
            ('Algebra Readiness Arithmetic', [
                ('Operations with Signed Numbers',
                 'Adding, subtracting, multiplying and dividing signed numbers follows sign '
                 'rules that keep arithmetic consistent with the number line.',
                 ['integers', 'sign rules', 'arithmetic']),
                ('Fraction and Decimal Fluency',
                 'Common denominators, reciprocals and decimal place value are the '
                 'arithmetic moves every later algebraic step still depends on.',
                 ['fractions', 'decimals', 'reciprocal']),
                ('Grouping and Order of Operations',
                 'Exponents first, then multiplication and division left to right, then '
                 'addition and subtraction, with grouping symbols overriding the order.',
                 ['order of operations', 'grouping', 'precedence']),
            ]),
            ('Units and Dimensional Analysis', [
                ('Units and Unit Conversion',
                 'Multiplying by a conversion factor equal to one changes the unit without '
                 'changing the quantity, so 12 inches and 1 foot name the same length.',
                 ['unit conversion', 'conversion factor', 'measurement']),
                ('Dimensional Analysis',
                 'Carrying units through a computation shows whether the result is the '
                 'quantity the question asked for, and cancels units like factors.',
                 ['dimensional analysis', 'units', 'rate']),
                ('Precision and Reasonable Answers',
                 'A result carries the precision of its inputs, so an answer is checked '
                 'against the size and units the context implies.',
                 ['precision', 'estimation', 'reasonableness']),
            ]),
        ],
    },
    {
        'unit': 'Linear Equations',
        'about': ('Solving equations in one variable: inverse operations, multi-step '
                  'solving past structural obstacles, literal-equation rearrangement, '
                  'modelling a context with one equation, and absolute value equations.'),
        'sections': [
            ('elementary-algebra', '2-1-solve-equations-using-the-subtraction-and-addition-properties-of-equality'),
            ('elementary-algebra', '2-2-solve-equations-using-the-division-and-multiplication-properties-of-equality'),
            ('elementary-algebra', '2-3-solve-equations-with-variables-and-constants-on-both-sides'),
            ('elementary-algebra', '2-4-use-a-general-strategy-to-solve-linear-equations'),
            ('elementary-algebra', '2-5-solve-equations-with-fractions-or-decimals'),
            ('elementary-algebra', '2-6-solve-a-formula-for-a-specific-variable'),
            ('algebra-and-trigonometry', '2-7-linear-inequalities-and-absolute-value-inequalities'),
        ],
        'topics': [
            ('One-Step and Two-Step Equations', [
                ('Inverse Operations',
                 'An equation stays true when the same operation is applied to both sides, '
                 'so the inverse operation isolates the variable.',
                 ['inverse operation', 'balance', 'properties of equality']),
                ('One-Step Equations',
                 'A single inverse operation undoes the one operation attached to the '
                 'variable, whether it is addition, subtraction, multiplication or division.',
                 ['one-step', 'solve', 'isolate']),
                ('Two-Step Equations',
                 'Undo addition or subtraction first and multiplication or division second, '
                 'which reverses the order the expression was built in.',
                 ['two-step', 'solve', 'reverse order']),
            ]),
            ('Multi-Step Linear Equations', [
                ('Distributing Before Solving',
                 'Clearing parentheses first turns a multi-step equation into the two-step '
                 'form already solved, and avoids dividing by an expression.',
                 ['distribute', 'multi-step', 'simplify first']),
                ('Variables on Both Sides',
                 'Collecting variable terms on one side and constants on the other reduces '
                 'the equation to a single coefficient times the variable.',
                 ['both sides', 'collect terms', 'solve']),
                ('Fractions and Decimals in Equations',
                 'Multiplying by the least common denominator or by a power of ten clears '
                 'fractions and decimals without changing the solution set.',
                 ['clear fractions', 'decimals', 'least common denominator']),
                ('Identities and Contradictions',
                 'An equation that reduces to a true statement holds for every value, while '
                 'one that reduces to a false statement has no solution.',
                 ['identity', 'no solution', 'all real numbers']),
            ]),
            ('Literal Equations and Formulas', [
                ('Rearranging a Formula',
                 'Solving for a named variable treats the other variables as constants and '
                 'applies the same inverse operations in reverse order.',
                 ['literal equation', 'rearrange', 'formula']),
                ('Formulas in Context',
                 'A rearranged formula answers a different question about the same '
                 'relationship, such as solving d = rt for the time t.',
                 ['formula', 'solve for a variable', 'context']),
            ]),
            ('Equation Modeling', [
                ('Translating a Context into an Equation',
                 'Define the unknown, state the relationship in words, then write the '
                 'relationship symbolically with units attached to each quantity.',
                 ['model', 'define variable', 'translate']),
                ('Checking a Model Against the Context',
                 'A solution is accepted only when it satisfies the equation and makes sense '
                 'in the situation, including its sign and size.',
                 ['check', 'reasonable answer', 'model']),
            ]),
            ('Absolute Value Equations', [
                ('Absolute Value as Distance',
                 'The absolute value of x is its distance from zero, so |x| = a with a > 0 '
                 'has two solutions, x = a and x = -a.',
                 ['absolute value', 'distance', 'two cases']),
                ('Solving Absolute Value Equations',
                 'Isolate the absolute value first, then split into the positive and '
                 'negative cases and reject any solution that fails the original equation.',
                 ['absolute value equation', 'cases', 'extraneous solution']),
            ]),
        ],
    },
    {
        'unit': 'Linear Inequalities',
        'about': ('Solving and graphing inequalities in one variable, including symbol '
                  'reversal, compound inequalities with interval notation, inequality '
                  'modelling and absolute value inequalities.'),
        'sections': [
            ('elementary-algebra', '2-7-solve-linear-inequalities'),
            ('elementary-algebra', '3-6-solve-applications-with-linear-inequalities'),
            ('algebra-and-trigonometry', '2-7-linear-inequalities-and-absolute-value-inequalities'),
        ],
        'topics': [
            ('Solving One-Variable Inequalities', [
                ('Solution Sets on a Number Line',
                 'An inequality has a set of solutions described by a symbol, a number-line '
                 'graph or interval notation, rather than a single value.',
                 ['inequality', 'solution set', 'number line']),
                ('Reversing the Symbol',
                 'Multiplying or dividing both sides by a negative number reverses the '
                 'inequality because the number line is reflected.',
                 ['reverse inequality', 'negative', 'solve']),
                ('Multi-Step Inequalities',
                 'The solving steps match linear equations; only the direction rule for '
                 'negative factors differs, and endpoints are open or closed by symbol.',
                 ['multi-step', 'inequality', 'endpoint']),
            ]),
            ('Compound Inequalities and Interval Notation', [
                ('And versus Or',
                 'A conjunction requires both conditions at once, while a disjunction '
                 'requires at least one, which changes the shape of the solution set.',
                 ['compound inequality', 'conjunction', 'disjunction']),
                ('Interval Notation',
                 'A parenthesis excludes an endpoint and a bracket includes it, and an '
                 'interval is always read from left to right.',
                 ['interval notation', 'bracket', 'parenthesis']),
            ]),
            ('Inequality Modeling', [
                ('Constraints as Inequalities',
                 'Phrases such as at most, at least and no more than set a boundary rather '
                 'than an exact value, which is what makes the model an inequality.',
                 ['constraint', 'at most', 'at least']),
                ('Interpreting a Boundary',
                 'The solution set states every allowed value, and a boundary value is '
                 'tested separately because the context may or may not include it.',
                 ['boundary', 'interpret', 'inclusive']),
            ]),
            ('Absolute Value Inequalities', [
                ('Less Than and Greater Than Forms',
                 'An inequality of the form |x| < a gives one interval between -a and a, '
                 'while |x| > a gives two rays pointing outward.',
                 ['absolute value inequality', 'interval', 'two cases']),
                ('Solving and Graphing',
                 'Isolate the absolute value, rewrite it as a compound inequality, then '
                 'graph the result and check both endpoints.',
                 ['solve', 'graph', 'compound']),
            ]),
        ],
    },
    {
        'unit': 'Linear Functions',
        'about': ('Linear relationships as functions: reading graphs, recognising linear '
                  'patterns, unit rates, slope, intercepts, the forms of a line, special '
                  'lines, arithmetic sequences and linear modelling.'),
        'sections': [
            ('elementary-algebra', '4-1-use-the-rectangular-coordinate-system'),
            ('elementary-algebra', '4-2-graph-linear-equations-in-two-variables'),
            ('elementary-algebra', '4-3-graph-with-intercepts'),
            ('elementary-algebra', '4-4-understand-slope-of-a-line'),
            ('elementary-algebra', '4-5-use-the-slope-intercept-form-of-an-equation-of-a-line'),
            ('elementary-algebra', '4-6-find-the-equation-of-a-line'),
            ('algebra-and-trigonometry', '13-2-arithmetic-sequences'),
        ],
        'topics': [
            ('Coordinate Plane and Graph Reading', [
                ('Ordered Pairs and Quadrants',
                 'A point (x, y) is located by a horizontal and a vertical displacement, and '
                 'the axes divide the plane into four quadrants.',
                 ['ordered pair', 'quadrant', 'coordinate plane']),
                ('Reading a Graph',
                 'A graph is read by tracing an input to its output, noting intercepts, '
                 'where the graph rises or falls, and where it is steepest.',
                 ['graph reading', 'intercept', 'increase']),
            ]),
            ('Identifying Linear Relationships', [
                ('Constant Rate of Change',
                 'A relationship is linear exactly when equal changes in the input produce '
                 'equal changes in the output.',
                 ['constant rate', 'linear', 'difference']),
                ('Linear versus Nonlinear',
                 'A table whose successive differences change, or a graph that curves, is '
                 'not linear no matter how straight a short segment looks.',
                 ['nonlinear', 'curve', 'compare']),
            ]),
            ('Proportional Relationships and Unit Rates', [
                ('Direct Proportion',
                 'A relationship of the form y = kx passes through the origin, and k is both '
                 'the unit rate and the constant ratio y/x.',
                 ['proportional', 'unit rate', 'origin']),
                ('Interpreting a Unit Rate',
                 'A unit rate restates a ratio as per one, which makes comparisons and '
                 'scaling direct and keeps the units attached.',
                 ['unit rate', 'ratio', 'scale']),
            ]),
            ('Slope and Rate of Change', [
                ('The Slope Formula',
                 'Slope is the change in y divided by the change in x between two points, so '
                 'it measures steepness and direction together.',
                 ['slope', 'rise over run', 'formula']),
                ('Slope in Context',
                 'The units of a slope are output units per input unit, so in a model it '
                 'names the rate the situation actually describes.',
                 ['rate of change', 'units', 'interpret']),
                ('Horizontal and Vertical Lines',
                 'A horizontal line has slope zero because its output never changes, and a '
                 'vertical line has undefined slope because its input never changes.',
                 ['horizontal line', 'vertical line', 'undefined slope']),
            ]),
            ('Intercepts', [
                ('Finding Intercepts',
                 'An intercept is where a graph meets an axis: set the other variable to '
                 'zero and solve for the remaining one.',
                 ['x-intercept', 'y-intercept', 'solve']),
                ('Intercepts in Context',
                 'In a model an intercept usually marks a starting amount, a break-even '
                 'point or a time when a quantity reaches zero.',
                 ['intercept', 'context', 'interpret']),
            ]),
            ('Forms of Linear Equations', [
                ('Slope-Intercept Form',
                 'The form y = mx + b displays the slope m and the y-intercept b directly, '
                 'which is why it is the fastest form to graph from.',
                 ['slope-intercept', 'y = mx + b', 'graph']),
                ('Standard Form of a Line',
                 'The form Ax + By = C describes the same line, and its intercepts are read '
                 'by setting each variable to zero in turn.',
                 ['standard form', 'intercept', 'linear equation']),
                ('Point-Slope Form',
                 'The form y - y1 = m(x - x1) writes the line through a known point with a '
                 'known slope, which is the form a context usually supplies.',
                 ['point-slope', 'slope', 'point']),
                ('Converting Between Forms',
                 'Algebraic rearrangement moves one form into another without changing the '
                 'line, so the form is chosen for what it reveals.',
                 ['convert', 'equivalent', 'rearrange']),
            ]),
            ('Special Lines and Line Families', [
                ('Parallel Lines',
                 'Parallel lines have equal slopes and never meet, because equal slopes mean '
                 'equal rates of change with a fixed vertical offset.',
                 ['parallel', 'equal slope', 'no intersection']),
                ('Perpendicular Lines',
                 'Perpendicular slopes are negative reciprocals, so their product is -1 and '
                 'one line rises where the other falls.',
                 ['perpendicular', 'negative reciprocal', 'slope']),
            ]),
            ('Arithmetic Sequences', [
                ('Common Difference',
                 'An arithmetic sequence adds the same difference at each step, so it is a '
                 'linear function whose domain is the term positions.',
                 ['arithmetic sequence', 'common difference', 'linear']),
                ('Arithmetic Explicit Rule',
                 'The rule a_n = a_1 + (n - 1)d gives any term directly from its position, '
                 'and the slope of the sequence is d.',
                 ['explicit rule', 'nth term', 'arithmetic sequence']),
            ]),
            ('Linear Modeling', [
                ('Building a Linear Model',
                 'A constant rate together with a starting value gives a model of the form '
                 'y = mx + b, with units on both the rate and the start.',
                 ['linear model', 'rate', 'initial value']),
                ('Interpreting and Evaluating a Model',
                 'A model is used by substituting an input for a prediction, and every '
                 'output is judged against the range the context allows.',
                 ['evaluate', 'predict', 'interpret']),
            ]),
        ],
    },
    {
        'unit': 'Statistics and Data Modeling',
        'about': ('One-variable data, categorical data in two-way tables, scatter plots '
                  'and trend lines, residuals and correlation versus causation, sampling '
                  'and measurement precision, and probability.'),
        'sections': [
            ('introductory-statistics', '2-5-measures-of-the-center-of-the-data'),
            ('introductory-statistics', '2-7-measures-of-the-spread-of-the-data'),
            ('introductory-statistics', '12-2-scatter-plots'),
            ('introductory-statistics', '12-3-the-regression-equation'),
            ('introductory-statistics', '1-2-data-sampling-and-variation-in-data-and-sampling'),
            ('introductory-statistics', '3-4-contingency-tables'),
            ('introductory-statistics', '3-3-two-basic-rules-of-probability'),
        ],
        'topics': [
            ('One-Variable Data', [
                ('Center and Spread',
                 'The mean and median describe the centre of a distribution, while the '
                 'range, interquartile range and standard deviation describe its spread.',
                 ['mean', 'median', 'standard deviation']),
                ('Displays and Shape',
                 'Dot plots, histograms and box plots expose shape, including skew and '
                 'outliers, which a single summary number can hide.',
                 ['histogram', 'box plot', 'skew']),
            ]),
            ('Two-Way Tables and Categorical Data', [
                ('Joint and Marginal Frequencies',
                 'A two-way table counts pairs of categories, and its margins give the '
                 'totals for each variable on its own.',
                 ['two-way table', 'marginal frequency', 'joint frequency']),
                ('Conditional Relative Frequency',
                 'Dividing by a row or column total gives a conditional relative frequency, '
                 'which compares groups of different sizes fairly.',
                 ['conditional frequency', 'relative frequency', 'compare groups']),
            ]),
            ('Scatter Plots and Trend Lines', [
                ('Association',
                 'A scatter plot shows the direction, strength and form of an association '
                 'between two quantitative variables.',
                 ['scatter plot', 'association', 'trend']),
                ('Line of Best Fit',
                 'A trend line summarises an association and supports prediction inside the '
                 'observed range, not far outside it.',
                 ['line of best fit', 'trend line', 'predict']),
            ]),
            ('Residuals, Correlation, and Causation', [
                ('Residuals',
                 'A residual is the actual value minus the predicted value, and a pattern in '
                 'the residuals shows the line is missing structure.',
                 ['residual', 'prediction error', 'pattern']),
                ('Correlation and Causation',
                 'Correlation measures only the strength of a linear association, so a '
                 'strong correlation by itself never establishes a cause.',
                 ['correlation', 'causation', 'confounding']),
            ]),
            ('Sampling, Bias, and Measurement Precision', [
                ('Random Sampling',
                 'A random sample supports inference about the population, while a sample '
                 'chosen for convenience does not.',
                 ['random sample', 'population', 'inference']),
                ('Bias and Precision',
                 'Question wording, sampling method and measurement error each distort a '
                 'conclusion in a different way, so they are diagnosed separately.',
                 ['bias', 'precision', 'measurement error']),
            ]),
            ('Probability', [
                ('Sample Space and Events',
                 'The sample space lists every possible outcome, and an event is a subset of '
                 'that space whose probability is a fraction of the whole.',
                 ['sample space', 'event', 'outcome']),
                ('Probability Rules',
                 'Probabilities lie between zero and one, complementary events sum to one, '
                 'and the addition rule handles events that can overlap.',
                 ['probability', 'complement', 'addition rule']),
                ('Two-Way Tables and Probability',
                 'Joint, marginal and conditional probabilities are read directly from a '
                 'two-way table by choosing the right denominator.',
                 ['conditional probability', 'two-way table', 'denominator']),
            ]),
        ],
    },
    {
        'unit': 'Linear Systems',
        'about': ('Systems of linear equations and inequalities: graphing, substitution, '
                  'elimination, the special solution cases, modelling with several '
                  'constraints, two-variable inequalities and feasible regions.'),
        'sections': [
            ('elementary-algebra', '5-1-solve-systems-of-equations-by-graphing'),
            ('elementary-algebra', '5-2-solve-systems-of-equations-by-substitution'),
            ('elementary-algebra', '5-3-solve-systems-of-equations-by-elimination'),
            ('elementary-algebra', '5-4-solve-applications-with-systems-of-equations'),
            ('elementary-algebra', '5-5-solve-mixture-applications-with-systems-of-equations'),
            ('elementary-algebra', '5-6-graphing-systems-of-linear-inequalities'),
        ],
        'topics': [
            ('Systems by Graphing', [
                ('Intersection as Solution',
                 'A solution of a system is an ordered pair that satisfies both equations at '
                 'once, which is exactly a point where the two graphs meet.',
                 ['system', 'graphing', 'intersection']),
            ]),
            ('Solving by Substitution', [
                ('The Substitution Method',
                 'Solving one equation for a variable and substituting into the other turns '
                 'a system of two equations into one equation in one variable.',
                 ['substitution', 'system', 'solve']),
            ]),
            ('Solving by Elimination', [
                ('The Elimination Method',
                 'Adding or subtracting multiples of the equations removes a variable when '
                 'its coefficients become opposites or equal.',
                 ['elimination', 'add equations', 'system']),
            ]),
            ('Special Systems', [
                ('No Solution',
                 'Parallel lines never intersect, so a system describing them is '
                 'inconsistent and has no solution.',
                 ['inconsistent', 'parallel', 'no solution']),
                ('Infinitely Many Solutions',
                 'Coincident lines are the same equation written twice, so every point on '
                 'the line solves the system.',
                 ['dependent', 'coincident', 'infinite solutions']),
            ]),
            ('System Modeling', [
                ('Two Constraints',
                 'Two conditions on two unknowns form a system whose solution satisfies both '
                 'conditions simultaneously, not one after the other.',
                 ['constraint', 'system model', 'two variables']),
                ('Checking a System Solution',
                 'A proposed solution is verified by substituting it into both original '
                 'equations, because a graphing error can imitate a solution.',
                 ['check', 'substitute', 'verify']),
            ]),
            ('Two-Variable Linear Inequalities', [
                ('Half-Planes',
                 'A linear inequality in two variables has a boundary line and one of the '
                 'two half-planes it divides the coordinate plane into.',
                 ['half-plane', 'boundary', 'inequality']),
                ('Testing a Point',
                 'Substituting a test point decides which side of the boundary satisfies the '
                 'inequality, and a dashed boundary excludes the line itself.',
                 ['test point', 'shade', 'dashed boundary']),
            ]),
            ('Systems of Inequalities and Feasible Regions', [
                ('Overlapping Regions',
                 'The solution of a system of inequalities is the overlap of the individual '
                 'solution regions, so a point must satisfy every inequality.',
                 ['system of inequalities', 'overlap', 'solution region']),
                ('Feasible Region',
                 'In a constraint model the overlap is the set of allowed choices, and its '
                 'vertices are where a linear objective reaches its extremes.',
                 ['feasible region', 'vertex', 'constraint']),
            ]),
        ],
    },
    {
        'unit': 'Functions',
        'about': ('The general function idea: inputs and outputs, notation, domain and '
                  'range, graph features, sequences and recursion, piecewise and absolute '
                  'value functions, and inverse relationships.'),
        'sections': [
            ('algebra-and-trigonometry', '3-1-functions-and-function-notation'),
            ('algebra-and-trigonometry', '3-2-domain-and-range'),
            ('algebra-and-trigonometry', '13-2-arithmetic-sequences'),
        ],
        'topics': [
            ('Relations and Functions', [
                ('The Function Definition',
                 'A function assigns exactly one output to each input, so a relation that '
                 'gives one input two different outputs is not a function.',
                 ['function', 'input', 'output']),
                ('The Vertical Line Test',
                 'A graph represents a function exactly when no vertical line meets it more '
                 'than once, which is the graphical form of the definition.',
                 ['vertical line test', 'function', 'graph']),
            ]),
            ('Function Notation', [
                ('Reading f(x)',
                 'The notation f(x) names the output of the function f at input x, so f(3) '
                 'means the output when the input is three.',
                 ['function notation', 'f(x)', 'input']),
                ('Evaluating and Interpreting',
                 'Evaluating substitutes a value into the rule, while interpreting states '
                 'what the resulting output means in the situation.',
                 ['evaluate', 'interpret', 'function notation']),
            ]),
            ('Domain and Range', [
                ('Domain',
                 'The domain is the set of allowed inputs, restricted by the context, by '
                 'division by zero and by even roots of negative numbers.',
                 ['domain', 'restriction', 'input']),
                ('Range',
                 'The range is the set of outputs a function actually produces, which is not '
                 'always every number the rule could theoretically give.',
                 ['range', 'output', 'graph']),
            ]),
            ('Interpreting Function Graphs', [
                ('Key Features',
                 'Intercepts, intervals of increase and decrease, and local maxima and '
                 'minima summarise what a function graph is doing.',
                 ['intercept', 'increasing', 'maximum']),
                ('Average Rate of Change',
                 'The average rate of change over an interval is the change in output divided '
                 'by the change in input, which is the slope of the secant line.',
                 ['average rate of change', 'secant', 'interval']),
            ]),
            ('Sequences and Recursive Rules', [
                ('Recursive Definition',
                 'A recursive rule states the first term and how each later term follows '
                 'from the previous one, which is enough to generate the whole sequence.',
                 ['recursive', 'sequence', 'initial term']),
                ('Sequence as Function',
                 'A sequence is a function whose domain is the positive integers, so its '
                 'graph is a set of isolated points rather than a curve.',
                 ['sequence', 'domain', 'discrete']),
            ]),
            ('Piecewise Functions', [
                ('Piecewise Notation',
                 'A piecewise function applies different rules on different intervals of its '
                 'domain, with each interval stated beside its rule.',
                 ['piecewise', 'interval', 'rule']),
                ('Evaluating and Graphing',
                 'Evaluation selects the branch whose interval contains the input, and the '
                 'graph draws each branch only on its own interval.',
                 ['evaluate', 'graph', 'branch']),
            ]),
            ('Absolute Value Functions', [
                ('The Parent Graph',
                 'The graph of y = |x| is V-shaped with its vertex at the origin and slopes '
                 'of 1 and -1 on its two branches.',
                 ['absolute value', 'vertex', 'V-shape']),
                ('Transformations of the Absolute Value Graph',
                 'Shifts move the vertex, a stretch changes how steep the branches are, and '
                 'a reflection turns the V upside down.',
                 ['transformation', 'vertex', 'stretch']),
            ]),
            ('Inverse Functions', [
                ('The Inverse Relationship',
                 'An inverse swaps the roles of input and output, so it undoes whatever the '
                 'original function did.',
                 ['inverse', 'swap', 'undo']),
                ('Finding an Inverse',
                 'Swap x and y in the equation and solve for y; the result is a function only '
                 'when the original passes the horizontal line test.',
                 ['inverse function', 'swap', 'one-to-one']),
            ]),
        ],
    },
    {
        'unit': 'Exponents and Radicals',
        'about': ('Powers, roots, scientific notation, radicals and rational exponents, and '
                  'the real-number structure that polynomial, exponential and quadratic work '
                  'all rely on.'),
        'sections': [
            ('elementary-algebra', '6-2-use-multiplication-properties-of-exponents'),
            ('elementary-algebra', '6-7-integer-exponents-and-scientific-notation'),
            ('elementary-algebra', '1-8-the-real-numbers'),
            ('elementary-algebra', '9-1-simplify-and-use-square-roots'),
            ('elementary-algebra', '9-2-simplify-square-roots'),
            ('elementary-algebra', '9-3-add-and-subtract-square-roots'),
            ('elementary-algebra', '9-4-multiply-square-roots'),
            ('elementary-algebra', '9-5-divide-square-roots'),
            ('elementary-algebra', '9-7-higher-roots'),
            ('elementary-algebra', '9-8-rational-exponents'),
        ],
        'topics': [
            ('Zero and Negative Exponents', [
                ('The Zero Exponent',
                 'Any nonzero base raised to the zero power is 1, because dividing equal '
                 'powers leaves no factor behind.',
                 ['zero exponent', 'power', 'base']),
                ('Negative Exponents',
                 'A negative exponent means the reciprocal of the positive power, so a '
                 'negative exponent never makes the value negative.',
                 ['negative exponent', 'reciprocal', 'power']),
            ]),
            ('Exponent Rules', [
                ('Product and Quotient Rules',
                 'Multiplying powers of one base adds the exponents, and dividing subtracts '
                 'them, because the factors are counted rather than multiplied.',
                 ['product rule', 'quotient rule', 'exponent']),
                ('Power Rules',
                 'A power of a power multiplies exponents, and a power of a product applies '
                 'the exponent to every factor.',
                 ['power rule', 'exponent', 'product']),
            ]),
            ('Scientific Notation', [
                ('Writing Scientific Notation',
                 'A number in scientific notation is written as a factor between 1 and 10 '
                 'times a power of ten, which fixes both size and precision.',
                 ['scientific notation', 'power of ten', 'magnitude']),
                ('Computing with Scientific Notation',
                 'Multiplying or dividing separates the coefficients from the powers of ten, '
                 'and the result is renormalised into scientific form.',
                 ['scientific notation', 'multiply', 'divide']),
            ]),
            ('Square and Cube Roots', [
                ('The Principal Square Root',
                 'The principal square root is the nonnegative number whose square is the '
                 'radicand, which is why solving x^2 = a gives both signs.',
                 ['square root', 'principal root', 'radicand']),
                ('Cube Roots',
                 'A cube root of a number is the value whose cube is that number, and unlike '
                 'a square root it exists for negative inputs too.',
                 ['cube root', 'negative', 'radical']),
            ]),
            ('Rational and Irrational Numbers', [
                ('Rational Numbers',
                 'A rational number is a ratio of two integers, and its decimal expansion '
                 'either terminates or repeats.',
                 ['rational number', 'ratio', 'decimal']),
                ('Irrational Numbers',
                 'An irrational number cannot be written as a ratio of integers, so its '
                 'decimal neither terminates nor repeats.',
                 ['irrational number', 'non-repeating', 'real number']),
            ]),
            ('Simplifying Radicals', [
                ('Product and Quotient Properties',
                 'The product property of radicals lets a perfect-square factor leave the '
                 'radical, which is what simplifying a radical means.',
                 ['radical', 'product property', 'simplify']),
                ('Rationalising a Denominator',
                 'Multiplying by a form of one removes a radical from a denominator without '
                 'changing the value of the expression.',
                 ['rationalise', 'denominator', 'radical']),
            ]),
            ('Rational Exponents', [
                ('Fractional Exponents',
                 'A rational exponent combines a power and a root, so a raised to m/n is the '
                 'nth root of a to the m.',
                 ['rational exponent', 'root', 'power']),
                ('Moving Between Forms',
                 'Radical form and rational-exponent form describe the same quantity, and '
                 'each one makes a different simplification visible.',
                 ['radical form', 'exponent form', 'equivalence']),
            ]),
        ],
    },
    {
        'unit': 'Exponential Functions',
        'about': ('Exponential relationships as functions, tables and graphs, growth and '
                  'decay models, geometric sequences, and how exponential change differs '
                  'from linear change.'),
        'sections': [
            ('algebra-and-trigonometry', '6-1-exponential-functions'),
            ('algebra-and-trigonometry', '13-3-geometric-sequences'),
        ],
        'topics': [
            ('Exponential Functions and Graphs', [
                ('The Exponential Growth Pattern',
                 'A function of the form f(x) = a b^x multiplies by b at each unit step, so '
                 'equal input steps give equal output ratios rather than equal differences.',
                 ['exponential function', 'growth factor', 'ratio']),
                ('Graph Features',
                 'An exponential graph has a horizontal asymptote, passes through (0, a), '
                 'and grows or decays without ever crossing the asymptote.',
                 ['asymptote', 'intercept', 'graph']),
            ]),
            ('Exponential Growth and Decay', [
                ('Growth and Decay Factors',
                 'A base greater than one grows, a base between zero and one decays, and the '
                 'percent change is the base minus one.',
                 ['growth', 'decay', 'percent change']),
                ('Compound Interest',
                 'Compounding applies the growth factor repeatedly, so more compounding '
                 'periods raise the effective rate without changing the nominal one.',
                 ['compound interest', 'growth factor', 'periods']),
            ]),
            ('Geometric Sequences', [
                ('Common Ratio',
                 'A geometric sequence multiplies by the same ratio at each step, which is '
                 'exactly why its terms follow an exponential rule.',
                 ['geometric sequence', 'common ratio', 'exponential']),
                ('Geometric Explicit Rule',
                 'The rule a_n = a_1 r^(n-1) gives any term from its position, and r is the '
                 'base of the matching exponential function.',
                 ['explicit rule', 'nth term', 'geometric sequence']),
            ]),
            ('Exponential Modeling', [
                ('Building an Exponential Model',
                 'An initial value together with a constant percent change gives a model of '
                 'the form f(t) = a b^t, with b determined by the change per period.',
                 ['exponential model', 'initial value', 'percent change']),
                ('Doubling Time and Half-Life',
                 'A fixed doubling time or half-life determines the base and the exponent, '
                 'so the model can be written from that single time.',
                 ['doubling time', 'half-life', 'model']),
            ]),
            ('Simple Exponential Equations', [
                ('Solving by Matching Bases',
                 'If two powers of the same base are equal then their exponents are equal, '
                 'so rewriting both sides with one base solves the equation.',
                 ['matching bases', 'exponential equation', 'exponent']),
                ('Estimating a Solution',
                 'When the bases cannot be matched, a solution is estimated from a graph or '
                 'a table and checked by substitution.',
                 ['estimate', 'graph', 'solve']),
            ]),
            ('Linear versus Exponential Change', [
                ('Additive versus Multiplicative Change',
                 'Linear change adds a constant amount per step while exponential change '
                 'multiplies by a constant factor, so their tables differ immediately.',
                 ['linear', 'exponential', 'compare']),
                ('Comparing Long-Run Behaviour',
                 'Over a long enough interval exponential growth overtakes any linear growth, '
                 'which is why the two models answer different questions.',
                 ['long run', 'growth', 'compare models']),
            ]),
        ],
    },
    {
        'unit': 'Polynomials and Factoring',
        'about': ('Polynomial vocabulary and operations, special products, and the factoring '
                  'methods that make expression rewriting fluent. Solving and graphing '
                  'factored forms belong to the quadratic units.'),
        'sections': [
            ('elementary-algebra', '6-1-add-and-subtract-polynomials'),
            ('elementary-algebra', '6-3-multiply-polynomials'),
            ('elementary-algebra', '6-4-special-products'),
            ('elementary-algebra', '6-5-divide-monomials'),
            ('elementary-algebra', '6-6-divide-polynomials'),
            ('elementary-algebra', '7-1-greatest-common-factor-and-factor-by-grouping'),
            ('elementary-algebra', '7-2-factor-quadratic-trinomials-with-leading-coefficient-1'),
            ('elementary-algebra', '7-3-factor-quadratic-trinomials-with-leading-coefficient-other-than-1'),
            ('elementary-algebra', '7-4-factor-special-products'),
            ('elementary-algebra', '7-5-general-strategy-for-factoring-polynomials'),
        ],
        'topics': [
            ('Polynomial Structure', [
                ('Degree and Leading Coefficient',
                 'The degree of a polynomial is its highest exponent, and the leading '
                 'coefficient belongs to that highest-degree term.',
                 ['degree', 'leading coefficient', 'polynomial']),
                ('Classifying Polynomials',
                 'Polynomials are named by degree and by number of terms, which tells you '
                 'which operations and patterns apply.',
                 ['monomial', 'binomial', 'trinomial']),
            ]),
            ('Polynomial Operations', [
                ('Adding and Subtracting Polynomials',
                 'Addition combines like terms, and subtraction distributes the minus sign to '
                 'every term of the polynomial being subtracted.',
                 ['add polynomials', 'subtract polynomials', 'like terms']),
                ('Multiplying Polynomials',
                 'Every term of one factor multiplies every term of the other, and like '
                 'terms are combined afterwards.',
                 ['multiply', 'distribute', 'polynomial']),
                ('Dividing by a Monomial',
                 'Each term of the polynomial is divided by the monomial separately, because '
                 'a sum divided by a term distributes.',
                 ['divide', 'monomial', 'quotient']),
            ]),
            ('Special Products', [
                ('The Square of a Binomial',
                 'Squaring a binomial gives the square of the first term plus twice the '
                 'product plus the square of the last term.',
                 ['perfect square', 'binomial square', 'special product']),
                ('The Difference of Squares',
                 'The product of a sum and a difference collapses to the difference of the '
                 'two squares because the middle terms cancel.',
                 ['difference of squares', 'special product', 'factor']),
            ]),
            ('Common Factors and Grouping', [
                ('The Greatest Common Factor',
                 'The greatest common factor of all terms moves outside the parentheses by '
                 'the distributive property, which is always the first factoring step.',
                 ['greatest common factor', 'distribute', 'factor']),
                ('Factoring by Grouping',
                 'Grouping terms in pairs with a shared factor exposes a common binomial '
                 'factor, which then factors out of the whole expression.',
                 ['grouping', 'factor', 'common binomial']),
            ]),
            ('Factoring Quadratic Trinomials', [
                ('Leading Coefficient One',
                 'For a trinomial with leading coefficient one, two numbers whose product is '
                 'the constant and whose sum is the middle coefficient give the factors.',
                 ['trinomial', 'factor', 'sum and product']),
                ('Leading Coefficient Other Than One',
                 'Splitting the middle term into two terms whose product is the product of '
                 'the end coefficients allows factoring by grouping.',
                 ['split middle term', 'factor', 'grouping']),
            ]),
            ('Special Factoring Patterns', [
                ('Perfect-Square Trinomials',
                 'A trinomial whose first and last terms are squares and whose middle term is '
                 'twice the product factors as a binomial squared.',
                 ['perfect square trinomial', 'factor', 'pattern']),
                ('Sum and Difference of Cubes',
                 'A sum or difference of cubes factors into a binomial and a trinomial whose '
                 'signs follow a fixed pattern.',
                 ['sum of cubes', 'difference of cubes', 'factor']),
            ]),
            ('Factoring Strategy', [
                ('A General Order',
                 'Take out the greatest common factor first, then count the terms to choose a '
                 'pattern, and always check by multiplying back.',
                 ['factoring strategy', 'check', 'pattern']),
                ('Factoring Completely',
                 'A factorisation is complete only when no remaining factor can be factored '
                 'further, which sometimes requires two passes.',
                 ['factor completely', 'repeat', 'check']),
            ]),
        ],
    },
    {
        'unit': 'Quadratic Functions',
        'about': ('Quadratic relationships as functions: recognising the pattern, graphing '
                  'parabolas, interpreting their features, using standard, factored and '
                  'vertex forms, transformations and quadratic modelling.'),
        'sections': [
            ('elementary-algebra', '10-5-graphing-quadratic-equations'),
            ('algebra-and-trigonometry', '5-1-quadratic-functions'),
        ],
        'topics': [
            ('Identifying Quadratic Relationships', [
                ('Constant Second Differences',
                 'A table of values is quadratic exactly when the second differences are '
                 'constant, just as a linear table has constant first differences.',
                 ['second difference', 'quadratic', 'table']),
                ('Quadratic versus Linear',
                 'A quadratic graph curves with a single turning point, while a line has the '
                 'same rate of change everywhere.',
                 ['quadratic', 'linear', 'turning point']),
            ]),
            ('Parabolas and Their Features', [
                ('Vertex and Axis of Symmetry',
                 'The vertex is the turning point of a parabola, and the axis of symmetry is '
                 'the vertical line through it that mirrors one side onto the other.',
                 ['vertex', 'axis of symmetry', 'parabola']),
                ('Direction of Opening',
                 'The sign of the leading coefficient decides whether the parabola opens '
                 'upward with a minimum or downward with a maximum.',
                 ['opening', 'leading coefficient', 'maximum']),
            ]),
            ('Quadratic Forms and Graphing', [
                ('Standard Form of a Parabola',
                 'Standard form shows the y-intercept immediately and, with the vertex '
                 'formula, locates the turning point.',
                 ['standard form', 'y-intercept', 'vertex formula']),
                ('Factored Form',
                 'Factored form displays the x-intercepts directly, and their midpoint gives '
                 'the axis of symmetry.',
                 ['factored form', 'x-intercept', 'symmetry']),
                ('Vertex Form',
                 'Vertex form displays the vertex and the direction and steepness of the '
                 'opening in one glance.',
                 ['vertex form', 'vertex', 'transformation']),
            ]),
            ('Quadratic Transformations', [
                ('Shifts, Stretches and Reflections',
                 'Changing the horizontal and vertical shift moves the vertex, while changing '
                 'the leading coefficient stretches or reflects the parabola.',
                 ['translation', 'stretch', 'reflection']),
            ]),
            ('Quadratic Modeling', [
                ('Building a Quadratic Model',
                 'A constant second difference, or a context with a maximum or minimum, '
                 'points to a quadratic rather than a linear model.',
                 ['quadratic model', 'second difference', 'context']),
                ('Interpreting Vertex and Intercepts',
                 'In a model the vertex is the optimum value and the intercepts are where the '
                 'modelled quantity is zero.',
                 ['vertex', 'intercept', 'interpret']),
            ]),
        ],
    },
    {
        'unit': 'Quadratic Equations',
        'about': ('Quadratic equations as solution problems: graphical and factored '
                  'solutions, square roots, completing the square, the quadratic formula '
                  'with discriminant reasoning, and modelling.'),
        'sections': [
            ('elementary-algebra', '7-6-quadratic-equations'),
            ('elementary-algebra', '10-1-solve-quadratic-equations-using-the-square-root-property'),
            ('elementary-algebra', '10-2-solve-quadratic-equations-by-completing-the-square'),
            ('elementary-algebra', '10-3-solve-quadratic-equations-using-the-quadratic-formula'),
            ('elementary-algebra', '10-4-solve-applications-modeled-by-quadratic-equations'),
        ],
        'topics': [
            ('Roots, Zeros, and Graphical Solutions', [
                ('Zeros and x-Intercepts',
                 'A zero of a quadratic function is an input whose output is zero, which is '
                 'exactly where its graph meets the x-axis.',
                 ['zero', 'x-intercept', 'solution']),
                ('The Number of Real Solutions',
                 'A parabola meets the x-axis zero, one or two times, and that count matches '
                 'the number of real solutions of the equation.',
                 ['real solutions', 'parabola', 'x-axis']),
            ]),
            ('Solving by Factoring', [
                ('The Zero Product Property',
                 'If a product equals zero then at least one factor is zero, so factored form '
                 'turns a quadratic equation into two linear equations.',
                 ['zero product property', 'factoring', 'solve']),
            ]),
            ('Solving with Square Roots', [
                ('The Square Root Property',
                 'If x squared equals a nonnegative number then x is plus or minus the square '
                 'root of that number, because both signs square to the same value.',
                 ['square root property', 'plus or minus', 'solve']),
            ]),
            ('Completing the Square', [
                ('Making a Perfect Square',
                 'Adding the square of half the linear coefficient turns a quadratic into a '
                 'perfect square, which then yields to the square root property.',
                 ['complete the square', 'perfect square', 'solve']),
            ]),
            ('Quadratic Formula and Discriminant', [
                ('The Quadratic Formula',
                 'The formula solves every quadratic in standard form, and it is derived by '
                 'completing the square on the general equation.',
                 ['quadratic formula', 'solve', 'standard form']),
                ('The Discriminant',
                 'The discriminant decides the number of real solutions: positive gives two, '
                 'zero gives one, and negative gives none.',
                 ['discriminant', 'number of solutions', 'sign']),
            ]),
            ('Quadratic Modeling and Synthesis', [
                ('Choosing a Method',
                 'Factoring is fastest when the factors are clean, square roots when there is '
                 'no linear term, and the formula always works.',
                 ['method choice', 'factoring', 'quadratic formula']),
                ('Modelling with Quadratics',
                 'A context about maximum height, area or an optimum yields a quadratic '
                 'equation whose solutions are interpreted and checked in the situation.',
                 ['quadratic model', 'application', 'interpret']),
            ]),
        ],
    },
]


def _concepts(topic_concepts: list[tuple[str, str, list[str]]]) -> list[dict]:
    """Turn (title, summary, keywords) rows into concept dicts with ordered gating.

    Inside one topic the concepts are ordered, so each later concept names the previous
    one as its prerequisite. Topics inside a unit stay parallel: no concept depends on a
    concept from another topic, which is what keeps the graph branching.
    """
    out: list[dict] = []
    previous: str | None = None
    for title, summary, keywords in topic_concepts:
        entry: dict = {'title': title, 'summary': summary, 'keywords': list(keywords)}
        if previous is not None:
            entry['prerequisites'] = [previous]
        out.append(entry)
        previous = title
    return out


def _course() -> dict:
    strands = []
    previous_unit: str | None = None
    for unit in UNITS:
        topics = [{'topic': name, 'concepts': _concepts(rows)}
                  for name, rows in unit['topics']]
        unit_entry: dict = {'unit': unit['unit'], 'topics': topics}
        if previous_unit is not None:
            # One bridge per unit, not one per concept: the unit-level prerequisite keeps
            # the gating structure branching instead of chaining 157 concepts in a line.
            unit_entry['prerequisites'] = [previous_unit]
        strands.append({'strand': unit['unit'], 'units': [unit_entry]})
        previous_unit = unit['unit']
    return {
        'id': COURSE_ID,
        'title': TITLE,
        'subject': 'Mathematics',
        'subject_kind': 'mathematics',
        'expected_weeks': 36,
        'description': DESCRIPTION,
        'course': 'Algebra 1 - Expressions, Linear and Quadratic Relationships',
        'strands': strands,
    }


def _alignment() -> dict:
    return {unit['unit']: [{'book': book, 'page': page} for book, page in unit['sections']]
            for unit in UNITS}


def main() -> int:
    course = _course()
    print(f"building {COURSE_ID} ({TITLE})")
    seed = write_seed(course)
    print(f'  wrote {seed.relative_to(BACKEND)}')
    pack_path = build_pack(course)
    print(f'  wrote {pack_path.relative_to(BACKEND)}')

    pack = json.loads(pack_path.read_text(encoding='utf-8'))
    pack['metadata']['textbook_alignment'] = {
        'spine': 'OpenStax Elementary Algebra (1e, CC BY 4.0)',
        'supplements': [
            'OpenStax Algebra and Trigonometry (1e, CC BY 4.0)',
            'OpenStax Introductory Statistics (1e, CC BY 4.0)',
        ],
        'link_only_note': ('OpenStax Algebra 1 reports CC BY-NC-SA 4.0 and is carried as a '
                           'link-only study reference: never stored or quoted.'),
        'units': _alignment(),
    }
    pack_path.write_text(json.dumps(pack, indent=1, ensure_ascii=False) + '\n',
                         encoding='utf-8')
    print(f'  anchored {sum(len(v) for v in _alignment().values())} textbook sections '
          f'across {len(_alignment())} units')
    print('\ndone. Register algebra_1 in app/courses.py and app/ingest/policy.py.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
