"""AP Calculus BC outline, in the shape ``scripts/course_pipeline.py`` expects.

The ten units follow the AP Calculus BC course framework as an *original* scope and
sequence dedicated to the public domain under CC0: unit weightings, unit names and topic
order follow the published framework, and every summary below is written for this
project rather than copied from any text. Each summary states a claim together with the
condition under which it holds, because the BC exam tests exactly those conditions —
which hypothesis of a test applies, where a formula is undefined, and where a limit of
the ratio test decides nothing.

Textbook position. OpenStax Calculus Volume 1, Volume 2 and Volume 3 all report
CC BY-NC-SA 4.0, so none may be a text anchor in this project: they are carried as
link-only study references and nothing is stored or quoted. No CC BY calculus textbook
exists in the OpenStax catalogue (checked 2026-11-10). ``TEXTBOOK`` therefore declares
``no_cc_by_anchor = True`` with that reason, every unit carries an empty ``sections``
list, and ``course_pipeline.py verify`` reports the anchoring check as SKIP with the
reason rather than a green tick the course has not earned.

The pack is generated: ``ap_calculus_bc.json`` is rebuilt by the pipeline from this
module and must never be hand-edited. The shipped ``ap_calculus`` course is a separate
pack and is not touched by this outline.
"""

from __future__ import annotations

ID = 'ap_calculus_bc'
TITLE = 'AP Calculus BC'
SUBJECT = 'Mathematics'
SUBJECT_KIND = 'mathematics'
EXPECTED_WEEKS = 36
COURSE_LINE = 'AP Calculus BC - Limits, Change, Coordinates and Series'
DESCRIPTION = (
    'The full AP Calculus BC sequence: limits and continuity; the derivative from its '
    'definition through the power, product, quotient, chain and implicit rules; '
    'contextual and analytical applications including related rates, L\'Hopital\'s rule, '
    'curve analysis and optimization; integration and accumulation, substitution, parts, '
    'partial fractions and improper integrals; differential equations with slope fields, '
    'Euler\'s method and the logistic model; areas, volumes and arc length; parametric, '
    'polar and vector-valued functions; and infinite sequences and series through Taylor '
    'polynomials, the Lagrange error bound and power series.'
)

TEXTBOOK = {
    'spine': '', 'supplements': [],
    'link_only_note': ('OpenStax Calculus Volumes 1-3 report CC BY-NC-SA 4.0 and are carried '
                       'as link-only study references: never stored or quoted.'),
    'no_cc_by_anchor': True,
    'reason': ('No CC BY calculus textbook exists in the OpenStax catalogue (checked '
               '2026-11-10; all three volumes are CC BY-NC-SA). The outline is an original '
               'CC0 scope and sequence and is not anchored to a textbook.'),
}

UNITS = [
    # ------------------------------------------------- exam weighting   4-7% --- 1
    {
        'unit': 'Limits and Continuity',
        'about': ('The entry unit: what a limit asserts, how one is established by a law, a '
                  'rewrite or a theorem, and what continuity adds once limits exist.'),
        'sections': [],
        'topics': [
            ('The Limit Idea', [
                ('Instantaneous Rate as a Limit',
                 'Instantaneous change is reached through average change, so the quotient '
                 '(f(a + h) - f(a))/h takes the indeterminate form 0/0 as h tends to 0 and '
                 'must be rewritten or estimated rather than evaluated by substitution.',
                 ['instantaneous rate', 'difference quotient', 'indeterminate']),
                ('Limit Notation and Two-Sided Limits',
                 'The statement lim_{x->a} f(x) = L means f(x) can be forced arbitrarily close '
                 'to L by taking x close to a but not equal to a, and the two-sided limit '
                 'exists exactly when both one-sided limits exist and are equal.',
                 ['limit notation', 'one-sided limit', 'two-sided']),
            ]),
            ('Limits from Several Representations', [
                ('Limits from Graphs, Tables and Multiple Representations',
                 'A graph, a table and an algebraic form of the same function must agree on '
                 'the limit wherever it exists, and a hole in the graph alongside an undefined '
                 'algebraic form is agreement rather than contradiction, because a limit '
                 'depends on nearby values and not on the value at the point.',
                 ['graphical limit', 'numerical limit', 'representations']),
            ]),
            ('Algebraic Properties of Limits', [
                ('The Limit Laws and Direct Substitution',
                 'If the limits of f and g at a exist then the limit of a sum, difference, '
                 'constant multiple or product is the corresponding combination of those '
                 'limits, the quotient law applies only when the denominator limit is '
                 'nonzero, and for a function continuous at a direct substitution gives the '
                 'limit exactly.',
                 ['limit laws', 'direct substitution', 'continuity']),
            ]),
            ('Algebraic Manipulation for Limits', [
                ('Rewriting Quotients That Give 0/0',
                 'If f(x) = g(x) for every x near a except possibly at a, then their limits at '
                 'a agree, so factoring, multiplying by a conjugate or combining fractions '
                 'can cancel the factor responsible for the 0/0 form and leave a quotient '
                 'that substitution evaluates.',
                 ['factor and cancel', 'conjugate', 'equivalence']),
            ]),
            ('Procedure Selection and the Squeeze Theorem', [
                ('Selecting a Limit Procedure',
                 'Procedures are tried in order of strength - direct substitution, then an '
                 'algebraic rewrite, then the squeeze theorem or a numerical estimate - and '
                 'only a law, an identity or a theorem establishes a limit, since a table can '
                 'always be too coarse to exclude a nearby jump.',
                 ['procedure selection', 'strategy', 'justification']),
                ('The Squeeze Theorem',
                 'If g(x) <= f(x) <= h(x) for all x near a and lim g = lim h = L, then '
                 'lim f = L at a, and a bounded factor multiplied by a quantity tending to '
                 'zero therefore has limit zero even when no product law applies.',
                 ['squeeze theorem', 'bounded', 'sandwich']),
            ]),
            ('Types of Discontinuity', [
                ('Removable, Jump and Infinite Discontinuities',
                 'A discontinuity at a is removable when the two-sided limit exists but f(a) '
                 'is missing or different, a jump when both one-sided limits exist and differ, '
                 'and infinite when at least one one-sided limit is unbounded.',
                 ['discontinuity types', 'jump', 'infinite']),
            ]),
            ('Continuity at a Point and on an Interval', [
                ('The Continuity Conditions',
                 'f is continuous at a exactly when f(a) is defined, lim_{x->a} f(x) exists '
                 'and the two are equal, and f is continuous on a closed interval when it is '
                 'continuous at every interior point and its one-sided limits at the endpoints '
                 'equal the endpoint values.',
                 ['continuity', 'three conditions', 'endpoint']),
            ]),
            ('Removing Discontinuities', [
                ('Repairing a Removable Discontinuity',
                 'A discontinuity at a is removable exactly when lim_{x->a} f(x) = L exists, '
                 'and redefining f(a) = L then makes f continuous at a while leaving every '
                 'other value unchanged, whereas a jump or an infinite discontinuity admits no '
                 'such repair.',
                 ['removable discontinuity', 'redefine value', 'continuous extension']),
            ]),
            ('Infinite Limits and Asymptotes', [
                ('Infinite Limits and Vertical Asymptotes',
                 'lim_{x->a} f(x) = inf means f(x) exceeds any bound once x is close enough to '
                 'a, and x = a is a vertical asymptote exactly when some one-sided limit at a '
                 'is infinite, which for a rational function means a zero of the denominator '
                 'that the numerator does not cancel.',
                 ['infinite limit', 'vertical asymptote', 'unbounded']),
                ('Limits at Infinity and Horizontal Asymptotes',
                 'lim_{x->inf} f(x) = L means f(x) stays arbitrarily close to L for all '
                 'sufficiently large x, and y = L is then a horizontal asymptote; for a '
                 'rational function the limit follows from comparing degrees, with a '
                 'lower-degree numerator forcing the limit to zero.',
                 ['limit at infinity', 'horizontal asymptote', 'degree comparison']),
            ]),
            ('The Intermediate Value Theorem', [
                ('The Intermediate Value Theorem',
                 'If f is continuous on [a, b] and N lies strictly between f(a) and f(b), then '
                 'some c in (a, b) satisfies f(c) = N, so continuity guarantees that the value '
                 'is attained while saying nothing about how many such c exist or where they '
                 'lie.',
                 ['intermediate value', 'existence', 'continuity']),
            ]),
        ],
    },
    # ------------------------------------------------- exam weighting   4-7% --- 2
    {
        'unit': 'Differentiation: Definition and Fundamental Properties',
        'about': ('The derivative as a limit and as a rule: average versus instantaneous rate, '
                  'the definition and its notation, what differentiability costs, and the '
                  'derivative formulas for powers, trigonometric, exponential and logarithmic '
                  'functions.'),
        'sections': [],
        'topics': [
            ('Average and Instantaneous Rates of Change', [
                ('Average and Instantaneous Rates of Change',
                 'The average rate of change of f on [a, b] is (f(b) - f(a))/(b - a), the slope '
                 'of the secant through the endpoints, and the instantaneous rate at a is the '
                 'limit of that quotient as the interval shrinks, which exists only when the '
                 'left-hand and right-hand quotients agree.',
                 ['average rate', 'secant slope', 'instantaneous rate']),
            ]),
            ('The Derivative Definition and Notation', [
                ('The Derivative at a Point and Its Notation',
                 'f is differentiable at a exactly when lim_{h->0} (f(a + h) - f(a))/h exists, '
                 'and that value, written f\'(a) or dy/dx at x = a, is the slope of the tangent '
                 'line there, carrying the units of f divided by the units of x.',
                 ['derivative definition', 'notation', 'tangent slope']),
            ]),
            ('Estimating Derivatives', [
                ('Estimating a Derivative from Data',
                 'A derivative is estimated from a table by the symmetric quotient '
                 '(f(a + h) - f(a - h))/(2h), or from a graph by the slope of a secant through '
                 'two nearby points, and either estimate is limited by the data rather than by '
                 'the arithmetic.',
                 ['numerical derivative', 'symmetric quotient', 'estimate']),
            ]),
            ('Differentiability and Continuity', [
                ('Differentiability Implies Continuity',
                 'Differentiability at a point implies continuity there, while continuity does '
                 'not imply differentiability: |x| at 0 has a corner and x^(1/3) at 0 a '
                 'vertical tangent, and neither has a limiting secant slope.',
                 ['differentiability', 'continuity', 'corner']),
            ]),
            ('Power and Linearity Rules', [
                ('The Power Rule',
                 'For every constant real exponent n, d/dx x^n = n x^(n-1) on every interval '
                 'where x^n is defined and differentiable, which for negative and fractional '
                 'exponents restricts the domain to x > 0.',
                 ['power rule', 'exponent', 'domain']),
                ('Constant, Sum, Difference and Constant-Multiple Rules',
                 'The derivative of a constant is zero and differentiation is linear, so '
                 '(c f +- g)\' = c f\' +- g\' wherever both derivatives exist, which is what '
                 'lets a polynomial be differentiated term by term.',
                 ['linearity', 'constant rule', 'sum rule']),
            ]),
            ('Derivatives of Sine, Cosine, e^x and ln x', [
                ('The Derivatives of Sine and Cosine',
                 'd/dx sin x = cos x and d/dx cos x = -sin x for every real x, and the pair '
                 'cycles with period four through -sin x and -cos x, so the fourth derivative of '
                 'either function is the function itself.',
                 ['sine', 'cosine', 'cycle']),
                ('The Derivatives of e^x and ln x',
                 'd/dx e^x = e^x for every real x because e is the base whose exponential is its '
                 'own derivative, and d/dx ln x = 1/x for x > 0, with the chain rule extending '
                 'them to e^(u)u\' and u\'/u wherever u is nonzero.',
                 ['exponential', 'natural log', 'chain rule']),
            ]),
            ('The Product and Quotient Rules', [
                ('The Product Rule',
                 'If f and g are differentiable at x then (fg)\'(x) = f\'(x)g(x) + f(x)g\'(x), '
                 'and the rule is required because the derivative of a product is not the '
                 'product of the derivatives unless one factor is constant.',
                 ['product rule', 'two factors', 'differentiable']),
                ('The Quotient Rule',
                 'If f and g are differentiable at x with g(x) nonzero then '
                 '(f/g)\'(x) = (f\'(x)g(x) - f(x)g\'(x))/g(x)^2, and the subtraction makes the '
                 'order of the numerator terms significant.',
                 ['quotient rule', 'nonzero denominator', 'order']),
            ]),
            ('Derivatives of the Remaining Trigonometric Functions', [
                ('Tangent, Cotangent, Secant and Cosecant Derivatives',
                 'd/dx tan x = sec^2 x and d/dx sec x = sec x tan x hold where cos x is nonzero, '
                 'while d/dx cot x = -csc^2 x and d/dx csc x = -csc x cot x hold where sin x is '
                 'nonzero, so each formula is valid only on the domain of the function it '
                 'differentiates.',
                 ['tangent', 'secant', 'cosecant']),
            ]),
        ],
    },
    # ------------------------------------------------- exam weighting   4-7% --- 3
    {
        'unit': 'Differentiation: Composite, Implicit and Inverse Functions',
        'about': ('Differentiating whatever is built out of other functions: compositions by '
                  'the chain rule, curves given implicitly, inverse functions and their '
                  'reciprocals of slope, and what repeated differentiation records.'),
        'sections': [],
        'topics': [
            ('The Chain Rule', [
                ('The Chain Rule',
                 'If g is differentiable at x and f is differentiable at g(x), then '
                 'd/dx f(g(x)) = f\'(g(x)) g\'(x), so the outer derivative is evaluated at the '
                 'inner function and multiplied by the inner derivative, with one application '
                 'per layer of composition.',
                 ['chain rule', 'composition', 'inner derivative']),
            ]),
            ('Implicit Differentiation', [
                ('Implicit Differentiation',
                 'If y is defined implicitly by an equation in x and y, differentiating both '
                 'sides with respect to x while treating y as a differentiable function of x '
                 'produces an equation linear in dy/dx, provided the tangent at the point is '
                 'not vertical.',
                 ['implicit', 'dy/dx', 'slope']),
            ]),
            ('Derivatives of Inverse Functions', [
                ('The Inverse Function Derivative Rule',
                 'If f is differentiable and one-to-one near a with f\'(a) nonzero, then its '
                 'inverse is differentiable at b = f(a) with (f^-1)\'(b) = 1/f\'(a), so slopes at '
                 'mirrored points are reciprocals and a horizontal tangent in f becomes a '
                 'vertical tangent in its inverse.',
                 ['inverse function', 'reciprocal slope', 'one-to-one']),
                ('Derivatives of the Inverse Trigonometric Functions',
                 'd/dx arcsin x = 1/sqrt(1 - x^2) and d/dx arccos x = -1/sqrt(1 - x^2) hold on '
                 '|x| < 1, while d/dx arctan x = 1/(1 + x^2) and d/dx arccot x = -1/(1 + x^2) '
                 'hold for every real x, each one following from the inverse rule on a chosen '
                 'branch.',
                 ['arcsin', 'arctan', 'inverse trig']),
            ]),
            ('Procedure Selection', [
                ('Choosing a Differentiation Procedure',
                 'The structure of the expression selects the rule - a sum term by term, a '
                 'product by the product rule, a quotient by the quotient rule, a composition '
                 'by the chain rule - and an equation that cannot be solved for y is '
                 'differentiated implicitly instead of after isolating y.',
                 ['procedure selection', 'structure', 'strategy']),
            ]),
            ('Higher-Order Derivatives', [
                ('Higher-Order Derivatives and Their Meaning',
                 'The second derivative f\'\' is the derivative of f\', the n-th derivative exists '
                 'at a only when every lower one exists and is differentiable near a, and f\'\' '
                 'measures how the slope itself is changing, which in a motion model is '
                 'acceleration.',
                 ['second derivative', 'higher order', 'acceleration']),
            ]),
        ],
    },
    # ------------------------------------------------- exam weighting   6-9% --- 4
    {
        'unit': 'Contextual Applications of Differentiation',
        'about': ('Derivatives read as rates in a situation: interpretation with units, motion '
                  'along a line, related rates, the tangent line as a local model, and '
                  "L'Hopital's rule for indeterminate quotients."),
        'sections': [],
        'topics': [
            ('Derivative Meaning in Context', [
                ('Interpreting a Derivative in Context',
                 'In a context the derivative is the rate of change of the modelled quantity '
                 'with respect to the independent variable, carrying the units of the output '
                 'over the units of the input, so its sign gives direction, its magnitude gives '
                 'how fast, a zero derivative marks a stationary instant rather than necessarily '
                 'an extremum, and a marginal rate such as marginal cost describes the next '
                 'unit rather than an average over an interval.',
                 ['interpretation', 'marginal rate', 'units']),
            ]),
            ('Straight-Line Motion', [
                ('Position, Velocity and Acceleration',
                 'For motion along a line v(t) = s\'(t) and a(t) = v\'(t), so speed is |v(t)|, a '
                 'particle speeds up exactly where velocity and acceleration share a sign, and '
                 'a zero velocity with nonzero acceleration is a momentary stop where the '
                 'direction reverses.',
                 ['motion', 'velocity', 'acceleration']),
            ]),
            ('Related Rates', [
                ('Setting Up a Related Rate',
                 'A related-rate problem begins with an equation among the quantities, '
                 'differentiates both sides with respect to time so every derivative becomes a '
                 'rate, and substitutes the instantaneous values only afterwards, because the '
                 'relation among the rates must be differentiated before the numbers are fixed.',
                 ['related rates', 'differentiate in time', 'chain rule']),
                ('Solving a Related Rate',
                 'The unknown rate is isolated in the differentiated relation and evaluated at '
                 'the instant in question, then checked for sign and units, since a length that '
                 'is decreasing must give a negative rate even when the geometry is described '
                 'with positive lengths.',
                 ['solve rate', 'units', 'sign check']),
            ]),
            ('Local Linearity and Linearization', [
                ('Local Linearity and the Tangent Line Approximation',
                 'Near a point of differentiability the tangent line approximates the curve, '
                 'f(x) is approximately f(a) + f\'(a)(x - a), and the approximation is local '
                 'because its error vanishes faster than |x - a| while the second derivative '
                 'decides whether the estimate is an over- or underestimate.',
                 ['linearization', 'tangent line', 'locality']),
            ]),
            ("L'Hopital's Rule", [
                ("L'Hopital's Rule and Its Indeterminate Forms",
                 'If f and g are differentiable near a with g\' nonzero there and the quotient '
                 'has the form 0/0 or inf/inf, then lim f/g = lim f\'/g\' whenever the latter '
                 'limit exists or is infinite, whereas the forms 0*inf, inf - inf, 0^0, 1^inf '
                 'and inf^0 must first be rewritten as a quotient or a logarithm before the '
                 'rule can apply.',
                 ["l'hopital", 'indeterminate form', 'derivative ratio']),
            ]),
        ],
    },
    # ------------------------------------------------- exam weighting  8-11% --- 5
    {
        'unit': 'Analytical Applications of Differentiation',
        'about': ('What the first and second derivatives reveal about a function on an '
                  'interval: existence theorems, monotonicity, concavity, extrema, the shape of '
                  'a graph, and the optimum of a modelled quantity.'),
        'sections': [],
        'topics': [
            ('The Mean Value Theorem', [
                ('The Mean Value Theorem',
                 'If f is continuous on [a, b] and differentiable on (a, b), then some c in '
                 '(a, b) satisfies f\'(c) = (f(b) - f(a))/(b - a), so some tangent is parallel '
                 'to the secant through the endpoints, and both hypotheses are needed since a '
                 'corner allows no parallel tangent.',
                 ['mean value theorem', 'secant', 'existence']),
            ]),
            ('Extrema and Critical Points', [
                ('Absolute Extrema and the Extreme Value Theorem',
                 'A function continuous on a closed interval attains both an absolute maximum '
                 'and an absolute minimum there, and the conclusion fails once the interval is '
                 'open, since 1/x on (0, 1] is unbounded and attains no maximum.',
                 ['extreme value', 'absolute extremum', 'closed interval']),
                ('Local Extrema and Critical Points',
                 'A local extremum at an interior point where f is differentiable forces '
                 'f\' = 0 there, so the critical points - zeros of f\' and points where f\' does '
                 'not exist - are the only candidates, although a critical point need not be an '
                 'extremum, as x^3 at 0 shows.',
                 ['critical point', 'local extremum', 'necessary condition']),
            ]),
            ('Increase, Decrease and the First Derivative Test', [
                ('Intervals of Increase and Decrease',
                 'On an interval where f\' > 0 the function is increasing and where f\' < 0 it is '
                 'decreasing, and the sign of f\' can change only at a zero or a point where it '
                 'is undefined, so those points alone separate the monotone intervals.',
                 ['increasing', 'decreasing', 'sign chart']),
                ('The First Derivative Test',
                 'At a critical point c the function has a local maximum where f\' changes from '
                 'positive to negative, a local minimum where it changes from negative to '
                 'positive, and neither where the sign of f\' does not change.',
                 ['first derivative test', 'sign change', 'local maximum']),
            ]),
            ('The Candidates Test', [
                ('The Candidates Test',
                 'The absolute extrema of a continuous function on a closed interval occur only '
                 'at its critical points inside the interval or at the two endpoints, so '
                 'comparing f at that finite list identifies the global maximum and minimum '
                 'without any sign analysis.',
                 ['candidates test', 'endpoints', 'absolute extremum']),
            ]),
            ('Concavity and the Second Derivative', [
                ('Concavity and Points of Inflection',
                 'A graph is concave up where f\'\' > 0 and concave down where f\'\' < 0, and a '
                 'point of inflection requires the concavity to change across it, so f\'\' = 0 '
                 'alone is insufficient and an inflection can also occur where f\'\' is '
                 'undefined.',
                 ['concavity', 'inflection', 'sign change']),
                ('The Second Derivative Test',
                 'Where f\'(c) = 0, a positive f\'\'(c) makes c a local minimum and a negative '
                 'f\'\'(c) makes it a local maximum, while f\'\'(c) = 0 is inconclusive and '
                 'returns the question to the first derivative test.',
                 ['second derivative test', 'inconclusive', 'local extremum']),
            ]),
            ('Connecting f, f\' and f\'\'', [
                ('Reading Slopes from the Graph of f',
                 'The graph of f\' records the slope of f: positive where f rises, negative '
                 'where f falls, zero at horizontal tangents, and greatest at the input where f '
                 'is steepest upwards, so a local extremum of f\' marks a change in how fast f '
                 'is climbing.',
                 ['graph reading', 'derivative graph', 'slope']),
                ('Reading f from the Graph of Its Derivative',
                 'The sign of f\' gives the intervals where f increases or decreases, its zeros '
                 'give the critical points and, with its sign changes, the extrema of f, while '
                 'the increase or decrease of f\' itself gives the concavity of f, and f is then '
                 'determined only up to a vertical translation until one function value is '
                 'known.',
                 ['antiderivative graph', 'extrema', 'concavity']),
            ]),
            ('Optimization', [
                ('Setting Up an Optimization Problem',
                 'An optimization problem names the objective, uses the constraint to express it '
                 'as a function of one variable, and records the domain the context permits '
                 'before differentiating, since a critical point outside the physical domain is '
                 'not a solution.',
                 ['optimization', 'constraint', 'domain']),
                ('Justifying an Optimum',
                 'A candidate optimum is confirmed by the candidates test on a closed domain or, '
                 'on an open domain, by a sign change of f\' or by the second derivative test, '
                 'because on a closed interval an endpoint can beat every interior critical '
                 'point.',
                 ['justification', 'closed domain', 'endpoint']),
            ]),
            ('Implicit Relations', [
                ('Horizontal and Vertical Tangents on Implicit Curves',
                 'On an implicitly defined curve dy/dx vanishes where its numerator does, '
                 'giving a horizontal tangent, and fails to exist where its denominator '
                 'vanishes with a nonzero numerator, giving a vertical tangent, provided the '
                 'point satisfies the original equation.',
                 ['implicit curve', 'tangent direction', 'numerator denominator']),
            ]),
        ],
    },
    # ------------------------------------------------- exam weighting 17-20% --- 6
    {
        'unit': 'Integration and Accumulation of Change',
        'about': ('The largest unit: accumulation as a limit of sums, the fundamental theorem '
                  'in both directions, the properties and antiderivative rules that make '
                  'evaluation possible, and the BC techniques for integrands that no basic rule '
                  'reaches.'),
        'sections': [],
        'topics': [
            ('Accumulation and Riemann Sums', [
                ('Accumulated Change from a Rate',
                 'If r(t) is the rate at which a quantity changes, the accumulated change on '
                 '[a, b] is the limit of sums of the form sum r(t_k) dt, which is the area under '
                 'the graph when r is nonnegative and the net signed area otherwise.',
                 ['accumulation', 'rate', 'net change']),
                ('Left, Right and Midpoint Riemann Sums',
                 'A Riemann sum multiplies each subinterval width by the rate sampled at its '
                 'left endpoint, its right endpoint or its midpoint, and the three agree in the '
                 'limit although at finite n a left sum underestimates an increasing rate while '
                 'a right sum overestimates it.',
                 ['riemann sum', 'sampling point', 'overestimate']),
            ]),
            ('Summation and Integral Notation', [
                ('Sigma Notation and the Definite Integral',
                 'Sigma notation writes a sum as sum_{k=1}^{n} a_k, with the closed forms for '
                 'sum k and sum k^2 used to evaluate a Riemann sum before the limit is taken, '
                 'and the definite integral is that limit as the widest subinterval tends to '
                 'zero, existing only when every partition and every sample choice gives the '
                 'same value.',
                 ['sigma notation', 'definite integral', 'integrability']),
            ]),
            ('The Fundamental Theorem and Accumulation Functions', [
                ('The Accumulation Function and the Fundamental Theorem',
                 'If f is continuous on an interval containing a, then '
                 'g(x) = int_a^x f(t) dt satisfies g\'(x) = f(x) there, so differentiation '
                 'undoes integration at a variable upper limit, and a differentiable limit u(x) '
                 'adds the factor u\'(x) by the chain rule.',
                 ['fundamental theorem', 'accumulation function', 'chain rule']),
                ('Behaviour of an Accumulation Function',
                 'Because g\' = f, an accumulation function increases where f is positive, has a '
                 'local extremum where f changes sign, and is concave up where f is increasing, '
                 'so the shape of g is read entirely from the graph of f.',
                 ['accumulation shape', 'extrema', 'concavity']),
            ]),
            ('Properties of Definite Integrals', [
                ('Properties of the Definite Integral',
                 'For integrable functions the integral is linear, additive over adjacent '
                 'intervals, zero on an interval of zero width, and changes sign when its limits '
                 'are exchanged, which is what allows a region to be split and recombined '
                 'across subintervals.',
                 ['integral properties', 'additivity', 'linearity']),
            ]),
            ('Evaluating Definite Integrals', [
                ('The Fundamental Theorem, Part 2',
                 'If f is continuous on [a, b] and F is any antiderivative of f there, then '
                 'int_a^b f(x) dx = F(b) - F(a), which turns a limit of sums into two '
                 'evaluations and fails if f is not continuous across the whole interval.',
                 ['evaluation theorem', 'antiderivative', 'continuity']),
            ]),
            ('Antiderivatives and Indefinite Integrals', [
                ('Antiderivatives, the Constant of Integration and Basic Rules',
                 'An antiderivative of f on an interval is a function F with F\' = f there, any '
                 'two of them differ by a constant on that interval so the indefinite integral '
                 'carries + C, and the power rule holds for every constant n except n = -1, '
                 'where the antiderivative is ln|x|.',
                 ['antiderivative', 'constant of integration', 'power rule']),
            ]),
            ('Integration by Substitution', [
                ('Integration by Substitution',
                 'With u = g(x) and du = g\'(x) dx, the chain rule read backwards gives '
                 'int f(g(x)) g\'(x) dx = int f(u) du, so the method applies only when the inner '
                 'derivative appears as a factor, possibly up to a constant multiple.',
                 ['substitution', 'chain rule reversed', 'inner derivative']),
                ('Substitution with Changed Limits',
                 'In a definite integral the limits must be converted to u-values when the '
                 'substitution is made, since x-limits left on a u-antiderivative evaluate the '
                 'wrong endpoints, and the substitution must be one-to-one on the interval of '
                 'integration.',
                 ['change of limits', 'definite integral', 'one-to-one']),
            ]),
            ('Long Division and Completing the Square', [
                ('Long Division and Completing the Square',
                 'A rational integrand whose numerator degree is at least the denominator '
                 'degree is rewritten by polynomial division as a polynomial plus a proper '
                 'fraction, and a quadratic denominator carrying a linear term is completed to '
                 '(x - h)^2 + k so that it matches an arctangent or a logarithm formula.',
                 ['long division', 'completing the square', 'rewrite']),
            ]),
            ('Integration by Parts', [
                ('Integration by Parts',
                 'Integration by parts restates the product rule as int u dv = uv - int v du, '
                 'and it is the right choice when the new integral is simpler than the original; '
                 'applying it twice reduces x^2 e^x, while on e^x sin x it returns the original '
                 'integral and the equation is solved for it instead.',
                 ['integration by parts', 'product rule', 'repeated']),
            ]),
            ('Linear Partial Fractions', [
                ('Linear Partial Fractions',
                 'A proper rational function whose denominator factors into distinct linear '
                 'factors decomposes into A/(x - r) terms, a repeated factor (x - r)^k '
                 'contributes one term for each power up to k, and every term then integrates to '
                 'a logarithm or to a negative power.',
                 ['partial fractions', 'linear factors', 'repeated factor']),
            ]),
            ('Improper Integrals', [
                ('Improper Integrals',
                 'An integral over an infinite interval or with an unbounded integrand is '
                 'defined as a limit of proper integrals at the offending endpoint or interior '
                 'singularity, converging exactly when that limit is finite, so int_1^inf '
                 'x^(-p) dx converges for p > 1 and int_0^1 x^(-p) dx converges for p < 1.',
                 ['improper integral', 'limit', 'convergence']),
            ]),
            ('Technique Selection', [
                ('Selecting an Integration Technique',
                 'The integrand is inspected before a rule is chosen: a composition carrying its '
                 'inner derivative suggests substitution, a product of unlike types suggests '
                 'parts, a proper rational function suggests partial fractions, and a quadratic '
                 'denominator suggests completing the square.',
                 ['technique selection', 'integrand structure', 'strategy']),
            ]),
        ],
    },
    # ------------------------------------------------- exam weighting   6-9% --- 7
    {
        'unit': 'Differential Equations',
        'about': ('Equations about rates: how to build one from a sentence, verify a proposed '
                  'solution, read it qualitatively through a slope field, approximate it '
                  'numerically, and solve the separable, exponential and logistic models '
                  'explicitly.'),
        'sections': [],
        'topics': [
            ('Modelling with Differential Equations', [
                ('Writing a Differential Equation from a Context',
                 'A verbal rate statement becomes a differential equation by replacing the rate '
                 'of change with a derivative and proportionality with a constant multiple, so '
                 'a population growing at a rate proportional to its size satisfies '
                 'dP/dt = kP with k carrying the units of inverse time.',
                 ['modelling', 'proportionality', 'translate rate']),
            ]),
            ('Verifying Solutions', [
                ('Verifying a Solution by Substitution',
                 'A function is a solution of a differential equation on an interval exactly '
                 'when substituting it and its derivatives into the equation produces an '
                 'identity for every x in that interval, which is the only accepted '
                 'verification.',
                 ['verification', 'substitution', 'identity']),
            ]),
            ('Slope Fields', [
                ('Sketching and Reading a Slope Field',
                 'A slope field plots a segment of slope dy/dx at each sample point, computed '
                 'from the equation alone, so a solution curve must stay tangent to the segment '
                 'where it passes, a horizontal segment marks a constant solution, and a curve '
                 'drawn through the field is consistent with the equation rather than a proof of '
                 'a formula.',
                 ['slope field', 'solution curve', 'equilibrium']),
            ]),
            ("Euler's Method", [
                ("Euler's Method",
                 "Euler's method advances a solution along its tangent line for one step of "
                 'size h, using y_{n+1} = y_n + h f(x_n, y_n), so the approximation improves as '
                 'h shrinks but drifts from the true curve wherever the solution bends.',
                 ['euler method', 'numerical solution', 'step size']),
            ]),
            ('Separation of Variables', [
                ('Separation of Variables and Particular Solutions',
                 'A separable equation dy/dx = f(x)g(y) is solved by dividing so that every '
                 'y-term sits with dy and every x-term with dx, integrating both sides, and '
                 'fixing the single constant with the initial condition, while the division is '
                 'valid only where g(y) is nonzero, so the constant solutions at the zeros of g '
                 'must be recorded separately.',
                 ['separation', 'initial condition', 'zero division']),
            ]),
            ('Exponential Models', [
                ('Exponential Growth and Decay Models',
                 'The equation dy/dt = ky has the solution y = C e^(kt), growing for positive k '
                 'and decaying for negative k, and a doubling time or half-life T fixes the '
                 'constant through k = ln 2 / T with the sign of T matching the direction of '
                 'change.',
                 ['exponential model', 'rate constant', 'half life']),
            ]),
            ('Logistic Models', [
                ('The Logistic Model and Its Point of Inflection',
                 'The logistic equation dP/dt = kP(1 - P/K) has carrying capacity K, so a '
                 'solution starting between 0 and K increases towards K without reaching it in '
                 'finite time, and its growth rate is greatest at P = K/2, where the solution '
                 'also changes concavity.',
                 ['logistic', 'carrying capacity', 'inflection']),
            ]),
        ],
    },
    # ------------------------------------------------- exam weighting   6-9% --- 8
    {
        'unit': 'Applications of Integration',
        'about': ('Integrals answering geometric and physical questions: average value, motion '
                  'and net change from rates, areas between curves, volumes from cross '
                  'sections, discs and washers, and arc length.'),
        'sections': [],
        'topics': [
            ('Average Value', [
                ('The Average Value of a Function',
                 'The average value of a continuous f on [a, b] is (1/(b - a)) int_a^b f(x) dx, '
                 'the height of the rectangle whose signed area over the interval equals the '
                 'integral, and continuity guarantees that f actually attains this value '
                 'somewhere on [a, b].',
                 ['average value', 'mean height', 'attainment']),
            ]),
            ('Motion with Integrals', [
                ('Position, Velocity and Acceleration with Integrals',
                 'The integral of velocity over [a, b] is the displacement s(b) - s(a) while the '
                 'integral of |v| is the distance travelled, so recovering position requires an '
                 'initial value and reads s(b) = s(a) + int_a^b v(t) dt.',
                 ['displacement', 'distance travelled', 'initial value']),
            ]),
            ('Accumulation in Applied Contexts', [
                ('Net Change in an Applied Model',
                 'For any quantity whose rate of change is known, the net change over an '
                 'interval is the integral of that rate, which is why a tank volume, a '
                 'population and a bank balance are all handled as net change problems with the '
                 'units of the rate times the units of time.',
                 ['net change', 'rate integral', 'applied']),
            ]),
            ('Area Between Curves', [
                ('Area Between Curves in x and in y',
                 'The area between two curves is int (upper - lower) dx when the region is '
                 'sliced vertically and int (right - left) dy when it is sliced horizontally, '
                 'and the correct slicing is the one that keeps a single pair of boundary '
                 'curves across the whole region.',
                 ['area between curves', 'slicing', 'upper lower']),
                ('Regions with More Than Two Intersections',
                 'When the boundary curves meet more than twice, the region is split at every '
                 'interior intersection and the integral of (upper - lower) is taken piecewise, '
                 'because which curve lies on top can change from one piece to the next.',
                 ['intersections', 'split region', 'piecewise']),
            ]),
            ('Volumes by Cross Section', [
                ('Square and Rectangular Cross Sections',
                 'For a solid whose cross sections perpendicular to an axis are squares on a '
                 'base of length b(x), the volume is int b(x)^2 dx, and rectangular sections '
                 'require the second side length as a function of x as well.',
                 ['cross sections', 'squares', 'volume']),
                ('Triangular and Semicircular Cross Sections',
                 'Cross sections that are equilateral triangles or semicircles on a base of '
                 'length b(x) have areas (sqrt 3 / 4) b(x)^2 and (pi / 8) b(x)^2 respectively, '
                 'so the volume is that area integrated along the axis.',
                 ['triangles', 'semicircles', 'cross section area']),
            ]),
            ('The Disc Method', [
                ('The Disc Method about Either Axis',
                 'Revolving a region that reaches from an axis out to a curve sweeps discs whose '
                 'radius is the distance to the axis, so the volume is int pi f(x)^2 dx about '
                 'the x-axis and int pi g(y)^2 dy about the y-axis, provided every cross section '
                 'is a full disc.',
                 ['disc method', 'axis of revolution', 'radius']),
            ]),
            ('The Washer Method', [
                ('The Washer Method about Either Axis',
                 'When the region does not reach the axis of revolution, each cross section is a '
                 'washer of area pi (R^2 - r^2), so the volume is the integral of that area '
                 'along the axis with R and r the distances from the axis to the outer and inner '
                 'curves.',
                 ['washer method', 'outer inner', 'gap from axis']),
            ]),
            ('Arc Length', [
                ('Arc Length and Distance Travelled',
                 'The length of a curve y = f(x) with continuous derivative from a to b is '
                 'int_a^b sqrt(1 + f\'(x)^2) dx, and it equals the distance travelled only when '
                 'the motion follows that curve exactly once without reversing direction.',
                 ['arc length', 'smooth curve', 'distance']),
            ]),
        ],
    },
    # ------------------------------------------------- exam weighting 11-12% --- 9
    {
        'unit': 'Parametric Equations, Polar Coordinates and Vector-Valued Functions',
        'about': ('Curves described by a parameter rather than by y as a function of x: '
                  'parametric slopes and arc length, vector-valued motion, and area in polar '
                  'coordinates.'),
        'sections': [],
        'topics': [
            ('Parametric Equations', [
                ('Defining and Differentiating Parametric Equations',
                 'A parametric curve (x(t), y(t)) has slope dy/dx = (dy/dt)/(dx/dt) wherever '
                 'dx/dt is nonzero, so the tangent is vertical where dx/dt vanishes with dy/dt '
                 'nonzero and the quotient is undefined where both vanish.',
                 ['parametric', 'slope', 'vertical tangent']),
                ('Second Derivatives of Parametric Curves',
                 'The second derivative of a parametric curve is '
                 'd^2y/dx^2 = (d/dt (dy/dx))/(dx/dt), not the quotient of the second '
                 'derivatives, because dy/dx is a function of t that must be differentiated with '
                 'respect to t and then divided by dx/dt.',
                 ['second derivative', 'parametric', 'concavity']),
            ]),
            ('Arc Length of Parametric Curves', [
                ('Arc Length of a Parametric Curve',
                 'The length of a parametric curve traced exactly once on [t1, t2] is '
                 'int sqrt((dx/dt)^2 + (dy/dt)^2) dt, and the formula requires continuous '
                 'derivatives and a single traversal, since a retraced arc is counted twice.',
                 ['arc length', 'parametric', 'single traversal']),
            ]),
            ('Vector-Valued Functions', [
                ('Defining and Differentiating Vector-Valued Functions',
                 'A vector-valued function r(t) = <x(t), y(t)> is differentiable exactly when '
                 'both components are, and r\'(t) = <x\'(t), y\'(t)> is tangent to the path at '
                 'r(t) whenever it is nonzero.',
                 ['vector function', 'componentwise', 'tangent vector']),
                ('Integrating Vector-Valued Functions',
                 'A vector-valued function is integrated componentwise, '
                 'int r(t) dt = <int x dt, int y dt> + C, and the constant of integration is '
                 'itself a vector because the position is determined only up to a translation.',
                 ['componentwise integral', 'vector constant', 'antiderivative']),
                ('Motion with Vector-Valued Functions',
                 'For a particle with position vector r(t), velocity is r\'(t), acceleration is '
                 'r\'\'(t) and speed is the magnitude |r\'(t)| rather than any component, while '
                 'displacement over an interval is the integral of the velocity vector.',
                 ['velocity vector', 'speed', 'displacement']),
            ]),
            ('Polar Coordinates', [
                ('Polar Coordinates and Differentiation in Polar Form',
                 'A polar curve r = f(theta) has slope '
                 'dy/dx = (f\'(theta) sin theta + f(theta) cos theta)/'
                 '(f\'(theta) cos theta - f(theta) sin theta) wherever that denominator is '
                 'nonzero, and the curve passes through the pole where f(theta) = 0.',
                 ['polar', 'slope', 'pole']),
                ('Area of a Polar Region',
                 'The area swept by r = f(theta) from alpha to beta is '
                 '1/2 int f(theta)^2 dtheta, valid when the curve is traced exactly once on that '
                 'interval so that no sector is counted twice.',
                 ['polar area', 'sector', 'single traversal']),
            ]),
            ('Area Between Polar Curves', [
                ('Area Between Two Polar Curves',
                 'The area between an outer curve r = f(theta) and an inner curve r = g(theta) '
                 'over a common angular interval is 1/2 int (f^2 - g^2) dtheta, with the '
                 'interval cut at the angles where the curves meet.',
                 ['area between curves', 'polar', 'intersection angles']),
            ]),
        ],
    },
    # ------------------------------------------------- exam weighting 17-18% --- 10
    {
        'unit': 'Infinite Sequences and Series',
        'about': ('When an infinite sum has a finite value: the convergence tests and what each '
                  'one can and cannot decide, absolute versus conditional convergence, error '
                  'bounds, and the power series that represent functions.'),
        'sections': [],
        'topics': [
            ('Series and Geometric Series', [
                ('Partial Sums, Convergence and Divergence',
                 'An infinite series converges exactly when its sequence of partial sums has a '
                 'finite limit, so the sum is defined by that limit rather than by adding '
                 'infinitely many terms, and a series whose partial sums fail to settle '
                 'diverges.',
                 ['partial sums', 'convergence', 'divergence']),
                ('Geometric Series and Their Sums',
                 'A geometric series sum a r^n converges to a/(1 - r) exactly when |r| < 1 and '
                 'diverges for |r| at least 1, which makes it the one family whose sum is '
                 'available in closed form and therefore the standard comparison target.',
                 ['geometric series', 'ratio', 'closed form']),
            ]),
            ('The nth-Term and Integral Tests', [
                ('The nth-Term Test for Divergence',
                 'If the terms of a series do not tend to zero then the series diverges, but '
                 'terms tending to zero prove nothing, as the harmonic series shows, so the test '
                 'can establish divergence only.',
                 ['nth term test', 'divergence', 'necessary condition']),
                ('The Integral Test',
                 'If f is positive, continuous and decreasing on [N, inf) with a_n = f(n), then '
                 'the series and the integral of f from N to infinity either both converge or '
                 'both diverge, and all three hypotheses are needed because a non-decreasing f '
                 'breaks the rectangle comparison.',
                 ['integral test', 'decreasing', 'hypotheses']),
            ]),
            ('Harmonic and p-Series', [
                ('The Harmonic Series and the p-Series Test',
                 'The p-series sum 1/n^p converges exactly when p > 1 and diverges for p at most '
                 '1, so the harmonic series diverges even though its terms tend to zero, and '
                 'p = 1 is precisely the boundary where the integral test returns a logarithm.',
                 ['p series', 'harmonic', 'boundary case']),
            ]),
            ('Comparison Tests', [
                ('The Direct and Limit Comparison Tests',
                 'If 0 <= a_n <= b_n eventually then convergence of the larger series forces '
                 'convergence of the smaller and divergence of the smaller forces divergence of '
                 'the larger, and when only a_n/b_n tends to a finite positive number the two '
                 'series share their convergence behaviour.',
                 ['comparison test', 'limit comparison', 'positive terms']),
            ]),
            ('Alternating Series', [
                ('The Alternating Series Test',
                 'An alternating series whose term magnitudes decrease eventually and tend to '
                 'zero converges, and both conditions are required, since a decreasing sequence '
                 'with a nonzero limit and a zero limit without decrease both permit divergence.',
                 ['alternating series', 'decreasing terms', 'zero limit']),
                ('Absolute and Conditional Convergence',
                 'A series converges absolutely when the series of absolute values converges, '
                 'which implies convergence of the original, while conditional convergence means '
                 'the original converges but the absolute version diverges, as with the '
                 'alternating harmonic series.',
                 ['absolute convergence', 'conditional convergence', 'absolute values']),
            ]),
            ('The Ratio Test', [
                ('The Ratio Test',
                 'For a series of eventually nonzero terms the ratio test gives convergence when '
                 'lim |a_{n+1}/a_n| < 1 and divergence when that limit exceeds 1, while a limit '
                 'of exactly 1 is inconclusive - the p-series boundary - and the integral or '
                 'comparison test must decide there.',
                 ['ratio test', 'inconclusive', 'p series boundary']),
            ]),
            ('The Alternating Series Error Bound', [
                ('The Alternating Series Error Bound',
                 'For a convergent alternating series satisfying the alternating series test, '
                 'the error from truncating after n terms is at most the magnitude of the first '
                 'omitted term, so the bound is available only while the hypotheses of that test '
                 'hold.',
                 ['error bound', 'first omitted term', 'truncation']),
            ]),
            ('Taylor Polynomials', [
                ('Taylor Polynomials about a Point',
                 'The n-th Taylor polynomial of f about a is the sum of '
                 'f^(k)(a)(x - a)^k/k! for k from 0 to n, and it agrees with f in value and in '
                 'its first n derivatives at a, which is why it is the degree-n polynomial that '
                 'best fits f near a.',
                 ['taylor polynomial', 'matching derivatives', 'centre']),
                ('The Lagrange Error Bound',
                 'The error of the n-th Taylor polynomial at x equals '
                 'f^(n+1)(c)(x - a)^(n+1)/(n+1)! for some c between a and x, so bounding the '
                 '(n+1)-st derivative on that interval bounds the error, and the bound is useful '
                 'only where such a bound is available.',
                 ['lagrange error', 'remainder', 'derivative bound']),
            ]),
            ('Power Series', [
                ('Radius and Interval of Convergence',
                 'A power series converges absolutely on the open interval |x - a| < R and '
                 'diverges outside it, with R found from the ratio test, and the two endpoints '
                 'must then be tested separately because the radius alone says nothing about '
                 'them.',
                 ['radius of convergence', 'interval of convergence', 'endpoints']),
                ('Taylor and Maclaurin Series',
                 'A function with derivatives of every order at a has the Taylor series formed '
                 'from those derivatives, and the series equals the function on its interval of '
                 'convergence only when the remainder tends to zero there; the Maclaurin series '
                 'is the case a = 0.',
                 ['taylor series', 'maclaurin series', 'remainder']),
                ('Representing Functions as Power Series',
                 'A known series such as 1/(1 - x) equal to the sum of x^n for |x| < 1 may be '
                 'differentiated, integrated or composed term by term inside its interval of '
                 'convergence, which produces new representations without new coefficients being '
                 'computed.',
                 ['power series representation', 'term by term', 'geometric series']),
            ]),
        ],
    },
]
