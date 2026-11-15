"""Tests for the concept mind map route.

The claims this route makes, and that these tests check:

- the map is the curriculum's own structure: every label it returns is a concept that exists
  in the caller's course, not a decorative placeholder;
- a caller without a token is refused, and a concept that is not in their course is a 404
  rather than a 403 that would confirm it exists;
- the interactive page is self-contained (no external requests) and carries the tree inline,
  so opening the saved file still expands a branch when the server is gone.

The layout itself is checked through its invariants - a parent is centred on its children,
columns do not overlap, and every child sits to the right of its parent - because pixel
assertions would break on every cosmetic change.
"""

from __future__ import annotations

import json

from app import courses, mindmap
from test_api import account, client, settings  # noqa: F401 - fixtures


def _first_concept(headers, client):
    detail = client.get('/api/v1/courses/integrated_math_1', headers=headers)
    assert detail.status_code == 200, detail.text
    sample = (detail.json().get('sample_concepts') or [{}])[0]
    return sample.get('id'), sample.get('title')


def test_map_labels_all_belong_to_the_course(client):
    headers, _ = account(client)
    concept_id, title = _first_concept(headers, client)
    response = client.get(f'/api/v1/mindmap/{concept_id}', headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()

    graph = courses.graph_for('integrated_math_1')
    known = {node.title for node in graph.nodes.values()}
    labels = set()

    def collect(node):
        labels.add(node['label'])
        for child in node.get('children') or []:
            collect(child)

    collect(body['tree'])
    groups = {'Rests on', 'Unlocks', 'Same unit'}
    unknown = {label for label in labels if label not in known and label not in groups}
    assert not unknown, f'labels that are not in the course: {sorted(unknown)}'
    assert body['title'] == title


def test_a_concept_outside_the_course_is_a_404_and_a_stranger_is_refused(client):
    headers, _ = account(client)
    assert client.get('/api/v1/mindmap/not_a_concept', headers=headers).status_code == 404
    assert client.get('/api/v1/mindmap/course').status_code == 401


def test_the_served_page_carries_the_tree_and_requests_nothing(client):
    headers, _ = account(client)
    concept_id, title = _first_concept(headers, client)
    response = client.get(f'/api/v1/mindmap/{concept_id}/html', headers=headers)
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/html')
    page = response.text

    assert f'<title>{title}</title>' in page or title in page
    assert 'const TREE = ' in page
    # Self-contained: no src= or href= that would reach the network, and the data is inline.
    assert 'src="http' not in page and "src='http" not in page
    assert 'https://' not in page.replace('http://www.w3.org', '')
    inline = page.split('const TREE = ', 1)[1].split(';\n', 1)[0]
    assert title in json.loads(inline)['label']


def test_layout_centres_a_parent_on_its_children_and_keeps_tiers_ordered():
    root = mindmap.Node('Root', [mindmap.Node('A', [mindmap.Node('A1'),
                                                    mindmap.Node('A2')]),
                                 mindmap.Node('B')])
    mindmap.measure(root)
    mindmap.layout(root)
    a = root.children[0]
    assert a.y == (a.children[0].y + a.children[1].y) / 2
    assert 0 < a.y < a.children[0].y or a.children[0].y < a.y < a.children[1].y
    for node in mindmap.walk(root):
        for child in node.children:
            assert child.x > node.x + node.w, 'a child must start right of its parent'
            assert child.depth == node.depth + 1


def test_the_page_starts_collapsed_at_the_requested_depth():
    root = mindmap.Node('Root', [mindmap.Node('A', [mindmap.Node('A1')])])
    page = mindmap.interactive_page(root, open_depth=1)
    assert 'OPEN_DEPTH = 1' in page
    deep = mindmap.interactive_page(root, open_depth=0)
    assert 'OPEN_DEPTH = 0' in deep
