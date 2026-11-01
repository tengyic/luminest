"""Original worked examples and questions; source books are credited, not copied.

Two layers live here and are joined by concept id:

* the **lesson layer** - the hand-authored ``CONCEPTS``/``QUESTIONS`` below, with
  full blocks, simulations, projects and diagnostic question variants;
* the **graph layer** - a much larger classified concept graph loaded from
  ``curriculum_packs/*.json``, built by ``app.ingest.pipeline``.

``LESSON_TARGETS`` is the reviewed join between them: it says which course graph
node each authored lesson teaches. Everything in the graph that is not a target is
an outline node - it takes part in prerequisite reasoning and coverage accounting
but has no lesson content yet.
"""
from fractions import Fraction
from pathlib import Path

from .ingest.policy import (KHAN_ACADEMY_TERMS, OPENSTAX_ELEMENTARY_ALGEBRA,
                            OPENSTAX_INTRODUCTORY_STATISTICS, course_media_extras,
                            reference_entry)
from .knowledge_graph import ConceptNode, KnowledgeGraph, Taxonomy, load_pack, slug
from .mathkit import template_for

# The reference URLs come from the licence gate rather than being restated here, so the link a
# learner opens and the audited rights position cannot drift apart.
SOURCE_ALGEBRA = OPENSTAX_ELEMENTARY_ALGEBRA.url
SOURCE_STATS = OPENSTAX_INTRODUCTORY_STATISTICS.url
SOURCE_KHAN = KHAN_ACADEMY_TERMS.url
SOURCES = [
    {'title': OPENSTAX_ELEMENTARY_ALGEBRA.name, 'url': SOURCE_ALGEBRA,
     'license': OPENSTAX_ELEMENTARY_ALGEBRA.licence,
     'status': 'external_link_only', 'rights_evidence': OPENSTAX_ELEMENTARY_ALGEBRA.evidence_id,
     'scope': 'Original hand-authored curriculum; no copied content, scraping, AI ingestion or permission claim.'},
    {'title': OPENSTAX_INTRODUCTORY_STATISTICS.name, 'url': SOURCE_STATS,
     'license': OPENSTAX_INTRODUCTORY_STATISTICS.licence,
     'status': 'external_link_only', 'rights_evidence': OPENSTAX_INTRODUCTORY_STATISTICS.evidence_id,
     'scope': 'Provider reports current CC BY-NC-SA transition and AI restrictions; link only pending exact-version clearance.'},
    {'title': 'Khan Academy — external, unofficial reference and terms', 'url': SOURCE_KHAN,
     'license': KHAN_ACADEMY_TERMS.licence,
     'status': 'external_link_only', 'rights_evidence': KHAN_ACADEMY_TERMS.evidence_id,
     'scope': 'External links only; no lessons, transcripts, exercises, embeddings, logos or training content copied. No endorsement.'},
]
SPECS = [
    ('fractions', 'Fractions and equivalent quantities', 'Number foundations', [], 'A fraction describes equal parts of a whole. Equivalent fractions multiply numerator and denominator by the same nonzero number.', 'a/b + c/d = (ad + bc)/(bd)', 'Write 1/2 as 2/4. Then 1/2 + 1/4 = 3/4. The denominator identifies the common unit.', 'Build a recipe scaled from two servings to five. Show how each fractional ingredient changes.', 'fraction', 'Common denominator', 'Choose a common unit before adding numerators.'),
    ('signed_numbers', 'Signed numbers and absolute value', 'Number foundations', ['fractions'], 'Signed numbers represent direction relative to zero. Subtracting a number adds its opposite; absolute value is distance from zero.', 'a - b = a + (-b)', 'From -3, subtracting -5 means moving five units right: -3 - (-5) = 2.', 'Model four temperature changes, including a negative starting temperature. Explain each direction.', 'number_line', 'Signed steps', 'Mark the starting point and the direction of each change.'),
    ('ratios', 'Ratios, proportions and percent', 'Number foundations', ['fractions'], 'A ratio compares quantities. A proportion asserts equal ratios. Percent means per hundred; a percent change uses the original quantity as denominator.', 'percent change = 100(new - old)/old', 'Three notebooks cost 12 units. The unit price is 12/3 = 4, so five notebooks cost 20.', 'Compare two package sizes by unit price and justify which is better value.', 'ratio', 'Unit rate', 'Divide the total quantity by the number of units first.'),
    ('expressions', 'Expressions and distributive structure', 'Algebra foundations', ['signed_numbers'], 'An expression names a quantity. Combine like terms only; distributing multiplication preserves equality for every value of the variable.', 'a(b + c) = ab + ac', '3(x + 2) + 2x = 3x + 6 + 2x = 5x + 6. Only the x terms combine.', 'Write and simplify a cost expression with a fixed fee and a per-item charge. Verify two inputs.', 'expression', 'Input value', 'Separate the coefficient of x from the constant term.'),
    ('equations', 'One-variable linear equations', 'Algebra foundations', ['expressions'], 'An equation asserts equal quantities. Apply the same reversible operation to both sides, then substitute the solution into the original equation.', 'ax + b = c implies x = (c - b)/a, a != 0', '4x + 3 = 19. Subtract 3 from both sides: 4x = 16. Divide by 4: x = 4; checking gives 19.', 'Create a budget equation, solve it, and substitute your result to check the budget.', 'balance', 'Balance both sides', 'Undo addition first, then undo multiplication.'),
    ('inequalities', 'Linear inequalities', 'Algebra foundations', ['equations'], 'An inequality describes a range. Multiplying or dividing both sides by a negative number reverses the order; show whether the boundary is included.', 'a < b implies -a > -b', '-2x < 6. Dividing by -2 reverses the sign, so x > -3. The boundary -3 is not included.', 'Model a capacity limit with an inequality. Give a valid value, an invalid value and the boundary.', 'number_line', 'Boundary', 'Check whether you divided by a negative number.'),
    ('coordinates', 'Coordinates and slope', 'Functions', ['signed_numbers', 'ratios'], 'A coordinate pair records horizontal and vertical position. Slope is the change in output divided by the change in input; vertical lines have undefined slope.', 'm = (y2 - y1)/(x2 - x1)', 'For (1, 2) and (4, 8), slope is (8 - 2)/(4 - 1) = 6/3 = 2.', 'Record two distance-time observations and compute slope with units. Interpret that rate.', 'slope', 'Horizontal change', 'Keep the same point order in both differences.'),
    ('linear_functions', 'Linear functions and intercepts', 'Functions', ['coordinates', 'equations'], 'A linear function has constant rate of change. In y = mx + b, m is slope and b is the output when the input is zero.', 'y = mx + b', 'For y = 3x - 2, the output at x = 4 is 10. Increasing x by 1 increases y by 3.', 'Compare two delivery pricing rules. Explain slope, intercept and the point where costs match.', 'linear', 'Input x', 'Substitute into the entire expression, including the intercept.'),
    ('systems', 'Systems of linear equations', 'Functions', ['linear_functions'], 'A solution to a system satisfies every equation. Use substitution or elimination, and check both equations; parallel distinct lines have no common solution.', 'a common solution satisfies both equations', 'For x + y = 7 and x - y = 1, adding gives 2x = 8. Thus x = 4 and y = 3; both equations check.', 'Find two quantities from their total and difference. Solve and check both constraints.', 'systems', 'Total', 'Choose an operation that eliminates one variable, then check both equations.'),
    ('exponents', 'Exponents and polynomial products', 'Algebra foundations', ['expressions'], 'A positive integer exponent counts repeated factors. When multiplying powers with the same base, add exponents; distribute every term in polynomial products.', 'x^a x^b = x^(a+b)', '(x + 2)(x + 3) = x^2 + 3x + 2x + 6 = x^2 + 5x + 6.', 'Expand a rectangle area with variable side lengths, and verify the expression at two values.', 'polynomial', 'Input x', 'Account for every pair of factors in the product.'),
    ('factoring', 'Factoring quadratics', 'Quadratics', ['exponents'], 'Factoring reverses multiplication. For a monic quadratic, seek two numbers whose sum is the middle coefficient and whose product is the constant.', 'x^2 + (r+s)x + rs = (x+r)(x+s)', 'x^2 + 7x + 12 = (x + 3)(x + 4), because 3 + 4 = 7 and 3 times 4 = 12.', 'Construct a quadratic from two linear factors. Expand, factor it again, and explain both checks.', 'polynomial', 'Factor constant', 'Check both the sum and the product, not just one.'),
    ('quadratics', 'Quadratic equations and graphs', 'Quadratics', ['factoring', 'linear_functions'], 'A quadratic function includes a nonzero squared term. Its graph is a parabola. A product equals zero only when at least one factor equals zero.', 'ax^2 + bx + c = 0; x = (-b +/- sqrt(b^2 - 4ac))/(2a)', 'x^2 - 5x + 6 = (x - 2)(x - 3) = 0, so x = 2 or x = 3. Substitute each to verify.', 'Model a rectangle area constraint with a quadratic. Solve and reject roots that cannot be lengths.', 'quadratic', 'Input x', 'Set each factor equal to zero and check all possible roots.'),
    ('probability', 'Probability and sample spaces', 'Data and uncertainty', ['ratios'], 'For equally likely outcomes, probability is favorable outcomes divided by all outcomes. Independence means one event does not change the probability of the other.', 'P(A) = favorable/total; P(A and B) = P(A)P(B) for independent events', 'A fair six-sided die has three even outcomes: P(even) = 3/6 = 1/2. Two independent even rolls have probability 1/4.', 'Define the sample space of two coin tosses. Compare theoretical probabilities with a small trial and discuss variation.', 'probability', 'Number of trials', 'List equally likely outcomes before counting favorable ones.'),
    ('descriptive_stats', 'Mean, median and spread', 'Data and uncertainty', ['fractions', 'signed_numbers'], 'Mean is the sum divided by count. Median is the center of sorted data. Range is maximum minus minimum; outliers can strongly affect the mean.', 'mean = sum(x)/n; range = max(x) - min(x)', 'For 2, 3, 4, 7, the mean is 16/4 = 4, median is (3 + 4)/2 = 3.5 and range is 5.', 'Compare two small datasets using mean, median and range. Explain how one outlier changes your summary.', 'statistics', 'Outlier value', 'Sort the observations and count them before choosing a statistic.'),
    ('data_interpretation', 'Interpreting data and uncertainty', 'Data and uncertainty', ['descriptive_stats', 'probability', 'linear_functions'], 'A data claim needs a defined population, sampling method and units. Association alone does not establish causation; small samples can vary substantially.', 'sample proportion = successes/sample size', 'If 12 of 20 sampled items pass inspection, the sample proportion is 12/20 = 0.60. It describes this sample, not a guaranteed population rate.', 'Design a small survey, state a sampling limitation, compute a proportion, and distinguish observation from causal inference.', 'sampling', 'Sample size', 'Describe what was actually observed and one reason it may not generalize.'),
    ('variables_and_algebraic_notation', 'Variables and algebraic notation', 'Algebraic expressions', ['expressions'], 'A variable stands for an unspecified quantity; an algebraic expression is a recipe built from variables, numbers and operations. Evaluating means substituting a value for every variable and following the order of operations.', 'if a = 3 and b = 1, then 5a - 2b = 15 - 2 = 13', 'With a = 4 and b = 2, 5a - 2b = 20 - 4 = 16. Each letter is replaced by its value before any arithmetic is done.', 'Write an expression for the cost of a pizza with a fixed base price and a per-topping charge, then evaluate it for two different orders.', 'expression', 'Probe value a', 'Substitute one variable at a time and keep each operation attached to its term.'),
    ('combining_like_terms', 'Combining like terms', 'Algebraic expressions', ['variables_and_algebraic_notation'], 'Like terms share the same variable part. An expression shortens by adding the coefficients of like terms, but a term with x and a plain number never combine.', 'ax + bx = (a + b)x', '3x + 4 + 2x + 5 = 5x + 9: the x terms pool their coefficients and the constants pool separately.', 'Simplify a shopping expression with several item types, naming which terms are like and why the others stay apart.', 'expression', 'Probe input x', 'Group terms by their variable part first, then combine each group.'),
    ('the_distributive_property', 'The distributive property', 'Algebraic expressions', ['combining_like_terms'], 'Multiplication distributes over addition: every term inside the parentheses is multiplied. Distribution and factoring are the same structure read in opposite directions.', 'a(b + c) = ab + ac', '4(x - 3) = 4x - 12. Both terms receive the multiplier, including the sign of the second term.', 'Expand a phone plan expression with a fixed fee per line and explain which term absorbed the multiplier.', 'expression', 'Probe input x', 'Draw arrows from the multiplier to every term inside the parentheses.'),
    ('one_step_equations', 'One-step equations', 'Linear equations', ['signed_numbers'], 'A one-step equation is undone by a single inverse operation: subtraction undoes addition, division undoes multiplication. Whatever operation undoes the left side also undoes the right.', 'x + b = c means x = c - b;  ax = c means x = c/a, a != 0', 'x + 7 = 12 subtracts 7 from both sides to give x = 5. Checking: 5 + 7 = 12.', 'Convert a real quantity question into a one-step equation, solve it, and verify by substitution.', 'balance', 'Probe input x', 'Name the operation that produced the equation, then apply its inverse to both sides.'),
    ('two_step_equations', 'Two-step equations', 'Linear equations', ['one_step_equations'], 'A two-step equation unwinds in reverse order of operations: clear the constant term first, then divide by the coefficient. Each step applies to both sides.', 'ax + b = c gives x = (c - b)/a', '3x + 4 = 19: subtract 4 to reach 3x = 15, then divide by 3 to find x = 5. Substitution confirms 19.', 'Model a taxi fare with a flag-fall and a per-kilometre charge, solve for the distance from a total, and check.', 'balance', 'Probe input x', 'Ask what happened to x last; undo that operation first.'),
    ('equations_with_variables_on_both_sides', 'Equations with variables on both sides', 'Linear equations', ['two_step_equations'], 'When variables appear on both sides, gather them onto one side first by adding or subtracting an x-term from both sides; the result is an ordinary two-step equation.', 'ax + b = cx + d gives (a - c)x = d - b', '3x + 5 = 5x - 1: subtract 3x from both sides to get 5 = 2x - 1, then x = 3. Both sides evaluate to 14.', 'Compare two payment plans as equations with variables on both sides and find the usage that equalises them.', 'balance', 'Probe input x', 'Choose which side keeps the variable and gather consistently.'),
    ('solving_proportions', 'Solving proportions', 'Ratios, rates and proportional reasoning', ['ratios'], 'A proportion states that two ratios are equal. Cross-multiplication is valid because it multiplies both sides by both denominators; the solution should still be checked in the original proportion.', 'x/b = a/c means cx = ab, so x = ab/c', 'x/6 = 2/3 cross-multiplies to 3x = 12, so x = 4; indeed 4/6 = 2/3.', 'Scale a recipe proportionally and justify the cross-multiplication step in words.', 'ratio', 'Probe quantity', 'Cross-multiply, then divide by the coefficient of x.'),
    ('percent_change', 'Percent change', 'Ratios, rates and proportional reasoning', ['ratios'], 'Percent change compares a new value to the original value: change divided by original, times 100. The denominator is always the starting quantity, not the new one.', 'percent change = 100(new - original)/original', 'Rising from 8 to 10 is 2/8 of the original, a 25% increase. Falling back from 10 to 8 is a 20% decrease, because the base changed.', 'Track two price changes on one item and show why the percent change differs in each direction.', 'ratio', 'Probe original', 'Write change/original as a fraction before converting to percent.'),
    ('direct_variation', 'Direct variation', 'Ratios, rates and proportional reasoning', ['linear_functions'], 'Two quantities vary directly when their ratio is constant: y = kx for a fixed k. The constant k is the value of y at x = 1 and the slope of the line through the origin.', 'y = kx, where k = y/x is constant', 'If y = 6 when x = 3, then k = 2, so at x = 5, y = 10. Every point satisfies y/x = 2.', 'Find a directly proportional quantity in daily life, measure two pairs, compute k twice, and compare.', 'linear', 'Constant k', 'Compute k from the given pair before predicting the new value.'),
    ('point_slope_form', 'Point-slope form', 'Linear functions', ['linear_functions'], 'A line is determined by one point and a slope. Point-slope form encodes the rise-over-run definition rearranged: the difference of outputs equals the slope times the difference of inputs.', 'y - y1 = m(x - x1)', 'Through (2, 5) with slope 3: y - 5 = 3(x - 2). At x = 4 the equation gives y = 11, matching 5 + 3(4 - 2).', 'Write the equation of a line from one real observation and one measured rate, then predict a further point.', 'linear', 'Slope m', 'Keep the signs of the coordinates exactly as the formula writes them.'),
    ('standard_form_and_intercepts', 'Standard form and intercepts', 'Linear functions', ['linear_functions'], 'Standard form Ax + By = C handles equations where solving for y is unnecessary. Setting y = 0 gives the x-intercept; setting x = 0 gives the y-intercept.', 'Ax + By = C: x-intercept (C/A, 0), y-intercept (0, C/B), A and B nonzero', '2x + 3y = 12 crosses the x-axis at (6, 0) and the y-axis at (0, 4). Both intercepts satisfy the original equation.', 'Convert a budget constraint into standard form, find both intercepts, and interpret each as an extreme purchase.', 'linear', 'Probe input x', 'Zero out one variable at a time; never zero both.'),
    ('solving_systems_by_substitution', 'Solving systems by substitution', 'Systems of linear equations', ['systems'], 'Substitution solves a system by using one equation to express a variable, then replacing it in the other equation. The result is a single equation in a single variable.', 'if y = expression, substitute it into the other equation', 'x + y = 7 with y = x + 1 substitutes to x + x + 1 = 7, so 2x = 6 and x = 3, y = 4. Both equations check.', 'Solve a price-comparison system by substitution and verify the pair in both original statements.', 'systems', 'Probe input x', 'Substitute the entire expression, parentheses included.'),
    ('solving_systems_by_elimination', 'Solving systems by elimination', 'Systems of linear equations', ['solving_systems_by_substitution'], 'Elimination adds or subtracts the equations so one variable cancels. The coefficients are matched first, sometimes by scaling one equation; the surviving equation gives one variable, and back-substitution gives the other.', 'adding ax + by = e to ax - by = f cancels y: 2ax = e + f', '2x + y = 8 and 2x - y = 0 add to 4x = 8, so x = 2; substituting back gives y = 4. Both equations check.', 'Solve a total-and-difference problem by elimination and explain why the chosen operation cancels one variable.', 'systems', 'Probe input x', 'Match one coefficient exactly before adding or subtracting.'),
    ('parallel_and_perpendicular_lines', 'Parallel and perpendicular lines', 'Linear functions', ['point_slope_form'], 'Parallel lines share the same slope and never meet. Perpendicular lines have slopes whose product is -1: the perpendicular slope is the negative reciprocal.', 'perpendicular to slope m is slope -1/m; parallel is m', 'A line of slope 3/4 is met perpendicularly by a line of slope -4/3, since (3/4)(-4/3) = -1.', 'Design two streets that meet a main road perpendicularly and express each as an equation.', 'slope', 'Slope m', 'Form -1/m; check by multiplying the two slopes.'),
    ('the_pythagorean_theorem', 'The Pythagorean theorem', 'Geometric foundations', ['coordinates'], 'In a right triangle, the square of the hypotenuse equals the sum of the squares of the legs. The theorem computes a missing length but applies only when a right angle is present.', 'a^2 + b^2 = c^2, where c is the hypotenuse', 'Legs 6 and 8 give c^2 = 36 + 64 = 100, so c = 10. The hypotenuse is the longest side, so c = -10 is rejected.', 'Measure a real rectangular object, verify its diagonal with the theorem, and state the assumption that the corner is square.', 'slope', 'Leg scale', 'Square both legs, add, then take the positive square root.'),
]
LESSON_DETAILS = {
    'fractions': (
        'The denominator must be nonzero and pieces must refer to the same whole. A numerator counts units; a denominator names their size. Multiplying both by 2 changes the description, not the quantity.',
        '1. To add 2/3 and 1/4, choose twelfths because 12 is divisible by 3 and 4.\n2. Rename 2/3 as 8/12 and 1/4 as 3/12.\n3. Add like units: 8/12 + 3/12 = 11/12.\n4. Check magnitude: the result exceeds 2/3 but is below 1; 11/12 fits those bounds.',
        'Adding denominators fails: 1/2 + 1/2 is one whole, not 2/4. A common whole matters too: half a small pizza plus half a large pizza is not necessarily one large pizza.',
        'Without notes, compute 3/5 + 1/10 and explain why the denominator stays 10. Then decide whether 2/6 and 1/3 name the same quantity.',
        'Draw equal-length bars split into twentieths to verify 3/5 + 1/10 = 7/10. This representation checks the unit choice independently of symbolic addition.'),
    'signed_numbers': (
        'Opposites sum to zero. Absolute value ignores direction but not magnitude: |-5| = 5. Subtraction is an operation, while a negative sign may describe the number being subtracted.',
        '1. Start at -4 for -4 - (-7).\n2. Replace subtraction of -7 with addition of +7.\n3. Move seven units right: -4 + 7 = 3.\n4. Reverse the calculation: 3 + (-7) = -4, so the subtraction is consistent.',
        'The claim that subtracting always makes a number smaller is false: 2 - (-3) = 5. Also |-3 + 3| = 0, whereas |-3| + |3| = 6; absolute value does not distribute over addition.',
        'Compute -6 - (-2) and 5 - 9. Name the starting point, movement and endpoint for each before calculating.',
        'Check -6 - (-2) = -4 by adding -2 back to -4. Compare that inverse check with a number-line drawing.'),
    'ratios': (
        'A unit rate divides quantities with units, such as cost per notebook. Proportional reasoning assumes a constant rate. Percent change requires a nonzero original value; the base must be stated.',
        '1. Six identical notebooks cost 27 units, so divide 27 by 6 to get 4.5 units per notebook.\n2. For ten notebooks, multiply 4.5 by 10 to get 45.\n3. Verify 27/6 = 45/10 by cross products: both products are 270.\n4. A bulk discount would invalidate the constant-rate assumption.',
        'A 20% rise followed by a 20% fall does not restore the original: 100 becomes 120, then 96. The second percentage uses a different base. Adding two notebooks does not mean adding two cost units.',
        'Eight pens cost 20 units at a constant price. Predict the cost of twelve and explain the units in your intermediate rate. What is the percent change from 20 to 25?',
        'Check the twelve-pen cost using a scale factor of 12/8 rather than first computing a unit rate. Both routes should give 30 units.'),
    'expressions': (
        'A term includes its sign. Like terms have the same variable part: 3x and -2x combine, but 3x and 3x^2 do not. An identity holds for every allowed input, unlike an equation that may hold only at particular inputs.',
        '1. Expand 4(x - 2) + 3x by multiplying both terms inside the parentheses: 4x - 8 + 3x.\n2. Combine the x terms to get 7x - 8.\n3. At x = 2, the original is 4(0) + 6 = 6 and the simplified form is 14 - 8 = 6.\n4. At x = -1, both forms give -15.',
        'Distributing only to the first term is wrong: 2(x + 3) is not 2x + 3. At x = 0 the two forms give 6 and 3. Likewise x + x = 2x, not x^2.',
        'Simplify 3(2x - 1) - x without notes. Explain which terms combine and test a negative input.',
        'Evaluate the original and proposed simplified expression at x = 0 and x = -2. A mismatch disproves an identity; agreement at only two points is a check, not a proof for arbitrary expressions.'),
    'equations': (
        'Equivalent equations have the same solution set. Adding the same number or dividing by the same nonzero constant on both sides preserves solutions. Dividing by an unknown that could be zero can lose solutions.',
        '1. Solve 3(x - 2) + 4 = 16 by distributing: 3x - 6 + 4 = 16.\n2. Combine constants: 3x - 2 = 16.\n3. Add 2 to both sides: 3x = 18. Divide both sides by 3: x = 6.\n4. Substitute into the original: 3(6 - 2) + 4 = 16.',
        'Changing one side only breaks balance: from 2x + 4 = 10, writing 2x = 10 is not equivalent. Not every linear-looking equation has one solution: x + 1 = x + 2 has none, and x + 1 = x + 1 has all real solutions.',
        'Solve 5x - 7 = 18 and state the operation on each side at every step. Then explain why 0x = 4 has no solution.',
        'Substitute your answer into the unsimplified original equation, not just the last transformed line. For 5x - 7 = 18, x = 5 produces 18.'),
    'inequalities': (
        'A solution set is a range of values. Strict signs exclude the boundary; <= and >= include it. Addition preserves order, but multiplying or dividing by a negative constant reverses order.',
        '1. Solve -3x + 2 <= 11 by subtracting 2: -3x <= 9.\n2. Divide by -3 and reverse the comparison: x >= -3.\n3. Test the included boundary x = -3: the original gives 11 <= 11.\n4. Test x = 0 (valid) and x = -4 (invalid).',
        'Keeping the sign after negative division fails: -2 < 4, but dividing by -2 gives 1 > -2. A strict inequality such as x > 2 does not include 2, even when nearby larger numbers work.',
        'Solve -4x < 12. Give one valid value, one invalid value and the boundary, with an explanation of the reversed sign.',
        'Test values on both sides of the boundary directly in the original inequality. A boundary-only check cannot tell which side of a number line is the solution.'),
    'coordinates': (
        'In (x, y), horizontal position comes first. Slope is signed rise divided by signed run and has output-units per input-unit. A horizontal line has slope zero; a vertical line has zero run and undefined slope.',
        '1. For (2, 5) and (6, -3), subtract in a consistent order: rise = -3 - 5 = -8, run = 6 - 2 = 4.\n2. Divide: slope = -8/4 = -2.\n3. Reverse both differences: 8/(-4) also gives -2.\n4. Interpret: each additional horizontal unit corresponds to two fewer vertical units.',
        'Reversing only one difference changes the sign incorrectly. The line through (3, 1) and (3, 9) does not have slope 8: its run is zero, so the slope is undefined.',
        'Find the slope through (-1, 4) and (2, 10). Then describe the slopes of y = 5 and x = 5 without dividing by zero.',
        'Draw a rise-run triangle and count six units up for three units right. Swapping the point order in both differences independently checks the same slope of 2.'),
    'linear_functions': (
        'In y = mx + b, m is a constant rate and b is the value at x = 0. Inputs may be restricted by context: a number of delivered packages cannot be negative or fractional when packages are counted.',
        '1. A delivery costs y = 2.5x + 6, where x counts packages. The fixed fee is 6 and the rate is 2.5 per package.\n2. At x = 4, calculate 2.5(4) + 6 = 16.\n3. At x = 5, calculate 18.5; the increase is exactly 2.5.\n4. The intercept is (0, 6), not (6, 0).',
        'A larger intercept does not mean a larger slope. y = x + 10 starts higher than y = 3x but grows more slowly. A graph of y = x^2 is not linear because its equal-input increments are not constant.',
        'For y = -2x + 5, find the intercept and outputs at x = 1 and x = 3. Explain why a negative slope does not require every output to be negative.',
        'Build a two-row input-output table and compute change in y divided by change in x. Compare the measured rate to m; then separately check x = 0 for b.'),
    'systems': (
        'A pair (x, y) solves a system only if both equations hold. Different slopes give one intersection; parallel distinct lines give none; coincident lines give infinitely many common points.',
        '1. Solve x + y = 9 and x - y = 3 by adding: 2x = 12.\n2. Divide by 2: x = 6.\n3. Substitute into x + y = 9: y = 3.\n4. Check both originals: 6 + 3 = 9 and 6 - 3 = 3. The intersection is (6, 3).',
        'The pair (5, 4) satisfies the total of 9 but not the difference of 3. Checking one constraint is insufficient. Lines y = 2x + 1 and y = 2x - 4 never meet.',
        'Solve x + y = 12 and x - y = 4. Check the ordered pair in both equations. Then distinguish no solution from infinitely many solutions.',
        'Rewrite the example as y = 9 - x and y = x - 3. Equating these expressions independently gives x = 6; the plotted intersection should match (6, 3).'),
    'exponents': (
        'For positive integer n, x^n is n repeated factors, not n times x. The same-base product law adds exponents. Expansion uses every term pair; negative inputs require care with parentheses.',
        '1. Expand (x + 2)(x - 3): multiply x by x and -3 to get x^2 - 3x.\n2. Multiply 2 by x and -3 to get 2x - 6.\n3. Combine like terms: x^2 - x - 6.\n4. At x = 4, the product is 6 times 1 = 6 and the expansion is 16 - 4 - 6 = 6.',
        'x^2 + x^3 is not x^5: exponent addition applies to multiplication, not addition. Also (-2)^2 = 4 but -2^2 = -4 under the usual order of operations.',
        'Expand (x + 4)(x + 2) and list all four products. Explain the difference between x^3 x^2 and x^3 + x^2.',
        'Use a rectangle divided into four subareas to check every product term. Evaluate the expanded and factored forms at x = 0 and x = 3 to catch missing constants or cross terms.'),
    'factoring': (
        'A factorization is an identity, not yet a solution of an equation. For a monic quadratic, the factor constants must meet both sum and product conditions. Some quadratics do not factor over the integers.',
        '1. Factor x^2 - x - 12. List integer pairs with product -12: (1, -12), (-1, 12), (2, -6), (-2, 6), (3, -4), (-3, 4).\n2. Choose 3 and -4 because their sum is -1.\n3. Write (x + 3)(x - 4).\n4. Expand to check: x^2 - 4x + 3x - 12 = x^2 - x - 12.',
        'Choosing numbers only because their product matches can fail: (x + 2)(x + 6) has constant 12 but middle coefficient 8, not 7. No integer pair has both sum 1 and product 1, so x^2 + x + 1 has no integer factorization.',
        'Factor x^2 + 6x + 8. State the required sum and product before choosing the numbers. Does factoring alone tell you the roots without an equation?',
        'Expand your proposed factors and compare all three coefficients. A substitution check at x = 0 checks the constant only and cannot replace checking the middle coefficient.'),
    'quadratics': (
        'A quadratic has a != 0. Roots solve y = 0 and correspond to horizontal-axis crossings when real. The discriminant b^2 - 4ac distinguishes two, one or no real roots; complex roots are outside this introductory graph task.',
        '1. Solve x^2 - 6x + 8 = 0 by factoring: (x - 2)(x - 4) = 0.\n2. Apply the zero-product property separately: x = 2 or x = 4.\n3. Substitute both into the original; both give zero.\n4. The vertex lies midway at x = 3; y = -1. In a length problem, reject any root that violates stated physical constraints.',
        'The zero-product property requires a product equal to zero: (x - 2)(x - 4) = 5 cannot be solved by simply setting each factor to zero. Reporting just one of two valid roots is incomplete.',
        'Solve (x - 1)(x - 5) = 0 and verify both roots. Explain why y = x^2 + 1 has no real horizontal-axis crossing.',
        'Use the quadratic formula on x^2 - 6x + 8: the discriminant is 4 and roots are (6 +/- 2)/2. This checks factoring independently; the graph checks real crossings.'),
    'probability': (
        'A sample space lists possible outcomes. Favorable/total requires equally likely elementary outcomes. For n independent trials with a constant success probability p, a binomial distribution describes the number of successes, not their order.',
        '1. Two fair coin tosses have ordered outcomes HH, HT, TH, TT, each with probability 1/4.\n2. Exactly one head occurs in HT or TH, so its probability is 2/4 = 1/2.\n3. Two heads has probability (1/2)(1/2) = 1/4 using independence.\n4. With n = 2 and p = 1/2, the probabilities for 0, 1 and 2 heads are 1/4, 1/2 and 1/4 and sum to one.',
        'Counting outcome labels alone fails if they are unequal in likelihood. In two tosses, zero heads, one head and two heads are not equally likely. Drawing without replacement usually changes probabilities and invalidates a simple independence product.',
        'List the sample space for two fair tosses and find P(at least one head). Contrast that event with exactly one head. What assumptions does a binomial plot need?',
        'Use the complement: P(at least one head) = 1 - P(TT) = 3/4. Compare to direct counting. Short simulations may differ from theory; they do not invalidate it by themselves.'),
    'descriptive_stats': (
        'Mean uses every value; median uses ordered position. With an even count, average the two middle values. Range describes extremes, not the full shape; different distributions can share the same summaries.',
        '1. Sort 8, 2, 5, 3 to obtain 2, 3, 5, 8.\n2. Sum 18 and divide by 4: mean = 4.5.\n3. Average the middle two values: median = (3 + 5)/2 = 4.\n4. Range = 8 - 2 = 6. Replacing 8 by 28 raises the mean to 9.5 and range to 26 but leaves the median at 4.',
        'The median is not the middle entry of an unsorted list. The mean need not be an observed value. Reporting range alone can hide clustering or outliers; it is not a complete measure of distribution.',
        'For 1, 2, 2, 7, find mean, median and range. Predict which statistics change if 7 becomes 27, then calculate to check.',
        'Check a mean by multiplying it by the observation count and recovering the sum. Check the median by counting ordered observations on either side, rather than reusing the mean procedure.'),
    'data_interpretation': (
        'A sample is observed; a population is the group a claim targets. A sampling frame and selection process affect representation. A proportion needs a count denominator; association does not establish cause without a suitable design.',
        '1. Suppose 18 of 30 sampled items pass inspection. The sample proportion is 18/30 = 0.60.\n2. State the observed group and method: items chosen from one morning batch.\n3. The observation describes that sample; selection bias and random variation may affect a population claim.\n4. No before-after comparison or randomized assignment was observed, so the inspection cannot be claimed to cause improvement.',
        'A sample proportion of 0.60 is not a guarantee that exactly 60% of the next batch passes. A voluntary survey may overrepresent strongly interested people. Two variables moving together can reflect a third variable or selection effects.',
        'A voluntary survey finds 14 of 20 respondents prefer option A. State the sample proportion, the population you would like to describe and one reason the result may not generalize.',
        'Independently recompute 14/20 as 0.70, then audit who could enter the sample and who did not respond. Arithmetic correctness does not resolve sampling bias or prove causation.'),
    'variables_and_algebraic_notation': (
        'A variable names a quantity that can change or is not yet known; it is not a hidden number to guess. Coefficients multiply variables: in 5a, the 5 belongs to a. Substitution replaces every occurrence of a letter with its value, keeping signs attached.',
        '1. Evaluate 5a - 2b at a = 4, b = 2.\n2. Replace a: 5(4) = 20. Replace b: 2(2) = 4.\n3. Subtract: 20 - 4 = 16.\n4. Reverse-check with a = 3, b = 1: 15 - 2 = 13, consistent with the same recipe.',
        'Treating 5a - 2b as 5a + 2b fails: at a = 4, b = 2 the first gives 16 and the second 24. Reading ab as a + b is a different error: 4 times 2 = 8, not 6.',
        'Evaluate 3x + 2y at x = 5, y = -1 without notes, naming each substitution before computing.',
        'Evaluate 5a - 2b and 5(a - b) at the same inputs: 16 versus 5 at a = 4, b = 2. The mismatch shows multiplication does not distribute over subtraction here without expanding first.'),
    'combining_like_terms': (
        'A term is a coefficient together with its variable part; the sign belongs to the term. Like terms have identical variable parts: 3x and 2x combine, 3x and 4 do not, and 3x and 3x^2 do not. Collecting like terms is repeated addition of coefficients.',
        '1. Simplify 3x + 4 + 2x + 5.\n2. Group: (3x + 2x) + (4 + 5).\n3. Combine coefficients: 5x + 9.\n4. Check at x = 1: original 3 + 4 + 2 + 5 = 14; simplified 5 + 9 = 14.',
        'Combining x terms with constants fails: 3x + 4 is not 7x. At x = 1 the two forms give 7 and 7 only by coincidence; at x = 2 they give 10 versus 14. Also 3x + 2x is 5x, not 5x^2.',
        'Simplify 4x + 7 - x + 2 without notes, keeping the sign of each term as you regroup.',
        'Evaluate the original and simplified expressions at x = 0 (constants only) and x = 3. Agreement at both points checks the collection; disagreement names exactly which group was miscounted.'),
    'the_distributive_property': (
        'Distribution multiplies every addend inside the parentheses: a(b + c) = ab + ac. The multiplier must reach the second term even when that term is negative. Factoring reverses the move by extracting a common factor.',
        '1. Expand 4(x - 3).\n2. Multiply the first term: 4x.\n3. Multiply the second term with its sign: 4 times -3 = -12.\n4. Result: 4x - 12. Check at x = 5: original 4(2) = 8; expanded 20 - 12 = 8.',
        'Distributing to only the first term gives 4x - 3, not 4x - 12: at x = 5 they differ, 17 versus 8. Dropping the sign gives 4x + 12, which fails the same check.',
        'Expand 6(x - 4) and then verify at x = 2, showing both computations.',
        'Compare 4(x - 3) and 4x - 3 at x = 0 and x = 3. The mismatch locates the error in the constant term, which is exactly where partial distribution loses information.'),
    'one_step_equations': (
        'Solving is undoing. An equation records operations applied to an unknown; each is reversed with its inverse on both sides. Addition and subtraction are inverses, as are multiplication and division. Division by zero is never allowed.',
        '1. Solve x + 7 = 12.\n2. Subtract 7 from both sides: x = 5.\n3. Check: 5 + 7 = 12.\n4. For 4x = 20, divide both sides by 4: x = 5; check 4(5) = 20.',
        'Operating on one side only breaks balance: from x + 7 = 12, writing x = 12 changes the equation. Dividing 4x = 20 by 4 on the left but not the right gives x = 20, which fails the check.',
        'Solve x - 6 = -2 and 5x = 35, naming the inverse operation used in each.',
        'Solve x + 7 = 12 two ways: by subtracting 7 and by substituting candidate values. The solution set is the same, which shows checking is a search for the value that balances, not a different rule.'),
    'two_step_equations': (
        'Order matters because operations were applied in an order. If n was multiplied by a and then increased by b, undo b first and a second. Each undo applies to the whole side, so dividing after clearing the constant divides every remaining term.',
        '1. Solve 3x + 4 = 19.\n2. Subtract 4 from both sides: 3x = 15.\n3. Divide both sides by 3: x = 5.\n4. Check: 3(5) + 4 = 19. Reversing the order (dividing 19 by 3 first) mixes the constant into the quotient.',
        'Dividing only the 3x term by 3 while leaving +4 outside gives x + 4 = 19/3, a different equation. Clearing the constant after dividing fails the check: x = 5 must satisfy the original, not a rewritten one.',
        'Solve 2x - 5 = 11 and state which operation was undone at each step.',
        'Solve 3x + 4 = 19 by first subtracting 4 and alternatively by substituting x = 5 into the original. Then test x = 19/3 - 4/3: it satisfies the wrongly-divided equation, showing why order discipline matters.'),
    'equations_with_variables_on_both_sides': (
        'Variables on both sides mean the unknown has been combined with itself twice. Gather all x-terms on one side by subtracting the smaller x-term from both sides; gather constants on the other. The equation then reduces to a two-step form.',
        '1. Solve 3x + 5 = 5x - 1.\n2. Subtract 3x from both sides: 5 = 2x - 1.\n3. Add 1: 6 = 2x, so x = 3.\n4. Check both originals: 3(3) + 5 = 14 and 5(3) - 1 = 14.',
        'Cancelling x from both sides of 3x + 5 = 5x - 1 leaves 5 = 5x - 1 only if the terms were equal, which they are not; dropping one x entirely gives 5 = -1, a false statement. The x-terms must be gathered, not erased.',
        'Solve 6x + 2 = 2x + 10 and verify the pair of values on both sides.',
        'Solve the same equation by gathering x-terms to the left instead of the right: -2x + 5 = -1. Both routes give x = 3, showing the gathering direction is a choice, not a rule.'),
    'solving_proportions': (
        'A proportion says two ratios are equal: a/b = c/d. Cross-multiplication gives ad = bc because it multiplies both sides by both denominators in one move. The check is to confirm the solved ratio simplifies to the given one.',
        '1. Solve x/6 = 2/3.\n2. Cross-multiply: 3x = 12.\n3. Divide by 3: x = 4.\n4. Check: 4/6 = 2/3 because both simplify to 2/3.',
        'Cross-multiplying the wrong diagonal gives 6x = 6? no: pairing x with 3 and 6 with 2 produces x times 3 = 12 only if the pairs are (x, 3) and (6, 2)... the wrong pairing multiplies x by 2: 2x = 12, x = 6, and 6/6 = 1 is not 2/3. The check catches it.',
        'Solve x/9 = 4/6 and verify the solution by simplifying both ratios.',
        'Solve x/6 = 2/3 by cross-multiplication and again by scaling: 2/3 = 4/6, so x = 4. Both routes agree, which independently confirms the cross-product step.'),
    'percent_change': (
        'Percent change measures the change relative to the original: (new - original)/original, times 100. Increases and decreases use the same formula; only the sign of the change differs. The base is the starting value, never the ending value.',
        '1. A price rises from 8 to 10.\n2. Change = 2. Original = 8.\n3. 2/8 = 0.25, so the increase is 25%.\n4. Reversing from 10 to 8 gives 2/10 = 20% decrease: the same absolute change is a different percent because the base moved.',
        'Dividing by the new value understates an increase: 2/10 = 20% instead of 25%. Reporting the raw difference 2 as "2%" confuses a quantity with a rate. Sequential changes do not cancel: +25% then -20% returns to the start, not to zero net percent.',
        'A population grows from 40 to 50. Compute the percent increase, naming the base explicitly.',
        'Compute the increase from 8 to 10 and the decrease from 10 to 8: 25% versus 20%. The asymmetry is not an error; it follows from the changing denominator.'),
    'direct_variation': (
        'Direct variation means y = kx with k constant: doubling x doubles y. The constant is computed from any single known pair, k = y/x, and reused for every prediction. The graph is a straight line through the origin.',
        '1. Given y = 6 when x = 3.\n2. k = 6/3 = 2.\n3. Predict y at x = 5: y = 2 times 5 = 10.\n4. Verify the ratio: 10/5 = 2, the same k.',
        'Assuming k = 1 gives y = 5 instead of 10. Adding the new x to the given y gives 9, which does not preserve the ratio 2. Inverting the ratio (x/y = 1/2) predicts y = 2.5, also wrong.',
        'y varies directly as x and y = 14 when x = 2. Find y when x = 7, computing k first.',
        'Compute k from the pair (3, 6) and independently from the predicted pair (5, 10): both give 2. A constant ratio across two pairs is the definition, so agreement here is a real check, not a tautology.'),
    'point_slope_form': (
        'Point-slope form states the rise-over-run definition with symbols: y - y1 = m(x - x1). The point (x1, y1) is a specific known point; the signs in the formula are subtraction signs, so a negative coordinate enters with its sign.',
        '1. Line through (2, 5) with slope 3.\n2. Substitute: y - 5 = 3(x - 2).\n3. Expand: y = 3x - 6 + 5 = 3x - 1.\n4. Check at x = 2: y = 5, the known point.',
        'Writing y + 5 = 3(x - 2) flips the y-sign: at x = 2 it gives y = -5, not 5. Writing x + 2 fails similarly. Expanding to y = 3x + 5 keeps the intercept without subtracting m times x1.',
        'Write the equation of the line through (-1, 4) with slope 2, keeping the signs of the coordinates.',
        'Convert y - 5 = 3(x - 2) to slope-intercept form and verify both the point (2, 5) and a second point such as (4, 11) on the expanded line.'),
    'standard_form_and_intercepts': (
        'Standard form Ax + By = C suits constraints and intercept work. An intercept is where a variable is zero: setting y = 0 gives the x-intercept C/A; setting x = 0 gives the y-intercept C/B. Both require the coefficient to be nonzero.',
        '1. 2x + 3y = 12.\n2. x-intercept: y = 0 gives 2x = 12, x = 6: the point (6, 0).\n3. y-intercept: x = 0 gives 3y = 12, y = 4: the point (0, 4).\n4. Check: 2(6) + 3(0) = 12 and 2(0) + 3(4) = 12.',
        'Zeroing both variables at once gives 0 = 12, which is false and finds nothing. Swapping the intercepts claims the line meets the y-axis at (6, 0), which the check 2(0) + 3(6) = 18 refutes.',
        'Find both intercepts of 4x + 6y = 24 as coordinate pairs.',
        'Convert 2x + 3y = 12 to slope-intercept form: y = -2/3 x + 4. The y-intercept 4 matches the standard-form computation, a route-independent check.'),
    'solving_systems_by_substitution': (
        'Substitution turns two equations into one: solve the simpler equation for a variable, then replace that variable in the other equation. The substituted expression must enter whole, with parentheses if it has more than one term.',
        '1. x + y = 7 and y = x + 1.\n2. Substitute: x + (x + 1) = 7.\n3. Collect: 2x = 6, so x = 3.\n4. Back-substitute: y = 4. Check: 3 + 4 = 7 and 4 = 3 + 1.',
        'Substituting into the same equation the expression came from gives 0 = 0 and no information. Dropping the parentheses in x + (x + 1) can produce x + x + 1 misread as x + 1 + 1; collecting carefully prevents it. Swapping the final pair puts 4 in the wrong slot and fails the first equation.',
        'Solve y = 2x and x + y = 9 by substitution, then check the pair in both equations.',
        'Solve the same system by graphing by hand: the lines y = 2x and y = 9 - x cross at (3, 6), matching the algebraic answer. Two independent methods agreeing is strong evidence.'),
    'solving_systems_by_elimination': (
        'Elimination cancels one variable by adding or subtracting the equations, possible only when that variable has equal or opposite coefficients. Scale an equation first if needed. After finding one variable, substitute back for the other.',
        '1. 2x + y = 8 and 2x - y = 0.\n2. Add the equations: the y terms cancel, 4x = 8.\n3. Divide: x = 2.\n4. Back-substitute: y = 8 - 2(2) = 4. Check both: 2(2) + 4 = 8 and 2(2) - 4 = 0.',
        'Adding without matching coefficients leaves both variables. Forgetting back-substitution reports only x = 2, half the answer. Leaving 4x = 8 undivided reports x = 4, which fails the first equation: 2(4) + 4 = 12.',
        'Solve 3x + y = 10 and 3x - y = 2 by elimination, then verify the pair.',
        'Solve the same system by substitution (y = 10 - 3x) and confirm the same pair (2, 4). Elimination and substitution must agree; a disagreement means an arithmetic slip in one of them.'),
    'parallel_and_perpendicular_lines': (
        'Parallel lines have equal slopes and never intersect. Perpendicular lines have slopes multiplying to -1: the perpendicular slope to m is -1/m, the negative reciprocal. Horizontal and vertical lines are perpendicular under the same idea taken to the limit.',
        '1. A line has slope 3/4.\n2. Reciprocal: 4/3.\n3. Negate: -4/3.\n4. Check: (3/4)(-4/3) = -1. A parallel line keeps slope 3/4 exactly.',
        'Negating without reciprocating gives -3/4, and (3/4)(-3/4) = -9/16, not -1. Reciprocating without negating gives 4/3. Only the negative reciprocal satisfies the product test.',
        'Find the slope perpendicular to -2/5 and verify by multiplying the two slopes.',
        'Write the equation of a line perpendicular to y = 2x through (0, 1): slope -1/2 gives y = -x/2 + 1. Substituting a second point confirms the product of slopes is -1.'),
    'the_pythagorean_theorem': (
        'For a right triangle with legs a, b and hypotenuse c, a^2 + b^2 = c^2. The hypotenuse is opposite the right angle and is the longest side, so only the positive root is a length. The theorem needs a right angle; without one it does not apply.',
        '1. Legs 6 and 8.\n2. Squares: 36 and 64; sum 100.\n3. Root: c = 10.\n4. The negative root -10 is rejected because a length is positive. Scaling the triangle by 2 scales the hypotenuse to 20, consistent with (2a)^2 + (2b)^2 = (2c)^2.',
        'Adding the legs without squaring gives 14, not 10. Keeping the square (c = 100) confuses a length with its square. Multiplying the legs (48) computes an area-like quantity, not a length.',
        'Find the hypotenuse of a right triangle with legs 5 and 12, showing the squares before the root.',
        'Verify 3-4-5 by measuring: draw the legs on grid paper and count the diagonal against the 5-unit diagonal of a 3 by 4 rectangle. The geometric check matches the algebra.'),
}


def parameter(pid, label, low, high, value, step=0.1):
    return {'id': pid, 'label': label, 'min': low, 'max': high, 'value': value, 'step': step,
            'integer': step == 1}


SIMULATIONS = {
    'linear_functions': [parameter('m', 'Slope m', -4, 4, 3), parameter('b', 'Intercept b', -6, 6, -2), parameter('value', 'Probe input x', -5, 5, 4)],
    'quadratics': [parameter('a', 'Squared coefficient a', 0.2, 2, 1), parameter('b', 'Linear coefficient b', -8, 8, -5), parameter('c', 'Constant c', -8, 8, 6), parameter('value', 'Probe input x', -5, 5, 2)],
    'systems': [parameter('m1', 'First slope', -3, 3, -1), parameter('b1', 'First intercept', -9, 9, 7), parameter('m2', 'Second slope', -3, 3, 1), parameter('b2', 'Second intercept', -9, 9, -1), parameter('value', 'Probe input x', -5, 5, 4)],
    'probability': [parameter('n', 'Independent trials n', 1, 40, 10, 1), parameter('p', 'Success probability p', 0, 1, 0.5, 0.05)],
}
CONCEPTS = {}
QUESTIONS = {}
for spec in SPECS:
    cid, title, unit, prerequisites, summary, formula, example, project, sim_kind, label, hint = spec
    source = SOURCE_STATS if unit == 'Data and uncertainty' else SOURCE_ALGEBRA
    definitions, worked, misconception, retrieval, crosscheck = LESSON_DETAILS[cid]
    low, high, default, step = (-5, 5, 2, 0.1)
    if sim_kind in {'fraction', 'ratio'}:
        low, high, default, step = (1, 10, 3, 1)
    elif sim_kind == 'sampling':
        low, high, default, step = (5, 200, 20, 1)
    elif sim_kind == 'statistics':
        low, high, default, step = (0, 30, 7, 1)
    if cid == 'fractions':
        label = 'Denominator n'
    elif cid in {'signed_numbers', 'inequalities'}:
        label = 'Signed movement from -3'
    elif cid == 'factoring':
        label = 'Probe input x'
    CONCEPTS[cid] = {
        'id': cid, 'title': title, 'unit': unit, 'prerequisites': prerequisites, 'summary': summary,
        'blocks': [
            {'kind': 'concept', 'title': 'Core idea', 'body': summary, 'formula': formula},
            {'kind': 'concept', 'title': 'Definitions and conditions', 'body': definitions},
            {'kind': 'worked_example', 'title': 'Worked multi-step example', 'body': worked},
            {'kind': 'reflection', 'title': 'Counterexample and misconception', 'body': misconception},
            {'kind': 'retrieval', 'title': 'Retrieve without notes', 'body': retrieval + ' Report your confidence from 0 to 1 before checking.'},
            {'kind': 'reflection', 'title': 'Independent cross-check', 'body': crosscheck},
            {'kind': 'retrieval', 'title': 'Transfer to a new setting', 'body': project + ' Change one assumption and explain which part of your method must change.'},
            {'kind': 'reflection', 'title': 'Evidence scope and external references',
             'body': 'These definitions, examples and prompts are original hand-authored mathematics. Retrieval and spacing research motivates practice, but does not establish app efficacy, a universal correctness target or certified mastery. One response is uncertain task evidence, not a learner label. External readings are link-only; no source content is scraped, copied or ingested for AI training. No permission or endorsement is implied.', 'source_url': source},
        ],
        'simulation': {'kind': sim_kind, 'title': title + ' exploration', 'parameters': SIMULATIONS.get(cid, [parameter('value', label, low, high, default, step)]),
                       'scope': 'A simplified mathematical representation; predict before changing a parameter and verify with an independent calculation.'},
        'project': {'title': title + ': apply and justify', 'prompt': project, 'rubric': ['Define quantities, units and assumptions.', 'Show a mathematically valid method with intermediate steps.', 'Verify the result independently or with a counterexample.', 'Reflect on limitations and disclose any AI assistance.']},
        'media': [reference_entry(OPENSTAX_INTRODUCTORY_STATISTICS if unit == 'Data and uncertainty'
                                  else OPENSTAX_ELEMENTARY_ALGEBRA,
                                  'OpenStax — external reference, not app content'),
                  reference_entry(KHAN_ACADEMY_TERMS,
                                  'Khan Academy — external, unofficial reference and terms'),
                  # The course-level video hubs and simulation providers. The authored
                  # mathematics course keeps its own hand-picked reading list, so it does not
                  # go through reference_media() and would otherwise be the one course with no
                  # video or simulation card at all.
                  *course_media_extras('integrated_math_1')],
        'hint': hint,
    }


DISTRACTOR_RULES = {
    'fractions': [('conceptual', 'The choice adds denominators as though units could be combined.', 'Use equal-sized pieces to compare 1/2 + 1/2 with one whole.'), ('procedural', 'The numerator may have been omitted while forming a common denominator.', 'Rename both fractions using a common denominator before adding.'), ('calculation', 'The result may use the wrong common-unit scale.', 'Check the result against the sum of decimal approximations.')],
    'signed_numbers': [('conceptual', 'The choice treats subtraction of a negative as addition of a negative.', 'Compare 0 - (-2) with a number-line movement.'), ('procedural', 'The subtraction order may have been reversed.', 'Add the subtracted number back to the proposed result.'), ('conceptual', 'The choice may replace signed quantities by absolute values.', 'Explain how -3 + 7 differs from 3 + 7.')],
    'ratios': [('conceptual', 'The choice adds item count directly to cost.', 'Name the units of the unit price and use a ratio table.'), ('calculation', 'The quantity appears one unit short.', 'Count the requested units and multiply the unit price again.'), ('calculation', 'The quantity appears one unit too large.', 'Check the requested count with a proportional scaling route.')],
    'expressions': [('procedural', 'The constant inside the parentheses may not have been multiplied.', 'Evaluate both expressions at x = 0.'), ('conceptual', 'A variable term may have been combined with a constant.', 'Group terms by their variable part before combining.'), ('procedural', 'The distribution may have used addition in place of multiplication.', 'List each product in the distribution and test x = 1.')],
    'equations': [('calculation', 'The proposed root is one larger than the solution.', 'Substitute the proposed root into the original equation.'), ('calculation', 'The proposed root is one smaller than the solution.', 'Substitute the proposed root and compare both sides.'), ('procedural', 'The last division by the coefficient may be missing.', 'Distinguish the value of nx from the value of x.')],
    'inequalities': [('procedural', 'The direction was not reversed after negative division.', 'Test a value on each side of the proposed boundary.'), ('calculation', 'The boundary sign may have been lost.', 'Compute the boundary using equality, then test both sides.'), ('conceptual', 'A strict boundary was included.', 'Substitute the boundary into the strict original inequality.')],
    'coordinates': [('procedural', 'Only one of the point differences may have been reversed.', 'Reverse both differences and compare the slope.'), ('procedural', 'The rise may have been reported without dividing by run.', 'Draw a rise-run triangle and label both changes.'), ('conceptual', 'Run over rise may have replaced rise over run.', 'State output-units per input-unit and compute that ratio.')],
    'linear_functions': [('calculation', 'The intercept sign may have been changed.', 'Check the intercept at x = 0 before substituting x = 4.'), ('procedural', 'The input may not have been multiplied by the slope.', 'Write the substituted expression with parentheses.'), ('conceptual', 'Slope and intercept may have been treated as inputs rather than rule parameters.', 'Build an input-output table and distinguish x, m and b.')],
    'systems': [('conceptual', 'The ordered coordinates may have been swapped.', 'Check the ordered pair in the difference equation.'), ('procedural', 'The total is satisfied but the second constraint is not.', 'Substitute into both equations, not only the total.'), ('procedural', 'The total is satisfied but the difference does not match.', 'Compute total and difference separately for the pair.')],
    'exponents': [('procedural', 'One cross product may be missing.', 'List all four term pairs in the product.'), ('calculation', 'The constant product may not have been computed.', 'Evaluate the product and expansion at x = 0.'), ('procedural', 'A variable cross product may be omitted.', 'Use a four-cell area model and sum the x terms.')],
    'factoring': [('calculation', 'Both factor signs are reversed.', 'Expand and compare the middle coefficient sign.'), ('procedural', 'The chosen constants do not satisfy both conditions.', 'Check the sum and product of the proposed constants.'), ('conceptual', 'One sign changes the product and the middle coefficient.', 'Expand all four products to test the identity.')],
    'quadratics': [('calculation', 'The roots may use the factor constants with the wrong sign.', 'Substitute each proposed root into its factor.'), ('procedural', 'Only one of two zero factors was considered.', 'Set each factor equal to zero separately.'), ('conceptual', 'A zero product may have been interpreted as requiring x = 0.', 'Test x = 0 in the original product, then test each factor root.')],
    'probability': [('conceptual', 'The denominator counts only the other color rather than all outcomes.', 'List all counters and identify favorable and total counts.'), ('procedural', 'The complementary event may have been selected.', 'Identify which color the event names and compare complements.'), ('conceptual', 'One elementary outcome may have replaced the full favorable event.', 'Count every favorable counter, not only one.')],
    'descriptive_stats': [('conceptual', 'The median may have been used in place of the mean.', 'Compute mean and median separately and explain their definitions.'), ('conceptual', 'The maximum may have been used as a central summary.', 'Explain why every observation contributes to the mean.'), ('procedural', 'The sum may not have been divided by the count.', 'Multiply the proposed mean by the count and recover the sum.')],
    'data_interpretation': [('conceptual', 'The claim guarantees future outcomes from a sample.', 'Describe a different future batch consistent with this sample.'), ('conceptual', 'The claim infers causation without a suitable comparison.', 'Name the missing causal comparison and possible confounding.'), ('conceptual', 'The claim infers individual unsampled outcomes.', 'Construct two populations with the same observed sample but different unsampled outcomes.')],
    'variables_and_algebraic_notation': [('procedural', 'The value of the subtracted term may have been added instead.', 'Keep the minus sign on 2b and subtract after substituting.'), ('procedural', 'The coefficients may have been swapped between a and b.', 'Substitute each value into its original position before multiplying.'), ('conceptual', 'The expression may have been factored before substituting.', 'Substitute first, then compute once; 5(a - b) is a different expression.')],
    'combining_like_terms': [('procedural', 'A constant term may have been dropped while collecting.', 'Recount the plain numbers separately from the x terms.'), ('calculation', 'The x coefficients may have been miscounted.', 'List 3x and 2x, then add the coefficients 3 and 2.'), ('conceptual', 'The constants may have been multiplied rather than added.', 'Like terms combine by addition: check the constant sum directly.')],
    'the_distributive_property': [('procedural', 'The multiplier may have reached only the first term.', 'Distribute to every term inside the parentheses.'), ('procedural', 'The sign of the second term may have been lost.', 'Carry each term sign into its product.'), ('procedural', 'The multiplier may have reached only the second term.', 'Multiply the variable term too, not only the constant.')],
    'one_step_equations': [('calculation', 'The quotient may be off by one.', 'Substitute the proposed root into the original equation.'), ('calculation', 'The quotient may be off by one in the other direction.', 'Reverse the division: multiply the proposal by the coefficient.'), ('procedural', 'The coefficient may have been added to the quotient instead of divided out.', 'nx = c needs division by n, not an adjustment by n.')],
    'two_step_equations': [('calculation', 'The root may be one too large after the division.', 'Substitute the proposed root into the original equation.'), ('calculation', 'The root may be one too small after the division.', 'Substitute the proposed root and compare both sides.'), ('procedural', 'The constant was never cleared before dividing.', 'Subtract the constant from both sides first, then divide.')],
    'equations_with_variables_on_both_sides': [('procedural', 'The x-terms may have been gathered toward the wrong side, mixing the constant in.', 'Gather all x-terms on one side and all constants on the other, consistently.'), ('procedural', 'The coefficient difference may have been reported as the root.', 'Solve (a - c)x = d - b completely before answering.'), ('calculation', 'The constant difference was never divided by the coefficient difference.', 'Divide d - b by a - c to finish.')],
    'solving_proportions': [('procedural', 'The proportion was solved on the wrong diagonal.', 'Multiply each numerator by the opposite denominator.'), ('procedural', 'The denominator of the given ratio was reported as the result.', 'Solve qx = ab for x; the denominator is not the answer.'), ('calculation', 'The cross product was divided by the wrong factor.', 'Divide ab by the coefficient q of x.')],
    'percent_change': [('conceptual', 'The new value may have been used as the denominator.', 'Divide the change by the original value.'), ('procedural', 'The raw difference may have been reported as a percent.', 'Convert change/original to a percentage by multiplying by 100.'), ('procedural', 'The ratio old/new may have replaced the change ratio.', 'Compute (new - original)/original, not original/new.')],
    'direct_variation': [('procedural', 'The new input was added to the given output instead of scaled.', 'Multiply the new x by the computed constant k.'), ('conceptual', 'The constant was assumed to be 1.', 'Compute k = y/x from the given pair first.'), ('calculation', 'The arithmetic in k times the new input may be off.', 'Recompute k(new x) step by step.')],
    'point_slope_form': [('procedural', 'The sign of y1 was flipped in the formula.', 'Use y - y1 exactly: subtract the given y-coordinate.'), ('procedural', 'The sign of x1 was flipped in the formula.', 'Use x - x1 exactly: subtract the given x-coordinate.'), ('procedural', 'The expanded form kept the wrong constant.', 'Expand m(x - x1) + y1 and simplify the constant carefully.')],
    'standard_form_and_intercepts': [('conceptual', 'The intercepts may have been swapped.', 'Set y = 0 for the x-intercept and x = 0 for the y-intercept.'), ('procedural', 'The division by the coefficient may have gone astray.', 'Recompute C/A step by step.'), ('procedural', 'The constant was never divided by the coefficient.', 'Solve Ax = C by dividing both sides by A.')],
    'solving_systems_by_substitution': [('procedural', 'The coordinates may have been swapped in the final pair.', 'Check the pair in the first equation with x and y in their places.'), ('procedural', 'The expression was substituted into the equation it came from.', 'Substitute into the other equation, where the variable still appears.'), ('procedural', 'The value of x was copied into y without back-substitution.', 'Compute y from its own equation after finding x.')],
    'solving_systems_by_elimination': [('procedural', 'The coordinates may have been swapped in the final pair.', 'Verify the pair in the difference equation.'), ('procedural', 'The eliminated variable was never back-substituted.', 'Solve for the second variable from either original equation.'), ('calculation', 'The summed equation was left undivided.', 'After adding, divide both sides by the coefficient of x.')],
    'parallel_and_perpendicular_lines': [('procedural', 'The reciprocal was taken without negating.', 'Flip the fraction and change the sign.'), ('procedural', 'The sign was changed without taking the reciprocal.', 'Perpendicular needs both the flip and the sign change.'), ('conceptual', 'The parallel slope was given instead of the perpendicular one.', 'Parallel lines share m; perpendicular lines need -1/m.')],
    'the_pythagorean_theorem': [('conceptual', 'The legs were added without squaring.', 'Square each leg, add, then take the square root.'), ('procedural', 'The square was kept without taking the root.', 'c^2 = 100 means c = 10, not 100.'), ('conceptual', 'The legs were multiplied instead of squared and added.', 'Compute a^2 + b^2, not a times b.')],
}


def add(cid, variant, prompt, answer, distractors, explanation, category='procedure_cross_check', seconds=60):
    values = [str(answer)] + [str(x) for x in distractors]
    if len(set(values)) != 4:
        raise ValueError(f'Duplicate choices for {cid}/{variant}: {values}')
    offset = (variant * 3 + len(cid)) % 4
    values = values[offset:] + values[:offset]
    qid = f'{cid}-{variant + 1}'
    options = [{'id': chr(97 + i), 'text': value} for i, value in enumerate(values)]
    mapped = {}
    for text_value, (kind, reason, check) in zip(map(str, distractors), DISTRACTOR_RULES[cid]):
        option_id = next(o['id'] for o in options if o['text'] == text_value)
        mapped[option_id] = {'category': kind, 'reason': reason, 'next_action': check}
    QUESTIONS[qid] = {'id': qid, 'concept_id': cid, 'concept_title': CONCEPTS[cid]['title'], 'prompt': prompt,
                      'options': options, 'kind': 'multiple_choice', 'expected_seconds': seconds,
                      'answer_id': next(x['id'] for x in options if x['text'] == str(answer)),
                      'answer_text': str(answer), 'explanation': explanation, 'category': category, 'distractor_diagnoses': mapped}


for v in range(4):
    n = v + 2
    denominator = 2 * n
    answer = Fraction(1, n) + Fraction(1, denominator)
    add('fractions', v, f'Compute 1/{n} + 1/{denominator}. Give a simplified fraction.', answer,
        [Fraction(2, 3*n), Fraction(1, 3*n), Fraction(3, n)], f'Use denominator {denominator}: 2/{denominator} + 1/{denominator} = 3/{denominator} = {answer}.', 'common_unit_cross_check')
    a, b = -(v + 3), -(v + 7)
    add('signed_numbers', v, f'Compute {a} - ({b}).', a-b, [a+b, b-a, abs(a)+abs(b)], f'Subtracting {b} adds its opposite: {a} + {-b} = {a-b}.', 'sign_cross_check')
    cost, count = 4+n, 3+n
    add('ratios', v, f'{count} identical notebooks cost {cost*count} units. What do {count+2} notebooks cost?', cost*(count+2), [cost*count+2, cost*(count+1), cost*(count+3)], f'The unit price is {cost*count}/{count} = {cost}. Multiply by {count+2} to obtain {cost*(count+2)}.')
    add('expressions', v, f'Simplify {n}(x + 3) + 2x.', f'{n+2}x + {3*n}', [f'{n+2}x + 3', f'{n}x + {3*n+2}', f'{n+2}x + {n+3}'], f'Distribute: {n}x + {3*n} + 2x. Combining x terms gives {n+2}x + {3*n}.', 'distributive_cross_check')
    solution = n+1
    add('equations', v, f'Solve {n}x + 5 = {n*solution+5}.', solution, [solution+1, solution-1, n*solution], f'Subtract 5: {n}x = {n*solution}. Divide by {n}: x = {solution}. Substitution checks the equation.')
    boundary = n+1
    add('inequalities', v, f'Solve -{n}x < {n*boundary}.', f'x > -{boundary}', [f'x < -{boundary}', f'x > {boundary}', f'x >= -{boundary}'], f'Divide by -{n} and reverse the inequality: x > -{boundary}. The strict boundary is excluded.', 'inequality_direction_cross_check')
    add('coordinates', v, f'Find the slope through (1, 2) and (3, {2+2*n}).', n, [-n, 2*n, Fraction(1,n)], f'Slope is ({2+2*n} - 2)/(3 - 1) = {2*n}/2 = {n}.')
    add('linear_functions', v, f'For y = {n}x - 3, find y when x = 4.', 4*n-3, [4*n+3, n-3, n+1], f'Substitute x = 4: y = {n} times 4 - 3 = {4*n-3}.')
    x, y = n+2, n
    add('systems', v, f'Solve x + y = {x+y} and x - y = 2. Select (x, y).', f'({x}, {y})', [f'({y}, {x})', f'({x+1}, {y-1})', f'({x-1}, {y+1})'], f'Add the equations: 2x = {x+y+2}, so x = {x}. Then y = {x+y} - {x} = {y}. Both equations hold.')
    add('exponents', v, f'Expand (x + {n})(x + 1).', f'x^2 + {n+1}x + {n}', [f'x^2 + {n}x + {n}', f'x^2 + {n+1}x + 1', f'x^2 + x + {n}'], f'Distributing gives x^2 + x + {n}x + {n} = x^2 + {n+1}x + {n}.')
    add('factoring', v, f'Factor x^2 + {n+1}x + {n}.', f'(x + {n})(x + 1)', [f'(x - {n})(x - 1)', f'(x + {n+1})(x + 1)', f'(x + {n})(x - 1)'], f'The numbers {n} and 1 have sum {n+1} and product {n}, so the factors are (x + {n})(x + 1).')
    add('quadratics', v, f'Solve (x - {n})(x - {n+2}) = 0. Give all roots.', f'{n} and {n+2}', [f'{-n} and {-n-2}', str(n), f'0 and {n+2}'], f'The zero-product rule gives x - {n} = 0 or x - {n+2} = 0. Both {n} and {n+2} satisfy the original equation.', 'all_roots_cross_check', 90)
    favorable = n
    add('probability', v, f'A bag has {n} blue and {n+3} red counters, equally likely to be drawn. What is P(blue)?', Fraction(n,2*n+3), [Fraction(n,n+3), Fraction(n+3,2*n+3), Fraction(1,2*n+3)], f'There are {2*n+3} equally likely counters and {n} favorable ones: P(blue) = {Fraction(n,2*n+3)}.', 'sample_space_cross_check')
    values = [n, n+1, n+2, n+5]
    mean = Fraction(sum(values),4)
    add('descriptive_stats', v, f'Find the mean of {", ".join(map(str,values))}.', mean, [Fraction(2*n+3,2), n+5, sum(values)], f'The sum is {sum(values)} across four observations, so mean = {sum(values)}/4 = {mean}.', 'statistic_cross_check')
    successes, total = 2*n+1, 5*n
    add('data_interpretation', v, f'{successes} of {total} sampled items passed inspection. Which claim is supported by this observation alone?', f'The sample pass proportion is {successes}/{total}.', ['The same fraction of every future batch will pass.', 'The inspection process caused all items to improve.', 'Every unsampled item must fail.'], f'The observation establishes the sample proportion {successes}/{total}. It does not guarantee future outcomes, establish causation or describe every unsampled item.', 'generalization_cross_check', 90)

for v in range(4):
    n = v + 2
    a, b = n + 1, n
    add('variables_and_algebraic_notation', v, f'Evaluate 5a - 2b when a = {a} and b = {b}.',
        5*a - 2*b, [5*a + 2*b, 5*b - 2*a, 5*(a - b)],
        f'Substitute in place: 5({a}) - 2({b}) = {5*a} - {2*b} = {5*a - 2*b}.', 'substitution_cross_check')
    ca, cb = n, n + 1
    add('combining_like_terms', v, f'Simplify 3x + {ca} + 2x + {cb}.',
        f'5x + {ca + cb}', [f'5x + {cb}', f'6x + {ca + cb}', f'5x + {ca * cb}'],
        f'The x terms give 3x + 2x = 5x; the constants give {ca} + {cb} = {ca + cb}.', 'like_terms_cross_check')
    add('the_distributive_property', v, f'Expand 4(x - {n}).',
        f'4x - {4*n}', [f'4x - {n}', f'4x + {4*n}', f'x - {4*n}'],
        f'Distribute 4 to both terms: 4x, and 4 times {n} keeps its minus sign, giving 4x - {4*n}.', 'distribution_cross_check')
    s = n + 2
    add('one_step_equations', v, f'Solve {n}x = {n*s}.',
        s, [s + 1, s - 1, n + s],
        f'Divide both sides by {n}: x = {n*s}/{n} = {s}. Check: {n}({s}) = {n*s}.', 'inverse_op_cross_check')
    add('two_step_equations', v, f'Solve {n}x + {n + 4} = {n*(n + 1) + n + 4}.',
        n + 1, [n + 2, n, n*(n + 1) + n + 4],
        f'Subtract {n + 4}: {n}x = {n*(n + 1)}. Divide by {n}: x = {n + 1}. Substitution checks the original.', 'order_cross_check')
    add('equations_with_variables_on_both_sides', v,
        f'Solve {n + 1}x + 3 = {n + 3}x - {2*n + 1}.',
        n + 2, [n + 3, n + 1, 2*n + 4],
        f'Subtract {n + 1}x: 3 = 2x - {2*n + 1}. Add {2*n + 1}: 2x = {2*n + 4}, so x = {n + 2}. Both sides evaluate equally.', 'gather_cross_check')
    p, q, d = n, n + 1, 2*(n + 1)
    add('solving_proportions', v, f'Solve x/{d} = {p}/{q}.',
        2*n, [n, 2*n + 2, 2*n + 1],
        f'Cross-multiply: {q}x = {p} times {d} = {p*d}. Divide by {q}: x = {2*n}. Check: {2*n}/{d} = {p}/{q}.', 'cross_multiply_cross_check')
    add('percent_change', v, f'A price rises from {4*n} to {5*n}. What is the percent increase?',
        '25%', ['20%', '5%', '80%'],
        f'The change is {n} on an original of {4*n}: {n}/{4*n} = 1/4 = 25%. The denominator is the original value.', 'base_cross_check')
    add('direct_variation', v, f'y varies directly as x, and y = {2*n} when x = {n}. Find y when x = {n + 3}.',
        2*n + 6, [2*n + 3, n + 3, 2*n + 2],
        f'k = y/x = {2*n}/{n} = 2, so y = 2 times {n + 3} = {2*n + 6}.', 'constant_k_cross_check')
    add('point_slope_form', v, f'Write the equation of the line through (1, 2) with slope {n}.',
        f'y - 2 = {n}(x - 1)', [f'y + 2 = {n}(x - 1)', f'y - 2 = {n}(x + 1)', f'y = {n}x + 2'],
        f'Point-slope form is y - y1 = m(x - x1): y - 2 = {n}(x - 1). Expanding gives y = {n}x + {2 - n}, not y = {n}x + 2.', 'sign_cross_check')
    add('standard_form_and_intercepts', v, f'Find the x-intercept of {n}x + {n}y = {2*n*n}. Give it as a coordinate pair.',
        f'({2*n}, 0)', [f'(0, {2*n})', f'({n}, 0)', f'({2*n*n}, 0)'],
        f'Set y = 0: {n}x = {2*n*n}, so x = {2*n}. The intercept is ({2*n}, 0).', 'intercept_cross_check')
    add('solving_systems_by_substitution', v, f'Solve x + y = {2*n + 3} and y = x + 1. Select (x, y).',
        f'({n + 1}, {n + 2})', [f'({n + 2}, {n + 1})', f'({2*n + 3}, {n + 1})', f'({n + 1}, {n + 1})'],
        f'Substitute y = x + 1: x + x + 1 = {2*n + 3}, so 2x = {2*n + 2} and x = {n + 1}; y = {n + 2}. Both equations check.', 'substitute_cross_check')
    add('solving_systems_by_elimination', v, f'Solve {n}x + y = {3*n + 1} and {n}x - y = {n - 1}. Select (x, y).',
        f'(2, {n + 1})', [f'({n + 1}, 2)', f'(2, {3*n + 1})', f'(4, {n + 1})'],
        f'Adding cancels y: {2*n}x = {4*n}, so x = 2. Back-substitute: y = {3*n + 1} - {2*n} = {n + 1}. Both equations check.', 'eliminate_cross_check')
    add('parallel_and_perpendicular_lines', v, f'A line has slope {n}. What is the slope of a line perpendicular to it?',
        f'-1/{n}', [f'1/{n}', f'-{n}', str(n)],
        f'The perpendicular slope is the negative reciprocal: -1/{n}. The product {n} times (-1/{n}) is -1.', 'reciprocal_sign_cross_check')
    add('the_pythagorean_theorem', v, f'A right triangle has legs {3*n} and {4*n}. How long is the hypotenuse?',
        5*n, [7*n, 25*n, 12*n*n],
        f'({3*n})^2 + ({4*n})^2 = {9*n*n} + {16*n*n} = {25*n*n} = ({5*n})^2, so the hypotenuse is {5*n}.', 'right_angle_cross_check')

def validate_curriculum():
    visited, visiting = set(), set()
    def visit(cid):
        if cid in visiting:
            raise ValueError('Curriculum contains a prerequisite cycle')
        if cid in visited:
            return
        visiting.add(cid)
        for prerequisite in CONCEPTS[cid]['prerequisites']:
            if prerequisite not in CONCEPTS:
                raise ValueError('Unknown prerequisite')
            visit(prerequisite)
        visiting.remove(cid)
        visited.add(cid)
    for cid in CONCEPTS:
        visit(cid)
        if sum(q['concept_id'] == cid for q in QUESTIONS.values()) < 4:
            raise ValueError('Every concept requires four variants')
    return True


validate_curriculum()


# ---------------------------------------------------------------------------
# Graph layer: a full course knowledge graph, loaded from generated packs.
# ---------------------------------------------------------------------------

PACK_DIR = Path(__file__).resolve().parent / 'curriculum_packs'

#: Packs merged into the runtime graph, in order. Later packs replace duplicate ids.
COURSE_PACKS = ('algebra_one_year',)

#: Reviewed join from an authored lesson to the course node it teaches.
#: A lesson is one node's worth of depth; the graph is the whole course's structure.
LESSON_TARGETS = {
    'fractions': 'fraction_equivalence',
    'signed_numbers': 'signed_numbers_on_the_number_line',
    'ratios': 'ratios_as_comparisons',
    'expressions': 'simplifying_linear_expressions',
    'equations': 'solutions_and_equivalent_equations',
    'inequalities': 'inequality_notation_and_solution_sets',
    'coordinates': 'computing_slope_from_graphs_tables_and_points',
    'linear_functions': 'slope_intercept_form',
    'systems': 'systems_as_simultaneous_constraints',
    'exponents': 'product_and_quotient_rules_for_exponents',
    'factoring': 'factoring_trinomials_with_leading_coefficient_one',
    'quadratics': 'quadratic_expressions_and_their_graphs',
    'probability': 'theoretical_probability',
    'descriptive_stats': 'measures_of_centre_mean_median_and_mode',
    'data_interpretation': 'making_and_critiquing_data_based_claims',
    'variables_and_algebraic_notation': 'variables_and_algebraic_notation',
    'combining_like_terms': 'combining_like_terms',
    'the_distributive_property': 'the_distributive_property',
    'one_step_equations': 'one_step_equations',
    'two_step_equations': 'two_step_equations',
    'equations_with_variables_on_both_sides': 'equations_with_variables_on_both_sides',
    'solving_proportions': 'solving_proportions',
    'percent_change': 'percent_change',
    'direct_variation': 'direct_variation',
    'point_slope_form': 'point_slope_form',
    'standard_form_and_intercepts': 'standard_form_and_intercepts',
    'solving_systems_by_substitution': 'solving_systems_by_substitution',
    'solving_systems_by_elimination': 'solving_systems_by_elimination',
    'parallel_and_perpendicular_lines': 'parallel_and_perpendicular_lines',
    'the_pythagorean_theorem': 'the_pythagorean_theorem',
}


def _load_course_graph() -> KnowledgeGraph:
    """Merge every declared course pack. Missing packs are skipped, not fatal."""
    graph = KnowledgeGraph()
    for name in COURSE_PACKS:
        path = PACK_DIR / f'{name}.json'
        if not path.exists():
            continue
        pack_graph, _ = load_pack(path)
        graph.merge(pack_graph, replace=True)
    return graph


KNOWLEDGE_GRAPH = _load_course_graph()
TAXONOMY: Taxonomy = KNOWLEDGE_GRAPH.taxonomy

# Attach the lesson layer to the graph, in both directions.
for _lesson_id, _node_id in LESSON_TARGETS.items():
    _node = KNOWLEDGE_GRAPH.nodes.get(_node_id)
    if _node is not None:
        _node.has_lesson = True
        _node.lesson_id = _lesson_id

# Give each authored lesson its classification from the graph, so both layers agree.
for _cid, _concept in CONCEPTS.items():
    _target = LESSON_TARGETS.get(_cid, '')
    _node = KNOWLEDGE_GRAPH.nodes.get(_target) if _target else None
    _concept['strand'] = _node.strand if _node else 'Algebra'
    _concept['topic'] = _node.topic if _node else ''
    _concept['tier'] = _node.tier if _node else 'core'
    _concept['difficulty'] = _node.difficulty if _node else 3
    _concept['graph_id'] = _target
    _concept['has_lesson'] = True

#: Course node id -> authored lesson id, the reverse of LESSON_TARGETS.
GRAPH_TO_LESSON = {node: lesson for lesson, node in LESSON_TARGETS.items()
                   if node in KNOWLEDGE_GRAPH.nodes}


def graph_states_in(states: dict, graph: KnowledgeGraph) -> dict:
    """Project learner states onto the node ids of one course graph.

    Attempts are recorded against the id the question carried: an authored lesson id for
    the mathematics course, a graph node id for a generated course. Resolving both and
    dropping anything outside the given graph means a physics view can never be populated
    by algebra evidence - the failure would otherwise be invisible, because the ids simply
    would not match and every concept would read as unstarted.
    """
    projected: dict = {}
    for concept_id, state in states.items():
        node_id = LESSON_TARGETS.get(concept_id, concept_id)
        if node_id in graph.nodes:
            projected[node_id] = state
    return projected


def graph_states(states: dict) -> dict:
    """Project learner states onto the mathematics course graph. See ``graph_states_in``."""
    return graph_states_in(states, KNOWLEDGE_GRAPH)


GRAPH_STATS = KNOWLEDGE_GRAPH.stats()

#: Course node id -> generated figure kind. Derived from each node's own
#: classification, so this is a property of the graph rather than a second list that
#: could drift out of step with it. Only the *kind* is precomputed; the payload is
#: built on demand so parameter overrides stay cheap.
SIMULATION_KINDS: dict[str, str] = {
    node.id: template_for(node.to_dict()).kind for node in KNOWLEDGE_GRAPH.nodes.values()
}


def simulation_node(concept_id: str) -> dict | None:
    """Resolve a graph concept id *or* an authored lesson id to a graph node.

    Lessons and graph nodes are different namespaces: ``fractions`` is a lesson while
    ``fraction_equivalence`` is a node. Accepting both means a client can ask for a
    figure using whichever id it already holds.
    """
    if concept_id in KNOWLEDGE_GRAPH.nodes:
        return KNOWLEDGE_GRAPH.nodes[concept_id].to_dict()
    target = LESSON_TARGETS.get(concept_id)
    if target and target in KNOWLEDGE_GRAPH.nodes:
        return KNOWLEDGE_GRAPH.nodes[target].to_dict()
    return None


def graph_summary() -> dict:
    """The knowledge graph plus the lesson-layer join, for the API and the client."""
    payload = KNOWLEDGE_GRAPH.to_payload()
    for node in payload['nodes']:
        node['simulation_kind'] = SIMULATION_KINDS.get(node['id'], '')
    payload['lesson_targets'] = dict(LESSON_TARGETS)
    payload['packs'] = [{'name': name, 'path': str((PACK_DIR / f'{name}.json'))}
                        for name in COURSE_PACKS if (PACK_DIR / f'{name}.json').exists()]
    payload['sources'] = SOURCES
    return payload


def validate_graph() -> bool:
    """Raise if the merged graph is structurally unsound."""
    KNOWLEDGE_GRAPH.raise_if_invalid()
    return True


# ---------------------------------------------------------------------------
# Generated lesson layer for courses that ship without authored content.
#
# The registries above are the authored mathematics course. Every other course is
# materialised into the *same* two dictionaries so that receipts, grading,
# diagnosis, memory, spaced review and projects need no special case at all - a
# generated concept is simply another entry. ``CONCEPT_COURSE`` records which
# course each entry belongs to, which is what lets the API scope a learner's view
# without splitting the registries apart.
#
# The import is deliberately late: ``generated_curriculum`` needs the course
# registry, which needs the graph, so importing it at module top would be a cycle.
# ---------------------------------------------------------------------------

from . import generated_curriculum as _generated  # noqa: E402

#: Concept id -> course id. Authored concepts belong to the mathematics course.
CONCEPT_COURSE: dict[str, str] = {cid: 'integrated_math_1' for cid in CONCEPTS}

#: What the generated layer added, per course. Reported by the health endpoint so
#: the split between authored and derived content is never a matter of opinion.
GENERATED_SUMMARY: dict = _generated.register(CONCEPTS, QUESTIONS)

for _cid, _entry in CONCEPTS.items():
    CONCEPT_COURSE.setdefault(_cid, _entry.get('course_id', ''))


def course_concepts(course_id: str) -> dict:
    """Authored and generated concepts for one course."""
    return {cid: entry for cid, entry in CONCEPTS.items()
            if CONCEPT_COURSE.get(cid) == course_id}


def course_questions(course_id: str) -> dict:
    """Every question that belongs to one course."""
    return {qid: q for qid, q in QUESTIONS.items()
            if CONCEPT_COURSE.get(q.get('concept_id', '')) == course_id}


def authored_share(course_id: str) -> dict:
    """How much of a course is hand-written rather than derived.

    A course that is entirely generated is still a real course, but a learner and a
    reviewer are both entitled to know which it is.

    Three numbers, because two were not enough. ``authored`` means a person wrote it.
    ``generated`` means the structural layer derived it. ``written`` means the concept has
    a lesson with depth in it - a worked example, a named misconception - whoever wrote the
    prose. The third number exists because an authored-by-the-harness overlay leaves the
    first two unchanged: the prose is still model output (so ``generated`` stays true and
    ``authored`` stays false), while the thing a learner actually experiences changes
    completely. Reporting only ``authored`` would make that work invisible; reporting it as
    ``authored`` would be a lie about who checked it.

    ``written`` is then split by who is answerable for it, because "has a lesson" and
    "someone has read that lesson" are different claims and only the first one is free:

    * ``reviewed_concepts`` - depth that lives in the shipped pack, in the source tree,
      where it went through review like any other code change.
    * ``model_drafted_concepts`` - depth the harness composed. It is real teaching material
      and it has passed a mechanical audit that checks every answer against the lesson it
      claims to come from. Nobody has read it. A count that merged the two would let the
      first claim cover for the second, which is the exact failure the audit exists to
      prevent.
    """
    concepts = course_concepts(course_id)
    questions = course_questions(course_id)
    generated_concepts = sum(1 for entry in concepts.values() if entry.get('generated'))
    generated_questions = sum(1 for q in questions.values() if q.get('generated'))
    with_depth = [entry for entry in concepts.values()
                  if any(str(block.get('kind')) == 'worked_example'
                         for block in entry.get('blocks') or ())]
    written = len(with_depth)
    reviewed = sum(1 for entry in with_depth if not entry.get('generated'))
    overlaid = sum(1 for entry in concepts.values() if entry.get('overlay'))
    return {'concepts': len(concepts), 'questions': len(questions),
            'authored_concepts': len(concepts) - generated_concepts,
            'authored_questions': len(questions) - generated_questions,
            'generated_concepts': generated_concepts,
            'generated_questions': generated_questions,
            'written_concepts': written,
            'reviewed_concepts': reviewed,
            'model_drafted_concepts': written - reviewed,
            'overlay_concepts': overlaid}
