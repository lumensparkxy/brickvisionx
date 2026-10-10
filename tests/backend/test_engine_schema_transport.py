"""Offline transport conversion proof; the engine schema remains authoritative."""
from copy import deepcopy
import json

from google.genai import models, types
from jsonschema.validators import validator_for
import pytest

from guide2build.engine.contracts import strict_schema
from guide2build.engine.exploration import CandidateComparison, exploration_proposal_type
from guide2build.engine.localized_review import CandidateComparison as LocalizedComparison
from guide2build.engine.panel_index import PageIndexV2
from guide2build.engine.schema_transport import SchemaTransportError, project_schema


@pytest.mark.parametrize("model", [PageIndexV2, exploration_proposal_type(), CandidateComparison, LocalizedComparison])
def test_real_engine_schemas_project_and_serialize_without_altering_original(model):
    schema = strict_schema(model)
    before = deepcopy(schema)
    projected = project_schema(schema)
    assert schema == before
    validator_for(projected).check_schema(projected)
    assert projected["required"] == schema["required"]
    assert projected["additionalProperties"] is False
    assert projected["properties"].keys() == schema["properties"].keys()
    # response_json_schema uses the SDK's raw JSON schema serializer; OpenAPI
    # types.Schema is not the wire format used by this provider.
    converted = models._GenerateContentConfig_to_mldev(None,
        types.GenerateContentConfig(response_json_schema=projected, response_mime_type="application/json"))
    assert converted["responseJsonSchema"] == projected
    assert converted["responseMimeType"] == "application/json"
    from guide2build.engine.schema_transport import SUPPORTED_KEYWORDS

    def inspect(node):
        assert node.keys() <= SUPPORTED_KEYWORDS
        for child in node.get("properties", {}).values():
            inspect(child)
        for key in ("items", "additionalProperties"):
            if isinstance(node.get(key), dict):
                inspect(node[key])
        for key in ("anyOf", "prefixItems"):
            for child in node.get(key, []):
                inspect(child)

    inspect(projected)


def test_real_page_schema_retains_identity_enum_bbox_bounds_and_nullable_objects():
    projected = project_schema(strict_schema(PageIndexV2))
    properties = projected["properties"]
    assert properties["schema_version"]["enum"] == ["2.0"]
    assert properties["page_index"]["minimum"] == 0
    assert properties["page_index"]["maximum"] == 1999
    panel = properties["panels"]["items"]
    assert panel["required"] == list(panel["properties"])
    assert panel["properties"]["bbox"]["minItems"] == panel["properties"]["bbox"]["maxItems"] == 4
    assert panel["properties"]["bbox"]["items"] == {"minimum": 0, "maximum": 1, "type": "number"}
    assert panel["properties"]["number"]["type"] == ["integer", "null"]
    associated = panel["properties"]["associated_event"]
    assert associated["type"] == ["object", "null"]
    assert associated["required"] == ["page_index", "event_key"]
    assert associated["properties"]["page_index"]["maximum"] == 1999
    assert associated["additionalProperties"] is False
    assert "maxItems" not in properties["panels"]
    assert "maxItems" not in properties["uncertainty"]
    assert "maxItems" not in panel["properties"]["uncertainty"]


@pytest.mark.parametrize("minimum,maximum", [(None, 128), (1, 64), (0, 64), (3, 3), (4, 4), (0, 0)])
def test_transport_array_caps_are_retained_only_for_exact_arity(minimum, maximum):
    schema = {"type": "array", "items": {"type": "number"}, "maxItems": maximum}
    if minimum is not None:
        schema["minItems"] = minimum
    projected = project_schema(schema)
    assert ("maxItems" in projected) == (minimum == maximum)
    assert projected.get("minItems") == minimum
    assert schema["maxItems"] == maximum


def test_exploration_fixed_vectors_retain_arity_while_variable_caps_are_local_only():
    from guide2build.core.models import Pose

    projected = project_schema(strict_schema(exploration_proposal_type()))
    properties = projected["properties"]
    assert "maxItems" not in properties["sequence"]
    assert "maxItems" not in properties["placement_hints"]
    bbox = properties["sequence"]["items"]["properties"]["bbox"]
    assert bbox["minItems"] == bbox["maxItems"] == 4
    pose = project_schema(strict_schema(Pose))["properties"]
    position = pose["position_ldu"]
    quaternion = pose["quaternion_xyzw"]
    assert position["minItems"] == position["maxItems"] == 3
    assert quaternion["minItems"] == quaternion["maxItems"] == 4


def test_keyword_named_properties_and_pointer_escapes_are_preserved():
    names = ["default", "pattern", "const", "title", "properties", "$defs"]
    schema = {"type": "object", "properties": {name: {"$ref": "#/$defs/a~1b~0c"} for name in names},
        "required": names, "additionalProperties": False,
        "$defs": {"a/b~c": {"type": "string", "pattern": "^[a-z]+$", "minLength": 1}}}
    projected = project_schema(schema)
    assert projected["required"] == names
    assert projected["properties"] == {name: {"type": "string"} for name in names}


def test_root_definition_reference_is_inlined_without_treating_defs_as_scoped_siblings():
    schema = {"$defs": {"root": {"type": "object", "properties": {"name": {"type": "string"}},
        "required": ["name"], "additionalProperties": False}}, "$ref": "#/$defs/root",
        "title": "Root envelope"}
    assert project_schema(schema) == {**schema["$defs"]["root"], "title": "Root envelope"}


@pytest.mark.parametrize("kind,bound,minimum,maximum", [
    ("integer", 2, 3, 1), ("integer", 2.5, 3, 2), ("integer", -2.5, -2, -3),
    ("number", 2.5, 2.5, 2.5)])
def test_exclusive_bounds_have_correct_integer_equivalence_or_numeric_superset(kind, bound, minimum, maximum):
    assert project_schema({"type": kind, "exclusiveMinimum": bound}) == {"type": kind, "minimum": minimum}
    assert project_schema({"type": kind, "exclusiveMaximum": bound}) == {"type": kind, "maximum": maximum}
    assert project_schema({"type": kind, "exclusiveMinimum": bound, "minimum": 9})["minimum"] == 9
    assert project_schema({"type": kind, "exclusiveMaximum": bound, "maximum": -9})["maximum"] == -9


def test_nullable_enum_and_distinct_unions_remain_anyof():
    schema = {"anyOf": [{"type": "string", "enum": ["known"]}, {"type": "null"}]}
    assert project_schema(schema) == schema
    schema = {"anyOf": [{"type": "string"}, {"type": "integer"}]}
    assert project_schema(schema) == schema
    assert project_schema({"anyOf": [{"type": "null"}, {"type": "string", "minLength": 1}]}) == {
        "type": ["string", "null"]}


@pytest.mark.parametrize("schema", [
    {"$ref": "https://untrusted.invalid/schema"}, {"$ref": "#/properties/name"},
    {"$ref": "#/$defs/missing"}, {"$ref": "#/$defs/bad~2name"},
    {"$defs": {"loop": {"$ref": "#/$defs/loop"}}, "$ref": "#/$defs/loop"},
    {"$defs": {"a": {"$ref": "#/$defs/b"}, "b": {"$ref": "#/$defs/a"}}, "$ref": "#/$defs/a"},
    {"$defs": {"a": {"type": "string"}}, "$ref": "#/$defs/a", "type": "integer"},
    {"allOf": [{"type": "object"}]},
    {"$id": "https://untrusted.invalid/scope", "type": "object"},
    {"const": "a", "enum": ["b"]}])
def test_unsafe_or_unrepresentable_schema_fails_with_bounded_safe_diagnostic(schema):
    with pytest.raises(SchemaTransportError) as error:
        project_schema(schema)
    assert "https://" not in str(error.value)


def test_cyclic_python_input_is_rejected():
    schema = {"type": "object"}
    schema["properties"] = {"self": schema}
    with pytest.raises(SchemaTransportError, match="cyclic"):
        project_schema(schema)


def test_expansion_depth_node_and_byte_limits_reject_instead_of_omitting_fields(monkeypatch):
    from guide2build.engine import schema_transport

    definitions = {"leaf": {"type": "string"}}
    reference = "leaf"
    for index in range(8):
        name = f"layer{index}"
        definitions[name] = {"type": "object", "properties": {
            "left": {"$ref": f"#/$defs/{reference}"}, "right": {"$ref": f"#/$defs/{reference}"}}}
        reference = name
    schema = {"$defs": definitions, "$ref": f"#/$defs/{reference}"}
    monkeypatch.setattr(schema_transport, "MAX_NODES", 500)
    with pytest.raises(SchemaTransportError, match="node"):
        project_schema(schema)
    monkeypatch.setattr(schema_transport, "MAX_NODES", 20_000)
    monkeypatch.setattr(schema_transport, "MAX_DEPTH", 8)
    with pytest.raises(SchemaTransportError, match="depth"):
        project_schema(schema)
    monkeypatch.setattr(schema_transport, "MAX_DEPTH", 64)
    monkeypatch.setattr(schema_transport, "MAX_TRANSPORT_BYTES", 300)
    with pytest.raises(SchemaTransportError, match="byte"):
        project_schema(schema)


def test_byte_limits_include_repeated_literal_annotations(monkeypatch):
    from guide2build.engine import schema_transport

    monkeypatch.setattr(schema_transport, "MAX_TRANSPORT_BYTES", 2000)
    schema = {"$defs": {"annotated": {"type": "string", "description": "x" * 900}},
        "type": "object", "properties": {str(index): {"$ref": "#/$defs/annotated"} for index in range(3)}}
    with pytest.raises(SchemaTransportError, match="byte"):
        project_schema(schema)
    assert len(json.dumps(schema)) < schema_transport.MAX_SCHEMA_BYTES


@pytest.mark.parametrize("annotation", ["\x00" * 180_000, '"' * 500_000])
def test_original_byte_limit_counts_json_escaping_even_for_discarded_constraints(annotation):
    from guide2build.engine.schema_transport import MAX_SCHEMA_BYTES

    schema = {"type": "object", "properties": {"name": {"type": "string"}},
        "required": ["name"], "default": annotation}
    assert len(json.dumps(schema, ensure_ascii=False).encode()) > MAX_SCHEMA_BYTES
    with pytest.raises(SchemaTransportError, match="Original schema exceeded its byte limit"):
        project_schema(schema)
