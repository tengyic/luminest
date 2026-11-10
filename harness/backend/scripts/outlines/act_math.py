"""ACT Math outline, in the shape ``scripts/course_pipeline.py`` expects.

A seven-unit ACT Math course written for this project as an original scope and
sequence, dedicated to the public domain under CC0. The seven units follow the ACT
Mathematics reporting categories -- number and quantity, algebra, functions, geometry,
statistics and probability, integrating essential skills, and modelling -- and the
topic names inside them follow the published test descriptions. Every concept title,
summary and keyword set below was written here; no test-preparation publisher's text is
reproduced.

Grain. Units 1-5 are the taught content and carry three concepts per topic. Units 6 and 7
are review strands rather than new mathematics -- one concept per listed skill -- so the
course reaches 101 concepts without inflating the review material into lessons it is not.

Textbook position. ACT Math overlaps first-year college algebra and trigonometry, and the
CC BY 4.0 first editions of four OpenStax books cover the overlap:

* ``algebra-and-trigonometry`` (1e) -- the spine: real numbers, exponents, complex
  numbers, vectors, equations and inequalities, functions, sequences, unit-circle
  trigonometry, coordinate geometry and the conics, and modelling.
* ``college-algebra`` (1e) -- polynomial, rational, radical and system technique.
* ``precalculus`` (1e) -- right-triangle trigonometry.
* ``introductory-statistics`` (1e) -- univariate and bivariate data, inference,
  probability and counting.

Every page slug below was read from the publisher's table of contents with
``scripts/probe_sections.py --book <slug>`` and confirmed with ``--check`` (HTTP 200)
before being written here.

Two honest gaps are left unfilled rather than papered over. ACT geometry includes formal
proof, constructions and circle theorems, and none of the four books teaches Euclidean
geometry, so the transformations/proof topic and the circle-properties topic carry no
section: a conic-sections page is not a stand-in for a circle theorem. The second editions
(``algebra-and-trigonometry-2e``, ``college-algebra-2e``, ``precalculus-2e``,
``introductory-statistics-2e``) report CC BY-NC-SA or link-only, so they are never anchors.
"""

from __future__ import annotations

ID = 'act_math'
TITLE = 'ACT Math'
SUBJECT = 'Mathematics'
SUBJECT_KIND = 'mathematics'
EXPECTED_WEEKS = 18
COURSE_LINE = 'ACT Math - Number, Algebra, Functions, Geometry and Data'
DESCRIPTION = (
    'A complete ACT Mathematics course: rational and irrational numbers, exponent '
    'properties, vectors, matrices and complex numbers, linear, quadratic, polynomial, '
    'rational and radical algebra with systems and inequalities, functions and their '
    'transformations, sequences, trigonometry, exponential and logarithmic functions, '
    'geometry from transformations and similarity through coordinate geometry, conics and '
    'circles, univariate and bivariate statistics with inference and probability, the '
    'integrating essential skills the test assumes, and modelling as a practice rather '
    'than a topic.')

TEXTBOOK = {
    'spine': 'OpenStax Algebra and Trigonometry (1e, CC BY 4.0)',
    'supplements': [
        'OpenStax College Algebra (1e, CC BY 4.0)',
        'OpenStax Precalculus (1e, CC BY 4.0)',
        'OpenStax Introductory Statistics (1e, CC BY 4.0)',
    ],
    'link_only_note': (
        'OpenStax Algebra and Trigonometry 2e, College Algebra 2e, Precalculus 2e and '
        'Introductory Statistics 2e report CC BY-NC-SA 4.0 or link-only status and are '
        'carried as link-only study references: never stored, quoted or used as anchors. '
        'Euclidean proof, construction and circle-theorem material has no section in these '
        'four books, so those ACT topics carry no anchor instead of a stand-in citation.'),
}

UNITS = [
    # ------------------------------------------------------------------ 1
    {
        'unit': 'Number and Quantity',
        'about': ('The number-system foundation the rest of the test assumes: which numbers '
                  'are rational, how exponents behave, how vectors, matrices and complex '
                  'numbers are written, and what a measurement with units actually claims.'),
        'sections': [
            ('algebra-and-trigonometry', '1-1-real-numbers-algebra-essentials'),
            ('algebra-and-trigonometry', '1-2-exponents-and-scientific-notation'),
            ('algebra-and-trigonometry', '10-8-vectors'),
            ('algebra-and-trigonometry', '2-4-complex-numbers'),
        ],
        'topics': [
            ('Rational and Irrational Numbers', [
                ('Rational Numbers as Ratios',
                 'A number is rational exactly when it equals a ratio of two integers, and '
                 'its decimal expansion then terminates or repeats a fixed block.',
                 ['rational number', 'ratio', 'terminating decimal']),
                ('Recognising Irrational Numbers',
                 'A number is irrational when no ratio of integers equals it, so its decimal '
                 'neither terminates nor repeats, as with the square root of 2.',
                 ['irrational number', 'non-repeating', 'square root']),
                ('Density and Ordering on the Number Line',
                 'Between any two distinct real numbers lies both a rational and an '
                 'irrational number, so there is no smallest positive real number.',
                 ['density', 'number line', 'ordering']),
            ]),
            ('Properties of Exponents', [
                ('Product and Quotient Rules',
                 'For a nonzero base a, a^m times a^n is a^(m+n) and a^m divided by a^n is '
                 'a^(m-n), because multiplying counts factors and dividing cancels them.',
                 ['product rule', 'quotient rule', 'base']),
                ('Zero, Negative, and Fractional Exponents',
                 'For nonzero a, a^0 is 1 and a^(-n) is 1/a^n, while a^(m/n) is the nth root '
                 'of a^m whenever that root is a real number.',
                 ['zero exponent', 'negative exponent', 'rational exponent']),
                ('Power of a Product and Power of a Power',
                 '(ab)^n equals a^n b^n and (a^m)^n equals a^(mn), but (a+b)^n is not '
                 'a^n + b^n because an exponent does not distribute over a sum.',
                 ['power rule', 'distribute', 'common error']),
            ]),
            ('Vectors and Matrices', [
                ('Vector Components and Magnitude',
                 'A plane vector is an ordered pair of components, and its magnitude is the '
                 'square root of the sum of their squares, which is a distance in the plane.',
                 ['vector', 'components', 'magnitude']),
                ('Vector Addition and Scalar Multiplication',
                 'Vectors add component by component and scale by multiplying each component, '
                 'so a negative scalar reverses direction without changing the line of action.',
                 ['vector addition', 'scalar', 'direction']),
                ('Matrix Dimensions and Products',
                 'A product AB exists only when the column count of A equals the row count of '
                 'B, and matrix multiplication is not commutative in general.',
                 ['matrix', 'dimension', 'product']),
            ]),
            ('Complex Numbers', [
                ('The Imaginary Unit',
                 'The imaginary unit i satisfies i^2 = -1, which makes x^2 + 1 = 0 solvable '
                 'and gives every negative real number two square roots.',
                 ['imaginary unit', 'complex number', 'square root']),
                ('Arithmetic with Complex Numbers',
                 'Complex numbers add part by part and multiply by distributing with '
                 'i^2 = -1, so the sum and product of complex numbers stay complex.',
                 ['complex arithmetic', 'distribute', 'i squared']),
                ('The Complex Conjugate',
                 'Multiplying a + bi by its conjugate a - bi gives the real number a^2 + b^2, '
                 'which is how a complex denominator is cleared.',
                 ['conjugate', 'complex division', 'real number']),
            ]),
            ('Quantities and Units', [
                ('Units as Part of the Quantity',
                 'A measurement is a number together with a unit, so an answer that lacks the '
                 'unit the question asked for has not answered the question.',
                 ['measurement', 'units', 'quantity']),
                ('Dimensional Analysis',
                 'Multiplying by a conversion factor equal to one changes the unit without '
                 'changing the value, and the unwanted units must cancel completely.',
                 ['conversion factor', 'cancel units', 'rate']),
                ('Precision and Significant Figures',
                 'A computed result carries no more precision than its least precise input, so '
                 'a calculator display is rounded to that precision rather than quoted whole.',
                 ['precision', 'significant figures', 'rounding']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 2
    {
        'unit': 'Algebra',
        'about': ('The solving core: linear and quadratic relationships, the rational, '
                  'radical and polynomial technique that extends them, systems that must hold '
                  'at once, and the equivalent forms a relationship can take.'),
        'sections': [
            ('college-algebra', '2-2-linear-equations-in-one-variable'),
            ('college-algebra', '2-5-quadratic-equations'),
            ('college-algebra', '2-6-other-types-of-equations'),
            ('college-algebra', '7-1-systems-of-linear-equations-two-variables'),
        ],
        'topics': [
            ('Linear Expressions, Equations, and Inequalities', [
                ('Solving Linear Equations',
                 'A linear equation is solved by applying the same operation to both sides '
                 'until the variable stands alone, which preserves the solution set at every '
                 'step.',
                 ['linear equation', 'inverse operation', 'balance']),
                ('Reversing an Inequality',
                 'Multiplying or dividing both sides of an inequality by a negative number '
                 'reverses the symbol, because that operation reflects the number line.',
                 ['inequality', 'negative factor', 'reverse symbol']),
                ('Solving a Formula for a Variable',
                 'Rearranging a formula for a named variable treats every other variable as a '
                 'constant, so the inverse operations are applied in reverse order.',
                 ['literal equation', 'rearrange', 'formula']),
            ]),
            ('Quadratic Expressions, Equations, and Inequalities', [
                ('Factoring and the Zero Product Property',
                 'If a product equals zero then at least one factor equals zero, so a factored '
                 'quadratic equation splits into two linear equations.',
                 ['zero product property', 'factor', 'solve']),
                ('The Quadratic Formula and Discriminant',
                 'For ax^2 + bx + c = 0 with a not zero, x = (-b +/- sqrt(b^2 - 4ac))/(2a), '
                 'and the sign of b^2 - 4ac gives two, one, or no real solutions.',
                 ['quadratic formula', 'discriminant', 'real solutions']),
                ('Sign Analysis of a Quadratic Inequality',
                 'A quadratic inequality is solved from its zeros and the sign of the leading '
                 'coefficient: an upward parabola is positive outside its roots and negative '
                 'between them.',
                 ['quadratic inequality', 'sign chart', 'roots']),
            ]),
            ('Rational and Radical Expressions and Equations', [
                ('Restricted Domains of Rational Expressions',
                 'A rational expression is undefined where its denominator is zero, so those '
                 'values are excluded before a common factor is cancelled.',
                 ['rational expression', 'domain', 'undefined']),
                ('Common Denominators for Rational Expressions',
                 'Rational expressions are added by rewriting each over a common denominator, '
                 'and multiplying numerator and denominator by the same nonzero factor '
                 'changes nothing.',
                 ['common denominator', 'equivalent fractions', 'simplify']),
                ('Extraneous Solutions from Squaring',
                 'A radical equation can produce extraneous solutions because squaring both '
                 'sides is not reversible, so every candidate is checked in the original '
                 'equation.',
                 ['radical equation', 'extraneous solution', 'check']),
            ]),
            ('Polynomial Expressions and Equations', [
                ('Degree, Zeros, and End Behaviour',
                 'A polynomial of degree n has at most n real zeros and at most n - 1 turning '
                 'points, and its end behaviour follows the sign of its leading coefficient.',
                 ['degree', 'zeros', 'end behaviour']),
                ('Remainder and Factor Theorems',
                 'Dividing p(x) by x - c leaves remainder p(c), so c is a zero of p exactly '
                 'when x - c is a factor of p.',
                 ['remainder theorem', 'factor theorem', 'zero']),
                ('Multiplying and Dividing Polynomials',
                 'Every term of one polynomial multiplies every term of the other, and '
                 'division by a monomial distributes over the terms while division by a '
                 'binomial needs long division.',
                 ['polynomial product', 'long division', 'monomial']),
            ]),
            ('Systems of Equations and Inequalities', [
                ('Substitution and Elimination',
                 'Substitution or elimination reduces a system of two linear equations to one '
                 'equation in one variable, and the second variable follows by back '
                 'substitution.',
                 ['system', 'substitution', 'elimination']),
                ('The Three Solution Cases',
                 'Two lines in a plane meet once, never, or at every point, so a linear system '
                 'has exactly one solution, none, or infinitely many.',
                 ['consistent', 'inconsistent', 'dependent']),
                ('Half-Planes from Two-Variable Inequalities',
                 'The solution set of a linear inequality in two variables is a half-plane, '
                 'and one test point decides which side of the boundary satisfies it.',
                 ['half-plane', 'boundary line', 'test point']),
            ]),
            ('Representation of Expressions and Equations', [
                ('Equivalent Forms of One Relationship',
                 'Factored, standard, and vertex forms describe the same quadratic, so the form '
                 'is chosen for what it displays: zeros, y-intercept, or turning point.',
                 ['equivalent forms', 'standard form', 'vertex form']),
                ('Interpreting Parameters in Context',
                 'In y = mx + b the slope is the change per input unit and b is the starting '
                 'value, and each parameter carries the units of the quantity it describes.',
                 ['parameter', 'slope', 'initial value']),
                ('Agreement of Equation, Table, and Graph',
                 'An equation, its table, and its graph describe the same relationship, so a '
                 'disagreement between any two of them exposes an algebra or scale error.',
                 ['multiple representations', 'check', 'scale']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 3
    {
        'unit': 'Functions',
        'about': ('Functions as the language of change: what a function is, how functions '
                  'combine and invert, how sequences, trigonometric functions and exponential '
                  'and logarithmic functions each encode a particular kind of growth.'),
        'sections': [
            ('algebra-and-trigonometry', '3-1-functions-and-function-notation'),
            ('algebra-and-trigonometry', '3-5-transformation-of-functions'),
            ('algebra-and-trigonometry', '13-1-sequences-and-their-notations'),
            ('algebra-and-trigonometry', '7-3-unit-circle'),
        ],
        'topics': [
            ('Properties of Functions', [
                ('Function Definition and Vertical Line Test',
                 'A function assigns exactly one output to each input, so a graph is a '
                 'function exactly when no vertical line meets it more than once.',
                 ['function', 'vertical line test', 'input']),
                ('Domain and Range',
                 'The domain is the set of inputs the rule accepts, limited by division by '
                 'zero and even roots of negatives, and the range is the set of outputs '
                 'actually produced.',
                 ['domain', 'range', 'restriction']),
                ('Average Rate of Change',
                 'The average rate of change between two inputs is the change in output '
                 'divided by the change in input, which is the slope of the secant line.',
                 ['average rate of change', 'secant', 'interval']),
            ]),
            ('Composition, Transformation, and Inverse Functions', [
                ('Composition of Functions',
                 'The composition f(g(x)) applies g first and f second, so its domain excludes '
                 'inputs that g rejects and inputs whose g(x) f cannot evaluate.',
                 ['composition', 'order of operations', 'domain']),
                ('Transformations of Graphs',
                 'Adding a constant to the output shifts a graph vertically, adding inside the '
                 'input shifts it horizontally in the opposite direction, and a factor '
                 'stretches or reflects it.',
                 ['translation', 'stretch', 'reflection']),
                ('Inverse Functions',
                 'An inverse swaps the roles of input and output and undoes the original, and '
                 'it is a function only where the original is one-to-one.',
                 ['inverse', 'one-to-one', 'swap']),
            ]),
            ('Sequences and Series', [
                ('Arithmetic Sequences and Their Sums',
                 'An arithmetic sequence adds a constant difference, so a_n = a_1 + (n - 1)d '
                 'and the first n terms sum to n(a_1 + a_n)/2.',
                 ['arithmetic sequence', 'common difference', 'series']),
                ('Geometric Sequences and Their Sums',
                 'A geometric sequence multiplies by a constant ratio, so a_n = a_1 r^(n-1) and '
                 'a finite sum is a_1(1 - r^n)/(1 - r) when r is not 1.',
                 ['geometric sequence', 'common ratio', 'finite sum']),
                ('Recursive versus Explicit Rules',
                 'A recursive rule needs a starting term and the previous term, while an '
                 'explicit rule gives any term from its position alone, which is what makes a '
                 'distant term computable.',
                 ['recursive rule', 'explicit rule', 'nth term']),
            ]),
            ('Trigonometric Functions', [
                ('Right-Triangle Ratios',
                 'In a right triangle sine, cosine, and tangent are fixed ratios of two sides, '
                 'so one acute angle and one side determine the remaining sides.',
                 ['sine', 'cosine', 'tangent']),
                ('Unit Circle and Radian Measure',
                 'On the unit circle the cosine and sine of an angle are the coordinates of '
                 'the point it reaches, and pi radians equal 180 degrees.',
                 ['unit circle', 'radian', 'coordinates']),
                ('Period, Amplitude, and Midline',
                 'For y = A sin(Bx + C) + D the amplitude is |A|, the period is 2pi/|B|, and '
                 'the midline is y = D, so each parameter changes one visible feature.',
                 ['amplitude', 'period', 'midline']),
            ]),
            ('Exponential and Logarithmic Functions', [
                ('Exponential Growth and Decay',
                 'In f(x) = a b^x the base b is the factor per unit step, so b > 1 grows, '
                 '0 < b < 1 decays, and the percent change per step is b - 1.',
                 ['exponential function', 'growth factor', 'decay']),
                ('Logarithms as Inverses',
                 'log_b x is the exponent that turns b into x, so it inverts b^x and accepts '
                 'only positive inputs because no power of b is zero or negative.',
                 ['logarithm', 'inverse', 'domain']),
                ('Solving Exponential and Logarithmic Equations',
                 'An exponential equation yields to a logarithm of both sides and a '
                 'logarithmic equation to rewriting it in exponential form, with every '
                 'candidate checked against the domain.',
                 ['exponential equation', 'logarithmic equation', 'check domain']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 4
    {
        'unit': 'Geometry',
        'about': ('Shape and space reasoned from a small set of facts: rigid motion and '
                  'similarity, right-triangle and general-triangle measurement, coordinates, '
                  'the conics, circle theorems, and the surface and volume formulas a model '
                  'needs.'),
        'sections': [
            ('precalculus', '5-4-right-triangle-trigonometry'),
            ('algebra-and-trigonometry', '10-1-non-right-triangles-law-of-sines'),
            ('algebra-and-trigonometry', '2-1-the-rectangular-coordinate-systems-and-graphs'),
            ('algebra-and-trigonometry', '12-1-the-ellipse'),
        ],
        'topics': [
            ('Transformations, Proof, Reasoning, and Constructions', [
                ('Rigid Motions Preserve Congruence',
                 'Translations, rotations, and reflections preserve every length and angle, so '
                 'a figure and its image under a rigid motion are congruent.',
                 ['rigid motion', 'congruence', 'isometry']),
                ('Dilations and Scale Factor',
                 'A dilation multiplies every length by its scale factor and preserves angle '
                 'measures, so it changes size while keeping the shape.',
                 ['dilation', 'scale factor', 'similarity']),
                ('Deductive Reasoning and Counterexamples',
                 'A proof derives each statement from givens and established results, and a '
                 'single counterexample is enough to refute a universal claim.',
                 ['proof', 'counterexample', 'conditional']),
            ]),
            ('Similarity, Right Triangles, and Trigonometry', [
                ('Similar Triangles and Proportional Sides',
                 'Two triangles are similar when two pairs of corresponding angles agree, and '
                 'then every pair of corresponding sides shares one ratio.',
                 ['similar triangles', 'proportion', 'corresponding sides']),
                ('Pythagorean Theorem and Its Converse',
                 'In a right triangle the square of the hypotenuse equals the sum of the '
                 'squares of the legs, and the converse guarantees a triangle satisfying it is '
                 'right.',
                 ['pythagorean theorem', 'hypotenuse', 'converse']),
                ('Law of Sines and Law of Cosines',
                 'The law of sines relates each side to the sine of its opposite angle, and the '
                 'law of cosines extends the Pythagorean theorem to triangles without a right '
                 'angle.',
                 ['law of sines', 'law of cosines', 'oblique triangle']),
            ]),
            ('Coordinate Geometry', [
                ('Distance and Midpoint',
                 'The distance between two points is the hypotenuse of a right triangle whose '
                 'legs are the coordinate differences, and the midpoint averages the '
                 'coordinates.',
                 ['distance formula', 'midpoint', 'coordinates']),
                ('Slope Criteria for Parallel and Perpendicular Lines',
                 'Two nonvertical lines are parallel exactly when their slopes are equal and '
                 'perpendicular exactly when their slopes have product -1.',
                 ['slope', 'parallel', 'perpendicular']),
                ('Equations of Circles in the Plane',
                 'A circle with centre (h, k) and radius r satisfies (x - h)^2 + (y - k)^2 = '
                 'r^2, and completing the square recovers the centre and radius from a general '
                 'equation.',
                 ['circle equation', 'centre', 'completing the square']),
            ]),
            ('Conic Sections', [
                ('Standard Forms of the Conics',
                 'Each conic has a standard form whose parameters display its centre or vertex, '
                 'its axis, and its size, so a shape is identified from its equation.',
                 ['conic', 'standard form', 'axis']),
                ('Completing the Square to Classify',
                 'Completing the square in x and y turns a general second-degree equation into '
                 'standard form, which shows which conic it is and whether it is degenerate.',
                 ['complete the square', 'classify', 'second degree']),
                ('Foci and Eccentricity',
                 'An ellipse is the set of points whose distances to two foci have a constant '
                 'sum, and its eccentricity measures how far it departs from a circle.',
                 ['ellipse', 'focus', 'eccentricity']),
            ]),
            ('Properties of Circles', [
                ('Central Angles and Arcs',
                 'A central angle has the same measure as its intercepted arc, so an arc length '
                 'is that fraction of the circumference.',
                 ['central angle', 'arc', 'circumference']),
                ('Inscribed Angles',
                 'An inscribed angle measures half of its intercepted arc, which is why an '
                 'angle inscribed in a semicircle is a right angle.',
                 ['inscribed angle', 'intercepted arc', 'semicircle']),
                ('Chords, Tangents, and Secants',
                 'A tangent line is perpendicular to the radius at the point of contact, and a '
                 'radius that bisects a chord is perpendicular to that chord.',
                 ['tangent', 'chord', 'radius']),
            ]),
            ('Geometric Measurement and Modeling', [
                ('Perimeter, Circumference, and Area',
                 'Area scales as the square of a length scale factor, so doubling every '
                 'dimension of a figure multiplies its area by four.',
                 ['area', 'perimeter', 'scale factor']),
                ('Surface Area and Volume',
                 'Volume scales as the cube of a length scale factor while surface area scales '
                 'as its square, so doubling a solid multiplies volume by eight and surface '
                 'area by four.',
                 ['volume', 'surface area', 'similar solids']),
                ('Density and Geometric Modelling',
                 'A geometric model answers a real question only when the units agree: volume '
                 'times density gives mass, and area times a coverage rate gives a total '
                 'amount.',
                 ['density', 'rate', 'units']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 5
    {
        'unit': 'Statistics and Probability',
        'about': ('Reading data and reasoning under uncertainty: describing one variable and '
                  'two, drawing an inference from a sample, the rules probability obeys, and '
                  'the counting that makes those rules computable.'),
        'sections': [
            ('introductory-statistics', '2-5-measures-of-the-center-of-the-data'),
            ('introductory-statistics', '12-2-scatter-plots'),
            ('introductory-statistics', '9-1-null-and-alternative-hypotheses'),
            ('introductory-statistics', '3-3-two-basic-rules-of-probability'),
        ],
        'topics': [
            ('Univariate Data Analysis', [
                ('Measures of Center',
                 'The mean is pulled toward a skew or an outlier while the median is not, so '
                 'the median better describes a typical value in a skewed distribution.',
                 ['mean', 'median', 'skew']),
                ('Measures of Spread',
                 'Range, interquartile range, and standard deviation all measure spread, and '
                 'the interquartile range resists outliers as the median does.',
                 ['range', 'interquartile range', 'standard deviation']),
                ('Shape from Displays',
                 'A histogram or box plot shows shape, centre, spread, and outliers together, '
                 'and no single summary statistic can reveal a second peak.',
                 ['histogram', 'box plot', 'distribution shape']),
            ]),
            ('Bivariate Data Analysis', [
                ('Scatterplots and Association',
                 'A scatterplot displays the direction, form, and strength of an association '
                 'between two quantitative variables, which a correlation alone cannot show.',
                 ['scatterplot', 'association', 'direction']),
                ('The Least-Squares Regression Line',
                 'The least-squares line minimises the sum of squared residuals, so it balances '
                 'prediction errors rather than passing through the most data points.',
                 ['regression line', 'residual', 'least squares']),
                ('Correlation and Prediction',
                 'The correlation coefficient measures only the strength and direction of a '
                 'linear association, so a strong correlation never by itself establishes '
                 'causation.',
                 ['correlation', 'causation', 'prediction']),
            ]),
            ('Introduction to Formal Inferential Statistics', [
                ('Samples and Populations',
                 'A statistic computed from a random sample estimates a population parameter, '
                 'and the sampling method decides whether that estimate can be trusted.',
                 ['sample', 'population', 'random sampling']),
                ('The Central Limit Theorem',
                 'For a large random sample the sample mean is approximately normal with mean '
                 'mu and standard deviation sigma over the square root of n, whatever the '
                 'population shape.',
                 ['central limit theorem', 'standard error', 'sample mean']),
                ('Null Hypotheses and p-Values',
                 'A hypothesis test compares the observed statistic with what the null '
                 'hypothesis predicts, and a small p-value means the observation is unlikely '
                 'under that null.',
                 ['null hypothesis', 'p-value', 'significance']),
            ]),
            ('Rules of Probability', [
                ('Probability as a Long-Run Proportion',
                 'A probability lies between 0 and 1 and equals the proportion of trials in '
                 'which the event occurs as the number of trials grows without bound.',
                 ['probability', 'long run', 'event']),
                ('Addition Rule and Mutually Exclusive Events',
                 'P(A or B) = P(A) + P(B) - P(A and B), and the subtracted term vanishes only '
                 'when A and B cannot occur together.',
                 ['addition rule', 'mutually exclusive', 'overlap']),
                ('Conditional Probability and Independence',
                 'P(A given B) = P(A and B)/P(B), and A and B are independent exactly when that '
                 'conditional probability equals P(A).',
                 ['conditional probability', 'independence', 'given']),
            ]),
            ('Counting, Permutations, and Combinations', [
                ('The Multiplication Principle',
                 'If one stage can be done in m ways and the next in n ways, the two stages '
                 'together can be done in mn ways, which multiplies through any number of '
                 'stages.',
                 ['counting principle', 'stages', 'outcomes']),
                ('Permutations Count Ordered Arrangements',
                 'The number of ordered arrangements of r items chosen from n distinct items is '
                 'n!/(n - r)!, because a different order is a different arrangement.',
                 ['permutation', 'factorial', 'order']),
                ('Combinations Count Unordered Selections',
                 'The number of unordered selections of r items from n is n!/(r!(n - r)!), '
                 'which is the permutation count divided by the r! orders of one set.',
                 ['combination', 'subset', 'factorial']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 6
    {
        'unit': 'Integrating Essential Skills',
        'about': ('The review strand the test assumes rather than teaches: arithmetic, ratio '
                  'and percent, translation, measurement, the plane-geometry and coordinate '
                  'essentials, and the data literacy the statistics items presuppose. One '
                  'concept per skill.'),
        'sections': [
            ('college-algebra', '1-1-real-numbers-algebra-essentials'),
            ('college-algebra', '1-3-radicals-and-rational-exponents'),
            ('introductory-statistics', '2-2-histograms-frequency-polygons-and-time-series-graphs'),
            ('introductory-statistics', '3-1-terminology'),
        ],
        'topics': [
            ('Properties of Real Numbers', [
                ('Field Properties of Real Numbers',
                 'Real numbers are closed under addition and multiplication, both operations '
                 'commute and associate, and multiplication distributes over addition, which '
                 'is what licenses every rearrangement.',
                 ['field properties', 'distributive', 'closure']),
            ]),
            ('Computation and Problem Solving with Real Numbers', [
                ('Signed Arithmetic and Order of Operations',
                 'Grouping and exponents are evaluated first, then multiplication and division '
                 'left to right, then addition and subtraction, with sign rules applied at each '
                 'step.',
                 ['order of operations', 'signed numbers', 'precedence']),
            ]),
            ('Ratio, Proportion, and Percent', [
                ('Setting Up and Solving a Proportion',
                 'A proportion states two equal ratios, and cross multiplication clears the '
                 'denominators, which is the same step as multiplying both sides by their '
                 'product.',
                 ['proportion', 'cross multiply', 'percent']),
            ]),
            ('Writing Algebraic Expressions', [
                ('Translating Words into Symbols',
                 'Each operation word maps to one symbol and order words such as twice the sum '
                 'fix the grouping, so a phrase is translated one operation at a time.',
                 ['translate', 'expression', 'grouping']),
            ]),
            ('Writing and Solving Simple Equations and Inequalities', [
                ('Isolating the Unknown',
                 'An equation or inequality is solved by undoing operations in reverse order on '
                 'both sides, and multiplying or dividing by a negative reverses an inequality.',
                 ['isolate', 'inverse operation', 'inequality']),
            ]),
            ('Measurement Units and Unit Conversion', [
                ('Conversion Factors in One Step',
                 'A conversion factor is a ratio of two equal quantities, so multiplying by it '
                 'changes only the unit and the unit being replaced must cancel.',
                 ['unit conversion', 'conversion factor', 'cancel']),
            ]),
            ('Properties of Lines, Angles, and Shapes', [
                ('Angle Relationships in Figures',
                 'Vertical angles are equal, angles on a straight line sum to 180 degrees, and '
                 'the angles of a triangle sum to 180 degrees, which fixes a missing angle.',
                 ['vertical angles', 'supplementary', 'triangle angle sum']),
            ]),
            ('Perimeter, Circumference, and Area', [
                ('Area of Composite Figures',
                 'A composite figure is measured by adding or subtracting the areas of the '
                 'shapes it decomposes into, with every length first converted to one unit.',
                 ['composite area', 'decomposition', 'perimeter']),
            ]),
            ('Surface Area and Volume', [
                ('Volume and Surface Area Formulas',
                 'A prism or cylinder has volume equal to base area times height, a pyramid or '
                 'cone has one third of that, and surface area sums the exposed faces.',
                 ['volume', 'surface area', 'solid']),
            ]),
            ('The Coordinate Plane', [
                ('Slope, Midpoint, and Distance from Coordinates',
                 'Between two points the slope is the ratio of the coordinate differences, the '
                 'midpoint averages the coordinates, and the distance is the hypotenuse of '
                 'those differences.',
                 ['slope', 'midpoint', 'distance']),
            ]),
            ('Pythagorean Theorem', [
                ('Right Triangles and the Distance Formula',
                 'In a right triangle the hypotenuse squared equals the sum of the legs '
                 'squared, and the coordinate distance formula is that theorem applied to the '
                 'two coordinate differences.',
                 ['pythagorean theorem', 'hypotenuse', 'distance formula']),
            ]),
            ('Scatterplots', [
                ('Reading a Scatterplot',
                 'A scatterplot is read for direction, strength, and form of association, and a '
                 'point far off the pattern is an outlier that can dominate a fitted line.',
                 ['scatterplot', 'outlier', 'trend']),
            ]),
            ('Data Summaries and Displays', [
                ('Choosing a Summary Statistic',
                 'The mean and standard deviation describe symmetric data, while the median and '
                 'interquartile range describe skewed data or data carrying outliers.',
                 ['mean', 'median', 'skewed data']),
            ]),
            ('Informal Inferential Statistics', [
                ('Inference from a Sample',
                 'A conclusion about a population drawn from a sample is only as sound as the '
                 'sample is random, so a biased sample supports no inference however large it '
                 'is.',
                 ['inference', 'random sample', 'bias']),
            ]),
            ('Basic Probability', [
                ('Probability from Equally Likely Outcomes',
                 'When outcomes are equally likely the probability of an event is the number of '
                 'favourable outcomes divided by the total number of outcomes.',
                 ['favorable outcomes', 'sample space', 'equally likely']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 7
    {
        'unit': 'Modeling',
        'about': ('Modelling treated as a cycle rather than a topic: build a model from a '
                  'context, read it, know what it assumes, judge it against data, and revise '
                  'it. One concept per stage.'),
        'sections': [
            ('algebra-and-trigonometry', '2-3-models-and-applications'),
            ('algebra-and-trigonometry', '4-2-modeling-with-linear-functions'),
            ('algebra-and-trigonometry', '6-7-exponential-and-logarithmic-models'),
            ('algebra-and-trigonometry', '5-8-modeling-using-variation'),
        ],
        'topics': [
            ('Producing', [
                ('Building a Model from a Context',
                 'Producing a model means naming the input and output with their units, '
                 'choosing a family that matches how the data change, and fitting its '
                 'parameters to the given values.',
                 ['model', 'parameter', 'function family']),
            ]),
            ('Interpreting', [
                ('Reading Parameters and Outputs in Context',
                 'Interpreting a model means stating what each parameter and each predicted '
                 'output means in the situation, including its units and the interval where it '
                 'applies.',
                 ['interpret', 'units', 'prediction']),
            ]),
            ('Understanding', [
                ('Assumptions and Limits of a Model',
                 'Every model rests on assumptions such as a constant rate or unlimited growth, '
                 'and understanding it means knowing which assumption a conclusion depends on.',
                 ['assumption', 'limitation', 'domain']),
            ]),
            ('Evaluating', [
                ('Judging a Model Against Data',
                 'A model is evaluated by comparing its predictions with observed values, and a '
                 'pattern in the residuals shows the family is wrong rather than merely '
                 'imprecise.',
                 ['evaluate', 'residual', 'fit']),
            ]),
            ('Improving', [
                ('Revising a Model',
                 'Improving a model means changing the family, the interval, or the '
                 'measurements in response to the residual pattern and then re-checking the new '
                 'predictions.',
                 ['revise', 'refit', 'iteration']),
            ]),
        ],
    },
]
