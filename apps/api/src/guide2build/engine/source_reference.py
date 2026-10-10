"""Opt-in exact structured source references; never repair provider payloads.

Only the structured SourcePanel definition is narrowed. Opaque delta_json and
other source-bearing contracts still require their existing independent checks.
"""
from __future__ import annotations

from copy import deepcopy
import re

from .contracts import strict_schema
from ..releases.models import digest

PROFILE = "exact-source-v1"
VERSION = "structured-source-panel-singletons-v1"


def normalize_profile(value="legacy"):
    if not isinstance(value, str) or value not in {"legacy", PROFILE}:
        raise ValueError("Unknown source reference profile")
    return value


def profile(config):
    selected = normalize_profile(config.get("source_reference_profile", "legacy"))
    if selected != "legacy" and (config.get("execution_policy", "strict") != "explore"
                                  or config.get("generation_mode", "strict") != "strict"):
        raise ValueError("A source reference profile requires the exploration engine")
    return selected


def binding(model):
    return {"name": PROFILE, "version": VERSION,
            "base_proposal_schema_sha256": digest(strict_schema(model)),
            "scope": "structured_SourcePanel_only",
            "opaque_delta_json": "independently_validated_unchanged"}


def bound_proposal_schema(model, *, source_hash, page_index, page_count):
    """Use only the caller's already verified official PDF and target-page binding."""
    if not isinstance(source_hash, str) or re.fullmatch(r"[a-f0-9]{64}", source_hash) is None:
        raise ValueError("Exact source schema requires a verified SHA-256")
    if (type(page_count) is not int or page_count < 1 or type(page_index) is not int
            or not 0 <= page_index < page_count):
        raise ValueError("Exact source schema requires a bounded verified page index")
    schema = deepcopy(strict_schema(model))
    definition = schema.get("$defs", {}).get("SourcePanel", {})
    fields = definition.get("properties", {})
    if (definition.get("type") != "object" or fields.get("source_sha256", {}).get("type") != "string"
            or fields.get("page_index", {}).get("type") != "integer"):
        raise ValueError("Proposal schema no longer exposes the expected SourcePanel contract")
    fields["source_sha256"]["enum"] = [source_hash]
    fields["page_index"]["enum"] = [page_index]
    return schema


def validate_bound_response(value, schema):
    """Validate fresh and cached payloads as-is; an invalid source stays an error."""
    from jsonschema import Draft202012Validator, ValidationError
    try:
        Draft202012Validator(schema).validate(value)
    except ValidationError as error:
        pointer = "/".join(str(item) for item in error.absolute_path)
        raise ValueError("Bound proposal schema rejected response at " + pointer[:1000]) from error
