"""Physics outline, in the shape ``scripts/course_pipeline.py`` expects.

Scope and sequence authored for the Luminfest Learning Harness (CC0). The sequence is
algebra-based introductory physics: measurement, mechanics, oscillations and waves,
thermal physics, electricity and magnetism, optics, then modern physics.

Textbook anchors are OpenStax **Physics (1e)** as the spine and OpenStax **College
Physics (1e)** where the spine has no chapter (fluids, centre of mass, angular
momentum, Kirchhoff's rules). Both are CC BY 4.0 and text-eligible. The 2e editions
and ``university-physics-volume-*`` report CC BY-NC-SA and are link-only: they are
named in ``TEXTBOOK['link_only_note']`` and never used as anchors.

Every page slug below was read from the publisher's own table of contents via
``scripts/probe_sections.py --book physics`` / ``--book college-physics``.
"""

from __future__ import annotations

ID = 'physics'
TITLE = 'Physics'
SUBJECT = 'Physics'
SUBJECT_KIND = 'science'
EXPECTED_WEEKS = 36
COURSE_LINE = 'Physics - Mechanics, Waves, Electromagnetism and Modern Physics'
DESCRIPTION = ('An algebra-based introduction to physics: measurement, motion and forces, energy '
               'and momentum, rotation and gravitation, oscillations and waves, fluids and '
               'thermodynamics, electricity and magnetism, optics, and the relativistic and '
               'quantum ideas that close the course.')

TEXTBOOK = {
    'spine': 'OpenStax Physics (1e, CC BY 4.0)',
    'supplements': ['OpenStax College Physics (1e, CC BY 4.0)'],
    'link_only_note': ('OpenStax College Physics 2e and University Physics Volumes 1-3 report '
                       'CC BY-NC-SA 4.0 and are carried as link-only study references: never '
                       'stored, quoted or used as anchors.'),
}

UNITS = [
    # ---------------------------------------------------------------- 1
    {
        'unit': 'Foundations & Measurement',
        'about': 'Fixes the measurement vocabulary of units, uncertainty and vectors that every '
                 'later model in the course is written in.',
        'sections': [
            ('physics', '1-3-the-language-of-physics-physical-quantities-and-units'),
            ('college-physics', '1-3-accuracy-precision-and-significant-figures'),
            ('physics', '1-2-the-scientific-methods'),
            ('physics', '5-1-vector-addition-and-subtraction-graphical-methods'),
        ],
        'topics': [
            ('Units, Dimensions & Precision', [
                ('SI Base Units and Derived Units',
                 'Every mechanical quantity reduces to powers of the seven SI base units, so '
                 'the newton is kg·m/s² and carries the dimensions of force rather than a new '
                 'base unit.',
                 ['si units', 'derived units', 'dimensions']),
                ('Dimensional Consistency',
                 'An equation is dimensionally consistent only when both sides carry the same '
                 'base-unit powers; a mismatch proves the equation wrong, while a match does '
                 'not prove it right.',
                 ['dimensional analysis', 'units', 'consistency']),
                ('Significant Figures in Measurement',
                 'The significant figures of a measurement record the digits the instrument '
                 'actually resolves, so quoting 12.30 cm claims a precision that 12.3 cm does '
                 'not, and a product keeps the fewest figures of its inputs.',
                 ['significant figures', 'precision', 'rounding']),
            ]),
            ('Vectors & Scalars', [
                ('Scalar and Vector Quantities',
                 'A scalar is fixed by magnitude alone while a vector needs magnitude and '
                 'direction, which is why 5 m of distance and 5 m east of displacement '
                 'describe different states.',
                 ['scalar', 'vector', 'displacement']),
                ('Vector Components',
                 'Any vector splits into perpendicular components of magnitude V cos θ and '
                 'V sin θ, and those components add independently, so one two-dimensional '
                 'problem becomes two one-dimensional problems.',
                 ['components', 'resolution', 'projection']),
                ('Adding Vectors Tip to Tail',
                 'Vectors add by placing them tip to tail, and the Pythagorean result applies '
                 'only to perpendicular components; at any other angle the law of cosines '
                 'gives the resultant.',
                 ['vector addition', 'resultant', 'parallelogram']),
            ]),
            ('Estimation & Measurement Reasoning', [
                ('Order-of-Magnitude Estimation',
                 'A Fermi estimate multiplies rounded factors so their powers of ten add, '
                 'which fixes a quantity to its nearest order of magnitude even when each '
                 'factor is uncertain by a factor of a few.',
                 ['estimation', 'order of magnitude', 'fermi']),
                ('Random and Systematic Uncertainty',
                 'Averaging N independent readings shrinks random uncertainty as 1/√N, while '
                 'systematic uncertainty survives averaging because it shifts every reading '
                 'the same way.',
                 ['uncertainty', 'random error', 'systematic error']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 2
    {
        'unit': 'Kinematics',
        'about': 'Turns position, velocity and acceleration into a predictive language for '
                 'motion, first along a line and then in two dimensions.',
        'sections': [
            ('physics', '2-3-position-vs-time-graphs'),
            ('physics', '3-1-acceleration'),
            ('college-physics', '2-7-falling-objects'),
            ('physics', '5-3-projectile-motion'),
        ],
        'topics': [
            ('Motion in One Dimension', [
                ('Position, Displacement and Distance',
                 'Displacement is the change in position and is zero over a closed path, while '
                 'distance travelled is the path length and never decreases.',
                 ['displacement', 'distance', 'position']),
                ('Average and Instantaneous Velocity',
                 'Average velocity is displacement divided by elapsed time, while instantaneous '
                 'velocity is the limit of that ratio as the interval shrinks and equals the '
                 'slope of the tangent on a position graph.',
                 ['velocity', 'average velocity', 'instantaneous']),
                ('Acceleration as the Rate of Change of Velocity',
                 'Acceleration is the change of velocity per unit time, so a body accelerates '
                 'whenever its velocity changes, including when only its direction changes at '
                 'constant speed.',
                 ['acceleration', 'rate of change', 'direction']),
            ]),
            ('Motion Graphs', [
                ('Reading a Position-Time Graph',
                 'On a position-time graph the slope at a point is the instantaneous velocity, '
                 'so a horizontal segment means rest and a curl means changing velocity.',
                 ['position graph', 'slope', 'velocity']),
                ('Reading a Velocity-Time Graph',
                 'On a velocity-time graph the slope gives acceleration and the area between '
                 'the curve and the time axis gives displacement, with area below the axis '
                 'counted as negative.',
                 ['velocity graph', 'area', 'displacement']),
                ('Constant-Acceleration Kinematics',
                 'For constant acceleration v = v₀ + at and Δx = v₀t + ½at² follow from the '
                 'definitions of velocity and acceleration, and both fail once the '
                 'acceleration itself varies.',
                 ['kinematic equations', 'constant acceleration', 'displacement']),
            ]),
            ('Free Fall', [
                ('Free Fall Under Gravity',
                 "Near Earth's surface a body in free fall accelerates downward at about "
                 '9.8 m/s² when air resistance is negligible, whatever its mass.',
                 ['free fall', 'gravity', 'acceleration']),
                ('Terminal Velocity',
                 'A falling body reaches terminal velocity when the upward drag equals its '
                 'weight, after which its acceleration is zero and its speed stops increasing.',
                 ['terminal velocity', 'drag', 'equilibrium']),
            ]),
            ('Projectile & 2D Motion', [
                ('Projectile Motion as Two Independent Motions',
                 "A projectile's horizontal velocity stays constant while its vertical motion "
                 'accelerates at g, so the trajectory is a parabola and the flight time is set '
                 'by the vertical component alone.',
                 ['projectile', 'parabola', 'independence']),
                ('Range and Launch Angle',
                 'For a fixed launch speed over level ground the range is greatest at 45°, and '
                 'complementary angles such as 30° and 60° give the same range.',
                 ['range', 'launch angle', 'trajectory']),
                ('Relative Velocity in Two Dimensions',
                 'Velocities combine as vectors between frames, so a boat crossing a current '
                 'must aim upstream of its intended path and its ground speed is the vector '
                 'sum of boat and current.',
                 ['relative velocity', 'frame of reference', 'current']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 3
    {
        'unit': "Forces & Newton's Laws",
        'about': 'Introduces force as an interaction and installs the free-body habit that '
                 'every later mechanics unit reuses.',
        'sections': [
            ('physics', '4-2-newtons-first-law-of-motion-inertia'),
            ('physics', '4-3-newtons-second-law-of-motion'),
            ('physics', '4-4-newtons-third-law-of-motion'),
            ('college-physics', '6-3-centripetal-force'),
        ],
        'topics': [
            ("Newton's Laws & Free-Body Diagrams", [
                ("Newton's First Law and Inertia",
                 'A body keeps its velocity unless a net external force acts on it, so rest '
                 'and constant velocity are the same dynamical state and no force is needed '
                 'to sustain motion.',
                 ['inertia', 'first law', 'net force']),
                ("Newton's Second Law for a Single Body",
                 'The vector sum of the external forces equals mass times acceleration, so a '
                 'body accelerates along the net force and not at all perpendicular to it.',
                 ['second law', 'net force', 'acceleration']),
                ('Free-Body Diagrams and Their Conventions',
                 'A free-body diagram draws only the forces acting on one chosen body, with '
                 'weight always vertical and a normal force always perpendicular to the '
                 'contact surface.',
                 ['free-body diagram', 'normal force', 'conventions']),
            ]),
            ('Common Forces', [
                ('Weight versus Mass',
                 'Weight is the gravitational force mg and changes with the local field, while '
                 'mass measures the quantity of matter and is the same everywhere.',
                 ['weight', 'mass', 'gravity']),
                ('Normal Force',
                 'The normal force takes whatever magnitude prevents interpenetration, so it '
                 'equals mg only on level ground with no other vertical force acting.',
                 ['normal force', 'contact force', 'surface']),
                ('Static and Kinetic Friction',
                 'Kinetic friction has magnitude μ_k N and opposes sliding, while static '
                 'friction adjusts up to μ_s N, so a block stays put until the applied force '
                 'exceeds that limit.',
                 ['friction', 'static', 'kinetic']),
            ]),
            ('Applying Newton\'s Laws', [
                ('Equilibrium and Zero Net Force',
                 'A body in equilibrium has zero net force, so the force components along any '
                 'two perpendicular axes each sum to zero.',
                 ['equilibrium', 'net force', 'components']),
                ('Forces on an Inclined Plane',
                 'On a frictionless incline of angle θ the weight component along the slope is '
                 'mg sin θ and the normal force is mg cos θ, so the acceleration down the '
                 'slope is g sin θ.',
                 ['inclined plane', 'components', 'acceleration']),
                ('Connected Bodies and Tension',
                 'Bodies joined by a taut string share one acceleration, and a massless string '
                 'over a frictionless pulley transmits the same tension at both ends.',
                 ['tension', 'connected bodies', 'pulley']),
            ]),
            ('Circular Motion Dynamics', [
                ('Centripetal Acceleration',
                 'A body moving on a circle of radius r at speed v accelerates toward the '
                 'centre with magnitude v²/r even when its speed is constant.',
                 ['centripetal', 'circular motion', 'acceleration']),
                ('Centripetal Force Is a Net Force',
                 'The centripetal force is not an extra interaction but the radial part of the '
                 'net force, supplied by tension, gravity, friction or a normal force '
                 'depending on the situation.',
                 ['centripetal force', 'net force', 'radial']),
                ('Minimum Speed at the Top of a Loop',
                 "At the top of a vertical loop the normal force vanishes at the minimum speed "
                 "v = √(gr), so gravity alone supplies the centripetal force and any slower "
                 'body leaves the track.',
                 ['vertical circle', 'minimum speed', 'normal force']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 4
    {
        'unit': 'Work & Energy',
        'about': 'Reframes mechanics around energy, so problems with varying forces become '
                 'bookkeeping instead of force integration.',
        'sections': [
            ('physics', '9-1-work-power-and-the-work-energy-theorem'),
            ('physics', '9-2-mechanical-energy-and-conservation-of-energy'),
            ('college-physics', '7-7-power'),
        ],
        'topics': [
            ('Work & Power', [
                ('Work Done by a Constant Force',
                 'Work equals F d cos θ, so a force perpendicular to the displacement, such as '
                 'the normal force on level ground, does zero work.',
                 ['work', 'dot product', 'force']),
                ('Power as the Rate of Energy Transfer',
                 'Power is work per unit time, equal to F v cos θ, so a given power lifts a '
                 'doubled load at half the speed.',
                 ['power', 'rate', 'watt']),
                ('The Work-Energy Theorem',
                 'The net work done on a body equals its change in kinetic energy, and the '
                 'statement holds even when the force varies along the path.',
                 ['work-energy theorem', 'kinetic energy', 'net work']),
            ]),
            ('Kinetic & Potential Energy', [
                ('Kinetic Energy',
                 'Kinetic energy is ½mv², so doubling the speed quadruples it and the same '
                 'braking force then needs four times the distance to stop.',
                 ['kinetic energy', 'speed', 'stopping distance']),
                ('Gravitational Potential Energy Near Earth',
                 'Near the surface the gravitational potential energy of a mass is mgh measured '
                 'from a chosen reference height, and only its change is physically meaningful.',
                 ['potential energy', 'height', 'reference']),
                ('Elastic Potential Energy',
                 'A spring deformed by x stores ½kx², so the stored energy grows with the '
                 'square of the deformation and is the same for stretch and compression.',
                 ['spring', 'elastic', 'hooke']),
            ]),
            ('Conservation of Energy', [
                ('Conservation of Mechanical Energy',
                 'When only conservative forces do work the sum of kinetic and potential energy '
                 'stays constant, so a falling body converts mgh into ½mv² exactly.',
                 ['conservation', 'mechanical energy', 'conservative']),
                ('Work by Nonconservative Forces',
                 'Friction and drag change the mechanical energy by exactly the negative of '
                 'the work they do, and the difference appears as thermal energy rather than '
                 'disappearing.',
                 ['friction', 'dissipation', 'thermal energy']),
                ('System Boundaries in Energy Accounting',
                 'The chosen system boundary decides which energies count as internal and '
                 'conserved and which appear as external work, so one process can be booked '
                 'either way.',
                 ['system boundary', 'energy accounting', 'internal energy']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 5
    {
        'unit': 'Momentum & Collisions',
        'about': 'Adds the quantity that survives a collision, where kinetic energy is lost but '
                 'momentum is not.',
        'sections': [
            ('physics', '8-1-linear-momentum-force-and-impulse'),
            ('physics', '8-2-conservation-of-momentum'),
            ('physics', '8-3-elastic-and-inelastic-collisions'),
            ('college-physics', '8-6-collisions-of-point-masses-in-two-dimensions'),
        ],
        'topics': [
            ('Impulse & Momentum', [
                ('Linear Momentum',
                 'Momentum is mv, a vector, so a light body moving fast can carry the same '
                 'momentum as a heavy slow one.',
                 ['momentum', 'mass', 'velocity']),
                ('The Impulse-Momentum Theorem',
                 'Impulse equals the change in momentum, so stretching the contact time for a '
                 'fixed impulse lowers the average force, which is how airbags and crumple '
                 'zones protect occupants.',
                 ['impulse', 'force', 'contact time']),
            ]),
            ('Conservation of Momentum & Collisions', [
                ('Conservation of Linear Momentum',
                 'When the net external force on a system is zero its total momentum is '
                 'constant, because the internal forces of an interaction cancel in pairs.',
                 ['conservation', 'momentum', 'isolated system']),
                ('Elastic versus Inelastic Collisions',
                 'Kinetic energy is conserved only in an elastic collision; in a perfectly '
                 'inelastic one the bodies move together afterwards and the largest energy '
                 'compatible with momentum conservation is lost.',
                 ['elastic', 'inelastic', 'kinetic energy']),
                ('Two-Dimensional Collisions',
                 'Momentum conservation applies to each component separately, so a '
                 'two-dimensional collision gives two equations for one event.',
                 ['two-dimensional', 'components', 'collision']),
            ]),
            ('Center of Mass', [
                ('Center of Mass of a System',
                 "The centre of mass is the mass-weighted mean position, so a system's "
                 'translational motion obeys Newton\'s second law as if its total mass were '
                 'concentrated there.',
                 ['center of mass', 'weighted average', 'system']),
                ('Motion of the Center of Mass',
                 'Internal forces cannot move the centre of mass, so after an explosion the '
                 'fragments\' centre of mass continues on the original trajectory.',
                 ['center of mass', 'internal forces', 'trajectory']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 6
    {
        'unit': 'Rotational Motion',
        'about': 'Carries the linear mechanics of the earlier units into rotation by matching '
                 'each linear quantity with its angular partner.',
        'sections': [
            ('college-physics', '10-2-kinematics-of-rotational-motion'),
            ('college-physics', '10-3-dynamics-of-rotational-motion-rotational-inertia'),
            ('college-physics', '10-4-rotational-kinetic-energy-work-and-energy-revisited'),
            ('college-physics', '10-5-angular-momentum-and-its-conservation'),
        ],
        'topics': [
            ('Rotational Kinematics', [
                ('Angular Displacement, Velocity and Acceleration',
                 'Angular quantities obey the same kinematic equations as linear ones with θ, '
                 'ω and α in place of x, v and a, and arc length is linked to angle by s = rθ.',
                 ['angular velocity', 'radian', 'kinematics']),
                ('Rolling Without Slipping',
                 'A wheel rolling without slipping has v = ωr at its centre, travels 2πr per '
                 'full turn, and its contact point is instantaneously at rest.',
                 ['rolling', 'no slip', 'omega r']),
            ]),
            ('Torque & Moment of Inertia', [
                ('Torque about a Pivot',
                 'Torque is r F sin θ about a chosen pivot, so the same force gives more '
                 'torque at a longer lever arm and none when it points straight at the pivot.',
                 ['torque', 'lever arm', 'pivot']),
                ('Moment of Inertia',
                 'Moment of inertia is Σmr², so it depends on how far the mass sits from the '
                 'axis: a ring resists spinning more than a solid disc of the same mass.',
                 ['moment of inertia', 'mass distribution', 'axis']),
                ('The Parallel-Axis Theorem',
                 'Moving the axis a distance d from the centre of mass adds md² to the moment '
                 'of inertia, so rotation about an off-centre axis is always harder.',
                 ['parallel axis', 'theorem', 'axis shift']),
            ]),
            ('Rotational Dynamics & Energy', [
                ("Rotational Form of Newton's Second Law",
                 'Net torque equals moment of inertia times angular acceleration, so for a '
                 'fixed torque a doubled moment of inertia halves the angular acceleration.',
                 ['torque', 'angular acceleration', 'second law']),
                ('Rotational Kinetic Energy',
                 'A spinning body has ½Iω² of kinetic energy, so a rolling body splits its '
                 'energy between translation ½mv² and rotation ½Iω².',
                 ['rotational energy', 'rolling', 'kinetic energy']),
                ('Static Equilibrium of Extended Bodies',
                 'An extended body is in equilibrium only when the net force is zero and the '
                 'net torque about one pivot is zero, which is two conditions rather than one.',
                 ['static equilibrium', 'torque', 'balance']),
            ]),
            ('Angular Momentum', [
                ('Angular Momentum',
                 'Angular momentum is L = Iω for a rigid body and mvr sin θ for a particle, so '
                 'the same particle has different angular momentum about different origins.',
                 ['angular momentum', 'moment of inertia', 'origin']),
                ('Conservation of Angular Momentum',
                 'With zero net external torque the total angular momentum stays constant, so a '
                 'skater who halves her moment of inertia doubles her spin rate.',
                 ['conservation', 'angular momentum', 'spin']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 7
    {
        'unit': 'Gravitation',
        'about': 'Extends the force model to planetary scale, where one inverse-square law sets '
                 'weight, orbits and escape.',
        'sections': [
            ('physics', '7-2-newtons-law-of-universal-gravitation-and-einsteins-theory-of-general-relativity'),
            ('college-physics', '7-3-gravitational-potential-energy'),
            ('physics', '7-1-keplers-laws-of-planetary-motion'),
        ],
        'topics': [
            ('Universal Gravitation', [
                ("Newton's Law of Universal Gravitation",
                 'Every pair of masses attracts with force G m₁m₂/r², so doubling the '
                 'separation cuts the force to a quarter and the force on each body is equal.',
                 ['gravitation', 'inverse square', 'newton']),
                ('Gravitational Field Strength',
                 'The gravitational field g = GM/r² is the force per unit mass, so it falls '
                 'with altitude and differs between Earth, the Moon and Mars.',
                 ['gravitational field', 'field strength', 'altitude']),
            ]),
            ('Gravitational Potential Energy', [
                ('Potential Energy at Large Separations',
                 'Far from a planet the potential energy is −GMm/r with zero taken at '
                 'infinity, so it is negative everywhere and rises toward zero as r grows.',
                 ['gravitational potential energy', 'infinity', 'negative']),
                ('Escape Velocity',
                 "The escape speed √(2GM/r) is the launch speed that makes total mechanical "
                 "energy zero, so it depends on the planet's mass and radius but not on the "
                 "projectile's mass.",
                 ['escape velocity', 'mechanical energy', 'launch']),
            ]),
            ('Orbits & Kepler\'s Laws', [
                ('Speed and Period of a Circular Orbit',
                 'A satellite in a circular orbit of radius r moves at √(GM/r), so a higher '
                 'orbit is slower and takes longer despite covering a longer path.',
                 ['orbit', 'satellite', 'period']),
                ("Kepler's Laws of Planetary Motion",
                 'A planet sweeps equal areas in equal times because its angular momentum about '
                 'the Sun is conserved, and its period squared is proportional to the '
                 'semi-major axis cubed.',
                 ['kepler', 'equal areas', 'period']),
                ('Weightlessness in Orbit',
                 'An astronaut and spacecraft in orbit fall together at g, so the normal force '
                 'vanishes; apparent weightlessness is free fall, not the absence of gravity.',
                 ['orbit', 'weightlessness', 'free fall']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 8
    {
        'unit': 'Oscillations',
        'about': 'Identifies the restoring-force pattern shared by springs, pendulums, waves and '
                 'circuits, and gives it a single description.',
        'sections': [
            ('physics', '5-5-simple-harmonic-motion'),
            ('college-physics', '16-4-the-simple-pendulum'),
            ('college-physics', '16-7-damped-harmonic-motion'),
            ('college-physics', '16-8-forced-oscillations-and-resonance'),
        ],
        'topics': [
            ('Simple Harmonic Motion', [
                ('Restoring Force and Simple Harmonic Motion',
                 'Motion is simple harmonic exactly when the restoring force is proportional '
                 'and opposite to the displacement, F = −kx, which makes displacement a sine '
                 'or cosine of time.',
                 ['restoring force', 'harmonic', 'hooke']),
                ('Amplitude, Period and Frequency',
                 'Amplitude is the maximum displacement and, for SHM, does not affect the '
                 'period; period is the time for one full cycle and frequency is its '
                 'reciprocal.',
                 ['amplitude', 'period', 'frequency']),
                ('Describing SHM by Phase',
                 'The displacement x = A cos(2πt/T) is fixed by amplitude and period alone, so '
                 'a phase angle states where in the cycle the oscillator sits.',
                 ['phase', 'cosine', 'cycle']),
            ]),
            ('Springs & Pendulums', [
                ('Period of a Mass on a Spring',
                 'A mass on a spring oscillates with T = 2π√(m/k), so a stiffer spring shortens '
                 'the period while a larger mass lengthens it.',
                 ['spring', 'period', 'stiffness']),
                ('The Simple Pendulum',
                 "For small angles a pendulum's period is 2π√(L/g), independent of its bob mass "
                 'and only approximately independent of amplitude.',
                 ['pendulum', 'small angle', 'period']),
            ]),
            ('Energy, Damping & Resonance in SHM', [
                ('Energy Exchange in SHM',
                 'An oscillator trades ½kx² of potential energy against ½mv² of kinetic energy, '
                 'and the total ½kA² stays constant while no damping acts.',
                 ['energy', 'oscillator', 'amplitude']),
                ('Damped Oscillations',
                 'Damping removes energy each cycle so the amplitude decays, and for a drag '
                 'force proportional to velocity that decay is exponential in time.',
                 ['damping', 'decay', 'amplitude']),
                ('Resonance',
                 'A driven oscillator reaches maximum amplitude when the driving frequency '
                 'matches its natural frequency, and weaker damping gives a taller and '
                 'narrower peak.',
                 ['resonance', 'natural frequency', 'driving']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 9
    {
        'unit': 'Waves & Sound',
        'about': 'Moves from one oscillator to many coupled ones, so energy travels through a '
                 'medium without the medium travelling with it.',
        'sections': [
            ('physics', '13-2-wave-properties-speed-amplitude-frequency-and-period'),
            ('physics', '13-3-wave-interaction-superposition-and-interference'),
            ('physics', '14-2-sound-intensity-and-sound-level'),
            ('physics', '14-3-doppler-effect-and-sonic-booms'),
        ],
        'topics': [
            ('Wave Properties & the Wave Equation', [
                ('Transverse and Longitudinal Waves',
                 'In a transverse wave the displacement is perpendicular to the propagation and '
                 'in a longitudinal wave it is parallel, which is why sound is a pressure wave '
                 'and a wave on a string is not.',
                 ['transverse', 'longitudinal', 'polarisation']),
                ('The Wave Equation v = fλ',
                 "Wave speed equals frequency times wavelength, so in a fixed medium a higher "
                 "frequency means a shorter wavelength because the speed is set by the medium.",
                 ['wavelength', 'frequency', 'wave speed']),
            ]),
            ('Wave Behavior at Boundaries', [
                ('Reflection and Transmission at a Boundary',
                 'At a boundary between media part of a wave reflects and part transmits, and a '
                 'fixed end inverts the reflected pulse while a free end returns it upright.',
                 ['reflection', 'transmission', 'boundary']),
                ('Refraction and the Change of Speed',
                 'A wave entering a slower medium bends toward the normal because its frequency '
                 'is fixed by the source while its speed and wavelength both fall.',
                 ['refraction', 'snell', 'speed change']),
                ('Diffraction Around Obstacles',
                 'A wave bends around an obstacle and spreads after an aperture, and the '
                 'spreading is pronounced only when the aperture is comparable to the '
                 'wavelength.',
                 ['diffraction', 'aperture', 'wavelength']),
            ]),
            ('Superposition, Interference & Standing Waves', [
                ('The Principle of Superposition',
                 'The displacements of overlapping waves add algebraically at every point, so '
                 'two crests give a doubled crest and a crest meeting a trough can cancel.',
                 ['superposition', 'interference', 'displacement']),
                ('Constructive and Destructive Interference',
                 'Two waves interfere constructively when their path difference is a whole '
                 'number of wavelengths and destructively when it is an odd number of half '
                 'wavelengths.',
                 ['constructive', 'destructive', 'path difference']),
                ('Standing Waves and Harmonics',
                 'A standing wave forms where two identical waves travel in opposite '
                 'directions, and a string fixed at both ends supports only wavelengths 2L/n.',
                 ['standing wave', 'nodes', 'harmonics']),
            ]),
            ('Sound, Intensity & the Doppler Effect', [
                ('Sound as a Pressure Wave',
                 'Sound is a longitudinal pressure wave travelling at about 343 m/s in air at '
                 '20 °C, and its speed rises with temperature because molecules collide more '
                 'often.',
                 ['sound', 'pressure wave', 'speed of sound']),
                ('Sound Intensity Level in Decibels',
                 'Sound level is 10 log₁₀(I/I₀) decibels, so a tenfold rise in intensity adds '
                 '10 dB and a hundredfold rise adds 20 dB.',
                 ['decibel', 'intensity', 'logarithm']),
                ('The Doppler Effect',
                 'An observer hears a higher frequency when source and observer approach and a '
                 'lower one when they recede, and the shift grows with their relative speed '
                 'compared with the wave speed.',
                 ['doppler', 'frequency shift', 'relative motion']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 10
    {
        'unit': 'Fluids',
        'about': 'Treats matter as a continuous medium, so pressure, buoyancy and flow explain '
                 'what particle mechanics makes unwieldy.',
        'sections': [
            ('college-physics', '11-3-pressure'),
            ('college-physics', '11-7-archimedes-principle'),
            ('college-physics', '12-1-flow-rate-and-its-relation-to-velocity'),
            ('college-physics', '12-2-bernoullis-equation'),
        ],
        'topics': [
            ('Density & Pressure', [
                ('Density and Specific Gravity',
                 'Density is mass per unit volume and specific gravity compares it with water, '
                 'so a body whose specific gravity is below 1 floats in water.',
                 ['density', 'specific gravity', 'volume']),
                ('Pressure in a Fluid',
                 'Pressure is force per unit area acting perpendicular to a surface, and at a '
                 'point in a static fluid it has the same value in every direction.',
                 ['pressure', 'force per area', 'isotropic']),
                ('Pressure Variation with Depth',
                 'In a static fluid the pressure at depth h is p₀ + ρgh, so about 10 m of water '
                 'adds one atmosphere of gauge pressure.',
                 ['depth', 'gauge pressure', 'atmosphere']),
            ]),
            ("Buoyancy & Archimedes' Principle", [
                ("Archimedes' Principle",
                 'A submerged or floating body feels an upward buoyant force equal to the '
                 'weight of the fluid it displaces.',
                 ['buoyancy', 'displaced fluid', 'archimedes']),
                ('Floating and Sinking Conditions',
                 "A body floats when its average density is below the fluid's, and it then "
                 'displaces exactly its own weight, so the submerged fraction equals the '
                 'density ratio.',
                 ['floating', 'sinking', 'density ratio']),
                ("Pascal's Principle",
                 'A pressure change applied to an enclosed fluid is transmitted undiminished, '
                 'so a hydraulic press multiplies force by the ratio of piston areas while the '
                 'pistons move inversely.',
                 ['pascal', 'hydraulic', 'pressure transmission']),
            ]),
            ('Fluid Dynamics', [
                ('The Continuity Equation',
                 'For an incompressible fluid the volume flow rate A v is constant along a '
                 'pipe, so narrowing the pipe speeds the fluid up.',
                 ['continuity', 'flow rate', 'incompressible']),
                ("Bernoulli's Equation",
                 'Along a streamline of steady, non-viscous, incompressible flow p + ½ρv² + '
                 'ρgh is constant, so faster flow at the same height means lower pressure.',
                 ['bernoulli', 'streamline', 'pressure']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 11
    {
        'unit': 'Thermodynamics',
        'about': 'Joins the microscopic motion of molecules to the macroscopic quantities of '
                 'temperature, heat and work, and states what such processes can never do.',
        'sections': [
            ('physics', '11-1-temperature-and-thermal-energy'),
            ('physics', '11-2-heat-specific-heat-and-heat-transfer'),
            ('college-physics', '13-3-the-ideal-gas-law'),
            ('physics', '12-3-second-law-of-thermodynamics-entropy'),
        ],
        'topics': [
            ('Temperature, Heat & Thermal Expansion', [
                ('Temperature and Thermal Equilibrium',
                 'Temperature is the quantity that decides the direction of heat flow, and two '
                 'bodies in contact exchange no net energy only when their temperatures match.',
                 ['temperature', 'equilibrium', 'zeroth law']),
                ('Heat versus Internal Energy',
                 'Heat is energy in transit because of a temperature difference, so a large '
                 'cool body can hold more internal energy than a small hot one.',
                 ['heat', 'internal energy', 'temperature difference']),
                ('Thermal Expansion of Solids and Liquids',
                 'A solid changes length by αL₀ΔT and volume by βV₀ΔT, so expansion scales with '
                 'the original dimension and matters most in long structures.',
                 ['thermal expansion', 'coefficient', 'length']),
            ]),
            ('Specific Heat & Phase Change', [
                ('Specific Heat Capacity',
                 "The energy needed to change a temperature is mcΔT, so water's 4186 J/kg·K "
                 'makes it a slow-warming coolant and a stable heat reservoir.',
                 ['specific heat', 'calorimetry', 'energy']),
                ('Latent Heat of Fusion and Vaporisation',
                 'A phase change happens at constant temperature and absorbs Q = mL, so melting '
                 'ice at 0 °C takes energy without raising its temperature at all.',
                 ['latent heat', 'phase change', 'melting']),
                ('Calorimetry and Heat Balance',
                 'In a thermally isolated system the heat lost by the hot bodies equals the heat '
                 'gained by the cold ones, and that balance fixes the final common temperature.',
                 ['calorimetry', 'heat balance', 'isolated']),
            ]),
            ('Kinetic Theory & Gas Laws', [
                ('The Ideal Gas Law',
                 'For an ideal gas pV = nRT links pressure, volume and absolute temperature, so '
                 'at fixed volume the pressure is proportional to the kelvin temperature.',
                 ['ideal gas', 'kelvin', 'pressure']),
                ('Kinetic Theory of Gases',
                 'Pressure comes from molecular momentum transfer to the walls, and the mean '
                 'translational kinetic energy 3/2 kT depends only on absolute temperature.',
                 ['kinetic theory', 'rms speed', 'temperature']),
                ('Molecular Speeds and Effusion',
                 'Root-mean-square speed grows as √(T/M), so at one temperature a light gas '
                 'moves faster and effuses faster than a heavy one.',
                 ['molecular speed', 'effusion', 'molar mass']),
            ]),
            ('Laws of Thermodynamics', [
                ('The First Law of Thermodynamics',
                 'The first law states ΔU = Q − W, so energy entering as heat either raises '
                 'internal energy or leaves as work done by the system.',
                 ['first law', 'internal energy', 'work']),
                ('The Second Law and Entropy',
                 'The second law states that the entropy of an isolated system never decreases, '
                 'so heat flows spontaneously from hot to cold and no cyclic engine converts '
                 'all its heat input into work.',
                 ['second law', 'entropy', 'irreversibility']),
                ('Heat Engine Efficiency and the Carnot Limit',
                 "A heat engine's efficiency is W/Q_H and cannot exceed 1 − T_C/T_H, the Carnot "
                 'bound set by the absolute temperatures of its two reservoirs.',
                 ['efficiency', 'carnot', 'heat engine']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 12
    {
        'unit': 'Electrostatics',
        'about': 'Opens the electricity half of the course with charge, the field it makes, and '
                 'the potential that field stores.',
        'sections': [
            ('physics', '18-2-coulombs-law'),
            ('physics', '18-3-electric-field'),
            ('physics', '18-4-electric-potential'),
            ('physics', '18-5-capacitors-and-dielectrics'),
        ],
        'topics': [
            ("Charge & Coulomb's Law", [
                ('Electric Charge and Its Conservation',
                 'Charge comes in two signs, is conserved in every process, and is quantised in '
                 'units of 1.6×10⁻¹⁹ C.',
                 ['charge', 'quantisation', 'conservation']),
                ("Coulomb's Law",
                 'Two point charges repel or attract with force k q₁q₂/r², so tripling their '
                 'separation reduces the force to one ninth.',
                 ['coulomb', 'inverse square', 'point charge']),
                ('Charging by Conduction and Induction',
                 'Conduction transfers charge by contact while induction redistributes it '
                 'without contact, so a grounded object can be left with the opposite charge.',
                 ['induction', 'conduction', 'grounding']),
            ]),
            ('The Electric Field', [
                ('Electric Field of a Point Charge',
                 'The field of a point charge is kq/r² directed away from positive charge and '
                 'toward negative charge, defined as force per unit positive test charge.',
                 ['electric field', 'point charge', 'test charge']),
                ('Field Lines and Superposition',
                 'Field lines begin on positive charge and end on negative, never cross, and the '
                 'fields of several charges add as vectors at each point.',
                 ['field lines', 'superposition', 'vector sum']),
                ('Deflection of Charges in a Uniform Field',
                 'A charge launched across a uniform field follows a parabola, because a '
                 'constant electric force plays the role gravity plays for a projectile.',
                 ['uniform field', 'deflection', 'parabola']),
            ]),
            ('Electric Potential & Potential Energy', [
                ('Electric Potential Energy of Two Charges',
                 'The potential energy of two charges is k q₁q₂/r, so like charges pushed '
                 'together store positive energy and unlike charges store negative energy.',
                 ['potential energy', 'pair of charges', 'sign']),
                ('Electric Potential and Voltage',
                 'Electric potential is potential energy per unit charge, kq/r for a point '
                 'charge, and only potential differences are measured by a voltmeter.',
                 ['electric potential', 'voltage', 'difference']),
                ('Equipotentials and Field Direction',
                 'Equipotential surfaces are everywhere perpendicular to field lines, so moving '
                 'a charge along one at constant speed requires no work.',
                 ['equipotential', 'perpendicular', 'work']),
            ]),
            ('Conductors, Insulators & Capacitance', [
                ('Conductors and Insulators',
                 'Charge moves freely in a conductor, so in electrostatic equilibrium the field '
                 'inside it is zero and excess charge sits on its surface, while an insulator '
                 'holds charge in place.',
                 ['conductor', 'insulator', 'electrostatic equilibrium']),
                ('Capacitance',
                 'A capacitor stores charge Q = CV at a given potential difference, and a '
                 'parallel-plate capacitor has C = ε₀A/d, so closer plates store more charge.',
                 ['capacitance', 'parallel plate', 'dielectric']),
                ('Energy Stored in a Capacitor',
                 'A charged capacitor stores ½CV² of energy, and inserting a dielectric of '
                 'constant κ raises its capacitance by the factor κ at the same voltage.',
                 ['energy stored', 'capacitor', 'dielectric']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 13
    {
        'unit': 'Electric Circuits',
        'about': 'Applies charge and potential to steady currents, so any resistor network can '
                 'be analysed rather than memorised case by case.',
        'sections': [
            ('physics', '19-1-ohms-law'),
            ('physics', '19-2-series-circuits'),
            ('physics', '19-4-electric-power'),
            ('college-physics', '21-3-kirchhoffs-rules'),
        ],
        'topics': [
            ('Current, Resistance & Ohm\'s Law', [
                ('Electric Current',
                 'Current is the rate of charge flow, I = ΔQ/Δt, measured in amperes, and '
                 'conventional current points opposite to the drift of electrons.',
                 ['current', 'ampere', 'conventional current']),
                ('Resistance and Resistivity',
                 'Resistance is V/I, and for a uniform wire R = ρL/A, so doubling the length '
                 'doubles it while doubling the cross-section halves it.',
                 ['resistance', 'resistivity', 'ohm']),
                ('Ohmic and Non-ohmic Conductors',
                 'A conductor is ohmic only when its resistance is independent of the applied '
                 'voltage, which is why a filament lamp gives a curved current-voltage graph '
                 'rather than a straight line.',
                 ['ohmic', 'non-ohmic', 'graph']),
            ]),
            ('Series & Parallel Circuits', [
                ('Series Circuits',
                 'In a series circuit the current is the same through every element and the '
                 'voltages add, so the total resistance is the sum of the parts.',
                 ['series', 'current', 'voltage divider']),
                ('Parallel Circuits',
                 'In a parallel circuit the voltage is the same across every branch and the '
                 'currents add, so the total resistance is smaller than any single branch.',
                 ['parallel', 'voltage', 'branch']),
                ('Equivalent Resistance of Networks',
                 'Series and parallel rules reduce any resistor network to one equivalent '
                 'resistance, which then fixes the total current drawn from the source.',
                 ['equivalent resistance', 'network', 'reduction']),
            ]),
            ('Electrical Power & Energy', [
                ('Electric Power Dissipation',
                 'A resistor converts P = IV = I²R = V²/R into thermal energy, so transmission '
                 'losses fall with the square of the current when the same power is delivered '
                 'at higher voltage.',
                 ['power', 'joule heating', 'i squared r']),
                ('Energy Consumption and the Kilowatt-hour',
                 'Electrical energy is power multiplied by time, and one kilowatt-hour equals '
                 '3.6 MJ, which is the unit a domestic meter bills.',
                 ['kilowatt hour', 'energy', 'billing']),
            ]),
            ("Kirchhoff's Rules & Capacitors in Circuits", [
                ("Kirchhoff's Junction and Loop Rules",
                 'Charge conservation at a junction gives the current rule and energy '
                 'conservation around a loop gives the voltage rule, which together solve '
                 'networks that series-parallel reduction cannot.',
                 ['kirchhoff', 'junction', 'loop']),
                ('Capacitors in Series and Parallel',
                 'Capacitors combine oppositely to resistors: in parallel their capacitances '
                 'add and in series their reciprocals add, because they share voltage or '
                 'charge respectively.',
                 ['capacitors', 'series', 'parallel']),
                ('RC Charging and the Time Constant',
                 'A capacitor charging through a resistor reaches 63% of its final voltage '
                 'after one time constant τ = RC, and is treated as fully charged after about '
                 'five.',
                 ['rc circuit', 'time constant', 'charging']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 14
    {
        'unit': 'Magnetism & Electromagnetic Induction',
        'about': 'Unites electricity and magnetism into one interaction and shows how a changing '
                 'field produces the currents that drive the grid.',
        'sections': [
            ('physics', '20-1-magnetic-fields-field-lines-and-force'),
            ('college-physics', '22-9-magnetic-fields-produced-by-currents-amperes-law'),
            ('physics', '20-3-electromagnetic-induction'),
            ('college-physics', '24-3-the-electromagnetic-spectrum'),
        ],
        'topics': [
            ('Magnetic Fields & Forces', [
                ('Magnetic Field Lines and Poles',
                 'Magnetic field lines run from north to south outside a magnet, close on '
                 'themselves, never cross, and no isolated magnetic pole has been observed.',
                 ['magnetic field', 'poles', 'field lines']),
                ('Magnetic Force on a Moving Charge',
                 'A charge moving in a magnetic field feels F = qvB sin θ perpendicular to both '
                 'v and B, so the force does no work and only bends the path.',
                 ['lorentz force', 'moving charge', 'perpendicular']),
                ('Magnetic Force on a Current-Carrying Wire',
                 'A straight wire carrying current I in a field B feels F = BIL sin θ, which is '
                 'the principle behind motors and loudspeakers.',
                 ['current', 'wire', 'force']),
            ]),
            ('Sources of the Magnetic Field', [
                ('Field of a Long Straight Wire',
                 'A long straight wire produces B = μ₀I/(2πr) circling it, so the field halves '
                 'at twice the distance while the current sets its strength.',
                 ['ampere', 'straight wire', 'permeability']),
                ('Solenoids and Electromagnets',
                 'Inside a solenoid the field is B = μ₀nI and nearly uniform, so more turns per '
                 'metre or more current strengthens an electromagnet in proportion.',
                 ['solenoid', 'electromagnet', 'turns']),
                ('Torque on a Current Loop',
                 'A current loop in a magnetic field feels torque τ = NIAB sin θ, which turns '
                 'its normal into alignment with the field, as in a motor or an analogue meter.',
                 ['torque', 'current loop', 'motor']),
            ]),
            ('Electromagnetic Induction', [
                ('Magnetic Flux',
                 'Magnetic flux Φ = BA cos θ counts the field lines through an area, so '
                 'tilting a loop reduces the flux and at 90° it is zero.',
                 ['flux', 'area', 'angle']),
                ("Faraday's Law of Induction",
                 'The induced emf equals the negative rate of change of magnetic flux, so a '
                 'faster flux change or more turns in the coil gives a larger emf.',
                 ['faraday', 'induced emf', 'flux change']),
                ("Lenz's Law",
                 'An induced current flows in the direction whose own field opposes the change '
                 'that produced it, which is why a magnet falling through a copper tube drops '
                 'slowly.',
                 ['lenz', 'opposition', 'direction']),
            ]),
            ('Introduction to Electromagnetic Waves', [
                ("Maxwell's Prediction of EM Waves",
                 'A changing electric field induces a magnetic field and a changing magnetic '
                 'field induces an electric one, so the pair sustains a wave travelling at '
                 'c = 1/√(μ₀ε₀).',
                 ['maxwell', 'electromagnetic wave', 'speed of light']),
                ('The Electromagnetic Spectrum',
                 'Radio, microwave, infrared, visible, ultraviolet, X-ray and gamma radiation '
                 'differ only in frequency and wavelength, and all travel at c in vacuum.',
                 ['spectrum', 'frequency', 'vacuum']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 15
    {
        'unit': 'Optics',
        'about': 'Uses rays to locate images and waves to explain interference, marking where '
                 'the ray model is a limit of the wave model.',
        'sections': [
            ('physics', '15-1-the-electromagnetic-spectrum'),
            ('physics', '16-2-refraction'),
            ('physics', '16-3-lenses'),
            ('physics', '17-1-understanding-diffraction-and-interference'),
        ],
        'topics': [
            ('Light & the EM Spectrum', [
                ('The Speed of Light and the Index of Refraction',
                 'Light travels at c in vacuum and at c/n in a medium of index n, so a larger '
                 'index means a slower wave and a proportionally shorter wavelength.',
                 ['speed of light', 'index', 'medium']),
                ('Visible Light and Colour',
                 'Visible light spans roughly 400 to 700 nm, and colour is set by frequency, so '
                 'light keeps its colour on entering glass even though its wavelength and speed '
                 'change.',
                 ['visible', 'wavelength', 'colour']),
            ]),
            ('Reflection & Refraction', [
                ('The Law of Reflection',
                 'The angle of incidence equals the angle of reflection, both measured from the '
                 'normal, so a plane mirror places the image as far behind the mirror as the '
                 'object is in front.',
                 ['reflection', 'normal', 'mirror']),
                ("Snell's Law",
                 'n₁ sin θ₁ = n₂ sin θ₂ fixes the bending at an interface, so light entering an '
                 'optically denser medium bends toward the normal.',
                 ['snell', 'refraction', 'index']),
                ('Total Internal Reflection',
                 'Total internal reflection needs light going from a denser to a less dense '
                 'medium at an incidence angle above the critical angle sin θ_c = n₂/n₁, which '
                 'is how optical fibres guide light.',
                 ['total internal reflection', 'critical angle', 'fibre optics']),
            ]),
            ('Mirrors & Lenses', [
                ('The Thin Lens and Mirror Equation',
                 'The equation 1/f = 1/d_o + 1/d_i locates an image, and a positive image '
                 'distance means a real image that can be caught on a screen.',
                 ['thin lens', 'image distance', 'focal length']),
                ('Magnification',
                 'Magnification is m = −d_i/d_o, so a negative value means an inverted image and '
                 'a magnitude above one means an enlarged one.',
                 ['magnification', 'inverted', 'image size']),
                ('Converging and Diverging Elements',
                 'A converging lens or concave mirror has positive focal length and can form '
                 'real images, while a diverging element has negative focal length and forms '
                 'only virtual, upright, reduced images.',
                 ['converging', 'diverging', 'focal point']),
            ]),
            ('Wave Optics', [
                ("Young's Double-Slit Interference",
                 'Two slits separated by d give bright fringes where d sin θ = mλ, so the fringe '
                 'spacing grows with wavelength and with the distance to the screen.',
                 ['double slit', 'fringes', 'path difference']),
                ('Single-Slit Diffraction',
                 'A slit of width a gives minima at a sin θ = mλ, and its central maximum is '
                 'twice as wide as each side maximum.',
                 ['single slit', 'diffraction', 'minima']),
                ('Thin-Film Interference',
                 'A thin film shows constructive or destructive interference according to the '
                 'path difference 2nt, together with any half-wavelength phase shift at the '
                 'boundary.',
                 ['thin film', 'path difference', 'phase shift']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 16
    {
        'unit': 'Modern Physics',
        'about': 'Shows where the classical model breaks down: at speed c, at the scale of the '
                 'atom, and inside the nucleus.',
        'sections': [
            ('physics', '10-1-postulates-of-special-relativity'),
            ('physics', '21-2-einstein-and-the-photoelectric-effect'),
            ('physics', '22-1-the-structure-of-the-atom'),
            ('physics', '22-3-half-life-and-radiometric-dating'),
        ],
        'topics': [
            ('Special Relativity (Intro)', [
                ('The Postulates of Special Relativity',
                 "Physics is the same in every inertial frame and light's vacuum speed is the "
                 'same for every observer, which forces space and time intervals to depend on '
                 'the frame.',
                 ['relativity', 'postulates', 'inertial frame']),
                ('Time Dilation and Length Contraction',
                 'A clock moving relative to an observer runs slow by the factor '
                 'γ = 1/√(1 − v²/c²), and a moving object is measured shorter along its motion '
                 'by the same factor.',
                 ['time dilation', 'length contraction', 'lorentz factor']),
            ]),
            ('Quantum Nature of Light', [
                ('The Photon and Quantised Energy',
                 'Light exchanges energy in photons of energy hf, so an ultraviolet photon '
                 'carries more energy than an infrared one whatever the beam intensity.',
                 ['photon', 'planck', 'quantum']),
                ('The Photoelectric Effect',
                 'Electrons are ejected only when the photon energy exceeds the work function, '
                 'and the maximum kinetic energy is hf − φ, independent of intensity.',
                 ['photoelectric', 'work function', 'threshold']),
                ('Wave-Particle Duality and the de Broglie Wavelength',
                 'Every particle has wavelength λ = h/p, which is measurable for electrons but '
                 'negligible for a thrown ball.',
                 ['de broglie', 'duality', 'matter wave']),
            ]),
            ('Atomic Models & Spectra', [
                ('The Bohr Model of the Atom',
                 'Electrons occupy discrete levels, and a photon carries exactly the level '
                 'difference when an electron drops, which reproduces the hydrogen line '
                 'spectrum.',
                 ['bohr', 'energy levels', 'hydrogen']),
                ('Atomic Spectra and Element Identification',
                 'Each element emits a unique set of lines because its level spacings are '
                 'unique, which is how spectroscopy reads the composition of distant stars.',
                 ['emission spectrum', 'absorption', 'element']),
                ("Heisenberg's Uncertainty Principle",
                 'Position and momentum cannot both be sharp, because Δx Δp ≥ ħ/2 bounds the '
                 'product of their uncertainties from below.',
                 ['uncertainty principle', 'heisenberg', 'bound']),
            ]),
            ('Nuclear Physics & Radioactivity', [
                ('Nuclear Structure and the Strong Force',
                 'A nucleus of Z protons and N neutrons is bound by the short-ranged strong '
                 'force, which must beat the Coulomb repulsion that grows with Z.',
                 ['nucleus', 'strong force', 'nucleon']),
                ('Alpha, Beta and Gamma Decay',
                 'Alpha decay removes two protons and two neutrons, beta decay turns a neutron '
                 'into a proton, and gamma emission carries away energy without changing Z or '
                 'A.',
                 ['alpha decay', 'beta decay', 'gamma']),
                ('Half-Life and Activity',
                 'Half-life is the time for half the nuclei to decay, so after n half-lives the '
                 'fraction remaining is 2⁻ⁿ and the activity has fallen by the same factor.',
                 ['half-life', 'decay', 'activity']),
            ]),
        ],
    },
]
