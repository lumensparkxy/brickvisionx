"""Aggregate measured provider evidence without double-counting copied receipts."""
import json
import math
from pathlib import Path


def _counts(value):
    if not isinstance(value, dict):
        return {}
    return {key: amount for key, amount in value.items() if isinstance(key, str)
            and key.endswith(("_tokens", "_token_count")) and type(amount) in (int, float)
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
            if not isinstance(event, dict):
                continue
            if event.get("type") == "turn.completed":
                measured = _counts(event.get("usage"))
            elif event.get("partial") is not True:
                # Embedded ADK emits reported_usage on the model response event.
                # Partial streaming snapshots are cumulative, so never add them
                # to the final response's usage.
                measured = _counts(event.get("reported_usage"))
            else:
                measured = {}
            for key, amount in measured.items():
                usage[key] = usage.get(key, 0) + amount
    return usage


def _call_usage(records, events):
    """Raw events win per field; missing fields may use a copied receipt once."""
    receipts = {}
    for record in reversed(records):
        receipts.update(_counts(record.get("reported_usage")))
    measured = _event_usage(events)
    has_events = bool(measured)
    supplemented = has_events and bool(receipts.keys() - measured.keys())
    return {**receipts, **measured}, has_events, supplemented


def summarize_calls(calls: Path):
    usage, elapsed = {}, 0.0
    invocations = usage_calls = event_calls = receipt_calls = supplement_calls = elapsed_calls = 0
    parents = {path.parent for name in ("invocation.json", "runtime-result.json", "process-result.json")
               for path in calls.glob(f"*/*/{name}")}
    for parent in sorted(parents):
        invocations += 1
        records = []
        for name in ("invocation.json", "runtime-result.json", "process-result.json"):
            try:
                receipt = json.loads((parent / name).read_text())
                records.append(receipt if isinstance(receipt, dict) else {})
            except (ValueError, TypeError, OSError):
                records.append({})
        duration = next((receipt.get("elapsed_seconds") for receipt in records
                         if type(receipt.get("elapsed_seconds")) in (int, float)
                         and math.isfinite(receipt["elapsed_seconds"]) and receipt["elapsed_seconds"] >= 0), None)
        if type(duration) in (int, float) and math.isfinite(duration) and duration >= 0:
            elapsed += duration
            elapsed_calls += 1
        measured, has_events, supplemented = _call_usage(records, parent / "events.jsonl")
        if has_events:
            event_calls += 1
        elif measured:
            receipt_calls += 1
        supplement_calls += bool(supplemented)
        if measured:
            usage_calls += 1
            for key, amount in measured.items():
                usage[key] = usage.get(key, 0) + amount
    return {"model_invocations": invocations, "model_elapsed_seconds": elapsed,
            "reported_usage": usage,
            "usage_reporting": {"status": "complete" if invocations and usage_calls == invocations else
                                "partial" if usage_calls else "unavailable",
                                "calls_with_usage": usage_calls, "calls_without_usage": invocations-usage_calls,
                                "raw_event_calls": event_calls, "receipt_fallback_calls": receipt_calls,
                                "receipt_supplement_calls": supplement_calls},
            "timing_reporting": {"calls_with_elapsed_time": elapsed_calls,
                                 "calls_without_elapsed_time": invocations-elapsed_calls}}
