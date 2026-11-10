"""Organic Chemistry outline, in the shape ``scripts/course_pipeline.py`` expects.

A two-semester, seventeen-unit organic chemistry course written for this project: structure
and representation, acids and electronic effects, stereochemistry, mechanism and energy,
then the reaction families in the order a mechanism-first course teaches them --
radicals, alkenes and alkynes, substitution and elimination, spectroscopy, conjugation and
aromaticity, the aromatic and carbonyl reaction classes, enolates, amines, synthesis, and
finally the bioorganic and materials applications. Unit and topic names follow the course
plan; every summary below is an original statement written here, not textbook text, and
each names the condition under which its claim holds.

Textbook position. OpenStax's only organic title is *Organic Chemistry: A Tenth Edition*,
which reports CC BY-NC-SA 4.0. A non-commercial share-alike book cannot be stored, quoted
or used as a text anchor, and no CC BY organic textbook exists in the OpenStax catalogue,
so this module does not anchor to a book at all. Chemistry 1e is not a substitute: its
organic chapter is a functional-group survey and does not teach curved-arrow mechanisms,
which is the spine of this course. ``TEXTBOOK`` therefore declares
``no_cc_by_anchor = True`` with the reason, every unit carries an empty ``sections`` list,
and ``course_pipeline.py verify`` reports the anchoring check as SKIP with that reason
rather than a green tick it has not earned. The OpenStax organic title stays link-only: it
is named as a study reference and is never fetched, stored or quoted.

The pack is generated: ``organic_chemistry.json`` is rebuilt by the pipeline from this
module and must never be hand-edited.
"""

from __future__ import annotations

ID = 'organic_chemistry'
TITLE = 'Organic Chemistry'
SUBJECT = 'Chemistry'
SUBJECT_KIND = 'science'
EXPECTED_WEEKS = 36
COURSE_LINE = 'Organic Chemistry - Structure, Mechanism and Synthesis'
DESCRIPTION = (
    'A full-year organic chemistry course: structure, bonding and representation; acids, '
    'bases and electronic effects; isomerism, conformation and stereochemistry; '
    'curved-arrow mechanisms and reaction energy; then the reaction families in mechanism '
    'order -- alkanes and radicals, alkenes and alkynes, substitution and elimination, '
    'spectroscopy, conjugation and aromaticity, aromatic substitution, alcohols, ethers '
    'and sulfur compounds, carbonyl addition, acyl substitution, enolates and '
    'condensations, amines and heterocycles, multistep synthesis and retrosynthesis, and '
    'the bioorganic molecules, pericyclic reactions and polymers that close the course.')

TEXTBOOK = {
    'spine': '',
    'supplements': [],
    'link_only_note': ('OpenStax Organic Chemistry: A Tenth Edition reports CC BY-NC-SA 4.0 '
                       'and is carried as a link-only study reference: never stored or quoted.'),
    'no_cc_by_anchor': True,
    'reason': ('No CC BY organic chemistry textbook exists in the OpenStax catalogue '
               '(checked 2026-11-10; the only organic title is CC BY-NC-SA). The outline is '
               'an original CC0 scope and sequence and is not anchored to a textbook.'),
}

UNITS = [
    # ------------------------------------------------------------------ 1
    {
        'unit': 'Structure, Bonding, and Representations',
        'about': ('The entry unit: how an organic structure is drawn and read, how carbon '
                  'hybridises to give the shapes those drawings stand for, how formal charge '
                  'and resonance locate the electrons, and how a functional group names the '
                  'reactive part of a molecule.'),
        'sections': [],
        'topics': [
            ('Organic Representations', [
                ('Skeletal Structures and Implied Hydrogens',
                 'A skeletal structure omits the carbon labels and most of the hydrogens, so '
                 'every vertex and line end is a carbon carrying enough hydrogens to complete '
                 'four bonds, which is why a bare line is methane and a line ending in a '
                 'junction is a methyl-substituted carbon.',
                 ['skeletal structure', 'line-angle', 'hydrogen count']),
                ('Wedge and Dash Conventions',
                 'A solid wedge points a bond out of the page and a dashed wedge points it '
                 'behind the page, so the two drawings of one connectivity that differ only in '
                 'wedge placement are different stereoisomers rather than the same structure '
                 'redrawn.',
                 ['wedge dash', 'tetrahedral', 'perspective']),
                ('What a Molecular Formula Cannot Tell You',
                 'A molecular formula fixes only the atom counts, so C4H10O describes both '
                 'butan-1-ol and its ether isomer, and the formula alone can neither name the '
                 'compound nor predict its boiling point.',
                 ['molecular formula', 'connectivity', 'isomer count']),
            ]),
            ('Bonding and Hybridization', [
                ('sp3 Carbon and the Tetrahedral Frame',
                 'Four electron groups around carbon mix one s and three p orbitals into four '
                 'sp3 hybrids pointing at 109.5 degrees, which is why methane is tetrahedral '
                 'rather than square planar and why a saturated carbon has no accessible pi '
                 'bond.',
                 ['sp3', 'hybridization', 'tetrahedral']),
                ('sp2 and sp Carbon with Pi Bonds',
                 'An sp2 carbon keeps one unhybridised p orbital for a pi bond and places three '
                 'sigma bonds at 120 degrees, while an sp carbon is linear at 180 degrees with '
                 'two pi bonds, so a double bond fixes a plane and a triple bond fixes a line.',
                 ['sp2', 'sp', 'pi bond']),
                ('s Character Sets Bond Length and Acidity',
                 'More s character holds the bonding electrons closer to the nucleus, so a C-H '
                 'bond shortens and strengthens from sp3 to sp2 to sp, and the sp C-H of a '
                 'terminal alkyne is the most acidic of the three at pKa about 25.',
                 ['s character', 'bond length', 'acidity']),
            ]),
            ('Formal Charge and Resonance', [
                ('Formal Charge as Electron Bookkeeping',
                 'Formal charge is the valence electron count minus the nonbonding electrons '
                 'minus half the bonding electrons, so it identifies which of several valid '
                 'Lewis structures carries the smallest charge separation and therefore '
                 'contributes most.',
                 ['formal charge', 'lewis structure', 'charge separation']),
                ('Resonance Forms and the Weighted Hybrid',
                 'Resonance forms differ only in where pi and lone-pair electrons sit while '
                 'every nucleus stays fixed, so the molecule is a weighted hybrid in which each '
                 'bond order lies between the drawings and no single form is the real structure.',
                 ['resonance hybrid', 'delocalization', 'bond order']),
                ('Ranking Resonance Contributors',
                 'The contributor with complete octets, the fewest formal charges and any '
                 'negative charge on the more electronegative atom dominates the hybrid, which '
                 'is why the C-N bond of an amide is short and rotation about it is slow.',
                 ['resonance ranking', 'octet', 'amide resonance']),
            ]),
            ('Functional Groups', [
                ('Heteroatom Functional Groups',
                 'An alcohol, ether, amine and thiol each place a heteroatom on an sp3 carbon, '
                 'and that heteroatom\'s lone pairs and bond polarity decide whether the group '
                 'donates a hydrogen bond, accepts one, or acts as a nucleophile.',
                 ['heteroatom', 'alcohol', 'amine']),
                ('The Carbonyl Family',
                 'An aldehyde, ketone, ester, amide and carboxylic acid all share a C=O group, '
                 'and what else is attached to the carbonyl carbon decides whether the group is '
                 'attacked by a nucleophile or substituted at that carbon.',
                 ['carbonyl', 'aldehyde', 'carboxylic acid']),
                ('Functional Groups Set Physical Properties',
                 'Because the functional group fixes a molecule\'s polarity and hydrogen-bonding '
                 'capacity, it sets boiling point and water solubility more strongly than chain '
                 'length does, so ethanol boils 60 degrees above its ether isomer.',
                 ['boiling point', 'solubility', 'polarity']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 2
    {
        'unit': 'Acids, Bases, and Electronic Effects',
        'about': ('The electronic vocabulary every mechanism uses: proton and electron-pair '
                  'acidity, the inductive, hyperconjugative and resonance effects that move '
                  'electron density, the nucleophile-electrophile pair, and the intermolecular '
                  'forces those polarities produce.'),
        'sections': [],
        'topics': [
            ('Acid-Base Reasoning', [
                ('Bronsted and Lewis Acid-Base Pairs',
                 'A Bronsted acid donates a proton and a Lewis acid accepts an electron pair, so '
                 'every proton transfer is also a Lewis acid-base reaction and boron '
                 'trifluoride or a carbocation is an acid with no proton to give.',
                 ['bronsted acid', 'lewis acid', 'electron pair']),
                ('pKa as a Comparable Scale',
                 'pKa is the negative logarithm of the acid dissociation constant, so one unit '
                 'lower means a tenfold stronger acid, and comparing the pKa of the acid on each '
                 'side of a proton transfer predicts which direction the equilibrium favours.',
                 ['pka', 'acid strength', 'equilibrium']),
                ('Conjugate Base Stability Sets Acidity',
                 'An acid is stronger when its conjugate base spreads charge over more atoms or '
                 'holds it on a more electronegative atom, which is why acetic acid at pKa 4.8 '
                 'is a far stronger acid than ethanol at pKa 16.',
                 ['conjugate base', 'charge stabilization', 'acidity trend']),
            ]),
            ('Electronic Effects', [
                ('Inductive Withdrawal Through Sigma Bonds',
                 'An electronegative substituent pulls electron density through the sigma '
                 'framework, and the effect falls off steeply with distance, so a fluorine two '
                 'bonds from a carboxyl group raises acidity far more than one four bonds away.',
                 ['inductive effect', 'electronegativity', 'distance']),
                ('Hyperconjugation and Carbocation Stability',
                 'Adjacent C-H or C-C sigma bonds donate electron density into an empty p '
                 'orbital, so a tertiary carbocation is more stable than a secondary one and a '
                 'methyl group stabilises a double bond by the same overlap.',
                 ['hyperconjugation', 'carbocation', 'stability']),
                ('Resonance Donation and Withdrawal',
                 'A lone pair conjugated to a pi system donates electron density while a pi bond '
                 'conjugated to an electronegative atom withdraws it, so a methoxy group '
                 'activates an aromatic ring by resonance even though it withdraws by induction.',
                 ['resonance donation', 'mesomeric effect', 'activation']),
            ]),
            ('Nucleophiles and Electrophiles', [
                ('Nucleophilicity versus Basicity',
                 'Basicity measures affinity for a proton while nucleophilicity measures the '
                 'rate of attack on carbon, so the two diverge and iodide is a weak base yet a '
                 'strong nucleophile in a polar aprotic solvent because it is large and '
                 'polarisable.',
                 ['nucleophilicity', 'basicity', 'polarizability']),
                ('Electrophilic Carbon Sites',
                 'A nucleophile attacks a carbon that carries a partial positive charge, an '
                 'empty orbital or a polarisable halogen, so a carbonyl carbon and a carbocation '
                 'are attacked while an alkane carbon is not.',
                 ['electrophile', 'polarized bond', 'reactive site']),
                ('Solvent Effects on Nucleophilicity',
                 'A polar aprotic solvent leaves the nucleophile unsolvated and free to attack, '
                 'while a protic solvent hydrogen-bonds it, so the halide order runs '
                 'I > Br > Cl in acetone and reverses to Cl > Br > I in water.',
                 ['polar aprotic', 'protic solvent', 'solvation']),
            ]),
            ('Intermolecular Forces', [
                ('Dipole-Dipole Forces and Hydrogen Bonding',
                 'A hydrogen bond needs an O-H, N-H or F-H donor and a lone pair acceptor, so '
                 'ethanol boils at 78 degrees Celsius while its isomer dimethyl ether boils at '
                 'minus 24 degrees Celsius from dipole-dipole forces alone.',
                 ['hydrogen bond', 'dipole', 'boiling point']),
                ('Dispersion Forces and Molecular Shape',
                 'Dispersion forces grow with the surface area over which electrons can '
                 'fluctuate, so boiling point rises with chain length and a branched isomer '
                 'boils below its straight-chain counterpart of the same formula.',
                 ['dispersion', 'surface area', 'branching']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 3
    {
        'unit': 'Isomerism, Conformation, and Stereochemistry',
        'about': ('Why one formula can be many compounds: connectivity and naming first, then '
                  'the conformations a single molecule adopts by rotation, then the configurational '
                  'labels and isomer relationships that fix a three-dimensional structure.'),
        'sections': [],
        'topics': [
            ('Constitutional Isomerism and Nomenclature', [
                ('Connectivity Defines a Constitutional Isomer',
                 'Constitutional isomers share a molecular formula but differ in which atom is '
                 'bonded to which, so they are separate compounds with different boiling points '
                 'and spectra rather than one compound drawn two ways.',
                 ['constitutional isomer', 'connectivity', 'physical properties']),
                ('Choosing the Parent Chain',
                 'IUPAC rules take the longest carbon chain, then the chain with the most '
                 'substituents, then the one carrying the principal functional group, because '
                 'the parent name must identify the largest continuous framework.',
                 ['iupac', 'parent chain', 'substituent']),
                ('Numbering and Alphabetical Order',
                 'Numbering starts at the end that gives the principal group the lowest locant '
                 'and then the lowest set of locants, while substituents are listed '
                 'alphabetically regardless of the numbers they carry.',
                 ['numbering', 'locant', 'alphabetical order']),
            ]),
            ('Conformational Analysis', [
                ('Ethane and Butane Rotamers',
                 'Rotation about a C-C single bond is fast at room temperature and passes through '
                 'eclipsed and staggered conformations with a 12 kJ/mol barrier in ethane, while '
                 'butane\'s anti conformer lies about 3.8 kJ/mol below gauche because its methyl '
                 'groups avoid eclipsing.',
                 ['conformation', 'eclipsed', 'gauche']),
                ('Cyclohexane Chairs and the Ring Flip',
                 'Cyclohexane adopts a chair in which every bond is staggered, and a ring flip '
                 'converts each axial substituent into an equatorial one, so the more stable '
                 'chair places the larger group equatorial to avoid 1,3-diaxial interactions.',
                 ['chair conformation', 'ring flip', 'diaxial interaction']),
                ('Ring Strain in Small Cycloalkanes',
                 'Cyclopropane and cyclobutane cannot reach tetrahedral angles and must eclipse '
                 'their bonds, so their angle and torsional strain makes them far more reactive '
                 'toward ring-opening than unstrained cyclohexane.',
                 ['ring strain', 'angle strain', 'cycloalkane']),
            ]),
            ('Configuration Labels', [
                ('Stereocenters and Molecular Chirality',
                 'A carbon bearing four different groups is a stereocenter, and a molecule with '
                 'exactly one such center is chiral because no rotation can superpose it on its '
                 'mirror image.',
                 ['stereocenter', 'chirality', 'mirror image']),
                ('Assigning R and S',
                 'Priorities follow atomic number, and once the lowest-priority group points '
                 'away a clockwise 1-2-3 sequence is R and a counter-clockwise one is S, so the '
                 'label fixes the arrangement however the drawing is rotated.',
                 ['r s configuration', 'cip priority', 'stereocenter']),
                ('E and Z Labels for Alkenes',
                 'When each alkene carbon carries two different groups, the higher-priority group '
                 'on each carbon decides E when the two lie opposite and Z when they lie '
                 'together, so the label is required where cis and trans would be ambiguous.',
                 ['e z isomerism', 'alkene geometry', 'cip priority']),
            ]),
            ('Stereoisomer Relationships', [
                ('Enantiomers and Diastereomers',
                 'Enantiomers are non-superposable mirror images that differ at every '
                 'stereocenter, while diastereomers differ at some but not all of them and are '
                 'therefore separated by ordinary physical methods because their properties '
                 'differ.',
                 ['enantiomer', 'diastereomer', 'stereoisomer']),
                ('Meso Compounds and Optical Activity',
                 'A molecule whose stereocenters are related by an internal mirror plane is '
                 'achiral overall, so a meso compound is optically inactive although it contains '
                 'stereocenters, whereas a single enantiomer rotates plane-polarised light.',
                 ['meso', 'optical activity', 'internal symmetry']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 4
    {
        'unit': 'Mechanisms, Energy, and Reaction Strategy',
        'about': ('How organic reactions are written and argued about: the curved arrow as the '
                  'unit of mechanism, the energy surface that decides rate, the selectivity and '
                  'rearrangements that follow from competing pathways, and the strategic choices '
                  'that come before any arrow is drawn.'),
        'sections': [],
        'topics': [
            ('Curved-Arrow Mechanisms', [
                ('Curved Arrows Track Electron Pairs',
                 'An arrow starts at a lone pair or a bond and ends where that pair goes, so a '
                 'full arrow moves two electrons while a half arrow moves one, which is why an '
                 'arrow never starts at an atom or at a positive charge.',
                 ['curved arrow', 'electron pair', 'mechanism']),
                ('Proton Transfers as Paired Arrows',
                 'A proton transfer is drawn as one arrow from the base\'s lone pair to the '
                 'hydrogen and a second from the breaking bond to the acid, so the products '
                 'emerge as a conjugate acid and a conjugate base rather than as neutral '
                 'fragments.',
                 ['proton transfer', 'conjugate acid', 'arrow pushing']),
                ('Checking a Step by Mass and Charge',
                 'A valid step conserves mass and charge, so a charged species on one side '
                 'requires a charged species on the other and any carbon drawn with five bonds '
                 'marks an error rather than a fast reaction.',
                 ['charge balance', 'arrow check', 'valence']),
            ]),
            ('Reaction Energy and Rates', [
                ('Energy Diagrams and Activation Energy',
                 'A reaction coordinate diagram plots free energy against progress, and the '
                 'height of the highest barrier above the starting material sets the activation '
                 'energy that controls the rate rather than the overall free-energy change.',
                 ['energy diagram', 'activation energy', 'reaction coordinate']),
                ('Hammond Postulate and Transition-State Shape',
                 'A transition state resembles the species it is closer to in energy, so an '
                 'endothermic step has a product-like transition state and an exothermic step a '
                 'reactant-like one, which is why carbocation formation looks like the cation.',
                 ['hammond postulate', 'transition state', 'endothermic']),
                ('Rate Law as Mechanistic Evidence',
                 'The rate law reports which species are present in the transition state of the '
                 'slow step, so a reaction first order in both substrate and nucleophile cannot '
                 'have a rate-determining step that excludes the nucleophile, which is how SN1 '
                 'and SN2 are distinguished.',
                 ['rate law', 'rate-determining step', 'kinetic evidence']),
            ]),
            ('Selectivity and Rearrangements', [
                ('Kinetic versus Thermodynamic Control',
                 'When the reaction is reversible, the product that forms fastest dominates under '
                 'kinetic control at low temperature while the more stable product dominates at '
                 'equilibrium, which is why an enolate can be trapped either way.',
                 ['kinetic control', 'thermodynamic control', 'reversibility']),
                ('Carbocation Rearrangements',
                 'A 1,2-hydride or alkyl shift moves a group with its electron pair to an '
                 'adjacent carbocation when that gives a more stable cation, so a secondary '
                 'cation next to a quaternary centre can rearrange before the nucleophile '
                 'arrives.',
                 ['rearrangement', 'hydride shift', 'carbocation']),
            ]),
            ('Reaction Strategy', [
                ('Functional Group Interconversion',
                 'A synthesis moves a molecule between functional-group levels, so an alcohol, an '
                 'alkyl halide and an alkene are interconverted in a planned order rather than '
                 'chosen at random for each step.',
                 ['functional group interconversion', 'synthesis', 'retrosynthesis']),
                ('Chemoselectivity: Reacting One Group and Sparing Another',
                 'A reagent is chosen for the group it attacks, so sodium borohydride reduces a '
                 'ketone in the presence of an ester while lithium aluminium hydride reduces '
                 'both, which makes the milder reagent the selective one.',
                 ['chemoselectivity', 'reagent choice', 'compatibility']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 5
    {
        'unit': 'Alkanes, Cycloalkanes, and Radical Chemistry',
        'about': ('The saturated framework and the one mechanistic channel it has: alkane and '
                  'cycloalkane properties, then radical chains, where the same propagation step '
                  'explains why chlorination is fast and unselective while bromination is slow '
                  'and selective.'),
        'sections': [],
        'topics': [
            ('Alkanes and Cycloalkanes', [
                ('Why Alkanes Are Unreactive',
                 'An alkane contains only strong, nonpolar sigma bonds and no lone pair or empty '
                 'orbital, so it offers no electrophilic or nucleophilic site and reacts by '
                 'radical substitution rather than by the ionic addition an alkene undergoes.',
                 ['alkane', 'sigma bond', 'unreactive']),
                ('Physical Properties of Alkanes',
                 'Alkanes interact only by dispersion forces, so they are insoluble in water and '
                 'their boiling points rise smoothly with carbon number while branching lowers '
                 'the boiling point at a fixed formula.',
                 ['alkane', 'dispersion', 'boiling point']),
                ('Cycloalkane Strain and Ring Opening',
                 'A cycloalkane carries two fewer hydrogens per ring than its open-chain '
                 'analogue, and because the ring constrains its bond angles, cyclopropane opens '
                 'readily under addition while cyclohexane behaves like an unstrained alkane.',
                 ['cycloalkane', 'ring strain', 'ring opening']),
            ]),
            ('Radical Reactions', [
                ('Initiation, Propagation, and Termination',
                 'Light or heat splits a halogen into two radicals, each propagation step '
                 'consumes one radical and returns another, and two radicals combining ends the '
                 'chain, which is why a radical chain needs only a trace of initiator.',
                 ['radical chain', 'propagation', 'initiation']),
                ('Chlorination: Fast and Poorly Selective',
                 'Chlorine abstraction of a hydrogen is early and exothermic, so its transition '
                 'state is reactant-like and the tertiary product only modestly predominates '
                 'over the primary one.',
                 ['chlorination', 'selectivity', 'exothermic']),
                ('Bromination: Slow and Highly Selective',
                 'Bromine abstraction is late and endothermic, so its transition state resembles '
                 'the radical and the stability of that radical dominates the outcome, which is '
                 'why bromination gives the tertiary bromide almost exclusively.',
                 ['bromination', 'selectivity', 'radical stability']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 6
    {
        'unit': 'Alkenes and Alkynes',
        'about': ('The pi bond as the reactive centre: the addition reactions that convert it to '
                  'sigma bonds, the extra reactivity of a triple bond, and the synthesis routes '
                  'that build a pi bond where a target needs one.'),
        'sections': [],
        'topics': [
            ('Alkene Addition Reactions', [
                ('Markovnikov Addition of Hydrogen Halides',
                 'Protonation gives the more stable carbocation, so the hydrogen adds to the '
                 'carbon that already carries more hydrogens and the halide to the other, while '
                 'a peroxide medium reverses the regiochemistry by making the first step radical.',
                 ['markovnikov', 'hydrohalogenation', 'regiochemistry']),
                ('Hydroboration-Oxidation',
                 'Borane adds in one concerted step with boron to the less hindered carbon, so '
                 'hydroboration followed by oxidation gives the anti-Markovnikov alcohol without '
                 'a carbocation and therefore without rearrangement.',
                 ['hydroboration', 'anti-markovnikov', 'syn addition']),
                ('Halogenation through a Bridged Ion',
                 'Bromine adds as a bridged bromonium ion that blocks one face, so the second '
                 'bromide must attack the opposite face and the product is anti, and in water '
                 'the solvent competes to give a halohydrin instead.',
                 ['bromonium ion', 'anti addition', 'halohydrin']),
            ]),
            ('Alkyne Reactions', [
                ('Terminal Alkyne Acidity and Acetylides',
                 'The sp C-H of a terminal alkyne has a pKa near 25, so amide deprotonates it '
                 'essentially completely and the resulting acetylide attacks alkyl halides or '
                 'carbonyls, which makes it a carbon nucleophile that adds a two-carbon unit.',
                 ['terminal alkyne', 'acetylide', 'deprotonation']),
                ('Partial Reduction to cis or trans Alkenes',
                 'Hydrogenation over a poisoned Lindlar catalyst stops at the cis alkene because '
                 'the surface no longer adsorbs it, while sodium in liquid ammonia delivers the '
                 'trans alkene through a radical-anion intermediate.',
                 ['lindlar catalyst', 'dissolving metal reduction', 'alkene geometry']),
                ('Double Addition to a Triple Bond',
                 'An alkyne adds two equivalents of hydrogen halide because the first addition '
                 'gives a vinyl halide that is still an alkene, and the second follows '
                 'Markovnikov\'s rule to place both halides on the same carbon.',
                 ['alkyne addition', 'vinyl halide', 'geminal dihalide']),
            ]),
            ('Pi-Bond Synthesis and Strategy', [
                ('Alkene Synthesis by Elimination',
                 'A strong base removes a beta hydrogen anti to the leaving group, so an alkyl '
                 'halide or a protonated alcohol becomes an alkene and the position of the double '
                 'bond is set by which beta hydrogen is removed.',
                 ['elimination', 'beta hydrogen', 'alkene synthesis']),
                ('Wittig Olefination of a Carbonyl',
                 'A phosphonium ylide attacks a carbonyl to form an oxaphosphetane that collapses '
                 'to an alkene and triphenylphosphine oxide, so the new C=C is built exactly '
                 'where the C=O stood.',
                 ['wittig', 'ylide', 'carbonyl olefination']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 7
    {
        'unit': 'Substitution and Elimination',
        'about': ('The four pathways that compete at an sp3 carbon: SN2 and SN1 substitution, E1 '
                  'and E2 elimination, and the substrate, nucleophile, base, solvent and '
                  'temperature rules that predict which one wins.'),
        'sections': [],
        'topics': [
            ('SN2 Reactions', [
                ('SN2 Is Concerted and Inverts',
                 'SN2 is one step with inversion because the nucleophile attacks opposite the '
                 'leaving group as it departs, so the rate depends on both concentrations and '
                 'the product has the opposite configuration at the carbon.',
                 ['sn2', 'backside attack', 'inversion']),
                ('Steric Access at the Electrophilic Carbon',
                 'Backside attack needs an open face, so SN2 is fastest at methyl and primary '
                 'carbons and effectively stops at a tertiary one, which is why a neopentyl '
                 'halide reacts far more slowly than an ordinary primary halide.',
                 ['steric hindrance', 'substrate order', 'neopentyl']),
                ('Leaving-Group Ability and Rate',
                 'A better leaving group lowers the barrier because its bond breaks as the '
                 'nucleophile arrives, so iodide and a tosylate react far faster than fluoride '
                 'or hydroxide under the same conditions.',
                 ['leaving group', 'tosylate', 'reaction rate']),
            ]),
            ('SN1 Reactions', [
                ('SN1 Ionisation Precedes Capture',
                 'SN1 proceeds by rate-limiting ionisation to a carbocation followed by '
                 'nucleophilic capture, so the rate depends only on the substrate and the '
                 'nucleophile enters after the slow step.',
                 ['sn1', 'ionization', 'carbocation']),
                ('Carbocation Stability Sets the SN1 Rate',
                 'Because the cation forms in the rate-determining step, SN1 rates track '
                 'carbocation stability, so a tertiary halide reacts orders of magnitude faster '
                 'than a primary one that would have to form an unstable cation.',
                 ['carbocation stability', 'tertiary halide', 'solvolysis']),
                ('Racemisation and Solvent Assistance',
                 'A planar carbocation can be attacked from either face, so SN1 gives '
                 'racemisation with some net inversion because the departing group partly shields '
                 'its own side, and a protic solvent stabilises the separating charges.',
                 ['racemization', 'protic solvent', 'ionization']),
            ]),
            ('E1 and E2 Reactions', [
                ('E2 Needs an Anti-Periplanar Beta Hydrogen',
                 'E2 removes the beta hydrogen and the leaving group together from an '
                 'anti-periplanar arrangement, so a rigid ring that cannot place them anti '
                 'eliminates slowly or gives the less substituted alkene.',
                 ['e2', 'anti-periplanar', 'stereospecificity']),
                ('Zaitsev Preference and Alkene Stability',
                 'With more than one beta hydrogen available, E2 gives mainly the more '
                 'substituted alkene because the developing double bond is stabilised, while a '
                 'bulky base or a poor anti arrangement can override that preference.',
                 ['zaitsev rule', 'alkene stability', 'bulky base']),
                ('E1 through the Shared Carbocation',
                 'E1 shares SN1\'s ionisation step and then loses a beta proton, so it '
                 'accompanies SN1, is favoured by heat, and yields the more substituted alkene '
                 'from the same carbocation.',
                 ['e1', 'carbocation', 'heat']),
            ]),
            ('Substitution-Elimination Competition', [
                ('Substrate and Base Choose the Pathway',
                 'Methyl and primary substrates with a strong nucleophile substitute by SN2, a '
                 'tertiary substrate ionises toward SN1 or E1, and a strong bulky base drives E2 '
                 'even at a secondary carbon.',
                 ['competition', 'substrate', 'base strength']),
                ('Heat Favours Elimination',
                 'Elimination converts one molecule into two and relieves steric crowding, so '
                 'raising the temperature shifts the mixture toward the alkene while a low '
                 'temperature favours substitution.',
                 ['temperature', 'entropy', 'product ratio']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 8
    {
        'unit': 'Spectroscopy and Structure Determination',
        'about': ('How an unknown structure is proved rather than guessed: the molecular ion and '
                  'fragments from mass spectrometry, functional groups from infrared absorption, '
                  'the hydrogen and carbon framework from NMR, and the order in which the four '
                  'are combined.'),
        'sections': [],
        'topics': [
            ('Mass Spectrometry', [
                ('The Molecular Ion and Molar Mass',
                 'Electron impact removes one electron to give a radical cation whose mass-to-'
                 'charge ratio is the molecular mass, and an odd nominal mass flags an odd number '
                 'of nitrogen atoms in the molecule.',
                 ['mass spectrometry', 'molecular ion', 'molar mass']),
                ('Fragmentation and Isotope Patterns',
                 'A molecule fragments at its weakest bonds, so losing 15 or 29 mass units marks a '
                 'methyl or ethyl group, and an M+2 peak about a third the height of M marks one '
                 'chlorine while a nearly equal M+2 marks one bromine.',
                 ['fragmentation', 'isotope pattern', 'halogen']),
            ]),
            ('Infrared Spectroscopy', [
                ('The Functional-Group Region',
                 'Absorption between 4000 and 1500 cm-1 marks specific bonds, so a broad band near '
                 '3300 cm-1 is an O-H, a sharp band near 1700 cm-1 a carbonyl, and a band '
                 'between 2100 and 2260 cm-1 a triple bond.',
                 ['infrared', 'wavenumber', 'functional group']),
                ('Carbonyl Frequency Reports Its Environment',
                 'A carbonyl stretches at higher frequency when its bond order rises, so an acid '
                 'chloride absorbs near 1800 cm-1 while an amide absorbs near 1650 cm-1 because '
                 'nitrogen donation lowers the C=O bond order.',
                 ['carbonyl stretch', 'bond order', 'amide']),
            ]),
            ('NMR Spectroscopy', [
                ('Chemical Shift Reports the Electronic Environment',
                 'Electron-withdrawing groups deshield nearby protons and move them downfield, so '
                 'an alkane proton appears near 1 ppm, a proton on a carbon bearing oxygen near '
                 '3.5 to 4 ppm, and an aromatic proton near 7 to 8 ppm from the ring current.',
                 ['chemical shift', 'deshielding', 'ppm']),
                ('Integration and the n+1 Splitting Rule',
                 'Integration is proportional to the number of equivalent protons and n equivalent '
                 'neighbours split a signal into n+1 peaks, so an ethyl group appears as a '
                 'triplet and a quartet that integrate in a 3 to 2 ratio.',
                 ['integration', 'splitting', 'n plus one']),
                ('Carbon-13 Signals and Molecular Symmetry',
                 'Carbon-13 NMR gives one signal per distinct carbon environment, so the number of '
                 'signals counts the symmetry-unique carbons and a molecule with a mirror plane '
                 'shows fewer signals than it has carbon atoms.',
                 ['carbon-13 nmr', 'symmetry', 'signal count']),
            ]),
            ('Combined Structure Determination', [
                ('Degrees of Unsaturation Constrain the Structure',
                 'Degrees of unsaturation count rings and pi bonds together, computed from the '
                 'formula as (2C + 2 + N - H - X)/2, so a formula with four degrees of '
                 'unsaturation can be a benzene ring but not an acyclic alkene.',
                 ['degrees of unsaturation', 'molecular formula', 'rings']),
                ('Assembling a Structure from Orthogonal Evidence',
                 'Each technique answers a different question, so mass spectrometry gives the '
                 'formula, infrared identifies the functional group and NMR fixes the '
                 'connectivity, and a proposed structure must satisfy every spectrum at once.',
                 ['structure elucidation', 'evidence', 'spectra']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 9
    {
        'unit': 'Conjugation and Aromaticity',
        'about': ('What happens when pi bonds talk to each other: delocalisation over conjugated '
                  'systems and its spectroscopic signature, then the Huckel count that separates '
                  'aromatic, antiaromatic and merely nonaromatic rings.'),
        'sections': [],
        'topics': [
            ('Conjugated Systems', [
                ('Conjugation Extends the Pi System',
                 'Two pi bonds separated by a single sigma bond share electron density through '
                 'overlapping p orbitals, which narrows the gap between the highest occupied and '
                 'lowest unoccupied orbitals and shifts absorption to a longer wavelength.',
                 ['conjugation', 'homo lumo gap', 'delocalization']),
                ('Allylic Resonance and Its Consequences',
                 'A radical, cation or anion next to a double bond is delocalised over both ends, '
                 'so an allylic carbocation is far more stable than an isolated one and attack at '
                 'the allylic position can give two isomeric products.',
                 ['allylic', 'resonance', 'carbocation']),
                ('Ultraviolet Absorption and Conjugation Length',
                 'The longer the conjugated system the smaller the orbital gap and the longer the '
                 'absorbed wavelength, which is why ethene absorbs in the far ultraviolet while '
                 'carotene absorbs blue light and therefore appears orange.',
                 ['ultraviolet', 'conjugation length', 'chromophore']),
            ]),
            ('Aromaticity', [
                ('Huckel\'s 4n+2 Rule',
                 'A planar, fully conjugated ring with 4n+2 pi electrons is aromatic because that '
                 'count exactly fills every bonding pi orbital, so benzene with six and the '
                 'cyclopentadienyl anion with six are aromatic.',
                 ['huckel rule', 'aromatic', 'pi electrons']),
                ('Benzene\'s Delocalisation Energy',
                 'Benzene shares its six pi electrons equally over the ring, and the resulting '
                 'resonance energy of about 150 kJ/mol makes it far more stable and far less '
                 'reactive toward addition than a hypothetical cyclohexatriene would be.',
                 ['benzene', 'resonance energy', 'stability']),
                ('Antiaromatic and Nonaromatic Rings',
                 'The same ring with 4n pi electrons is antiaromatic and strongly destabilised if '
                 'it stays planar, but if it puckers out of planarity it becomes nonaromatic, '
                 'which is why cyclooctatetraene adopts a tub shape and behaves like an ordinary '
                 'polyene.',
                 ['antiaromatic', 'nonaromatic', 'cyclooctatetraene']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 10
    {
        'unit': 'Aromatic Reactions',
        'about': ('The characteristic reaction of an aromatic ring: substitution that restores '
                  'the aromatic sextet, the substituent effects that decide rate and position, '
                  'and the sequencing rules that turn those effects into a synthesis.'),
        'sections': [],
        'topics': [
            ('Electrophilic Aromatic Substitution', [
                ('The Arenium Ion Mechanism',
                 'Electrophilic aromatic substitution replaces a ring hydrogen in two steps: the '
                 'electrophile adds to give a resonance-stabilised arenium ion, then a base '
                 'removes the proton to restore aromaticity, which is why substitution rather '
                 'than addition is observed.',
                 ['electrophilic aromatic substitution', 'arenium ion', 'aromaticity']),
                ('Activating and Deactivating Substituents',
                 'An electron-donating substituent stabilises the arenium ion and accelerates '
                 'substitution while an electron-withdrawing one destabilises it and slows the '
                 'reaction, so toluene reacts faster than benzene and nitrobenzene far slower.',
                 ['activating group', 'deactivating group', 'reaction rate']),
                ('Directing Effects Follow Intermediate Stability',
                 'An ortho-para director donates electron density or stabilises the arenium ion at '
                 'those positions, a meta director withdraws density and leaves the meta '
                 'positions least destabilised, and a halogen is the exception that deactivates '
                 'while still directing ortho and para.',
                 ['directing effect', 'ortho para', 'meta director']),
            ]),
            ('Aromatic Synthesis', [
                ('Limits of Friedel-Crafts Reactions',
                 'Friedel-Crafts alkylation fails on a deactivated ring and suffers from '
                 'carbocation rearrangement and polyalkylation, whereas acylation avoids both '
                 'because the acyl cation does not rearrange and the product ring is deactivated.',
                 ['friedel-crafts', 'acylation', 'limitations']),
                ('Sequencing Substituents on a Ring',
                 'Because each substituent directs the next one, a synthesis installs activating '
                 'groups before deactivating ones and introduces a group that must later be '
                 'converted, such as a nitro group reduced to an amine, at the point where its '
                 'directing effect is wanted.',
                 ['synthesis planning', 'directing group', 'sequence']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 11
    {
        'unit': 'Alcohols, Phenols, Ethers, Epoxides, and Sulfur Compounds',
        'about': ('The oxygen and sulfur families: the acidity and hydrogen bonding of alcohols '
                  'and phenols, the oxidation levels those groups sit between, the substitution '
                  'chemistry of ethers and epoxides, and the protecting-group logic sulfur makes '
                  'possible.'),
        'sections': [],
        'topics': [
            ('Alcohols and Phenols', [
                ('Hydrogen Bonding Sets Alcohol Properties',
                 'The O-H group both donates and accepts hydrogen bonds, so an alcohol boils far '
                 'above the ether or alkane of similar mass and a small alcohol mixes with water '
                 'in all proportions.',
                 ['hydrogen bonding', 'alcohol', 'boiling point']),
                ('Alcohol Acidity and Alkoxide Formation',
                 'An alcohol has a pKa near 16 and is deprotonated only by a stronger base such '
                 'as sodium hydride or an alkyllithium, so hydroxide leaves it largely intact and '
                 'an alkoxide must be made deliberately.',
                 ['alcohol acidity', 'alkoxide', 'base strength']),
                ('Phenol Acidity from Ring Delocalisation',
                 'A phenoxide ion spreads its negative charge into the ring, so phenol has a pKa '
                 'near 10 and dissolves in sodium hydroxide, and an electron-withdrawing '
                 'substituent on the ring raises that acidity further.',
                 ['phenol', 'phenoxide', 'acidity']),
            ]),
            ('Oxidation and Reduction', [
                ('Selective Oxidation of Alcohols',
                 'PCC oxidises a primary alcohol only to the aldehyde because it is used under '
                 'anhydrous conditions, aqueous Jones reagent carries it on to the carboxylic '
                 'acid, and a secondary alcohol gives a ketone under either.',
                 ['oxidation', 'pcc', 'jones reagent']),
                ('Hydride Reagents and Their Scope',
                 'Sodium borohydride reduces aldehydes and ketones but leaves esters and amides, '
                 'while lithium aluminium hydride reduces esters, acids and amides as well, so '
                 'the milder reagent is chosen when another group must survive.',
                 ['hydride reduction', 'sodium borohydride', 'lithium aluminium hydride']),
            ]),
            ('Ethers and Epoxides', [
                ('Williamson Ether Synthesis',
                 'An alkoxide attacks an unhindered primary alkyl halide by SN2 to give an ether, '
                 'and the method fails with a tertiary halide because elimination takes over '
                 'instead of substitution.',
                 ['williamson synthesis', 'ether', 'sn2']),
                ('Regiochemistry of Epoxide Opening',
                 'Base opens an epoxide at the less hindered carbon by SN2 while acid opens it at '
                 'the carbon that better stabilises positive charge, so the two conditions give '
                 'opposite products from the same epoxide.',
                 ['epoxide', 'ring opening', 'regiochemistry']),
            ]),
            ('Sulfur Compounds and Protecting Groups', [
                ('Thiols and Thioethers',
                 'Sulfur is larger and more polarisable than oxygen, so a thiol is more acidic, a '
                 'better nucleophile and a better leaving group than the matching alcohol, and it '
                 'is readily oxidised to a disulfide.',
                 ['thiol', 'thioether', 'polarizability']),
                ('Protecting Groups in Practice',
                 'A protecting group temporarily masks a reactive site, so a ketone is carried '
                 'through a Grignard addition as an acetal and an alcohol as a silyl ether, and '
                 'each is removed under conditions the rest of the molecule survives.',
                 ['protecting group', 'acetal', 'silyl ether']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 12
    {
        'unit': 'Aldehydes and Ketones: Carbonyl Addition',
        'about': ('The carbonyl as an electrophile: why the C=O carbon is attacked, how sterics '
                  'and electronics rank aldehyde against ketone, and the addition reactions that '
                  'convert the carbonyl into an alcohol, an acetal or an imine.'),
        'sections': [],
        'topics': [
            ('Carbonyl Structure and Reactivity', [
                ('The Polarised Carbonyl Bond',
                 'Oxygen is more electronegative than carbon, so the C=O bond leaves a partial '
                 'positive carbon that a nucleophile attacks along a trajectory perpendicular to '
                 'the pi system, which is why hydride and Grignard reagents add there.',
                 ['carbonyl', 'polarization', 'nucleophilic addition']),
                ('Steric and Electronic Control of Addition',
                 'An aldehyde is more reactive than a ketone because it is less hindered and less '
                 'electron-rich, so a limiting reagent adds to the aldehyde first, and an '
                 'adjacent electron-withdrawing group makes a carbonyl more electrophilic still.',
                 ['aldehyde', 'ketone', 'reactivity order']),
                ('Reversible and Irreversible Addition',
                 'Addition of a strong nucleophile such as a Grignard reagent is irreversible, '
                 'whereas addition of an alcohol or an amine is reversible, so those products '
                 'follow an equilibrium that can be driven by removing water.',
                 ['reversible addition', 'equilibrium', 'grignard']),
            ]),
            ('Aldehyde and Ketone Additions', [
                ('Hydride and Organometallic Additions',
                 'Hydride from borohydride or a carbanion from a Grignard reagent adds to the '
                 'carbonyl carbon and gives an alcohol after aqueous workup, and a Grignard cannot '
                 'be used on a molecule that still carries an acidic proton.',
                 ['grignard', 'hydride', 'workup']),
                ('Hemiacetals, Acetals, and Their Equilibrium',
                 'An alcohol adds reversibly to a carbonyl to give a hemiacetal, and acid '
                 'catalyses replacement of the hydroxyl by a second alkoxy group to give an '
                 'acetal, which is stable to base and therefore useful as a protected carbonyl.',
                 ['hemiacetal', 'acetal', 'acid catalysis']),
                ('Imine and Enamine Formation',
                 'An amine condenses with a carbonyl under mildly acidic conditions to give an '
                 'imine after water is lost, and a secondary amine stops at an enamine because it '
                 'has no N-H left to eliminate.',
                 ['imine', 'enamine', 'condensation']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 13
    {
        'unit': 'Carboxylic Acids and Derivatives: Acyl Substitution',
        'about': ('The acyl carbon and its leaving group: why a carboxylic acid is acidic, how a '
                  'nitrile is hydrolysed to one, and why acid chlorides, anhydrides, esters and '
                  'amides interconvert in a strict reactivity order.'),
        'sections': [],
        'topics': [
            ('Carboxylic Acids and Nitriles', [
                ('Carboxylate Resonance and Acidity',
                 'The carboxylate ion spreads its negative charge over two equivalent oxygens, so '
                 'a carboxylic acid has a pKa near 5 and is deprotonated by bicarbonate, which '
                 'distinguishes it from an alcohol or a phenol.',
                 ['carboxylic acid', 'carboxylate', 'acidity']),
                ('Nitrile Synthesis and Hydrolysis',
                 'A nitrile is made by SN2 displacement with cyanide on a primary halide and '
                 'hydrolyses through an amide to a carboxylic acid in hot aqueous acid or base, '
                 'so the sequence lengthens a chain by one carbon.',
                 ['nitrile', 'cyanide', 'hydrolysis']),
                ('Substituent Effects on Acid Strength',
                 'An electron-withdrawing group stabilises the carboxylate and raises acidity, so '
                 'trichloroacetic acid is far stronger than acetic acid, and the effect weakens '
                 'as the substituent moves further from the carboxyl group.',
                 ['substituent effect', 'trichloroacetic acid', 'induction']),
            ]),
            ('Nucleophilic Acyl Substitution', [
                ('Addition-Elimination at the Acyl Carbon',
                 'A nucleophile adds to the acyl carbon to give a tetrahedral intermediate, and '
                 'the carbonyl reforms by expelling the best leaving group, so the net result '
                 'replaces the group on the carbonyl rather than the oxygen.',
                 ['acyl substitution', 'tetrahedral intermediate', 'leaving group']),
                ('Reactivity Order of Acid Derivatives',
                 'Reactivity falls from acid chloride to anhydride to ester to amide as the '
                 'attached group donates more electron density into the carbonyl, so an acid '
                 'chloride converts an amine, an alcohol or a carboxylate into the matching '
                 'amide, ester or anhydride.',
                 ['acid chloride', 'reactivity order', 'interconversion']),
                ('Ester Hydrolysis and Saponification',
                 'An ester hydrolyses by base-promoted addition-elimination, and because the '
                 'carboxylate product is not attacked further, saponification with hydroxide is '
                 'irreversible and consumes a full equivalent of base.',
                 ['ester hydrolysis', 'saponification', 'irreversible']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 14
    {
        'unit': 'Enols, Enolates, and Condensations',
        'about': ('The chemistry of the alpha carbon: why an alpha hydrogen is acidic, how the '
                  'resulting enolate attacks a carbonyl, and the aldol, Claisen and conjugate '
                  'additions that build carbon skeletons with it.'),
        'sections': [],
        'topics': [
            ('Enols and Enolates', [
                ('Alpha-Hydrogen Acidity',
                 'A hydrogen on the carbon next to a carbonyl is acidic because the resulting '
                 'enolate delocalises its charge onto oxygen, so a ketone has an alpha pKa near '
                 '20 and only a base stronger than that deprotonates it completely.',
                 ['alpha hydrogen', 'enolate', 'pka']),
                ('Keto-Enol Tautomerism',
                 'The keto and enol forms interconvert by a proton transfer coupled to a pi-bond '
                 'shift, and the keto form usually dominates at equilibrium although the enol is '
                 'the species that reacts in halogenation and in acid-catalysed racemisation.',
                 ['tautomerism', 'enol', 'equilibrium']),
            ]),
            ('Aldol Reactions', [
                ('Aldol Addition and Condensation',
                 'An enolate attacks another carbonyl to give a beta-hydroxy carbonyl, and heating '
                 'dehydrates it to an alpha,beta-unsaturated carbonyl because the new double bond '
                 'is conjugated with the existing one.',
                 ['aldol', 'beta-hydroxy carbonyl', 'dehydration']),
                ('Crossed and Directed Aldol Strategies',
                 'A crossed aldol between two different carbonyls gives mixtures unless one '
                 'partner has no alpha hydrogens and is added slowly to the other\'s enolate, '
                 'which is why benzaldehyde is a common electrophilic partner.',
                 ['crossed aldol', 'directed aldol', 'benzaldehyde']),
            ]),
            ('Claisen and Related Condensations', [
                ('The Claisen Condensation',
                 'Two esters condense when one is deprotonated to an enolate that attacks the '
                 'other\'s acyl carbon, and the product is a beta-keto ester because the alkoxide '
                 'leaves and the remaining alpha proton is acidic enough to be removed by that '
                 'alkoxide.',
                 ['claisen condensation', 'beta-keto ester', 'ester enolate']),
                ('Acetoacetic and Malonic Ester Syntheses',
                 'A beta-keto ester or a malonate is alkylated at its acidic alpha carbon and then '
                 'hydrolysed and decarboxylated, so the sequence installs a substituted acetic '
                 'acid or a methyl ketone with a chosen substituent.',
                 ['acetoacetic ester', 'malonic ester', 'decarboxylation']),
            ]),
            ('Conjugate Addition', [
                ('1,2- versus 1,4-Addition to Enones',
                 'A nucleophile can add to the carbonyl carbon or to the beta carbon of an enone, '
                 'and a hard irreversible nucleophile such as a Grignard adds 1,2 while a soft '
                 'reversible one such as a thiolate or a cuprate adds 1,4.',
                 ['conjugate addition', 'enone', 'hard soft']),
                ('The Michael Addition',
                 'A stabilised enolate adds to the beta carbon of an enone, and the conjugate '
                 'product is the thermodynamic one because the alkene is consumed while the '
                 'carbonyl survives intact.',
                 ['michael addition', 'enolate', 'thermodynamic product']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 15
    {
        'unit': 'Amines and Heterocycles',
        'about': ('Nitrogen in organic molecules: the basicity that makes an amine a nucleophile, '
                  'the synthesis routes that avoid over-alkylation, the reactions that convert an '
                  'amine into an amide or a diazonium salt, and the aromatic heterocycles.'),
        'sections': [],
        'topics': [
            ('Amine Properties and Synthesis', [
                ('Amine Basicity and Its Limits',
                 'An amine\'s lone pair accepts a proton, so an alkylamine is more basic than '
                 'ammonia while an aromatic amine is far less basic because its lone pair is '
                 'delocalised into the ring.',
                 ['amine basicity', 'aniline', 'lone pair']),
                ('Reductive Amination as a Controlled Route',
                 'A carbonyl and an amine condense to an imine that is reduced in the same flask, '
                 'so reductive amination gives a monoalkylated amine and avoids the '
                 'over-alkylation that direct substitution suffers.',
                 ['reductive amination', 'imine', 'monoalkylation']),
            ]),
            ('Amine Reactions', [
                ('Amide Formation from Amines',
                 'An amine attacks an acid chloride or an anhydride to give an amide, and because '
                 'the amide nitrogen\'s lone pair is delocalised into the carbonyl the product is '
                 'no longer basic or nucleophilic.',
                 ['amide formation', 'acid chloride', 'delocalization']),
                ('Diazonium Salts as Synthetic Intermediates',
                 'A primary aromatic amine treated with nitrous acid gives a diazonium salt whose '
                 'nitrogen can be replaced by halide, hydroxide or cyanide, which makes it a '
                 'route to substituents that electrophilic substitution cannot install directly.',
                 ['diazonium', 'nitrous acid', 'sandmeyer']),
            ]),
            ('Heterocycles', [
                ('Pyridine versus Pyrrole Basicity',
                 'Pyridine\'s lone pair sits in an sp2 orbital in the ring plane and accepts a '
                 'proton, while pyrrole\'s lone pair is part of its aromatic sextet, so '
                 'protonating pyrrole destroys aromaticity and it is essentially not basic.',
                 ['pyridine', 'pyrrole', 'heterocycle basicity']),
                ('Reactivity of Aromatic Heterocycles',
                 'An electron-poor heterocycle such as pyridine resists electrophilic attack and '
                 'undergoes nucleophilic substitution, whereas an electron-rich one such as furan '
                 'or pyrrole is attacked by electrophiles at the position that best stabilises '
                 'the intermediate.',
                 ['heterocycle', 'electrophilic attack', 'electron density']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 16
    {
        'unit': 'Multistep Synthesis and Retrosynthesis',
        'about': ('The capstone that turns the reaction catalogue into a plan: working backward '
                  'from a target through real disconnections, matching synthons to reagents, and '
                  'ordering steps so protecting groups, compatibility and yield all hold.'),
        'sections': [],
        'topics': [
            ('Multistep Synthesis and Retrosynthesis', [
                ('Retrosynthetic Disconnection',
                 'A retrosynthesis breaks a target at a bond that a known reaction can form in the '
                 'forward direction, so every disconnection must correspond to a real reagent and '
                 'the analysis ends only at available starting materials.',
                 ['retrosynthesis', 'disconnection', 'starting material']),
                ('Synthons, Reagents, and Polarity Matching',
                 'A synthon is the idealised fragment a disconnection implies, and it must be '
                 'matched to a real reagent of the same polarity, so an acyl anion equivalent is '
                 'needed wherever an acyl anion itself cannot be used.',
                 ['synthon', 'umpolung', 'reagent']),
                ('Ordering Steps and Protecting Groups',
                 'A plan orders reactions so each reagent is compatible with the groups already '
                 'present, which often requires a protecting group, and because yields multiply '
                 'along a linear route a convergent plan that joins two halves late usually wins.',
                 ['synthesis planning', 'protecting group', 'convergent synthesis']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 17
    {
        'unit': 'Bioorganic Molecules and Materials',
        'about': ('Where the course lands: the four biomolecule families read as carbonyl and '
                  'amine chemistry, the pericyclic reactions that run on orbital symmetry, and the '
                  'polymers whose properties follow from the same structural rules.'),
        'sections': [],
        'topics': [
            ('Biomolecules', [
                ('Amino Acids and the Peptide Bond',
                 'An amino acid carries an amine and a carboxyl group on the same carbon, and the '
                 'peptide bond joining two of them is a planar amide with partial double-bond '
                 'character, so the protein backbone rotates freely everywhere except at that bond.',
                 ['amino acid', 'peptide bond', 'amide']),
                ('Carbohydrates and Lipids',
                 'A sugar is a polyhydroxy aldehyde or ketone that cyclises into a hemiacetal '
                 'ring, while a triglyceride is glycerol esterified with three fatty acids, so '
                 'both families are built from the carbonyl chemistry of the earlier units.',
                 ['carbohydrate', 'triglyceride', 'hemiacetal']),
            ]),
            ('Pericyclic Reactions', [
                ('The Diels-Alder Reaction',
                 'A diene and a dienophile combine in one concerted step that forms two sigma '
                 'bonds and one ring, and the reaction works best when the diene can adopt the '
                 's-cis conformation and the dienophile carries an electron-withdrawing group.',
                 ['diels-alder', 'cycloaddition', 's-cis']),
                ('Orbital Symmetry and Stereospecificity',
                 'A concerted pericyclic reaction is allowed only when orbital symmetry is '
                 'conserved, so a thermal Diels-Alder is suprafacial on both components and '
                 'delivers the stereochemistry of the dienophile unchanged in the product.',
                 ['woodward-hoffmann', 'orbital symmetry', 'stereospecific']),
            ]),
            ('Polymers and Materials', [
                ('Addition and Condensation Polymerisation',
                 'An addition polymer grows by repeated alkene addition with no small molecule '
                 'lost, while a condensation polymer loses water or hydrogen chloride at each new '
                 'link, so its repeat unit is smaller than the monomers that formed it.',
                 ['polymer', 'addition polymerization', 'condensation polymerization']),
                ('Tacticity, Cross-Linking, and Properties',
                 'Crystallinity raises a polymer\'s strength and melting point, so an isotactic '
                 'chain packs better than an atactic one, and a lightly cross-linked rubber '
                 'recovers its shape while a heavily cross-linked resin cannot be melted.',
                 ['tacticity', 'cross-linking', 'crystallinity']),
            ]),
        ],
    },
]
