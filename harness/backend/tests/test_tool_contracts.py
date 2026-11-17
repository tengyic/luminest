"""The published tool catalogue must be a contract the dispatcher can enforce."""

from app.harness import toolbox


def _schema(name):
    return toolbox.REGISTRY[name][0].argument_schema


def test_every_tool_publishes_a_checkable_contract():
    assert toolbox.REGISTRY
    for spec, _ in toolbox.REGISTRY.values():
        schema = spec.argument_schema
        assert schema['type'] == 'object'
        assert schema['additionalProperties'] is False
        assert isinstance(schema['required'], list)
        assert spec.return_schema['type'] == 'object'
        assert spec.timeout_seconds > 0
        for name, child in schema['properties'].items():
            assert name and ('type' in child or 'anyOf' in child)


def test_compact_annotations_keep_their_shape():
    requirements = _schema('write_simulation')['properties']['requirements']
    assert requirements['type'] == 'array'
    assert requirements['items'] == {'type': 'string'}
    assert requirements['default'] == []

    sections = _schema('generate_slides')['properties']['sections']
    assert sections['type'] == 'array'
    assert set(sections['items']['properties']) == {'heading', 'bullets', 'notes'}
    assert sections['default'] == []

    signals = _schema('check_on_task')['properties']['signals']
    assert signals['type'] == 'object'
    assert set(signals['properties']) == {
        'idle_seconds', 'hidden_seconds', 'active_seconds',
        'blur_events', 'attempts', 'window_seconds'}

    blueprint = _schema('author_course')['properties']['blueprint_json']
    assert {branch['type'] for branch in blueprint['anyOf']} == {'object', 'string'}


def test_dispatcher_rejects_arguments_that_break_the_contract():
    unknown = toolbox.invoke(toolbox.ToolContext(), 'search_concepts',
                             {'query': 'fractions', 'limit': 8, 'surprise': True})
    assert not unknown.ok
    assert 'Bad arguments' in unknown.refused
    assert 'surprise' in unknown.refused

    wrong_type = toolbox.invoke(toolbox.ToolContext(), 'search_concepts',
                                {'query': 'fractions', 'limit': 'eight'})
    assert not wrong_type.ok
    assert 'Bad argument type' in wrong_type.refused
    assert 'limit' in wrong_type.refused


def test_a_tool_description_never_names_a_tool_that_does_not_exist():
    """A description that says "call X" must name a registered tool.

    This caught a real one: `emit_interactive` told the model to call
    `interactive_registry`, which was an HTTP route and never a tool, so a model that
    followed the instruction produced a call the dispatcher could not resolve.

    Scope is deliberately narrow: only the imperative "call X" / "use X" form is
    checked, and only snake_case tokens, because every tool in the catalogue is
    snake_case. Narrative words such as ``idle_seconds`` or ``link_only`` are argument
    and result vocabulary, not instructions. The snake_case invariant is asserted first
    so that adding a single-word tool breaks this test loudly instead of silently
    shrinking what it checks.
    """
    import re

    assert all('_' in name for name in toolbox.REGISTRY), \
        'this guard only sees snake_case tool names'

    offenders = []
    for name, (spec, _fn) in toolbox.REGISTRY.items():
        text = ' '.join(part for part in (spec.summary, spec.arguments, spec.returns) if part)
        for match in re.finditer(r'\b(?:call|use)\s+([a-z][a-z0-9]*_[a-z0-9_]+)', text):
            if match.group(1) not in toolbox.REGISTRY:
                offenders.append((name, match.group(1)))
    assert not offenders, offenders
