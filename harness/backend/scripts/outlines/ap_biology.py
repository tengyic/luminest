"""AP Biology outline, in the shape ``scripts/course_pipeline.py`` expects.

Scope and sequence authored for the Luminfest Learning Harness (CC0). The eight units
follow the publicly published AP Biology course framework and its exam weightings, in
framework order: chemistry of life (8-11%), cells (10-13%), cellular energetics
(12-16%), cell communication and the cell cycle (10-15%), heredity (8-11%), gene
expression and regulation (12-16%), natural selection (13-20%), ecology (10-15%).
Every summary is an original statement written here, not textbook text.

Textbook alignment. Every slug in ``sections`` was read from OpenStax's own table of
contents with ``scripts/probe_sections.py --book biology`` and is re-fetched through the
licence gate by ``course_pipeline.py verify``, so none is guessed.

* ``biology`` (1e, CC BY 4.0) is the spine and the only anchor book: its 205 published
  sections cover all eight units.
* ``biology-2e`` reports CC BY-NC-SA 4.0 and is therefore link-only: named in the
  alignment metadata as a study reference, never stored, quoted or used as an anchor.

Units carry four sections each, which is the anchor budget this outline was written to;
a unit with eight topics (gene expression) is anchored on the four sections that carry
the most topics rather than on every topic it teaches.
"""

from __future__ import annotations

ID = 'ap_biology'
TITLE = 'AP Biology'
SUBJECT = 'Biology'
SUBJECT_KIND = 'science'
EXPECTED_WEEKS = 34
COURSE_LINE = 'AP Biology - Information, Energetics, Evolution and Systems'
DESCRIPTION = (
    'A college-level biology course organised around the AP framework: the chemistry of '
    'water and macromolecules, cell structure and membrane transport, enzymes, '
    'photosynthesis and respiration, signal transduction and the cell cycle, meiosis and '
    'inheritance, gene expression and biotechnology, natural selection and phylogeny, and '
    'the ecology of populations, communities and ecosystems.')

TEXTBOOK = {
    'spine': 'OpenStax Biology (1e, CC BY 4.0)',
    'supplements': [],
    'link_only_note': ('OpenStax Biology 2e reports CC BY-NC-SA 4.0 and is carried as a '
                       'link-only study reference: never stored, quoted or used as an anchor.'),
}

UNITS = [
    # ---------------------------------------------------------------- 1
    {
        'unit': 'Chemistry of Life',
        'about': 'Establishes the molecular vocabulary of the course: why water behaves as it '
                 'does, which elements living systems build from, and how four classes of '
                 'polymer are assembled and folded.',
        'sections': [
            ('biology', '2-1-atoms-isotopes-ions-and-molecules-the-building-blocks'),
            ('biology', '2-2-water'),
            ('biology', '3-1-synthesis-of-biological-macromolecules'),
            ('biology', '3-4-proteins'),
        ],
        'topics': [
            ('Structure of Water and Hydrogen Bonding', [
                ('Water as a Polar Solvent',
                 "Oxygen's higher electronegativity gives water a partial negative charge on "
                 'oxygen and partial positives on its hydrogens, so water surrounds ions and '
                 'polar molecules in a hydration shell, which is why salts dissolve while '
                 'oils do not.',
                 ['polarity', 'hydration shell', 'solvent']),
                ('Cohesion, Adhesion and Capillary Action',
                 'Water hydrogen-bonds to itself (cohesion) and to polar surfaces (adhesion), '
                 'and that combination pulls water up a narrow xylem column against gravity '
                 'as long as the column stays unbroken.',
                 ['cohesion', 'adhesion', 'capillary action']),
            ]),
            ('Elements of Life', [
                ('CHNOPS and Trace Elements',
                 'Carbon, hydrogen, nitrogen, oxygen, phosphorus and sulfur make up most of '
                 'the mass of living tissue, while elements such as iron and iodine are needed '
                 'only in trace amounts yet remain essential to specific proteins and hormones.',
                 ['chnops', 'trace elements', 'essential elements']),
            ]),
            ('Introduction to Macromolecules', [
                ('Dehydration Synthesis and Hydrolysis',
                 'Monomers are joined into polymers by dehydration synthesis, which removes one '
                 'water molecule per bond formed, and polymers are taken apart by hydrolysis, '
                 'which adds water back at each bond.',
                 ['dehydration synthesis', 'hydrolysis', 'polymer']),
            ]),
            ('Carbohydrates', [
                ('Glycosidic Bonds Set Polysaccharide Function',
                 'Sugars are joined by glycosidic bonds, and the linkage pattern decides the '
                 "polymer's role: alpha-linked starch stores glucose for later use, while "
                 'beta-linked cellulose resists animal digestion and supplies structural '
                 'support.',
                 ['glycosidic bond', 'starch', 'cellulose']),
            ]),
            ('Lipids', [
                ('Triglycerides, Saturation and Energy Storage',
                 'A triglyceride joins glycerol to three fatty acids by ester bonds, its highly '
                 'reduced chains store about twice the energy per gram of carbohydrate, and '
                 'saturated chains without double bonds pack into solids while cis-unsaturated '
                 'chains kink and stay liquid.',
                 ['triglyceride', 'ester bond', 'saturated fatty acid']),
                ('Phospholipids Form Bilayers',
                 'A phospholipid trades one fatty acid for a phosphate-containing head, so the '
                 'molecule is amphipathic and in water it self-assembles into a bilayer with '
                 'the hydrophobic tails inward.',
                 ['phospholipid', 'amphipathic', 'bilayer']),
            ]),
            ('Nucleic Acids', [
                ('Nucleotides and Strand Directionality',
                 'A nucleotide is a phosphate, a pentose and a nitrogenous base, and because '
                 "each phosphate joins the 5' carbon of one sugar to the 3' carbon of the next, "
                 'a nucleic acid strand has distinct 5-prime and 3-prime ends.',
                 ['nucleotide', 'sugar-phosphate backbone', 'directionality']),
                ('Complementary Base Pairing',
                 'Adenine pairs with thymine through two hydrogen bonds and guanine with '
                 'cytosine through three, so each strand specifies its partner and the two '
                 'strands of a double helix run antiparallel.',
                 ['base pairing', 'complementary', 'antiparallel']),
            ]),
            ('Proteins', [
                ('Peptide Bonds and Amino Acid Side Chains',
                 'The 20 amino acids differ only in their R groups, and a peptide bond forms '
                 'between the carboxyl carbon of one amino acid and the amino nitrogen of the '
                 'next with the loss of water.',
                 ['amino acid', 'peptide bond', 'r group']),
                ('Four Levels of Protein Structure',
                 'Primary structure is the amino acid sequence, secondary structure is local '
                 'alpha-helix and beta-sheet hydrogen bonding, tertiary structure is the folded '
                 'three-dimensional shape, and quaternary structure is the assembly of several '
                 'polypeptide subunits.',
                 ['primary structure', 'tertiary structure', 'quaternary structure']),
                ('Denaturation and Chaperone-Assisted Folding',
                 'Heat, extreme pH or high salt disrupts the hydrogen and ionic bonds that hold '
                 'tertiary structure, so the protein denatures and loses function, while a '
                 'chaperonin provides an isolated cavity in which a new chain can fold without '
                 'aggregating with others.',
                 ['denaturation', 'chaperone', 'tertiary structure']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 2
    {
        'unit': 'Cells',
        'about': 'Moves from the whole cell to the membrane: which compartments exist and why, '
                 'what limits cell size, and how solutes cross a selectively permeable barrier '
                 'with and without energy.',
        'sections': [
            ('biology', '4-1-studying-cells'),
            ('biology', '5-1-components-and-structure'),
            ('biology', '5-2-passive-transport'),
            ('biology', '5-3-active-transport'),
        ],
        'topics': [
            ('Cell Structure and Function', [
                ('Prokaryotic and Eukaryotic Cell Plans',
                 'A eukaryotic cell keeps its DNA inside a nucleus and divides its interior '
                 'with membrane-bound organelles, while a prokaryotic cell holds a single '
                 'circular chromosome in a nucleoid and has no membrane-bound compartments.',
                 ['prokaryote', 'eukaryote', 'nucleoid']),
                ('Organelles Match Their Functions',
                 'Structure tracks function inside the endomembrane system: rough ER studded '
                 'with ribosomes builds secretory proteins, smooth ER synthesises lipids and '
                 'detoxifies, and the Golgi modifies, sorts and packages what arrives from the ER.',
                 ['organelle', 'rough er', 'golgi']),
            ]),
            ('Cell Size', [
                ('Surface Area to Volume Ratio Limits Cell Size',
                 "Volume rises with the cube of a cell's linear dimension while surface area "
                 'rises only with the square, so a larger cell has less membrane per unit of '
                 'volume and cannot exchange materials fast enough to keep up with its metabolism.',
                 ['surface area', 'volume', 'diffusion']),
            ]),
            ('Plasma Membrane', [
                ('Fluid Mosaic Model',
                 'The plasma membrane is a phospholipid bilayer with proteins, cholesterol and '
                 'glycolipids embedded in it, and those components drift laterally unless '
                 'anchored to the cytoskeleton, which is why the mosaic is described as fluid.',
                 ['fluid mosaic', 'phospholipid bilayer', 'cholesterol']),
                ('Integral and Peripheral Membrane Proteins',
                 'An integral protein spans the hydrophobic core and can serve as a channel, '
                 'carrier, receptor or anchor, while a peripheral protein sits on one face and '
                 'often links the membrane to the cytoskeleton or to a signalling partner.',
                 ['integral protein', 'peripheral protein', 'transport protein']),
            ]),
            ('Membrane Permeability', [
                ('Selective Permeability of the Bilayer',
                 'The hydrophobic core admits small nonpolar gases such as oxygen and carbon '
                 'dioxide but blocks ions and large polar molecules, so permeability depends on '
                 'a solute size, polarity and charge rather than on its concentration alone.',
                 ['selective permeability', 'hydrophobic core', 'solute']),
            ]),
            ('Membrane Transport', [
                ('Passive versus Active Transport',
                 'Passive transport moves a solute down its gradient without energy input, '
                 'whereas active transport moves it against the gradient using ATP hydrolysis '
                 'or a gradient that was built earlier.',
                 ['passive transport', 'active transport', 'concentration gradient']),
            ]),
            ('Facilitated Diffusion', [
                ('Carrier Saturation in Facilitated Diffusion',
                 'Facilitated diffusion carries a polar solute down its gradient through a '
                 'channel or carrier, but the rate levels off at high solute concentration '
                 'because the number of transport proteins in the membrane is fixed.',
                 ['facilitated diffusion', 'carrier protein', 'saturation']),
            ]),
            ('Tonicity and Osmoregulation', [
                ('Tonicity and Water Movement',
                 'Water crosses a membrane toward the compartment with the higher solute '
                 'concentration, so an animal cell shrinks in a hypertonic solution, swells and '
                 'may lyse in a hypotonic one, and holds its volume only in an isotonic one.',
                 ['tonicity', 'osmosis', 'water potential']),
            ]),
            ('Mechanisms of Transport', [
                ('The Sodium-Potassium Pump',
                 'The sodium-potassium ATPase exports three sodium ions and imports two '
                 'potassium ions per ATP hydrolysed, which keeps the interior negative and '
                 'builds the sodium gradient that secondary active transport spends to import '
                 'glucose.',
                 ['sodium-potassium pump', 'secondary active transport', 'membrane potential']),
            ]),
            ('Cell Compartmentalization', [
                ('Compartments Raise Reaction Efficiency',
                 'Membrane-bound compartments keep incompatible reactions apart and concentrate '
                 'reactants, which is why a lysosome can hydrolyse material at pH 5 without '
                 'digesting the cytosol around it.',
                 ['compartmentalization', 'lysosome', 'ph gradient']),
            ]),
            ('Origins of Cell Compartmentalization', [
                ('Endosymbiotic Theory',
                 'Mitochondria and chloroplasts descend from prokaryotes engulfed by a host '
                 'cell, which their double membranes, their own circular DNA and their '
                 'bacteria-like ribosomes all support.',
                 ['endosymbiosis', 'mitochondria', 'chloroplast']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 3
    {
        'unit': 'Cellular Energetics',
        'about': 'How cells obtain and spend energy: enzyme kinetics first, then the coupled '
                 'redox reactions of photosynthesis and respiration that move energy from light '
                 'and glucose into ATP.',
        'sections': [
            ('biology', '6-1-energy-and-metabolism'),
            ('biology', '6-5-enzymes'),
            ('biology', '8-1-overview-of-photosynthesis'),
            ('biology', '7-1-energy-in-living-systems'),
        ],
        'topics': [
            ('Enzymes', [
                ('Enzymes Lower Activation Energy',
                 'An enzyme binds its substrate at an active site and stabilises the transition '
                 'state, which lowers the activation energy and speeds the reaction without '
                 'changing the free-energy difference between reactants and products.',
                 ['activation energy', 'active site', 'catalysis']),
                ('Induced Fit and Substrate Specificity',
                 'The active site is complementary to its substrate and shifts shape as the '
                 'substrate binds, which is why one enzyme catalyses only a narrow set of '
                 'reactions rather than any reaction it encounters.',
                 ['induced fit', 'specificity', 'substrate']),
            ]),
            ('Environmental Impacts on Enzyme Function', [
                ('Temperature and pH Optima',
                 'Each enzyme works fastest at an optimum temperature and pH, and beyond them '
                 'hydrogen and ionic bonds break, the active site loses its shape and the rate '
                 'falls because denaturation is largely irreversible in the cell.',
                 ['optimum temperature', 'denaturation', 'ph']),
                ('Competitive and Noncompetitive Inhibition',
                 'A competitive inhibitor occupies the active site and its effect is overcome by '
                 'raising substrate concentration, while a noncompetitive inhibitor binds '
                 'elsewhere and lowers the maximum rate however much substrate is supplied.',
                 ['competitive inhibition', 'noncompetitive inhibition', 'maximum rate']),
            ]),
            ('Cellular Energy', [
                ('ATP Couples Exergonic and Endergonic Reactions',
                 'ATP hydrolysis releases about 7.3 kcal per mole under standard conditions, and '
                 'a cell spends that energy by phosphorylating a reactant so that the coupled '
                 'pair has a negative free-energy change overall.',
                 ['atp', 'energy coupling', 'phosphorylation']),
            ]),
            ('Photosynthesis', [
                ('Light Reactions and the Calvin Cycle',
                 'The light reactions split water, release oxygen, reduce NADP+ and build a '
                 'proton gradient that makes ATP, and the Calvin cycle then spends that ATP and '
                 'NADPH to fix carbon dioxide into triose phosphate.',
                 ['light reactions', 'calvin cycle', 'carbon fixation']),
                ('Pigment Absorption and Action Spectra',
                 'Chlorophyll a absorbs red and blue light and reflects green, so photosynthetic '
                 'rate peaks at the absorbed wavelengths and the action spectrum tracks the '
                 'absorption spectra of whichever pigments the plant contains.',
                 ['chlorophyll', 'absorption spectrum', 'action spectrum']),
            ]),
            ('Cellular Respiration', [
                ('Glycolysis',
                 'Glycolysis splits one glucose into two pyruvate in the cytosol with a net gain '
                 'of two ATP and two NADH, and it requires no oxygen, so it is the only '
                 'ATP-yielding stage available to an anaerobic cell.',
                 ['glycolysis', 'pyruvate', 'cytosol']),
                ('Pyruvate Oxidation and the Citric Acid Cycle',
                 'Pyruvate loses carbon dioxide to become acetyl-CoA, which enters the citric '
                 'acid cycle, and each turn releases two carbon dioxide and reduces three NAD+ '
                 'and one FAD while regenerating oxaloacetate.',
                 ['citric acid cycle', 'acetyl coa', 'oxaloacetate']),
                ('Oxidative Phosphorylation and Chemiosmosis',
                 'Electrons handed down the transport chain pump protons into the intermembrane '
                 'space, and the returning protons drive ATP synthase; oxygen is the terminal '
                 'electron acceptor, so without it the chain backs up and ATP output collapses.',
                 ['oxidative phosphorylation', 'chemiosmosis', 'atp synthase']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 4
    {
        'unit': 'Cell Communication and Cell Cycle',
        'about': 'How a signal becomes a response and how a response becomes a division: '
                 'receptor classes, relay and amplification, feedback, and the checkpoint '
                 'control that regulates the cell cycle.',
        'sections': [
            ('biology', '9-1-signaling-molecules-and-cellular-receptors'),
            ('biology', '9-3-response-to-the-signal'),
            ('biology', '10-2-the-cell-cycle'),
            ('biology', '10-3-control-of-the-cell-cycle'),
        ],
        'topics': [
            ('Cell Communication', [
                ('Local and Long-Distance Signalling',
                 'Paracrine signals diffuse to nearby cells, synaptic signals cross a narrow '
                 'cleft to one target, and endocrine hormones travel in blood to any cell that '
                 'carries the matching receptor.',
                 ['paracrine', 'endocrine', 'synaptic']),
                ('Reception, Transduction and Response',
                 'A signal pathway runs from ligand binding at a receptor, through intracellular '
                 'relay and amplification, to a response that alters gene expression, enzyme '
                 'activity or the cytoskeleton.',
                 ['reception', 'transduction', 'response']),
            ]),
            ('Introduction to Signal Transduction', [
                ('G Protein-Coupled and Tyrosine Kinase Receptors',
                 'A G protein-coupled receptor activates an intracellular G protein when its '
                 'ligand binds, whereas a receptor tyrosine kinase dimerises and phosphorylates '
                 'itself, so the two classes launch different intracellular relays.',
                 ['g protein', 'receptor tyrosine kinase', 'dimerisation']),
                ('Second Messengers',
                 'A second messenger such as cAMP or calcium ion carries the signal from the '
                 'membrane into the cytoplasm, and because one activated receptor makes many '
                 'messenger molecules the internal signal greatly exceeds the bound ligand.',
                 ['second messenger', 'camp', 'calcium']),
            ]),
            ('Signal Transduction Pathways', [
                ('Amplification in Kinase Cascades',
                 'A signal transduction pathway amplifies the original signal because each '
                 'activated kinase activates many downstream molecules, which is why a single '
                 'hormone molecule can produce a large cellular response.',
                 ['amplification', 'kinase cascade', 'signal']),
            ]),
            ('Feedback', [
                ('Negative and Positive Feedback',
                 'Negative feedback reverses a deviation and holds a variable near its set '
                 'point, while positive feedback reinforces the deviation and drives a process '
                 'to completion, as oxytocin release does during labour.',
                 ['negative feedback', 'positive feedback', 'set point']),
            ]),
            ('Cell Cycle', [
                ('Phases of the Cell Cycle',
                 'Interphase occupies most of the cycle with G1 growth, S-phase replication and '
                 'G2 preparation, after which mitosis divides the nucleus and cytokinesis '
                 'divides the cytoplasm.',
                 ['interphase', 's phase', 'cytokinesis']),
            ]),
            ('Regulation of Cell Cycle', [
                ('Cyclins, Cdks and Checkpoints',
                 'A cyclin binds its cyclin-dependent kinase and the complex phosphorylates the '
                 'proteins that carry a cell past the G1, G2 and spindle checkpoints, and cyclin '
                 'degradation resets the switch at the end of each cycle.',
                 ['cyclin', 'cdk', 'checkpoint']),
                ('Loss of Cycle Control and Cancer',
                 'Cancer begins when mutation removes the control on a proto-oncogene or '
                 'disables a tumour suppressor, so a cell divides without a growth signal and '
                 'its descendants accumulate further mutations.',
                 ['proto-oncogene', 'tumour suppressor', 'cancer']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 5
    {
        'unit': 'Heredity',
        'about': 'How chromosomes are shuffled into gametes and how the resulting genotypes '
                 'produce phenotypes, from Mendel\'s ratios through linkage, non-Mendelian '
                 'inheritance and environmental modification.',
        'sections': [
            ('biology', '11-1-the-process-of-meiosis'),
            ('biology', '11-2-sexual-reproduction'),
            ('biology', '12-1-mendels-experiments-and-the-laws-of-probability'),
            ('biology', '12-2-characteristics-and-traits'),
        ],
        'topics': [
            ('Meiosis', [
                ('Two Divisions Yield Four Haploid Cells',
                 'Meiosis separates homologous chromosomes in meiosis I and sister chromatids in '
                 'meiosis II, so one diploid cell gives four haploid cells carrying half the '
                 "parent's chromosome number.",
                 ['meiosis', 'haploid', 'homologous chromosomes']),
                ('Crossing Over in Prophase I',
                 'Homologues pair as tetrads in prophase I and exchange segments at chiasmata, '
                 'which recombines alleles that were linked on the same chromosome.',
                 ['prophase i', 'crossing over', 'chiasma']),
            ]),
            ('Meiosis and Genetic Diversity', [
                ('Independent Assortment',
                 'Homologues orient independently at metaphase I, so a human cell can produce '
                 '2^23 different chromosome combinations in its gametes before crossing over is '
                 'counted.',
                 ['independent assortment', 'metaphase i', 'combinations']),
                ('Random Fertilisation',
                 'Any of a male 2^23 gamete types can fuse with any of a female 2^23 types, so '
                 'fertilisation multiplies the variety meiosis generated instead of merely '
                 'preserving it.',
                 ['random fertilisation', 'gamete', 'variation']),
            ]),
            ('Mendelian Genetics', [
                ('Segregation and Complete Dominance',
                 'Each gamete receives one allele of a gene, and in complete dominance the '
                 'heterozygote shows the dominant phenotype, so a cross between two heterozygotes '
                 'gives a 3:1 phenotypic ratio.',
                 ['segregation', 'dominant allele', 'monohybrid cross']),
                ('Dihybrid Crosses and Independent Assortment',
                 'A cross between two double heterozygotes at unlinked loci gives a 9:3:3:1 '
                 'phenotypic ratio, and a significant departure from that ratio indicates '
                 'linkage or epistasis.',
                 ['dihybrid cross', 'ratio', 'linkage']),
            ]),
            ('Non-Mendelian Genetics', [
                ('Incomplete Dominance and Codominance',
                 'In incomplete dominance the heterozygote shows an intermediate phenotype, '
                 'whereas in codominance both alleles are fully expressed at once, as in AB '
                 'blood type.',
                 ['incomplete dominance', 'codominance', 'heterozygote']),
                ('Sex-Linked Inheritance',
                 'A recessive allele on the X chromosome appears far more often in males, '
                 'because a male carries one X and therefore expresses whatever allele it holds.',
                 ['sex-linked', 'x chromosome', 'hemizygous']),
            ]),
            ('Environmental Effects on Phenotype', [
                ('Phenotype as Genotype Plus Environment',
                 'Phenotype results from genotype expressed in an environment, which is why '
                 'genetically identical plants differ in height with light and hydrangeas change '
                 'flower colour with soil pH.',
                 ['phenotype', 'environment', 'gene expression']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 6
    {
        'unit': 'Gene Expression and Regulation',
        'about': 'The information path from DNA to protein and the control imposed on it: '
                 'replication, transcription, translation, regulation, mutation and the '
                 'techniques that manipulate the sequence directly.',
        'sections': [
            ('biology', '14-2-dna-structure-and-sequencing'),
            ('biology', '14-5-dna-replication-in-eukaryotes'),
            ('biology', '15-5-ribosomes-and-protein-synthesis'),
            ('biology', '16-1-regulation-of-gene-expression'),
        ],
        'topics': [
            ('DNA and RNA Structure', [
                ('Antiparallel DNA Double Helix',
                 'The two DNA strands run in opposite directions with the sugar-phosphate '
                 'backbones outside and the base pairs inside, so a purine always faces a '
                 'pyrimidine and the helix keeps a constant diameter.',
                 ['double helix', 'antiparallel', 'purine']),
                ('RNA Structure and Catalytic Folding',
                 'RNA uses ribose and uracil in place of deoxyribose and thymine, and because it '
                 'is usually single-stranded it folds into shapes that can recognise substrates, '
                 'which is how a ribozyme catalyses a reaction.',
                 ['ribose', 'uracil', 'ribozyme']),
            ]),
            ('DNA Replication', [
                ('Semiconservative Replication',
                 'Each daughter molecule keeps one parental strand and one newly made strand, as '
                 'the Meselson-Stahl density experiment showed, so replication copies a template '
                 'rather than conserving the original duplex intact.',
                 ['semiconservative', 'meselson-stahl', 'template']),
                ('Leading and Lagging Strand Synthesis',
                 'DNA polymerase extends only a free 3-prime end, so the leading strand is built '
                 'continuously toward the replication fork while the lagging strand is built in '
                 'Okazaki fragments that DNA ligase later joins.',
                 ['dna polymerase', 'okazaki fragments', 'ligase']),
            ]),
            ('Transcription and RNA Processing', [
                ('RNA Polymerase and the Promoter',
                 'RNA polymerase binds a promoter, unwinds the template and adds '
                 'ribonucleotides in the 5-prime to 3-prime direction, so the transcript matches '
                 'the coding strand except that uracil replaces thymine.',
                 ['rna polymerase', 'promoter', 'coding strand']),
                ('Capping, Polyadenylation and Splicing',
                 'A eukaryotic transcript receives a 5-prime cap and a 3-prime poly-A tail and '
                 'is spliced by the spliceosome to remove introns, so alternative splicing can '
                 'produce several proteins from one gene.',
                 ['rna processing', 'spliceosome', 'intron']),
            ]),
            ('Translation', [
                ('Codons, tRNA and the Ribosome',
                 'Triplet codons are read in the ribosome A, P and E sites while tRNA delivers '
                 'the amino acid matched to each codon, and the code is redundant without being '
                 'ambiguous.',
                 ['codon', 'trna', 'ribosome']),
                ('Initiation, Elongation and Termination',
                 'Translation starts at the start codon, elongates as peptide bonds form between '
                 'the P-site and A-site residues, and stops when a stop codon recruits a release '
                 'factor that frees the polypeptide.',
                 ['start codon', 'elongation', 'release factor']),
            ]),
            ('Regulation of Gene Expression', [
                ('Operons and Eukaryotic Control Points',
                 'A prokaryotic operon puts several genes under one promoter so a single '
                 'repressor can silence them together, whereas a eukaryote regulates the same '
                 'gene separately at transcription, at RNA processing, at translation and after '
                 'translation.',
                 ['operon', 'repressor', 'control point']),
            ]),
            ('Gene Expression and Cell Specialization', [
                ('Differential Expression Defines Cell Types',
                 'Every somatic cell of an organism carries the same genome, so tissues differ '
                 'because different subsets of genes are expressed, not because they contain '
                 'different genes.',
                 ['differential expression', 'cell type', 'genome']),
            ]),
            ('Mutations', [
                ('Point Mutations and Reading Frames',
                 'A silent substitution leaves the amino acid unchanged, a missense substitution '
                 'changes one residue and a nonsense substitution creates a stop codon, while an '
                 'insertion or deletion not divisible by three shifts the frame and garbles '
                 'every later codon.',
                 ['point mutation', 'missense', 'frameshift']),
            ]),
            ('Biotechnology', [
                ('PCR and Gel Electrophoresis',
                 'PCR amplifies a target sequence through repeated denaturation, primer '
                 'annealing and extension, and gel electrophoresis then separates the products '
                 'by size because smaller fragments travel further through the matrix.',
                 ['pcr', 'gel electrophoresis', 'amplification']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 7
    {
        'unit': 'Natural Selection',
        'about': 'The unifying mechanism of the course: how heritable variation plus '
                 'differential reproduction changes allele frequencies, how that change is '
                 'measured, dated and reconstructed as phylogeny, and where life came from.',
        'sections': [
            ('biology', '18-1-understanding-evolution'),
            ('biology', '19-2-population-genetics'),
            ('biology', '18-2-formation-of-new-species'),
            ('biology', '20-2-determining-evolutionary-relationships'),
        ],
        'topics': [
            ('Introduction to Natural Selection', [
                ('Conditions Required for Natural Selection',
                 'Natural selection acts only when a population varies, the variation is '
                 'heritable and some variants leave more offspring, so fitness means relative '
                 'reproductive success in the current environment rather than strength or '
                 'longevity.',
                 ['heritable variation', 'fitness', 'differential reproduction']),
            ]),
            ('Natural Selection', [
                ('Directional, Stabilizing and Disruptive Selection',
                 'Directional selection shifts the mean phenotype, stabilizing selection narrows '
                 'variation around an intermediate optimum, and disruptive selection favours both '
                 'extremes and can split a population in two.',
                 ['directional selection', 'stabilizing selection', 'disruptive selection']),
            ]),
            ('Artificial Selection', [
                ('Human Choice as a Selective Pressure',
                 'Artificial selection uses the same mechanism as natural selection but lets '
                 'humans decide which individuals breed, which is how one wild mustard gave '
                 'cabbage, kale, broccoli and cauliflower.',
                 ['artificial selection', 'selective breeding', 'brassica']),
            ]),
            ('Population Genetics', [
                ('Allele Frequencies and the Forces That Change Them',
                 'Population genetics describes a population by allele frequencies in its gene '
                 'pool, and evolution is any change in those frequencies caused by mutation, '
                 'gene flow, genetic drift or selection.',
                 ['allele frequency', 'gene pool', 'genetic drift']),
            ]),
            ('Hardy-Weinberg Equilibrium', [
                ('Conditions for Hardy-Weinberg Equilibrium',
                 'Allele and genotype frequencies stay constant only in a large, randomly mating '
                 'population with no mutation, no migration and no selection, so a measured '
                 'change is evidence that one of those conditions fails.',
                 ['hardy-weinberg', 'equilibrium', 'assumptions']),
                ('Genotype Frequencies from Allele Frequencies',
                 'At equilibrium genotypes follow p-squared plus 2pq plus q-squared, so the '
                 'carrier frequency 2pq stays appreciable even when a recessive allele q is rare.',
                 ['genotype frequency', 'carrier frequency', 'recessive allele']),
            ]),
            ('Evidence of Evolution', [
                ('Fossils, Homology and Biogeography',
                 'Fossil strata record sequential change, homologous structures reveal shared '
                 'descent while analogous ones reveal convergence, and endemic island species '
                 'record long isolation.',
                 ['fossil record', 'homology', 'biogeography']),
            ]),
            ('Common Ancestry', [
                ('Conserved Molecular Evidence for Common Descent',
                 'A nearly universal genetic code, conserved ribosomal RNA sequences and similar '
                 'Hox gene order across distant phyla indicate descent from one ancestor rather '
                 'than repeated independent origins.',
                 ['common ancestor', 'conserved sequence', 'hox genes']),
            ]),
            ('Continuing Evolution', [
                ('Evolution Observed Within Human Timescales',
                 'Evolution is directly observable whenever a selective pressure is strong, as '
                 'when antibiotic use raises the frequency of resistant bacteria within a few '
                 'generations.',
                 ['antibiotic resistance', 'observed evolution', 'selection pressure']),
            ]),
            ('Phylogeny', [
                ('Reading a Phylogenetic Tree',
                 'Branch points mark common ancestors and branch lengths can scale with time or '
                 'genetic change, so two tips are closest relatives only when they share the '
                 'most recent node.',
                 ['phylogenetic tree', 'node', 'clade']),
            ]),
            ('Speciation', [
                ('Reproductive Isolation Defines a Species',
                 'Under the biological species concept a species is a group that interbreeds to '
                 'produce viable fertile offspring, so speciation is complete once prezygotic or '
                 'postzygotic barriers stop gene flow.',
                 ['reproductive isolation', 'species concept', 'barrier']),
                ('Allopatric and Sympatric Speciation',
                 'Allopatric speciation follows geographic separation that interrupts gene flow, '
                 'while sympatric speciation arises within one range through polyploidy, habitat '
                 'shift or behavioural divergence.',
                 ['allopatric', 'sympatric', 'polyploidy']),
            ]),
            ('Variations in Populations', [
                ('Maintaining Genetic Variation',
                 'Mutation and recombination generate variation while diploidy and sexual '
                 'reproduction preserve it, which is why populations retain alleles that '
                 'selection does not currently favour.',
                 ['variation', 'recombination', 'diploidy']),
            ]),
            ('Origins of Life on Earth', [
                ('Abiotic Synthesis and the RNA World',
                 'Organic monomers form from inorganic gases when energy is supplied, and the '
                 'RNA world hypothesis holds that self-replicating RNA preceded DNA and protein, '
                 'which is why ribozymes are read as molecular fossils.',
                 ['rna world', 'abiotic synthesis', 'ribozyme']),
            ]),
        ],
    },
    # ---------------------------------------------------------------- 8
    {
        'unit': 'Ecology',
        'about': 'Scales the course up to populations, communities and ecosystems: how '
                 'organisms respond to their environment, how energy moves through a food web, '
                 'what limits population size, and what destabilises a community.',
        'sections': [
            ('biology', '45-3-environmental-limits-to-population-growth'),
            ('biology', '45-6-community-ecology'),
            ('biology', '46-2-energy-flow-through-ecosystems'),
            ('biology', '47-3-threats-to-biodiversity'),
        ],
        'topics': [
            ('Responses to the Environment', [
                ('Cues, Taxis and Photoperiodism',
                 'An organism answers an environmental cue with a directed movement or a timed '
                 'physiological change, as when a plant flowers only after the critical night '
                 'length has been reached.',
                 ['taxis', 'photoperiod', 'critical night length']),
            ]),
            ('Energy Flow Through Ecosystems', [
                ('Productivity and the Ten Percent Rule',
                 'Net primary productivity, the energy fixed by producers minus their own '
                 'respiration, sets the energy available to consumers, and only about ten '
                 'percent passes to the next trophic level because the rest is lost in '
                 'respiration, which is why chains rarely exceed five links.',
                 ['net primary productivity', 'trophic level', 'energy transfer']),
            ]),
            ('Population Ecology', [
                ('Exponential and Logistic Growth',
                 'A population with unlimited resources grows exponentially, but a finite '
                 'environment imposes a carrying capacity and growth then follows a logistic '
                 'curve that levels off at that ceiling.',
                 ['exponential growth', 'carrying capacity', 'logistic growth']),
            ]),
            ('Effect of Density on Populations', [
                ('Density-Dependent Regulation',
                 'As density rises, intraspecific competition and disease lower the per-capita '
                 'birth rate and raise the death rate, which is the feedback that holds a '
                 'logistic population near its carrying capacity.',
                 ['density-dependent', 'intraspecific competition', 'per-capita rate']),
            ]),
            ('Community Ecology', [
                ('Competition, Predation and Symbiosis',
                 'Species interactions run from mutualism, where both partners gain, through '
                 'commensalism, to parasitism and competition, where at least one partner loses.',
                 ['mutualism', 'predation', 'symbiosis']),
                ('Niche Differentiation and Keystone Species',
                 'Species coexist only if their niches differ enough to reduce competition, and '
                 'a keystone species shapes the community far out of proportion to its '
                 'abundance, so its removal reorganises the whole assemblage.',
                 ['niche', 'keystone species', 'competitive exclusion']),
            ]),
            ('Biodiversity', [
                ('Richness and Evenness',
                 'Biodiversity combines species richness with evenness of abundance, so a '
                 'community with the same number of species but one dominant species is less '
                 'diverse than an evenly distributed one.',
                 ['species richness', 'evenness', 'diversity']),
            ]),
            ('Disruptions in Ecosystems', [
                ('Habitat Loss, Invasive Species and Climate Change',
                 'Habitat fragmentation, introduced species and shifting climate each raise '
                 'extinction risk by shrinking ranges and breaking the interactions a species '
                 'depends on.',
                 ['habitat loss', 'invasive species', 'extinction risk']),
            ]),
        ],
    },
]
