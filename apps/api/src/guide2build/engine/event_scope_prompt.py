"""Opt-in wording for one indexed event, without changing routing or validation.

The profile binds every replacement and appended instruction in the durable
policy. Historical baseline and attachment prompts retain their original bytes.
"""
import hashlib
import json
from typing import Final


PROFILE: Final = "event-scoped"
VERSION: Final = "event-scope-v1"

CONSTRUCTION_INSTRUCTION: Final = (
    "Construct only the requested panel and its explicitly listed required_callouts. "
)

SOURCE_REGION_RULE: Final = """The allowed construction scope is exactly panel plus required_callouts.
The required_callouts list is exhaustive, including when empty. The full_page_index,
other source_regions and other visible events are context, not permission to construct
a parent, sibling or later event. Source-supported assembly for this request means an
assembly change established within this allowed scope. An ambiguous thumbnail, ghost
view or other region may establish no construction action: return delta_json=null and
identify that requested region by source hash, page and bbox in observations/blockers.
Retain the uncertainty; do not invent a snapshot or construct a neighboring event.
Associated inventory/detail crops on the exact target page may support an allowed event
without introducing another operation or additional physical copies.
"""

PROMPT_SUFFIX: Final = """Source sequence contract:
Return exactly one sequence record per new_steps snapshot, with the same step_id in the
same order and no duplicate record or extra parent/header record. Use printed_main only
for one ordinary add_parts snapshot without a substep_label. Use numbered_callout only
for an actual printed local operation: printed_label must equal substep_label, action
must be build_subassembly and assembly_group_id must identify its detached group,
including when adding later pieces to that group. An attachment reuses existing physical
IDs and the same group after its callout evidence; it does not introduce those pieces again.
Quantities require the correct number of physical instances within the source operation,
not extra snapshots or arbitrary per-copy insertion stages. Do not invent printed labels,
operations or group membership to satisfy the schema. Preserve unresolved source scope
and grouping in observations/blockers; when no construction action is established in the
requested scope, delta_json=null is permitted.
"""


def binding():
    """Bind all profile wording, not just its appended sequence guidance."""
    wording = {"construction_instruction": CONSTRUCTION_INSTRUCTION,
               "source_region_rule": SOURCE_REGION_RULE, "prompt_suffix": PROMPT_SUFFIX}
    encoded = json.dumps(wording, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return {"name": PROFILE, "version": VERSION, "prompt_sha256": hashlib.sha256(encoded).hexdigest()}
