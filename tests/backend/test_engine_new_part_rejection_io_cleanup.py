"""Actual reader cleanup probes; runnable directly without importing pytest."""

import errno
import multiprocessing
import os
from pathlib import Path
import resource

from guide2build.reconstruction import individual_closure as module

KINDS = ("directory", "fifo", "oversize", "hardlink", "first_fstat", "constructor", "read", "second_fstat")


class InjectedFailure(RuntimeError):
    pass


def _exercise(root, kind, channel):
    root = Path(root)
    original_open, original_fstat, original_fdopen = module._open_nofollow, os.fstat, os.fdopen
    current, fstats, wrappers = None, 0, 0

    def inventory():
        present = []
        for number in range(64):
            try:
                original_fstat(number)
            except OSError as error:
                if error.errno != errno.EBADF:
                    raise
            else:
                present.append(number)
        return present

    def open_leaf(path):
        nonlocal current, fstats
        current, fstats = original_open(path), 0
        return current

    def fstat(descriptor):
        nonlocal fstats
        if descriptor == current:
            fstats += 1
            if (kind == "first_fstat" and fstats == 1) or (kind == "second_fstat" and fstats == 2):
                raise InjectedFailure(kind)
        return original_fstat(descriptor)

    class FailingRead:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def fileno(self):
            return self.stream.fileno()

        def read(self, _limit):
            raise InjectedFailure("read")

    def fdopen(*args, **kwargs):
        nonlocal wrappers
        wrappers += 1
        if kind == "constructor":
            raise InjectedFailure(kind)
        stream = original_fdopen(*args, **kwargs)
        return FailingRead(stream) if kind == "read" else stream

    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        resource.setrlimit(resource.RLIMIT_NOFILE, (64 if soft == resource.RLIM_INFINITY else min(64, soft), hard))
        root.mkdir()
        regular = root / "regular.dat"
        regular.write_bytes(b"untouched regular bytes")
        target = root / "target.dat"
        if kind == "directory":
            target.mkdir()
        elif kind == "fifo":
            os.mkfifo(target)
        else:
            target.write_bytes(b"bounded original bytes")
            if kind == "hardlink":
                os.link(target, root / "alias.dat")
        before = inventory()
        module._open_nofollow, os.fstat, os.fdopen = open_leaf, fstat, fdopen
        rejected = 0
        for _ in range(128):
            try:
                module.read(target, root, limit=3 if kind == "oversize" else module.MAX_RESOURCE)
            except (ValueError, InjectedFailure):
                rejected += 1
            else:
                raise AssertionError("Invalid resource or injected failure was admitted")
            assert inventory() == before, (kind, before, inventory())
        module._open_nofollow, os.fstat, os.fdopen = original_open, original_fstat, original_fdopen
        assert rejected == 128
        if kind in ("directory", "fifo", "oversize", "hardlink", "first_fstat"):
            assert wrappers == 0, "Wrapping preceded raw-descriptor admission"
        assert module.read(regular, root) == b"untouched regular bytes"
        assert inventory() == before
        channel.send({"status": "passed", "kind": kind, "rejections": rejected,
                      "fd_inventory_before": before, "fd_inventory_after": inventory(),
                      "fdopen_calls": wrappers, "regular_read_after_rejections": True})
    except BaseException as error:
        channel.send({"status": "failed", "kind": kind, "error": type(error).__name__, "message": str(error)})
    finally:
        module._open_nofollow, os.fstat, os.fdopen = original_open, original_fstat, original_fdopen
        channel.close()


def run_io_case(root, kind):
    context = multiprocessing.get_context("fork")
    parent, sender = context.Pipe(duplex=False)
    process = context.Process(target=_exercise, args=(str(root), kind, sender))
    process.start()
    sender.close()
    try:
        process.join(timeout=5)
        assert not process.is_alive(), "Private IO probe exceeded five seconds"
        assert process.exitcode == 0 and parent.poll()
        result = parent.recv()
        assert result["status"] == "passed", result
        return result
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=2)
        parent.close()


def test_directory_admission_closes_raw_descriptor(tmp_path):
    run_io_case(tmp_path / "private", "directory")


def test_fifo_admission_closes_raw_descriptor(tmp_path):
    run_io_case(tmp_path / "private", "fifo")


def test_oversized_admission_closes_raw_descriptor(tmp_path):
    run_io_case(tmp_path / "private", "oversize")


def test_hardlink_admission_closes_raw_descriptor(tmp_path):
    run_io_case(tmp_path / "private", "hardlink")


def test_initial_fstat_failure_closes_raw_descriptor(tmp_path):
    run_io_case(tmp_path / "private", "first_fstat")


def test_stream_constructor_failure_closes_raw_descriptor(tmp_path):
    run_io_case(tmp_path / "private", "constructor")


def test_stream_read_failure_closes_raw_descriptor(tmp_path):
    run_io_case(tmp_path / "private", "read")


def test_final_fstat_failure_closes_raw_descriptor(tmp_path):
    run_io_case(tmp_path / "private", "second_fstat")
