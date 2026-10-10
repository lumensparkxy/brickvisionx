"""Immutable ADK runtime choices and shared, durable request ceilings."""
from __future__ import annotations

import math

DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_THINKING_LEVEL = "medium"
DEFAULT_INFERENCE_TIMEOUT_SECONDS = 120
DEFAULT_MAX_MODEL_CALLS = 3
PROVIDER = "google_adk"
FATAL_PROVIDER_CODES = {"auth", "authentication_required", "rate_limited", "quota_exceeded",
                        "provider_unavailable", "invalid_schema", "unsupported_model", "request_rejected",
                        "subscription_limit"}  # Last code is retained for historical receipt inspection.
PAUSE_PROVIDER_CODES = FATAL_PROVIDER_CODES - {"invalid_schema", "unsupported_model"}


class ModelCallBudgetExhausted(RuntimeError):
    pass


def runtime_choice(config, checkpoint=None):
    """Bind all runtime settings, never infer a provider from an old model name."""
    provider = config.get("provider", PROVIDER)
    model = config.get("model", DEFAULT_MODEL)
    thinking = config.get("thinking_level", DEFAULT_THINKING_LEVEL)
    timeout = config.get("provider_timeout", DEFAULT_INFERENCE_TIMEOUT_SECONDS)
    if provider != PROVIDER:
        raise ValueError("Only the Google ADK runtime is available for new jobs")
    if not isinstance(model, str) or not 1 <= len(model) <= 200 or model.strip() != model:
        raise ValueError("Model must be a nonempty identifier of at most 200 characters")
    if not isinstance(thinking, str) or thinking not in {"low", "medium", "high"}:
        raise ValueError("thinking_level must be low, medium or high")
    if timeout is not None and (type(timeout) not in (int, float)
            or not math.isfinite(timeout) or not 0 < timeout <= 3600):
        raise ValueError("provider_timeout must be null or finite and between zero and 3600 seconds")
    choice = {"provider": provider, "model": model, "thinking_level": thinking, "provider_timeout": timeout}
    if checkpoint is not None:
        if checkpoint.get("runtime_choice", choice) != choice:
            raise ValueError("Frozen runtime choice changed; enqueue a new revision")
        checkpoint["runtime_choice"] = choice
    return choice


def reject_secret_config(value):
    """Credentials belong in the backend environment, never durable job configuration."""
    if isinstance(value, dict):
        for key, item in value.items():
            name = str(key).lower()
            if ("api_key" in name or "secret" in name or "password" in name
                    or name in {"credentials", "private_key", "access_token", "refresh_token", "token"}):
                raise ValueError("Credentials must not be persisted in engine configuration")
            reject_secret_config(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            reject_secret_config(item)


def bind_model_budget(config, checkpoint):
    limit = config.get("max_model_calls", DEFAULT_MAX_MODEL_CALLS)
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("max_model_calls must be an integer from 1 to 1000")
    policy = {"version": "adk-request-budget-v1", "max_model_calls": limit}
    if checkpoint.get("model_call_budget", policy) != policy:
        raise ValueError("Frozen model-call budget changed; enqueue a new revision")
    checkpoint["model_call_budget"] = policy
    used = checkpoint.get("model_calls_used", checkpoint.get("inherited_model_calls_used", 0))
    local = checkpoint.get("local_model_calls_used", max(len(checkpoint.get("model_requests", {})),
        len(checkpoint.get("exploration_calls", {}))))
    if any(type(value) is not int or value < 0 for value in (used, local)) or local > used:
        raise ValueError("Invalid durable model-call accounting")
    checkpoint.update(model_calls_used=used, local_model_calls_used=local)
    return limit


def reserve_model_call(config, checkpoint, save, *, key, store=None, job_id=None):
    """Charge before sending, retaining uncertain interrupted reservations across restart."""
    limit = bind_model_budget(config, checkpoint)
    root = checkpoint.get("budget_root_job_id", config.get("budget_root_job_id", job_id))
    if store is not None and hasattr(store, "lineage_model_calls_used"):
        checkpoint["model_calls_used"] = max(checkpoint["model_calls_used"], store.lineage_model_calls_used(root))
    requests = checkpoint.setdefault("model_requests", {})
    if key in requests:
        raise ValueError("A reserved model request cannot be repeated")
    if checkpoint["model_calls_used"] >= limit:
        raise ModelCallBudgetExhausted("The frozen overall model-call budget is exhausted")
    checkpoint["model_calls_used"] += 1
    checkpoint["local_model_calls_used"] += 1
    requests[key] = {"status": "reserved", "call_number": checkpoint["model_calls_used"]}
    save("model_call_reserved")
    return requests[key]
