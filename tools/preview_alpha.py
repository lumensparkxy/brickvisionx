"""Browse explicitly selected alpha engine jobs in one private, read-only local portal."""
import argparse
import json
from pathlib import Path

import uvicorn

from _paths import ROOT
from guide2build.engine.preview import create_campaign_preview_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job_ids', nargs='*')
    parser.add_argument('--campaign-file', type=Path, help='JSON object with an explicit job_ids list')
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'var')
    parser.add_argument('--port', type=int, default=4175)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Port must be between 1 and 65535')
    if bool(args.job_ids) == bool(args.campaign_file):
        parser.error('Supply job identifiers or --campaign-file, exclusively')
    try:
        job_ids = args.job_ids if args.job_ids else json.loads(args.campaign_file.read_text())['job_ids']
        app = create_campaign_preview_app(args.data_dir, job_ids)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(f'Private alpha sample portal: http://127.0.0.1:{args.port}', flush=True)
    uvicorn.run(app, host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
