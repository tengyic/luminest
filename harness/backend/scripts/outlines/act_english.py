"""ACT English outline, in the shape ``scripts/course_pipeline.py`` expects.

A three-unit course written for this project against the ACT English reporting
categories: production of writing (purpose and focus, organisation, unity and cohesion),
knowledge of language (expressing ideas clearly, style), and the conventions of standard
English (sentence structure, usage, punctuation). The two rhetorical units teach judgement
-- which sentence earns its place, which transition names the real relation, which wording
is precise and concise -- and the conventions unit teaches the rules those judgements are
written with. Every summary below is an original statement written here, not textbook
text, and each names the condition under which its claim holds, so a concept is a rule a
learner can apply to a new passage rather than a description of one passage.

Textbook position. OpenStax publishes exactly one writing title, *Writing Guide with
Handbook*, and it reports CC BY-NC-SA 4.0. A non-commercial share-alike book cannot be
stored, quoted or used as a text anchor, and no CC BY English-language or composition
textbook exists in the OpenStax catalogue, so this module does not anchor to a book at
all. The reporting categories above are a public test description, not a curriculum text,
and no ACT item, passage or explanation is reproduced here. ``TEXTBOOK`` therefore
declares ``no_cc_by_anchor = True`` with the reason, every unit carries an empty
``sections`` list, and ``course_pipeline.py verify`` reports the anchoring check as SKIP
with that reason rather than a green tick it has not earned. The OpenStax writing guide
stays link-only: it is named as a study reference and is never fetched, stored or quoted.

The pack is generated: ``act_english.json`` is rebuilt by the pipeline from this module
and must never be hand-edited.
"""

from __future__ import annotations

ID = 'act_english'
TITLE = 'ACT English'
SUBJECT = 'English'
SUBJECT_KIND = 'social_science'
EXPECTED_WEEKS = 30
COURSE_LINE = 'ACT English - Rhetorical Skill and Conventions of Standard English'
DESCRIPTION = (
    'A focused course in the two halves of ACT English: the rhetorical decisions that '
    'decide what a passage says and how well it says it, and the conventions that decide '
    'whether its sentences are correct. The first unit judges purpose and focus, then '
    'organisation, unity and cohesion -- whether a sentence earns its place, which '
    'transition names the real relation, where a sentence belongs, and what keeps a '
    'paragraph on one idea. The second unit works on expression and style: concision, '
    'redundancy, precise wording, clarity of reference, tone, register and figurative '
    'language. The third unit drills the conventions the test rewards: fragments, run-ons '
    'and clause boundaries, parallelism and modifier placement, agreement, pronoun case, '
    'tense consistency, idiomatic preposition, and the punctuation of clauses, series, '
    'lists and possessives.')

TEXTBOOK = {
    'spine': '', 'supplements': [],
    'link_only_note': ('OpenStax Writing Guide with Handbook reports CC BY-NC-SA 4.0 and is '
                       'carried as a link-only study reference: never stored or quoted.'),
    'no_cc_by_anchor': True,
    'reason': ('No CC BY English-language or composition textbook exists in the OpenStax '
               'catalogue (checked 2026-11-10; the only writing title is CC BY-NC-SA). The '
               'outline is an original CC0 scope and sequence and is not anchored to a '
               'textbook, so no section is quoted for this course.'),
}

UNITS = [
    # ------------------------------------------------------------------ 1
    {
        'unit': 'Production of Writing',
        'about': ('The unit that decides what a passage is for: whether a proposed sentence '
                  'earns its place, whether a paragraph still serves the idea it announced, '
                  'and whether the sentences are ordered and connected so a reader can '
                  'follow the argument without re-reading it.'),
        'sections': [],
        'topics': [
            ('Purpose and Focus', [
                ('Relevance of an Added Sentence',
                 'A sentence proposed for addition belongs only where it supports the '
                 'paragraph\'s controlling idea, so when it opens a subject the paragraph '
                 'never develops the correct choice leaves the passage unchanged, however '
                 'accurate the sentence is on its own.',
                 ['relevance', 'added sentence', 'paragraph focus']),
                ('Deciding Whether to Delete a Sentence',
                 'A sentence is deleted when it repeats information already given, '
                 'contradicts the paragraph\'s claim, or drifts into a subject the passage '
                 'abandons, while it is kept when it supplies the particular kind of support '
                 'the paragraph is missing.',
                 ['deletion', 'stray detail', 'support']),
                ('Purpose of a Sentence in Context',
                 'A purpose question asks what a sentence does for the reader rather than '
                 'what it says, so the right answer names its function -- to introduce, '
                 'illustrate, qualify or conclude -- and an answer that merely paraphrases '
                 'the sentence is wrong even when the paraphrase is exact.',
                 ['rhetorical purpose', 'function', 'context']),
                ('The Paragraph\'s Controlling Idea',
                 'Each paragraph carries one controlling idea, usually announced in its '
                 'opening sentence, so a question about where a sentence belongs is settled '
                 'by finding the paragraph whose announced idea that sentence develops.',
                 ['controlling idea', 'topic sentence', 'paragraph unity']),
                ('Passage Focus Against the Prompt',
                 'The whole passage answers one prompt, so an addition that shifts the '
                 'subject, the intended audience or the writer\'s position fails at passage '
                 'level even when it fits neatly into the paragraph it would enter.',
                 ['passage focus', 'prompt', 'audience']),
            ]),
            ('Organization, Unity, and Cohesion', [
                ('Transitions Name a Logical Relation',
                 'A transition is correct only when it names the relation that actually '
                 'holds between the two sentences it joins, so "however" fails where the '
                 'second sentence supports the first and "therefore" fails where it merely '
                 'restates it.',
                 ['transition', 'logical relation', 'contrast']),
                ('Placement Follows the Words a Sentence Depends On',
                 'A sentence goes where the words it depends on have already appeared, which '
                 'is why a sentence opening "This process ..." cannot precede the description '
                 'of the process, and why a paragraph opener must announce the idea its '
                 'sentences then develop rather than start inside an example.',
                 ['sentence placement', 'antecedent', 'sequence']),
                ('Unity Repaired by Moving, Not Patching',
                 'A paragraph is unified when every sentence supports its controlling idea, '
                 'so an off-topic sentence is repaired by moving or deleting it rather than '
                 'by inserting a transition that pretends the two ideas connect.',
                 ['unity', 'coherence', 'off-topic sentence']),
                ('Cohesion Through a Deliberate Reference Chain',
                 'Cohesion holds when a key term or a clear pronoun carries the topic from '
                 'one sentence to the next, so replacing a repeated term with a loose synonym '
                 'breaks the chain even though every sentence still parses.',
                 ['cohesion', 'repetition', 'reference chain']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 2
    {
        'unit': 'Knowledge of Language',
        'about': ('The unit that works on how a correct sentence is also a good one: cutting '
                  'what repeats itself, choosing the word that names the relation exactly, '
                  'keeping a sentence unambiguous, and matching tone and register to the '
                  'reader the passage is written for.'),
        'sections': [],
        'topics': [
            ('Expressing Ideas Clearly', [
                ('Concision Between Equivalent Choices',
                 'When two choices are both grammatical and mean the same thing, the shorter '
                 'one is the answer, so "the reason is because" loses to "because" and "at '
                 'this point in time" loses to "now".',
                 ['concision', 'wordiness', 'economy']),
                ('Redundancy Hidden Inside a Phrase',
                 'A phrase is redundant when one of its words already contains the meaning of '
                 'another, which is why "past history", "annual ... each year" and "return '
                 'back" fail although no single word in them is ungrammatical.',
                 ['redundancy', 'tautology', 'repetition']),
                ('Precision Over Vague Approximation',
                 'The correct word names exactly the relation or quantity the passage '
                 'establishes, so a choice that overstates ("always" for "often") or '
                 'understates ("changed" for "declined") is wrong even when it is not '
                 'strictly false.',
                 ['precision', 'denotation', 'word choice']),
                ('Ambiguity in Reference and Attachment',
                 'A sentence is unclear when a pronoun could point to either of two nouns or '
                 'a trailing phrase could attach to either of two constituents, so the repair '
                 'makes the referent or the attachment explicit rather than merely '
                 'grammatical.',
                 ['ambiguity', 'clear reference', 'attachment']),
            ]),
            ('Style', [
                ('Tone Must Fit Audience and Purpose',
                 'Tone is the writer\'s attitude toward the subject, and a passage written to '
                 'inform a general reader rejects sarcasm, slang and rhetorical questions even '
                 'when the sentence carrying them is grammatical.',
                 ['tone', 'audience', 'attitude']),
                ('Register Stays Consistent',
                 'Register is the level of formality a passage sustains, so a single '
                 'colloquial phrase inside academic prose -- "a whole lot of" in a report -- is '
                 'the element to change rather than the sentences around it.',
                 ['register', 'formality', 'consistency']),
                ('Figurative Language Serves the Comparison',
                 'A metaphor or simile earns its place when it sharpens a comparison the '
                 'passage is already making, and it fails when it introduces an image the '
                 'passage never uses or mixes two incompatible images in one clause.',
                 ['figurative language', 'metaphor', 'mixed image']),
            ]),
        ],
    },
    # ------------------------------------------------------------------ 3
    {
        'unit': 'Conventions of Standard English',
        'about': ('The rule unit: what makes a group of words a sentence, how clauses may be '
                  'joined, how items in a series are kept parallel and how modifiers are kept '
                  'next to what they modify, then the agreement, case and tense rules, and '
                  'finally the punctuation that marks clause boundaries, lists and '
                  'possession.'),
        'sections': [],
        'topics': [
            ('Sentence Structure and Formation', [
                ('Fragments Have No Independent Clause',
                 'A word group is a fragment when it lacks a subject-verb pair that can stand '
                 'alone, which is why a subordinate clause beginning "because", a participial '
                 'phrase or an appositive cannot be punctuated as a sentence.',
                 ['fragment', 'independent clause', 'sentence completeness']),
                ('Run-Ons and Comma Splices',
                 'Two independent clauses joined with no punctuation make a run-on, and the '
                 'same two joined by a comma alone make a comma splice, so the repair is a '
                 'period, a semicolon, or a comma with a coordinating conjunction.',
                 ['run-on', 'comma splice', 'independent clause']),
                ('Clause Boundaries Decide the Join',
                 'Whether a clause can stand alone decides how it may be joined to its '
                 'neighbour, so inserting "although" turns an independent clause into a '
                 'dependent one that a comma may then attach to the main clause.',
                 ['clause boundary', 'subordination', 'coordination']),
                ('Parallel Structure in a Series',
                 'Items joined by "and", "or" or a correlative pair must share grammatical '
                 'form, so a series mixing a noun, a gerund and a clause is repaired by '
                 'casting all three members in the same form.',
                 ['parallelism', 'series', 'correlative conjunction']),
                ('Modifier Placement and Dangling Modifiers',
                 'A modifier is read as attaching to the nearest word it can modify, so an '
                 'introductory participial phrase must be followed immediately by the subject '
                 'that performs its action or the phrase dangles.',
                 ['modifier placement', 'dangling modifier', 'misplaced modifier']),
            ]),
            ('Usage Conventions', [
                ('Subject-Verb Agreement Across Intervening Words',
                 'The verb agrees with the grammatical subject rather than with a noun inside '
                 'a prepositional phrase between them, so "the list of items is" is correct '
                 'although "items" stands directly beside the verb.',
                 ['subject-verb agreement', 'intervening phrase', 'number']),
                ('Compound and Indefinite Subjects',
                 'Subjects joined by "and" take a plural verb while "each", "everyone" and '
                 '"neither" used alone take a singular one, and with "either ... or" or '
                 '"neither ... nor" the verb agrees with the nearer subject.',
                 ['compound subject', 'indefinite pronoun', 'agreement']),
                ('Pronoun Case by Grammatical Slot',
                 'A pronoun takes subject case where it is the subject of a verb and object '
                 'case where it is the object of a verb or a preposition, so "between you and '
                 'me" is correct and "for whoever calls" keeps "whoever" as the subject of '
                 '"calls".',
                 ['pronoun case', 'who and whom', 'object of preposition']),
                ('Pronoun-Antecedent Agreement',
                 'A pronoun must match its antecedent in number and person, so a singular '
                 'antecedent such as "a student" or "the company" takes a singular pronoun in '
                 'formal written English no matter how far away it stands.',
                 ['pronoun agreement', 'antecedent', 'singular']),
                ('Tense Consistency Within a Passage',
                 'A passage keeps one time frame until a shift is marked, so a narrative cast '
                 'in the past tense keeps its verbs past while a comment on a text that still '
                 'exists stays in the present.',
                 ['tense consistency', 'time frame', 'sequence of tenses']),
                ('Idiom Fixes the Preposition',
                 'English idiom fixes which preposition a verb or adjective takes, so "differ '
                 'from", "capable of" and "preoccupied with" are correct forms that no rule of '
                 'grammar derives and that have to be recognised rather than reasoned out.',
                 ['idiom', 'preposition', 'usage']),
            ]),
            ('Punctuation Conventions', [
                ('Non-Essential Clauses Take Two Commas',
                 'A non-essential clause or appositive is set off by commas on both sides, so '
                 'closing it with one comma only fuses it to the rest of the sentence and '
                 'misreads which information is parenthetical.',
                 ['non-essential clause', 'comma pair', 'appositive']),
                ('Comma Before a Conjunction Joining Clauses',
                 'A comma is required before "and", "but" or "so" only when it joins two '
                 'independent clauses, so a compound predicate takes no comma while two full '
                 'clauses do.',
                 ['comma', 'coordinating conjunction', 'compound sentence']),
                ('Commas in a Series and Between Coordinate Adjectives',
                 'Commas separate three or more items in a series and separate coordinate '
                 'adjectives that each modify the noun independently, but no comma goes '
                 'between a cumulative adjective and the one that forms a unit with the noun, '
                 'as in "a small wooden box".',
                 ['serial comma', 'coordinate adjectives', 'list']),
                ('Semicolon Where a Period Could Stand',
                 'A semicolon may join two independent clauses or separate list items that '
                 'already contain commas, but it may not follow a dependent clause, introduce '
                 'a list, or attach a fragment to a sentence.',
                 ['semicolon', 'independent clause', 'complex list']),
                ('Colon After a Complete Statement',
                 'A colon must follow an independent clause and introduce what that clause '
                 'promises -- a list, an explanation or a quotation -- so a colon between a '
                 'verb and its object, after "such as", or inside a clause is wrong.',
                 ['colon', 'introduce a list', 'complete clause']),
                ('Apostrophe for Possession or Omission',
                 'An apostrophe marks possession or a contraction and never a plain plural, so '
                 '"its" is possessive, "it\'s" means "it is", and a plural such as "the '
                 '1990s" takes none.',
                 ['apostrophe', 'possession', 'contraction']),
            ]),
        ],
    },
]
