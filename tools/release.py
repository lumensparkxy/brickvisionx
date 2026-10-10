#!/usr/bin/env python3
"""Stage or approve one immutable tutorial version. No implicit tutorial approval."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/api/src'))
from guide2build.releases.auth import verify_google_identity, role_credentials  # noqa: E402
from guide2build.releases.cloud import GCSReleases  # noqa: E402
from guide2build.releases.store import FirestoreReleaseStore  # noqa: E402
from guide2build.releases.packaging import package_release, verify_bundle  # noqa: E402
from guide2build.releases.models import SceneV2, ReleaseValidation  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('package')
    p.add_argument('--scene', type=Path, required=True)
    p.add_argument('--validation', type=Path, required=True)
    p.add_argument('--coverage-index', type=Path, required=True)
    p.add_argument('--geometry-root', type=Path, default=ROOT / 'var/public/ldraw')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--preview', type=Path, required=True, help='Actual model-render PNG for this exact scene')
    p = sub.add_parser('package-alpha', help='Package a disclosed unverified alpha; never a reviewed tutorial')
    p.add_argument('--scene', type=Path, required=True)
    p.add_argument('--disclosure', type=Path, required=True)
    p.add_argument('--source-index', type=Path, required=True)
    p.add_argument('--preview-binding', type=Path, required=True)
    p.add_argument('--geometry-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--preview', type=Path, required=True)
    p = sub.add_parser('verify')
    p.add_argument('directory', type=Path)
    p = sub.add_parser('stage')
    p.add_argument('directory', type=Path)
    p.add_argument('--transfer-workers', type=int, choices=range(1, 9), default=1)
    for command in ('approve', 'publish', 'rollback'):
        p = sub.add_parser(command)
        p.add_argument('--release', required=True)
        p.add_argument('--transfer-workers', type=int, choices=range(1, 9), default=1)
        if command != 'approve':
            p.add_argument('--expected-head', default=None)
    args = parser.parse_args()
    if args.command == 'package':
        manifest = package_release(SceneV2.model_validate_json(args.scene.read_text()),
            ReleaseValidation.model_validate_json(args.validation.read_text()), args.geometry_root, args.output, args.preview,
            source_index=json.loads(args.coverage_index.read_text()))
        print(json.dumps({'release_sha256': manifest['release_sha256'], 'state': 'packaged'}))
        return
    if args.command == 'verify':
        manifest = verify_bundle(args.directory)
        print(json.dumps({'release_sha256': manifest['release_sha256'], 'state': 'verified'}))
        return
    if args.command == 'package-alpha':
        from guide2build.releases.alpha import package_alpha_release
        manifest = package_alpha_release(SceneV2.model_validate_json(args.scene.read_text()),
            json.loads(args.disclosure.read_text()), args.geometry_root, args.output, args.preview,
            source_index=json.loads(args.source_index.read_text()),
            preview_binding=json.loads(args.preview_binding.read_text()))
        print(json.dumps({'release_sha256': manifest['release_sha256'], 'state': 'packaged',
                          'release_kind': manifest['release_kind']}))
        return
    project = os.getenv('GOOGLE_CLOUD_PROJECT', 'lumensparkxy')
    os.environ.setdefault('CLOUDSDK_CONFIG', str(ROOT / 'var/gcloud'))
    os.environ.setdefault('CLOUDSDK_PYTHON', sys.executable)
    os.environ.setdefault('CLOUDSDK_CORE_DISABLE_USAGE_REPORTING', 'true')
    adc = ROOT / 'var/gcloud/application_default_credentials.json'
    if adc.is_file():
        os.environ.setdefault('GOOGLE_APPLICATION_CREDENTIALS', str(adc))
    credentials = role_credentials(project, 'uploader' if args.command == 'stage' else 'publisher')
    store = FirestoreReleaseStore(project, credentials=credentials)
    cloud = GCSReleases(project, os.getenv('GUIDE2BUILD_STAGING_BUCKET', project + '-guide2build-staging'),
                        os.getenv('GUIDE2BUILD_PUBLIC_BUCKET', project + '-guide2build-assets'), credentials=credentials,
                        transfer_workers=getattr(args, 'transfer_workers', 1))
    if args.command == 'stage':
        manifest = cloud.stage(args.directory)
        print(json.dumps({'release_sha256': manifest['release_sha256'], 'state': 'awaiting_approval'}))
        return
    # gcloud authenticates the approved human; neither CLI email flags nor actor_type grant authority.
    gcloud = os.getenv('GUIDE2BUILD_GCLOUD', str(ROOT / 'var/tools/google-cloud-sdk/bin/gcloud'))
    token = subprocess.run([gcloud, 'auth', 'print-identity-token', '--account=maswadkar@gmail.com'],
        capture_output=True, text=True, check=True, timeout=30).stdout.strip()
    identity = verify_google_identity(token)
    if args.command == 'approve':
        manifest = cloud.validate_staged(args.release)
        store.stage(manifest)
        store.approve(args.release, identity)
        state = 'approved'
    else:
        # Approval check BEFORE public writes. No approved hash means no asset publication.
        approval = store.db.collection('approvals').document(args.release).get()
        if not approval.exists or approval.to_dict().get('email') != identity.email:
            raise PermissionError('Exact release requires your approval first')
        cloud.publish(args.release, identity)
        store.promote(args.release, identity, args.expected_head)
        state = 'published'
    print(json.dumps({'release_sha256': args.release, 'state': state}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Never print credentials or external-provider response bodies.
        print(f'Release operation failed ({type(exc).__name__}); no success is claimed.', file=sys.stderr)
        raise SystemExit(1)
