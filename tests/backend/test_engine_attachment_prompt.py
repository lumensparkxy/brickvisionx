"""Synthetic prompt-boundary tests; no inference or reconstruction accuracy claim."""
import hashlib
import json
import re

import pytest

from guide2build.engine import attachment_prompt


@pytest.mark.parametrize("base", ["", "Unchanged baseline\n", "Source text: café — 零\n  ",
                                  '{"context":"literal \\\\n text","parts":[]}'])
def test_baseline_is_byte_exact_and_requires_explicit_opt_in(base):
    original_digest = hashlib.sha256(base.encode()).hexdigest()
    assert attachment_prompt.prompt_suffix() == ""
    assert attachment_prompt.apply_profile(base) is base
    assert attachment_prompt.apply_profile(base, "baseline") is base
    assert hashlib.sha256(attachment_prompt.apply_profile(base).encode()).hexdigest() == original_digest


@pytest.mark.parametrize("profile", [None, "", "attachment", "attachment-reasoning-v2", "baseline "])
def test_unknown_profile_fails_instead_of_silently_changing_an_experiment(profile):
    with pytest.raises(ValueError, match="Unknown proposal profile"):
        attachment_prompt.apply_profile("Frozen baseline", profile)


def test_variant_preserves_synthetic_payload_and_does_not_change_schema_or_bounds():
    from guide2build.engine.contracts import strict_schema
    from guide2build.engine.exploration import exploration_proposal_type
    from guide2build.engine.hypotheses import PlacementHint
    from guide2build.releases.models import canonical

    # The actual model-facing contract, including its bounds, remains identical.
    schema = strict_schema(exploration_proposal_type())
    schema_bytes = canonical(schema)
    hint = PlacementHint(step_id="fixture-attachment", moving_instance_id="fixture-anchor",
        target_instance_ids=["fixture-receiver-a", "fixture-receiver-b"],
        moving_group_ids=["fixture-anchor", "fixture-member", "fixture-occluded"],
        source={"page_index": 0, "bbox": [0, 0, 1, 1], "source_sha256": "a" * 64})
    context = {"source_sha256": "a" * 64, "synthetic_only": True,
               "placement_hints": [hint.model_dump(mode="json")],
               "schema": schema, "limits": {"max_candidates": 64, "beam_width": 8, "return_count": 3}}
    payload = json.dumps(context, sort_keys=True, separators=(",", ":"))
    base = "Existing frozen instructions\n" + payload
    expanded = attachment_prompt.apply_profile(base, attachment_prompt.VARIANT)
    assert expanded[:len(base)] == base
    assert len(expanded) > len(base)
    decoded, end = json.JSONDecoder().raw_decode(expanded[expanded.index("{"):])
    assert decoded == context
    assert expanded[expanded.index("{")+end:] == "\n\n" + attachment_prompt.PROMPT_SUFFIX
    assert canonical(strict_schema(exploration_proposal_type())) == schema_bytes
    restored = PlacementHint.model_validate(decoded["placement_hints"][0])
    assert restored.moving_group_ids == hint.moving_group_ids
    assert restored.moving_connector_ids == restored.target_connector_ids == []
    assert restored.quarter_turns == [0, 1, 2, 3]
    assert restored.target_instance_ids == ["fixture-receiver-a", "fixture-receiver-b"]


def test_prompt_is_generic_and_contains_no_literal_answer_or_source_identifier():
    suffix = attachment_prompt.PROMPT_SUFFIX
    # The prose needs field names, not any numeric coordinates, part/set IDs,
    # source hashes, filenames, URLs, specific printed steps or named assemblies.
    assert not re.search(r"\d|https?://|(?:parts|var|evidence)/|\.(?:dat|ldr|mpd|json)\b", suffix)
    assert not re.search(r"\b(?:model-\w+|alt-\w+|wing|nose|tail|canopy)\b", suffix, re.IGNORECASE)
    assert not re.search(r"\b[a-f0-9]{64}\b|\[[^\]]*\]", suffix)
    assert len(suffix.split()) <= 350


def test_variant_binding_is_stable_without_mutable_registration():
    first = attachment_prompt.prompt_suffix(attachment_prompt.VARIANT)
    baseline = attachment_prompt.prompt_suffix("baseline")
    second = attachment_prompt.prompt_suffix(attachment_prompt.VARIANT)
    assert first == second and baseline == ""
    assert attachment_prompt.PROFILES[:2] == ("baseline", attachment_prompt.VARIANT)
    assert attachment_prompt.VERSION == attachment_prompt.VARIANT + "-v1"
    assert hashlib.sha256(first.encode()).digest() != hashlib.sha256(baseline.encode()).digest()
