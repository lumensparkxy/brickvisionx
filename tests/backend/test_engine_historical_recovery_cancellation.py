"""Stop saved-evidence replay through the real heartbeat, without inference or evidence loss."""
from copy import deepcopy
import hashlib
from threading import Event
from types import SimpleNamespace

import pytest

from guide2build.engine import exploration
from guide2build.engine.runner import Heartbeat, WorkerStopped
from test_engine_exploration import harness as harness


def saved_bytes(directory):
    return {str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in directory.rglob('*') if path.is_file()}


def stopped_heartbeat(stop):
    # Real stop-event/WorkerStopped behavior; no leased worker thread or live store.
    return Heartbeat(SimpleNamespace(cancel_requested=lambda _: False), 'synthetic-job', 'synthetic-owner',
                     stop_event=stop)


def test_saved_call_receipts_stop_before_next_call_and_legacy_verification_still_works(harness, monkeypatch):
    h = harness
    assert exploration.run_exploration(**h.args)
    before, files = deepcopy(h.cp), saved_bytes(h.directory)
    call_count = len(h.provider.calls)
    keys = list(h.cp['exploration_calls'])
    assert len(keys) > 1
    stop, reads = Event(), []
    heartbeat = stopped_heartbeat(stop)
    original = exploration._read
    first_receipt = f'exploration/calls/{keys[0]}/receipt.json'
    next_request = f'exploration/calls/{keys[1]}/request.json'
    def read_then_stop(directory, relative, *args):
        value = original(directory, relative, *args)
        reads.append(relative)
        if relative == first_receipt:
            stop.set()
        return value
    monkeypatch.setattr(exploration, '_read', read_then_stop)
    with pytest.raises(WorkerStopped, match='Local queue stopped'):
        exploration._verify_call_receipts(h.directory, h.cp, check_cancel=heartbeat.check)
    assert first_receipt in reads and next_request not in reads
    assert h.cp == before and saved_bytes(h.directory) == files
    assert len(h.provider.calls) == call_count
    monkeypatch.setattr(exploration, '_read', original)
    stop.clear()
    # The existing two-argument correction caller remains source-compatible and verifies everything.
    exploration._verify_call_receipts(h.directory, h.cp)
    assert h.cp == before and saved_bytes(h.directory) == files
    assert len(h.provider.calls) == call_count


@pytest.mark.parametrize('stop_after', [1, 2])
def test_run_exploration_stops_between_or_after_last_historical_result_and_recovers(harness, monkeypatch, stop_after):
    h = harness
    assert exploration.run_exploration(**h.args)
    assert h.cp['processed_panels'] == len(h.cp['instruction_results']) == 2
    before, files = deepcopy(h.cp), saved_bytes(h.directory)
    call_count = len(h.provider.calls)
    stop = Event()
    h.args['heartbeat'] = stopped_heartbeat(stop)
    original = exploration._recover_result
    recovered = []
    def recover_then_stop(directory, result, *args):
        value = original(directory, result, *args)
        recovered.append(result['ordinal'])
        if len(recovered) == stop_after:
            stop.set()
        return value
    monkeypatch.setattr(exploration, '_recover_result', recover_then_stop)
    with pytest.raises(WorkerStopped, match='Local queue stopped'):
        exploration.run_exploration(**h.args)
    assert recovered == list(range(stop_after))
    for key in ['exploration_policy', 'exploration_calls', 'exploration_instructions', 'instruction_results',
                'candidate', 'processed_panels', 'model_calls_used', 'local_model_calls_used']:
        assert h.cp.get(key) == before.get(key), key
    assert saved_bytes(h.directory) == files and len(h.provider.calls) == call_count
    monkeypatch.setattr(exploration, '_recover_result', original)
    stop.clear()
    assert exploration.run_exploration(**h.args)
    assert h.cp == before and saved_bytes(h.directory) == files
    assert len(h.provider.calls) == call_count
