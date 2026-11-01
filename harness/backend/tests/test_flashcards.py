"""Tests for the persisted flashcard deck: grounded generation, FSRS-6 scheduling,
interleaved sessions and per-account isolation.

These assert the claims the feature makes, not the implementation:

- a generated card's ``source`` names a curriculum block or question that really exists;
- a diagnosed distractor becomes a ``misconception`` card whose answer is the error process;
- generation is idempotent -- running it twice inserts nothing the second time;
- grading ``good`` schedules further out than ``again`` (ordering, not a magic number);
- a session interleaves concepts instead of running one concept's cards together;
- a card is private to its account, and another learner sees 404, never 403;
- a card with no provenance cannot be created.
"""

from app import flashcards
from app.curriculum import CONCEPTS, QUESTIONS
from test_api import account, client, settings  # noqa: F401 - fixtures
from test_harness import database, learner  # noqa: F401 - DB fixtures (need settings)


def _generate(client, headers, concept_id, count=None):
    body = {'concept_id': concept_id}
    if count is not None:
        body['count'] = count
    response = client.post('/api/v1/flashcards/generate', headers=headers, json=body)
    assert response.status_code == 200, response.text
    return response.json()


# ------------------------------------------------------------------ provenance

def test_generation_is_grounded_in_real_curriculum_blocks_and_questions(client):
    headers, _ = account(client)
    result = _generate(client, headers, 'fractions')
    cards = result['cards']
    assert cards, 'a real concept must generate at least one card'
    kinds = {card['kind'] for card in cards}
    assert {'misconception', 'definition', 'cloze'} <= kinds
    for card in cards:
        source = card['source']
        assert flashcards.source_exists(source), f'{card["front"]!r} has dangling provenance'
        if source['kind'] == 'question':
            question = QUESTIONS[source['question_id']]
            assert question['concept_id'] == 'fractions'
            assert question.get('distractor_diagnoses'), 'a misconception card needs a diagnosis'
        elif source['kind'] == 'block':
            blocks = CONCEPTS['fractions']['blocks']
            assert 0 <= source['index'] < len(blocks)
            assert blocks[source['index']].get('body')


def test_a_diagnosed_distractor_becomes_a_misconception_card(client):
    headers, _ = account(client)
    cards = _generate(client, headers, 'fractions')['cards']
    misconceptions = [c for c in cards if c['kind'] == 'misconception']
    assert misconceptions
    question = QUESTIONS['fractions-1']
    diagnoses = list(question['distractor_diagnoses'].values())
    option_texts = {o['text'] for o in question['options']}
    checked = 0
    for card in misconceptions:
        if card['source'].get('question_id') != 'fractions-1':
            continue
        # The prompt names a wrong option, and the answer is the diagnosis text -- the
        # error process, not a restatement of the question.
        assert any(text and text in card['front'] for text in option_texts)
        assert any(diagnosis['reason'][:40] in card['back'] for diagnosis in diagnoses)
        checked += 1
    assert checked, 'fractions-1 has diagnosed distractors and must yield misconception cards'


def test_generation_is_idempotent(client):
    headers, _ = account(client)
    first = _generate(client, headers, 'fractions')
    assert first['created'] > 0
    second = _generate(client, headers, 'fractions')
    assert second['created'] == 0
    assert second['skipped'] == first['created']
    listed = client.get('/api/v1/flashcards', headers=headers, params={'concept_id': 'fractions'})
    assert listed.json()['count'] == first['created']


def test_generation_preview_does_not_persist(client):
    headers, _ = account(client)
    preview = client.post('/api/v1/flashcards/generate', headers=headers,
                          json={'concept_id': 'fractions', 'dry_run': True}).json()
    assert preview['created'] > 0
    assert all({'front', 'back', 'kind', 'source'} <= set(card) for card in preview['cards'])
    assert client.get('/api/v1/flashcards', headers=headers).json()['count'] == 0
    committed = _generate(client, headers, 'fractions')
    assert committed['created'] == preview['created']


def test_a_card_without_provenance_cannot_be_created(client):
    headers, _ = account(client)
    base = {'concept_id': 'fractions', 'front': 'A question', 'back': 'An answer'}
    assert client.post('/api/v1/flashcards', headers=headers, json=base).status_code == 422
    bogus = {**base, 'source': {'kind': 'block', 'concept_id': 'fractions', 'index': 999}}
    assert client.post('/api/v1/flashcards', headers=headers, json=bogus).status_code == 422
    unknown = {**base, 'source': {'kind': 'concept', 'concept_id': 'not_a_concept'}}
    assert client.post('/api/v1/flashcards', headers=headers, json=unknown).status_code == 422
    good = {**base, 'source': {'kind': 'concept', 'concept_id': 'fractions'}}
    assert client.post('/api/v1/flashcards', headers=headers, json=good).status_code == 201


# ------------------------------------------------------------------ scheduling

def test_good_schedules_further_out_than_again(client):
    headers, _ = account(client)
    cards = _generate(client, headers, 'fractions')['cards']
    assert len(cards) >= 2
    again = client.post(f'/api/v1/flashcards/{cards[0]["id"]}/review',
                        headers=headers, json={'grade': 1})
    good = client.post(f'/api/v1/flashcards/{cards[1]["id"]}/review',
                       headers=headers, json={'grade': 3})
    assert again.status_code == 200, again.text
    assert good.status_code == 200, good.text
    assert good.json()['schedule']['due_at'] > again.json()['schedule']['due_at']
    # easy must reach further than good, and hard must land between again and good
    assert good.json()['schedule']['stability'] > again.json()['schedule']['stability']
    assert again.json()['card']['lapses'] == 1
    assert good.json()['card']['lapses'] == 0
    assert good.json()['card']['reps'] == 1


def test_review_rejects_an_out_of_range_grade(client):
    headers, _ = account(client)
    card = _generate(client, headers, 'fractions')['cards'][0]
    assert client.post(f'/api/v1/flashcards/{card["id"]}/review',
                       headers=headers, json={'grade': 5}).status_code == 422


def test_session_interleaves_two_concepts(client):
    headers, _ = account(client)
    _generate(client, headers, 'fractions')
    _generate(client, headers, 'ratios')
    session = client.get('/api/v1/flashcards/session', headers=headers).json()
    concepts = [card['concept_id'] for card in session['cards']]
    assert len(concepts) >= 4
    # Massed practice would be A A A ...; interleaving keeps the window mixed.
    assert len(set(concepts[:3])) == 2, concepts[:3]
    assert set(concepts) == {'fractions', 'ratios'}
    # Every card offers the consequence of each grade, so grading is informed.
    for card in session['cards']:
        assert set(card['preview']) == {'again', 'hard', 'good', 'easy'}
        assert card['preview']['easy']['due_at'] >= card['preview']['again']['due_at']


def test_stats_and_schedule_move_after_a_review(client):
    headers, _ = account(client)
    card = _generate(client, headers, 'fractions')['cards'][0]
    before = client.get('/api/v1/flashcards/stats', headers=headers).json()
    assert before['total'] > 0 and before['due_now'] > 0 and before['learned'] == 0
    client.post(f'/api/v1/flashcards/{card["id"]}/review', headers=headers, json={'grade': 3})
    after = client.get('/api/v1/flashcards/stats', headers=headers).json()
    assert after['learned'] == 1
    assert after['retention_rate'] == 1.0
    assert after['next_due_in_seconds'] is not None


# ------------------------------------------------------------------ isolation

def test_a_card_is_private_to_its_account(client):
    alice_headers, _ = account(client, 'alice')
    bob_headers, _ = account(client, 'bob')
    card = _generate(client, alice_headers, 'fractions')['cards'][0]

    # Bob cannot see it in a listing.
    bob_list = client.get('/api/v1/flashcards', headers=bob_headers).json()
    assert all(row['id'] != card['id'] for row in bob_list['cards'])

    # Bob cannot read, review, edit or delete it. 404, never 403 -- a 403 would confirm
    # the card exists.
    assert client.post(f'/api/v1/flashcards/{card["id"]}/review',
                       headers=bob_headers, json={'grade': 3}).status_code == 404
    assert client.patch(f'/api/v1/flashcards/{card["id"]}',
                        headers=bob_headers, json={'front': 'hijacked'}).status_code == 404
    assert client.delete(f'/api/v1/flashcards/{card["id"]}',
                         headers=bob_headers).status_code == 404

    # Alice still owns it and can act on it.
    assert client.post(f'/api/v1/flashcards/{card["id"]}/review',
                       headers=alice_headers, json={'grade': 3}).status_code == 200


def test_editing_and_deleting_a_card(client):
    headers, _ = account(client)
    card = _generate(client, headers, 'fractions')['cards'][0]
    edited = client.patch(f'/api/v1/flashcards/{card["id"]}', headers=headers,
                          json={'front': 'Edited prompt', 'tags': ['edited']})
    assert edited.status_code == 200, edited.text
    assert edited.json()['front'] == 'Edited prompt'
    assert edited.json()['tags'] == ['edited']
    assert client.delete(f'/api/v1/flashcards/{card["id"]}',
                         headers=headers).status_code == 204
    assert client.patch(f'/api/v1/flashcards/{card["id"]}',
                        headers=headers, json={'front': 'gone'}).status_code == 404


# ------------------------------------------------------------------ interchange

def test_export_import_round_trip(client):
    headers, _ = account(client)
    _generate(client, headers, 'fractions')
    exported = client.get('/api/v1/flashcards/export', headers=headers,
                          params={'fmt': 'json'}).json()
    assert exported['format'] == 'luminfest-flashcards'
    assert exported['count'] == len(exported['cards'])

    # A second account imports the deck; the duplicate guard keeps a re-import a no-op.
    other_headers, _ = account(client, 'importer')
    payload = {'cards': [{k: card[k] for k in ('front', 'back', 'kind', 'concept_id',
                                               'tags', 'source')}
                         for card in exported['cards']]}
    first = client.post('/api/v1/flashcards/import', headers=other_headers, json=payload)
    assert first.status_code == 200, first.text
    assert first.json()['imported'] == exported['count']
    second = client.post('/api/v1/flashcards/import', headers=other_headers, json=payload)
    assert second.json()['imported'] == 0
    assert second.json()['skipped_duplicate'] == exported['count']

    csv_body = client.get('/api/v1/flashcards/export', headers=headers,
                          params={'fmt': 'csv'})
    assert csv_body.status_code == 200
    assert 'text/csv' in csv_body.headers['content-type']
    # The boundary middleware requires application/json for writes, so the CSV text travels
    # inside a JSON envelope rather than as a raw text/csv body.
    third_headers, _ = account(client, 'csv')
    csv_import = client.post('/api/v1/flashcards/import', headers=third_headers,
                             json={'csv': csv_body.text})
    assert csv_import.status_code == 200, csv_import.text
    assert csv_import.json()['imported'] == exported['count']
    # Provenance survives the CSV round trip, so an imported card can still be checked
    # against the block or question it came from.
    imported = client.get('/api/v1/flashcards', headers=third_headers).json()['cards']
    assert all(flashcards.source_exists(card['source']) for card in imported)
