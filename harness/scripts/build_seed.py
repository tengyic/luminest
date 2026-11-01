#!/usr/bin/env python3
"""Author the bundled one-year course outline and emit it as a plain data file.

The outline below is original work written for this harness: concept titles, the
order they are taught in, and the prerequisite *intent* between units. It is
dedicated to the public domain (CC0) so the ingestion pipeline can consume it
through exactly the same licence gate as any third-party outline.

Run:  python scripts/build_seed.py
Out:  backend/app/ingest/seed/algebra_one_year.json
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'backend' / 'app' / 'ingest' / 'seed' / 'algebra_one_year.json'

COURSE = {
    'course': 'Algebra I and Integrated Mathematics — one year',
    'licence': 'cc0',
    'source_url': '',
    'attribution': 'Original scope and sequence authored for the Luminfest Learning Harness, '
                   'dedicated to the public domain under CC0.',
    'scope': 'Structure only: concept titles, unit order and prerequisite intent. No third-party '
             'curriculum text is reproduced, and no restricted source is ingested.',
    'description': 'A full-year integrated mathematics course: number and quantity, algebra, '
                   'functions, geometry and measurement, statistics and probability.',
    'expected_weeks': 36,
}

# (strand, unit, [prerequisite units], [ (topic, [ (title, summary, "keyword;keyword") ]) ])
UNITS: list[tuple[str, str, list[str], list[tuple[str, list[tuple[str, str, str]]]]]] = [
    # ---------------------------------------------------------------- Number & Quantity
    ('Number & Quantity', 'Number foundations', [], [
        ('Whole-number structure', [
            ('Place value and base-ten structure', 'Each digit carries a value set by its position, which is what makes regrouping possible.', 'place value;regrouping;base ten'),
            ('Factors, multiples and divisibility', 'Divisibility rules let you test factor structure without dividing, which speeds up later work with fractions and polynomials.', 'divisibility;factor;multiple'),
            ('Prime factorisation', 'Every whole number above one factors uniquely into primes, giving one canonical description of a number.', 'prime;factorisation;fundamental theorem'),
            ('Greatest common factor and least common multiple', 'The GCF is the largest shared divisor and the LCM the smallest shared multiple; both come straight out of prime factorisation.', 'gcf;lcm;common factor'),
        ]),
        ('Fractions as quantities', [
            ('Fraction equivalence', 'Multiplying numerator and denominator by the same nonzero number renames a quantity without changing it.', 'equivalent fractions;common denominator'),
            ('Fraction addition and subtraction', 'Fractions can only be combined once they name the same size of piece, so a common unit comes first.', 'common denominator;unlike denominators;sum'),
            ('Fraction multiplication and division', 'Multiplication scales one fraction by another; division asks how many of one fraction fit inside another.', 'multiply fractions;reciprocal;divide fractions'),
            ('Decimals, fractions and percent equivalence', 'Decimals, fractions and percent are three notations for the same rational quantity, and converting between them is a routine move.', 'decimal;percent;conversion'),
        ]),
        ('Signed numbers', [
            ('Signed numbers on the number line', 'A negative sign records direction relative to zero, not merely a subtraction waiting to happen.', 'negative;number line;opposite'),
            ('Absolute value as distance', 'Absolute value measures distance from zero and therefore discards direction while keeping size.', 'absolute value;distance;magnitude'),
            ('Integer addition and subtraction', 'Adding a signed number moves along the number line; subtracting a number is the same as adding its opposite.', 'integer;opposite;subtract negative'),
            ('Integer multiplication and division', 'The sign rules for products and quotients follow from repeated addition, and they set up sign handling in algebra.', 'sign rules;product;quotient'),
        ]),
    ]),

    ('Number & Quantity', 'Ratios, rates and proportional reasoning', ['Number foundations'], [
        ('Building and comparing ratios', [
            ('Ratios as comparisons', 'A ratio compares two quantities of the same or different kinds, and the order of the terms carries meaning.', 'ratio;comparison;part to part'),
            ('Unit rates', 'A unit rate divides a comparison down to a single unit of the second quantity, which makes prices and speeds comparable.', 'unit rate;per unit;rate'),
            ('Proportional relationships', 'Two quantities are proportional when their ratio is constant, so scaling one scales the other by the same factor.', 'proportion;constant of proportionality;scale factor'),
            ('Solving proportions', 'Cross multiplication is a shortcut that follows from multiplying both sides of an equality of ratios by the same product.', 'cross multiplication;proportion;solve'),
        ]),
        ('Scaling and percent', [
            ('Scale drawings and scale factor', 'A scale drawing preserves shape while changing size, and the scale factor connects drawing lengths to real lengths.', 'scale drawing;scale factor;similar'),
            ('Percent as a rate per hundred', 'Percent is a ratio with an implicit denominator of one hundred, which is why it converts directly to a decimal.', 'percent;per hundred;decimal'),
            ('Percent change', 'Percent change compares the size of a change to the original quantity, so the base must be stated.', 'percent change;increase;decrease'),
            ('Applications: tax, tip, discount and interest', 'Everyday percent problems are one proportional structure wearing different words.', 'tax;tip;discount;markup'),
            ('Direct variation', 'Direct variation is a proportional relationship written as an equation through the origin.', 'direct variation;constant of variation;origin'),
            ('Dimensional analysis and unit conversion', 'Tracking units as if they were algebraic quantities catches conversion errors before they reach an answer.', 'unit conversion;dimensional analysis;rate'),
        ]),
    ]),

    ('Number & Quantity', 'Exponents, radicals and irrational numbers', ['Number foundations', 'Ratios, rates and proportional reasoning'], [
        ('Exponent structure', [
            ('Integer exponents', 'A positive integer exponent counts repeated factors, which is not the same as repeated addition.', 'exponent;repeated factors;power'),
            ('Product and quotient rules for exponents', 'Multiplying like bases adds exponents because it concatenates two runs of identical factors.', 'product rule;quotient rule;like bases'),
            ('Power of a power and power of a product', 'An outer exponent distributes over a product and multiplies against an inner exponent.', 'power of a power;distribute exponent;parentheses'),
            ('Zero and negative exponents', 'The rules extend to zero and negative exponents in exactly the way that keeps the quotient rule consistent.', 'zero exponent;negative exponent;reciprocal'),
        ]),
        ('Radicals and scientific notation', [
            ('Square roots and perfect squares', 'A square root reverses squaring, and perfect squares let you factor a root exactly.', 'square root;perfect square;radical'),
            ('Simplifying radical expressions', 'A radical simplifies by pulling out the largest perfect-square factor, which is factoring under a root.', 'simplify radical;perfect square factor;radical'),
            ('Rational exponents', 'A fractional exponent names a root, which unifies radical notation with exponent rules.', 'rational exponent;fractional exponent;root'),
            ('Estimating and locating irrational numbers', 'Irrational numbers cannot be written as a ratio of integers, so they are placed by approximation rather than exact form.', 'irrational;estimate;approximate'),
            ('Scientific notation', 'Scientific notation writes a number as a mantissa times a power of ten, which makes extreme magnitudes readable and comparable.', 'scientific notation;mantissa;power of ten'),
        ]),
    ]),

    # ---------------------------------------------------------------- Algebra
    ('Algebra', 'Algebraic expressions', ['Number foundations', 'Exponents, radicals and irrational numbers'], [
        ('Expressions and notation', [
            ('Variables and algebraic notation', 'A variable names a quantity that may vary, and juxtaposition is the conventional way to write multiplication.', 'variable;coefficient;notation'),
            ('Translating verbal statements into expressions', 'Moving from words to symbols requires deciding what each quantity is before choosing operations.', 'translate;verbal expression;word phrase'),
            ('Evaluating expressions', 'Substituting a value and computing is the direct test of what an expression means.', 'evaluate;substitute;value'),
        ]),
        ('Structure of expressions', [
            ('Terms, coefficients and constants', 'An expression is a sum of terms, and each term carries its own sign and coefficient.', 'term;coefficient;constant'),
            ('Combining like terms', 'Only terms with identical variable parts can be merged, because only they describe the same kind of quantity.', 'like terms;combine;simplify'),
            ('The distributive property', 'Multiplication distributes over addition, which is what lets you remove parentheses correctly.', 'distributive;expand;parentheses'),
            ('Simplifying linear expressions', 'Simplifying means rewriting an expression in an equivalent but shorter form, verified by substitution.', 'simplify;equivalent;linear expression'),
        ]),
        ('Polynomial structure', [
            ('Expanding products of binomials', 'Every term of one factor multiplies every term of the other, so a two-by-two product produces four terms before simplification.', 'expand;binomial;foil;product'),
            ('Polynomial vocabulary and degree', 'The degree is the highest exponent present and the leading coefficient governs end behaviour.', 'polynomial;degree;leading coefficient;monomial'),
            ('Adding and subtracting polynomials', 'Polynomials combine by matching like terms, and subtracting requires distributing the minus sign across every term.', 'add polynomials;subtract polynomials;like terms'),
        ]),
    ]),

    ('Algebra', 'Linear equations', ['Algebraic expressions', 'Ratios, rates and proportional reasoning'], [
        ('What a solution means', [
            ('Solutions and equivalent equations', 'An equation asserts equality, and applying the same reversible operation to both sides preserves the solution set.', 'equation;solution;equivalent equations'),
            ('One-step equations', 'A single inverse operation isolates the variable when only one operation is applied to it.', 'one step;inverse operation;isolate'),
            ('Two-step equations', 'Undo addition before multiplication, because the order of inverse operations reverses the order of the original operations.', 'two step;order of operations;inverse'),
        ]),
        ('Multi-step and general linear equations', [
            ('Multi-step equations with distribution', 'Removing parentheses first turns a multi-step equation into a familiar linear one.', 'multi step;distribute;combine'),
            ('Equations with variables on both sides', 'Collecting variable terms on one side and constants on the other reduces any linear equation to a two-step form.', 'variables both sides;collect;linear'),
            ('Equations with fractions and decimals', 'Clearing denominators by multiplying every term by the common denominator removes fractions without changing the solution.', 'clear denominators;fraction coefficient;decimal'),
            ('Literal equations and formulas', 'Solving a formula for a different variable uses the same operations, treating the other variables as numbers.', 'literal equation;solve for a variable;formula'),
            ('Absolute value equations', 'An absolute value equation splits into two cases because two numbers sit at the same distance from zero.', 'absolute value;two cases;extraneous solution'),
        ]),
        ('Equations from context', [
            ('Modelling with linear equations', 'Translating a situation into an equation requires naming the unknown and writing what the situation asserts.', 'model;word problem;define variable'),
            ('Consecutive integer and age problems', 'These problems are linear equations in disguise, and the modelling step is where they are won or lost.', 'consecutive integers;age problem;model'),
            ('Mixture, rate and work problems', 'Rates and mixtures combine as weighted sums, which produce linear equations in one unknown.', 'mixture;rate;work problem'),
        ]),
    ]),

    ('Algebra', 'Linear inequalities', ['Linear equations'], [
        ('Inequality basics', [
            ('Inequality notation and solution sets', 'An inequality describes a range of values rather than a single number, and the solution set is that whole range.', 'inequality;solution set;range'),
            ('Graphing inequalities on the number line', 'An open circle excludes the boundary and a closed circle includes it, which is the visual record of strictness.', 'graph inequality;open circle;closed circle'),
            ('Solving one- and two-step inequalities', 'Inequalities solve with the same inverse operations as equations, with one exception.', 'solve inequality;inverse operation;boundary'),
            ('Reversing the inequality symbol', 'Multiplying or dividing by a negative number reverses order, which is why the symbol flips.', 'reverse inequality;negative divisor;order'),
        ]),
        ('Compound and absolute value inequalities', [
            ('Compound inequalities', 'An "and" compound restricts to an interval while an "or" compound allows two separate rays.', 'compound inequality;and;or;interval'),
            ('Interval notation', 'Interval notation compresses an inequality solution set into a compact pair of endpoints.', 'interval notation;bracket;parenthesis'),
            ('Absolute value inequalities', 'Distance reasoning turns an absolute value inequality into a compound inequality rather than two separate cases.', 'absolute value inequality;distance;compound'),
        ]),
        ('Inequalities in context', [
            ('Modelling constraints with inequalities', 'A constraint states a range the answer may occupy, which is naturally an inequality rather than an equation.', 'constraint;model;at least;at most'),
            ('Graphing linear inequalities in two variables', 'A two-variable inequality shades a half-plane bounded by the corresponding line.', 'half plane;boundary line;shading'),
        ]),
    ]),

    ('Algebra', 'Systems of linear equations', ['Linear equations', 'Linear inequalities'], [
        ('Systems and their solutions', [
            ('Systems as simultaneous constraints', 'A solution to a system must satisfy every equation at once, which is why it is an intersection rather than a root.', 'system;simultaneous;intersection'),
            ('Solving systems by graphing', 'Graphing shows the solution as an intersection, which makes the meaning of no solution and infinite solutions visible.', 'graph system;intersection;coincident'),
        ]),
        ('Algebraic solution methods', [
            ('Solving systems by substitution', 'Substitution replaces one variable with an equivalent expression so that a two-variable problem becomes one-variable.', 'substitution;isolate;substitute'),
            ('Solving systems by elimination', 'Elimination adds or subtracts multiples of equations so one variable cancels, leaving a single-variable equation.', 'elimination;add equations;cancel variable'),
            ('Special systems: no solution and infinitely many', 'Parallel distinct lines share no point and coincident lines share every point, and the algebra reports both cases.', 'no solution;infinitely many;parallel;coincident'),
            ('Choosing an efficient solution method', 'Method choice is a judgement about which form the equations are already in, not a rule about correctness.', 'method choice;substitution;elimination'),
        ]),
        ('Systems in context', [
            ('Systems modelling two constraints', 'Two unknowns with two conditions produce a system, and each equation encodes one condition.', 'model;two unknowns;constraint'),
            ('Systems with three variables', 'Three unknowns need three independent equations, and elimination extends to that case one variable at a time.', 'three variables;elimination;independent'),
            ('Introduction to linear programming', 'Optimising a linear objective under linear constraints is solved at the vertices of the feasible region.', 'linear programming;objective;feasible region'),
        ]),
    ]),

    # ---------------------------------------------------------------- Functions
    ('Algebra', 'Quadratic expressions and equations', ['Algebraic expressions', 'Linear equations', 'Exponents, radicals and irrational numbers'], [
        ('Quadratic structure', [
            ('Quadratic expressions and their graphs', 'A quadratic has a nonzero squared term, and its graph is a parabola whose vertex is the turning point.', 'quadratic;parabola;vertex;squared term'),
            ('Standard, factored and vertex forms', 'The three forms of a quadratic each expose a different feature: intercepts, roots, or the vertex.', 'standard form;factored form;vertex form;quadratic'),
            ('The zero-product property', 'A product equals zero only when at least one factor equals zero, which is what turns factoring into a solution method.', 'zero product property;factor;roots'),
        ]),
        ('Factoring', [
            ('Factoring out a common monomial factor', 'Factoring begins by removing the largest shared factor, which is the distributive property run backwards.', 'common factor;monomial;factor out'),
            ('Factoring trinomials with leading coefficient one', 'For a monic quadratic, two numbers must meet a sum condition and a product condition simultaneously.', 'factor trinomial;monic;sum and product'),
            ('Factoring trinomials with leading coefficient other than one', 'When the leading coefficient is not one, the factor pair search must also account for the leading term.', 'leading coefficient;factor trinomial;grouping'),
            ('Special products: difference of squares and perfect squares', 'Recognising a special product pattern lets you factor in one step instead of searching for a factor pair.', 'difference of squares;perfect square trinomial;special product'),
        ]),
        ('Solving and applying', [
            ('Solving quadratic equations by factoring', 'Factoring converts a quadratic equation into two linear equations, each of which is easy to solve.', 'solve by factoring;zero product;roots'),
            ('Solving quadratic equations by completing the square', 'Completing the square rewrites a quadratic as a perfect square plus a constant, which exposes the vertex and the roots.', 'completing the square;perfect square;vertex'),
            ('The quadratic formula and the discriminant', 'The quadratic formula solves every quadratic, and the discriminant reports how many real roots exist before you compute them.', 'quadratic formula;discriminant;real roots'),
            ('Choosing an efficient method for quadratics', 'Factoring, completing the square and the formula all work, and the choice is a judgement about the numbers involved.', 'method choice;factoring;formula'),
            ('Quadratic models and optimisation', 'A quadratic models any quantity with a constant second difference, and its vertex is the maximum or minimum of that model.', 'quadratic model;maximum;minimum;vertex'),
        ]),
    ]),

    ('Functions', 'Coordinate plane and relations', ['Number foundations', 'Algebraic expressions'], [
        ('Coordinates and graphing', [
            ('The coordinate plane and ordered pairs', 'An ordered pair records horizontal then vertical position, and the order is part of the meaning.', 'coordinate plane;ordered pair;x axis'),
            ('Plotting points and identifying quadrants', 'Quadrant location is determined by the signs of the coordinates, which makes sign errors visible immediately.', 'plot;quadrant;sign'),
        ]),
        ('Relations, domain and range', [
            ('Relations and multiple representations', 'The same relation can be shown as a table, a graph, a set of pairs or an equation, and each view hides different things.', 'relation;table;graph;representation'),
            ('Domain and range', 'Domain collects the permitted inputs and range the resulting outputs, and both can be restricted by context.', 'domain;range;input;output'),
            ('Discrete and continuous domains', 'A countable set of inputs gives a discrete domain while an unbroken interval gives a continuous one.', 'discrete;continuous;interval'),
        ]),
        ('Function concepts', [
            ('Functions and the vertical line test', 'A relation is a function when each input has exactly one output, which the vertical line test detects graphically.', 'function;vertical line test;one output'),
            ('Function notation', 'Function notation names the rule and the input together, which makes substitution explicit.', 'function notation;f of x;rule'),
            ('Evaluating functions and reading graphs', 'Evaluating a function and reading a value off its graph are the same act performed in two representations.', 'evaluate function;read graph;input output'),
            ('Independent and dependent variables', 'Naming which quantity drives which is a modelling decision, and it determines which axis carries which variable.', 'independent variable;dependent variable;model'),
        ]),
    ]),

    ('Functions', 'Linear functions', ['Coordinate plane and relations', 'Linear equations'], [
        ('Slope and rate of change', [
            ('Slope as a constant rate of change', 'Slope is the change in output per unit change in input, which is why it carries units.', 'slope;rate of change;units'),
            ('Computing slope from graphs, tables and points', 'The slope formula is a difference quotient, and the point order must be consistent in numerator and denominator.', 'slope formula;rise over run;two points'),
        ]),
        ('Forms of a linear equation', [
            ('Slope-intercept form', 'Writing a line as y equals mx plus b exposes the rate and the starting value directly.', 'slope intercept form;y intercept;rate'),
            ('Point-slope form', 'Point-slope form builds a line from one known point and the rate, which suits data with a natural starting observation.', 'point slope form;point;slope'),
            ('Standard form and intercepts', 'Standard form makes the x and y intercepts easy to read, which is useful for constraints written as equations.', 'standard form;intercepts;coefficients'),
            ('Parallel and perpendicular lines', 'Parallel lines share a slope while perpendicular slopes multiply to negative one, both of which follow from the geometry.', 'parallel;perpendicular;negative reciprocal'),
        ]),
        ('Linear models', [
            ('Writing equations of lines from context', 'Turning a described situation into a line requires identifying the rate and one known point.', 'model;write equation;context'),
            ('Interpreting slope and intercept in context', 'In a model the slope and intercept carry units and meaning, and misreading either produces a plausible but wrong claim.', 'interpret slope;interpret intercept;units'),
            ('Arithmetic sequences as linear functions', 'An arithmetic sequence is a linear function restricted to whole-number inputs, with the common difference as slope.', 'arithmetic sequence;common difference;linear'),
        ]),
        ('Linear data', [
            ('Scatter plots and lines of best fit', 'A line of best fit summarises a linear trend, and how close the points sit to it decides how much the summary is worth.', 'scatter plot;best fit;trend'),
            ('Correlation and causation', 'Two quantities moving together is evidence of association only, and association alone does not establish a cause.', 'correlation;causation;association'),
        ]),
    ]),

    ('Functions', 'Transformations and absolute value functions', ['Linear functions'], [
        ('Function families and transformations', [
            ('Parent functions and their graphs', 'A parent function is the simplest member of a family, and every other member is a transformation of it.', 'parent function;family;graph'),
            ('Translations of graphs', 'Adding inside the input shifts the graph horizontally in the opposite direction to the sign.', 'translation;shift;horizontal'),
            ('Reflections of graphs', 'A negative outside the function reflects vertically while a negative inside reflects horizontally.', 'reflection;axis;negative'),
            ('Stretches and compressions', 'A factor outside the function stretches or compresses vertically, and its reciprocal does the same horizontally.', 'stretch;compression;scale factor'),
        ]),
        ('Absolute value and piecewise functions', [
            ('Absolute value functions', 'The absolute value function is two linear pieces joined at a vertex, which explains its V-shaped graph.', 'absolute value function;vertex;piecewise'),
            ('Piecewise-defined functions', 'A piecewise rule applies different formulas on different parts of the domain, and each piece needs its own interval.', 'piecewise;domain;interval'),
            ('Step functions and modelling', 'A step function is constant on intervals, which fits any quantity that changes in discrete jumps.', 'step function;floor;discrete model'),
            ('Comparing linear and absolute value models', 'Choosing between a linear and an absolute value model is a claim about the shape of the underlying relationship.', 'compare models;linear;absolute value'),
        ]),
    ]),

    ('Functions', 'Exponential functions', ['Linear functions', 'Exponents, radicals and irrational numbers'], [
        ('Exponential structure', [
            ('Exponential growth and decay', 'Repeated multiplication by a constant factor produces growth or decay, which is qualitatively different from repeated addition.', 'exponential growth;decay;factor'),
            ('Exponential functions and their graphs', 'An exponential function has a constant ratio between successive outputs, which produces its characteristic curve.', 'exponential function;ratio;asymptote'),
            ('Geometric sequences', 'A geometric sequence is an exponential function restricted to whole-number inputs, with the common ratio as base.', 'geometric sequence;common ratio;exponential'),
            ('Comparing linear and exponential growth', 'Linear growth adds a constant while exponential growth multiplies by one, and the ordering of the two eventually reverses.', 'compare growth;linear;exponential'),
        ]),
        ('Exponential models and inverses', [
            ('Compound interest', 'Compound interest is exponential growth where the base is one plus the periodic rate.', 'compound interest;principal;rate'),
            ('Exponential modelling in context', 'Population, depreciation and radioactive decay all share the same multiplicative structure.', 'model;population;depreciation;half life'),
            ('Transforming exponential functions', 'Shifts and stretches move an exponential curve without changing the fact that it is exponential.', 'transform;shift;stretch'),
            ('Logarithms as inverses of exponentials', 'A logarithm answers what exponent produces a given value, which makes it the inverse of an exponential.', 'logarithm;inverse;exponent'),
            ('Solving simple exponential equations', 'When both sides share a base, matching exponents solves the equation; otherwise estimation or logarithms are required.', 'exponential equation;common base;solve'),
        ]),
    ]),

    # ---------------------------------------------------------------- Geometry & Measurement
    ('Geometry & Measurement', 'Geometric foundations', ['Coordinate plane and relations', 'Ratios, rates and proportional reasoning'], [
        ('Lines, angles and triangles', [
            ('Points, lines, rays and planes', 'These undefined terms are the vocabulary every later geometric statement is built from.', 'point;line;ray;plane'),
            ('Angle relationships', 'Complementary, supplementary and vertical angles are fixed arithmetic relationships, not estimates.', 'complementary;supplementary;vertical angles'),
            ('Parallel lines and transversals', 'A transversal across parallel lines creates equal and supplementary angle pairs that let you transfer information.', 'parallel lines;transversal;corresponding angles'),
            ('Triangle angle sum and exterior angles', 'The interior angles of a triangle sum to a straight angle, and an exterior angle equals the sum of the two remote interior angles.', 'triangle angle sum;exterior angle;remote interior'),
        ]),
        ('Similarity and coordinate geometry', [
            ('Similar figures and scale factor', 'Similar figures share angles and have proportional sides, which is what makes indirect measurement possible.', 'similar;scale factor;proportion'),
            ('Congruence and rigid motions', 'Congruent figures are related by translations, rotations and reflections, none of which change size or shape.', 'congruent;rigid motion;transformation'),
            ('The Pythagorean theorem', 'In a right triangle the squares on the legs sum to the square on the hypotenuse, which converts between distances.', 'pythagorean theorem;hypotenuse;right triangle'),
            ('The distance formula', 'The distance formula is the Pythagorean theorem applied to a difference in coordinates.', 'distance formula;coordinate;distance'),
            ('The midpoint formula', 'The midpoint formula averages coordinates, which places a point exactly halfway between two others.', 'midpoint formula;average;coordinate'),
        ]),
    ]),

    ('Geometry & Measurement', 'Measurement and geometric modelling', ['Geometric foundations', 'Algebraic expressions'], [
        ('Perimeter, area and volume', [
            ('Perimeter and area of polygons', 'Perimeter measures a boundary while area measures a region, and confusing the two changes the units of the answer.', 'perimeter;area;polygon;units'),
            ('Circumference and area of circles', 'Circle measurements are proportional to the radius and to its square respectively, which is why pi appears in both.', 'circumference;area of circle;pi;radius'),
            ('Surface area of prisms and cylinders', 'Surface area sums the areas of every face, and a net makes the individual faces countable.', 'surface area;net;prism;cylinder'),
            ('Volume of prisms, cylinders and spheres', 'Volume multiplies a base area by a height, with the sphere formula as the notable exception.', 'volume;prism;cylinder;sphere'),
        ]),
        ('Measurement reasoning', [
            ('Density and measurement unit conversion', 'Density is a rate of mass per volume, so converting units converts the density too.', 'density;mass;volume;conversion'),
            ('Composite figures and decomposition', 'Decomposing an unfamiliar region into familiar pieces is the standard route to its area.', 'composite figure;decompose;area'),
            ('Geometric modelling with algebraic expressions', 'Expressing an area or volume with a variable turns a geometry question into an algebra question.', 'model;expression;area;volume'),
            ('Precision, accuracy and significant figures', 'Precision describes the fineness of a measurement while accuracy describes its closeness to the true value, and they are independent.', 'precision;accuracy;significant figures'),
        ]),
    ]),

    # ---------------------------------------------------------------- Statistics & Probability
    ('Statistics & Probability', 'Descriptive statistics', ['Ratios, rates and proportional reasoning', 'Linear functions'], [
        ('Organising data', [
            ('Data types and variables', 'Whether a variable is categorical or quantitative decides which summaries and displays are meaningful.', 'categorical;quantitative;variable'),
            ('Frequency tables and dot plots', 'Counting how often each value occurs is the first step in every summary statistic.', 'frequency table;dot plot;count'),
            ('Histograms and binning', 'A histogram groups quantitative data into bins, and the bin width changes the shape you see.', 'histogram;bin;distribution shape'),
        ]),
        ('Centre and spread', [
            ('Measures of centre: mean, median and mode', 'The mean uses every value, the median uses position and the mode records the most common value, and each is affected differently by skew.', 'mean;median;mode;centre'),
            ('Measures of spread: range and interquartile range', 'Range uses only the extremes while the interquartile range describes the middle half, which makes it resistant to outliers.', 'range;interquartile range;spread;quartile'),
            ('Standard deviation', 'Standard deviation averages squared deviations from the mean, so it describes typical distance from centre.', 'standard deviation;deviation;variance'),
            ('Box plots and five-number summaries', 'A box plot displays the five-number summary, which shows centre, spread and skew in one picture.', 'box plot;five number summary;quartile;median'),
            ('Outliers and their effect on summaries', 'An outlier moves the mean much more than the median, so the choice of summary is a judgement about the data.', 'outlier;effect;mean;median'),
            ('Comparing distributions', 'Comparing two distributions requires centre, spread and shape together, because any one alone is misleading.', 'compare distributions;centre;spread;shape'),
        ]),
    ]),

    ('Statistics & Probability', 'Bivariate data and inference', ['Descriptive statistics', 'Linear functions'], [
        ('Relationships between two variables', [
            ('Scatter plots and association', 'A scatter plot shows whether two quantitative variables are associated, and in which direction and form.', 'scatter plot;association;direction;form'),
            ('The correlation coefficient', 'The correlation coefficient measures the strength and direction of a linear association only, and it is not a percentage.', 'correlation coefficient;strength;linear'),
            ('Lines of best fit and residuals', 'A residual is the vertical gap between an observation and the fitted line, and its pattern diagnoses whether the line fits.', 'best fit line;residual;fit'),
            ('Interpreting slope and intercept in data context', 'In a fitted model the slope is a predicted change per unit and the intercept a predicted baseline, both with units.', 'interpret slope;intercept;units;prediction'),
        ]),
        ('Categorical data and sampling', [
            ('Two-way frequency tables', 'A two-way table cross-classifies two categorical variables, which makes joint and marginal counts visible.', 'two way table;frequency;joint;marginal'),
            ('Conditional relative frequency', 'Conditioning on a row or column converts counts into rates that can be compared across groups.', 'conditional relative frequency;row;column'),
            ('Sampling methods', 'Simple random, systematic, stratified and cluster sampling each have different practical costs and assumptions.', 'sampling method;random;stratified;cluster'),
            ('Sampling bias and variability', 'A biased sample systematically misses part of the population, while variability is the unavoidable spread between samples.', 'bias;variability;sample;population'),
            ('Making and critiquing data-based claims', 'A defensible claim names the population, the sample, the method and the uncertainty, and stops short of causation without a suitable design.', 'claim;critique;population;inference'),
        ]),
    ]),

    ('Statistics & Probability', 'Probability', ['Descriptive statistics', 'Ratios, rates and proportional reasoning'], [
        ('Foundations of probability', [
            ('Sample spaces and outcomes', 'A sample space lists every possible outcome, and the list must be exhaustive and mutually exclusive.', 'sample space;outcome;exhaustive'),
            ('Theoretical probability', 'Theoretical probability divides favourable equally likely outcomes by all equally likely outcomes.', 'theoretical probability;favourable;equally likely'),
            ('Experimental probability and the law of large numbers', 'Experimental probability converges towards theoretical probability as the number of trials grows, which is why small samples mislead.', 'experimental probability;law of large numbers;trials'),
            ('Compound events and the addition rule', 'The probability of either event requires subtracting the overlap, otherwise the intersection is counted twice.', 'compound event;addition rule;union;overlap'),
            ('Independent events and the multiplication rule', 'Independent events multiply because one event does not change the other probability.', 'independent;multiplication rule;and'),
        ]),
        ('Conditional probability and counting', [
            ('Conditional probability', 'Conditional probability restricts the sample space to the known condition, which changes the denominator.', 'conditional probability;given;restrict'),
            ('Permutations and combinations', 'Permutations count arrangements where order matters and combinations count selections where it does not.', 'permutation;combination;order;selection'),
            ('Probability distributions', 'A probability distribution lists every value of a random variable with its probability, and the probabilities sum to one.', 'distribution;random variable;sum to one'),
            ('Expected value', 'Expected value is a probability-weighted average outcome, which is what makes it a long-run prediction rather than a guarantee.', 'expected value;weighted average;long run'),
            ('Simulation and probability models', 'A simulation estimates a probability by generating many trials, which is useful when a theoretical model is hard to write down.', 'simulation;model;trials;estimate'),
        ]),
    ]),
]

# Curated cross-unit prerequisites. In-unit ordering is inferred automatically, but a
# dependency that crosses units is a pedagogical claim, so it is written down by hand
# and reviewed. Format: (prerequisite title, dependent title).
LINKS: list[tuple[str, str]] = [
    ('The distributive property', 'Multi-step equations with distribution'),
    ('Combining like terms', 'Solving systems by elimination'),
    ('Combining like terms', 'Adding and subtracting polynomials'),
    ('Fraction addition and subtraction', 'Solving proportions'),
    ('Percent change', 'Exponential growth and decay'),
    ('Slope as a constant rate of change', 'Solving systems by graphing'),
    ('Slope as a constant rate of change', 'Interpreting slope and intercept in data context'),
    ('Slope-intercept form', 'Solving systems by substitution'),
    ('Function notation', 'Exponential functions and their graphs'),
    ('Domain and range', 'Exponential functions and their graphs'),
    ('Square roots and perfect squares', 'Simplifying radical expressions'),
    ('Prime factorisation', 'Simplifying radical expressions'),
    ('The Pythagorean theorem', 'The distance formula'),
    ('The distance formula', 'The midpoint formula'),
    ('Graphing inequalities on the number line', 'Interval notation'),
    ('Systems as simultaneous constraints', 'Introduction to linear programming'),
    ('Graphing linear inequalities in two variables', 'Introduction to linear programming'),
    ('Solving systems by substitution', 'Systems with three variables'),
    ('Sample spaces and outcomes', 'Compound events and the addition rule'),
    ('Conditional relative frequency', 'Conditional probability'),
    ('Probability distributions', 'Expected value'),
    ('Measures of centre: mean, median and mode', 'Standard deviation'),
    ('Interpreting slope and intercept in context', 'Interpreting slope and intercept in data context'),
    ('Scatter plots and lines of best fit', 'Lines of best fit and residuals'),
    ('Perimeter and area of polygons', 'Geometric modelling with algebraic expressions'),
    ('Exponential functions and their graphs', 'Solving simple exponential equations'),
    ('Absolute value functions', 'Absolute value inequalities'),
    ('Absolute value equations', 'Absolute value inequalities'),
    ('The distributive property', 'Factoring out a common monomial factor'),
    ('Expanding products of binomials', 'Factoring trinomials with leading coefficient one'),
    ('Expanding products of binomials', 'Special products: difference of squares and perfect squares'),
    ('Square roots and perfect squares', 'Solving quadratic equations by completing the square'),
    ('Factoring trinomials with leading coefficient one', 'Solving quadratic equations by factoring'),
    ('Factoring trinomials with leading coefficient one', 'The quadratic formula and the discriminant'),
    ('Quadratic expressions and their graphs', 'Quadratic models and optimisation'),
    ('The zero-product property', 'Solving quadratic equations by factoring'),
]


def build() -> dict:
    strands: list[dict] = []
    index: dict[str, dict] = {}
    by_title: dict[str, dict] = {}
    total = 0
    for strand, unit, prerequisites, topics in UNITS:
        block = index.get(strand)
        if block is None:
            block = {'strand': strand, 'units': []}
            index[strand] = block
            strands.append(block)
        unit_payload = {
            'unit': unit,
            'prerequisites': prerequisites,
            'topics': [
                {
                    'topic': topic,
                    'concepts': [
                        {'title': title, 'summary': summary,
                         'keywords': [k for k in keywords.split(';') if k]}
                        for title, summary, keywords in concepts
                    ],
                }
                for topic, concepts in topics
            ],
        }
        for topic, concepts in topics:
            for title, summary, keywords in concepts:
                if title in by_title:
                    raise ValueError(f'Duplicate concept title in the outline: {title!r}')
                by_title[title] = {'title': title, 'summary': summary,
                                   'keywords': [k for k in keywords.split(';') if k],
                                   'prerequisites': []}
        total += sum(len(c) for _, c in topics)
        block['units'].append(unit_payload)

    # Rebuild concept dicts from the shared registry so LINKS can attach to them.
    for block in strands:
        for unit_payload in block['units']:
            for topic_block in unit_payload['topics']:
                topic_block['concepts'] = [by_title[c['title']] for c in topic_block['concepts']]

    for prerequisite, dependent in LINKS:
        for name in (prerequisite, dependent):
            if name not in by_title:
                raise ValueError(f'LINKS references unknown concept title: {name!r}')
        entry = by_title[dependent]['prerequisites']
        if prerequisite not in entry:
            entry.append(prerequisite)

    document = {**COURSE, 'concept_count': total, 'unit_count': len(UNITS),
                'cross_unit_links': len(LINKS), 'strands': strands}
    return document


def main() -> int:
    document = build()
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(document, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'{TARGET.relative_to(ROOT)}: {document["concept_count"]} concepts across '
          f'{document["unit_count"]} units in {len(document["strands"])} strands')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
