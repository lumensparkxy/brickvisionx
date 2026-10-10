"""Aggregate measured CLI evidence across adapter versions without double-counting receipts."""
import json
import math
from pathlib import Path


def _counts(value):
    if not isinstance(value, dict):
        return {}
    return {key: amount for key, amount in value.items() if isinstance(key, str)
            and key.endswith("_tokens") and type(amount) in (int, float)
            and math.isfinite(amount) and amount >= 0}


def _event_usage(path):
    usage = {}
    if not path.is_file():
        return usage
    with path.open() as stream:
        for line in stream:
            try:
                event = json.loads(line)
            except (ValueError, TypeError):
                continue
            if not isinstance(event, dict) or event.get("type") != "turn.completed":
                continue
            for key, amount in _counts(event.get("usage")).items():
                usage[key] = usage.get(key, 0) + amount
    return usage


def summarize_calls(calls: Path):
    usage, elapsed = {}, 0.0
    invocations = usage_calls = event_calls = receipt_calls = elapsed_calls = 0
    for record in calls.glob("*/*/invocation.json"):
        invocations += 1
        try:
            receipt = json.loads(record.read_text())
            if not isinstance(receipt, dict):
                receipt = {}
        except (ValueError, TypeError):
            receipt = {}
        duration = receipt.get("elapsed_seconds")
        if type(duration) in (int, float) and math.isfinite(duration) and duration >= 0:
            elapsed += duration
            elapsed_calls += 1
        # Raw completed-turn events are the original measured data. Early adapters did not
        # copy their usage into invocation.json. Never add both copies of the same call.
        measured = _event_usage(record.with_name("events.jsonl"))
        if measured:
            event_calls += 1
        else:
            measured = _counts(receipt.get("reported_usage"))
            if measured:
                receipt_calls += 1
        if measured:
            usage_calls += 1
            for key, amount in measured.items():
                usage[key] = usage.get(key, 0) + amount
    return {"model_invocations": invocations, "model_elapsed_seconds": elapsed,
            "reported_usage": usage,
            "usage_reporting": {"status": "complete" if invocations and usage_calls == invocations else
                                "partial" if usage_calls else "unavailable",
                                "calls_with_usage": usage_calls, "calls_without_usage": invocations-usage_calls,
                                "raw_event_calls": event_calls, "receipt_fallback_calls": receipt_calls},
            "timing_reporting": {"calls_with_elapsed_time": elapsed_calls,
                                 "calls_without_elapsed_time": invocations-elapsed_calls}}
