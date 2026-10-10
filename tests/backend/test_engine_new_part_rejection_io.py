"""Bounded local IO regressions; no provider, network or active job inputs."""

import multiprocessing
import os
from pathlib import Path
import resource

from guide2build.reconstruction.individual_closure import read


def _exercise(path, root, connection, mode):
    path, root = Path(path), Path(root)
    real_open = os.open
    try:
        if mode == "swap":
            replaced = False

            def open_leaf(name, flags, *args, **kwargs):
                nonlocal replaced
                if name == path.name and "dir_fd" in kwargs and not replaced:
                    path.unlink()
                    os.mkfifo(path)
                    replaced = True
                return real_open(name, flags, *args, **kwargs)

            os.open = open_leaf
            try:
                read(path, root)
            except ValueError as error:
                connection.send({"replaced": replaced, "rejected": type(error).__name__})
            else:
                connection.send({"unexpected_success": True})
        else:
            soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
            bounded_soft = 64 if soft == resource.RLIM_INFINITY else min(64, soft)
            resource.setrlimit(resource.RLIMIT_NOFILE, (bounded_soft, hard))
            rejected = 0
            for _ in range(128):
                try:
                    read(path, root)
                except ValueError:
                    rejected += 1
            regular = root / "regular.dat"
            connection.send({"rejected": rejected, "regular_after_rejections": read(regular, root) == b"intact"})
    except BaseException as error:
        connection.send({"unexpected_error": type(error).__name__, "message": str(error)})
    finally:
        os.open = real_open
        connection.close()


def _bounded(path, root, mode):
    context = multiprocessing.get_context("fork")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_exercise, args=(str(path), str(root), child, mode))
    process.start()
    child.close()
    try:
        process.join(timeout=5)
        assert not process.is_alive(), "Non-regular local resource read exceeded its bounded subprocess time"
        assert process.exitcode == 0 and parent.poll()
        return parent.recv()
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=2)
        parent.close()


def test_regular_file_keeps_exact_bytes_with_nofollow_nonblocking_leaf(tmp_path, monkeypatch):
    path = tmp_path / "regular.dat"
    content = bytes(range(256)) * 4
    path.write_bytes(content)
    original = os.open
    observed = []

    def observe(name, flags, *args, **kwargs):
        if name == path.name and "dir_fd" in kwargs:
            observed.append(flags)
        return original(name, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", observe)
    assert read(path, tmp_path) == content
    assert len(observed) == 1
    assert observed[0] & os.O_NOFOLLOW and observed[0] & os.O_NONBLOCK


def test_regular_leaf_swapped_to_fifo_before_open_is_rejected_without_blocking(tmp_path):
    path = tmp_path / "resource.dat"
    path.write_bytes(b"original regular file")
    assert _bounded(path, tmp_path, "swap") == {"replaced": True, "rejected": "ValueError"}


def test_repeated_fifo_rejection_closes_descriptors_under_finite_process_limit(tmp_path):
    path = tmp_path / "resource.dat"
    os.mkfifo(path)
    (tmp_path / "regular.dat").write_bytes(b"intact")
    assert _bounded(path, tmp_path, "repeat") == {"rejected": 128, "regular_after_rejections": True}
