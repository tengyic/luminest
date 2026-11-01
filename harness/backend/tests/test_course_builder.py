"""Tests for the "build a course from your own material" pipeline.

These pin the four promises the feature makes, each of which is easy to break
silently:

1. every generated concept cites a **verbatim** span of the learner's source;
2. the generated graph is a real **DAG** whose edges name real concepts;
3. a source too thin to support a course is **refused with a reason**, never
   padded out into a course;
4. a created course is **studyable through the endpoints that already exist**,
   and belongs to exactly one account.

Nothing here needs a network or an API key: the pipeline is offline by design.
"""

from __future__ import annotations

import base64
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app import course_builder as cb
from app import courses, curriculum
from app.config import Settings
from app.main import create_app
from test_api import account, client, settings  # noqa: F401 - fixtures re-exported

#: A real multi-paragraph source, in the shape a learner would paste: a heading
#: and passages that define concepts in terms of earlier ones.
SOURCE = """# Photosynthesis

Photosynthesis is the process by which green plants convert light energy into chemical energy stored in glucose.

Chlorophyll is the green pigment inside chloroplasts that absorbs light energy for photosynthesis.

The light-dependent reactions are the first stage of photosynthesis, where light energy splits water molecules and releases oxygen.

The Calvin cycle is the second stage of photosynthesis, where carbon dioxide is fixed into glucose using the energy from the light-dependent reactions.

Cellular respiration is the process that releases energy from glucose inside every living cell.

Mitochondria are the organelles where cellular respiration takes place and most ATP is produced.

ATP is the molecule that carries usable energy between reactions inside a cell.

Fermentation is an anaerobic pathway that regenerates ATP when oxygen is unavailable.

Glycolysis is the first stage of cellular respiration, where one glucose molecule is split into two pyruvate molecules.

The Krebs cycle is the second stage of cellular respiration, where pyruvate is oxidised and more ATP is generated.
"""

THIN = 'Photosynthesis is the process plants use to turn light into food.'

#: Six paragraphs that are each complete in themselves and name none of the
#: others, so the source yields teaching order but no invented dependency.
INDEPENDENT = '\n\n'.join([
    'Alpha is a distinct idea that stands entirely on its own, with no link to any other term in this list.',
    'Beta is a separate idea that also stands on its own, and nothing here depends on anything before it.',
    'Gamma is another independent idea, written so that it names no earlier term and no later one either.',
    'Delta is a fourth idea of the same kind, complete in itself and connected to none of its neighbours.',
    'Epsilon is a fifth idea that needs no background at all, which is the whole point of the passage here.',
    'Zeta is the last of these ideas, and like the others it is defined only by its own sentence here.',
])

#: Long enough and structured enough to clear every size floor, but written as
#: narrative rather than definition, so it yields no extractable concept at all.
TOO_FEW = (
    'Green plants take in air through the tiny openings in their leaves and give water vapour '
    'back to the sky above them every single day of the growing season.\n\n'
    'Over a long summer the roots reach down through the soil and draw up the water and the '
    'dissolved minerals that the rest of the plant depends on.\n\n'
    'When the days shorten and the nights grow cold the leaves change colour and eventually '
    'fall, and the plant rests quietly until the warmth returns.\n'
)


# ------------------------------------------------------------------- isolation

@pytest.fixture(autouse=True)
def _restore_shared_registries():
    """Undo the global registries a created course is published into.

    A created course becomes studyable by being written into the *same* module-level
    registries the shipped courses live in (``curriculum.CONCEPTS`` and friends). The
    database is per-test, but those registries are per-process, so without this a
    course created in one test would still be visible - and would make
    ``test_a_preview_persists_nothing`` fail - in the next.
    """
    saved = (dict(curriculum.CONCEPTS), dict(curriculum.QUESTIONS),
             dict(curriculum.CONCEPT_COURSE), dict(courses.COURSE_BY_ID),
             dict(cb._RUNTIME_COURSES), dict(cb._RUNTIME_GRAPHS), cb._STORE_FACTORY)
    try:
        yield
    finally:
        curriculum.CONCEPTS.clear(), curriculum.CONCEPTS.update(saved[0])
        curriculum.QUESTIONS.clear(), curriculum.QUESTIONS.update(saved[1])
        curriculum.CONCEPT_COURSE.clear(), curriculum.CONCEPT_COURSE.update(saved[2])
        courses.COURSE_BY_ID.clear(), courses.COURSE_BY_ID.update(saved[3])
        cb._RUNTIME_COURSES.clear(), cb._RUNTIME_COURSES.update(saved[4])
        cb._RUNTIME_GRAPHS.clear(), cb._RUNTIME_GRAPHS.update(saved[5])
        cb._STORE_FACTORY = saved[6]


# --------------------------------------------------------------------- helpers

def make_pdf(text: str) -> bytes:
    """A minimal but structurally valid PDF, so the PDF path is exercised for real.

    Hand-built rather than generated by a library: the point of the test is that
    *this server* parses a real PDF byte stream, and a fixture produced by the
    same library would not prove that. The text carries its paragraph breaks
    inside the run: pypdf preserves them, and the builder reads them back as
    paragraphs - see ``_pdf_paragraphs``, which also reassembles a real PDF's
    line-per-run layout into paragraphs.
    """
    content = f'BT /F1 12 Tf 72 720 Td ({text}) Tj ET'.encode('latin-1')
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] '
        b'/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length ' + str(len(content)).encode() + b' >>\nstream\n' + content + b'\nendstream',
    ]
    out = bytearray(b'%PDF-1.4\n')
    offsets: list[int] = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f'{index} 0 obj\n'.encode() + body + b'\nendobj\n'
    xref_at = len(out)
    out += f'xref\n0 {len(objects) + 1}\n'.encode()
    out += b'0000000000 65535 f \n'
    for offset in offsets:
        out += f'{offset:010d} 00000 n \n'.encode()
    out += (f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n'
            f'startxref\n{xref_at}\n%%EOF\n').encode()
    return bytes(out)


def make_docx(paragraphs: list[str]) -> bytes:
    """A minimal valid .docx: a zip whose word/document.xml holds the paragraphs."""
    ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    body = ''.join(f'<w:p><w:r><w:t>{text}</w:t></w:r></w:p>' for text in paragraphs)
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<w:document xmlns:w="{ns}"><w:body>{body}</w:body></w:document>')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types/>')
        archive.writestr('word/document.xml', document)
    return buffer.getvalue()


def build(plan_source: str = SOURCE, **kwargs):
    return cb.plan_course(cb.intake_text(plan_source), **kwargs)


def create(client, headers, *, title='My Biology', text=SOURCE, subject='Biology'):
    response = client.post('/api/v1/create/course', headers=headers,
                           json={'title': title, 'text': text, 'subject': subject})
    assert response.status_code == 201, response.text
    return response.json()['course']['id']


def enrol(client, headers, course_id):
    response = client.post(f'/api/v1/my-courses/{course_id}/enrol', headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# ------------------------------------------------------------------ provenance

def test_every_concept_carries_a_verbatim_span_of_the_source():
    plan = build()
    assert len(plan.concepts) >= cb.MIN_CONCEPTS
    for concept_id, entry in plan.concepts.items():
        span = entry['source_span']
        assert span.strip(), f'{concept_id} has an empty source span'
        assert span in SOURCE, f'{concept_id} span is not a verbatim slice of the source: {span!r}'
        # The graph node carries the same provenance, so a client reading the map
        # sees exactly what a client reading the lesson sees.
        assert plan.graph.nodes[concept_id].provenance['span'] == span
        assert plan.graph.nodes[concept_id].provenance['licence_class'] == 'cc_by'


def test_extraction_is_deterministic():
    first, second = build(), build()
    assert [entry['title'] for entry in first.concepts.values()] == \
           [entry['title'] for entry in second.concepts.values()]
    def strip(prefix, values):
        return sorted(value.replace(prefix, '') for value in values)
    assert strip(first.course_id + '_', first.graph.nodes) == \
           strip(second.course_id + '_', second.graph.nodes)
    assert strip(first.course_id, first.questions) == strip(second.course_id, second.questions)


# ---------------------------------------------------------------------- graph

def test_generated_graph_is_a_dag_and_every_edge_names_a_real_concept():
    plan = build()
    graph = plan.graph
    assert graph.edges, 'a source that defines concepts in terms of earlier ones must yield edges'
    assert graph._cycles() == [], 'the generated graph contains a cycle'
    assert graph._cycles(include_sequence=True) == [], 'the teaching order contradicts the graph'
    assert graph.errors() == []
    # A topological order only exists for an acyclic graph; this raises otherwise.
    assert len(graph.topological_order()) == len(graph.nodes)
    for source_id, target_id in (*graph.edges, *graph.sequence_edges):
        assert source_id in graph.nodes and target_id in graph.nodes
    for node in graph.nodes.values():
        assert set(node.prerequisites) <= set(graph.nodes)
        assert set(node.sequence_predecessors) <= set(graph.nodes)
        assert node.has_lesson


def test_prerequisites_come_from_the_source_not_from_position_alone():
    """Unrelated material yields teaching order but no invented dependencies."""
    # INDEPENDENT is the fixture this test is about: six paragraphs, each complete in
    # itself and naming none of the others. It is deliberately not used inline - an
    # inline six-sentence source is 358 characters and is refused for being too short,
    # which makes the test assert the wrong refusal and hide the one it meant to make.
    plan = build(INDEPENDENT)
    assert plan.graph.edges == [], 'no concept references another, so no hard edge is claimed'
    assert plan.graph.sequence_edges, 'the source order is still recorded as teaching order'
    assert plan.graph._cycles(include_sequence=True) == []


# ------------------------------------------------------------------- refusals

def test_a_too_thin_source_is_refused_with_a_reason_and_a_minimum():
    with pytest.raises(cb.BuildRefused) as excinfo:
        build(THIN)
    refusal = excinfo.value.refusal
    assert refusal.code == 'source_too_short'
    assert refusal.minimum['characters'] == cb.MIN_SOURCE_CHARS
    assert 'at least' in refusal.reason
    payload = refusal.to_dict()
    assert payload['refused'] is True
    assert {rule['code'] for rule in payload['rules']} >= {
        'source_too_short', 'too_few_paragraphs', 'too_few_concepts'}


def test_a_single_paragraph_is_refused_even_when_it_is_long():
    long_paragraph = ('Photosynthesis is the process plants use. ' * 20).strip()
    assert cb.word_count(long_paragraph) > cb.MIN_SOURCE_WORDS
    with pytest.raises(cb.BuildRefused) as excinfo:
        build(long_paragraph)
    assert excinfo.value.refusal.code == 'too_few_paragraphs'


def test_a_source_with_too_few_concepts_is_refused():
    # TOO_FEW is the fixture for this: long enough to clear the size floor, written
    # as narrative rather than definition, so the concept refusal is the one that fires.
    with pytest.raises(cb.BuildRefused) as excinfo:
        build(TOO_FEW)
    assert excinfo.value.refusal.code == 'too_few_concepts'


def test_the_refusal_contract_is_data_and_is_served(client):
    headers, _ = account(client)
    response = client.post('/api/v1/create/preview', headers=headers, json={'text': THIN})
    assert response.status_code == 422
    detail = response.json()['detail']
    assert detail['refused'] is True and detail['code'] == 'source_too_short'
    assert detail['minimum']['words'] == cb.MIN_SOURCE_WORDS
    assert any(rule['code'] == 'too_few_concepts' for rule in detail['rules'])


# ------------------------------------------------------------------ questions

def test_every_question_has_four_options_one_correct_and_a_diagnosis_per_distractor():
    plan = build()
    assert plan.questions
    for question_id, question in plan.questions.items():
        assert question['id'] == question_id
        assert len(question['options']) == 4
        option_ids = [option['id'] for option in question['options']]
        assert len(set(option_ids)) == 4
        assert question['answer_id'] in option_ids
        correct = [option for option in question['options']
                   if option['id'] == question['answer_id']]
        assert len(correct) == 1
        assert question['answer_text'] == correct[0]['text']
        # Every wrong option is diagnosed, not merely marked wrong.
        wrong = [option_id for option_id in option_ids if option_id != question['answer_id']]
        assert set(question['distractor_diagnoses']) == set(wrong)
        for option_id, diagnosis in question['distractor_diagnoses'].items():
            assert diagnosis['category'] and diagnosis['reason'] and diagnosis['next_action']
        # Every item cites its concept and the passage it came from.
        assert question['concept_id'] in plan.concepts
        assert question['source_span'] in SOURCE
        assert question['source_span'] == plan.concepts[question['concept_id']]['source_span']
        assert question['difficulty'] in (1, 2, 3, 4, 5)
        assert question['difficulty_band'] in ('foundation', 'core', 'extension')


def test_every_concept_has_more_than_one_variant():
    plan = build()
    counts: dict[str, int] = {}
    for question in plan.questions.values():
        counts[question['concept_id']] = counts.get(question['concept_id'], 0) + 1
    assert set(counts) == set(plan.concepts)
    assert min(counts.values()) >= 2


# ------------------------------------------------------------------ studyable

def test_a_created_course_is_studyable_through_the_existing_endpoints(client):
    headers, _ = account(client)
    course_id = create(client, headers)
    enrol(client, headers, course_id)

    curriculum_payload = client.get('/api/v1/curriculum', headers=headers).json()
    assert curriculum_payload['course']['id'] == course_id
    assert curriculum_payload['concepts'], 'the course must offer concepts'
    for concept in curriculum_payload['concepts']:
        assert concept['course_id'] == course_id
        assert concept['generated'] is True

    graph = client.get('/api/v1/knowledge-graph', headers=headers).json()
    assert graph['course']['id'] == course_id
    assert graph['stats']['concepts'] == len(curriculum_payload['concepts'])
    node_ids = {node['id'] for node in graph['nodes']}
    assert node_ids == {concept['id'] for concept in curriculum_payload['concepts']}

    concept_id = curriculum_payload['concepts'][0]['id']
    lesson = client.get(f'/api/v1/lessons/{concept_id}', headers=headers)
    assert lesson.status_code == 200, lesson.text
    body = lesson.json()
    assert body['id'] == concept_id and body['blocks']
    assert any(block.get('source_span') for block in body['blocks'])

    question = client.get('/api/v1/questions/next', headers=headers,
                          params={'mode': 'practice', 'concept_id': concept_id})
    assert question.status_code == 200, question.text
    assert question.json()['concept_id'] == concept_id
    assert question.json()['id'] in curriculum.QUESTIONS


def test_a_created_course_survives_a_restart_of_the_process(client):
    """The registry is in memory, so a persisted course must be re-hydrated on demand."""
    headers, _ = account(client)
    course_id = create(client, headers)
    enrol(client, headers, course_id)

    # A fresh process has neither the runtime registry nor the session factory.
    cb._RUNTIME_COURSES.clear()
    cb._RUNTIME_GRAPHS.clear()
    cb._STORE_FACTORY = None
    courses.COURSE_BY_ID.pop(course_id, None)
    try:
        # Until something touches this account's courses, the learner degrades to the
        # default course rather than to a 500 or a dangling id.
        degraded = client.get('/api/v1/knowledge-graph', headers=headers)
        assert degraded.status_code == 200
        assert degraded.json()['course']['id'] == courses.DEFAULT_COURSE_ID

        # Listing the account's own courses re-hydrates them, and the course is back.
        assert client.get('/api/v1/my-courses', headers=headers).json()['count'] == 1
        restored = client.get('/api/v1/knowledge-graph', headers=headers)
        assert restored.status_code == 200
        assert restored.json()['course']['id'] == course_id
        assert restored.json()['stats']['concepts'] > 0
    finally:
        cb._STORE_FACTORY = None


def test_deleting_a_course_removes_it_and_resets_the_active_course(client):
    headers, _ = account(client)
    course_id = create(client, headers)
    enrol(client, headers, course_id)
    concept_ids = set(curriculum.course_concepts(course_id))
    assert concept_ids

    deleted = client.delete(f'/api/v1/my-courses/{course_id}', headers=headers)
    assert deleted.status_code == 200
    assert deleted.json() == {'deleted': True, 'course_id': course_id,
                              'active_course_reset': True}
    assert client.get('/api/v1/my-courses', headers=headers).json()['count'] == 0
    assert not (set(curriculum.CONCEPTS) & concept_ids), 'lessons outlived their course'
    assert not (set(curriculum.CONCEPT_COURSE) & concept_ids)
    for question_id, question in curriculum.QUESTIONS.items():
        assert question.get('concept_id') not in concept_ids, question_id
    assert client.get('/api/v1/curriculum', headers=headers).json()['course']['id'] == \
        courses.DEFAULT_COURSE_ID
    assert client.get(f'/api/v1/my-courses/{course_id}', headers=headers).status_code == 404


# --------------------------------------------------------------- per-account

def test_a_course_belongs_to_one_account_only(client):
    alice, _ = account(client, 'alice')
    bob, _ = account(client, 'bob')
    course_id = create(client, alice, title='Alice material')

    assert client.get('/api/v1/my-courses', headers=bob).json()['count'] == 0
    assert client.get(f'/api/v1/my-courses/{course_id}', headers=bob).status_code == 404
    assert client.delete(f'/api/v1/my-courses/{course_id}', headers=bob).status_code == 404
    assert client.post(f'/api/v1/my-courses/{course_id}/enrol', headers=bob).status_code == 404
    # Alice's course is untouched by Bob's attempts.
    assert client.get('/api/v1/my-courses', headers=alice).json()['count'] == 1
    assert client.get(f'/api/v1/my-courses/{course_id}', headers=alice).status_code == 200


def test_an_anonymous_request_is_refused(client):
    assert client.get('/api/v1/my-courses').status_code == 401
    assert client.post('/api/v1/create/preview', json={'text': SOURCE}).status_code == 401


def test_a_preview_persists_nothing(client):
    headers, _ = account(client)
    response = client.post('/api/v1/create/preview', headers=headers, json={'text': SOURCE})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['concepts'] and payload['questions'] and payload['graph']['nodes']
    assert payload['graph_stats']['concepts'] == len(payload['concepts'])
    assert client.get('/api/v1/my-courses', headers=headers).json()['count'] == 0
    assert not any(concept_id.startswith('mine_') for concept_id in curriculum.CONCEPTS)


# -------------------------------------------------------------------- intake

def make_textbook_pdf(lines: list[tuple[float, str, str]]) -> bytes:
    """A PDF with real *structure*: per-line font and size, the way a textbook
    sets a module heading in large semibold, a term in bold, and prose in the
    body face.

    ``lines`` is ``(size, font, text)`` in reading order, ``font`` being
    ``'F1'`` (the body face) or ``'F2'`` (its bold). The single-font PDF above
    proves the parser reads a byte stream; this one proves it reads the
    *formatting*, which is what a real textbook upload depends on.
    """
    ops = []
    y = 720.0
    for size, font, text in lines:
        escaped = (text.replace('\\', r'\\').replace('(', r'\(')
                       .replace(')', r'\)').replace('\r', ' ').replace('\n', ' '))
        ops.append(f'BT /{font} {size:g} Tf 72 {y:g} Td ({escaped}) Tj ET')
        y -= 22.0
    content = '\n'.join(ops).encode('latin-1')
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] '
        b'/Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>',
        b'<< /Length ' + str(len(content)).encode() + b' >>\nstream\n' + content + b'\nendstream',
    ]
    out = bytearray(b'%PDF-1.4\n')
    offsets: list[int] = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f'{index} 0 obj\n'.encode() + body + b'\nendobj\n'
    xref_at = len(out)
    out += f'xref\n0 {len(objects) + 1}\n'.encode()
    out += b'0000000000 65535 f \n'
    for offset in offsets:
        out += f'{offset:010d} 00000 n \n'.encode()
    out += (f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n'
            f'startxref\n{xref_at}\n%%EOF\n').encode()
    return bytes(out)


#: A miniature textbook page in the shape a real one has: a large module
#: heading, a learning objective, prose, bold run-in terms, a wrapped bold
#: feature heading, a folio number, and the three kinds of junk a flattened
#: extraction used to read as concepts - a quiz stem, a narrative name and a
#: one-word question.
TEXTBOOK_LINES = [
    (24, 'F2', 'Module 0.2 The Need for Psychological Science'),
    (12, 'F1', '0.2-1 Explain how cognitive biases show why science beats common sense.'),
    (12, 'F1', 'Some people suppose that psychology is mere common sense.'),
    (12, 'F2', 'Hindsight Bias'),
    (12, 'F1', 'Hindsight bias is the tendency to believe that we knew it all along.'),
    (12, 'F2', 'Overconfidence'),
    (12, 'F1', 'Overconfidence is the tendency to overestimate how much we know.'),
    (16, 'F2', 'Did We Know It All Along? Hindsight'),
    (16, 'F2', 'Bias'),
    (12, 'F1', 'Consider how easy it is to draw the bullseye after the arrow strikes.'),
    (12, 'F1', 'Which of the following is an example of hindsight bias?'),
    (12, 'F1', 'Armend is certain that electric cars will represent 80 percent of sales.'),
    (12, 'F1', 'Why are we so prone to pattern-seeking?'),
    (20, 'F1', '95'),
    (24, 'F2', 'Module 0.3 The Scientific Method'),
    (12, 'F2', 'theory'),
    (12, 'F1', 'A theory is an explanation using an integrated set of principles.'),
    (12, 'F2', 'hypotheses'),
    (12, 'F1', 'Hypotheses are testable predictions that follow from a theory.'),
    (12, 'F2', 'peer reviewers'),
    (12, 'F1', 'Peer reviewers are scientific experts who evaluate a research report.'),
    (12, 'F1', 'The Scientific Method is how theories are tested and revised.'),
]


def test_a_textbook_pdf_yields_its_terms_not_its_furniture():
    """The regression this pins: a real textbook upload produced concepts named
    "Which of the following", "Armend" and "Hindsight Bias Consider how easy
    it" - the quiz stems, the names inside the practice questions and the
    feature-box heading with its prose glued on. The terms were buried in them."""
    data = make_textbook_pdf(TEXTBOOK_LINES)
    text, fmt = cb._detect_and_extract(data)
    assert fmt == 'pdf'
    titles = [concept.title for concept in cb.extract_concepts(text)]
    assert 'Hindsight Bias' in titles
    assert 'Overconfidence' in titles
    # The module heading loses its "Module 0.2" running prefix.
    assert 'The Need for Psychological Science' in titles
    # And none of the junk survives, under any spelling.
    for junk in ('Which of the following', 'Armend', 'Why', 'Consider how easy',
                 'Some people suppose', '95'):
        assert junk not in titles, f'{junk!r} was read as a concept'


def test_a_wrapped_bold_heading_is_one_term():
    """A feature-box heading wraps across two baselines ("Did We Know It All
    Along? Hindsight" + "Bias"). Reading it as two runs produced a concept
    called "Bias"; joining the lines produces the term, once."""
    data = make_textbook_pdf(TEXTBOOK_LINES)
    text, _ = cb._detect_and_extract(data)
    concepts = cb.extract_concepts(text)
    titles = [concept.title for concept in concepts]
    assert titles.count('Hindsight Bias') == 1
    assert 'Bias' not in titles and 'Hindsight' not in titles
    assert 'Did We Know It All Along' not in titles


def test_the_term_markers_never_reach_the_learner():
    """The ``**`` markers are this module's private notation for "the font was
    weighted here". They were never in the document, so a span quoted in a
    lesson or offered as a quiz option must not carry them."""
    data = make_textbook_pdf(TEXTBOOK_LINES)
    text, _ = cb._detect_and_extract(data)
    assert '**' in text  # the extractor needs them
    for concept in cb.extract_concepts(text):
        assert '**' not in concept.span
        assert '**' not in concept.summary
        assert '**' not in concept.title


def test_a_textbook_course_plans_end_to_end():
    data = make_textbook_pdf(TEXTBOOK_LINES)
    plan = cb.plan_course(cb.intake_bytes('textbook.pdf', data),
                          title='The Need for Psychological Science')
    assert len(plan.concepts) >= cb.MIN_CONCEPTS
    assert plan.questions
    assert plan.stats()['with_lesson'] == len(plan.concepts)
    # Every concept's lesson quotes the source passage it came from, marker-free.
    for concept_id, concept in plan.concepts.items():
        entry = concept if isinstance(concept, dict) else {}
        blocks = entry.get('blocks') or []
        assert blocks, concept_id
        for block in blocks:
            assert '**' not in str(block.get('body', ''))


def test_upload_can_save_and_enrol_the_course(client):
    """A textbook chapter is not something a client can echo back as text, so
    the upload route must be able to store what it read - not only preview it."""
    headers, _ = account(client)
    document = make_docx([line for line in SOURCE.split('\n') if line.strip()])
    response = client.post('/api/v1/create/upload', headers=headers,
                           params={'save': '1'},
                           files={'file': ('notes.docx', document,
                                           'application/vnd.openxmlformats-officedocument'
                                           '.wordprocessingml.document'),
                                  'title': (None, 'My uploaded course'),
                                  'subject': (None, 'Biology')})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['created'] is True
    assert payload['enrolled'] is True
    course_id = payload['course_id']
    # It is stored, it is the active course, and it is studyable like any other.
    assert client.get('/api/v1/my-courses', headers=headers).json()['count'] == 1
    assert client.get(f'/api/v1/my-courses/{course_id}', headers=headers).status_code == 200
    enrolled = client.get('/api/v1/me', headers=headers).json()
    assert enrolled.get('course_id') == course_id


def test_upload_preview_still_persists_nothing(client):
    headers, _ = account(client)
    response = client.post(
        '/api/v1/create/upload', headers=headers,
        files={'file': ('notes.txt', SOURCE.encode('utf-8'), 'text/plain')})
    assert response.status_code == 200, response.text
    assert 'created' not in response.json()
    assert client.get('/api/v1/my-courses', headers=headers).json()['count'] == 0


def test_upload_reads_a_multipart_body(client):
    headers, _ = account(client)
    response = client.post(
        '/api/v1/create/upload', headers=headers,
        files={'file': ('notes.txt', SOURCE.encode('utf-8'), 'text/plain')})
    assert response.status_code == 200, response.text
    assert response.json()['graph_stats']['concepts'] >= cb.MIN_CONCEPTS
    assert response.json()['source']['label'] == 'notes.txt'


def test_upload_reads_a_raw_body_with_a_filename(client):
    headers, _ = account(client)
    # The bytes travel raw, so the client declares what they are (a body with no
    # content type is refused at the boundary before any route sees it), and the
    # filename rides in the query string because a raw body has no part headers.
    response = client.post('/api/v1/create/upload',
                           headers={**headers, 'content-type': 'text/markdown'},
                           params={'filename': 'notes.md'},
                           content=SOURCE.encode('utf-8'))
    assert response.status_code == 200, response.text
    assert response.json()['graph_stats']['concepts'] >= cb.MIN_CONCEPTS


def test_upload_detects_docx_by_content_not_by_extension(client):
    headers, _ = account(client)
    document = make_docx([line for line in SOURCE.split('\n') if line.strip()])
    response = client.post('/api/v1/create/upload', headers=headers,
                           files={'file': ('mislabelled.txt', document,
                                           'application/octet-stream')})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['source']['format'] == 'docx'
    assert payload['graph_stats']['concepts'] >= cb.MIN_CONCEPTS


def test_upload_reads_a_pdf(client):
    headers, _ = account(client)
    paragraphs = [line.strip() for line in SOURCE.split('\n') if line.strip()]
    # Joined with a blank line, not a space. The source is written as separate
    # paragraphs on purpose - the paragraph floor is what makes a prerequisite order
    # buildable - so the PDF has to carry those breaks or it extracts back as one
    # block of prose and is refused with `too_few_paragraphs`.
    text = '\n\n'.join(paragraphs)
    response = client.post('/api/v1/create/upload', headers=headers,
                           files={'file': ('notes.pdf', make_pdf(text), 'application/pdf')})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['source']['format'] == 'pdf'
    assert payload['graph_stats']['concepts'] >= cb.MIN_CONCEPTS


def test_upload_refuses_a_file_it_cannot_parse(client):
    headers, _ = account(client)
    response = client.post('/api/v1/create/upload', headers=headers,
                           files={'file': ('scan.pdf', b'\x00\x01\x02\x03\xff\xfe binary', 
                                           'application/octet-stream')})
    assert response.status_code == 422
    assert response.json()['detail']['refused'] is True


def test_upload_refuses_an_empty_file(client):
    headers, _ = account(client)
    response = client.post('/api/v1/create/upload', headers=headers,
                           files={'file': ('empty.txt', b'', 'text/plain')})
    assert response.status_code == 422
    assert response.json()['detail']['code'] in ('empty_file', 'missing_file')


def test_upload_without_a_file_part_is_a_structured_refusal(client):
    headers, _ = account(client)
    response = client.post('/api/v1/create/upload', headers=headers,
                           files={'not_the_file_field': ('notes.txt', SOURCE.encode(), 'text/plain')})
    assert response.status_code == 422
    assert response.json()['detail']['refused'] is True


# ----------------------------------------------------------------- url intake

def test_a_non_https_url_is_refused_without_fetching(client):
    headers, _ = account(client)
    response = client.post('/api/v1/create/preview', headers=headers,
                           json={'url': 'http://example.org/notes'})
    assert response.status_code == 422
    detail = response.json()['detail']
    assert detail['refused'] is True and detail['code'] == 'insecure_url'


def test_an_oversized_page_is_refused_and_does_not_raise(client, monkeypatch):
    headers, _ = account(client)

    def huge(url, max_bytes):
        raise cb.IntakeRefused(cb.Refusal(
            code='source_too_large',
            reason=f'That page is larger than the {max_bytes} byte limit.',
            minimum={'bytes': max_bytes}))

    monkeypatch.setattr(cb, 'URL_FETCHER', huge)
    response = client.post('/api/v1/create/preview', headers=headers,
                           json={'url': 'https://example.org/huge'})
    assert response.status_code == 422
    detail = response.json()['detail']
    assert detail['refused'] is True
    assert detail['code'] == 'source_too_large'
    assert detail['minimum']['bytes'] == cb.URL_MAX_BYTES


def test_a_login_walled_page_is_refused(client, monkeypatch):
    html = (b'<html><body><h1>Sign in</h1><form>'
            b'<input type="text" name="user"><input type="password" name="pw">'
            b'</form></body></html>')

    def walled(url, max_bytes):
        return url, 'text/html; charset=utf-8', html

    monkeypatch.setattr(cb, 'URL_FETCHER', walled)
    headers, _ = account(client)
    response = client.post('/api/v1/create/preview', headers=headers,
                           json={'url': 'https://example.org/private'})
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'login_walled'


def test_a_non_text_content_type_is_refused(client, monkeypatch):
    monkeypatch.setattr(cb, 'URL_FETCHER',
                        lambda url, cap: (url, 'image/png', b'\x89PNG\r\n'))
    headers, _ = account(client)
    response = client.post('/api/v1/create/preview', headers=headers,
                           json={'url': 'https://example.org/picture.png'})
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'unsupported_content_type'


def test_a_fetch_failure_is_a_structured_refusal_not_a_500(client, monkeypatch):
    def boom(url, max_bytes):
        raise cb.IntakeRefused(cb.Refusal(code='fetch_failed',
                                          reason='That page could not be fetched.'))

    monkeypatch.setattr(cb, 'URL_FETCHER', boom)
    headers, _ = account(client)
    response = client.post('/api/v1/create/preview', headers=headers,
                           json={'url': 'https://example.org/down'})
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'fetch_failed'


def test_a_redirect_to_http_is_refused(client, monkeypatch):
    monkeypatch.setattr(cb, 'URL_FETCHER',
                        lambda url, cap: ('http://example.org/plain', 'text/plain', b'hello there'))
    headers, _ = account(client)
    response = client.post('/api/v1/create/preview', headers=headers,
                           json={'url': 'https://example.org/redirects'})
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'insecure_redirect'


def test_an_https_page_is_ingested(client, monkeypatch):
    html = ('<html><body>' + ''.join(f'<p>{line.strip()}</p>'
                                     for line in SOURCE.split('\n') if line.strip())
            + '</body></html>').encode('utf-8')
    monkeypatch.setattr(cb, 'URL_FETCHER',
                        lambda url, cap: ('https://example.org/notes', 'text/html', html))
    headers, _ = account(client)
    response = client.post('/api/v1/create/preview', headers=headers,
                           json={'url': 'https://example.org/notes'})
    assert response.status_code == 200, response.text
    assert response.json()['source']['kind'] == 'url'
    assert response.json()['graph_stats']['concepts'] >= cb.MIN_CONCEPTS


def test_a_missing_source_is_refused(client):
    headers, _ = account(client)
    response = client.post('/api/v1/create/preview', headers=headers, json={})
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'missing_source'


# ------------------------------------------------------------------ my-courses

def test_my_courses_lists_the_account_own_courses_with_their_graph(client):
    headers, _ = account(client)
    first = create(client, headers, title='First course')
    second = create(client, headers, title='Second course')

    listing = client.get('/api/v1/my-courses', headers=headers).json()
    assert {row['id'] for row in listing['courses']} == {first, second}
    assert all(row['custom'] is True and row['generated'] is True for row in listing['courses'])
    assert all(row['concepts'] > 0 and row['questions'] > 0 for row in listing['courses'])

    detail = client.get(f'/api/v1/my-courses/{first}', headers=headers).json()
    assert detail['id'] == first
    assert detail['lesson_count'] == len(detail['concepts_list'])
    assert detail['graph_stats']['concepts'] == detail['lesson_count']
    assert detail['graph']['nodes']
    assert detail['source']['kind'] == 'text'
    assert detail['enrolled'] is False

    assert enrol(client, headers, first)['enrolled'] is True
    assert client.get(f'/api/v1/my-courses/{first}', headers=headers).json()['enrolled'] is True
    # Enrolling marks onboarding complete, so the first-run flow does not reappear.
    assert client.get('/api/v1/me', headers=headers).json()['onboarding_complete'] is True


def test_creating_a_course_does_not_leak_it_into_the_shared_catalogue(client):
    headers, _ = account(client)
    create(client, headers, title='Private material')
    catalogue = client.get('/api/v1/courses', headers=headers).json()
    assert all(not row['id'].startswith(cb.COURSE_ID_PREFIX) for row in catalogue['courses'])
    assert catalogue['total_concepts'] == courses.total_concepts()
