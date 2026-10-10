"""Open a real engine candidate in the local web portal without publishing it."""
import argparse
from pathlib import Path

from _paths import ROOT
from guide2build.engine.preview import create_preview_app
import uvicorn


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job_id')
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'var')
    parser.add_argument('--port', type=int, default=4175)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Port must be between 1 and 65535')
    app = create_preview_app(args.data_dir, args.job_id)
    print(f'Private engine candidate preview: http://127.0.0.1:{args.port}', flush=True)
    uvicorn.run(app, host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
