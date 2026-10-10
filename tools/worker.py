"""Run the local durable conversion worker; no provider calls or paid services."""
import argparse
import os
from pathlib import Path
import time
import uuid
from _paths import ROOT
from guide2build.jobs.store import Store
from guide2build.jobs.worker import run_once


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--data-dir", type=Path, default=Path(os.getenv("GUIDE2BUILD_DATA_DIR", str(ROOT / "var"))))
    args = parser.parse_args()
    store = Store(args.data_dir)
    owner = uuid.uuid4().hex
    try:
        while True:
            worked = run_once(store, owner=owner)
            if args.once:
                return
            if not worked:
                time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
