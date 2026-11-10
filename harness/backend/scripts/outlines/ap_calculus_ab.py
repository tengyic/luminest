"""AP Calculus AB outline, in the shape ``scripts/course_pipeline.py`` expects.

A one-year college-level calculus course written for this project. The eight units
follow the publicly published AP Calculus AB course framework and its exam weightings,
in framework order: limits and continuity (10-12%), differentiation definition and
fundamental properties (10-12%), composite, implicit and inverse functions (9-13%),
contextual applications of differentiation (10-15%), analytical applications of
differentiation (15-18%), integration and accumulation of change (17-20%),
differential equations (6-12%), and applications of integration (10-15%). Topic order
matches the framework's own topic sequence, so a learner working through the pack meets
the ideas in the order the exam assumes. Every summary below is an original statement
written here, not textbook text, and each names the condition under which its claim
holds -- a limit law only for existing limits, the mean value theorem only on a closed
interval with an open interior, a disc only when the slice is perpendicular to the axis
of revolution.

Textbook position. OpenStax Calculus Volume 1 reports CC BY-NC-SA 4.0, and so do
Volumes 2 and 3; all three were checked on 2026-11-10. None may be an anchor: the
licence forbids storing or quoting the text, so the volumes are named as a link-only
study reference. No CC BY calculus textbook exists in the OpenStax catalogue at all --
the other candidates are either NC or do not cover differentiation and integration --
so ``TEXTBOOK`` declares ``no_cc_by_anchor = True`` with the reason. Every unit carries
an empty ``sections`` list, and ``course_pipeline.py verify`` reports the anchoring
check as SKIP with that reason rather than a green tick it has not earned. The existing
``ap_calculus`` course (which spans the BC topics) is a separate course and is not
touched by this module.

The pack is generated: ``ap_calculus_ab.json`` is rebuilt by the pipeline from this
module and must never be hand-edited.
"""

from __future__ import annotations

ID = 'ap_calculus_ab'
TITLE = 'AP Calculus AB'
SUBJECT = 'Mathematics'
SUBJECT_KIND = 'mathematics'
EXPECTED_WEEKS = 34
COURSE_LINE = 'AP Calculus AB - Limits, Derivatives, Integrals and Applications'
DESCRIPTION = (
    'A college-level calculus course organised around the AP Calculus AB framework: '
    'limits and continuity at a point and over an interval; the derivative as a limit, '
    'the power, product and quotient rules, and the derivatives of the elementary '
    'functions; the chain rule, implicit differentiation and inverse functions; '
    'interpretation of the derivative in motion and related-rate contexts, linearization '
    'and L\'Hopital\'s rule; the mean value theorem, monotonicity, concavity, curve '
    'sketching and optimization; Riemann sums, the fundamental theorem and techniques of '
    'antidifferentiation; slope fields, separation of variables and exponential models; '
    'and average value, displacement, area between curves and volumes of revolution.')

TEXTBOOK = {
    'spine': '', 'supplements': [],
    'link_only_note': ('OpenStax Calculus Volume 1 reports CC BY-NC-SA 4.0 and is carried as '
                       'a link-only study reference: never stored or quoted.'),
    'no_cc_by_anchor': True,
    'reason': ('No CC BY calculus textbook exists in the OpenStax catalogue (checked '
               '2026-11-10; all three calculus volumes are CC BY-NC-SA). The outline is an '
               'original CC0 scope and sequence and is not anchored to a textbook.'),
}

UNITS = [
    # ------------------------------------------------------------------ 1
    {
        'unit': 'Limits and Continuity',
        'about': ('The foundation the whole course rests on: limit notation, estimating and '
                  'computing limits, the squeeze theorem, the classification of '
                  'discontinuities, continuity on an interval, and behaviour at infinity.'),
        'sections': [],
        'topics': [
            ('Can Change Occur at an Instant?', [
                ('Instantaneous Rate as a Limit of Average Rates',
                 'The average rate of change of f over [a, a+h] is (f(a+h) - f(a))/h, and '
                 'the instantaneous rate at a is the limit of that quotient as h approaches '
                 'zero, so the instantaneous rate exists only when that two-sided limit '
                 'exists and is finite.',
                 ['average rate', 'difference quotient', 'instantaneous rate']),
                ('Secant Slopes Approaching a Tangent Slope',
                 'As the second point of a secant line slides towards the fixed point, the '
                 'secant slopes approach the slope of the tangent at that point, which is '
                 'what makes the tangent slope a limit rather than a ratio of two points.',
                 ['secant line', 'tangent line', 'limit of slopes']),
            ]),
            ('Defining Limits and Limit Notation', [
                ('The Two-Sided Limit Definition',
                 'lim_{x->a} f(x) = L means the values of f can be made arbitrarily close to '
                 'L by taking x close enough to a but distinct from a, so f need not be '
                 'defined at a and its value there, if any, does not affect the limit.',
                 ['limit', 'two-sided', 'punctured neighbourhood']),
            ]),
            ('Estimating Limits from Graphs', [
                ('Reading a Limit from a Graph',
                 'A graph supports lim_{x->a} f(x) = L when both branches approach height L '
                 'as x approaches a from either side, so an open circle, a filled point or a '
                 'mismatched point height at x = a is irrelevant to the limit itself.',
                 ['graph', 'one-sided approach', 'hole']),
            ]),
            ('Estimating Limits from Tables', [
                ('Limits from Tables on Both Sides',
                 'A table estimates a limit only when the inputs approach a from below and '
                 'from above and both output columns settle on the same value; a table is '
                 'evidence for a limit and never a proof of one.',
                 ['table', 'numerical estimate', 'two-sided']),
            ]),
            ('Limits Using Algebraic Properties', [
                ('Limit Laws for Sums, Products and Quotients',
                 'If lim f and lim g both exist at a, then the limit of a sum, difference, '
                 'constant multiple or product is the matching combination of the two '
                 'limits, and the quotient law holds as well provided lim g is nonzero.',
                 ['limit laws', 'sum rule', 'quotient law']),
                ('Direct Substitution for Continuous Forms',
                 'Direct substitution gives the limit whenever f is a polynomial, or a '
                 'rational or trigonometric function at a point of its domain, because those '
                 'functions are continuous there and a continuous function has limit equal '
                 'to its value.',
                 ['direct substitution', 'polynomial', 'continuous function']),
            ]),
            ('Limits Using Algebraic Manipulation', [
                ('Cancelling a Common Factor',
                 'When substitution produces the indeterminate form 0/0, factoring numerator '
                 'and denominator and cancelling the common factor gives a function that '
                 'agrees with f for x near a but not equal to a, so the limit equals the '
                 'value of the simplified expression at a.',
                 ['indeterminate form', 'factoring', 'cancellation']),
                ('Rationalising a Radical Expression',
                 'For a quotient whose numerator or denominator contains a radical '
                 'difference and whose denominator vanishes at a, multiplying both parts by '
                 'the conjugate creates a factor that cancels the source of the zero.',
                 ['conjugate', 'rationalise', 'radical']),
            ]),
            ('Selecting Procedures for Determining Limits', [
                ('A Decision Order for Evaluating Limits',
                 'Substitute first; if the result is 0/0, try factoring, rationalising or a '
                 'common denominator; if the result is a nonzero number over zero, compare '
                 'the one-sided behaviours, so the form the substitution produces selects '
                 'the method.',
                 ['strategy', 'indeterminate form', 'method choice']),
            ]),
            ('The Squeeze Theorem', [
                ('The Squeeze Theorem',
                 'If g(x) <= f(x) <= h(x) on a punctured interval around a and lim g = lim h '
                 '= L, then lim f = L, which is how sin(x)/x is evaluated at zero without '
                 'dividing by zero.',
                 ['squeeze theorem', 'bounds', 'pinching']),
            ]),
            ('Connecting Multiple Representations', [
                ('Agreement Across Graph, Table and Algebra',
                 'A limit claim is supported only when the graph, the table and the algebra '
                 'agree on one value, and a disagreement means that at least one '
                 'representation has been read outside the range where it is informative.',
                 ['representations', 'consistency', 'evidence']),
            ]),
            ('Types of Discontinuities', [
                ('Removable, Jump and Infinite Discontinuities',
                 'A discontinuity at a is removable when the two-sided limit exists but f(a) '
                 'is undefined or different, jump when both one-sided limits exist and are '
                 'unequal, and infinite when at least one one-sided limit is unbounded.',
                 ['removable', 'jump', 'infinite discontinuity']),
            ]),
            ('Defining Continuity at a Point', [
                ('The Three-Part Continuity Condition',
                 'f is continuous at a exactly when f(a) is defined, lim_{x->a} f(x) exists, '
                 'and the limit equals f(a), so continuity is a limit statement plus a value '
                 'statement and fails if either part fails.',
                 ['continuity', 'three conditions', 'point']),
            ]),
            ('Confirming Continuity over an Interval', [
                ('Continuity on Open and Closed Intervals',
                 'f is continuous on an open interval when it is continuous at every point '
                 'of it, and on a closed interval [a, b] when it is also right-continuous at '
                 'a and left-continuous at b, since only one side exists at each endpoint.',
                 ['interval continuity', 'one-sided continuity', 'endpoint']),
                ('Continuity of Combinations',
                 'Sums, differences, products, quotients with a nonzero denominator and '
                 'compositions of continuous functions are continuous, so polynomials, '
                 'rationals on their domains, and sin x, cos x, e^x and ln x are continuous '
                 'wherever they are defined.',
                 ['combinations', 'composition', 'elementary functions']),
            ]),
            ('Removing Discontinuities', [
                ('Filling a Removable Discontinuity',
                 'A discontinuity at a is removed by defining f(a) to be lim_{x->a} f(x), '
                 'which is possible exactly when that two-sided limit exists and is finite, '
                 'so a jump or infinite discontinuity cannot be repaired by one value.',
                 ['removable discontinuity', 'redefinition', 'finite limit']),
            ]),
            ('Infinite Limits and Vertical Asymptotes', [
                ('Infinite Limits and Vertical Asymptotes',
                 'If f(x) grows without bound as x approaches a from one side, the line x = a '
                 'is a vertical asymptote, and the two one-sided behaviours are reported '
                 'separately because they may diverge with the same sign or with opposite '
                 'signs.',
                 ['infinite limit', 'vertical asymptote', 'unbounded']),
            ]),
            ('Limits at Infinity and Horizontal Asymptotes', [
                ('Limits at Infinity by Comparing Degrees',
                 'For a rational function, the limit at plus or minus infinity is decided by '
                 'the leading terms: equal degrees give the ratio of leading coefficients, a '
                 'higher denominator degree gives zero, and a higher numerator degree gives '
                 'no finite limit.',
                 ['limits at infinity', 'horizontal asymptote', 'degree comparison']),
            ]),
            ('The Intermediate Value Theorem', [
                ('The Intermediate Value Theorem',
                 'If f is continuous on [a, b] and k lies between f(a) and f(b), then f(c) = '
                 'k for some c in (a, b), which guarantees a root whenever the endpoint '
                 'values have opposite signs but guarantees nothing when f is discontinuous.',
                 ['intermediate value', 'continuity', 'root existence']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 2
    {
        'unit': 'Differentiation: Definition and Fundamental Properties',
        'about': ('The derivative as a limit and the short rules that replace that limit: '
                  'notation, estimation, the link between differentiability and continuity, '
                  'and the power, product, quotient and elementary-function rules.'),
        'sections': [],
        'topics': [
            ('Average and Instantaneous Rates of Change', [
                ('The Difference Quotient and Its Limit',
                 'The average rate of change over [a, a+h] is (f(a+h) - f(a))/h, and the '
                 'instantaneous rate at a is the limit of this quotient as h approaches '
                 'zero, so the derivative is a limit of secant slopes rather than a quotient '
                 'at a single point.',
                 ['difference quotient', 'average rate', 'instantaneous rate']),
            ]),
            ('Defining the Derivative and Its Notation', [
                ('The Derivative as a Limit at a Point',
                 'f\'(a) = lim_{h->0} (f(a+h) - f(a))/h, equivalently lim_{x->a} '
                 '(f(x) - f(a))/(x - a), exists exactly when both forms give the same finite '
                 'value, and the two notations dy/dx, f\'(x) name that value at x.',
                 ['derivative definition', 'notation', 'two forms']),
            ]),
            ('Estimating Derivatives at a Point', [
                ('Estimating a Derivative from Values or a Graph',
                 'A derivative is estimated by a symmetric difference quotient '
                 '(f(a+h) - f(a-h))/(2h) for a small h, or by the slope of the tangent drawn '
                 'at the point, and either estimate is trustworthy only where the function is '
                 'locally linear to the precision wanted.',
                 ['numerical derivative', 'symmetric difference', 'tangent slope']),
            ]),
            ('Differentiability and Continuity', [
                ('Differentiability Implies Continuity',
                 'Differentiability implies continuity but not the converse: |x| is '
                 'continuous at 0 yet has no derivative there because the one-sided '
                 'difference quotients disagree, so continuity is necessary but not '
                 'sufficient for differentiability.',
                 ['differentiability', 'continuity', 'corner']),
            ]),
            ('The Power Rule', [
                ('The Power Rule for Constant Exponents',
                 'd/dx x^n = n x^(n-1) for every constant real exponent n, including '
                 'negative and fractional ones, on any interval where x^n is defined, with '
                 'the derivative failing to exist at points where the power itself is '
                 'undefined.',
                 ['power rule', 'exponent', 'derivative']),
            ]),
            ('Constant, Sum, Difference and Constant Multiple Rules', [
                ('Linearity of the Derivative',
                 'The derivative of a constant is zero and differentiation is linear, so '
                 '(c f + g)\' = c f\' + g\' at every point where both f\' and g\' exist, '
                 'which lets a polynomial be differentiated term by term.',
                 ['constant rule', 'sum rule', 'linearity']),
            ]),
            ('Derivatives of cos x, sin x, e^x and ln x', [
                ('Derivatives of the Four Elementary Functions',
                 'd/dx sin x = cos x and d/dx cos x = -sin x for all real x, d/dx e^x = e^x '
                 'for all real x, and d/dx ln x = 1/x for x > 0, the last restricted because '
                 'ln x is defined only on the positive reals.',
                 ['sine', 'cosine', 'exponential', 'logarithm']),
            ]),
            ('The Product Rule', [
                ('The Product Rule',
                 '(f g)\' = f\' g + f g\' at every point where both f and g are '
                 'differentiable, and the rule needs both terms because each factor is '
                 'differentiated once while the other is held fixed.',
                 ['product rule', 'differentiable', 'factors']),
            ]),
            ('The Quotient Rule', [
                ('The Quotient Rule',
                 '(f/g)\' = (f\' g - f g\')/g^2 wherever f and g are differentiable and g is '
                 'nonzero, and the order of the numerator matters because a reversed order '
                 'changes the sign of the result.',
                 ['quotient rule', 'nonzero denominator', 'derivative']),
            ]),
            ('Derivatives of Tangent, Cotangent, Secant and Cosecant', [
                ('Derivatives of tan, cot, sec and csc',
                 'd/dx tan x = sec^2 x, d/dx cot x = -csc^2 x, d/dx sec x = sec x tan x and '
                 'd/dx csc x = -csc x cot x, each on the domain where the original function '
                 'is defined, so the derivative is undefined at the vertical asymptotes.',
                 ['tangent', 'secant', 'trigonometric derivatives']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 3
    {
        'unit': 'Differentiation: Composite, Implicit, and Inverse Functions',
        'about': ('Differentiation when the function is built out of others: the chain rule '
                  'for compositions, implicit differentiation for relations, the reciprocal '
                  'rule for inverses, and the inverse trigonometric derivatives it yields.'),
        'sections': [],
        'topics': [
            ('The Chain Rule', [
                ('The Chain Rule for Composites',
                 'If g is differentiable at a and f is differentiable at g(a), then '
                 '(f o g)\'(a) = f\'(g(a)) g\'(a), so the outer derivative is evaluated at the '
                 'inner value and multiplied by the inner derivative, and neglecting the '
                 'last factor is the standard error.',
                 ['chain rule', 'composite', 'outer derivative']),
            ]),
            ('Implicit Differentiation', [
                ('Differentiating an Implicit Relation',
                 'Differentiating both sides of F(x, y) = 0 with respect to x while treating '
                 'y as a differentiable function of x produces an equation solved for dy/dx, '
                 'which gives the slope wherever F_y is nonzero without solving for y '
                 'explicitly.',
                 ['implicit differentiation', 'dy/dx', 'relation']),
            ]),
            ('Differentiating Inverse Functions', [
                ('The Inverse Function Derivative Rule',
                 'If f is differentiable at a with f\'(a) nonzero and f has an inverse '
                 'defined near f(a), then (f^-1)\'(f(a)) = 1/f\'(a), because the tangent '
                 'slopes of a function and its inverse are reciprocals and a zero slope '
                 'would give a vertical tangent.',
                 ['inverse function', 'reciprocal slope', 'nonzero derivative']),
            ]),
            ('Differentiating Inverse Trigonometric Functions', [
                ('Derivatives of arcsin, arccos and arctan',
                 'd/dx arcsin x = 1/sqrt(1 - x^2) and d/dx arccos x = -1/sqrt(1 - x^2) for '
                 '|x| < 1, while d/dx arctan x = 1/(1 + x^2) for all real x, the restricted '
                 'domains matching the range on which each inverse is defined.',
                 ['arcsine', 'arctangent', 'inverse trig']),
            ]),
            ('Selecting Procedures for Calculating Derivatives', [
                ('Choosing a Differentiation Procedure',
                 'Read the outermost structure first: a sum differentiates termwise, a '
                 'product needs the product rule, a quotient the quotient rule, and a '
                 'composition the chain rule, with inner structure handled recursively so '
                 'that each rule is applied exactly where it belongs.',
                 ['procedure choice', 'structure', 'recursion']),
            ]),
            ('Higher-Order Derivatives', [
                ('Second and Higher Derivatives',
                 'The second derivative is the derivative of f\', written f\'\' or d^2y/dx^2, '
                 'and it exists at a only where f\' is itself differentiable there, so the '
                 'existence of each higher derivative is a separate condition.',
                 ['second derivative', 'higher order', 'notation']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 4
    {
        'unit': 'Contextual Applications of Differentiation',
        'about': ('The derivative read as a rate in a situation: motion on a line, marginal '
                  'and related rates, the tangent line used as a local approximation, and '
                  'L\'Hopital\'s rule for limits that resist algebra.'),
        'sections': [],
        'topics': [
            ('Interpreting the Derivative in Context', [
                ('Units and Meaning of a Derivative',
                 'In an applied model f\'(a) is the instantaneous rate of change of the '
                 'output with respect to the input at a, carrying output units per input '
                 'unit, and its sign states whether the quantity is increasing or decreasing '
                 'at that instant.',
                 ['units', 'interpretation', 'rate']),
            ]),
            ('Straight-Line Motion', [
                ('Position, Velocity and Acceleration',
                 'For a particle on a line with position s(t), velocity is v(t) = s\'(t) and '
                 'acceleration is a(t) = v\'(t), so the particle moves forward where v > 0, '
                 'backward where v < 0, and reverses direction exactly where v changes sign.',
                 ['velocity', 'acceleration', 'direction']),
                ('Speed and the Sign Test for Speeding Up',
                 'Speed is |v(t)|, so the particle speeds up exactly where velocity and '
                 'acceleration have the same sign and slows down where they have opposite '
                 'signs, which is a statement about signs and not about the sign of v alone.',
                 ['speed', 'speeding up', 'sign test']),
            ]),
            ('Rates of Change in Other Applied Contexts', [
                ('Marginal Rate and Accumulated Total',
                 'A derivative quoted as a marginal quantity is the change in the total per '
                 'one additional unit, so marginal cost is C\'(q) and it approximates the '
                 'cost of the next item only while the step of one unit stays small relative '
                 'to the scale of q.',
                 ['marginal', 'applied rate', 'per unit']),
            ]),
            ('Introduction to Related Rates', [
                ('Relating Rates Through a Constraint',
                 'When two changing quantities satisfy an equation, differentiating that '
                 'equation with respect to time relates their rates, so one rate is found '
                 'from the other through the relation and neither can be obtained from its '
                 'own value alone.',
                 ['related rates', 'time derivative', 'constraint']),
            ]),
            ('Solving Related Rates Problems', [
                ('The Related-Rates Procedure',
                 'Name the variables and the instant, write the relation that holds for all '
                 'time, differentiate both sides with respect to t, then substitute the '
                 'values at the instant and solve for the unknown rate with its units '
                 'attached.',
                 ['procedure', 'differentiate in time', 'substitution']),
            ]),
            ('Local Linearity and Linearization', [
                ('The Tangent-Line Approximation',
                 'Near a, f(x) is approximately f(a) + f\'(a)(x - a), and the approximation '
                 'error is small only while x stays close to a and the second derivative '
                 'stays bounded there, so linearization is a local and not a global claim.',
                 ['linearization', 'tangent line', 'local approximation']),
            ]),
            ("L'Hopital's Rule for Indeterminate Forms", [
                ("L'Hopital's Rule for Quotient Indeterminate Forms",
                 'If f and g are differentiable near a with g\' nonzero there and the '
                 'quotient has the indeterminate form 0/0 or infinity over infinity, then '
                 'lim f/g = lim f\'/g\', provided the limit of the derivative quotient exists '
                 'or is infinite, so the rule replaces one limit by another rather than '
                 'computing a value by substitution.',
                 ['l\'hopital', 'indeterminate form', 'quotient limit']),
                ('Rewriting the Other Indeterminate Forms',
                 'Forms such as 0 times infinity, infinity minus infinity, 1 to the infinity, '
                 '0 to the zero and infinity to the zero are first rewritten as a ratio or '
                 'as an exponential of a logarithm, because the rule itself applies only to '
                 'the two quotient forms.',
                 ['indeterminate product', 'logarithm', 'rewrite']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 5
    {
        'unit': 'Analytical Applications of Differentiation',
        'about': ('What the derivative says about a function globally: the mean value '
                  'theorem, extrema and critical points, monotonicity, concavity, curve '
                  'sketching, optimization, and the slopes of implicitly defined curves.'),
        'sections': [],
        'topics': [
            ('The Mean Value Theorem', [
                ('The Mean Value Theorem',
                 'If f is continuous on [a, b] and differentiable on (a, b), then some c in '
                 '(a, b) satisfies f\'(c) = (f(b) - f(a))/(b - a), so at least one tangent is '
                 'parallel to the secant, and dropping either hypothesis can destroy the '
                 'conclusion.',
                 ['mean value theorem', 'secant slope', 'interior point']),
            ]),
            ('Extreme Value Theorem, Extrema and Critical Points', [
                ('The Extreme Value Theorem',
                 'A function continuous on a closed interval [a, b] attains an absolute '
                 'maximum and an absolute minimum somewhere in that interval, whereas on an '
                 'open interval it may approach an extreme without ever reaching it.',
                 ['extreme value', 'closed interval', 'absolute extrema']),
                ('Critical Points as Extremum Candidates',
                 'An interior extremum of a differentiable function occurs only where '
                 'f\'(c) = 0, so candidates for extrema are the critical points, where f\' is '
                 'zero or fails to exist, together with the endpoints of a closed interval.',
                 ['critical point', 'fermat condition', 'candidates']),
            ]),
            ('Intervals of Increase and Decrease', [
                ('Sign of the Derivative and Monotonicity',
                 'On an interval where f\' > 0 throughout, f is strictly increasing, and '
                 'where f\' < 0 throughout it is strictly decreasing, the conclusion requiring '
                 'continuity on the closed interval and differentiability inside it.',
                 ['increasing', 'decreasing', 'sign of derivative']),
            ]),
            ('The First Derivative Test', [
                ('The First Derivative Test',
                 'At a critical point c, f\' changing from positive to negative gives a local '
                 'maximum, changing from negative to positive gives a local minimum, and no '
                 'change of sign gives neither.',
                 ['first derivative test', 'local maximum', 'sign change']),
            ]),
            ('The Candidates Test for Absolute Extrema', [
                ('The Candidates Test',
                 'On a closed interval the absolute extrema occur among the critical points '
                 'and the endpoints, so evaluating f at every candidate and comparing those '
                 'values decides both absolute extrema without any sign analysis.',
                 ['candidates test', 'closed interval', 'absolute extremum']),
            ]),
            ('Concavity over a Domain', [
                ('Concavity and the Sign of the Second Derivative',
                 'f is concave up on an interval where f\'\' > 0 throughout and concave down '
                 'where f\'\' < 0 throughout, and an inflection point is a point where the '
                 'concavity changes, which requires f\'\' to change sign there.',
                 ['concavity', 'inflection point', 'second derivative']),
            ]),
            ('The Second Derivative Test', [
                ('The Second Derivative Test',
                 'At a critical point c with f\'(c) = 0, f\'\'(c) > 0 gives a local minimum '
                 'and f\'\'(c) < 0 a local maximum, while f\'\'(c) = 0 leaves the test '
                 'inconclusive and sends the question back to the first derivative test.',
                 ['second derivative test', 'local extremum', 'inconclusive']),
            ]),
            ('Sketching Graphs of Functions and Their Derivatives', [
                ('Reading Shape from a Derivative Graph',
                 'A derivative graph is read by where it crosses zero, where it is positive '
                 'or negative, and where it is increasing or decreasing, which respectively '
                 'report the extrema and the concavity of the original function.',
                 ['derivative graph', 'shape', 'reading']),
            ]),
            ('Connecting a Function, Its First and Second Derivative', [
                ('Translating Between f, f\' and f\'\'',
                 'The three graphs describe one function at successive levels: f\' gives the '
                 'slope of f and f\'\' gives the slope of f\', so a zero of f\' is a '
                 'horizontal tangent of f and an extremum of f\' is an inflection point of '
                 'the concavity of f.',
                 ['relationship', 'slope', 'correspondence']),
            ]),
            ('Introduction to Optimization', [
                ('Setting Up an Optimization Problem',
                 'An optimization problem names the quantity to be optimized, uses the '
                 'constraint to write that quantity as a function of a single variable, and '
                 'states the interval the context allows before any derivative is taken.',
                 ['optimization', 'objective', 'constraint']),
            ]),
            ('Solving Optimization Problems', [
                ('Confirming a Global Optimum',
                 'After solving the objective\'s critical points, the global optimum is '
                 'confirmed by the candidates test on the closed feasible interval or by a '
                 'sign analysis of the derivative that also accounts for the endpoint '
                 'behaviour.',
                 ['global optimum', 'candidates', 'feasible interval']),
            ]),
            ('Behaviours of Implicit Relations', [
                ('Slopes and Tangents of an Implicit Curve',
                 'On a curve F(x, y) = 0 the derivative dy/dx = -F_x/F_y gives the slope '
                 'wherever F_y is nonzero, a vertical tangent occurs where F_y = 0 with F_x '
                 'nonzero, and a horizontal tangent requires F_x = 0 with F_y nonzero.',
                 ['implicit curve', 'tangent', 'partial derivatives']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 6
    {
        'unit': 'Integration and Accumulation of Change',
        'about': ('Accumulation as the inverse of differentiation: Riemann sums, the '
                  'definite integral as their limit, both parts of the fundamental theorem, '
                  'and the antidifferentiation techniques the exam expects.'),
        'sections': [],
        'topics': [
            ('Exploring Accumulation of Change', [
                ('Accumulation as Signed Area',
                 'The accumulated change of a rate over an interval is the signed area '
                 'between its graph and the horizontal axis, so area below the axis counts '
                 'negatively and the accumulation can be smaller than the geometric area.',
                 ['accumulation', 'signed area', 'rate']),
            ]),
            ('Approximating Areas with Riemann Sums', [
                ('Left, Right and Midpoint Riemann Sums',
                 'A Riemann sum approximates accumulation by rectangles whose heights are '
                 'sampled at the left endpoint, the right endpoint or the midpoint of each '
                 'subinterval, and the left and right sums bracket the true value only when '
                 'the function is monotone on the interval.',
                 ['riemann sum', 'rectangle', 'sample point']),
                ('The Trapezoidal Approximation',
                 'The trapezoidal rule averages the left and right sums, which is exact for '
                 'linear functions and normally closer than either sum for a smooth curve, '
                 'because each slice is a trapezoid rather than a rectangle.',
                 ['trapezoid', 'average of sums', 'approximation']),
            ]),
            ('Riemann Sums, Summation Notation and Definite Integral Notation', [
                ('The Definite Integral as a Limit of Sums',
                 'The definite integral of f from a to b is the limit of its Riemann sums as '
                 'the number of subintervals grows and every width shrinks to zero, and that '
                 'limit exists whenever f is continuous on [a, b], in which case its value '
                 'does not depend on where the sample points are chosen.',
                 ['definite integral', 'limit of sums', 'integrable']),
                ('Summation Notation and Its Rules',
                 'Sigma notation compresses a sum and is manipulated by splitting at a '
                 'boundary, factoring out constants and applying the standard formulas for '
                 'the sum of k and of k^2, which is how a Riemann sum is evaluated in closed '
                 'form before the limit is taken.',
                 ['sigma notation', 'sum formulas', 'closed form']),
            ]),
            ('The Fundamental Theorem of Calculus and Accumulation Functions', [
                ('The First Fundamental Theorem',
                 'If f is continuous on an interval containing a, then the accumulation '
                 'function A(x) = integral from a to x of f(t) dt is differentiable inside '
                 'that interval with A\'(x) = f(x), so differentiating an accumulation '
                 'function returns the integrand evaluated at the upper limit.',
                 ['fundamental theorem', 'accumulation function', 'continuous integrand']),
            ]),
            ('Interpreting Accumulation Functions Involving Area', [
                ('Reading an Accumulation Function from a Graph',
                 'An accumulation function\'s value is the net area gathered from a to x, its '
                 'derivative is the height of the graph at x, and its concavity follows the '
                 'sign of the slope of that height, so the area graph can be analysed without '
                 'an antiderivative.',
                 ['accumulation graph', 'net area', 'derivative of integral']),
            ]),
            ('Properties of Definite Integrals', [
                ('Linearity and Interval Properties',
                 'The integral of a sum is the sum of the integrals and a constant factor '
                 'moves outside, an integral over a single point is zero, reversing the '
                 'limits changes the sign, and splitting at an interior point adds, each '
                 'property holding whenever the integrals involved exist.',
                 ['integral properties', 'additivity', 'orientation']),
            ]),
            ('The Fundamental Theorem of Calculus and Definite Integrals', [
                ('The Second Fundamental Theorem',
                 'If f is continuous on [a, b] and F is any antiderivative of f there, then '
                 'the integral of f from a to b equals F(b) - F(a), so a definite integral is '
                 'evaluated by one antiderivative at the two endpoints rather than by a '
                 'limit of sums.',
                 ['evaluation theorem', 'antiderivative', 'endpoints']),
            ]),
            ('Antiderivatives and Indefinite Integrals', [
                ('The Indefinite Integral and Its Constant',
                 'The indefinite integral of f is F(x) + C for any antiderivative F, because '
                 'two antiderivatives of a function on an interval differ by a constant, and '
                 'that constant must be determined by an initial condition rather than '
                 'guessed.',
                 ['antiderivative', 'constant of integration', 'indefinite integral']),
            ]),
            ('Integration by Substitution', [
                ('Integration by Substitution',
                 'Setting u = g(x) turns the integral of f(g(x)) g\'(x) dx into the integral '
                 'of f(u) du, and the method applies only when the integrand contains the '
                 'inner derivative as a factor, which is what makes the change of variable '
                 'exact rather than approximate.',
                 ['substitution', 'u-substitution', 'inner derivative']),
                ('Changing Limits in a Definite Substitution',
                 'In a definite integral the limits must be converted to values of u when '
                 'substituting, because carrying the x-limits into a u-integral evaluates the '
                 'antiderivative on the wrong interval.',
                 ['limits of integration', 'definite substitution', 'conversion']),
            ]),
            ('Integration Using Long Division and Completing the Square', [
                ('Rewriting an Integrand Before Integrating',
                 'When the integrand is a rational function with numerator degree at least '
                 'the denominator\'s, polynomial long division separates a polynomial from a '
                 'proper remainder, and completing the square turns a quadratic denominator '
                 'into a shifted square that matches a standard antiderivative form.',
                 ['long division', 'completing the square', 'rational integrand']),
            ]),
            ('Selecting Techniques for Antidifferentiation', [
                ('A Decision Order for Antidifferentiation',
                 'Check for a standard form first, then for a substitution whose inner '
                 'derivative is present, then for algebraic rewriting such as division or '
                 'completing the square, and always verify the result by differentiating it.',
                 ['technique choice', 'standard forms', 'verify']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 7
    {
        'unit': 'Differential Equations',
        'about': ('Equations about rates rather than values: how a differential equation '
                  'models a situation, how solutions are verified and pictured, and how '
                  'separation of variables plus an initial condition produces a particular '
                  'solution.'),
        'sections': [],
        'topics': [
            ('Modeling with Differential Equations', [
                ('A Differential Equation as a Rate Law',
                 'A differential equation states how a quantity\'s rate of change depends on '
                 'the quantity and on the independent variable, so dy/dt = ky models change '
                 'proportional to the amount present while dy/dt = k(M - y) models change '
                 'bounded by a capacity M.',
                 ['differential equation', 'rate law', 'model']),
            ]),
            ('Verifying Solutions', [
                ('Verifying a Solution by Substitution',
                 'A function is a solution of a differential equation on an interval exactly '
                 'when substituting it and its derivatives makes the two sides identical at '
                 'every point of that interval, so verification is an identity check and not '
                 'a single-point test.',
                 ['verify solution', 'substitution', 'interval']),
            ]),
            ('Sketching Slope Fields', [
                ('Constructing a Slope Field',
                 'A slope field draws at each grid point a short segment whose slope is the '
                 'value the equation assigns there, so the field displays the direction of '
                 'every solution without the equation being solved.',
                 ['slope field', 'direction segment', 'grid']),
            ]),
            ('Reasoning Using Slope Fields', [
                ('Reading Solution Curves from a Slope Field',
                 'A solution curve follows the drawn segments tangentially, its inflection '
                 'points occur where the field gives a locally extreme slope, and a row of '
                 'constant segments along a horizontal line signals an equilibrium solution.',
                 ['solution curve', 'equilibrium', 'inflection']),
            ]),
            ('General Solutions by Separation of Variables', [
                ('Separation of Variables',
                 'When dy/dx can be written as g(x) h(y) with h(y) nonzero, separating the '
                 'variables and integrating both sides gives the general solution as an '
                 'equation in y and x, with the division by h(y) excluding the constant '
                 'solutions h(y) = 0 from that family.',
                 ['separation', 'general solution', 'implicit form']),
            ]),
            ('Particular Solutions with Initial Conditions', [
                ('Applying an Initial Condition',
                 'Substituting the initial condition into the general solution fixes the '
                 'arbitrary constant and yields the particular solution, which is valid on an '
                 'interval containing the initial point where the solution stays '
                 'differentiable.',
                 ['initial condition', 'particular solution', 'constant']),
            ]),
            ('Exponential Models with Differential Equations', [
                ('Solutions of dy/dt = ky',
                 'The solutions of dy/dt = ky are y = C e^(kt), growing for k > 0 and '
                 'decaying for k < 0, with doubling time or half-life equal to ln 2 divided '
                 'by the absolute value of k, which makes that one time determine the whole '
                 'model.',
                 ['exponential model', 'growth constant', 'half-life']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 8
    {
        'unit': 'Applications of Integration',
        'about': ('The integral used as a measuring instrument: average value, net change '
                  'and motion, area between curves in either variable, and volumes built from '
                  'cross sections, discs and washers.'),
        'sections': [],
        'topics': [
            ('Average Value of a Function', [
                ('The Average Value of a Continuous Function',
                 'The average value of f on [a, b] is the integral of f over [a, b] divided '
                 'by b - a, and for continuous f the mean value theorem for integrals '
                 'guarantees some c in [a, b] where f(c) equals that average.',
                 ['average value', 'integral mean', 'continuous']),
            ]),
            ('Position, Velocity and Acceleration Using Integrals', [
                ('Displacement and Distance from Velocity',
                 'The integral of v(t) from a to b gives displacement, the net change in '
                 'position, while the integral of |v(t)| gives total distance travelled, so '
                 'the two agree only when the velocity never changes sign on the interval.',
                 ['displacement', 'total distance', 'velocity integral']),
            ]),
            ('Accumulation Functions in Applied Contexts', [
                ('Net Change from a Rate',
                 'When r(t) is a rate of change, the integral of r from a to b is the net '
                 'change in the quantity over that interval, and adding the amount present at '
                 'a gives the quantity\'s value at b.',
                 ['net change', 'rate', 'initial amount']),
            ]),
            ('Area Between Curves as Functions of x', [
                ('Area Between Curves in x',
                 'For continuous curves with f(x) at least g(x) on [a, b], the area between '
                 'them is the integral of f - g over [a, b], and the upper curve must be '
                 'identified before integrating because a reversed difference gives the '
                 'negative area.',
                 ['area between curves', 'upper minus lower', 'x-integration']),
            ]),
            ('Area Between Curves as Functions of y', [
                ('Area Between Curves in y',
                 'Integrating with respect to y computes the integral of right(y) - left(y) '
                 'over the y-interval, which is the practical choice when the boundary curves '
                 'are more naturally described as x as a function of y.',
                 ['y-integration', 'right minus left', 'horizontal strips']),
            ]),
            ('Area Between Curves with More Than Two Intersections', [
                ('Splitting at Every Intersection',
                 'When the curves cross inside the interval, the region must be split at each '
                 'interior intersection and integrated piece by piece, because the identity of '
                 'the upper curve changes at every crossing.',
                 ['intersection points', 'split interval', 'upper curve']),
            ]),
            ('Volumes with Cross Sections: Squares and Rectangles', [
                ('Volumes with Square Cross Sections',
                 'If a solid has cross sections perpendicular to an axis that are squares of '
                 'side s(x), its volume is the integral of s(x)^2 over the axis interval, so '
                 'the geometry of the section alone fixes the integrand.',
                 ['cross section', 'square section', 'volume integral']),
            ]),
            ('Volumes with Cross Sections: Triangles and Semicircles', [
                ('Volumes with Triangular and Semicircular Sections',
                 'An equilateral triangle on base b has area (sqrt 3 / 4) b^2 and a semicircle '
                 'on diameter b has area (pi / 8) b^2, so each section type contributes its own '
                 'constant factor to the integrated area.',
                 ['equilateral triangle', 'semicircle', 'section area']),
            ]),
            ('Disc Method Around x- or y-Axis', [
                ('The Disc Method',
                 'Revolving the region between y = f(x) and the x-axis about the x-axis gives '
                 'a volume equal to pi times the integral of f(x)^2, because each slice '
                 'perpendicular to the axis is a disc whose radius is the height f(x).',
                 ['disc method', 'revolution', 'radius']),
            ]),
            ('Disc Method Around Other Axes', [
                ('Discs About a Shifted Axis',
                 'Revolving about a horizontal line y = k makes the radius |f(x) - k|, so the '
                 'integrand becomes pi times (f(x) - k)^2 and it is the distance to the axis, '
                 'not the function value, that is squared.',
                 ['shifted axis', 'radius', 'revolution']),
            ]),
            ('Washer Method Around x- or y-Axis', [
                ('The Washer Method',
                 'When the region between two curves is revolved, each slice is a washer with '
                 'volume pi (R^2 - r^2) dx, where R is the outer radius and r the inner '
                 'radius, and the inner radius must be subtracted because the hole removes '
                 'volume.',
                 ['washer method', 'outer radius', 'inner radius']),
            ]),
            ('Washer Method Around Other Axes', [
                ('Washers About a Line Other Than an Axis',
                 'Revolving about y = k gives pi times the integral of (R(x) - k)^2 - '
                 '(r(x) - k)^2, with both radii measured from the same line, and the larger '
                 'distance is always the outer radius regardless of the signs involved.',
                 ['shifted washer', 'outer minus inner', 'axis offset']),
            ]),
        ],
    },
]
