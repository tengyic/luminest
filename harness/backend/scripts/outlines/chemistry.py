"""Chemistry outline, in the shape ``scripts/course_pipeline.py`` expects.

The scope and sequence below is written for this project: an eighteen-unit introductory
chemistry course from classification of matter to organic chemistry. Unit and topic names
follow the course plan; every summary is an original statement written here, not textbook
text.

Textbook alignment. Every slug in ``sections`` was read from OpenStax's own table of
contents with ``scripts/probe_sections.py`` and is re-fetched through the licence gate by
``course_pipeline.py verify``, so none is guessed.

* ``chemistry`` (1e, CC BY 4.0) is the spine: it carries all eighteen units.
* ``chemistry-atoms-first`` (1e, CC BY 4.0) is a supplement, used for the atomic-structure
  unit because that edition teaches the atom before bonding.
* ``chemistry-2e`` reports CC BY-NC-SA 4.0 and is therefore link-only: named in the
  alignment metadata as a study reference, never stored or quoted, and never an anchor.

Two units (bonding, aqueous equilibria) carry five sections rather than four because each
has four topics and no single section covers the last of them (hybrid orbitals; Ksp).
"""

from __future__ import annotations

ID = 'chemistry'
TITLE = 'Chemistry'
SUBJECT = 'Chemistry'
SUBJECT_KIND = 'science'
EXPECTED_WEEKS = 36
COURSE_LINE = 'Chemistry - Matter, Reactions and Energy'
DESCRIPTION = (
    'A full-year introductory chemistry course: matter and measurement, the atom and its '
    'electronic structure, bonding and molecular shape, nomenclature, the mole and '
    'stoichiometry, reactions in solution, gases, thermochemistry, condensed phases, '
    'solutions, kinetics, equilibrium, acids and bases, thermodynamics, electrochemistry, '
    'nuclear chemistry and organic chemistry.')

TEXTBOOK = {
    'spine': 'OpenStax Chemistry (1e, CC BY 4.0)',
    'supplements': ['OpenStax Chemistry: Atoms First (1e, CC BY 4.0)'],
    'link_only_note': ('OpenStax Chemistry 2e reports CC BY-NC-SA 4.0 and is carried as a '
                       'link-only study reference: never stored or quoted.'),
}

UNITS = [
    {
        'unit': 'Matter and Measurement',
        'about': ('The entry unit: how chemists sort matter into substances and mixtures, '
                  'describe its properties and changes, measure it with SI units, and reason '
                  'about the numbers those measurements produce.'),
        'sections': [
            ('chemistry', '1-2-phases-and-classification-of-matter'),
            ('chemistry', '1-3-physical-and-chemical-properties'),
            ('chemistry', '1-4-measurements'),
            ('chemistry', '1-6-mathematical-treatment-of-measurement-results'),
        ],
        'topics': [
            ('Classifying Matter', [
                ('Pure Substances and Mixtures',
                 'A pure substance has a fixed composition throughout, while a mixture '
                 'contains two or more substances that keep their own identities and can be '
                 'separated by physical means.',
                 ['pure substance', 'mixture', 'composition']),
                ('Elements and Compounds',
                 'An element cannot be broken into simpler substances by chemical means, '
                 'whereas a compound contains two or more elements combined in a fixed '
                 'whole-number ratio.',
                 ['element', 'compound', 'fixed ratio']),
                ('Homogeneous and Heterogeneous Mixtures',
                 'A homogeneous mixture is uniform at the molecular scale, so any sample has '
                 'the same composition, while a heterogeneous mixture has regions that '
                 'differ in composition.',
                 ['homogeneous', 'heterogeneous', 'solution']),
            ]),
            ('Properties and Changes', [
                ('Physical and Chemical Properties',
                 'A physical property such as density or melting point is observed without '
                 'changing the substance, while a chemical property describes a reaction the '
                 'substance undergoes.',
                 ['physical property', 'chemical property', 'density']),
                ('Intensive versus Extensive Properties',
                 'An intensive property such as temperature or density does not depend on '
                 'sample size, whereas an extensive property such as mass or volume does.',
                 ['intensive', 'extensive', 'sample size']),
                ('Physical and Chemical Changes',
                 'A physical change alters only state or form, but a chemical change produces '
                 'a new substance and is recognised by a colour change, gas, precipitate or '
                 'heat release.',
                 ['physical change', 'chemical change', 'evidence']),
            ]),
            ('Measurement, Units, and the Nature of Science', [
                ('SI Base and Derived Units',
                 'The SI system fixes seven base units, and every other unit, such as the '
                 'newton or the joule, is a product or quotient of those base units.',
                 ['si units', 'derived unit', 'base unit']),
                ('Accuracy and Precision',
                 'Accuracy is agreement with the accepted value while precision is agreement '
                 'among repeated measurements, so a set of readings can be precise and still '
                 'biased.',
                 ['accuracy', 'precision', 'bias']),
            ]),
            ('Quantitative Reasoning', [
                ('Significant Figures in Calculations',
                 'A result carries no more certainty than its least certain input, so '
                 'multiplication keeps the smallest significant-figure count and addition '
                 'keeps the smallest decimal place.',
                 ['significant figures', 'rounding', 'certainty']),
                ('Dimensional Analysis',
                 'Multiplying by a ratio equal to one converts units while cancelling the '
                 'unwanted unit, which is why the answer arrives carrying the unit the '
                 'question asked for.',
                 ['dimensional analysis', 'conversion factor', 'units']),
                ('Scientific Notation and Order of Magnitude',
                 'Writing a value as a coefficient between one and ten times a power of ten '
                 'fixes its size, and the exponent alone gives its order of magnitude.',
                 ['scientific notation', 'magnitude', 'exponent']),
            ]),
        ],
    },
    {
        'unit': 'Atomic Structure',
        'about': ('From early atomism to a measured model of the atom: the experiments that '
                  'located the nucleus, the accounting of protons, neutrons and electrons, '
                  'and why atomic mass is an abundance-weighted average.'),
        'sections': [
            ('chemistry', '2-1-early-ideas-in-atomic-theory'),
            ('chemistry', '2-2-evolution-of-atomic-theory'),
            ('chemistry', '2-3-atomic-structure-and-symbolism'),
            ('chemistry-atoms-first', '2-3-atomic-structure-and-symbolism'),
        ],
        'topics': [
            ('Atomic Theory and Models', [
                ("Dalton's Atomic Postulates",
                 "Dalton's model treats each element as identical indivisible atoms combined "
                 'in fixed ratios, which explains the law of definite proportions but cannot '
                 'account for isotopes.',
                 ['dalton', 'atomic theory', 'postulates']),
                ('Discovery of the Electron',
                 "Thomson's cathode-ray experiments showed that atoms contain negative "
                 'particles, and their charge-to-mass ratio was the same whatever gas filled '
                 'the tube.',
                 ['electron', 'cathode ray', 'thomson']),
                ("Rutherford's Nuclear Model",
                 'Alpha particles that rebounded from gold foil forced the positive charge '
                 'and nearly all the mass into a tiny nucleus, leaving the rest of the atom '
                 'as empty space.',
                 ['rutherford', 'nucleus', 'gold foil']),
            ]),
            ('Subatomic Particles and Atomic Symbols', [
                ('Protons, Neutrons and Electrons',
                 'A proton carries +1 charge and a neutron carries none, each with a mass of '
                 'about 1 u, while an electron carries -1 charge and about 1/1836 of that '
                 'mass.',
                 ['proton', 'neutron', 'electron']),
                ('Atomic Number and Mass Number',
                 'The atomic number Z counts protons and fixes the element, while the mass '
                 'number A counts protons plus neutrons for one particular nuclide.',
                 ['atomic number', 'mass number', 'nuclide']),
                ('Nuclide Notation',
                 'Nuclide notation places A as a superscript and Z as a subscript before the '
                 'element symbol, so a uranium-238 symbol with 92 means 92 protons and 146 '
                 'neutrons.',
                 ['nuclide notation', 'symbol', 'superscript']),
            ]),
            ('Isotopes and Atomic Mass', [
                ('Isotopes of an Element',
                 'Isotopes of one element share the proton count but differ in neutron '
                 'count, so they are chemically nearly identical and differ in mass.',
                 ['isotope', 'neutron', 'mass']),
                ('Atomic Mass as a Weighted Average',
                 'The atomic mass listed on the periodic table is the abundance-weighted '
                 'average of the isotope masses, so it is close to but usually not equal to '
                 'any single isotope.',
                 ['atomic mass', 'weighted average', 'abundance']),
            ]),
            ('Ions', [
                ('Cations and Anions',
                 'A cation forms when an atom loses electrons and an anion when it gains '
                 'them, so the nucleus is unchanged while the charge and radius are not.',
                 ['cation', 'anion', 'ion']),
                ('Predicting Monatomic Ion Charge',
                 'Main-group metals lose their few valence electrons and nonmetals gain '
                 'electrons until the octet is complete, so group 1 forms 1+ and group 17 '
                 'forms 1-.',
                 ['ion charge', 'octet', 'valence']),
                ('Polyatomic Ions',
                 'A polyatomic ion is a covalently bonded group of atoms with a net charge, '
                 'such as the sulfate ion, and it behaves as one unit in a formula.',
                 ['polyatomic ion', 'sulfate', 'charge']),
            ]),
        ],
    },
    {
        'unit': 'Electron Configuration and Periodicity',
        'about': ('Why electrons occupy discrete levels, how configurations are written, and '
                  'how those configurations produce the periodic trends that organise every '
                  'later unit.'),
        'sections': [
            ('chemistry', '6-1-electromagnetic-energy'),
            ('chemistry', '6-2-the-bohr-model'),
            ('chemistry', '6-4-electronic-structure-of-atoms-electron-configurations'),
            ('chemistry', '6-5-periodic-variations-in-element-properties'),
        ],
        'topics': [
            ('Light, Energy, and the Quantum Model', [
                ('Wave Properties and the Speed of Light',
                 'Frequency times wavelength equals the speed of light, so a shorter '
                 'wavelength means a higher frequency and a more energetic photon.',
                 ['wavelength', 'frequency', 'speed of light']),
                ('Photons and Quantized Energy',
                 'Light exchanges energy in photons of energy h times its frequency, which '
                 'is why dim light above the threshold ejects electrons and bright light '
                 'below it does not.',
                 ['photon', 'planck', 'photoelectric']),
                ('The Bohr Model and Line Spectra',
                 'The Bohr model allows only certain orbits, so an electron emits a photon '
                 'whose energy equals the gap between two levels and the spectrum shows '
                 'discrete lines.',
                 ['bohr model', 'line spectrum', 'energy level']),
            ]),
            ('Electron Configurations', [
                ('Orbitals and Quantum Numbers',
                 'Three quantum numbers fix an orbital and a fourth fixes the electron spin, '
                 'and the Pauli principle allows at most two electrons of opposite spin in '
                 'one orbital.',
                 ['orbital', 'quantum numbers', 'pauli']),
                ('Filling Order and Hund\'s Rule',
                 'Electrons fill orbitals in order of increasing energy, with 4s below 3d, '
                 "and Hund's rule keeps electrons unpaired with parallel spins before any "
                 'orbital is doubled.',
                 ['aufbau', "hund's rule", 'filling order']),
                ('Noble-Gas Shorthand and Valence Electrons',
                 'Replacing the filled inner shells with a noble-gas symbol leaves the '
                 'outer configuration visible, and those outer electrons are the valence '
                 'electrons that determine bonding.',
                 ['noble gas core', 'valence electrons', 'configuration']),
            ]),
            ('Periodic Trends', [
                ('Effective Nuclear Charge',
                 'Effective nuclear charge is the nuclear charge minus the screening of inner '
                 'electrons, and it rises across a period because the screening hardly '
                 'changes while Z increases.',
                 ['effective nuclear charge', 'shielding', 'trend']),
                ('Atomic Radius Across and Down',
                 'Atomic radius falls from left to right across a period and rises down a '
                 'group, because an added shell outweighs the greater nuclear charge.',
                 ['atomic radius', 'trend', 'shells']),
                ('Ionization Energy and Electron Affinity',
                 'Ionization energy rises across a period and falls down a group, and its '
                 'dips at groups 13 and 16 come from an unpaired p electron and a paired '
                 'p electron respectively.',
                 ['ionization energy', 'electron affinity', 'trend']),
            ]),
        ],
    },
    {
        'unit': 'Chemical Bonding and Molecular Geometry',
        'about': ('How atoms join: the continuum from ionic to covalent bonding, Lewis '
                  'bookkeeping, the three-dimensional shapes that follow from electron-pair '
                  'repulsion, and the orbital models behind those shapes.'),
        'sections': [
            ('chemistry', '7-1-ionic-bonding'),
            ('chemistry', '7-2-covalent-bonding'),
            ('chemistry', '7-3-lewis-symbols-and-structures'),
            ('chemistry', '7-6-molecular-structure-and-polarity'),
            ('chemistry', '8-2-hybrid-atomic-orbitals'),
        ],
        'topics': [
            ('Bond Types and Electronegativity', [
                ('Ionic, Covalent and Metallic Bonding',
                 'Ionic bonding transfers electrons from a metal to a nonmetal, covalent '
                 'bonding shares them between nonmetals, and metallic bonding delocalises '
                 'them over a lattice of cations.',
                 ['ionic bond', 'covalent bond', 'metallic']),
                ('Electronegativity and Bond Polarity',
                 'A bond is polar when the electronegativity difference is roughly 0.4 to '
                 '1.7 and largely ionic above that, with the shared electrons drawn towards '
                 'the more electronegative atom.',
                 ['electronegativity', 'polar bond', 'difference']),
                ('Lattice Energy',
                 'Lattice energy grows with the product of the ion charges and falls as the '
                 'ions get larger, which is why magnesium oxide melts far above sodium '
                 'chloride.',
                 ['lattice energy', 'ion charge', 'coulomb']),
            ]),
            ('Lewis Structures', [
                ('Drawing a Lewis Structure',
                 'Count the valence electrons, join the atoms with single bonds, complete '
                 'the outer octets, then place the remainder on the central atom and form '
                 'multiple bonds if it is short of an octet.',
                 ['lewis structure', 'octet', 'lone pair']),
                ('Formal Charge and Resonance',
                 'Formal charge is the valence-electron count minus the electrons assigned to '
                 'an atom, and structures that differ only in electron placement are '
                 'resonance forms of one hybrid.',
                 ['formal charge', 'resonance', 'hybrid']),
                ('Octet Exceptions',
                 'Beryllium and boron compounds can be electron deficient, a species with an '
                 'odd electron count such as nitric oxide has an unpaired electron, and '
                 'third-period atoms may exceed eight electrons.',
                 ['octet exception', 'expanded octet', 'radical']),
            ]),
            ('Molecular Geometry and Polarity', [
                ('VSEPR Electron-Pair Geometry',
                 'Electron pairs repel and spread as far apart as possible, giving linear, '
                 'trigonal planar, tetrahedral, trigonal bipyramidal and octahedral '
                 'arrangements for two to six pairs.',
                 ['vsepr', 'geometry', 'electron pair']),
                ('Lone Pairs and Molecular Shape',
                 'A lone pair occupies more angular space than a bond, so it compresses the '
                 'bond angles and turns tetrahedral electron geometry into trigonal '
                 'pyramidal or bent molecular shape.',
                 ['lone pair', 'bond angle', 'shape']),
                ('Molecular Polarity from Dipole Cancellation',
                 'A molecule is polar only when its bond dipoles do not cancel, so carbon '
                 'dioxide is nonpolar even though each carbon-oxygen bond is polar.',
                 ['dipole', 'polarity', 'symmetry']),
            ]),
            ('Advanced Bonding Theory', [
                ('Hybrid Orbitals and Valence Bond Theory',
                 'Mixing s and p orbitals gives sp, sp2 or sp3 hybrids whose directions match '
                 'the observed bond angles, which is how the tetrahedral carbon of methane is '
                 'explained.',
                 ['hybridization', 'valence bond', 'sp3']),
                ('Sigma and Pi Bonds',
                 'A sigma bond comes from head-on overlap and permits rotation, while a pi '
                 'bond comes from side-on p overlap that holds the atoms in a plane and '
                 'blocks rotation about a double bond.',
                 ['sigma bond', 'pi bond', 'rotation']),
                ('Molecular Orbital Theory',
                 'Combining atomic orbitals gives bonding and antibonding molecular orbitals, '
                 'and filling them in order explains why oxygen is paramagnetic although its '
                 'Lewis structure shows no unpaired electrons.',
                 ['molecular orbital', 'paramagnetic', 'bond order']),
            ]),
        ],
    },
    {
        'unit': 'Chemical Nomenclature and Formulas',
        'about': ('The naming and formula conventions that let a written formula be read as '
                  'a composition, covering ionic compounds, molecular compounds, acids and '
                  'the oxidation numbers that redox chemistry later depends on.'),
        'sections': [
            ('chemistry', '2-4-chemical-formulas'),
            ('chemistry', '2-6-molecular-and-ionic-compounds'),
            ('chemistry', '2-7-chemical-nomenclature'),
        ],
        'topics': [
            ('Ionic Compounds', [
                ('Charge Balance in Ionic Formulas',
                 'An ionic formula is written so the total positive charge equals the total '
                 'negative charge, which is why aluminium oxide is Al2O3 rather than AlO.',
                 ['formula unit', 'charge balance', 'ionic']),
                ('Naming Ionic Compounds',
                 'Name the cation first and the anion second with an -ide ending, and add a '
                 'Roman numeral when the metal can take more than one stable charge.',
                 ['ionic naming', 'roman numeral', 'anion']),
                ('Hydrates',
                 'A hydrate holds a fixed number of water molecules per formula unit, written '
                 'after a dot, and heating drives that water off as a measurable mass loss.',
                 ['hydrate', 'water of crystallization', 'formula']),
            ]),
            ('Molecular Compounds and Acids', [
                ('Greek Prefixes in Molecular Names',
                 'Binary molecular compounds use prefixes from mono- to deca- to state each '
                 'atom count, and the mono- on the first element is dropped.',
                 ['greek prefix', 'binary compound', 'naming']),
                ('Naming Acids',
                 'An acid of the form HX is named hydro-X-ic acid, while an oxyacid takes the '
                 '-ous ending when its anion ends in -ite and -ic when the anion ends in '
                 '-ate.',
                 ['acid naming', 'oxyacid', 'anion suffix']),
            ]),
            ('Oxidation Numbers', [
                ('Rules for Assigning Oxidation Numbers',
                 'Oxygen is -2 in compounds except with fluorine, hydrogen is +1 when bonded '
                 'to a nonmetal, and the oxidation numbers in a neutral compound sum to '
                 'zero.',
                 ['oxidation number', 'rules', 'sum']),
                ('Oxidation and Reduction as Electron Transfer',
                 'An atom is oxidised when its oxidation number rises and reduced when it '
                 'falls, so the two changes always occur together in one reaction.',
                 ['oxidation', 'reduction', 'redox']),
            ]),
        ],
    },
    {
        'unit': 'The Mole and Stoichiometry',
        'about': ('The counting bridge between the balance and the balanced equation: the '
                  'mole, formula determination, equation balancing, and the stoichiometric '
                  'calculation the rest of the course relies on.'),
        'sections': [
            ('chemistry', '3-1-formula-mass-and-the-mole-concept'),
            ('chemistry', '3-2-determining-empirical-and-molecular-formulas'),
            ('chemistry', '4-1-writing-and-balancing-chemical-equations'),
            ('chemistry', '4-3-reaction-stoichiometry'),
        ],
        'topics': [
            ('The Mole and Molar Mass', [
                ("The Mole and Avogadro's Number",
                 'One mole contains 6.022 x 10^23 entities, so the mole converts a count of '
                 'particles into an amount that can be weighed.',
                 ['mole', 'avogadro', 'particles']),
                ('Molar Mass',
                 'Molar mass is the mass in grams of one mole of a substance and is '
                 'numerically equal to its formula mass in unified atomic mass units.',
                 ['molar mass', 'formula mass', 'grams per mole']),
                ('Converting Between Mass, Moles and Particles',
                 'Mass, moles and particle count convert into one another through molar mass '
                 'and Avogadro\'s number, with each ratio chosen so the given unit cancels.',
                 ['mole conversion', 'molar mass', 'avogadro']),
            ]),
            ('Composition and Formulas', [
                ('Percent Composition by Mass',
                 'Percent composition is the mass of one element in a mole divided by the '
                 'molar mass, so water is 11.2% hydrogen by mass although two of its three '
                 'atoms are hydrogen.',
                 ['percent composition', 'mass fraction', 'element']),
                ('Empirical Formula from Mole Ratios',
                 'The empirical formula is the smallest whole-number atom ratio, found by '
                 'converting masses to moles and dividing through by the smallest count.',
                 ['empirical formula', 'ratio', 'moles']),
                ('Molecular Formula from the Empirical Formula',
                 'The molecular formula is a whole-number multiple of the empirical formula, '
                 'and the multiplier is the molar mass divided by the empirical formula mass.',
                 ['molecular formula', 'multiple', 'molar mass']),
            ]),
            ('Balancing Equations', [
                ('Conservation of Atoms in a Reaction',
                 'A balanced equation has the same number of each kind of atom on both sides, '
                 'because a reaction only rearranges atoms and never creates or destroys '
                 'them.',
                 ['conservation', 'balancing', 'atoms']),
                ('Balancing by Inspection',
                 'Balance one element at a time and leave hydrogen and oxygen until last, '
                 'adjusting only coefficients because changing a subscript would change the '
                 'substance.',
                 ['inspection', 'coefficients', 'subscript']),
            ]),
            ('Reaction Stoichiometry', [
                ('Mole Ratios from Coefficients',
                 'The coefficients of a balanced equation give the mole ratio between any two '
                 'substances, and that ratio is the only bridge from one substance to '
                 'another.',
                 ['mole ratio', 'coefficients', 'stoichiometry']),
                ('Limiting Reactant',
                 'The limiting reactant is used up first and sets the maximum product, while '
                 'the excess reactant is still present when the reaction stops.',
                 ['limiting reactant', 'excess', 'maximum product']),
                ('Percent Yield',
                 'Percent yield is the actual yield divided by the theoretical yield times '
                 '100, and a value above 100 signals an impure or wet product rather than a '
                 'better reaction.',
                 ['percent yield', 'theoretical yield', 'actual yield']),
            ]),
        ],
    },
    {
        'unit': 'Chemical Reactions and Solution Stoichiometry',
        'about': ('Reactions in water: recognising the reaction classes, writing net ionic '
                  'equations, tracking electrons in redox, and extending stoichiometry to '
                  'solutions of known concentration.'),
        'sections': [
            ('chemistry', '4-2-classifying-chemical-reactions'),
            ('chemistry', '4-5-quantitative-chemical-analysis'),
            ('chemistry', '3-3-molarity'),
        ],
        'topics': [
            ('Classifying Reactions', [
                ('Precipitation Reactions',
                 'Two soluble salts exchange ions and a product of low solubility leaves '
                 'solution as a solid, which a solubility table predicts before the '
                 'reaction is run.',
                 ['precipitation', 'solubility', 'double displacement']),
                ('Acid-Base Neutralization',
                 'An acid and a base react to give water and a salt, with the hydrogen ion '
                 'and the hydroxide ion combining in a one-to-one ratio.',
                 ['neutralization', 'salt', 'water']),
            ]),
            ('Aqueous Reactions', [
                ('Dissociation and Spectator Ions',
                 'A strong electrolyte dissociates completely in water, and the ions that '
                 'appear unchanged on both sides are spectators omitted from the net ionic '
                 'equation.',
                 ['dissociation', 'spectator ion', 'net ionic']),
                ('Strong and Weak Electrolytes',
                 'A strong electrolyte ionises essentially completely, a weak electrolyte '
                 'only partly and a nonelectrolyte not at all, which conductivity reveals.',
                 ['electrolyte', 'conductivity', 'ionization']),
            ]),
            ('Acid-Base and Redox Reactions', [
                ('Electron Transfer in Redox Equations',
                 'In a redox reaction the oxidation number of the oxidised element rises and '
                 'that of the reduced element falls, and the electrons lost must equal the '
                 'electrons gained.',
                 ['redox', 'oxidation state', 'electrons']),
                ('Displacement and Combustion Reactions',
                 'A single-displacement reaction has a more reactive element replace a less '
                 'reactive one, and complete combustion of a hydrocarbon gives carbon '
                 'dioxide and water.',
                 ['displacement', 'combustion', 'activity series']),
            ]),
            ('Solution Stoichiometry', [
                ('Molarity',
                 'Molarity is moles of solute per litre of solution, and because a '
                 'solution\'s volume changes with temperature, so does its molarity.',
                 ['molarity', 'moles', 'volume']),
                ('Dilution',
                 'Dilution adds solvent without changing the moles of solute, so the product '
                 'of molarity and volume is constant before and after.',
                 ['dilution', 'molarity', 'volume']),
                ('Titration to the Equivalence Point',
                 'A titration reaches its equivalence point when the moles of titrant equal '
                 'the moles required by the balanced equation, which need not be the point '
                 'of neutral pH.',
                 ['titration', 'equivalence point', 'moles']),
            ]),
        ],
    },
    {
        'unit': 'Gases',
        'about': ('The gas laws as one coherent model, applied to mixtures and to reactions, '
                  'and grounded in the kinetic-molecular picture of particles in constant '
                  'motion.'),
        'sections': [
            ('chemistry', '9-1-gas-pressure'),
            ('chemistry', '9-2-relating-pressure-volume-amount-and-temperature-the-ideal-gas-law'),
            ('chemistry', '9-3-stoichiometry-of-gaseous-substances-mixtures-and-reactions'),
            ('chemistry', '9-5-the-kinetic-molecular-theory'),
        ],
        'topics': [
            ('The Gas Laws', [
                ('Gas Pressure and Its Units',
                 'Gas pressure is force per unit area on the walls of its container, and one '
                 'atmosphere equals 760 mmHg, 101.325 kPa and 14.7 pounds per square inch.',
                 ['pressure', 'atmosphere', 'units']),
                ("Boyle's and Charles's Laws",
                 'At fixed temperature the volume of a gas is inversely proportional to its '
                 'pressure, and at fixed pressure the volume is directly proportional to its '
                 'absolute temperature.',
                 ['boyle', 'charles', 'gas law']),
                ("Avogadro's Law and the Combined Gas Law",
                 'At fixed temperature and pressure equal volumes of gases hold equal moles, '
                 'and combining the three laws makes pressure times volume over temperature '
                 'constant for a fixed amount.',
                 ['avogadro', 'combined gas law', 'proportional']),
            ]),
            ('The Ideal Gas Law', [
                ('The Ideal Gas Equation',
                 'The equation PV = nRT with R equal to 0.08206 litre-atmosphere per mole '
                 'kelvin relates pressure, volume, amount and absolute temperature for a gas '
                 'treated as non-interacting point particles.',
                 ['ideal gas law', 'gas constant', 'pv nrt']),
                ('Molar Volume at Standard Conditions',
                 'One mole of an ideal gas occupies 22.4 litres at 0 degrees Celsius and one '
                 'atmosphere, and 22.7 litres at one bar, so a gas volume can be read as an '
                 'amount.',
                 ['molar volume', 'stp', '22.4']),
                ('Gas Density and Molar Mass',
                 'Rearranging the ideal gas law gives density equal to pressure times molar '
                 'mass over RT, so measuring density at known pressure and temperature yields '
                 'a molar mass.',
                 ['gas density', 'molar mass', 'ideal gas']),
            ]),
            ('Gas Mixtures and Stoichiometry', [
                ("Dalton's Law of Partial Pressures",
                 'Each gas in a mixture exerts the pressure it would exert alone, and the '
                 'total pressure is the sum of those partial pressures.',
                 ['partial pressure', 'dalton', 'mixture']),
                ('Volume Ratios in Gas Reactions',
                 'Because equal volumes hold equal moles at the same temperature and pressure, '
                 'gaseous reactants and products combine in the volume ratio of their '
                 'coefficients.',
                 ['volume ratio', 'gas stoichiometry', 'coefficients']),
            ]),
            ('Kinetic-Molecular Theory', [
                ('Postulates of the Kinetic-Molecular Model',
                 'Gas particles move randomly with negligible volume and no attractions, and '
                 'the pressure they exert comes from collisions with the container walls.',
                 ['kinetic molecular theory', 'collisions', 'ideal gas']),
                ('Temperature and Molecular Speed',
                 'Average kinetic energy depends only on absolute temperature, so at one '
                 'temperature all gases share the same average kinetic energy but have '
                 'different root-mean-square speeds.',
                 ['kinetic energy', 'rms speed', 'temperature']),
                ('Effusion and Diffusion',
                 "Graham's law states that the rate of effusion is inversely proportional to "
                 'the square root of molar mass, so a lighter gas escapes through a small '
                 'hole faster.',
                 ['effusion', 'diffusion', 'graham']),
            ]),
        ],
    },
    {
        'unit': 'Thermochemistry',
        'about': ('Energy accounting for chemical change: heat and work, enthalpy, '
                  'calorimetric measurement, and Hess\'s law, which makes reactions that '
                  'cannot be run directly still calculable.'),
        'sections': [
            ('chemistry', '5-1-energy-basics'),
            ('chemistry', '5-2-calorimetry'),
            ('chemistry', '5-3-enthalpy'),
        ],
        'topics': [
            ('Energy and Heat', [
                ('Internal Energy and the First Law',
                 'The internal energy of a system changes by the heat added to it plus the '
                 'work done on it, so energy is conserved and only moves between system and '
                 'surroundings.',
                 ['internal energy', 'first law', 'work']),
                ('Specific Heat Capacity',
                 'Specific heat is the energy needed to raise one gram of a substance by one '
                 'kelvin, and the value of 4.18 joules per gram kelvin for water makes it a '
                 'slow-warming thermal reservoir.',
                 ['specific heat', 'heat capacity', 'joule']),
            ]),
            ('Enthalpy and Calorimetry', [
                ('Enthalpy Change at Constant Pressure',
                 'Enthalpy change is the heat exchanged at constant pressure, and a negative '
                 'value means the system released energy to the surroundings.',
                 ['enthalpy', 'exothermic', 'constant pressure']),
                ('Calorimetry',
                 'A calorimeter finds the heat transferred from a temperature change using q '
                 'equals mass times specific heat times temperature change, and a bomb '
                 'calorimeter does it at constant volume instead of constant pressure.',
                 ['calorimetry', 'heat measurement', 'bomb']),
            ]),
            ("Hess's Law and Formation Enthalpies", [
                ("Hess's Law",
                 'Because enthalpy is a state function, the enthalpy change of a reaction is '
                 'the same whatever route is taken, so it can be assembled from steps that '
                 'are easier to measure.',
                 ['hess law', 'state function', 'path']),
                ('Standard Enthalpies of Formation',
                 'The standard enthalpy of reaction is the sum of the formation enthalpies of '
                 'the products minus that of the reactants, with each element in its standard '
                 'state assigned zero.',
                 ['formation enthalpy', 'standard state', 'products minus reactants']),
            ]),
        ],
    },
    {
        'unit': 'Intermolecular Forces, Liquids, and Solids',
        'about': ('What holds condensed phases together: the intermolecular forces, the phase '
                  'transitions they produce, the diagrams that map those transitions, and the '
                  'solids the same forces build.'),
        'sections': [
            ('chemistry', '10-1-intermolecular-forces'),
            ('chemistry', '10-3-phase-transitions'),
            ('chemistry', '10-4-phase-diagrams'),
            ('chemistry', '10-5-the-solid-state-of-matter'),
        ],
        'topics': [
            ('Intermolecular Forces', [
                ('London Dispersion Forces',
                 'Instantaneous dipoles attract every pair of molecules, and the force '
                 'strengthens with polarisability, which is why the larger halogens boil at '
                 'higher temperatures.',
                 ['dispersion', 'polarizability', 'london']),
                ('Dipole-Dipole Forces and Hydrogen Bonding',
                 'A hydrogen bond is the strong attraction between a hydrogen bonded to N, O '
                 'or F and a lone pair on another of those atoms, and it explains the high '
                 'boiling point of water.',
                 ['hydrogen bond', 'dipole', 'boiling point']),
                ('Ion-Dipole Forces',
                 'An ion attracts the oppositely charged end of a polar molecule, and these '
                 'ion-dipole attractions are what pull sodium chloride apart in water.',
                 ['ion-dipole', 'dissolution', 'polar']),
            ]),
            ('Phase Changes and Diagrams', [
                ('Vapour Pressure and Boiling',
                 'Vapour pressure rises with temperature, and a liquid boils when that '
                 'pressure equals the external pressure, which is why water boils below 100 '
                 'degrees Celsius on a mountain.',
                 ['vapour pressure', 'boiling', 'altitude']),
                ('Energy Absorbed in Phase Changes',
                 'Melting and vaporisation absorb energy without raising the temperature, so '
                 'the heating curve of water has flat plateaus at 0 and 100 degrees Celsius.',
                 ['latent heat', 'heating curve', 'plateau']),
                ('Phase Diagrams and the Triple Point',
                 'A phase diagram plots pressure against temperature, its triple point is '
                 'where all three phases coexist, and its critical point ends the '
                 'liquid-vapour boundary.',
                 ['phase diagram', 'triple point', 'critical point']),
            ]),
            ('Solids', [
                ('Crystalline and Amorphous Solids',
                 'A crystalline solid has a repeating long-range lattice, while an amorphous '
                 'solid such as glass lacks one and softens over a range instead of melting '
                 'at a single temperature.',
                 ['crystalline', 'amorphous', 'lattice']),
                ('Classes of Crystalline Solids',
                 'Molecular, ionic, covalent-network and metallic solids differ in what holds '
                 'the lattice together, so a network solid such as diamond melts above 3500 '
                 'degrees Celsius while molecular solids melt far lower.',
                 ['network solid', 'ionic solid', 'melting point']),
            ]),
        ],
    },
    {
        'unit': 'Solutions and Their Properties',
        'about': ('Solutions as mixtures with their own behaviour: how dissolving happens, '
                  'how concentration is expressed, and the colligative effects that depend '
                  'only on the number of dissolved particles.'),
        'sections': [
            ('chemistry', '11-1-the-dissolution-process'),
            ('chemistry', '3-4-other-units-for-solution-concentrations'),
            ('chemistry', '11-4-colligative-properties'),
        ],
        'topics': [
            ('The Dissolution Process', [
                ('Energetics of Dissolution',
                 'A solute dissolves when the energy released by solute-solvent attractions '
                 'offsets the energy needed to separate the solute particles and the solvent '
                 'molecules.',
                 ['dissolution', 'hydration', 'energy']),
                ('Like Dissolves Like',
                 'A polar solvent dissolves polar and ionic solutes while a nonpolar solvent '
                 'dissolves nonpolar solutes, because the new attractions must resemble the '
                 'ones they replace.',
                 ['like dissolves like', 'polarity', 'solvent']),
            ]),
            ('Concentration', [
                ('Molarity and Molality',
                 'Molality is moles of solute per kilogram of solvent, so unlike molarity it '
                 'does not change when the solution is heated or cooled.',
                 ['molality', 'molarity', 'temperature']),
                ('Mass Percent and Parts per Million',
                 'Mass percent compares solute mass with total solution mass, and parts per '
                 'million scales the same ratio by 10^6 for trace concentrations.',
                 ['mass percent', 'ppm', 'trace']),
            ]),
            ('Colligative Properties', [
                ("Raoult's Law and Vapour Pressure Lowering",
                 'A nonvolatile solute lowers the vapour pressure in proportion to its mole '
                 'fraction, because solute particles occupy part of the surface otherwise '
                 'available for evaporation.',
                 ['raoult', 'vapour pressure', 'mole fraction']),
                ('Boiling Point Elevation and Freezing Point Depression',
                 'Dissolved particles raise the boiling point and lower the freezing point by '
                 'amounts proportional to molality, which is why salt melts ice on a road.',
                 ['boiling point elevation', 'freezing point depression', 'molality']),
                ('Osmotic Pressure',
                 'Osmosis moves solvent through a semipermeable membrane into the more '
                 'concentrated solution, and the pressure that just stops it is proportional '
                 'to molarity and absolute temperature.',
                 ['osmosis', 'osmotic pressure', 'membrane']),
            ]),
        ],
    },
    {
        'unit': 'Reaction Kinetics',
        'about': ('How fast reactions go: measuring rate, extracting the experimental rate '
                  'law, reasoning with collisions and activation energy, and following a '
                  'mechanism through its slowest step.'),
        'sections': [
            ('chemistry', '12-1-chemical-reaction-rates'),
            ('chemistry', '12-3-rate-laws'),
            ('chemistry', '12-6-reaction-mechanisms'),
            ('chemistry', '12-7-catalysis'),
        ],
        'topics': [
            ('Reaction Rates and Collision Theory', [
                ('Expressing Reaction Rate',
                 'Reaction rate is the change in concentration per unit time, divided by the '
                 'species coefficient so that one number describes the whole reaction.',
                 ['reaction rate', 'concentration', 'coefficient']),
                ('Collision Theory and Activation Energy',
                 'A reaction proceeds only when colliding molecules have at least the '
                 'activation energy and the right orientation, so raising temperature raises '
                 'the fraction of successful collisions.',
                 ['collision theory', 'activation energy', 'orientation']),
                ('Factors That Change Rate',
                 'Concentration, surface area, temperature and catalysts change the rate by '
                 'changing how often particles collide or how high the barrier is.',
                 ['concentration', 'surface area', 'temperature']),
            ]),
            ('Rate Laws', [
                ('Rate Law and Reaction Order',
                 'A rate law expresses rate as the rate constant times concentrations raised '
                 'to experimentally determined powers, and those exponents sum to the overall '
                 'order.',
                 ['rate law', 'reaction order', 'rate constant']),
                ('Determining Order from Initial Rates',
                 'Order is found by comparing runs in which one concentration changes, because '
                 'doubling a first-order reactant doubles the rate while doubling a '
                 'second-order one quadruples it.',
                 ['order determination', 'initial rates', 'data']),
                ('Half-Life of a First-Order Reaction',
                 'A first-order reaction has a half-life equal to 0.693 divided by the rate '
                 'constant, independent of starting concentration, which is why radioactive '
                 'decay follows the same law.',
                 ['half-life', 'first order', 'rate constant']),
            ]),
            ('Mechanisms and Catalysis', [
                ('Elementary Steps and the Rate-Determining Step',
                 'A mechanism is a sequence of elementary steps that must sum to the balanced '
                 'equation, and the slowest step controls the overall rate.',
                 ['mechanism', 'rate-determining step', 'elementary']),
                ('How a Catalyst Works',
                 'A catalyst supplies a lower-energy pathway without being consumed, so it '
                 'raises the rate in both directions and leaves the equilibrium constant '
                 'unchanged.',
                 ['catalyst', 'activation energy', 'equilibrium']),
            ]),
        ],
    },
    {
        'unit': 'Chemical Equilibrium',
        'about': ('How far reactions go: dynamic equilibrium, the equilibrium constant, the '
                  'quantitative calculations built on it, and the response of a system to a '
                  'disturbance.'),
        'sections': [
            ('chemistry', '13-1-chemical-equilibria'),
            ('chemistry', '13-2-equilibrium-constants'),
            ('chemistry', '13-3-shifting-equilibria-le-chateliers-principle'),
        ],
        'topics': [
            ('Equilibrium and the Equilibrium Constant', [
                ('Dynamic Equilibrium',
                 'At equilibrium the forward and reverse rates are equal, so concentrations '
                 'stop changing even though both reactions continue at the molecular level.',
                 ['dynamic equilibrium', 'forward rate', 'reverse rate']),
                ('The Equilibrium Constant Expression',
                 'The equilibrium constant is the product of product concentrations raised to '
                 'their coefficients divided by the same expression for reactants, with pure '
                 'solids and liquids omitted.',
                 ['equilibrium constant', 'expression', 'heterogeneous']),
                ('Interpreting the Magnitude of K',
                 'A large K means products dominate at equilibrium and a small K means '
                 'reactants dominate, but K says nothing about how fast equilibrium is '
                 'reached.',
                 ['magnitude of k', 'products', 'kinetics']),
            ]),
            ('Equilibrium Calculations', [
                ('The Reaction Quotient and Direction',
                 'The reaction quotient has the form of K but uses current concentrations, so '
                 'Q below K drives the reaction forward and Q above K drives it in reverse.',
                 ['reaction quotient', 'direction', 'compare']),
                ('ICE Table Calculations',
                 'An ICE table records initial and equilibrium concentrations with the change '
                 'set by the stoichiometry, and K then supplies the equation that fixes the '
                 'unknown.',
                 ['ice table', 'change', 'equilibrium concentration']),
            ]),
            ("Le Chatelier's Principle", [
                ('Response to Concentration and Pressure Changes',
                 'A system at equilibrium shifts to oppose a change in concentration or '
                 'partial pressure, and a catalyst does not shift it because it speeds both '
                 'directions equally.',
                 ['le chatelier', 'shift', 'stress']),
                ('Temperature Dependence of K',
                 'Changing the temperature changes the value of K itself rather than only the '
                 'position, and an endothermic reaction is favoured by heating.',
                 ['temperature', 'endothermic', 'equilibrium constant']),
            ]),
        ],
    },
    {
        'unit': 'Acids, Bases, and Aqueous Equilibria',
        'about': ('Aqueous acid-base chemistry as equilibrium applied: proton transfer, pH, '
                  'weak-acid calculations, buffers and titrations, and the solubility '
                  'equilibrium that closes the unit.'),
        'sections': [
            ('chemistry', '14-1-bronsted-lowry-acids-and-bases'),
            ('chemistry', '14-2-ph-and-poh'),
            ('chemistry', '14-3-relative-strengths-of-acids-and-bases'),
            ('chemistry', '14-6-buffers'),
            ('chemistry', '15-1-precipitation-and-dissolution'),
        ],
        'topics': [
            ('Acid-Base Definitions and pH', [
                ('Bronsted-Lowry Proton Transfer',
                 'A Bronsted-Lowry acid donates a proton and a base accepts one, so every '
                 'acid has a conjugate base that differs from it by a single hydrogen ion.',
                 ['bronsted-lowry', 'proton', 'conjugate']),
                ('pH and pOH',
                 'pH is the negative base-ten logarithm of the hydrogen ion concentration, '
                 'and at 25 degrees Celsius pH plus pOH equals 14 because the ion product of '
                 'water is 1.0 x 10^-14.',
                 ['ph', 'poh', 'water constant']),
                ('Strong versus Weak Acids',
                 'A strong acid ionises completely in water while a weak acid reaches an '
                 'equilibrium, so solutions of equal concentration differ greatly in pH and '
                 'conductivity.',
                 ['strong acid', 'weak acid', 'ionization']),
            ]),
            ('Weak Acid-Base Equilibria', [
                ('Ka, Kb and the Conjugate Pair',
                 'Ka measures the extent of weak-acid ionisation, and Ka times Kb equals the '
                 'ion product of water for a conjugate pair, so a stronger acid has a weaker '
                 'conjugate base.',
                 ['ka', 'kb', 'conjugate pair']),
                ('Calculating the pH of a Weak Acid',
                 'Solving the Ka expression for a weak acid gives the hydrogen ion '
                 'concentration, and the shortcut that ignores the change in the denominator '
                 'fails once the acid is not actually weak or dilute.',
                 ['weak acid ph', 'ka expression', 'approximation']),
                ('Percent Ionization',
                 'Percent ionization is the fraction of acid molecules ionised times 100, and '
                 'it falls as the initial concentration rises because the equilibrium shifts '
                 'towards the intact acid.',
                 ['percent ionization', 'dilution', 'weak acid']),
            ]),
            ('Neutralization, Titration, and Buffers', [
                ('Buffer Action',
                 'A buffer resists pH change because it contains a weak acid and its conjugate '
                 'base in comparable amounts, which neutralise any added acid or base.',
                 ['buffer', 'conjugate pair', 'ph resistance']),
                ('The Henderson-Hasselbalch Equation',
                 'A buffer pH equals the acid pKa plus the logarithm of the conjugate base to '
                 'acid ratio, and the buffer works best within about one pH unit of that pKa.',
                 ['henderson hasselbalch', 'buffer range', 'pka']),
            ]),
            ('Solubility Equilibria', [
                ('The Solubility Product Ksp',
                 'The solubility product is the product of the ion concentrations in a '
                 'saturated solution, each raised to its coefficient, and comparing Q with '
                 'Ksp predicts whether a precipitate forms.',
                 ['ksp', 'saturated solution', 'precipitation']),
                ('The Common Ion Effect',
                 'Adding an ion that the salt already supplies lowers its solubility, because '
                 'Q then exceeds Ksp and solid precipitates until Q returns to Ksp.',
                 ['common ion', 'solubility', 'precipitate']),
            ]),
        ],
    },
    {
        'unit': 'Thermodynamics: Entropy and Free Energy',
        'about': ('The direction of chemical change: entropy and the second law first, then '
                  'Gibbs free energy, which combines enthalpy and entropy into one criterion '
                  'for whether a reaction can proceed.'),
        'sections': [
            ('chemistry', '16-1-spontaneity'),
            ('chemistry', '16-2-entropy'),
            ('chemistry', '16-4-free-energy'),
        ],
        'topics': [
            ('Entropy and Spontaneity', [
                ('Entropy as Energy Dispersal',
                 'Entropy measures how widely a system\'s energy is dispersed among '
                 'microstates, so a process that spreads matter or energy over more '
                 'arrangements has a positive entropy change.',
                 ['entropy', 'microstates', 'dispersal']),
                ('The Second Law of Thermodynamics',
                 'A process is spontaneous when the total entropy of system plus surroundings '
                 'increases, so an entropy decrease in the system is allowed if the '
                 'surroundings gain more.',
                 ['second law', 'total entropy', 'spontaneous']),
            ]),
            ('Gibbs Free Energy', [
                ('Gibbs Free Energy and Spontaneity',
                 'The free energy change equals enthalpy change minus temperature times '
                 'entropy change, and at constant temperature and pressure a negative value '
                 'means spontaneous while zero means equilibrium.',
                 ['gibbs free energy', 'spontaneity', 'criterion']),
                ('Temperature and Reaction Feasibility',
                 'The signs of the enthalpy and entropy changes decide whether a reaction is '
                 'always, never or only at some temperatures feasible, with the crossover at '
                 'temperature equal to enthalpy change over entropy change.',
                 ['crossover temperature', 'enthalpy', 'entropy']),
                ('Standard Free Energy and the Equilibrium Constant',
                 'The standard free energy change equals minus RT times the natural logarithm '
                 'of K, so a large negative value corresponds to a large equilibrium '
                 'constant.',
                 ['free energy', 'equilibrium constant', 'standard']),
            ]),
        ],
    },
    {
        'unit': 'Electrochemistry',
        'about': ('Redox chemistry turned into electrical work: half-reactions, galvanic and '
                  'electrolytic cells, standard potentials, and how concentration changes the '
                  'voltage a cell delivers.'),
        'sections': [
            ('chemistry', '17-1-balancing-oxidation-reduction-reactions'),
            ('chemistry', '17-2-galvanic-cells'),
            ('chemistry', '17-3-standard-reduction-potentials'),
            ('chemistry', '17-4-the-nernst-equation'),
        ],
        'topics': [
            ('Redox Reactions', [
                ('Splitting a Redox Reaction into Half-Reactions',
                 'A redox reaction separates into an oxidation half-reaction and a reduction '
                 'half-reaction, each balanced for atoms and charge before they are combined.',
                 ['half-reaction', 'oxidation', 'reduction']),
                ('Balancing Redox in Acid and Base',
                 'Balancing in acidic solution adds water and hydrogen ions to equalise atoms '
                 'and charge, and in basic solution the same steps are followed before '
                 'hydrogen ions are replaced by hydroxide.',
                 ['balancing redox', 'acidic', 'basic']),
            ]),
            ('Electrochemical Cells', [
                ('Galvanic Cells and the Salt Bridge',
                 'In a galvanic cell oxidation occurs at the anode and reduction at the '
                 'cathode, electrons flow through the external circuit and ions carry charge '
                 'through the salt bridge.',
                 ['galvanic cell', 'anode', 'salt bridge']),
                ('Cell Notation and Electrolytic Cells',
                 'Cell notation places the anode on the left and the cathode on the right, '
                 'and an electrolytic cell uses an external supply to drive the reverse, '
                 'nonspontaneous reaction.',
                 ['cell notation', 'electrolytic', 'external supply']),
            ]),
            ('Cell Potential and Conditions', [
                ('Standard Reduction Potentials',
                 'A cell potential is the cathode reduction potential minus the anode '
                 'reduction potential, and a positive value means the cell reaction is '
                 'spontaneous under standard conditions.',
                 ['standard reduction potential', 'cell potential', 'cathode']),
                ('The Nernst Equation',
                 'Cell potential falls as the reaction quotient rises, following the Nernst '
                 'equation, which at 25 degrees Celsius reduces to the standard potential '
                 'minus 0.0592 over n times the logarithm of Q.',
                 ['nernst equation', 'concentration', 'cell potential']),
            ]),
        ],
    },
    {
        'unit': 'Nuclear Chemistry',
        'about': ('The nucleus as a source of energy: what makes a nucleus stable, the decay '
                  'modes and their equations, half-life as a clock, and the fission and '
                  'fusion processes behind nuclear power.'),
        'sections': [
            ('chemistry', '21-1-nuclear-structure-and-stability'),
            ('chemistry', '21-2-nuclear-equations'),
            ('chemistry', '21-3-radioactive-decay'),
            ('chemistry', '21-4-transmutation-and-nuclear-energy'),
        ],
        'topics': [
            ('Radioactivity and Nuclear Equations', [
                ('Nuclear Stability and Binding Energy',
                 'A nucleus is stable when the strong force outweighs proton repulsion, which '
                 'is why the neutron-to-proton ratio needed for stability rises with atomic '
                 'number and heavy nuclei decay.',
                 ['nuclear stability', 'binding energy', 'neutron ratio']),
                ('Alpha, Beta and Gamma Decay',
                 'Alpha decay lowers the mass number by four and the atomic number by two, '
                 'beta-minus decay raises the atomic number by one, and gamma emission '
                 'changes neither.',
                 ['alpha decay', 'beta decay', 'gamma']),
            ]),
            ('Half-Life and Nuclear Energy', [
                ('Half-Life of a Radionuclide',
                 'After n half-lives the fraction of a radionuclide remaining is one half '
                 'raised to n, so activity falls by half in every equal time interval.',
                 ['half-life', 'decay', 'fraction']),
                ('Fission and Fusion Energy',
                 'Fission splits a heavy nucleus and fusion joins light ones, and both release '
                 'energy because the products are more tightly bound than the reactants.',
                 ['fission', 'fusion', 'mass defect']),
            ]),
        ],
    },
    {
        'unit': 'Organic Chemistry',
        'about': ('Carbon chemistry: the hydrocarbon families, the functional groups that '
                  'define compound classes, the isomerism that multiplies formulas, and the '
                  'reaction and polymer patterns that follow from both.'),
        'sections': [
            ('chemistry', '20-1-hydrocarbons'),
            ('chemistry', '20-2-alcohols-and-ethers'),
            ('chemistry', '20-3-aldehydes-ketones-carboxylic-acids-and-esters'),
            ('chemistry', '20-4-amines-and-amides'),
        ],
        'topics': [
            ('Hydrocarbons', [
                ('Alkanes and Structural Isomerism',
                 'Alkanes are saturated hydrocarbons with the formula CnH2n+2, and from '
                 'butane onward the same formula admits branched isomers with different '
                 'boiling points.',
                 ['alkane', 'isomer', 'saturated']),
                ('Alkenes, Alkynes and Aromatic Rings',
                 'A carbon-carbon double or triple bond makes a hydrocarbon unsaturated, while '
                 'the delocalised six-electron ring of benzene makes it aromatic.',
                 ['alkene', 'alkyne', 'aromatic']),
            ]),
            ('Functional Groups and Isomerism', [
                ('Functional Group Families',
                 'A functional group is the reactive part of a molecule, and its identity '
                 'defines the family: hydroxyl for alcohols, carbonyl for ketones and '
                 'aldehydes, carboxyl for acids.',
                 ['functional group', 'hydroxyl', 'carboxyl']),
                ('Naming and Isomer Classes',
                 'An organic name takes the longest carbon chain as parent and adds suffixes '
                 'for the principal functional group, while constitutional isomers differ in '
                 'connectivity and stereoisomers differ only in spatial arrangement.',
                 ['iupac naming', 'constitutional isomer', 'stereoisomer']),
            ]),
            ('Organic Reactions and Polymers', [
                ('Substitution, Addition and Elimination',
                 'Alkanes react mainly by substitution, alkenes by addition across the double '
                 'bond, and alkyl halides by elimination to form an alkene.',
                 ['substitution', 'addition', 'elimination']),
                ('Addition and Condensation Polymers',
                 'An addition polymer links monomers through their double bonds, while a '
                 'condensation polymer forms by losing a small molecule such as water at each '
                 'new link.',
                 ['polymer', 'addition polymerization', 'condensation']),
            ]),
        ],
    },
]
