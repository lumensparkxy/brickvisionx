import json
from guide2build.engine.reporting import summarize_calls


def call(root, stage, receipt, events=None):
    directory = root / stage / "1"
    directory.mkdir(parents=True)
    (directory / "invocation.json").write_text(json.dumps(receipt))
    if events is not None:
        (directory / "events.jsonl").write_text("\n".join(json.dumps(event) for event in events))


def test_legacy_usage_is_recovered_without_double_counting_new_receipts(tmp_path):
    legacy = {"input_tokens": 100, "output_tokens": 20, "cached_input_tokens": 50}
    new = {"input_tokens": 40, "output_tokens": 10, "cached_input_tokens": 0}
    call(tmp_path, "index-0", {"elapsed_seconds": 2}, [{"type": "turn.completed", "usage": legacy}])
    call(tmp_path, "construct-0", {"elapsed_seconds": 3, "reported_usage": new},
         [{"type": "turn.completed", "usage": new}])
    result = summarize_calls(tmp_path)
    assert result["model_invocations"] == 2
    assert result["model_elapsed_seconds"] == 5
    assert result["reported_usage"] == {"input_tokens": 140, "output_tokens": 30, "cached_input_tokens": 50}
    assert result["usage_reporting"]["status"] == "complete"
    assert result["usage_reporting"]["raw_event_calls"] == 2


def test_raw_events_take_precedence_and_missing_usage_is_explicit(tmp_path):
    call(tmp_path, "one", {"elapsed_seconds": 1, "reported_usage": {"input_tokens": 99}},
         [{"type": "turn.completed", "usage": {"input_tokens": 5}},
          {"type": "turn.completed", "usage": {"input_tokens": 7}},
          {"type": "item.completed", "usage": {"input_tokens": 1000}}])
    call(tmp_path, "two", {"elapsed_seconds": 2, "reported_usage": {"input_tokens": 8}})
    call(tmp_path, "three", {"elapsed_seconds": 3})
    result = summarize_calls(tmp_path)
    assert result["reported_usage"] == {"input_tokens": 20}
    assert result["usage_reporting"] == {"status": "partial", "calls_with_usage": 2, "calls_without_usage": 1,
                                          "raw_event_calls": 1, "receipt_fallback_calls": 1}


def test_malformed_and_nonfinite_measurements_are_not_invented(tmp_path):
    call(tmp_path, "bad", {"elapsed_seconds": float("nan"), "reported_usage": {"input_tokens": -1,
         "output_tokens": True, "cached_input_tokens": "30", "reasoning_output_tokens": float("inf")}},
         [None, {"type": "turn.completed", "usage": "invalid"}])
    result = summarize_calls(tmp_path)
    assert result["reported_usage"] == {}
    assert result["usage_reporting"]["status"] == "unavailable"
    assert result["timing_reporting"]["calls_without_elapsed_time"] == 1
