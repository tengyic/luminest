"""AP Chemistry outline, in the shape ``scripts/course_pipeline.py`` expects.

The scope and sequence below reproduces the College Board's nine-unit AP Chemistry
framework: the 91 framework bullets appear verbatim as topics, under their published
unit names, with the published exam weightings in mind. The concepts inside each topic
are written here -- they are original teaching statements, not framework language, and
each carries the condition under which its claim holds.

Grain: one topic per framework bullet, one or two concepts per topic, so a topic is the
lesson an exam question is written from and a concept is the idea inside it. Ninety-one
topics and 104 concepts is deliberately deeper than the general chemistry course in
``chemistry.py``, which groups many bullets into a single lesson.

Textbook alignment. Every slug in ``sections`` was read from OpenStax's own table of
contents with ``scripts/probe_sections.py`` and is re-fetched through the licence gate by
``course_pipeline.py verify``, so none is guessed.

* ``chemistry`` (1e, CC BY 4.0) is the spine and anchors eight of the nine units.
* ``chemistry-atoms-first`` (1e, CC BY 4.0) is a supplement. It is the anchor for unit 1's
  electron-configuration topic because that edition teaches the atom before bonding, and
  its chapter numbering differs from the spine's.
* ``chemistry-2e`` reports CC BY-NC-SA 4.0 and is therefore link-only: named in the
  alignment metadata as a study reference, never stored or quoted, never an anchor.

One gap is declared rather than papered over. Unit 3's four anchors carry its
intermolecular, gas and solution topics, and the solubility topic is anchored by 11-3
with its quantitative treatment continued at 15-1 in unit 7. The spectroscopy and photon
topics (framework 3.11-3.12) and the Beer-Lambert law (3.13) have no dedicated section in
the first edition -- the Beer-Lambert treatment appears only in the NC second edition --
so no anchor is claimed for them and they are taught from the unit's own photon
discussion.

The pack is generated: ``ap_chemistry.json`` is rebuilt by the pipeline from this module
and must never be hand-edited.
"""

from __future__ import annotations

ID = 'ap_chemistry'
TITLE = 'AP Chemistry'
SUBJECT = 'Chemistry'
SUBJECT_KIND = 'science'
EXPECTED_WEEKS = 34
COURSE_LINE = 'AP Chemistry - Structure, Equilibrium and Energy'
DESCRIPTION = (
    'A college-level chemistry course organised around the nine AP units: atomic '
    'structure and properties, compound structure, the properties of substances and '
    'mixtures, chemical reactions, kinetics, thermochemistry, equilibrium, acids and '
    'bases, and thermodynamics with electrochemistry. Each unit works from the '
    'particulate, symbolic and graphical representations an AP exam question moves '
    'between, and every quantitative claim is tied to the condition under which it holds.')

TEXTBOOK = {
    'spine': 'OpenStax Chemistry (1e, CC BY 4.0)',
    'supplements': ['OpenStax Chemistry: Atoms First (1e, CC BY 4.0)'],
    'link_only_note': ('OpenStax Chemistry 2e reports CC BY-NC-SA 4.0 and is carried as a '
                       'link-only study reference: never stored, quoted or used as an '
                       'anchor.'),
}

UNITS = [
    {
        'unit': 'Atomic Structure and Properties',
        'about': ('The quantitative atom: counting particles with the mole, reading mass '
                  'spectra and photoelectron spectra, and turning electron configuration '
                  'into the periodic trends the rest of the course uses.'),
        'sections': [
            ('chemistry', '3-1-formula-mass-and-the-mole-concept'),
            ('chemistry', '2-3-atomic-structure-and-symbolism'),
            ('chemistry-atoms-first', '3-4-electronic-structure-of-atoms-electron-configurations'),
            ('chemistry', '6-5-periodic-variations-in-element-properties'),
        ],
        'topics': [
            ('Moles and Molar Mass', [
                ('The Mole and Molar Mass',
                 'One mole contains 6.022 x 10^23 entities, and the molar mass in grams '
                 'per mole is numerically equal to the average atomic or formula mass in '
                 'u, so a measured mass becomes a particle count through one ratio.',
                 ['mole', 'molar mass', 'avogadro']),
            ]),
            ('Mass Spectra of Elements', [
                ('Reading a Mass Spectrum',
                 'Each peak of a mass spectrum sits at the mass of a single isotope and its '
                 'relative height is that isotope fraction, so the peak pattern gives the '
                 'element isotope composition without any chemical separation.',
                 ['mass spectrum', 'isotope', 'abundance']),
                ('Average Atomic Mass from Isotope Abundances',
                 'The average atomic mass is the sum of each isotope mass times its '
                 'fractional abundance, so an element whose heaviest isotope dominates has '
                 'a tabulated mass close to that isotope and never outside the isotope '
                 'range.',
                 ['atomic mass', 'weighted average', 'isotope']),
            ]),
            ('Elemental Composition of Pure Substances', [
                ('Percent Composition from a Formula',
                 'Percent composition is the total mass of one element in a mole of the '
                 'compound divided by the molar mass, so for a pure compound it is fixed '
                 'by the formula and independent of sample size.',
                 ['percent composition', 'mass fraction', 'formula']),
            ]),
            ('Composition of Mixtures', [
                ('Mass Percent of a Component in a Mixture',
                 'A mixture mass percent is the mass of one component divided by the total '
                 'mixture mass, and unlike percent composition it varies between samples '
                 'because a mixture carries no fixed formula.',
                 ['mass percent', 'mixture', 'composition']),
            ]),
            ('Atomic Structure and Electron Configuration', [
                ("Coulomb's Law and Effective Nuclear Charge",
                 "Coulomb's law makes the nucleus-electron attraction grow with the "
                 'product of the charges and fall with the square of the separation, and '
                 'because inner electrons shield incompletely the effective nuclear charge '
                 'still rises left to right across a period.',
                 ['coulomb', 'effective nuclear charge', 'shielding']),
                ('Orbital Filling and Electron Configuration',
                 'Electrons occupy the lowest-energy orbital available, filling 4s before '
                 '3d and leaving degenerate p orbitals singly occupied with parallel spins '
                 "before any pairing, which is why a configuration predicts unpaired "
                 'electrons and paramagnetism.',
                 ['electron configuration', 'aufbau', "hund's rule"]),
            ]),
            ('Photoelectron Spectroscopy', [
                ('Photoelectron Spectra and Subshell Energies',
                 'Each photoelectron peak gives the binding energy of one subshell as the '
                 'photon energy minus the ejected electron kinetic energy, and its area is '
                 'proportional to the number of electrons in that subshell.',
                 ['photoelectron', 'binding energy', 'subshell']),
            ]),
            ('Periodic Trends', [
                ('Radius and Ionization Energy Trends',
                 'Atomic radius falls across a period as effective nuclear charge rises and '
                 'grows down a group as shells are added, and first ionization energy '
                 'follows the opposite pattern apart from two dips: group 13 loses a lone p '
                 'electron from a higher sublevel and group 16 loses one electron of a '
                 'paired set.',
                 ['atomic radius', 'ionization energy', 'trend']),
            ]),
            ('Valence Electrons and Ionic Compounds', [
                ('Valence Electrons and Main-Group Ion Charges',
                 'Main-group atoms gain or lose electrons to reach a noble-gas '
                 'configuration, so group 1 and 2 metals form 1+ and 2+ cations while '
                 'group 16 and 17 nonmetals form 2- and 1- anions.',
                 ['valence electrons', 'ion charge', 'octet']),
            ]),
        ],
    },
    {
        'unit': 'Compound Structure and Properties',
        'about': ('How atoms are held together and how that holding shapes a particle: the '
                  'bond-type continuum, the potential-energy well of a bond, the lattices of '
                  'ionic solids and metals, and the Lewis, VSEPR and hybrid-orbital models '
                  'that predict geometry.'),
        'sections': [
            ('chemistry', '7-1-ionic-bonding'),
            ('chemistry', '7-4-formal-charges-and-resonance'),
            ('chemistry', '7-6-molecular-structure-and-polarity'),
            ('chemistry', '8-2-hybrid-atomic-orbitals'),
        ],
        'topics': [
            ('Types of Chemical Bonds', [
                ('The Ionic-Covalent Continuum',
                 'A bond is largely ionic once the electronegativity difference exceeds '
                 'roughly 1.7 and largely covalent when the difference is small, so the two '
                 'labels mark the ends of one continuum rather than two kinds of bond.',
                 ['electronegativity', 'ionic bond', 'covalent bond']),
                ('Bond Polarity and Molecular Dipole Moments',
                 'A polar bond carries a dipole towards its more electronegative atom, but a '
                 'molecule has a net dipole only when symmetry leaves the bond dipoles '
                 'unable to cancel, which is why carbon dioxide is nonpolar.',
                 ['dipole moment', 'polarity', 'symmetry']),
            ]),
            ('Intramolecular Force and Potential Energy', [
                ('Potential Energy Curves for Covalent Bonds',
                 'A bond potential energy falls to a minimum at the equilibrium bond length '
                 'and climbs steeply at shorter distances as the nuclei repel, so the depth '
                 'of that well measures bond strength and, between the same two elements, a '
                 'shorter equilibrium distance belongs to the deeper well.',
                 ['potential energy', 'bond length', 'bond energy']),
            ]),
            ('Structure of Ionic Solids', [
                ('Ionic Lattice Structure and Coordination',
                 'An ionic solid is a three-dimensional lattice in which every ion is '
                 'surrounded by counter-ions, and its lattice energy grows with the product '
                 'of the ionic charges and shrinks as the ions become larger.',
                 ['ionic lattice', 'coordination number', 'lattice energy']),
            ]),
            ('Structure of Metals and Alloys', [
                ('Metallic Bonding and Alloys',
                 'Metal cations are held by a delocalised sea of valence electrons, which '
                 'explains conductivity and malleability, and an alloy distorts that lattice '
                 'by substituting or inserting atoms of a different size.',
                 ['metallic bond', 'delocalized electrons', 'alloy']),
            ]),
            ('Lewis Diagrams', [
                ('Drawing Lewis Diagrams',
                 'A Lewis diagram is built by counting all valence electrons, bonding the '
                 'skeleton with single bonds, completing outer octets, then placing any '
                 'remainder on the central atom or forming multiple bonds until it reaches '
                 'an octet.',
                 ['lewis diagram', 'octet', 'lone pair']),
            ]),
            ('Resonance and Formal Charge', [
                ('Formal Charge and Resonance Hybrids',
                 'Formal charge is the valence-electron count minus the electrons an atom '
                 'owns in the diagram, and the preferred structure minimises it, while '
                 'forms that differ only in electron placement are resonance contributors to '
                 'one delocalised hybrid.',
                 ['formal charge', 'resonance', 'delocalization']),
            ]),
            ('VSEPR and Hybridization', [
                ('Electron-Domain Geometry and Molecular Shape',
                 'Electron domains spread to the arrangement that maximises their separation, '
                 'and a lone pair occupies more angular space than a bonding pair, so a '
                 'tetrahedral domain set becomes trigonal pyramidal or bent when lone pairs '
                 'are present.',
                 ['vsepr', 'electron domain', 'bond angle']),
                ('Hybridization and Sigma versus Pi Bonds',
                 'Mixing one s with one, two or three p orbitals gives sp, sp2 or sp3 hybrids '
                 'whose directions match the observed linear, trigonal planar or tetrahedral '
                 'angles, and the untouched p orbitals form the pi bond of a double or '
                 'triple bond.',
                 ['hybridization', 'sigma bond', 'pi bond']),
            ]),
        ],
    },
    {
        'unit': 'Properties of Substances and Mixtures',
        'about': ('The heaviest unit on the exam: what holds particles to each other, how '
                  'those forces set the behaviour of solids, liquids, gases and solutions, '
                  'and how light probes a sample through absorbance.'),
        'sections': [
            ('chemistry', '10-1-intermolecular-forces'),
            ('chemistry', '9-2-relating-pressure-volume-amount-and-temperature-the-ideal-gas-law'),
            ('chemistry', '9-6-non-ideal-gas-behavior'),
            ('chemistry', '11-3-solubility'),
        ],
        'topics': [
            ('Intermolecular and Interparticle Forces', [
                ('London Dispersion Forces and Polarizability',
                 'Every pair of particles attracts through instantaneous dipoles, and the '
                 'force strengthens with polarizability and contact area, which is why the '
                 'halogens boil at higher temperatures down the group.',
                 ['dispersion', 'polarizability', 'boiling point']),
                ('Hydrogen Bonding and Dipole-Dipole Forces',
                 'A hydrogen bond is the attraction between hydrogen covalently bound to N, '
                 'O or F and a lone pair on another such atom, strong enough to give water '
                 'an unusually high boiling point and enthalpy of vaporisation.',
                 ['hydrogen bond', 'dipole-dipole', 'boiling point']),
            ]),
            ('Properties of Solids', [
                ('Order in Crystalline and Amorphous Solids',
                 'A crystalline solid has a repeating long-range lattice and melts at one '
                 'temperature, while an amorphous solid lacks that order and softens over a '
                 'range, so melting behaviour alone distinguishes the two.',
                 ['crystalline', 'amorphous', 'lattice']),
            ]),
            ('Solids, Liquids, and Gases', [
                ('Particulate Structure of the Three States',
                 'Particles of a solid are fixed in place and only vibrate, particles of a '
                 'liquid stay in contact but slide past one another, and particles of a gas '
                 'are far apart and fill their container, so density and compressibility '
                 'follow from the spacing.',
                 ['states of matter', 'particulate', 'compressibility']),
                ('Vapor Pressure and Boiling',
                 'Vapor pressure rises with temperature as a larger fraction of molecules '
                 'gains escape energy, and a liquid boils when that pressure equals the '
                 'external pressure, which is why water boils below 100 degrees Celsius at '
                 'altitude.',
                 ['vapor pressure', 'boiling point', 'altitude']),
            ]),
            ('Ideal Gas Law', [
                ('The Ideal Gas Law',
                 'The equation PV = nRT treats particles as point masses with no attractions, '
                 'so it holds best at low pressure and high temperature and fails when '
                 'particle volume and intermolecular attraction become significant.',
                 ['ideal gas law', 'gas constant', 'assumptions']),
            ]),
            ('Kinetic Molecular Theory', [
                ('Kinetic Molecular Theory and Molecular Speed',
                 'Average kinetic energy depends only on absolute temperature, so at one '
                 'temperature all gases share the same average kinetic energy while their '
                 'root-mean-square speeds differ as the inverse square root of molar mass.',
                 ['kinetic molecular theory', 'kinetic energy', 'rms speed']),
            ]),
            ('Deviation from Ideal Gas Law', [
                ('Real Gases Deviate in Both Directions',
                 'For most gases at ordinary temperature, attractions pull the measured '
                 'pressure below the ideal prediction while the particles own volume pushes '
                 'it above, so the compressibility factor falls below one at moderate '
                 'pressure and rises above one at high pressure.',
                 ['real gas', 'compressibility', 'deviation']),
            ]),
            ('Solutions and Mixtures', [
                ('Solutions Compared with Heterogeneous Mixtures',
                 'A solution is a homogeneous mixture whose components are dispersed at the '
                 'particle level and cannot be separated by settling or filtering, while a '
                 'heterogeneous mixture keeps visibly distinct regions that scatter light or '
                 'settle on standing.',
                 ['solution', 'homogeneous', 'mixture']),
            ]),
            ('Representations of Solutions', [
                ('Molarity and Solution Representations',
                 'Molarity is moles of solute per litre of solution, so dissolving one mole '
                 'of a strong electrolyte such as sodium chloride yields two moles of ions, '
                 'and a particulate drawing must show that doubled count.',
                 ['molarity', 'dissociation', 'particulate']),
            ]),
            ('Separation of Solutions and Mixtures', [
                ('Separation by Distillation and Chromatography',
                 'Distillation separates components by boiling point, while chromatography '
                 'separates them by differing affinity for a mobile and a stationary phase, '
                 'so each exploits a physical property rather than a reaction.',
                 ['distillation', 'chromatography', 'separation']),
            ]),
            ('Solubility', [
                ('Solubility as a Saturation Equilibrium',
                 'Solubility is the dissolved concentration in a saturated solution at a '
                 'given temperature, and it is a property of the solute-solvent pair because '
                 'the dissolution equilibrium shifts with temperature and with the solvent.',
                 ['solubility', 'saturated', 'equilibrium']),
            ]),
            ('Spectroscopy and the Electromagnetic Spectrum', [
                ('Spectra Record Absorbed and Emitted Photons',
                 'A spectrum records the wavelengths a sample absorbs or emits, and because '
                 'each transition needs a photon of matching energy, a line position '
                 'identifies the species while a line intensity reports how much of it is '
                 'present.',
                 ['spectroscopy', 'spectrum', 'transition']),
            ]),
            ('Properties of Photons', [
                ('Photon Energy and the Electromagnetic Spectrum',
                 'A photon carries energy equal to h times its frequency, so ultraviolet '
                 'photons carry enough energy to break some bonds, visible photons excite '
                 'valence electrons and infrared photons only excite vibrations, which is '
                 'why the spectral region fixes the kind of interaction.',
                 ['photon', 'frequency', 'electromagnetic spectrum']),
            ]),
            ('Beer-Lambert Law', [
                ('The Beer-Lambert Law',
                 'Absorbance equals molar absorptivity times path length times concentration, '
                 'so a calibration curve at one wavelength converts an absorbance reading '
                 'into an unknown concentration, provided the absorbing species and the '
                 'instrument settings are unchanged.',
                 ['beer-lambert', 'absorbance', 'calibration']),
            ]),
        ],
    },
    {
        'unit': 'Chemical Reactions',
        'about': ('Reading a reaction correctly before calculating with it: what counts as '
                  'a reaction, the three representations of a reaction in solution, the '
                  'classes a reaction falls into, and the stoichiometry and titration '
                  'arithmetic that follow from a balanced equation.'),
        'sections': [
            ('chemistry', '4-1-writing-and-balancing-chemical-equations'),
            ('chemistry', '4-2-classifying-chemical-reactions'),
            ('chemistry', '4-3-reaction-stoichiometry'),
            ('chemistry', '4-5-quantitative-chemical-analysis'),
        ],
        'topics': [
            ('Introduction for Reactions', [
                ('What Counts as a Chemical Reaction',
                 'A chemical reaction rearranges atoms so that existing bonds break and new '
                 'ones form, which is why the same atoms appear on both sides of a balanced '
                 'equation in different partnerships.',
                 ['chemical reaction', 'bond breaking', 'rearrangement']),
            ]),
            ('Net Ionic Equations', [
                ('Writing Net Ionic Equations',
                 'A net ionic equation keeps only the species that change, so ions appearing '
                 'identically on both sides are cancelled as spectators and every strong '
                 'electrolyte is written as its separated ions.',
                 ['net ionic', 'spectator ion', 'dissociation']),
            ]),
            ('Representations of Reactions', [
                ('Representing a Reaction at the Particle Level',
                 'The balanced equation, the particulate drawing and the net ionic equation '
                 'describe one change at three levels, and any acceptable representation '
                 'conserves both atoms and charge.',
                 ['particulate', 'conservation', 'representation']),
            ]),
            ('Physical and Chemical Changes', [
                ('Distinguishing Physical from Chemical Change',
                 'A physical change alters state or form without altering composition, while '
                 'a chemical change produces new substances and is recognised by a colour '
                 'change, gas evolution, precipitate or temperature change.',
                 ['physical change', 'chemical change', 'evidence']),
            ]),
            ('Stoichiometry', [
                ('Mole Ratios and the Limiting Reactant',
                 'Coefficients give the mole ratio linking any two species, and the limiting '
                 'reactant is the one whose stoichiometric requirement runs out first, so it '
                 'sets the maximum product while the excess reactant remains.',
                 ['mole ratio', 'limiting reactant', 'theoretical yield']),
                ('Percent Yield from the Limiting Reactant',
                 'Percent yield is the actual product mass divided by the theoretical mass '
                 'from the limiting reactant, so a result above 100 percent signals an '
                 'impure or wet product rather than a better reaction.',
                 ['percent yield', 'theoretical yield', 'purity']),
            ]),
            ('Introduction to Titration', [
                ('Titration and the Equivalence Point',
                 'A titration reaches equivalence when the added titrant moles match the '
                 'stoichiometric requirement of the analyte, a point computed from the '
                 'balanced equation that need not sit at neutral pH.',
                 ['titration', 'equivalence point', 'stoichiometry']),
            ]),
            ('Types of Chemical Reactions', [
                ('Precipitation, Acid-Base and Redox Classes',
                 'A precipitation reaction forms an insoluble product from soluble ions, an '
                 'acid-base reaction transfers a proton and a redox reaction changes '
                 'oxidation numbers, so the class is identified by what is exchanged.',
                 ['precipitation', 'neutralization', 'classification']),
            ]),
            ('Introduction to Acid-Base Reactions', [
                ('Proton Transfer in Acid-Base Reactions',
                 'In an acid-base reaction a proton moves from the acid to the base, giving '
                 'the conjugate base of the acid and the conjugate acid of the base, and the '
                 'equilibrium favours the weaker acid and weaker base.',
                 ['proton transfer', 'conjugate', 'acid-base']),
            ]),
            ('Oxidation-Reduction (Redox) Reactions', [
                ('Assigning Oxidation Numbers and Balancing Redox',
                 'Oxidation numbers follow fixed rules with oxygen at -2 and hydrogen at +1, '
                 'and a redox equation balances once the electrons lost by oxidation equal '
                 'the electrons gained by reduction.',
                 ['oxidation number', 'redox', 'half-reaction']),
            ]),
        ],
    },
    {
        'unit': 'Kinetics',
        'about': ('How fast a reaction goes: rate as a measured quantity, the experimental '
                  'rate law, the collision and energy-profile explanations, and the mechanism '
                  'that the rate law exposes.'),
        'sections': [
            ('chemistry', '12-1-chemical-reaction-rates'),
            ('chemistry', '12-3-rate-laws'),
            ('chemistry', '12-5-collision-theory'),
            ('chemistry', '12-6-reaction-mechanisms'),
        ],
        'topics': [
            ('Reaction Rates', [
                ('Average and Instantaneous Rate',
                 'Average rate is a concentration change over an interval while instantaneous '
                 'rate is the tangent slope at one moment, so the two agree only when the '
                 'rate is constant.',
                 ['average rate', 'instantaneous rate', 'slope']),
                ('Rate Normalised by Stoichiometric Coefficients',
                 'Dividing each species concentration change by its coefficient gives a '
                 'single reaction rate, so a reactant consumed twice as fast as another still '
                 'yields the same rate value.',
                 ['reaction rate', 'coefficient', 'normalization']),
            ]),
            ('Introduction to Rate Law', [
                ('Determining a Rate Law Experimentally',
                 'A rate law is determined experimentally, not from the balanced equation, '
                 'because the exponents reflect the mechanism slow step, so the orders come '
                 'from varying one concentration at a time and comparing initial rates.',
                 ['rate law', 'reaction order', 'initial rates']),
                ('Reaction Orders and the Units of k',
                 'The exponents sum to the overall order, and the units of the rate constant '
                 'follow from that order, being per second for first order and per molar per '
                 'second for second order.',
                 ['reaction order', 'rate constant', 'units']),
            ]),
            ('Concentration Changes Over Time', [
                ('Integrated Rate Laws and Half-Life',
                 'An integrated rate law gives concentration as a function of time, and a '
                 'first-order reaction has a half-life of 0.693 divided by the rate constant '
                 'that does not depend on the starting concentration.',
                 ['integrated rate law', 'half-life', 'first order']),
            ]),
            ('Elementary Reactions', [
                ('Molecularity of an Elementary Step',
                 'An elementary step is classified by its molecularity as unimolecular, '
                 'bimolecular or termolecular, and because the step happens as written its '
                 'rate law follows from that molecularity rather than from experiment.',
                 ['elementary step', 'molecularity', 'termolecular']),
            ]),
            ('Collision Model', [
                ('Collision Model and Activation Energy',
                 'A collision reacts only if the molecules arrive with at least the '
                 'activation energy and the right orientation, so heating raises the rate '
                 'mainly by raising the fraction of collisions that clear the barrier rather '
                 'than by raising the collision frequency.',
                 ['collision model', 'activation energy', 'orientation']),
            ]),
            ('Reaction Energy Profile', [
                ('Reaction Energy Profile and the Transition State',
                 'A reaction energy profile plots potential energy along the reaction '
                 'coordinate, its peak is the transition state, the reactant-to-peak gap is '
                 'the activation energy and the reactant-to-product gap is the enthalpy '
                 'change.',
                 ['energy profile', 'transition state', 'activation energy']),
            ]),
            ('Introduction to Reaction Mechanisms', [
                ('Mechanism Steps and the Slow Step',
                 'A mechanism is a series of elementary steps that sum to the overall '
                 'equation, and the slowest step controls the rate, so a rate law can be '
                 'written from the reactants of that step alone.',
                 ['mechanism', 'rate-determining step', 'elementary step']),
            ]),
            ('Reaction Mechanism and Rate Law', [
                ('Rate Law Derived from the Slow Step',
                 'The rate law predicted by a mechanism uses the reactants of its slow step '
                 "with that step's coefficients as exponents, so a predicted law that "
                 'contradicts the measured one rules the mechanism out.',
                 ['predicted rate law', 'slow step', 'mechanism test']),
            ]),
            ('Pre-Equilibrium Approximation', [
                ('Pre-Equilibrium Approximation',
                 'When a fast reversible step precedes the slow step, solving the fast step '
                 'for the intermediate concentration and substituting it into the slow rate '
                 'gives a rate law containing only species actually present.',
                 ['pre-equilibrium', 'intermediate', 'approximation']),
            ]),
            ('Multistep Reaction Energy Profile', [
                ('Mechanisms on an Energy Diagram',
                 'A multistep mechanism shows one peak per transition state on its energy '
                 'profile, and the highest peak belongs to the slow step, so the diagram '
                 'reveals which step gates the rate.',
                 ['multistep', 'energy diagram', 'intermediate']),
            ]),
            ('Catalysis', [
                ('Catalysis and the Lower-Energy Pathway',
                 'A catalyst supplies an alternative pathway of lower activation energy '
                 'without being consumed, so it raises the rate in both directions and '
                 'leaves the equilibrium constant and the enthalpy change unchanged.',
                 ['catalyst', 'activation energy', 'equilibrium']),
            ]),
        ],
    },
    {
        'unit': 'Thermochemistry',
        'about': ('Energy bookkeeping for chemical change: the sign conventions, '
                  'calorimetric measurement, the enthalpy of phase change, and the routes to '
                  "a reaction enthalpy -- bonds, formation enthalpies and Hess's law."),
        'sections': [
            ('chemistry', '5-1-energy-basics'),
            ('chemistry', '5-2-calorimetry'),
            ('chemistry', '5-3-enthalpy'),
            ('chemistry', '10-3-phase-transitions'),
        ],
        'topics': [
            ('Endothermic and Exothermic Processes', [
                ('Sign Conventions for Heat Flow',
                 'An exothermic process releases heat and carries a negative enthalpy change '
                 'because the system loses energy, while an endothermic process absorbs heat '
                 'and carries a positive one, both at constant pressure.',
                 ['exothermic', 'endothermic', 'enthalpy sign']),
            ]),
            ('Energy Diagrams', [
                ('Energy Diagrams and Enthalpy Change',
                 'An energy diagram places the enthalpy of reactants and products on one '
                 'vertical scale, so the difference is the enthalpy change and the barrier '
                 'above the reactants is the activation energy.',
                 ['energy diagram', 'enthalpy', 'activation energy']),
            ]),
            ('Heat Transfer and Thermal Equilibrium', [
                ('Thermal Equilibrium and the Direction of Heat Flow',
                 'Heat flows spontaneously from the hotter body to the colder one until both '
                 'reach the same temperature, so at thermal equilibrium the net transfer is '
                 'zero even though molecular collisions continue.',
                 ['thermal equilibrium', 'heat flow', 'temperature']),
            ]),
            ('Heat Capacity and Calorimetry', [
                ('Specific Heat and Heat Capacity',
                 'Specific heat is the energy needed to raise one gram of a substance by one '
                 'kelvin, and the value 4.18 joules per gram kelvin for liquid water makes it '
                 'a slow-warming reservoir that moderates climate and body temperature.',
                 ['specific heat', 'heat capacity', 'water']),
                ('Coffee-Cup and Bomb Calorimetry',
                 'Calorimetry finds the heat exchanged as mass times specific heat times the '
                 'temperature change, with a coffee-cup calorimeter measuring at constant '
                 'pressure so the heat equals the enthalpy change and a bomb calorimeter at '
                 'constant volume so it equals the internal energy change.',
                 ['calorimetry', 'bomb calorimeter', 'heat']),
            ]),
            ('Energy of Phase Changes', [
                ('Enthalpy of Phase Change and Heating Curves',
                 'Melting and vaporisation absorb energy without raising the temperature, so '
                 'a heating curve shows flat plateaus whose lengths are set by the enthalpy '
                 'of fusion or vaporisation and by the sample mass.',
                 ['phase change', 'enthalpy of fusion', 'heating curve']),
            ]),
            ('Introduction to Enthalpy of Reaction', [
                ('Why Reaction Heats Are Tabulated as Enthalpies',
                 'At constant pressure the heat exchanged by a reaction equals its enthalpy '
                 'change, which is why reactions run in open vessels are tabulated as '
                 'enthalpies rather than as internal energy changes.',
                 ['enthalpy change', 'constant pressure', 'heat']),
            ]),
            ('Bond Enthalpies', [
                ('Bond Enthalpies and Reaction Enthalpy',
                 'A reaction enthalpy can be estimated as the bond enthalpies broken minus '
                 'those formed, a route that works best for gas-phase reactions because bond '
                 'enthalpies are averages over many compounds.',
                 ['bond enthalpy', 'gas phase', 'estimate']),
            ]),
            ('Enthalpy of Formation', [
                ('Formation Enthalpy and the Zero Convention',
                 'The standard enthalpy of formation is the enthalpy change when one mole of '
                 'a compound forms from its elements in their standard states, so an element '
                 'in its standard state has a formation enthalpy of exactly zero.',
                 ['formation enthalpy', 'standard state', 'elements']),
            ]),
            ("Hess's Law", [
                ("Hess's Law and Path Independence",
                 'Because enthalpy is a state function, a reaction enthalpy is the same '
                 'whatever sequence of steps connects reactants to products, so it can be '
                 'assembled from reactions that are easier to measure.',
                 ['hess law', 'state function', 'path']),
            ]),
        ],
    },
    {
        'unit': 'Equilibrium',
        'about': ('How far a reaction goes: dynamic equilibrium, the equilibrium constant '
                  'and its arithmetic, the quotient that predicts direction, the response to '
                  'a disturbance, and the solubility equilibrium that closes the unit.'),
        'sections': [
            ('chemistry', '13-1-chemical-equilibria'),
            ('chemistry', '13-2-equilibrium-constants'),
            ('chemistry', '13-3-shifting-equilibria-le-chateliers-principle'),
            ('chemistry', '15-1-precipitation-and-dissolution'),
        ],
        'topics': [
            ('Introduction to Equilibrium', [
                ('Equal Forward and Reverse Rates',
                 'At equilibrium the forward and reverse reactions run at equal rates, so '
                 'concentrations stop changing although both reactions continue, and the '
                 'state is reached from either direction.',
                 ['dynamic equilibrium', 'equal rates', 'reversible']),
            ]),
            ('Direction of Reversible Reactions', [
                ('Direction of Reversible Reactions',
                 'A reversible reaction proceeds in the direction that lowers the system free '
                 'energy until the reaction quotient equals the equilibrium constant, after '
                 'which no net change is observed.',
                 ['reversible', 'net change', 'direction']),
            ]),
            ('Reaction Quotient and Equilibrium Constant', [
                ('Writing the Equilibrium Expression',
                 'The equilibrium constant is the product of product concentrations raised to '
                 'their coefficients divided by the same expression for reactants, with pure '
                 'solids and liquids omitted because their concentrations are constant.',
                 ['equilibrium constant', 'expression', 'heterogeneous']),
                ('Comparing Q with K to Predict Direction',
                 'The reaction quotient has the form of K but uses current concentrations, so '
                 'Q below K drives the reaction forward, Q above K drives it in reverse and Q '
                 'equal to K means the system is at equilibrium.',
                 ['reaction quotient', 'direction', 'comparison']),
            ]),
            ('Calculating the Equilibrium Constant', [
                ('Calculating K from Equilibrium Data',
                 'Substituting equilibrium concentrations into the expression gives K, '
                 'whereas initial concentrations cannot be substituted unless the system has '
                 'actually reached equilibrium.',
                 ['equilibrium constant', 'calculation', 'equilibrium data']),
            ]),
            ('Magnitude of the Equilibrium Constant', [
                ('Magnitude of K and the Extent of Reaction',
                 'A K far above one means the reaction has run almost to completion, a K far '
                 'below one means hardly any product forms, and a K near one leaves '
                 'comparable amounts of both sides at equilibrium.',
                 ['magnitude', 'extent', 'equilibrium position']),
            ]),
            ('Properties of the Equilibrium Constant', [
                ('Rules for Combining Equilibrium Constants',
                 'Reversing an equation inverts K, multiplying its coefficients raises K to '
                 'that power and adding two equations multiplies their constants, so K is '
                 'meaningful only for the equation as written at that temperature.',
                 ['reciprocal', 'power', 'combined reactions']),
            ]),
            ('Calculating Equilibrium Concentrations', [
                ('ICE Tables and the Small-x Approximation',
                 'An ICE table derives each equilibrium concentration from the initial value '
                 'and the stoichiometric change, and dropping x beside an initial '
                 'concentration is valid only when x stays under about 5 percent of it.',
                 ['ice table', 'approximation', 'change']),
            ]),
            ('Representations of Equilibrium', [
                ('Particulate and Graphical Views of Equilibrium',
                 'At equilibrium a particulate drawing shows reactants and products present '
                 'in unchanging numbers while collisions continue, and a concentration-time '
                 'graph flattens at a nonzero value instead of reaching zero.',
                 ['particulate model', 'graph', 'nonzero concentration']),
            ]),
            ("Introduction to Le Châtelier's Principle", [
                ("Le Chatelier's Response to a Disturbance",
                 'A system at equilibrium shifts to partly offset a change in concentration, '
                 'pressure or temperature, but only a temperature change alters the value of '
                 'K itself.',
                 ['le chatelier', 'stress', 'temperature']),
            ]),
            ("Reaction Quotient and Le Châtelier's Principle", [
                ('Explaining a Shift with the Reaction Quotient',
                 'Adding a reactant or removing a product makes Q smaller than K so the '
                 'forward reaction dominates, and compressing a gas mixture shifts it towards '
                 'the side with fewer gas moles because that direction drives Q below K.',
                 ['reaction quotient', 'shift direction', 'pressure']),
            ]),
            ('Introduction to Solubility Equilibria', [
                ('Ksp and Molar Solubility',
                 'The solubility product is the product of the ion concentrations in a '
                 'saturated solution each raised to its coefficient, so molar solubility '
                 'follows from Ksp through the salt stoichiometry.',
                 ['ksp', 'molar solubility', 'saturated']),
            ]),
            ('Common-Ion Effect', [
                ('The Common-Ion Effect',
                 'Adding an ion the dissolving salt already produces pushes Q above Ksp, so '
                 'solid precipitates until Q returns to Ksp and the salt solubility is lower '
                 'than in pure water.',
                 ['common ion', 'solubility', 'precipitation']),
            ]),
        ],
    },
    {
        'unit': 'Acids and Bases',
        'about': ('Proton transfer treated as equilibrium: the definitions, strong and weak '
                  'acid pH, the Ka and Kb bookkeeping, buffers and their capacity, titration '
                  'curves, and the structural reasons acids differ in strength.'),
        'sections': [
            ('chemistry', '14-1-bronsted-lowry-acids-and-bases'),
            ('chemistry', '14-3-relative-strengths-of-acids-and-bases'),
            ('chemistry', '14-6-buffers'),
            ('chemistry', '14-7-acid-base-titrations'),
        ],
        'topics': [
            ('Introduction to Acids and Bases', [
                ('Bronsted-Lowry and Lewis Definitions',
                 'A Bronsted-Lowry acid donates a proton and a base accepts one, while the '
                 'Lewis definition widens acids to electron-pair acceptors so that a species '
                 'without hydrogen, such as boron trifluoride, still counts as an acid.',
                 ['bronsted-lowry', 'lewis acid', 'proton']),
                ('Conjugate Pairs and Amphiprotic Species',
                 'Every Bronsted-Lowry acid has a conjugate base differing by one proton, and '
                 'a species such as water or the hydrogen carbonate ion can donate or accept '
                 'a proton depending on its partner.',
                 ['conjugate pair', 'amphiprotic', 'proton']),
            ]),
            ('pH and pOH of Strong Acids and Bases', [
                ('pH, pOH and the Water Ion Product',
                 'pH is the negative base-ten logarithm of the hydrogen ion concentration, '
                 'and at 25 degrees Celsius pH plus pOH equals 14 because the ion product of '
                 'water is 1.0 x 10^-14.',
                 ['ph', 'poh', 'kw']),
            ]),
            ('Weak Acid and Base Equilibria', [
                ('Ka, Kb and the Conjugate Relationship',
                 'Ka measures the extent of weak-acid ionisation and Kb the extent for its '
                 'conjugate base, and their product equals the water ion product, so a '
                 'stronger acid always has a weaker conjugate base.',
                 ['ka', 'kb', 'conjugate']),
                ('Solving Weak-Acid Equilibrium Problems',
                 'Combining Ka with an initial concentration and an unknown x gives the '
                 'hydrogen ion concentration, and the shortcut that neglects x fails once x '
                 'exceeds about 5 percent of the initial concentration, which happens for a '
                 'relatively strong weak acid or a very dilute solution.',
                 ['weak acid', 'ka', 'approximation']),
            ]),
            ('Acid-Base Reactions and Buffers', [
                ('Neutralization and Buffer Formation',
                 'Adding a limited amount of strong base to a weak acid converts part of it '
                 'into its conjugate base, so the mixture left behind holds the acid and '
                 'conjugate base pair a buffer requires.',
                 ['neutralization', 'buffer formation', 'conjugate base']),
            ]),
            ('Acid-Base Titrations', [
                ('Titration Curves and the Half-Equivalence Point',
                 'On a weak-acid titration curve the pH at half-equivalence equals the acid '
                 'pKa because acid and conjugate base are then equimolar, and the steepest '
                 'segment of the curve brackets the equivalence point.',
                 ['titration curve', 'half-equivalence', 'pka']),
            ]),
            ('Molecular Structure of Acids and Bases', [
                ('Inductive and Resonance Effects on pKa',
                 'Electron-withdrawing atoms or groups stabilise the conjugate base and lower '
                 'pKa, which is why trichloroacetic acid is far stronger than acetic acid and '
                 'why an oxyacid strengthens as its central atom becomes more '
                 'electronegative.',
                 ['inductive effect', 'pka', 'oxyacid']),
            ]),
            ('pH and pKa', [
                ('Comparing pH with pKa',
                 'When the pH is below an acid pKa the protonated form dominates and when it '
                 'is above the pKa the deprotonated form dominates, so comparing the two '
                 'numbers predicts the charge of the species in solution.',
                 ['ph', 'pka', 'protonation state']),
            ]),
            ('Properties of Buffers', [
                ('How a Buffer Responds to Added Acid or Base',
                 'A buffer neutralises added strong acid with its basic component and added '
                 'strong base with its acidic component, so the pH moves only slightly until '
                 'one member of the pair is used up.',
                 ['buffer action', 'strong acid', 'ph change']),
            ]),
            ('Henderson-Hasselbalch Equation', [
                ('Buffers and the Henderson-Hasselbalch Equation',
                 'A buffer holds a weak acid and its conjugate base in comparable amounts, '
                 'and its pH equals the acid pKa plus the logarithm of the base-to-acid '
                 'ratio, so the ratio rather than the absolute amounts sets the pH.',
                 ['buffer', 'henderson-hasselbalch', 'pka']),
            ]),
            ('Buffer Capacity', [
                ('Buffer Capacity and Effective Range',
                 'A buffer works within roughly one pH unit of its acid pKa, and its capacity '
                 'grows with the absolute concentrations of the pair, so a buffer of correct '
                 'ratio but low concentration fails on adding strong acid.',
                 ['buffer capacity', 'buffer range', 'concentration']),
            ]),
            ('pH and Solubility', [
                ('pH-Dependent Solubility of Salts',
                 'The solubility of a salt whose anion is the conjugate base of a weak acid '
                 'rises in acidic solution, because protonating the anion removes it and '
                 'pulls the dissolution equilibrium towards dissolving.',
                 ['ph', 'solubility', 'protonation']),
            ]),
        ],
    },
    {
        'unit': 'Thermodynamics and Electrochemistry',
        'about': ('Direction and usefulness of change: entropy and free energy as the '
                  'favorability criterion, the competition between thermodynamic and kinetic '
                  'products, and the conversion of a redox reaction into electrical work.'),
        'sections': [
            ('chemistry', '16-2-entropy'),
            ('chemistry', '16-4-free-energy'),
            ('chemistry', '17-2-galvanic-cells'),
            ('chemistry', '17-7-electrolysis'),
        ],
        'topics': [
            ('Introduction to Entropy', [
                ('Entropy and Microstates',
                 'Entropy measures the number of microstates available to a system, so a '
                 'process that spreads matter or energy over more arrangements has a positive '
                 'entropy change, as when a solid melts or a gas expands into a vacuum.',
                 ['entropy', 'microstates', 'dispersal']),
            ]),
            ('Absolute Entropy and Entropy Change', [
                ('Absolute Entropy and the Third Law',
                 'The third law sets the entropy of a perfect crystal at absolute zero to '
                 'zero, so tabulated absolute entropies let a reaction entropy change be taken '
                 'as products minus reactants without any arbitrary reference point.',
                 ['third law', 'absolute entropy', 'standard entropy']),
            ]),
            ('Gibbs Free Energy and Thermodynamic Favorability', [
                ('Gibbs Free Energy as the Favorability Criterion',
                 'The free energy change equals the enthalpy change minus temperature times '
                 'the entropy change, and at constant temperature and pressure a negative '
                 'value means the forward process is thermodynamically favoured while zero '
                 'means equilibrium.',
                 ['gibbs free energy', 'favorability', 'criterion']),
                ('Temperature Dependence of Favorability',
                 'An endothermic reaction with a positive entropy change becomes favourable '
                 'only above the temperature at which T times the entropy change exceeds the '
                 'enthalpy change, so the sign pair decides whether a reaction is always, '
                 'never or sometimes favourable.',
                 ['temperature', 'enthalpy', 'entropy']),
            ]),
            ('Thermodynamic and Kinetic Control', [
                ('Thermodynamic versus Kinetic Control',
                 'A reaction under thermodynamic control yields the more stable product, '
                 'while under kinetic control the faster-forming product dominates, so the '
                 'product distribution depends on temperature and on how long the reaction '
                 'is allowed to run.',
                 ['thermodynamic control', 'kinetic control', 'product distribution']),
            ]),
            ('Free Energy and Equilibrium', [
                ('Free Energy and the Equilibrium Constant',
                 'The standard free energy change equals minus RT times the natural logarithm '
                 'of K, so a large negative value corresponds to a large equilibrium '
                 'constant and a reaction that runs nearly to completion.',
                 ['free energy', 'equilibrium constant', 'standard']),
            ]),
            ('Free Energy of Dissolution', [
                ('Free Energy of Dissolution',
                 'Dissolution must supply the lattice enthalpy and is repaid by the hydration '
                 'enthalpy, and the sum corrected by the entropy gain of dispersing the ions '
                 'decides whether the salt dissolves at all.',
                 ['dissolution', 'lattice enthalpy', 'hydration']),
            ]),
            ('Coupled Reactions', [
                ('Coupled Reactions',
                 'A thermodynamically unfavourable reaction can be driven by coupling it to a '
                 'favourable one whose free energy release exceeds the cost, as ATP '
                 'hydrolysis does for the reactions of a cell.',
                 ['coupled reaction', 'free energy', 'atp']),
            ]),
            ('Galvanic (Voltaic) and Electrolytic Cells', [
                ('Anode, Cathode and Electron Flow',
                 'In any electrochemical cell oxidation occurs at the anode and reduction at '
                 'the cathode, electrons travel through the external circuit from anode to '
                 'cathode, and ions carry the current through the salt bridge or electrolyte.',
                 ['anode', 'cathode', 'salt bridge']),
            ]),
            ('Cell Potential and Free Energy', [
                ('Cell Potential and the Sign of Free Energy',
                 'The standard cell potential is the cathode reduction potential minus the '
                 'anode reduction potential, and a positive potential corresponds to a '
                 'negative free energy change because that change equals minus nFE.',
                 ['cell potential', 'standard reduction potential', 'free energy']),
            ]),
            ('Cell Potential Under Nonstandard Conditions', [
                ('Nernst Equation and Nonstandard Potential',
                 'Cell potential falls as the reaction quotient rises, following a potential '
                 'equal to the standard potential minus RT over nF times the natural logarithm '
                 'of Q, which at 25 degrees Celsius becomes the standard potential minus '
                 '0.0592 over n times log Q.',
                 ['nernst equation', 'nonstandard', 'cell potential']),
            ]),
            ('Electrolysis and Faraday\'s Law', [
                ("Electrolysis and Faraday's Law",
                 'An electrolytic cell uses an external voltage to drive a nonspontaneous '
                 'reaction, and the moles of substance deposited equal the charge passed '
                 'divided by nF, so the charge alone fixes the mass produced.',
                 ['electrolysis', 'faraday', 'charge']),
            ]),
        ],
    },
]
