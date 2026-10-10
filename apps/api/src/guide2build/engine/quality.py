"""Explicit image-fit tolerances; neither profile grants assembly/release approval."""
from __future__ import annotations


def source_view_policy(profile="strict"):
    if profile not in ("strict", "alpha"):
        raise ValueError("quality_profile must be strict or alpha")
    return {"version": "source-view-tolerance-v1", "profile": profile,
            "max_rms_pixels": 8.0 if profile == "alpha" else 4.0,
            "max_point_pixels": 12.0, "ambiguity_pixels": 0.75}


def bind_source_view_policy(config, checkpoint):
    """Freeze tolerances before any trial. Existing work keeps the strict policy."""
    policy = source_view_policy(config.get("quality_profile", "strict"))
    prior = checkpoint.get("source_view_policy")
    if prior is None and (checkpoint.get("panel_attempts") or checkpoint.get("candidate")):
        prior = source_view_policy()
    if prior is not None and prior != policy:
        raise ValueError("Saved image tolerance cannot change on resume; enqueue a new experiment revision")
    checkpoint["source_view_policy"] = policy
    return policy


def fit_acceptance(fit):
    """Preserve the strict result even when an alpha fit can proceed to visual review."""
    strict = source_view_policy()
    rms, point = fit.get("rms_pixels"), fit.get("max_error_pixels")
    exceeds_strict = ((rms is not None and rms > strict["max_rms_pixels"])
                      or (point is not None and point > strict["max_point_pixels"]))
    return {"strict_status": "poor_fit" if exceeds_strict else fit["status"],
            "accepted_with_relaxed_tolerance": fit["status"] == "fitted" and exceeds_strict}


def quality_summary(config, checkpoint):
    policy = source_view_policy(config.get("quality_profile", "strict"))
    relaxed = []
    for review in checkpoint.get("panel_reviews", []):
        for step_id, check in review.get("source_view_checks", {}).items():
            if check.get("accepted_with_relaxed_tolerance"):
                relaxed.append({"step_id": step_id, **check})
    return {**policy, "strict_max_rms_pixels": 4.0, "relaxed_steps": relaxed}
