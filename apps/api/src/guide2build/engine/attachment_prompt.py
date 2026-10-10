"""Opt-in proposal wording only; no source data, runtime or solver changes.

The caller binds VARIANT, VERSION and the suffix hash in a new experiment's
policy. Baseline requests must keep their existing prompt bytes and bindings.
"""
from typing import Final

from . import event_scope_prompt


VARIANT: Final = "attachment-reasoning"
VERSION: Final = "attachment-reasoning-v1"
PROFILES: Final = ("baseline", VARIANT, event_scope_prompt.PROFILE)

PROMPT_SUFFIX: Final = """Attachment evidence check:
Use only the supplied official images and individual-part catalogue. For a group
attachment, recover the complete moving group from its preceding callouts and
current own assembly history; retain its detached assembly_group_id. In connections
and placement_hints, moving_group_ids means every member's physical instance ID,
including the anchor and occluded members, not a group label or just the newest
piece. Keep receivers outside that group. Reuse these IDs without new introductions
on attachment; repeated physical copies must follow the source quantities.
Apply one rigid transform to the complete group, preserving internal poses and
original part origins. Include each moved member's pose and scene presence. Keep
unrelated pieces and prior snapshots unchanged; do not invent corrective microsteps.

Identify the receiving face and side from arrow endpoints, exposed studs or socket
openings, occlusion, edge shapes and asymmetric landmarks. Separate camera turns
and exploded presentation offsets from final attachment placement. Consider top,
underside and opposite-side alternatives only where the official evidence supports
them or leaves them unresolved; do not lock a guessed side because it is nearest
the raw pose. Express a small source-supported set through existing placement_hints,
including target-specific hints when needed. Use supplied connector IDs only.
An empty connector-ID list permits supported catalogue alternatives; do not replace
uncertainty with an invented or arbitrary single connector. Retain supported
quarter_turns alternatives unless visible evidence rules them out. Stay within all
existing schema and search bounds; unsupported contact remains an uncertainty.

Use short observable-evidence and constraint statements in the existing observations
and blockers, tied to the affected group and exact source panel. Preserve ambiguous
identities, colours, faces and seating in those fields. A renderable estimate or close
camera fit does not establish hidden engagement or physical verification.
"""


def prompt_suffix(profile: str = "baseline") -> str:
    """Return no experiment text unless the named variant is selected explicitly."""
    if profile == "baseline":
        return ""
    if profile == VARIANT:
        return PROMPT_SUFFIX
    if profile == event_scope_prompt.PROFILE:
        return event_scope_prompt.PROMPT_SUFFIX
    raise ValueError("Unknown proposal profile")


def apply_profile(base_prompt: str, profile: str = "baseline") -> str:
    """Append only proposal guidance; never rewrite the supplied baseline context."""
    suffix = prompt_suffix(profile)
    return base_prompt + "\n\n" + suffix if suffix else base_prompt
