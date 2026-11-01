"""Author and build the AP Psychology course.

Run:  python scripts/build_ap_psychology.py

Why this script exists
----------------------
The shipped catalogue covers mathematics, the sciences, computing and economics.
Psychology is missing, so the one subject a learner may actually be examined in has
no course, no map and no practice items. This script is the provenance record for
adding it: it holds the scope and sequence as data, writes it to
``app/ingest/seed/ap_psychology.json``, builds the graph pack through the *ordinary*
``app.ingest.pipeline`` path, and namespaces every concept id with the course id.

Structure
---------
Unit 0 is deliberate. The current AP course framework opens with biological bases,
but a learner meeting the subject for the first time needs the vocabulary of
evidence - variables, correlation, significance, ethics - before any of the content
claims mean anything. Unit 0 carries that, and the five units after it follow the
published AP unit organisation.

Licence position
----------------
The outline is an *original* scope and sequence authored for this project and
dedicated to the public domain under CC0, exactly like the bundled outlines beside
it. No third-party curriculum text is reproduced. The course *framework* follows the
publicly published unit organisation of AP Psychology, which is why the course also
carries a Khan Academy link as a study reference. That link is link-only: nothing is
fetched, copied or trained on, and ``app.ingest.policy`` refuses it at the gate.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
SEED_DIR = BACKEND / 'app' / 'ingest' / 'seed'
PACK_DIR = BACKEND / 'app' / 'curriculum_packs'

#: Concept ids must fit the receipt schema, which caps them at 64 characters.
MAX_ID = 64

ATTRIBUTION = ('Original scope and sequence authored for the Luminfest Learning Harness, '
               'dedicated to the public domain under CC0.')
SCOPE = ('Structure only: concept titles, unit order and prerequisite intent. No third-party '
         'curriculum text is reproduced, and no restricted source is ingested.')


def c(title, summary, keywords=(), prerequisites=()):
    """One concept: a title, a one-line summary, keywords and declared prerequisites.

    Prerequisites name other concepts *by title*, which is the reference form the
    ingest classifier resolves against its own title index.
    """
    entry = {'title': title, 'summary': summary}
    if keywords:
        entry['keywords'] = list(keywords)
    if prerequisites:
        entry['prerequisites'] = list(prerequisites)
    return entry


# ================================================================ Unit 0
FOUNDATIONS = {
    'strand': 'Foundations',
    'units': [
        {'unit': 'History and approaches', 'topics': [
            {'topic': 'Schools of thought', 'concepts': [
                c('Structuralism and introspection',
                  'Wundt and Titchener tried to break conscious experience into its '
                  'elements, training observers to report what a stimulus felt like rather '
                  'than what it was.',
                  ['structuralism', 'introspection', 'Wundt', 'Titchener']),
                c('Functionalism',
                  'James asked what consciousness is for rather than what it is made of, so '
                  'mental processes were explained by their adaptive value.',
                  ['functionalism', 'William James', 'adaptation'],
                  ['Structuralism and introspection']),
                c('Psychoanalytic perspective',
                  'Freud located behaviour in unconscious conflict and early experience, '
                  'which is why the same situation can produce anxiety the person cannot '
                  'explain.',
                  ['psychoanalytic', 'unconscious', 'Freud']),
                c('Behaviourist perspective',
                  'Behaviourism studies only what can be observed, and explains it by the '
                  'consequences that followed it rather than by inner states.',
                  ['behaviourism', 'observable behaviour', 'Watson', 'Skinner']),
                c('Humanistic perspective',
                  'Rogers and Maslow argued that people are driven toward growth and '
                  'self-direction, so a person is not reducible to drives or reinforcement.',
                  ['humanistic', 'self-actualisation', 'Rogers', 'Maslow']),
                c('Cognitive perspective',
                  'The cognitive perspective explains behaviour through the mental processes '
                  'between stimulus and response: attention, encoding, retrieval and '
                  'decision.',
                  ['cognitive', 'information processing']),
                c('Biological perspective',
                  'The biological perspective explains behaviour through genes, brain '
                  'structures, neurotransmitters and hormones.',
                  ['biological', 'neuroscience', 'genes']),
                c('Evolutionary perspective',
                  'The evolutionary perspective asks which adaptive problem a trait solved, '
                  'so a behaviour is explained by the survival or reproductive advantage it '
                  'once carried.',
                  ['evolutionary', 'natural selection', 'adaptation']),
                c('Sociocultural perspective',
                  'The sociocultural perspective explains behaviour through culture, norms '
                  'and social situation, so the same act can mean different things in '
                  'different groups.',
                  ['sociocultural', 'culture', 'norms']),
                c('Biopsychosocial approach',
                  'A complete explanation combines biological, psychological and social '
                  'levels rather than choosing one, because each level answers a different '
                  'question about the same behaviour.',
                  ['biopsychosocial', 'levels of analysis'],
                  ['Biological perspective', 'Cognitive perspective', 'Sociocultural perspective']),
            ]},
        ]},
        {'unit': 'Research methods', 'prerequisites': ['History and approaches'], 'topics': [
            {'topic': 'Designing a study', 'concepts': [
                c('Hypothesis and operational definition',
                  'A hypothesis is a testable prediction, and an operational definition '
                  'states exactly how a variable will be measured so another researcher '
                  'could repeat it.',
                  ['hypothesis', 'operational definition', 'measurement']),
                c('Independent and dependent variables',
                  'The independent variable is what the researcher manipulates; the '
                  'dependent variable is what is measured as the outcome.',
                  ['independent variable', 'dependent variable'],
                  ['Hypothesis and operational definition']),
                c('Confounding variables',
                  'A confound is an unintended difference between conditions that could '
                  'produce the effect instead of the manipulated variable.',
                  ['confound', 'internal validity'],
                  ['Independent and dependent variables']),
                c('Random assignment and random sampling',
                  'Random sampling decides who is in the study; random assignment decides '
                  'which condition each participant enters. Only assignment supports a '
                  'causal claim.',
                  ['random sampling', 'random assignment', 'generalisation'],
                  ['Confounding variables']),
                c('Experimental and correlational designs',
                  'An experiment manipulates a variable and can establish cause; a '
                  'correlational study measures two variables as they occur and cannot.',
                  ['experiment', 'correlational design', 'causation'],
                  ['Random assignment and random sampling']),
                c('Correlation coefficient',
                  'A correlation coefficient runs from -1 to +1 and reports the strength and '
                  'direction of a relationship; its size says nothing about causation.',
                  ['correlation', 'scatterplot', 'coefficient'],
                  ['Experimental and correlational designs']),
                c('Naturalistic observation and case study',
                  'Naturalistic observation watches behaviour where it happens, and a case '
                  'study examines one person in depth; both describe richly but neither '
                  'controls variables.',
                  ['naturalistic observation', 'case study', 'description']),
                c('Survey and self-report bias',
                  'Surveys depend on what people say about themselves, so wording, social '
                  'desirability and inaccurate self-knowledge all distort the data.',
                  ['survey', 'self-report', 'social desirability']),
                c('Longitudinal and cross-sectional designs',
                  'A longitudinal design follows one group over time and a cross-sectional '
                  'design compares age groups at one moment; cohort differences are the '
                  'price of the faster design.',
                  ['longitudinal', 'cross-sectional', 'cohort']),
                c('Reliability and validity',
                  'Reliability is consistency of measurement and validity is whether the '
                  'measure actually captures the construct, so a test can be reliable '
                  'without being valid.',
                  ['reliability', 'validity', 'construct']),
                c('Replication and publication bias',
                  'A finding counts when independent researchers reproduce it; studies that '
                  'fail to replicate tend to go unpublished, which inflates the published '
                  'literature.',
                  ['replication', 'publication bias', 'file drawer'],
                  ['Reliability and validity']),
            ]},
        ]},
        {'unit': 'Statistics and ethics', 'prerequisites': ['Research methods'], 'topics': [
            {'topic': 'Reading the evidence', 'concepts': [
                c('Measures of central tendency',
                  'Mean, median and mode summarise a distribution differently, and the mean '
                  'is the one an outlier drags away from the centre.',
                  ['mean', 'median', 'mode', 'outlier']),
                c('Variation and standard deviation',
                  'Two groups can share a mean and differ completely in spread, which is why '
                  'standard deviation is reported beside the average.',
                  ['standard deviation', 'range', 'variability'],
                  ['Measures of central tendency']),
                c('Normal distribution and percentile rank',
                  'In a normal distribution most scores cluster near the mean and fall away '
                  'symmetrically, so a percentile describes position rather than percentage '
                  'correct.',
                  ['normal curve', 'percentile', 'distribution'],
                  ['Variation and standard deviation']),
                c('Inferential statistics and significance',
                  'A significance test estimates how often a difference this large would '
                  'appear by chance alone; a small p-value is evidence against chance, not '
                  'proof of importance.',
                  ['inferential statistics', 'p-value', 'significance'],
                  ['Normal distribution and percentile rank']),
                c('Effect size',
                  'Effect size reports how large a difference is in standardised units, which '
                  'is why a statistically significant result can still be trivial.',
                  ['effect size', 'practical significance'],
                  ['Inferential statistics and significance']),
                c('Informed consent and debriefing',
                  'Participants must agree to take part knowing the risks, and must be told '
                  'the true purpose afterwards, especially when deception was used.',
                  ['informed consent', 'debriefing', 'deception']),
                c('Confidentiality and protection from harm',
                  'Data must be kept private and participants must leave the study no worse '
                  'than they arrived, which is the standard an ethics board applies.',
                  ['confidentiality', 'protection from harm', 'IRB'],
                  ['Informed consent and debriefing']),
                c('Placebo and double-blind procedure',
                  'A placebo control separates the effect of expecting improvement from the '
                  'effect of the treatment, and blinding keeps the experimenter from '
                  'communicating that expectation.',
                  ['placebo', 'double-blind', 'expectancy'],
                  ['Experimental and correlational designs']),
                c('Experimenter and demand characteristics',
                  'Cues in a study tell participants what is expected of them, so behaviour '
                  'can reflect the hypothesis rather than the manipulation.',
                  ['demand characteristics', 'experimenter bias'],
                  ['Placebo and double-blind procedure']),
            ]},
        ]},
    ],
}

# ================================================================ Unit 1
BIOLOGICAL = {
    'strand': 'Biological Bases of Behavior',
    'units': [
        {'unit': 'Heredity and environment', 'topics': [
            {'topic': 'Nature and nurture', 'concepts': [
                c('Behaviour genetics and twin studies',
                  'Comparing identical and fraternal twins separates the contribution of '
                  'shared genes from shared environment, because both kinds of twin share a '
                  'home but only one kind shares all its genes.',
                  ['twin study', 'behaviour genetics', 'identical twins']),
                c('Heritability',
                  'Heritability estimates how much of the variation in a group is explained '
                  'by genetic differences; it is a property of a population, not a fixed '
                  'share of one person.',
                  ['heritability', 'population', 'variation'],
                  ['Behaviour genetics and twin studies']),
                c('Gene-environment interaction',
                  'Genes set a range of possible outcomes and environment decides where '
                  'inside that range a person lands, so the same genotype can develop '
                  'differently.',
                  ['gene-environment interaction', 'range of reaction'],
                  ['Heritability']),
                c('Epigenetics',
                  'Experience can switch genes on or off without changing the DNA sequence, '
                  'which is how stress or diet in one generation can shape expression in the '
                  'next.',
                  ['epigenetics', 'gene expression'],
                  ['Gene-environment interaction']),
            ]},
        ]},
        {'unit': 'Neural communication', 'prerequisites': ['Heredity and environment'], 'topics': [
            {'topic': 'How a neuron signals', 'concepts': [
                c('Neuron structure',
                  'A neuron receives at dendrites, integrates at the cell body and transmits '
                  'down the axon to terminals, which is why damage to different parts '
                  'produces different deficits.',
                  ['neuron', 'dendrite', 'axon', 'myelin']),
                c('Action potential',
                  'A neuron fires all-or-none when excitation passes threshold, so intensity '
                  'is coded by firing rate rather than by a bigger impulse.',
                  ['action potential', 'threshold', 'all-or-none'],
                  ['Neuron structure']),
                c('Neurotransmitters',
                  'Neurotransmitters cross the synapse and bind to receptors, turning the '
                  'signal into excitation or inhibition in the next cell.',
                  ['neurotransmitter', 'synapse', 'receptor'],
                  ['Action potential']),
                c('Agonists and antagonists',
                  'An agonist mimics or strengthens a neurotransmitter and an antagonist '
                  'blocks it, which is how most psychiatric drugs change behaviour.',
                  ['agonist', 'antagonist', 'drug action'],
                  ['Neurotransmitters']),
                c('Reuptake and synaptic plasticity',
                  'Reuptake clears transmitter from the gap, and repeated signalling '
                  'strengthens or weakens the synapse, which is the cellular basis of '
                  'learning.',
                  ['reuptake', 'plasticity', 'long-term potentiation'],
                  ['Neurotransmitters']),
            ]},
        ]},
        {'unit': 'Nervous system and brain', 'prerequisites': ['Neural communication'], 'topics': [
            {'topic': 'Systems and structures', 'concepts': [
                c('Central and peripheral nervous system',
                  'The central nervous system is the brain and spinal cord; the peripheral '
                  'system carries sensory input in and motor commands out.',
                  ['central nervous system', 'peripheral nervous system']),
                c('Somatic and autonomic nervous system',
                  'The somatic division controls voluntary movement and the autonomic '
                  'division runs involuntary functions, which is why arousal happens without '
                  'a decision.',
                  ['somatic', 'autonomic'],
                  ['Central and peripheral nervous system']),
                c('Sympathetic and parasympathetic division',
                  'The sympathetic division mobilises the body for threat and the '
                  'parasympathetic division restores and conserves, so they pull against '
                  'each other.',
                  ['sympathetic', 'parasympathetic', 'arousal'],
                  ['Somatic and autonomic nervous system']),
                c('Endocrine system and hormones',
                  'Glands release hormones into the blood, so their effects are slower and '
                  'longer-lasting than neural signals.',
                  ['endocrine', 'hormone', 'adrenal', 'cortisol']),
                c('Brainstem and cerebellum',
                  'The brainstem sustains automatic survival functions and the cerebellum '
                  'coordinates movement and balance, which is why damage shows up as '
                  'clumsiness rather than as lost knowledge.',
                  ['brainstem', 'medulla', 'pons', 'cerebellum']),
                c('Limbic system',
                  'The amygdala tags emotional significance, the hippocampus forms new '
                  'memories and the hypothalamus regulates drives, so emotion, memory and '
                  'motivation share one circuit.',
                  ['limbic system', 'amygdala', 'hippocampus', 'hypothalamus']),
                c('Cerebral cortex and lobes',
                  'The occipital lobe processes vision, the temporal lobe hearing and '
                  'language, the parietal lobe touch and spatial location, and the frontal '
                  'lobe movement, planning and inhibition.',
                  ['cortex', 'occipital', 'temporal', 'parietal', 'frontal']),
                c('Hemispheric specialisation and split brain',
                  'The hemispheres specialise, and when the connecting fibres are cut each '
                  'half behaves as though it did not know what the other perceived.',
                  ['hemisphere', 'corpus callosum', 'split brain', 'lateralisation'],
                  ['Cerebral cortex and lobes']),
                c('Neuroplasticity',
                  'The brain reorganises its connections with experience, which is why '
                  'recovery after injury and skill learning are possible at all.',
                  ['plasticity', 'reorganisation'],
                  ['Synaptic plasticity']),
                c('Brain imaging techniques',
                  'EEG records electrical activity quickly, MRI and CT show structure, and '
                  'PET and fMRI show activity, so each technique answers a different '
                  'question.',
                  ['EEG', 'MRI', 'fMRI', 'PET']),
            ]},
        ]},
        {'unit': 'Sleep', 'prerequisites': ['Nervous system and brain'], 'topics': [
            {'topic': 'Rhythms and rest', 'concepts': [
                c('Circadian rhythm',
                  'An internal clock of roughly twenty-four hours regulates alertness and '
                  'body temperature, and light is what resets it.',
                  ['circadian rhythm', 'biological clock', 'melatonin']),
                c('Sleep stages',
                  'Sleep cycles through light, deep and REM stages, and the EEG signature '
                  'changes with each because brain activity differs.',
                  ['REM', 'slow wave sleep', 'EEG'],
                  ['Circadian rhythm']),
                c('Sleep disorders',
                  'Insomnia, narcolepsy and sleep apnoea are distinguished by what fails - '
                  'falling asleep, staying awake, or breathing - not by how tired the person '
                  'feels.',
                  ['insomnia', 'narcolepsy', 'sleep apnoea'],
                  ['Sleep stages']),
                c('Theories of dreaming',
                  'Freudian, activation-synthesis and cognitive views disagree about whether '
                  'dreams express hidden conflict, assemble random activity into a story, or '
                  'consolidate memory.',
                  ['dreaming', 'activation-synthesis', 'manifest content'],
                  ['Sleep stages']),
            ]},
        ]},
        {'unit': 'Sensation', 'prerequisites': ['Nervous system and brain'], 'topics': [
            {'topic': 'From stimulus to signal', 'concepts': [
                c('Sensation and perception',
                  'Sensation is the detection of a stimulus and perception is its '
                  'interpretation, so the same physical input can yield different experience.',
                  ['sensation', 'perception']),
                c('Transduction and thresholds',
                  'Transduction converts one form of energy into neural signals, and the '
                  'absolute and difference thresholds mark the weakest detectable stimulus '
                  'and the smallest detectable change.',
                  ['transduction', 'absolute threshold', 'difference threshold'],
                  ['Sensation and perception']),
                c('Signal detection and sensory adaptation',
                  'Detection depends on both sensitivity and response bias, and adaptation '
                  'means a constant stimulus fades from awareness.',
                  ['signal detection', 'adaptation', 'response bias'],
                  ['Transduction and thresholds']),
                c('Vision: rods, cones and the retina',
                  'Rods work in dim light without colour and cones give colour and detail, so '
                  'night vision is poor in colour and colour vision is poor in the dark.',
                  ['rods', 'cones', 'retina', 'photoreceptor']),
                c('Audition: pitch and localisation',
                  'Place and frequency coding together explain pitch, and timing and loudness '
                  'differences between the ears explain where a sound comes from.',
                  ['audition', 'cochlea', 'pitch', 'localisation']),
                c('Touch, pain and the body senses',
                  'Nociceptors signal tissue damage, gate control explains why attention '
                  'changes pain, and the vestibular and kinesthetic senses report balance and '
                  'limb position.',
                  ['pain', 'gate control', 'vestibular', 'kinesthetic']),
            ]},
        ]},
    ],
}

# ================================================================ Unit 2
COGNITION = {
    'strand': 'Cognition',
    'units': [
        {'unit': 'Perception', 'prerequisites': ['Sensation'], 'topics': [
            {'topic': 'Organising the input', 'concepts': [
                c('Bottom-up and top-down processing',
                  'Bottom-up processing builds a percept from features and top-down '
                  'processing applies expectation, which is why a blurry word becomes '
                  'readable in context.',
                  ['bottom-up', 'top-down', 'expectation']),
                c('Perceptual constancy',
                  'Size, shape and colour stay stable across changing retinal images, so we '
                  'see a door as rectangular while its image is a trapezoid.',
                  ['constancy', 'size constancy', 'shape constancy'],
                  ['Bottom-up and top-down processing']),
                c('Gestalt principles of grouping',
                  'Proximity, similarity, continuity and closure describe how elements are '
                  'grouped into wholes, because perception organises rather than records.',
                  ['Gestalt', 'proximity', 'closure', 'grouping'],
                  ['Perceptual constancy']),
                c('Depth perception and binocular cues',
                  'Convergence and retinal disparity use two eyes, and relative size, '
                  'interposition and linear perspective work with one, which is why depth '
                  'survives closing an eye.',
                  ['depth perception', 'retinal disparity', 'monocular cue'],
                  ['Gestalt principles of grouping']),
                c('Selective and divided attention',
                  'Selective attention filters input by relevance and divided attention '
                  'splits capacity, which is why two demanding tasks degrade together.',
                  ['attention', 'cocktail party effect', 'multitasking']),
                c('Perceptual set and context',
                  'Expectation, context and culture bias what is perceived, so the same '
                  'ambiguous figure resolves differently for different observers.',
                  ['perceptual set', 'context', 'expectation'],
                  ['Selective and divided attention']),
            ]},
        ]},
        {'unit': 'Memory', 'prerequisites': ['Perception'], 'topics': [
            {'topic': 'Encoding, storage, retrieval', 'concepts': [
                c('Three-stage model of memory',
                  'Sensory memory holds a trace briefly, working memory holds a few items '
                  'while they are used, and long-term memory stores effectively without '
                  'limit.',
                  ['sensory memory', 'working memory', 'long-term memory']),
                c('Encoding and levels of processing',
                  'Deep, meaning-based encoding produces better retention than shallow '
                  'structural encoding, which is why elaborating beats rereading.',
                  ['encoding', 'elaboration', 'levels of processing'],
                  ['Three-stage model of memory']),
                c('Chunking and working-memory capacity',
                  'Working memory holds about four chunks, and grouping items into larger '
                  'units raises the amount carried without raising the capacity.',
                  ['chunking', 'capacity', 'working memory'],
                  ['Three-stage model of memory']),
                c('Retrieval: recall and recognition',
                  'Recall reproduces information and recognition identifies it, and '
                  'recognition is usually easier because the cue is present.',
                  ['recall', 'recognition', 'retrieval cue'],
                  ['Encoding and levels of processing']),
                c('Forgetting: decay and interference',
                  'Traces fade with disuse and similar material interferes, with proactive '
                  'interference blocking new learning and retroactive interference blocking '
                  'old.',
                  ['forgetting', 'interference', 'decay'],
                  ['Retrieval: recall and recognition']),
                c('Reconstructive memory and the misinformation effect',
                  'Memory is rebuilt at retrieval, so misleading post-event information can '
                  'be incorporated as though it had been witnessed.',
                  ['reconstruction', 'misinformation effect', 'eyewitness'],
                  ['Retrieval: recall and recognition']),
                c('Spacing, testing and the serial position effect',
                  'Distributed practice and retrieval practice beat massed rereading, and the '
                  'primacy and recency effects show that position in a list changes what is '
                  'remembered.',
                  ['spacing effect', 'testing effect', 'serial position'],
                  ['Forgetting: decay and interference']),
            ]},
        ]},
        {'unit': 'Thinking and intelligence', 'prerequisites': ['Memory'], 'topics': [
            {'topic': 'Reasoning and ability', 'concepts': [
                c('Concepts and prototypes',
                  'A concept groups similar things and a prototype is the best example of the '
                  'category, so categorisation is graded rather than all-or-nothing.',
                  ['concept', 'prototype', 'categorisation']),
                c('Algorithms and heuristics',
                  'An algorithm guarantees a solution by trying every option and a heuristic '
                  'trades certainty for speed, which is why heuristics produce predictable '
                  'errors.',
                  ['algorithm', 'heuristic', 'problem solving'],
                  ['Concepts and prototypes']),
                c('Availability and representativeness heuristics',
                  'The availability heuristic judges likelihood by how easily examples come '
                  'to mind and the representativeness heuristic judges it by resemblance to a '
                  'stereotype.',
                  ['availability heuristic', 'representativeness heuristic'],
                  ['Algorithms and heuristics']),
                c('Confirmation bias and belief perseverance',
                  'People seek evidence that fits a existing belief and discount what '
                  'contradicts it, so a wrong belief can survive disconfirming data.',
                  ['confirmation bias', 'belief perseverance'],
                  ['Availability and representativeness heuristics']),
                c('Framing and loss aversion',
                  'The same choice framed as a gain or a loss produces different decisions, '
                  'because losses weigh more than equivalent gains.',
                  ['framing', 'loss aversion', 'prospect theory'],
                  ['Confirmation bias and belief perseverance']),
                c('Language structure and development',
                  'Phonemes, morphemes, syntax and semantics are separate levels, and '
                  'children acquire them in a predictable order without explicit instruction.',
                  ['phoneme', 'morpheme', 'syntax', 'language acquisition']),
                c('Linguistic relativity',
                  'Language shapes the categories available for thought, so a distinction '
                  'encoded in words is easier to notice and remember.',
                  ['linguistic relativity', 'Whorf', 'language and thought'],
                  ['Language structure and development']),
                c('Intelligence as psychometric g',
                  'Scores on diverse mental tests correlate, which supports a general factor '
                  'behind performance while leaving room for specific abilities.',
                  ['g factor', 'psychometrics', 'factor analysis']),
                c('Standardisation, reliability and validity of tests',
                  'A test is standardised on a norm group, and its scores are only '
                  'interpretable if it measures consistently and predicts what it claims to '
                  'predict.',
                  ['standardisation', 'norms', 'test validity'],
                  ['Intelligence as psychometric g']),
                c('Stereotype threat and test bias',
                  'Awareness of a negative stereotype about one group can depress '
                  'performance, so a group difference is not evidence about ability.',
                  ['stereotype threat', 'test bias'],
                  ['Standardisation, reliability and validity of tests']),
                c('Creativity and divergent thinking',
                  'Creativity combines expertise, imaginative thinking skills and a '
                  'venturesome personality, so it is a profile rather than a single score.',
                  ['creativity', 'divergent thinking', 'expertise'],
                  ['Intelligence as psychometric g']),
            ]},
        ]},
    ],
}

# ================================================================ Unit 3
DEVELOPMENT = {
    'strand': 'Development and Learning',
    'units': [
        {'unit': 'Development', 'topics': [
            {'topic': 'Change across the lifespan', 'concepts': [
                c('Prenatal development and teratogens',
                  'Development proceeds through germinal, embryonic and fetal stages, and a '
                  'teratogen is any agent that damages the developing organism during a '
                  'critical period.',
                  ['prenatal', 'teratogen', 'critical period']),
                c('Piaget stages of cognitive development',
                  'Children move from sensorimotor action to preoperational symbolism, then '
                  'concrete operations, then formal operations, with each stage defined by '
                  'what the child can now do that it could not before.',
                  ['Piaget', 'sensorimotor', 'concrete operations', 'formal operations']),
                c('Assimilation and accommodation',
                  'Assimilation fits new experience into an existing schema and accommodation '
                  'changes the schema, and the tension between them drives stage change.',
                  ['assimilation', 'accommodation', 'schema'],
                  ['Piaget stages of cognitive development']),
                c('Object permanence and conservation',
                  'Object permanence is knowing a thing continues to exist unseen and '
                  'conservation is knowing quantity survives a change of appearance; both '
                  'fail in the young child and mark stage boundaries.',
                  ['object permanence', 'conservation', 'egocentrism'],
                  ['Piaget stages of cognitive development']),
                c('Vygotsky and the zone of proximal development',
                  'Learning is social first, and the zone of proximal development is the gap '
                  'between what a learner can do alone and with support, which is what '
                  'scaffolding targets.',
                  ['Vygotsky', 'zone of proximal development', 'scaffolding']),
                c('Attachment and the strange situation',
                  'Attachment forms in the first year, and Ainsworth classified secure, '
                  'avoidant and ambivalent patterns by how an infant reacts to separation and '
                  'reunion.',
                  ['attachment', 'strange situation', 'secure base']),
                c('Parenting styles',
                  'Authoritative parenting, high in warmth and demand, is associated with the '
                  'best outcomes, while authoritarian, permissive and neglectful styles are '
                  'not.',
                  ['parenting style', 'authoritative', 'authoritarian'],
                  ['Attachment and the strange situation']),
                c('Erikson psychosocial stages',
                  'Each stage poses a crisis between two outcomes, and resolution shapes the '
                  'next stage, which is why identity work dominates adolescence.',
                  ['Erikson', 'identity', 'psychosocial crisis']),
                c('Kohlberg moral development',
                  'Moral reasoning moves from consequences, to social approval and law, to '
                  'abstract principle, and the stage is about the reason given rather than '
                  'the choice made.',
                  ['Kohlberg', 'preconventional', 'postconventional']),
                c('Adolescent brain and identity',
                  'The limbic system matures before the prefrontal cortex, so sensation '
                  'seeking peaks before impulse control catches up.',
                  ['adolescence', 'prefrontal cortex', 'identity'],
                  ['Erikson psychosocial stages']),
                c('Gender and sexual orientation development',
                  'Gender identity, expression and orientation develop from interacting '
                  'biological, cognitive and social influences rather than one cause.',
                  ['gender identity', 'sexual orientation', 'socialisation']),
                c('Ageing and cognitive change',
                  'Fluid abilities decline earlier than crystallised ones, so vocabulary can '
                  'hold while processing speed falls.',
                  ['ageing', 'fluid intelligence', 'crystallised intelligence']),
            ]},
        ]},
        {'unit': 'Learning', 'prerequisites': ['Development'], 'topics': [
            {'topic': 'Conditioning', 'concepts': [
                c('Classical conditioning',
                  'A neutral stimulus paired repeatedly with an unconditioned stimulus comes '
                  'to elicit the response alone, which is how a physiological reaction gets '
                  'attached to a new cue.',
                  ['classical conditioning', 'Pavlov', 'conditioned stimulus']),
                c('Acquisition, extinction and spontaneous recovery',
                  'Acquisition builds the association, extinction weakens it when the pairing '
                  'stops, and spontaneous recovery shows the original learning was suppressed '
                  'rather than erased.',
                  ['acquisition', 'extinction', 'spontaneous recovery'],
                  ['Classical conditioning']),
                c('Generalisation and discrimination',
                  'A response generalises to stimuli similar to the conditioned one and '
                  'discrimination narrows it to the one that predicts the outcome.',
                  ['generalisation', 'discrimination'],
                  ['Classical conditioning']),
                c('Operant conditioning',
                  'Behaviour is shaped by its consequences: reinforcement raises the '
                  'probability of a response and punishment lowers it.',
                  ['operant conditioning', 'Skinner', 'reinforcement', 'punishment']),
                c('Positive and negative reinforcement',
                  'Both reinforcement types increase behaviour; positive adds a consequence '
                  'and negative removes one, which is why negative reinforcement is not '
                  'punishment.',
                  ['positive reinforcement', 'negative reinforcement'],
                  ['Operant conditioning']),
                c('Schedules of reinforcement',
                  'Ratio schedules count responses and interval schedules count time, and '
                  'variable schedules resist extinction better than fixed ones.',
                  ['fixed ratio', 'variable interval', 'partial reinforcement'],
                  ['Operant conditioning']),
                c('Observational learning',
                  'Bandura showed that behaviour is acquired by watching a model and its '
                  'consequences, so learning can occur without the learner being reinforced.',
                  ['observational learning', 'Bandura', 'modelling']),
                c('Latent learning and cognitive maps',
                  'Learning can occur without performance and without reward, appearing only '
                  'when an incentive makes it useful.',
                  ['latent learning', 'cognitive map', 'Tolman'],
                  ['Observational learning']),
                c('Biological constraints on conditioning',
                  'Some associations form far more easily than others, so preparedness limits '
                  'what can be conditioned in a species.',
                  ['preparedness', 'taste aversion', 'biological constraint'],
                  ['Classical conditioning']),
            ]},
        ]},
    ],
}

# ================================================================ Unit 4
SOCIAL = {
    'strand': 'Social Psychology and Personality',
    'units': [
        {'unit': 'Social cognition', 'topics': [
            {'topic': 'Persons in situations', 'concepts': [
                c('Attribution theory and the fundamental attribution error',
                  'People explain behaviour by disposition or situation, and the fundamental '
                  'attribution error is over-weighting disposition when judging others.',
                  ['attribution', 'fundamental attribution error', 'dispositional']),
                c('Attitudes and cognitive dissonance',
                  'An attitude is an evaluation that guides behaviour, and dissonance is the '
                  'discomfort of holding inconsistent cognitions, usually resolved by changing '
                  'the attitude.',
                  ['attitude', 'cognitive dissonance', 'Festinger']),
                c('Conformity and normative influence',
                  'Asch showed that people yield to a unanimous wrong majority, because '
                  'fitting in and being right are separate pressures.',
                  ['conformity', 'Asch', 'normative influence']),
                c('Obedience to authority',
                  'Milgram showed that ordinary people follow an authority instruction that '
                  'harms another person when the situation makes each step small and the '
                  'authority takes responsibility.',
                  ['obedience', 'Milgram', 'authority']),
                c('Group influence: facilitation, loafing and polarisation',
                  'Presence of others improves simple performance and impairs complex '
                  'performance, individual effort drops when it cannot be identified, and '
                  'discussion pushes a group toward a more extreme position.',
                  ['social facilitation', 'social loafing', 'group polarisation']),
                c('Groupthink and deindividuation',
                  'Groupthink suppresses dissent in the interest of harmony and '
                  'deindividuation reduces self-awareness in a crowd, so both loosen '
                  'restraint.',
                  ['groupthink', 'deindividuation'],
                  ['Group influence: facilitation, loafing and polarisation']),
                c('Prejudice, stereotypes and discrimination',
                  'A stereotype is a belief about a group, prejudice is an attitude toward '
                  'it, and discrimination is behaviour; the three can occur separately.',
                  ['prejudice', 'stereotype', 'discrimination', 'ingroup']),
                c('Bystander effect and altruism',
                  'Helping drops as the number of witnesses rises, because responsibility is '
                  'diffused and each person reads the others as not alarmed.',
                  ['bystander effect', 'diffusion of responsibility', 'altruism']),
                c('Attraction and interpersonal factors',
                  'Proximity, physical attractiveness, similarity and reciprocity of liking '
                  'predict attraction better than the idea of opposites attracting.',
                  ['proximity', 'similarity', 'mere exposure']),
            ]},
        ]},
        {'unit': 'Personality', 'prerequisites': ['Social cognition'], 'topics': [
            {'topic': 'Theories and assessment', 'concepts': [
                c('Psychodynamic structure: id, ego and superego',
                  'The id seeks immediate gratification, the superego enforces internalised '
                  'rules, and the ego negotiates between them and reality.',
                  ['id', 'ego', 'superego', 'Freud']),
                c('Defence mechanisms',
                  'The ego reduces anxiety by distorting reality - repression, projection, '
                  'displacement, rationalisation - which protects the self at the cost of '
                  'accuracy.',
                  ['defence mechanism', 'repression', 'projection'],
                  ['Psychodynamic structure: id, ego and superego']),
                c('Humanistic self-concept',
                  'Rogers held that growth requires unconditional positive regard, and that a '
                  'gap between the real and ideal self produces incongruence.',
                  ['self-concept', 'unconditional positive regard', 'congruence']),
                c('Trait theory and the Big Five',
                  'Trait models describe stable, continuous differences; the Big Five - '
                  'openness, conscientiousness, extraversion, agreeableness, neuroticism - '
                  'summarise them with better predictive validity than type labels.',
                  ['trait', 'Big Five', 'OCEAN', 'factor analysis']),
                c('Social-cognitive theory and locus of control',
                  'Behaviour results from the interaction of person, behaviour and '
                  'environment, and locus of control is the belief that outcomes depend on '
                  'one\'s own actions or on outside forces.',
                  ['reciprocal determinism', 'locus of control', 'self-efficacy']),
                c('Projective and objective personality tests',
                  'Projective tests interpret ambiguous stimuli and objective tests score '
                  'fixed items; the second is far more reliable, whatever the first claims to '
                  'reveal.',
                  ['projective test', 'MMPI', 'self-report inventory'],
                  ['Trait theory and the Big Five']),
            ]},
        ]},
        {'unit': 'Motivation and emotion', 'prerequisites': ['Personality'], 'topics': [
            {'topic': 'Why we act and feel', 'concepts': [
                c('Drive-reduction and arousal theory',
                  'Drive-reduction explains behaviour as restoring balance, and arousal theory '
                  'explains it as seeking an optimal level of stimulation.',
                  ['drive reduction', 'homeostasis', 'arousal']),
                c('Intrinsic and extrinsic motivation',
                  'Intrinsic motivation comes from the activity itself and extrinsic from its '
                  'consequences, and heavy external reward can undercut the first.',
                  ['intrinsic motivation', 'extrinsic motivation', 'overjustification']),
                c('Maslow hierarchy of needs',
                  'Needs are arranged from physiological to self-actualisation, and lower '
                  'needs dominate attention until they are met.',
                  ['Maslow', 'hierarchy of needs', 'self-actualisation'],
                  ['Drive-reduction and arousal theory']),
                c('Theories of emotion',
                  'James-Lange says the body reaction comes first, Cannon-Bard says body and '
                  'feeling occur together, and Schachter-Singer says arousal plus a cognitive '
                  'label produces the emotion.',
                  ['James-Lange', 'Cannon-Bard', 'two-factor theory', 'appraisal']),
                c('Stress and the general adaptation syndrome',
                  'Selye described alarm, resistance and exhaustion, which is why prolonged '
                  'stress damages health rather than merely feeling unpleasant.',
                  ['stress', 'general adaptation syndrome', 'cortisol'],
                  ['Theories of emotion']),
            ]},
        ]},
    ],
}

# ================================================================ Unit 5
HEALTH = {
    'strand': 'Mental and Physical Health',
    'units': [
        {'unit': 'Health and positive psychology', 'topics': [
            {'topic': 'Stress, coping and well-being', 'concepts': [
                c('Appraisal and coping',
                  'Lazarus held that stress depends on whether an event is appraised as '
                  'threatening and whether resources are judged sufficient, so coping follows '
                  'appraisal.',
                  ['appraisal', 'coping', 'problem-focused', 'emotion-focused']),
                c('Health psychology and behaviour',
                  'Health psychology links behaviour - sleep, exercise, smoking, adherence - '
                  'to physical outcomes, because most chronic disease has a behavioural '
                  'component.',
                  ['health psychology', 'behavioural risk', 'adherence'],
                  ['Appraisal and coping']),
                c('Positive psychology and well-being',
                  'Positive psychology studies what makes life go well rather than only what '
                  'goes wrong, measuring engagement, relationships, meaning and accomplishment '
                  'alongside pleasant feeling.',
                  ['positive psychology', 'well-being', 'flourishing']),
                c('Resilience and social support',
                  'Resilience is the capacity to recover after adversity, and social support '
                  'is one of the strongest predictors of recovery.',
                  ['resilience', 'social support', 'recovery'],
                  ['Positive psychology and well-being']),
            ]},
        ]},
        {'unit': 'Psychological disorders', 'prerequisites': ['Health and positive psychology'],
         'topics': [
            {'topic': 'Classification and categories', 'concepts': [
                c('Classifying disorder: the DSM and diagnosis',
                  'A classification system names clusters of symptoms so clinicians agree on '
                  'what they are treating; a diagnosis describes a pattern and is not a '
                  'statement about the person.',
                  ['DSM', 'diagnosis', 'classification']),
                c('Diathesis-stress model',
                  'Disorder appears when a vulnerability meets a stressor, which is why the '
                  'same stressor harms one person and not another.',
                  ['diathesis-stress', 'vulnerability', 'stressor'],
                  ['Classifying disorder: the DSM and diagnosis']),
                c('Anxiety disorders',
                  'Generalised anxiety, panic disorder, phobia and social anxiety share '
                  'excessive fear but differ in what triggers it and how it is avoided.',
                  ['anxiety disorder', 'panic', 'phobia']),
                c('Obsessive-compulsive and related disorders',
                  'Obsessions are intrusive thoughts and compulsions are repeated acts that '
                  'reduce the distress, so the compulsion is maintained by relief rather than '
                  'by pleasure.',
                  ['obsession', 'compulsion', 'OCD'],
                  ['Anxiety disorders']),
                c('Depressive and bipolar disorders',
                  'Major depression is a sustained low mood or loss of interest, and bipolar '
                  'disorder adds episodes of elevated mood, which is why the two are treated '
                  'differently.',
                  ['major depression', 'bipolar', 'mania']),
                c('Schizophrenia spectrum',
                  'Positive symptoms add experience - hallucinations, delusions, disorganised '
                  'speech - and negative symptoms subtract it, such as flat affect and '
                  'withdrawal.',
                  ['schizophrenia', 'positive symptom', 'negative symptom', 'delusion']),
                c('Dissociative and somatic symptom disorders',
                  'Dissociative disorders involve disruption of identity or memory and somatic '
                  'symptom disorders involve bodily complaints without a matching medical '
                  'explanation.',
                  ['dissociative', 'somatic symptom']),
                c('Neurodevelopmental and personality disorders',
                  'Neurodevelopmental disorders appear early and affect development, while '
                  'personality disorders are enduring patterns of relating that are rigid and '
                  'cause impairment.',
                  ['neurodevelopmental', 'personality disorder', 'autism spectrum']),
            ]},
        ]},
        {'unit': 'Treatment', 'prerequisites': ['Psychological disorders'], 'topics': [
            {'topic': 'What helps', 'concepts': [
                c('Psychodynamic and humanistic therapy',
                  'Psychodynamic therapy works on insight into unconscious patterns and '
                  'humanistic therapy on self-acceptance and growth, so both aim at '
                  'understanding rather than at a specific behaviour.',
                  ['psychotherapy', 'insight', 'client-centred']),
                c('Cognitive-behavioural therapy',
                  'CBT changes the thoughts and behaviours that maintain a problem, and it '
                  'has the strongest evidence base of the talking therapies for anxiety and '
                  'depression.',
                  ['CBT', 'cognitive restructuring', 'behavioural activation']),
                c('Behavioural therapy and exposure',
                  'Exposure works by preventing the avoidance that keeps a fear alive, so the '
                  'extinction is experienced rather than argued.',
                  ['exposure therapy', 'systematic desensitisation', 'extinction'],
                  ['Cognitive-behavioural therapy']),
                c('Biomedical treatments',
                  'Psychopharmacology changes neurotransmitter signalling - SSRIs for '
                  'depression, antipsychotics for psychosis, lithium for bipolar - and '
                  'medication and therapy are often combined.',
                  ['SSRI', 'antipsychotic', 'lithium', 'psychopharmacology']),
                c('Evaluating treatment effectiveness',
                  'Improvement must be compared with no treatment and with placebo, because '
                  'many conditions improve on their own and expectation alone produces change.',
                  ['efficacy', 'placebo control', 'randomised trial'],
                  ['Biomedical treatments']),
            ]},
        ]},
    ],
}

COURSE = {
    'id': 'ap_psychology',
    'title': 'AP Psychology',
    'subject': 'Psychology',
    'subject_kind': 'social_science',
    'expected_weeks': 30,
    'description': ('The AP Psychology framework: the vocabulary of evidence, biological '
                    'bases of behaviour, cognition, development and learning, social '
                    'psychology and personality, and mental and physical health.'),
    'course': 'AP Psychology - Behaviour, Evidence and Explanation',
    'strands': [FOUNDATIONS, BIOLOGICAL, COGNITION, DEVELOPMENT, SOCIAL, HEALTH],
}


def seed_document(course: dict) -> dict:
    strands = []
    for strand in course['strands']:
        strands.append({
            'strand': strand['strand'],
            'units': [
                {k: v for k, v in unit.items() if k != 'topics'} | {
                    'topics': [{'topic': topic['topic'], 'concepts': topic['concepts']}
                               for topic in unit['topics']],
                }
                for unit in strand['units']
            ],
        })
    return {
        'course': course['course'],
        'licence': 'cc0',
        'source_url': '',
        'attribution': ATTRIBUTION,
        'scope': SCOPE,
        'description': course['description'],
        'expected_weeks': course['expected_weeks'],
        'strands': strands,
    }


def write_seed(course: dict) -> Path:
    path = SEED_DIR / f"{course['id']}.json"
    path.write_text(json.dumps(seed_document(course), indent=1, ensure_ascii=False) + '\n',
                    encoding='utf-8')
    return path


def build_pack(course: dict) -> Path:
    """Build the pack through the ordinary pipeline, then namespace every concept id.

    ``--sequence-within unit`` keeps within-unit ordering as teaching order rather
    than a gating chain, so the graph branches on the prerequisite intent authored
    above instead of collapsing into one long dependency.
    """
    out = PACK_DIR / f"{course['id']}.json"
    result = subprocess.run(
        [sys.executable, '-m', 'app.ingest.pipeline', 'build',
         '--seed', course['id'], '--name', course['id'], '--title', course['title'],
         '--sequence-within', 'unit', '--out', str(out)],
        cwd=str(BACKEND), capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f'pipeline build failed for {course["id"]}:\n{result.stdout}\n{result.stderr}')
    print(f'  {result.stdout.strip()}')

    pack = json.loads(out.read_text(encoding='utf-8'))
    prefix = f"{course['id']}_"
    room = MAX_ID - len(prefix)
    mapping = {node['id']: f'{prefix}{node["id"][:room]}' for node in pack['concepts']}
    for node in pack['concepts']:
        node['id'] = mapping[node['id']]
        node['prerequisites'] = [mapping.get(p, p) for p in node.get('prerequisites', [])]
        node['sequence_predecessors'] = [mapping.get(p, p) for p in
                                         node.get('sequence_predecessors', [])]
    pack['metadata']['id_namespace'] = {
        'prefix': prefix,
        'reason': ('Concept ids are global; the prefix keeps this course disjoint from the '
                   'shipped courses that share concept titles.'),
    }
    out.write_text(json.dumps(pack, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    return out


def main() -> int:
    print(f"building {COURSE['id']} ({COURSE['title']})")
    seed = write_seed(COURSE)
    print(f'  wrote {seed.relative_to(BACKEND)}')
    pack = build_pack(COURSE)
    print(f'  wrote {pack.relative_to(BACKEND)}')
    print('\ndone. Register the course in app/courses.py and its video hub in '
          'app/ingest/policy.py.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
