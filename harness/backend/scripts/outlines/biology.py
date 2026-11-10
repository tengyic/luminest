"""Biology outline, in the shape ``scripts/course_pipeline.py`` expects.

An eleven-unit introductory biology course written for this project: the process of
science and the chemistry of life, cells and transport, bioenergetics, division and
reproduction, molecular genetics, heredity, evolution and classification, body systems
and homeostasis, ecology, and human impact. Unit and topic names follow the course plan;
every summary below is an original statement written here, not textbook text.

Textbook alignment. Every slug in ``sections`` was read from OpenStax's own table of
contents with ``scripts/probe_sections.py --book biology`` and is re-fetched through the
licence gate by ``course_pipeline.py verify``, so none is guessed.

* ``biology`` (1e, CC BY 4.0) is the spine and the only anchor book: it carries all
  eleven units.
* ``biology-2e`` reports CC BY-NC-SA 4.0 and is therefore link-only: named in the
  alignment metadata as a study reference, never stored or quoted, never an anchor.

Units carry three or four sections rather than five because the plan fixes a maximum of
four; where a unit has five topics, the sections chosen are the ones that teach the
unit's regulation or exchange principle rather than a survey of parts.
"""

from __future__ import annotations

ID = 'biology'
TITLE = 'Biology'
SUBJECT = 'Biology'
SUBJECT_KIND = 'science'
EXPECTED_WEEKS = 36
COURSE_LINE = 'Biology - Cells, Genetics, Evolution and Ecology'
DESCRIPTION = (
    'A full-year introductory biology course: the process of science and the chemistry '
    'of life, cell structure and transport, photosynthesis and respiration, cell division '
    'and reproduction, molecular genetics and heredity, evolution and classification, '
    'homeostasis in body systems and plants, ecology, and human impact and sustainability.')

TEXTBOOK = {
    'spine': 'OpenStax Biology (1e, CC BY 4.0)',
    'supplements': [],
    'link_only_note': ('OpenStax Biology 2e reports CC BY-NC-SA 4.0 and is carried as a '
                       'link-only study reference: never stored, quoted or used as an anchor.'),
}

UNITS = [
    # ------------------------------------------------------------------ 1
    {
        'unit': 'Foundations of Biology',
        'about': ('The entry unit: how biological claims are tested and read from data, '
                  'what makes a system living, and the scales and instruments at which '
                  'biology is observed.'),
        'sections': [
            ('biology', '1-1-the-science-of-biology'),
            ('biology', '1-2-themes-and-concepts-of-biology'),
            ('biology', '4-1-studying-cells'),
        ],
        'topics': [
            ('Scientific Method & Experimental Design', [
                ('Hypotheses as Testable Explanations',
                 'A hypothesis is a proposed explanation stated so that a prediction follows '
                 'from it, which is why "the plant wilted because the soil dried out" can be '
                 'tested and "the plant wilted for no reason" cannot.',
                 ['hypothesis', 'prediction', 'falsifiable']),
                ('Independent and Dependent Variables',
                 'The independent variable is the condition the experimenter sets and the '
                 'dependent variable is the one measured, so a valid test changes only the '
                 'independent variable between groups.',
                 ['independent variable', 'dependent variable', 'experiment']),
                ('Control Groups and Confounding Variables',
                 'A control group holds every condition constant except the treatment, so a '
                 'difference in outcome can be credited to the treatment rather than to a '
                 'confounder such as temperature or age.',
                 ['control group', 'confounding variable', 'constant']),
            ]),
            ('Data & Graph Interpretation', [
                ('Types of Data and Their Displays',
                 'Counts and categories are discrete data drawn as a bar chart, whereas '
                 'measurements on a continuous scale are plotted as a line or scatter graph so '
                 'the shape of the relationship is visible.',
                 ['discrete data', 'continuous data', 'graph choice']),
                ('Slope and Rate from a Graph',
                 'The slope of a line is the change in the y-variable per unit change in the '
                 'x-variable, so a steeper line means the measured quantity changes faster, '
                 'not that it reaches a larger value.',
                 ['slope', 'rate', 'graph reading']),
                ('Correlation, Causation and Uncertainty',
                 'A correlation shows that two variables change together but not that one '
                 'causes the other, and overlapping error bars mean the difference between two '
                 'means is not resolvable at that sample size.',
                 ['correlation', 'causation', 'error bars']),
            ]),
            ('Characteristics of Life & Levels of Organization', [
                ('Shared Features of Living Systems',
                 'Living systems are organised, metabolise, respond to stimuli, maintain '
                 'homeostasis, grow, reproduce and evolve, and a virus meets none of the '
                 'metabolic criteria on its own, which is why its status as alive is debated.',
                 ['characteristics of life', 'metabolism', 'virus']),
                ('Levels of Organization from Molecule to Biosphere',
                 'Biological organisation runs from organelle to cell, tissue, organ, organ '
                 'system, organism, population, community, ecosystem and biosphere, and each '
                 'level shows properties its parts do not.',
                 ['levels of organization', 'emergent properties', 'hierarchy']),
                ('Structure Fits Function at Every Scale',
                 'A structure\'s shape constrains what it can do, so the thin flattened wall of '
                 'an alveolus and the branching of a root hair both increase the surface '
                 'available for exchange.',
                 ['structure and function', 'surface area', 'adaptation']),
            ]),
            ('Measurement & Microscopy', [
                ('SI Units and Biological Scale',
                 'Biology measures length in metres, mass in kilograms and volume in litres, '
                 'and a cell 10 micrometres across is 10 to the minus five metres, so unit '
                 'conversion is the first step in comparing structures.',
                 ['si units', 'scale', 'conversion']),
                ('Light and Electron Microscopy',
                 'A light microscope resolves about 200 nanometres and can view living cells, '
                 'while an electron microscope resolves below one nanometre by using electron '
                 'wavelengths but needs fixed, dehydrated specimens.',
                 ['light microscope', 'electron microscope', 'resolution']),
                ('Magnification, Resolution and Scale Bars',
                 'Magnification is image size divided by actual size, but resolution sets the '
                 'finest detail visible, so a scale bar converts a measured image length back '
                 'into a real length.',
                 ['magnification', 'resolution', 'scale bar']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 2
    {
        'unit': 'Chemistry of Life',
        'about': ('The molecular layer beneath every later unit: why water behaves as it '
                  'does, how the four macromolecule classes are built and used, and how '
                  'proteins catalyse reactions.'),
        'sections': [
            ('biology', '2-2-water'),
            ('biology', '3-1-synthesis-of-biological-macromolecules'),
            ('biology', '3-4-proteins'),
            ('biology', '6-5-enzymes'),
        ],
        'topics': [
            ('Water, Bonds & pH', [
                ('Polar Covalent Bonds in Water',
                 'Oxygen pulls the shared electrons of a water molecule toward itself, so the '
                 'molecule carries partial charges and each molecule can hydrogen-bond with up '
                 'to four neighbours.',
                 ['polar covalent', 'hydrogen bond', 'electronegativity']),
                ('Cohesion, Adhesion and Thermal Buffering',
                 'Hydrogen bonds make water cohesive, so a continuous column can be pulled up a '
                 'xylem vessel, and give water a specific heat of 4.18 joules per gram kelvin '
                 'that buffers temperature change.',
                 ['cohesion', 'adhesion', 'specific heat']),
                ('The pH Scale and Biological Buffers',
                 'pH is the negative logarithm of hydrogen-ion concentration, so one unit lower '
                 'means ten times more hydrogen ions, and a buffer pair such as carbonic acid '
                 'and bicarbonate holds pH near its pKa.',
                 ['ph', 'buffer', 'hydrogen ion']),
            ]),
            ('Macromolecules', [
                ('Dehydration Synthesis and Hydrolysis',
                 'Monomers join by dehydration synthesis, which removes a water molecule at '
                 'each new bond, and polymers are split by hydrolysis, which adds water back at '
                 'that bond.',
                 ['dehydration synthesis', 'hydrolysis', 'polymer']),
                ('Carbohydrates and Lipids as Fuel and Structure',
                 'Sugars and starch store readily mobilised energy while cellulose and chitin '
                 'give rigid structure, and lipids store about twice the energy per gram '
                 'because their hydrocarbon chains are more reduced.',
                 ['carbohydrate', 'lipid', 'energy storage']),
                ('Proteins and Nucleic Acids as Machinery and Information',
                 'A protein\'s function follows its folded shape, which is fixed by its '
                 'amino-acid sequence, while a nucleic acid stores that sequence as bases read '
                 'three at a time.',
                 ['protein', 'nucleic acid', 'amino acid']),
            ]),
            ('Enzymes & Catalysis', [
                ('The Active Site and Enzyme Specificity',
                 'An enzyme binds its substrate in a pocket whose shape and charge match it, so '
                 'a single amino-acid substitution in that pocket can abolish catalysis.',
                 ['active site', 'specificity', 'substrate']),
                ('Lowering Activation Energy',
                 'An enzyme accelerates a reaction by stabilising the transition state and so '
                 'lowering the activation energy, which raises the fraction of collisions that '
                 'succeed without changing the equilibrium position.',
                 ['activation energy', 'catalysis', 'transition state']),
                ('Temperature, pH and Inhibition',
                 'Each enzyme works fastest in a narrow temperature and pH range because beyond '
                 'it the bonds holding its tertiary structure break, and a competitive inhibitor '
                 'occupies the active site while a noncompetitive one binds elsewhere and '
                 'distorts it.',
                 ['denaturation', 'inhibition', 'optimum ph']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 3
    {
        'unit': 'Cells & Cell Transport',
        'about': ('The cell as the unit of life: the theory that established it, the parts '
                  'that divide its labour, the membrane that bounds it, and the traffic that '
                  'crosses that membrane.'),
        'sections': [
            ('biology', '4-1-studying-cells'),
            ('biology', '4-3-eukaryotic-cells'),
            ('biology', '5-1-components-and-structure'),
            ('biology', '5-2-passive-transport'),
        ],
        'topics': [
            ('Cell Theory & Cell Types', [
                ('The Three Statements of Cell Theory',
                 'Cell theory holds that every organism consists of one or more cells, that the '
                 'cell is the basic unit of life, and that all cells come from pre-existing '
                 'cells by division.',
                 ['cell theory', 'basic unit', 'division']),
                ('Prokaryotic and Eukaryotic Cells',
                 'A prokaryotic cell has no membrane-bound nucleus and keeps its DNA in a '
                 'nucleoid, while a eukaryotic cell encloses its DNA in a nucleus and divides '
                 'its labour among organelles.',
                 ['prokaryote', 'eukaryote', 'nucleus']),
                ('Why Small Cells Dominate',
                 'As a cell grows its volume rises with the cube of its length while its surface '
                 'rises only with the square, so exchange across the membrane cannot keep pace '
                 'and the cell must stay small or divide.',
                 ['surface area to volume', 'cell size', 'exchange']),
            ]),
            ('Organelles & Cell Structure', [
                ('The Nucleus and Ribosomes',
                 'The nucleus stores chromatin and assembles ribosomal subunits in its '
                 'nucleolus, and the ribosomes it exports translate mRNA in the cytoplasm or on '
                 'the rough endoplasmic reticulum.',
                 ['nucleus', 'ribosome', 'nucleolus']),
                ('Endomembrane System and Protein Traffic',
                 'Proteins made on the rough ER are folded and modified as they pass through the '
                 'endomembrane system, then sorted by the Golgi apparatus into vesicles '
                 'addressed to the membrane, a lysosome or the exterior.',
                 ['endomembrane system', 'golgi', 'vesicle']),
                ('Mitochondria and Chloroplasts as Converters',
                 'Mitochondria oxidise pyruvate in their matrix and use the extracted electrons '
                 'to pump protons across the inner membrane, chloroplasts trap light in '
                 'thylakoids, and both organelles carry their own DNA as the endosymbiotic '
                 'theory predicts.',
                 ['mitochondria', 'chloroplast', 'endosymbiosis']),
            ]),
            ('Membrane Structure & Transport', [
                ('The Fluid Mosaic Model',
                 'A membrane is a phospholipid bilayer with hydrophilic heads outward and '
                 'hydrophobic tails inward, and its proteins, cholesterol and glycolipids move '
                 'laterally within the sheet, which is what makes it fluid and mosaic.',
                 ['phospholipid bilayer', 'fluid mosaic', 'membrane protein']),
                ('Diffusion and Osmosis',
                 'A substance diffuses down its concentration gradient without energy input, and '
                 'water crosses a selectively permeable membrane by osmosis toward the side with '
                 'the higher solute concentration, so a cell in a hypertonic solution shrinks.',
                 ['diffusion', 'osmosis', 'tonicity']),
                ('Active Transport Against a Gradient',
                 'Active transport spends ATP to move solute against its gradient, as the '
                 'sodium-potassium pump does by exporting three sodium ions for every two '
                 'potassium ions it imports, and it stores the work as an electrochemical '
                 'gradient.',
                 ['active transport', 'sodium-potassium pump', 'electrochemical gradient']),
            ]),
            ('Cell Specialization & Organization', [
                ('Differentiation from One Genome',
                 'Every cell of an organism carries the same genome, so differentiation into '
                 'distinct types comes from expressing different gene sets rather than from '
                 'losing genes.',
                 ['differentiation', 'gene expression', 'cell type']),
                ('Tissues, Organs and Organ Systems',
                 'Similar specialised cells group into a tissue, tissues into an organ and '
                 'organs into a system, so a function such as absorption is carried by a '
                 'coordinated structure rather than by one cell type.',
                 ['tissue', 'organ', 'organ system']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 4
    {
        'unit': 'Cellular Energetics',
        'about': ('How cells pay for work: ATP as the currency, photosynthesis as the '
                  'energy-capturing route, respiration and fermentation as the releasing '
                  'routes, and the shared machinery that links them.'),
        'sections': [
            ('biology', '6-4-atp-adenosine-triphosphate'),
            ('biology', '8-1-overview-of-photosynthesis'),
            ('biology', '7-4-oxidative-phosphorylation'),
            ('biology', '7-5-metabolism-without-oxygen'),
        ],
        'topics': [
            ('ATP & Energy Flow', [
                ('ATP Hydrolysis as the Energy Currency',
                 'Hydrolysing ATP to ADP and phosphate releases usable energy because '
                 'separating the negatively charged phosphate groups is exergonic, and coupling '
                 'that step to an endergonic reaction is how the cell pays for work.',
                 ['atp', 'hydrolysis', 'coupled reaction']),
                ('Coupled Reactions and Phosphorylation',
                 'A coupled reaction pairs an exergonic step with an endergonic one through a '
                 'shared intermediate, and phosphorylation transfers a phosphate from ATP to a '
                 'substrate so that the substrate can react.',
                 ['coupled reaction', 'phosphorylation', 'energy coupling']),
                ('Redox Carriers NAD+ and FAD',
                 'NAD+ and FAD accept electrons and hydrogen at oxidation steps and deliver them '
                 'to the electron transport chain, so their reduced forms carry the energy that '
                 'later pumps protons.',
                 ['nad+', 'fad', 'electron carrier']),
            ]),
            ('Photosynthesis', [
                ('Light Reactions in the Thylakoid',
                 'Photosystem II splits water to replace the electron it loses, and the '
                 'resulting electron flow pumps protons into the thylakoid lumen, whose return '
                 'through ATP synthase makes ATP while NADP+ is reduced to NADPH.',
                 ['light reactions', 'photosystem', 'proton gradient']),
                ('The Calvin Cycle Fixes Carbon',
                 'RuBisCO attaches carbon dioxide to RuBP in the stroma, and ATP and NADPH from '
                 'the light reactions reduce the product to G3P, of which five of every six '
                 'molecules go to regenerate RuBP.',
                 ['calvin cycle', 'rubisco', 'carbon fixation']),
                ('Photorespiration and C4 or CAM Adaptations',
                 'RuBisCO also binds oxygen, so the hot dry conditions that close stomata drive '
                 'photorespiration, and C4 plants separate initial fixation from the Calvin '
                 'cycle in space while CAM plants separate it in time.',
                 ['photorespiration', 'c4', 'cam']),
            ]),
            ('Cellular Respiration & Fermentation', [
                ('Glycolysis and Pyruvate Oxidation',
                 'Glycolysis splits glucose into two pyruvate molecules in the cytoplasm with a '
                 'net gain of two ATP and two NADH, and each pyruvate is then decarboxylated to '
                 'acetyl-CoA for the citric acid cycle.',
                 ['glycolysis', 'pyruvate', 'acetyl coa']),
                ('The Citric Acid Cycle and Oxidative Phosphorylation',
                 'The citric acid cycle completes the oxidation of acetyl groups and loads NADH '
                 'and FADH2, whose electrons drive the proton pumps of the inner membrane so '
                 'that ATP synthase makes most of the cell\'s ATP.',
                 ['citric acid cycle', 'electron transport chain', 'atp synthase']),
                ('Fermentation Regenerates NAD+',
                 'Without oxygen the electron transport chain stalls, so fermentation reduces '
                 'pyruvate to lactate or to ethanol and carbon dioxide purely to regenerate '
                 'NAD+ and keep glycolysis running.',
                 ['fermentation', 'lactic acid', 'anaerobic']),
            ]),
            ('Comparing & Connecting the Pathways', [
                ('The Shared Architecture of Energy Pathways',
                 'Photosynthesis and respiration both run electron transport chains that pump '
                 'protons across a membrane and both use the resulting gradient to make ATP, but '
                 'they run in opposite directions from opposite electron sources.',
                 ['chemiosmosis', 'electron transport', 'energy pathway']),
                ('Carbon and Energy Balance Between the Pathways',
                 'Photosynthesis fixes inorganic carbon into sugar using light energy and '
                 'respiration oxidises that sugar back to carbon dioxide and water, so the two '
                 'pathways cycle carbon while energy passes one way through the ecosystem.',
                 ['carbon cycle', 'energy transfer', 'photosynthesis and respiration']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 5
    {
        'unit': 'Cell Division & Reproduction',
        'about': ('How genomes are copied and distributed: the cycle and its checkpoints, '
                  'the mechanics of mitosis, the variation generated by meiosis, and the '
                  'trade-offs between the two reproductive modes.'),
        'sections': [
            ('biology', '10-2-the-cell-cycle'),
            ('biology', '10-3-control-of-the-cell-cycle'),
            ('biology', '11-1-the-process-of-meiosis'),
            ('biology', '11-2-sexual-reproduction'),
        ],
        'topics': [
            ('Cell Cycle & Regulation', [
                ('Phases of the Cell Cycle',
                 'Interphase occupies most of the cycle as G1, S and G2 with DNA replicated '
                 'during S, and the mitotic phase then divides the nucleus and the cytoplasm.',
                 ['interphase', 'cell cycle', 's phase']),
                ('Checkpoints and Cyclin Control',
                 'The G1, G2 and spindle checkpoints block progress until their conditions are '
                 'met, and they are enforced by cyclin-CDK complexes whose levels rise and fall '
                 'with the cycle.',
                 ['checkpoint', 'cyclin', 'cdk']),
                ('Loss of Control and Cancer',
                 'Cancer begins when mutations disable checkpoint or repair genes so that cells '
                 'divide without the usual signals, and a proto-oncogene becomes an oncogene '
                 'when overactive while a tumour-suppressor gene must lose both copies.',
                 ['cancer', 'oncogene', 'tumor suppressor']),
            ]),
            ('Mitosis', [
                ('The Stages of Mitosis',
                 'Prophase condenses the chromosomes and breaks down the nuclear envelope, '
                 'metaphase aligns them on the spindle equator, anaphase separates sister '
                 'chromatids, and telophase rebuilds two nuclei.',
                 ['mitosis', 'spindle', 'chromosome']),
                ('The Spindle and Chromosome Segregation',
                 'Kinetochore microtubules attach each sister chromatid to the opposite pole, '
                 'and tension from both attachments is what satisfies the spindle checkpoint '
                 'before anaphase begins.',
                 ['spindle fiber', 'kinetochore', 'segregation']),
                ('Cytokinesis in Plants and Animals',
                 'An animal cell pinches off with a contractile ring of actin and myosin, '
                 'whereas a plant cell builds a cell plate from vesicles because a rigid wall '
                 'cannot be pinched.',
                 ['cytokinesis', 'cleavage furrow', 'cell plate']),
            ]),
            ('Meiosis & Genetic Variation', [
                ('Meiosis Halves the Chromosome Number',
                 'One replication followed by two divisions produces four haploid cells, so each '
                 'gamete carries one chromosome of every homologous pair instead of two.',
                 ['meiosis', 'haploid', 'homologous chromosomes']),
                ('Crossing Over in Prophase I',
                 'Homologous chromosomes exchange segments at chiasmata during prophase I, so a '
                 'chromatid can carry alleles from both grandparents and the resulting gametes '
                 'are recombinants.',
                 ['crossing over', 'chiasma', 'recombination']),
                ('Independent Assortment of Homologues',
                 'Each homologous pair orients independently at metaphase I, so a human gamete '
                 'is one of about eight million combinations before crossing over adds more.',
                 ['independent assortment', 'genetic variation', 'metaphase i']),
            ]),
            ('Sexual vs. Asexual Reproduction', [
                ('Costs and Benefits of Asexual Reproduction',
                 'Asexual reproduction copies the parent quickly and needs no mate, but it '
                 'produces genetically uniform offspring, so one change in the environment can '
                 'remove the whole clone.',
                 ['asexual reproduction', 'clone', 'uniformity']),
                ('Why Sex Persists',
                 'Sexual reproduction costs the search for a mate and halves each parent\'s '
                 'genetic contribution, but recombination and independent assortment generate '
                 'the variation that selection needs when conditions change.',
                 ['sexual reproduction', 'variation', 'recombination']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 6
    {
        'unit': 'Molecular Genetics',
        'about': ('The information path from DNA to protein: how the molecule is copied, '
                  'how its message is transcribed and translated, what happens when the '
                  'message changes, how expression is controlled, and how the techniques '
                  'that manipulate it work.'),
        'sections': [
            ('biology', '14-2-dna-structure-and-sequencing'),
            ('biology', '15-5-ribosomes-and-protein-synthesis'),
            ('biology', '16-1-regulation-of-gene-expression'),
            ('biology', '17-1-biotechnology'),
        ],
        'topics': [
            ('DNA Structure & Replication', [
                ('The Double Helix and Base Pairing',
                 'Two antiparallel strands pair adenine with thymine by two hydrogen bonds and '
                 'guanine with cytosine by three, so the sequence of one strand specifies the '
                 'sequence of the other.',
                 ['double helix', 'base pairing', 'antiparallel']),
                ('Semiconservative Replication',
                 'Helicase unwinds the helix, DNA polymerase copies each strand only in the '
                 'five-prime to three-prime direction, and the lagging strand is built as '
                 'Okazaki fragments that ligase later joins.',
                 ['dna polymerase', 'okazaki fragment', 'semiconservative']),
                ('Proofreading and Repair',
                 'DNA polymerase proofreads as it copies and mismatch, base-excision and '
                 'nucleotide-excision repair remove damage afterwards, so a faulty repair gene '
                 'such as BRCA1 leaves mutations uncorrected.',
                 ['proofreading', 'dna repair', 'mismatch']),
            ]),
            ('Transcription & Translation', [
                ('Transcription Makes an RNA Copy',
                 'RNA polymerase binds a promoter, reads the template strand and builds a '
                 'complementary RNA, and a eukaryotic transcript is capped, polyadenylated and '
                 'spliced before it leaves the nucleus.',
                 ['transcription', 'rna polymerase', 'promoter']),
                ('The Genetic Code Is Redundant and Non-overlapping',
                 'Codons are read three bases at a time from a fixed start, 61 specify amino '
                 'acids and three stop translation, so several codons can name one amino acid '
                 'but a frameshift alters every codon after it.',
                 ['genetic code', 'codon', 'frameshift']),
                ('Translation on the Ribosome',
                 'The ribosome holds the mRNA and matches each codon with a tRNA at the A site, '
                 'catalyses the peptide bond, then translocates so the growing chain leaves '
                 'through the exit tunnel.',
                 ['translation', 'trna', 'peptide bond']),
            ]),
            ('Mutations', [
                ('Point Mutations and Their Effects',
                 'A substitution changes one base and may be silent, missense or nonsense, while '
                 'an insertion or deletion that is not a multiple of three shifts the reading '
                 'frame and usually destroys the protein.',
                 ['point mutation', 'substitution', 'reading frame']),
                ('Sources of Mutation and Their Consequences',
                 'Mutations arise from replication errors, radiation and chemical mutagens, and '
                 'only a mutation in a germ-line cell is inherited, which is why a somatic '
                 'mutation can cause cancer in one body without passing to offspring.',
                 ['mutagen', 'germ line', 'somatic mutation']),
            ]),
            ('Gene Regulation', [
                ('Why Regulation Matters',
                 'Every cell of an organism carries the same genes, so regulating when and where '
                 'a gene is transcribed is what makes a liver cell different from a neuron.',
                 ['gene regulation', 'cell identity', 'transcription']),
                ('The Operon as a Prokaryotic Switch',
                 'In the lac operon a repressor blocks transcription when lactose is absent, and '
                 'the genes are switched on only when lactose is present and glucose is low, so '
                 'the cell builds the enzyme only when it pays.',
                 ['operon', 'lac operon', 'repressor']),
                ('Epigenetic and Post-transcriptional Control',
                 'Methylation of DNA and modification of histones can silence a gene heritably '
                 'without changing its sequence, and a microRNA can block translation or degrade '
                 'a transcript after it is made.',
                 ['epigenetics', 'methylation', 'microrna']),
            ]),
            ('Biotechnology & Genetic Engineering', [
                ('Restriction Enzymes and Plasmids',
                 'A restriction enzyme cuts DNA at a specific recognition sequence, and a '
                 'plasmid cut with the same enzyme can carry a foreign gene into a bacterium '
                 'that then expresses it.',
                 ['restriction enzyme', 'plasmid', 'recombinant dna']),
                ('PCR Amplifies DNA In Vitro',
                 'PCR cycles denaturation, primer annealing and extension so that each round '
                 'doubles the target, which is why thirty cycles turn one molecule into about a '
                 'billion copies.',
                 ['pcr', 'primer', 'amplification']),
                ('CRISPR and Gel Electrophoresis',
                 'CRISPR-Cas9 cuts a chosen sequence guided by a matching RNA, and gel '
                 'electrophoresis then separates the resulting fragments by size because '
                 'shorter fragments travel farther through the gel.',
                 ['crispr', 'gel electrophoresis', 'gene editing']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 7
    {
        'unit': 'Heredity',
        'about': ('How alleles pass from parents to offspring: Mendel\'s ratios and the '
                  'probability that predicts them, the inheritance patterns that depart '
                  'from those ratios, and the family evidence used to trace a trait.'),
        'sections': [
            ('biology', '12-1-mendels-experiments-and-the-laws-of-probability'),
            ('biology', '12-3-laws-of-inheritance'),
            ('biology', '13-1-chromosomal-theory-and-genetic-linkage'),
            ('biology', '13-2-chromosomal-basis-of-inherited-disorders'),
        ],
        'topics': [
            ('Mendelian Inheritance & Crosses', [
                ("Mendel's Law of Segregation",
                 'A diploid organism carries two alleles per gene and they separate during '
                 'meiosis so each gamete receives one, which is why a monohybrid cross between '
                 'heterozygotes gives a 3:1 phenotypic ratio.',
                 ['segregation', 'allele', 'monohybrid cross']),
                ('The Law of Independent Assortment',
                 'Genes on different chromosomes assort independently, so a dihybrid cross '
                 'between heterozygotes gives the 9:3:3:1 ratio, but genes close together on one '
                 'chromosome do not.',
                 ['independent assortment', 'dihybrid cross', 'linkage']),
                ('Genotype, Phenotype and Dominance',
                 'Genotype is the allele combination and phenotype the observable trait, so a '
                 'heterozygote whose phenotype matches the homozygous dominant still carries a '
                 'hidden recessive allele.',
                 ['genotype', 'phenotype', 'dominant allele']),
            ]),
            ('Probability & Punnett Squares', [
                ('Probability Rules for Inheritance',
                 'The probability that two independent events both occur is the product of their '
                 'probabilities, so a cross between two heterozygotes gives one quarter '
                 'homozygous recessive offspring rather than one half.',
                 ['probability', 'product rule', 'independent events']),
                ('Reading a Punnett Square',
                 'A Punnett square lists each parent\'s possible gametes along one axis and fills '
                 'the boxes with their combinations, so the box counts give an expected ratio '
                 'that only holds over many offspring.',
                 ['punnett square', 'gamete', 'expected ratio']),
                ('Test Crosses and Predicting Offspring',
                 'A test cross with a homozygous recessive partner reveals an unknown dominant '
                 'genotype, because any recessive offspring prove the unknown parent carried a '
                 'recessive allele.',
                 ['test cross', 'homozygous recessive', 'unknown genotype']),
            ]),
            ('Non-Mendelian Inheritance', [
                ('Incomplete Dominance and Codominance',
                 'In incomplete dominance the heterozygote shows an intermediate phenotype, as '
                 'pink snapdragons do, while in codominance both alleles are expressed '
                 'separately, as in AB blood type.',
                 ['incomplete dominance', 'codominance', 'heterozygote']),
                ('Multiple Alleles and Polygenic Traits',
                 'A gene with more than two alleles in the population, such as ABO with three, '
                 'still gives each diploid person only two, and a polygenic trait such as height '
                 'varies continuously because many genes add small effects.',
                 ['multiple alleles', 'polygenic', 'continuous variation']),
                ('Pleiotropy, Epistasis and Environment',
                 'One gene can affect several traits, one gene can mask another, and the same '
                 'genotype can yield different phenotypes in different environments, as '
                 'hydrangea flower colour shifts with soil pH.',
                 ['pleiotropy', 'epistasis', 'environmental effect']),
            ]),
            ('Sex Linkage & Pedigrees', [
                ('Sex Chromosomes and Sex-Linked Traits',
                 'A human female is XX and a male XY, so a recessive allele on the X chromosome '
                 'shows in a son who inherits that X, while a daughter must inherit two copies '
                 'to be affected.',
                 ['sex chromosome', 'x-linked', 'hemizygous']),
                ('Reading a Pedigree',
                 'A pedigree traces a trait through a family, and a trait present in every '
                 'generation of both sexes suggests dominance while one that skips generations '
                 'and affects mostly males suggests X-linked recessiveness.',
                 ['pedigree', 'inheritance pattern', 'carrier']),
                ('Linkage and Recombination Frequency',
                 'Genes on the same chromosome tend to be inherited together, and the farther '
                 'apart they sit the more often crossing over separates them, so recombination '
                 'frequency serves as a rough measure of map distance.',
                 ['genetic linkage', 'recombination frequency', 'map distance']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 8
    {
        'unit': 'Evolution & Classification',
        'about': ('The unifying theory of biology: the mechanism of selection, the evidence '
                  'that supports common descent, the origin of species, and the tree that '
                  'organises life\'s diversity.'),
        'sections': [
            ('biology', '18-1-understanding-evolution'),
            ('biology', '18-2-formation-of-new-species'),
            ('biology', '20-1-organizing-life-on-earth'),
            ('biology', '20-2-determining-evolutionary-relationships'),
        ],
        'topics': [
            ('Natural Selection & Adaptation', [
                ('Natural Selection Requires Heritable Variation',
                 'Natural selection changes allele frequencies only when individuals differ in '
                 'heritable traits that affect survival or reproduction, so a population with no '
                 'such variation cannot evolve by selection.',
                 ['natural selection', 'heritable variation', 'fitness']),
                ('Fitness and Differential Reproduction',
                 'Fitness is the relative contribution of a genotype to the next generation, so '
                 'a trait that raises survival while lowering reproduction can still be selected '
                 'against.',
                 ['fitness', 'reproduction', 'selection']),
                ('Directional, Stabilising and Disruptive Selection',
                 'Directional selection shifts a trait\'s mean, stabilising selection removes '
                 'both extremes, and disruptive selection favours both extremes and can split '
                 'one population into two phenotypic groups.',
                 ['directional selection', 'stabilizing selection', 'disruptive selection']),
            ]),
            ('Evidence for Evolution', [
                ('Fossils and Transitional Forms',
                 'The fossil record places organisms in a historical order, and a transitional '
                 'fossil such as Tiktaalik combines features of two groups in the order that '
                 'common ancestry predicts.',
                 ['fossil record', 'transitional fossil', 'common ancestry']),
                ('Homology, Analogy and Vestigial Structures',
                 'Homologous structures share an underlying anatomy inherited from a common '
                 'ancestor even when their functions differ, whereas analogous structures do the '
                 'same job from different origins, so only homology indicates relatedness.',
                 ['homology', 'analogy', 'vestigial structure']),
                ('Molecular and Biogeographic Evidence',
                 'Neutral gene sequences accumulate differences roughly in proportion to the '
                 'time since two lineages diverged, and island species resemble the nearest '
                 'mainland forms rather than distant species in a similar climate.',
                 ['molecular evidence', 'biogeography', 'pseudogene']),
            ]),
            ('Speciation & Common Ancestry', [
                ('Species Concepts and Reproductive Isolation',
                 'The biological species concept defines a species as a group that interbreeds '
                 'and produces fertile offspring, so reproductive isolation rather than physical '
                 'difference is what keeps two species apart.',
                 ['species concept', 'reproductive isolation', 'fertile offspring']),
                ('Allopatric and Sympatric Speciation',
                 'Allopatric speciation begins when a geographic barrier divides populations, '
                 'while sympatric speciation arises within one area, often through polyploidy or '
                 'a shift in mating preference.',
                 ['allopatric', 'sympatric', 'polyploidy']),
            ]),
            ('Phylogeny & Classification', [
                ('Reading a Phylogenetic Tree',
                 'A phylogenetic tree records branching order rather than a ladder of progress, '
                 'so two tips joined by a recent node are more closely related to each other than '
                 'either is to a tip that branches earlier.',
                 ['phylogenetic tree', 'node', 'common ancestor']),
                ('Cladistics and Shared Derived Characters',
                 'Cladistics groups organisms by shared derived characters, so a valid group '
                 'contains an ancestor and all of its descendants, which is why reptiles that '
                 'exclude birds do not form a clade.',
                 ['cladistics', 'derived character', 'clade']),
                ('The Three Domains and Binomial Naming',
                 'Life divides into Bacteria, Archaea and Eukarya, and each species carries a '
                 'two-part Latin name of genus and specific epithet, so Homo sapiens names one '
                 'species within the genus Homo.',
                 ['three domains', 'binomial nomenclature', 'taxonomy']),
            ]),
            ('Survey of Biological Diversity', [
                ('Prokaryotes and Their Metabolic Range',
                 'Bacteria and archaea lack a nucleus but cover almost every metabolic strategy, '
                 'including nitrogen fixation and methanogenesis, which is why they drive the '
                 'biogeochemical cycles.',
                 ['prokaryote', 'nitrogen fixation', 'metabolism']),
                ('Protists, Fungi and Plants',
                 'Protists are eukaryotes outside the fungi, plants and animals and form several '
                 'independent lineages, fungi absorb nutrients through external hyphae, and '
                 'plants are multicellular photosynthesizers with cellulose walls.',
                 ['protist', 'fungi', 'plant']),
                ('Animal Body Plans and Vertebrate Groups',
                 'Animals are multicellular heterotrophs with tissues and, in most phyla, '
                 'bilateral symmetry, and vertebrates divide into fishes, amphibians, reptiles, '
                 'birds and mammals by their skeletal and reproductive features.',
                 ['animal kingdom', 'body plan', 'vertebrate']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 9
    {
        'unit': 'Body Systems & Homeostasis',
        'about': ('One principle applied across systems: how feedback holds an internal '
                  'condition near its set point, in immunity, neural and hormonal signalling, '
                  'exchange with the environment, and plant water relations.'),
        'sections': [
            ('biology', '33-3-homeostasis'),
            ('biology', '42-2-adaptive-immune-response'),
            ('biology', '37-3-regulation-of-body-processes'),
            ('biology', '30-5-transport-of-water-and-solutes-in-plants'),
        ],
        'topics': [
            ('Homeostasis & Feedback', [
                ('Set Points and Negative Feedback',
                 'A negative feedback loop compares a measured value with a set point and '
                 'reverses any deviation, which is how core temperature is held near 37 degrees '
                 'Celsius when the environment changes.',
                 ['negative feedback', 'set point', 'thermoregulation']),
                ('Positive Feedback Amplifies Change',
                 'Positive feedback reinforces a deviation instead of reversing it, so it drives '
                 'a process to completion, as oxytocin release does during labour, and cannot '
                 'hold a steady state on its own.',
                 ['positive feedback', 'amplification', 'labour']),
                ('Balancing Water, Solutes and Heat',
                 'Osmoregulation holds solute concentration by adjusting water gain and loss, and '
                 'thermoregulation balances heat from metabolism and the environment against heat '
                 'lost by evaporation and radiation.',
                 ['osmoregulation', 'thermoregulation', 'water balance']),
            ]),
            ('Immunity, Disease & Pathogens', [
                ('Innate Immunity Is Fast and Non-specific',
                 'The innate response uses barriers, phagocytes and inflammation to answer any '
                 'invader within hours and without memory, so it slows an infection but does not '
                 'target one pathogen in particular.',
                 ['innate immunity', 'inflammation', 'phagocyte']),
                ('Adaptive Immunity Is Specific and Remembers',
                 'B and T lymphocytes whose receptor matches an antigen are selected and clonally '
                 'expanded, and the memory cells left behind make a second response faster and '
                 'stronger, which is the basis of vaccination.',
                 ['adaptive immunity', 'lymphocyte', 'memory cell']),
                ('Pathogens, Transmission and Antibiotic Resistance',
                 'A pathogen causes disease by damaging tissue or releasing toxins, and bacteria '
                 'survive an antibiotic only if they already carry resistance, so incomplete '
                 'courses of treatment select for resistant strains.',
                 ['pathogen', 'antibiotic resistance', 'transmission']),
            ]),
            ('Nervous & Endocrine Regulation', [
                ('Neurons Signal by Electrical Gradients',
                 'A neuron holds a resting potential near minus 70 millivolts by pumping sodium '
                 'out and potassium in, and it fires an action potential once depolarisation '
                 'reaches threshold.',
                 ['neuron', 'action potential', 'resting potential']),
                ('Synapses and Neurotransmitters',
                 'An action potential releases neurotransmitter across a synapse, and the signal '
                 'crosses in one direction only because vesicles sit on the presynaptic side and '
                 'receptors on the postsynaptic side.',
                 ['synapse', 'neurotransmitter', 'presynaptic']),
                ('Hormones as Slower, Broadcast Signals',
                 'A hormone travels in blood to cells that carry its receptor, so a steroid '
                 'hormone enters the cell and alters transcription while a peptide hormone binds '
                 'a surface receptor and triggers a second messenger.',
                 ['hormone', 'receptor', 'second messenger']),
            ]),
            ('Transport & Exchange Systems', [
                ('Exchange Surfaces and the Surface-Area Constraint',
                 'An exchange surface works only when it is thin, moist and large relative to '
                 'the body\'s volume, which is why lungs fold into alveoli and intestine into '
                 'villi rather than relying on the skin.',
                 ['exchange surface', 'surface area', 'diffusion distance']),
                ('Circulation Moves Materials Between Surfaces',
                 'A circulatory system connects exchange surfaces to every cell, and a double '
                 'circulation sends blood through the lungs at low pressure before the heart '
                 'drives it around the body at high pressure.',
                 ['circulatory system', 'double circulation', 'blood pressure']),
            ]),
            ('Plant Structure & Physiology', [
                ('Xylem and Phloem as Two Transport Tissues',
                 'Xylem carries water and minerals upward from the roots, pulled by transpiration '
                 'from the leaves, while phloem carries sugars from sources to sinks under '
                 'pressure flow.',
                 ['xylem', 'phloem', 'transpiration']),
                ('Stomata, Guard Cells and Water Loss',
                 'Guard cells open a stoma when they take up water and become turgid, which '
                 'admits carbon dioxide for photosynthesis but also lets water vapour escape, so '
                 'the plant trades carbon gain against water loss.',
                 ['stomata', 'guard cell', 'transpiration']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 10
    {
        'unit': 'Ecology',
        'about': ('Populations, communities and ecosystems as systems with their own '
                  'accounting: where energy and matter go, what limits a population, how '
                  'species interact, and what keeps a community stable.'),
        'sections': [
            ('biology', '46-2-energy-flow-through-ecosystems'),
            ('biology', '46-3-biogeochemical-cycles'),
            ('biology', '45-4-population-dynamics-and-regulation'),
            ('biology', '45-6-community-ecology'),
        ],
        'topics': [
            ('Energy Flow & Food Webs', [
                ('Trophic Levels and the Ten Percent Rule',
                 'Energy passes from producers to consumers along a food chain, and only about '
                 'ten percent of the energy at one level is stored as biomass at the next, so '
                 'food chains rarely exceed four or five links.',
                 ['trophic level', 'ten percent rule', 'food chain']),
                ('Food Webs and Keystone Species',
                 'A food web records the many feeding links in a community, and a keystone '
                 'species holds that web together out of proportion to its abundance, so its '
                 'removal reshapes the community.',
                 ['food web', 'keystone species', 'community']),
                ('Productivity and Why It Limits Ecosystems',
                 'Gross primary productivity is the total carbon fixed by producers and net '
                 'primary productivity is what remains after their respiration, which is the '
                 'energy budget available to every consumer.',
                 ['primary productivity', 'biomass', 'carbon fixation']),
            ]),
            ('Biogeochemical Cycles', [
                ('Carbon and Nitrogen Cycle Between Pools',
                 'Carbon moves between the atmosphere, living matter and sediments through '
                 'photosynthesis, respiration and combustion, while atmospheric nitrogen must be '
                 'fixed by bacteria before most producers can use it.',
                 ['carbon cycle', 'nitrogen cycle', 'nitrogen fixation']),
                ('Phosphorus and Water as Material Cycles',
                 'Phosphorus has no gaseous phase and moves from rock through soil and organisms '
                 'by weathering and decomposition, while water cycles by evaporation, '
                 'condensation and precipitation, so neither behaves like the carbon cycle.',
                 ['phosphorus cycle', 'water cycle', 'weathering']),
            ]),
            ('Population Dynamics & Carrying Capacity', [
                ('Exponential Growth and Its Limits',
                 'A population with unlimited resources grows at a rate proportional to its size '
                 'and so rises exponentially, but resources, disease and predation eventually '
                 'reduce that rate.',
                 ['exponential growth', 'population growth', 'limiting resource']),
                ('Logistic Growth and Carrying Capacity',
                 'Logistic growth slows as population size approaches the carrying capacity K, '
                 'because per-capita growth falls as competition for limited resources '
                 'intensifies.',
                 ['logistic growth', 'carrying capacity', 'competition']),
                ('Life Histories and Age Structure',
                 'An r-selected species produces many offspring with little care while a '
                 'K-selected species produces few with heavy care, and a population\'s age '
                 'structure predicts whether it will grow or shrink next.',
                 ['life history', 'r-selected', 'age structure']),
            ]),
            ('Community Interactions & Succession', [
                ('Competition, Predation and Symbiosis',
                 'Two species competing for one limiting resource cannot coexist indefinitely '
                 'unless they divide it, while predation, mutualism, commensalism and parasitism '
                 'each change the two populations in a different direction.',
                 ['competition', 'predation', 'symbiosis']),
                ('Ecological Niches and Resource Partitioning',
                 'A species\' niche is the full set of conditions and resources it uses, and two '
                 'species whose niches overlap heavily must partition those resources or one will '
                 'exclude the other.',
                 ['niche', 'resource partitioning', 'competitive exclusion']),
                ('Primary and Secondary Succession',
                 'Primary succession starts on bare substrate with no soil and begins with '
                 'pioneer species, while secondary succession follows a disturbance that leaves '
                 'soil and seeds and therefore proceeds faster.',
                 ['primary succession', 'secondary succession', 'pioneer species']),
            ]),
            ('Ecosystem Stability & Biodiversity', [
                ('Resistance, Resilience and Trophic Cascades',
                 'A stable ecosystem resists change and recovers after it, and a trophic cascade '
                 'shows that removing a top predator can change the abundance of every level '
                 'beneath it.',
                 ['resistance', 'resilience', 'trophic cascade']),
                ('Biodiversity Supports Ecosystem Function',
                 'A community with more species usually keeps functioning when conditions '
                 'change, because different species respond differently, so diversity works as '
                 'insurance rather than decoration.',
                 ['biodiversity', 'ecosystem function', 'redundancy']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 11
    {
        'unit': 'Human Impact & Sustainability',
        'about': ('The course\'s closing lens: the pressures human activity puts on '
                  'ecosystems, what biodiversity is worth and how it is conserved, and what '
                  'sustainability would require.'),
        'sections': [
            ('biology', '47-1-the-biodiversity-crisis'),
            ('biology', '47-3-threats-to-biodiversity'),
            ('biology', '47-4-preserving-biodiversity'),
            ('biology', '44-5-climate-and-the-effects-of-global-climate-change'),
        ],
        'topics': [
            ('Human Impact on Ecosystems', [
                ('Habitat Loss and Fragmentation',
                 'Converting land to farmland, roads and cities removes habitat and cuts what '
                 'remains into isolated patches, and small patches lose species faster because '
                 'their populations are smaller and cannot exchange migrants.',
                 ['habitat loss', 'fragmentation', 'migration']),
                ('Overexploitation and Invasive Species',
                 'Harvesting a population faster than it reproduces drives it down, and an '
                 'introduced species released from its natural predators can outcompete natives '
                 'because nothing in the new community limits it.',
                 ['overexploitation', 'invasive species', 'competition']),
                ('Pollution and Eutrophication',
                 'Excess nitrogen and phosphorus run off farmland into water, where the algal '
                 'growth they fuel is decomposed by bacteria that consume the dissolved oxygen '
                 'and create a hypoxic dead zone.',
                 ['eutrophication', 'nutrient runoff', 'dead zone']),
            ]),
            ('Biodiversity & Conservation', [
                ('Measuring Biodiversity at Three Levels',
                 'Biodiversity is measured as genetic variation within a species, species '
                 'richness within a community and the variety of ecosystems in a region, and '
                 'each level can decline independently of the others.',
                 ['biodiversity', 'species richness', 'genetic diversity']),
                ('Why Biodiversity Has Value',
                 'Biodiversity supplies ecosystem services such as pollination, water filtration '
                 'and medicines, so its loss carries an economic cost as well as an ecological '
                 'one.',
                 ['ecosystem services', 'pollination', 'intrinsic value']),
                ('Conservation Strategies',
                 'A protected area works only if it is large, connected and enforced, and ex situ '
                 'measures such as seed banks and captive breeding complement it for species that '
                 'cannot persist in the wild.',
                 ['protected area', 'corridor', 'captive breeding']),
            ]),
            ('Climate Change & Sustainability', [
                ('The Greenhouse Effect and Its Intensification',
                 'Greenhouse gases absorb outgoing infrared radiation and re-emit part of it '
                 'downward, and burning fossil fuel adds carbon dioxide that strengthens this '
                 'absorption and warms the planet\'s energy budget.',
                 ['greenhouse effect', 'carbon dioxide', 'radiative forcing']),
                ('Sustainability as Living Within Regeneration Rates',
                 'A practice is sustainable only if it uses renewable resources no faster than '
                 'they regenerate and releases wastes no faster than they are absorbed, so a '
                 'fishery can be harvested indefinitely only up to its maximum sustainable '
                 'yield.',
                 ['sustainability', 'regeneration', 'maximum sustainable yield']),
            ]),
        ],
    },
]
