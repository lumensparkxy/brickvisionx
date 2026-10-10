"""Fixed Gemini JSON-schema transport projection, never the validation authority.

The original engine schema is retained and validates every returned value. This
projection applies once before requesting inference, with no retry or fallback.
Supported keywords follow https://ai.google.dev/gemini-api/docs/structured-output.
Unsupported validation constraints remain in the original local schema.
"""
from __future__ import annotations

import json
import math
import re

CONVERSION_VERSION = "gemini-json-subset-v2"
MAX_SCHEMA_BYTES = 1_000_000
MAX_TRANSPORT_BYTES = 2_000_000
MAX_NODES = 20_000
MAX_DEPTH = 64
SUPPORTED_KEYWORDS = frozenset({"type", "title", "description", "properties", "required",
    "additionalProperties", "enum", "format", "minimum", "maximum", "items", "prefixItems",
    "minItems", "maxItems", "anyOf"})
_REF = re.compile(r"#\/\$defs\/((?:[^~/]|~[01])+)\Z")
_COMPOSITIONS = {"allOf", "oneOf", "not", "if", "then", "else", "$dynamicRef", "$recursiveRef"}


class SchemaTransportError(ValueError):
    """Fixed safe diagnostic; no schema values or reference URLs are exposed."""


class _Budget:
    def __init__(self, max_bytes):
        self.nodes = 0
        self.bytes = 0
        self.max_bytes = max_bytes

    def charge(self, value, depth):
        self.nodes += 1
        if depth > MAX_DEPTH or self.nodes > MAX_NODES:
            raise SchemaTransportError("Schema conversion exceeded its depth or node limit")
        if isinstance(value, str):
            self.bytes += len(value.encode()) + 2
        elif isinstance(value, (dict, list)):
            self.bytes += 2 + len(value) * 2
        elif value is None or type(value) is bool:
            self.bytes += 5
        elif type(value) in (int, float):
            if type(value) is float and not math.isfinite(value):
                raise SchemaTransportError("Schema must contain finite JSON values")
            if type(value) is int and value.bit_length() > 4096:
                raise SchemaTransportError("Schema numeric value exceeded its size limit")
            self.bytes += len(str(value))
        else:
            raise SchemaTransportError("Schema must contain JSON values")
        if self.bytes > self.max_bytes:
            raise SchemaTransportError("Schema conversion exceeded its byte limit")


def _copy_json(value, budget, depth=0, ancestors=frozenset()):
    budget.charge(value, depth)
    if isinstance(value, (dict, list)):
        if id(value) in ancestors:
            raise SchemaTransportError("Schema contains a cyclic JSON value")
        ancestors = ancestors | {id(value)}
    if isinstance(value, dict):
        output = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise SchemaTransportError("Schema object keys must be strings")
            budget.charge(key, depth + 1)
            output[key] = _copy_json(child, budget, depth + 1, ancestors)
        return output
    if isinstance(value, list):
        return [_copy_json(child, budget, depth + 1, ancestors) for child in value]
    return value


def project_schema(schema):
    """Return a fresh bounded transport schema without mutating the original.

    Only local references into the root $defs are expanded. Recursive schemas
    and unsupported composition constructs fail before any model request.
    """
    original = _copy_json(schema, _Budget(MAX_SCHEMA_BYTES))
    # JSON escaping can expand control characters and quotes. Check the actual
    # serialized original as well, including annotations discarded below.
    if len(json.dumps(original, ensure_ascii=False, allow_nan=False).encode()) > MAX_SCHEMA_BYTES:
        raise SchemaTransportError("Original schema exceeded its byte limit")
    if not isinstance(original, dict):
        raise SchemaTransportError("The engine schema must be an object")
    definitions = original.get("$defs", {})
    if not isinstance(definitions, dict):
        raise SchemaTransportError("Schema definitions must be an object")
    budget = _Budget(MAX_TRANSPORT_BYTES)

    def visit(node, depth=0, references=frozenset()):
        budget.charge(node, depth)
        if not isinstance(node, dict):
            raise SchemaTransportError("Transport subschemas must be objects")
        if "$id" in node or "$anchor" in node or (depth and "$defs" in node):
            raise SchemaTransportError("Scoped schema definitions are unsupported by this conversion")
        if _COMPOSITIONS & node.keys():
            raise SchemaTransportError("Schema composition is unsupported by this conversion")
        if "$ref" in node:
            reference = node["$ref"]
            match = _REF.fullmatch(reference) if isinstance(reference, str) else None
            if not match:
                raise SchemaTransportError("Only local root definitions may be referenced")
            name = match[1].replace("~1", "/").replace("~0", "~")
            if name in references:
                raise SchemaTransportError("Recursive schema references are unsupported")
            if name not in definitions:
                raise SchemaTransportError("Schema reference does not resolve")
            resolved = visit(definitions[name], depth + 1, references | {name})
            siblings = visit({key: value for key, value in node.items() if key not in {"$ref", "$defs"}},
                             depth + 1, references)
            # JSON Schema ref siblings are an intersection. Conflicting validation
            # keywords cannot safely be represented by overwriting either side.
            for key, value in siblings.items():
                if key in resolved and resolved[key] != value and key not in {"title", "description"}:
                    raise SchemaTransportError("Conflicting schema reference siblings are unsupported")
                resolved[key] = value
            return resolved
        output = {}
        for key, value in node.items():
            if key not in SUPPORTED_KEYWORDS:
                continue
            budget.charge(key, depth + 1)
            if key == "properties":
                output[key] = {}
                for name, child in value.items():
                    budget.charge(name, depth + 1)
                    output[key][name] = visit(child, depth + 1, references)
            elif key in {"items", "additionalProperties"} and isinstance(value, dict):
                output[key] = visit(value, depth + 1, references)
            elif key in {"anyOf", "prefixItems"}:
                output[key] = [visit(child, depth + 1, references) for child in value]
            else:
                output[key] = _copy_json(value, budget, depth + 1)
        # Variable array caps multiply nested grammar complexity. Retain exact
        # tuple arity on the wire; all other caps remain strict in the original
        # engine schema used for local postvalidation.
        if "maxItems" in output and output.get("minItems") != output["maxItems"]:
            del output["maxItems"]
        if "const" in node:
            constant = _copy_json(node["const"], budget, depth + 1)
            if "enum" in output and constant not in output["enum"]:
                raise SchemaTransportError("Schema constant conflicts with its enum")
            output["enum"] = [constant]
        schema_type = node.get("type")
        integer_only = schema_type == "integer" or (isinstance(schema_type, list)
            and "integer" in schema_type and set(schema_type) <= {"integer", "null"})
        for exclusive, inclusive, rounding, combine in (
                ("exclusiveMinimum", "minimum", lambda x: math.floor(x) + 1, max),
                ("exclusiveMaximum", "maximum", lambda x: math.ceil(x) - 1, min)):
            if exclusive in node:
                value = rounding(node[exclusive]) if integer_only else node[exclusive]
                output[inclusive] = combine(output[inclusive], value) if inclusive in output else value
        # This collapse is equivalent only when one branch is exactly null and
        # the other has no enum: a lifted enum would wrongly exclude null.
        alternatives = output.get("anyOf", [])
        if len(alternatives) == 2 and "type" not in output:
            nullable = [item for item in alternatives if item == {"type": "null"}]
            concrete = [item for item in alternatives if item != {"type": "null"}]
            if nullable and len(concrete) == 1 and isinstance(concrete[0].get("type"), str):
                branch = concrete[0]
                if "enum" not in branch and "anyOf" not in branch and all(
                        key not in output or output[key] == value or key in {"title", "description"}
                        for key, value in branch.items()):
                    del output["anyOf"]
                    output = {**branch, **output, "type": [branch["type"], "null"]}
        return output

    projected = visit(original)
    if len(json.dumps(projected, ensure_ascii=False, allow_nan=False).encode()) > MAX_TRANSPORT_BYTES:
        raise SchemaTransportError("Transport schema exceeded its byte limit")
    return projected
