"""Linear Algebra outline, in the shape ``scripts/course_pipeline.py`` expects.

A one-semester linear algebra course written for this project: vectors and linear
combinations, linear systems and elimination, matrix algebra and inverses, vector spaces
and basis, the four fundamental subspaces and rank, linear transformations, orthogonality
and projection, least squares and QR, determinants, eigenvalues and diagonalisation,
symmetric matrices and the spectral theorem, and the singular value decomposition. Unit,
topic and concept order follows the course plan; every summary below is an original
statement written here, not textbook text, and each names the condition under which its
claim holds.

Textbook position. OpenStax publishes no linear algebra textbook -- its catalogue of 129
books was checked on 2026-11-10. Algebra and Trigonometry and College Algebra are not
substitutes: they stop at matrix arithmetic and 2x2 systems and never define a vector
space, state rank-nullity or reach the SVD, so anchoring to them would be a fabricated
citation for most of this course. ``TEXTBOOK`` therefore declares
``no_cc_by_anchor = True`` with the reason, every unit carries an empty ``sections``
list, and ``course_pipeline.py verify`` reports the anchoring check as SKIP with that
reason rather than a green tick it has not earned.

The pack is generated: ``linear_algebra.json`` is rebuilt by the pipeline from this
module and must never be hand-edited.
"""

from __future__ import annotations

ID = 'linear_algebra'
TITLE = 'Linear Algebra'
SUBJECT = 'Mathematics'
SUBJECT_KIND = 'mathematics'
EXPECTED_WEEKS = 30
COURSE_LINE = 'Linear Algebra - Vectors, Spaces and the SVD'
DESCRIPTION = (
    'A one-semester linear algebra course: vectors, linear combinations and span; linear '
    'systems and Gaussian elimination; matrix algebra and inverses; vector spaces, '
    'independence and basis; the four fundamental subspaces and rank-nullity; linear '
    'transformations and change of basis; orthogonality, projection and Gram-Schmidt; '
    'least squares and QR; determinants; eigenvalues, diagonalisation and Markov chains; '
    'symmetric matrices and the spectral theorem; and the singular value decomposition '
    'with low-rank approximation.')

TEXTBOOK = {
    'spine': '', 'supplements': [], 'link_only_note': '',
    'no_cc_by_anchor': True,
    'reason': ('OpenStax publishes no linear algebra textbook (catalogue checked 2026-11-10). '
               'The outline is an original CC0 scope and sequence and is not anchored to a '
               'textbook, so no section is quoted for this course.'),
}

UNITS = [
    # ------------------------------------------------------------------ 1
    {
        'unit': 'Vectors and Linear Combinations',
        'about': ('The entry unit: what a vector is in R^n, how the two vector operations '
                  'build every linear combination, and how length and angle come out of the '
                  'dot product.'),
        'sections': [],
        'topics': [
            ('Vectors and Vector Operations', [
                ('Vectors as Ordered n-Tuples',
                 'A vector in R^n is an ordered list of n real numbers, and two vectors are '
                 'added componentwise while a scalar multiplies every component, so R^n is '
                 'closed under both operations.',
                 ['vector', 'component', 'r^n']),
                ('Vector Addition and Scalar Multiplication',
                 'Vector addition in R^n is commutative and associative with a zero vector '
                 'and an additive inverse, and scalar multiplication distributes over both, '
                 'so R^n satisfies the vector-space axioms before any abstraction.',
                 ['vector addition', 'scalar multiplication', 'axioms']),
                ('Vectors as Arrows in R2 and R3',
                 'In R^2 and R^3 a vector is drawn as an arrow from the origin, addition is '
                 'the diagonal of the parallelogram its two arrows span, and a negative '
                 'scalar reverses the arrow rather than only stretching it.',
                 ['geometric vector', 'parallelogram', 'direction']),
            ]),
            ('Linear Combinations and Span', [
                ('Linear Combinations of Vectors',
                 'A linear combination of v1 to vk is c1v1 + ... + ckvk with real scalars, '
                 'and it is defined only when all the vectors lie in the same R^n so the sum '
                 'is taken componentwise.',
                 ['linear combination', 'weights', 'coefficients']),
                ('The Span of a Set of Vectors',
                 'The span of a set is the set of all its linear combinations, so it always '
                 'contains the zero vector and is closed under addition and scalar '
                 'multiplication, which makes it a subspace even when the set is not.',
                 ['span', 'subspace', 'closure']),
                ('When a Set Spans R^n',
                 'A set of vectors spans R^n exactly when the matrix with those vectors as '
                 'columns has a pivot in every row, so more than n vectors can still fail to '
                 'span while fewer than n never span.',
                 ['spanning set', 'pivot', 'row count']),
            ]),
            ('Dot Product, Length, and Angle', [
                ('The Dot Product',
                 'The dot product u.v is the sum of the products of corresponding components, '
                 'it is symmetric and bilinear, and it is zero exactly when the two nonzero '
                 'vectors are perpendicular.',
                 ['dot product', 'inner product', 'perpendicular']),
                ('Length, Distance, and Unit Vectors',
                 'The length of v is the square root of v.v, which is zero only for the zero '
                 'vector, and scaling by c multiplies length by the absolute value of c, so a '
                 'unit vector is a nonzero vector divided by its own length.',
                 ['length', 'unit vector', 'distance']),
                ('Angles and the Cauchy-Schwarz Inequality',
                 'The Cauchy-Schwarz inequality gives |u.v| at most the product of the two '
                 'lengths, so for nonzero vectors cos(theta) = u.v/(|u||v|) is defined and '
                 'lies between -1 and 1, which makes the angle well defined.',
                 ['cauchy-schwarz', 'angle', 'cosine formula']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 2
    {
        'unit': 'Linear Systems and Elimination',
        'about': ('Solving Ax = b: the geometry of intersecting hyperplanes, the row '
                  'operations of Gaussian elimination, the staircase of echelon form, and '
                  'the particular-plus-null-space description of the full solution.'),
        'sections': [],
        'topics': [
            ('Geometry of Linear Systems', [
                ('Each Equation as a Hyperplane',
                 'One linear equation in n unknowns is the solution set of a single row, a '
                 'hyperplane of dimension n - 1, so a system of m equations asks for the '
                 'common intersection of m such hyperplanes in R^n.',
                 ['hyperplane', 'intersection', 'geometry']),
                ('The Three Solution Cases',
                 'A linear system has no solution, exactly one solution, or infinitely many, '
                 'because once two distinct solutions exist the whole line through them '
                 'consists of solutions, so a system can never have exactly two.',
                 ['solution set', 'consistency', 'infinitely many']),
                ('Homogeneous Systems and the Trivial Solution',
                 'A homogeneous system Ax = 0 always has the trivial solution x = 0, so it is '
                 'consistent for every matrix and is either uniquely trivial or has '
                 'infinitely many solutions.',
                 ['homogeneous system', 'trivial solution', 'null space']),
            ]),
            ('Gaussian Elimination', [
                ('Augmented Matrices and Row Equivalence',
                 'The augmented matrix records the coefficients and the right-hand side '
                 'together, and two augmented matrices that are row equivalent have exactly '
                 'the same solution set, so elimination can be performed on the matrix alone.',
                 ['augmented matrix', 'row equivalence', 'system']),
                ('Elementary Row Operations',
                 'Swapping two rows, adding a multiple of one row to another, and multiplying '
                 'a row by a nonzero scalar each preserve the solution set, which is why the '
                 'reduced system answers the original question.',
                 ['row operation', 'row swap', 'solution preserving']),
                ('Pivots and the Elimination Procedure',
                 'Elimination takes the leftmost nonzero entry of the working row as pivot, '
                 'clears every entry below it, and repeats on the submatrix, so it terminates '
                 'in echelon form from which back substitution gives x.',
                 ['pivot', 'forward elimination', 'back substitution']),
            ]),
            ('Reduced Row Echelon Form', [
                ('Echelon Form and the Staircase',
                 'A matrix is in echelon form when every nonzero row sits above the zero rows, '
                 'each pivot lies to the right of the pivot above it, and all entries below a '
                 'pivot are zero, so the pivots are found by scanning left to right.',
                 ['echelon form', 'pivot position', 'staircase']),
                ('Reduced Row Echelon Form and Pivot Columns',
                 'Reduced echelon form further makes each pivot 1 and clears the entries above '
                 'it, and that form is unique for a given matrix, so two matrices are row '
                 'equivalent exactly when they reduce to the same matrix.',
                 ['reduced row echelon', 'uniqueness', 'pivot column']),
                ('Free Variables and Parametric Solutions',
                 'In reduced form every non-pivot column carries a free variable, so a '
                 'consistent system with f free variables has a solution set described by f '
                 'independent parameters and is a translate of an f-dimensional subspace.',
                 ['free variable', 'parametric solution', 'degrees of freedom']),
            ]),
            ('Complete Solution of Ax=b', [
                ('Particular Solution plus Null Space',
                 'When Ax = b is consistent, its complete solution is x = xp + xn where xp is '
                 'one particular solution and xn ranges over the null space of A, because '
                 'differences of two solutions to Ax = b both solve Ax = 0.',
                 ['particular solution', 'null space', 'general solution']),
                ('Consistency and a Pivot in the Last Column',
                 'The system Ax = b is consistent exactly when row reduction of the augmented '
                 'matrix leaves no pivot in the last column, since such a pivot is the row '
                 '0 = c with c nonzero.',
                 ['consistency', 'augmented column', 'inconsistent system']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 3
    {
        'unit': 'Matrix Algebra and Inverses',
        'about': ('Matrices as objects in their own right: the operations and their '
                  'dimension rules, transpose and special forms, the inverse and when it '
                  'exists, and elimination written as A = LU.'),
        'sections': [],
        'topics': [
            ('Matrix Operations', [
                ('Matrix Addition and Scalar Multiplication',
                 'Two matrices can be added only when they have the same shape, entry by '
                 'entry, and a scalar multiplies every entry, so the m by n matrices form a '
                 'vector space of dimension mn under those two operations.',
                 ['matrix addition', 'scalar multiple', 'shape']),
                ('The Matrix Product and Its Dimensions',
                 'The product AB is defined only when the column count of A equals the row '
                 'count of B, its ij entry is the dot product of row i of A with column j of '
                 'B, and the product is generally not commutative.',
                 ['matrix product', 'dimension rule', 'noncommutative']),
                ('Matrix Multiplication as Composition',
                 'An m by n matrix A applied to an n by p matrix B represents B followed by A, '
                 'which is why (AB)x = A(Bx) and why the product is associative while most '
                 'matrices have no multiplicative inverse.',
                 ['composition', 'associativity', 'linear map']),
            ]),
            ('Transpose and Special Matrices', [
                ('The Transpose and Its Rules',
                 'The transpose swaps rows and columns, so the transpose of a transpose returns '
                 'the original and the transpose of a product reverses the order, giving '
                 '(AB)^T = B^T A^T.',
                 ['transpose', 'reversal rule', 'dimensions']),
                ('Symmetric, Diagonal, and Triangular Matrices',
                 'A matrix is symmetric when it equals its transpose, diagonal when only its '
                 'diagonal entries may be nonzero, and triangular when one whole side of the '
                 'diagonal vanishes, and each class is closed under addition but not in '
                 'general under multiplication.',
                 ['symmetric matrix', 'diagonal matrix', 'triangular matrix']),
            ]),
            ('Matrix Inverses', [
                ('Invertibility and the Two-Sided Inverse',
                 'An n by n matrix A is invertible when some B satisfies AB = BA = I, and then '
                 'B is unique and written A inverse, which requires A to be square before the '
                 'question can even be asked.',
                 ['inverse matrix', 'identity', 'square matrix']),
                ('Inverses of Products and Transposes',
                 'When both factors are invertible, (AB)^-1 = B^-1 A^-1 and the inverse of a '
                 'transpose is the transpose of the inverse, because undoing a composition '
                 'undoes the last step first.',
                 ['inverse product', 'transpose inverse', 'order reversal']),
                ('Solving Ax=b with an Inverse',
                 'If A is invertible then Ax = b has the unique solution x = A^-1 b for every '
                 'b, so invertibility is exactly the condition that the system is never '
                 'inconsistent and never has a free variable.',
                 ['solve by inverse', 'unique solution', 'invertible criterion']),
            ]),
            ('Elimination Matrices and A=LU', [
                ('Elementary Matrices and Row Operations',
                 'Every elementary row operation is left multiplication by an elementary '
                 'matrix obtained from the identity, and each such matrix is invertible with '
                 'an elementary inverse, so elimination is a product of matrices.',
                 ['elementary matrix', 'row operation', 'left multiplication']),
                ('The LU Factorization',
                 'When elimination needs only row replacements, A factors as A = LU with L '
                 'unit lower triangular holding the multipliers and U the echelon form, while '
                 'any row swap is absorbed by a permutation so that PA = LU.',
                 ['lu factorization', 'multiplier', 'partial pivoting']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 4
    {
        'unit': 'Vector Spaces, Independence, and Basis',
        'about': ('The abstractions the rest of the course runs on: subspaces, linear '
                  'independence, bases and coordinates, and the same definitions carried into '
                  'abstract vector spaces.'),
        'sections': [],
        'topics': [
            ('Subspaces of Rn', [
                ('The Subspace Test',
                 'A subset of R^n is a subspace exactly when it contains the zero vector and '
                 'is closed under addition and scalar multiplication, so a plane through the '
                 'origin qualifies while the same plane shifted off the origin does not.',
                 ['subspace test', 'closure', 'zero vector']),
                ('Spans and Null Spaces as Subspaces',
                 'The span of any set of vectors is a subspace, and the solution set of '
                 'Ax = 0 is the span of the vectors attached to its free variables, whereas '
                 'the solution set of Ax = b with b nonzero is not a subspace.',
                 ['span', 'null space', 'non-example']),
            ]),
            ('Linear Independence', [
                ('Independence as a Trivial Combination',
                 'The vectors v1 to vk are linearly independent when c1v1 + ... + ckvk = 0 '
                 'forces every coefficient to be zero, so a set is dependent exactly when one '
                 'of its members is a combination of the others.',
                 ['linear independence', 'trivial combination', 'dependence']),
                ('Pivots and Linear Independence',
                 'The columns of a matrix are linearly independent exactly when every column '
                 'is a pivot column, which is impossible when the matrix has more columns than '
                 'rows, so such a set is always dependent.',
                 ['pivot column', 'column independence', 'wide matrix']),
                ('Dependence and Redundant Vectors',
                 'In a dependent set some vector is a combination of the vectors before it, so '
                 'deleting it leaves the span unchanged, which is why a basis may contain no '
                 'redundant vector.',
                 ['redundancy', 'span preservation', 'deletion']),
            ]),
            ('Basis, Dimension, and Coordinates', [
                ('The Basis Definition',
                 'A basis of a subspace is a set that both spans the subspace and is linearly '
                 'independent, so every vector of the subspace is a combination of the basis '
                 'vectors in exactly one way.',
                 ['basis', 'spanning and independent', 'uniqueness']),
                ('Dimension and the Size of a Basis',
                 'Any two bases of the same subspace have the same number of vectors, which is '
                 'its dimension, so n + 1 vectors in R^n are always dependent and fewer than n '
                 'never span it.',
                 ['dimension', 'basis size', 'invariance']),
                ('Coordinates Relative to a Basis',
                 'Once a basis B is fixed, the coordinates of x relative to B are the unique '
                 'weights that express x in that basis, and they change when the basis changes '
                 'even though x itself does not.',
                 ['coordinate vector', 'ordered basis', 'representation']),
            ]),
            ('General Vector Spaces (Extension)', [
                ('The Vector Space Axioms',
                 'A vector space is a set with an addition and a scalar multiplication '
                 'satisfying the ten axioms, so polynomials of bounded degree, matrices and '
                 'functions are vector spaces whose elements are not arrows.',
                 ['vector space', 'axioms', 'abstract space']),
                ('Bases and Dimension in Abstract Spaces',
                 'The subspace test, the basis definition and the dimension theorem use the '
                 'same words in any vector space, so the polynomials of degree at most n have '
                 'dimension n + 1 with basis 1, x, ..., x^n.',
                 ['polynomial space', 'abstract basis', 'dimension']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 5
    {
        'unit': 'The Four Fundamental Subspaces and Rank',
        'about': ('The four subspaces attached to every matrix, their dimensions, and '
                  'rank-nullity as the one equation that ties the row and column counts '
                  'together.'),
        'sections': [],
        'topics': [
            ('Column Space and Null Space', [
                ('The Column Space of a Matrix',
                 'The column space of an m by n matrix A is the span of its columns, so it '
                 'equals the set of b for which Ax = b is consistent and it is a subspace of '
                 'R^m.',
                 ['column space', 'consistency', 'image']),
                ('The Null Space of a Matrix',
                 'The null space of A is the set of solutions of Ax = 0, a subspace of R^n '
                 'whose dimension is the number of free variables left by row reduction, so '
                 'it is nontrivial exactly when some column is not a pivot column.',
                 ['null space', 'free variable', 'kernel']),
            ]),
            ('Row Space and Left Null Space', [
                ('The Row Space and the Rank',
                 'The row space of A is the span of its rows, row operations leave it '
                 'unchanged, and its dimension is the number of pivots, which is by definition '
                 'the rank of A.',
                 ['row space', 'rank', 'pivot count']),
                ('The Left Null Space',
                 'The left null space of A consists of the vectors y with y^T A = 0, and it is '
                 'the orthogonal complement of the column space inside R^m, of dimension m - r '
                 'when A has rank r.',
                 ['left null space', 'orthogonal complement', 'm minus r']),
            ]),
            ('Rank and the Big Picture', [
                ('Rank-Nullity',
                 'Rank-nullity gives dim(column space) + dim(null space) = n for an m by n '
                 'matrix, so a matrix with more columns than rows must have a nontrivial null '
                 'space.',
                 ['rank-nullity', 'dimension theorem', 'wide matrix']),
                ('Rank Bounds and Their Consequences',
                 'The rank of an m by n matrix satisfies r at most the smaller of m and n, and '
                 'an n by n matrix is invertible exactly when r = n, so full rank is both '
                 'necessary and sufficient for invertibility.',
                 ['rank bound', 'full rank', 'invertibility']),
                ('The Four Subspaces in One Picture',
                 'For an m by n matrix of rank r, the column space and left null space sit '
                 'inside R^m with dimensions r and m - r, while the null space and row space '
                 'sit inside R^n with dimensions n - r and r.',
                 ['four subspaces', 'dimension bookkeeping', 'ambient space']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 6
    {
        'unit': 'Linear Transformations',
        'about': ('Linear maps and their matrices: what linearity forbids, how rotations, '
                  'reflections and scalings look, kernel and image as the measures of '
                  'injectivity and surjectivity, and what changes when the basis changes.'),
        'sections': [],
        'topics': [
            ('Linear Transformations and Their Matrices', [
                ('The Linearity Conditions',
                 'A map T from R^n to R^m is linear when it preserves sums and scalar '
                 'multiples, equivalently when T(0) = 0 and T sends every linear combination '
                 'to the matching combination of images, so a translation by a nonzero vector '
                 'is never linear.',
                 ['linearity', 'preserves combinations', 'translation']),
                ('The Standard Matrix of a Transformation',
                 'Every linear T from R^n to R^m equals multiplication by the unique matrix '
                 'whose j-th column is T(ej), so once standard bases are fixed a linear map '
                 'and a matrix are the same object.',
                 ['standard matrix', 'standard basis', 'matrix representation']),
            ]),
            ('Geometry of Transformations', [
                ('Rotations, Reflections, and Scalings',
                 'A rotation about the origin has an orthogonal matrix with determinant 1, a '
                 'reflection has determinant -1, and a scaling multiplies lengths by its '
                 'factor, so each family is read off its matrix.',
                 ['rotation', 'reflection', 'scaling']),
                ('Determinants as a Geometric Classifier',
                 'The determinant of a linear map scales signed area or volume by that factor, '
                 'so a zero determinant collapses the image to lower dimension while a negative '
                 'one reverses orientation.',
                 ['determinant', 'signed volume', 'orientation']),
            ]),
            ('Kernel and Image', [
                ('Kernel and Image as Subspaces',
                 'The kernel of T is the set of inputs sent to zero and the image is the set of '
                 'outputs actually attained, and both are subspaces, of the domain and the '
                 'codomain respectively.',
                 ['kernel', 'image', 'subspace']),
                ('One-to-One and Onto in Matrix Terms',
                 'A linear map is one-to-one exactly when its kernel is the zero subspace and '
                 'onto exactly when its image is the whole codomain, which for T(x) = Ax means '
                 'a pivot in every column and a pivot in every row respectively.',
                 ['injective', 'surjective', 'pivot criterion']),
                ('Rank-Nullity for Transformations',
                 'For a linear map on a finite-dimensional domain, the dimension of the domain '
                 'equals dim(kernel) + dim(image), so no linear map from R^3 to R^2 can be '
                 'one-to-one.',
                 ['rank-nullity', 'dimension count', 'impossible map']),
            ]),
            ('Change of Basis', [
                ('The Change-of-Basis Matrix',
                 'The change-of-basis matrix from B to C has the C-coordinates of the B basis '
                 'vectors as its columns, and multiplying it by B-coordinates returns the '
                 'C-coordinates of the same vector.',
                 ['change of basis', 'coordinate conversion', 'transition matrix']),
                ('Similar Matrices Represent One Map',
                 'Two matrices represent the same linear map in different bases exactly when '
                 'they are similar, B = P^-1 A P for some invertible P, so similar matrices '
                 'share determinant, trace, rank and eigenvalues.',
                 ['similar matrices', 'invariant', 'conjugation']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 7
    {
        'unit': 'Orthogonality and Projection',
        'about': ('Orthogonality as a computational tool: orthogonal and orthonormal sets, '
                  'orthogonal complements, and the projection of a vector onto a subspace.'),
        'sections': [],
        'topics': [
            ('Orthogonal and Orthonormal Sets', [
                ('Orthogonal Sets and Independence',
                 'A set of nonzero vectors that are pairwise orthogonal is linearly '
                 'independent, because dotting a zero combination with one member isolates that '
                 'member as the only surviving term.',
                 ['orthogonal set', 'independence', 'dot product']),
                ('Orthonormal Bases and Their Coordinates',
                 'An orthonormal basis consists of mutually orthogonal unit vectors, and then '
                 'the coordinates of any vector are simply its dot products with the basis '
                 'vectors, so no linear system has to be solved.',
                 ['orthonormal basis', 'coordinates', 'unit vectors']),
            ]),
            ('Orthogonal Complements', [
                ('The Orthogonal Complement',
                 'The orthogonal complement of a subspace W is the set of vectors orthogonal to '
                 'every vector of W, which is itself a subspace and satisfies '
                 'dim W + dim W complement = n inside R^n.',
                 ['orthogonal complement', 'dimension', 'perpendicular']),
                ('Unique Decomposition into Complements',
                 'Every vector of R^n splits in exactly one way as a part in W plus a part in '
                 'its orthogonal complement, and taking the complement twice returns W, so a '
                 'subspace and its complement determine each other.',
                 ['direct sum', 'unique decomposition', 'involution']),
                ('The Four Subspaces as Complement Pairs',
                 'For any matrix A the null space of A is the orthogonal complement of the row '
                 'space and the left null space is the orthogonal complement of the column '
                 'space, which is what forces the dimension pairs r and n - r.',
                 ['fundamental subspaces', 'complement pair', 'dimension count']),
            ]),
            ('Projection onto Subspaces', [
                ('The Projection Formula',
                 'For a subspace W with orthonormal basis u1 to uk, the projection of x onto W '
                 'is the sum of (x.ui)ui, and the residual x minus that projection is '
                 'orthogonal to every vector of W.',
                 ['projection', 'orthonormal basis', 'residual']),
                ('Projection Matrices',
                 'Projection onto the column space of a matrix A with independent columns is '
                 'multiplication by P = A(A^T A)^-1 A^T, and such a P satisfies P^2 = P and '
                 'P^T = P.',
                 ['projection matrix', 'idempotent', 'symmetric']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 8
    {
        'unit': 'Least Squares, Gram-Schmidt, and QR',
        'about': ('Approximation when no exact solution exists: the normal equations, '
                  'least-squares fitting of data, and Gram-Schmidt with its QR '
                  'factorisation.'),
        'sections': [],
        'topics': [
            ('Normal Equations and Least Squares', [
                ('The Least-Squares Problem',
                 'When Ax = b has no solution, a least-squares solution minimises the length '
                 'of Ax - b, which is the same as projecting b onto the column space of A.',
                 ['least squares', 'residual norm', 'inconsistent system']),
                ('When the Normal Equations Are Unique',
                 'Least-squares solutions are exactly the solutions of the normal equations '
                 'A^T A x = A^T b, which are always consistent, and the solution is unique '
                 'exactly when the columns of A are linearly independent.',
                 ['normal equations', 'uniqueness', 'independent columns']),
            ]),
            ('Least-Squares Fitting (Application)', [
                ('Fitting a Line by Least Squares',
                 'A straight-line fit to data points (ti, bi) is the least-squares problem for '
                 'the design matrix with columns of ones and ti, so the intercept and slope '
                 'solve a 2 by 2 normal system.',
                 ['line fit', 'design matrix', 'regression']),
                ('Residuals and the Projection View',
                 'The least-squares residual b - Ax is orthogonal to every column of A, so the '
                 'fitted values are the projection of b onto the column space and the residual '
                 'carries only what that space cannot represent.',
                 ['residual', 'orthogonality', 'fitted values']),
            ]),
            ('Gram-Schmidt and QR', [
                ('The Gram-Schmidt Process',
                 'Gram-Schmidt replaces each vector by its residual after subtracting its '
                 'projections onto the previous orthonormal vectors, so the span of the first k '
                 'vectors is unchanged at every step.',
                 ['gram-schmidt', 'orthonormalization', 'span preservation']),
                ('The QR Factorization',
                 'When A has linearly independent columns, Gram-Schmidt gives A = QR with Q of '
                 'orthonormal columns and R upper triangular with positive diagonal, so '
                 'Ax = b becomes the triangular system Rx = Q^T b.',
                 ['qr factorization', 'triangular system', 'orthonormal columns']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 9
    {
        'unit': 'Determinants',
        'about': ('The determinant as one number that reports invertibility, volume and '
                  'eigenvalue information, computed either by expansion or by elimination.'),
        'sections': [],
        'topics': [
            ('Computing Determinants', [
                ('Cofactor Expansion',
                 'The determinant expands along any row or column as a signed sum of entries '
                 'times their minors, with the signs following the checkerboard pattern, so '
                 'expanding along the row or column with the most zeros is cheapest.',
                 ['cofactor expansion', 'minor', 'sign pattern']),
                ('Triangular Matrices and Elimination',
                 'The determinant of a triangular matrix is the product of its diagonal '
                 'entries, and during elimination a row replacement leaves the determinant '
                 'unchanged while a swap multiplies it by -1 and a row scaling multiplies it '
                 'by the same factor.',
                 ['triangular determinant', 'row replacement', 'elimination']),
            ]),
            ('Properties of Determinants', [
                ('The Product Rule for Determinants',
                 'For square matrices of the same size the determinant is multiplicative, '
                 'det(AB) = det(A)det(B), so an invertible A has det(A^-1) = 1/det(A) and '
                 'det(A^k) = det(A)^k.',
                 ['multiplicativity', 'determinant of inverse', 'product rule']),
                ('Singularity and the Determinant',
                 'A square matrix is invertible exactly when its determinant is nonzero, '
                 'because elimination produces a zero pivot exactly when the determinant '
                 'vanishes, and a matrix and its transpose share one determinant.',
                 ['singular matrix', 'zero determinant', 'transpose']),
            ]),
            ('Geometry and Applications of Determinants', [
                ('Determinants as Volume',
                 'The absolute value of the determinant of a square matrix is the volume of '
                 'the parallelepiped its columns span, so a zero determinant means the columns '
                 'are dependent and that volume has collapsed.',
                 ['volume', 'parallelepiped', 'linear dependence']),
                ('Cramer\'s Rule and the Adjugate',
                 'Cramer\'s rule writes each component of the solution of Ax = b as a ratio of '
                 'determinants, and the adjugate formula A^-1 = adj(A)/det(A) restates the same '
                 'fact, both requiring det(A) nonzero.',
                 ['cramer rule', 'adjugate', 'inverse formula']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 10
    {
        'unit': 'Eigenvalues, Eigenvectors, and Diagonalization',
        'about': ('Invariant directions: eigenvalues and eigenvectors, the criterion for '
                  'diagonalisation, complex eigenvalues as rotation with scaling, and Markov '
                  'chains as the application.'),
        'sections': [],
        'topics': [
            ('Eigenvalues and Eigenvectors', [
                ('The Eigenvalue Equation',
                 'A nonzero v is an eigenvector of A with eigenvalue lambda when Av = lambda v, '
                 'and lambda is an eigenvalue exactly when A - lambda I is singular, so the '
                 'eigenvalues are the roots of the characteristic polynomial.',
                 ['eigenvalue', 'eigenvector', 'characteristic polynomial']),
                ('Eigenspaces and Multiplicity',
                 'The eigenvectors for a fixed eigenvalue together with the zero vector form '
                 'the eigenspace, the null space of A - lambda I, so its dimension is the '
                 'geometric multiplicity and never exceeds the algebraic multiplicity of the '
                 'root.',
                 ['eigenspace', 'geometric multiplicity', 'algebraic multiplicity']),
                ('Eigenvalues from Trace and Determinant',
                 'For a 2 by 2 matrix the two eigenvalues sum to the trace and multiply to the '
                 'determinant, which often recovers them from one quadratic without expanding '
                 'the characteristic polynomial in full.',
                 ['trace', 'determinant', 'two by two']),
            ]),
            ('Diagonalization', [
                ('The Diagonalization Criterion',
                 'An n by n matrix is diagonalisable exactly when it has n linearly independent '
                 'eigenvectors, and then A = PDP^-1 with D the diagonal matrix of eigenvalues '
                 'and P the matrix of eigenvectors.',
                 ['diagonalization', 'eigenvector basis', 'similarity']),
                ('Distinct Eigenvalues and Independence',
                 'Eigenvectors belonging to distinct eigenvalues are linearly independent, so a '
                 'matrix with n distinct eigenvalues is diagonalisable, while a repeated '
                 'eigenvalue may still supply enough eigenvectors or may not.',
                 ['distinct eigenvalues', 'independence', 'sufficient condition']),
                ('Powers from Diagonalization',
                 'Once A = PDP^-1 holds, every power is A^k = PD^kP^-1, so diagonalisation '
                 'turns repeated application of A into raising each eigenvalue to the k-th '
                 'power.',
                 ['matrix power', 'diagonal power', 'iteration']),
            ]),
            ('Complex Eigenvalues', [
                ('Complex Eigenvalues in Conjugate Pairs',
                 'A real matrix can have nonreal eigenvalues, and they occur in conjugate pairs '
                 'with conjugate eigenvectors, so a 2 by 2 rotation by theta has eigenvalues '
                 'cos theta plus or minus i sin theta.',
                 ['complex eigenvalue', 'conjugate pair', 'rotation']),
                ('Rotation and Scaling from Complex Eigenvalues',
                 'A real 2 by 2 matrix with complex eigenvalues is similar to a rotation '
                 'combined with a scaling by the modulus of the eigenvalue, which is why its '
                 'orbits spiral instead of lying along invariant lines.',
                 ['rotation scaling', 'modulus', 'spiral']),
            ]),
            ('Markov Matrices (Application)', [
                ('Markov Matrices and Steady States',
                 'A Markov matrix has nonnegative entries with every column summing to 1, so 1 '
                 'is always an eigenvalue and a steady state is a probability eigenvector for '
                 'it.',
                 ['markov matrix', 'stochastic', 'steady state']),
                ('Convergence to the Steady State',
                 'If some power of a Markov matrix has all positive entries then the iterates '
                 'converge to the steady state from every starting distribution, because all '
                 'other eigenvalues have modulus strictly below 1.',
                 ['convergence', 'positive entries', 'eigenvalue modulus']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 11
    {
        'unit': 'Symmetric Matrices and the Spectral Theorem',
        'about': ('The strongest structure a real matrix can have: orthogonal '
                  'diagonalisation of symmetric matrices, quadratic forms, and positive '
                  'definiteness.'),
        'sections': [],
        'topics': [
            ('The Spectral Theorem', [
                ('Orthogonal Diagonalization of Symmetric Matrices',
                 'A real matrix is symmetric exactly when it equals QDQ^T with Q orthogonal '
                 'and D real diagonal, so every symmetric matrix has real eigenvalues and an '
                 'orthonormal basis of eigenvectors.',
                 ['spectral theorem', 'orthogonal diagonalization', 'real eigenvalues']),
                ('Orthogonality of Eigenvectors',
                 'Eigenvectors of a symmetric matrix that belong to different eigenvalues are '
                 'orthogonal, which is the step that lets each eigenspace be orthonormalised '
                 'separately and still combine into one orthonormal eigenbasis.',
                 ['orthogonal eigenvectors', 'distinct eigenvalues', 'eigenbasis']),
            ]),
            ('Quadratic Forms', [
                ('The Quadratic Form of a Matrix',
                 'A quadratic form is x^T A x for a symmetric A, and replacing A by its '
                 'symmetric part leaves every value unchanged, so every quadratic form may be '
                 'written with a symmetric matrix without loss.',
                 ['quadratic form', 'symmetric part', 'homogeneous degree two']),
                ('Diagonalizing a Quadratic Form',
                 'Substituting x = Qy with Q the orthogonal eigenvector matrix turns x^T A x '
                 'into a weighted sum of squares of the y coordinates, so the eigenvalues are '
                 'the coefficients in the principal-axis description.',
                 ['principal axes', 'change of variable', 'sum of squares']),
            ]),
            ('Positive-Definite Matrices', [
                ('The Positive-Definite Test',
                 'A symmetric matrix is positive definite when x^T A x is positive for every '
                 'nonzero x, which holds exactly when all its eigenvalues are positive, and '
                 'then it factors as R^T R with R invertible.',
                 ['positive definite', 'eigenvalue test', 'factorization']),
                ('Sylvester\'s Criterion',
                 'Sylvester\'s criterion says a symmetric matrix is positive definite exactly '
                 'when every leading principal minor is positive, so definiteness is checked '
                 'from the elimination pivots without computing eigenvalues.',
                 ['sylvester criterion', 'principal minor', 'pivot sign']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 12
    {
        'unit': 'The Singular Value Decomposition',
        'about': ('The factorisation that exists for every matrix: how the SVD is computed, '
                  'what it does to the four subspaces and the unit sphere, and how truncation '
                  'gives low-rank approximation.'),
        'sections': [],
        'topics': [
            ('Computing the SVD', [
                ('Singular Values of a Matrix',
                 'The singular values of A are the square roots of the eigenvalues of A^T A, '
                 'which are nonnegative because A^T A is symmetric positive semidefinite, and '
                 'the right singular vectors are its orthonormal eigenvectors.',
                 ['singular value', 'a transpose a', 'eigenvalue']),
                ('The SVD Factorization',
                 'Every m by n matrix factors as A = U Sigma V^T with U and V orthogonal and '
                 'Sigma diagonal with nonnegative entries in decreasing order, and the rank of '
                 'A is the number of positive singular values.',
                 ['svd', 'orthogonal factors', 'rank']),
            ]),
            ('Geometry and Subspaces of the SVD', [
                ('The SVD as Rotate-Scale-Rotate',
                 'The SVD sends each right singular vector vi to the scaled left singular '
                 'vector sigma_i ui, so it maps the unit sphere to an ellipsoid whose semi-axis '
                 'lengths are the singular values and generalises diagonalisation to '
                 'non-square matrices.',
                 ['ellipsoid', 'geometric action', 'non-square']),
                ('Singular Vectors as Subspace Bases',
                 'The right singular vectors with positive singular values form an orthonormal '
                 'basis of the row space, the matching left singular vectors one of the column '
                 'space, and the remaining vectors span the two null spaces.',
                 ['subspace basis', 'row space', 'null space']),
            ]),
            ('Low-Rank Approximation and Applications', [
                ('The Best Rank-k Approximation',
                 'Truncating the SVD after its k largest singular values gives the matrix of '
                 'rank at most k nearest to A in both the spectral and Frobenius norms, which '
                 'is the Eckart-Young theorem.',
                 ['low rank', 'eckart-young', 'truncation']),
                ('Pseudoinverse and Condition Number',
                 'The pseudoinverse V Sigma^+ U^T solves the least-squares problem for '
                 'rank-deficient A, and the ratio of largest to smallest positive singular '
                 'value measures how strongly small data errors are amplified.',
                 ['pseudoinverse', 'condition number', 'rank deficient']),
            ]),
        ],
    },
]
