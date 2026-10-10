"""Scoped, resumable Google Cloud setup/deployment. No credentials are printed or stored in source."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import ssl
import time
from pathlib import Path
import urllib.request
import urllib.error
from urllib.parse import urlsplit
import certifi
import xml.etree.ElementTree as ET
from decimal import Decimal, ROUND_DOWN

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / 'deploy/settings.json').read_text())
EVIDENCE = ROOT / 'var/evidence/cloud-release'


def environment():
    env = dict(os.environ)
    env.update(CLOUDSDK_CONFIG=str(ROOT / 'var/gcloud'), CLOUDSDK_PYTHON=sys.executable,
               CLOUDSDK_CORE_DISABLE_USAGE_REPORTING='true')
    return env


def gcloud(*args, check=True, quiet=True):
    binary = ROOT / 'var/tools/google-cloud-sdk/bin/gcloud'
    command = [str(binary), *args, '--project=' + CFG['project'], '--format=json']
    if quiet:
        command.append('--quiet')
    result = subprocess.run(command, env=environment(), cwd=ROOT, text=True, capture_output=True)
    if check and result.returncode:
        raise RuntimeError(f'gcloud {" ".join(args[:3])} failed: {result.stderr[-3000:]}')
    if result.returncode:
        if ('NOT_FOUND' in result.stderr or 'not found' in result.stderr.lower()
                or '(gcloud.run.services.describe) Cannot find service [' in result.stderr):
            return None
        raise RuntimeError(result.stderr[-3000:])
    return json.loads(result.stdout) if result.stdout.strip() else {}


def save(name, data):
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / name).write_text(json.dumps(data, indent=2) + '\n')


def account_gate():
    accounts = gcloud('auth', 'list')
    if not any(a['account'] == CFG['administrator'] and a.get('status') == 'ACTIVE' for a in accounts):
        raise RuntimeError('Sign in to the project-local gcloud as ' + CFG['administrator'])
    project = gcloud('projects', 'describe', CFG['project'])
    if str(project['projectNumber']) != CFG['project_number']:
        raise RuntimeError('Project number mismatch; refusing mutation')
    return project


def preflight():
    project = account_gate()
    result = {'project': project, 'billing': gcloud('billing', 'projects', 'describe', CFG['project']),
              'services': gcloud('run', 'services', 'list'),
              'databases': gcloud('firestore', 'databases', 'list')}
    if not result['billing'].get('billingEnabled'):
        raise RuntimeError('Billing is not enabled')
    save('preflight-latest.json', result)
    baseline = EVIDENCE / 'preflight-before.json'
    if not baseline.exists():
        baseline.write_text(json.dumps(result, indent=2) + '\n')
    return result


def service_account(name):
    return f'guide2build-{name}@{CFG["project"]}.iam.gserviceaccount.com'


def project_role(principal, role, database=None):
    condition = ('expression=resource.name=="projects/' + CFG['project'] + '/databases/' + database
                 + '",title=guide2build-' + database) if database else 'None'
    gcloud('projects', 'add-iam-policy-binding', CFG['project'], '--member=' + principal,
           '--role=' + role, '--condition=' + condition)


def bucket_role(bucket, principal, role):
    gcloud('storage', 'buckets', 'add-iam-policy-binding', 'gs://' + bucket,
           '--member=' + principal, '--role=' + role)


def service_origins(service):
    """Use advertised Cloud Run origins, including both aliases and active tags."""
    metadata = service.get('metadata', {})
    name = metadata.get('name')
    if name not in (CFG['public_service'], CFG['preview_service']):
        raise RuntimeError('Unexpected service in asset CORS configuration')
    try:
        advertised = json.loads(metadata.get('annotations', {}).get('run.googleapis.com/urls', '[]'))
    except (ValueError, TypeError) as exc:
        raise RuntimeError('Invalid Cloud Run URL metadata') from exc
    if not isinstance(advertised, list):
        raise RuntimeError('Invalid Cloud Run URL metadata')
    status = service.get('status', {})
    urls = [status.get('url'), *advertised,
            *(entry['url'] for entry in status.get('traffic', []) if entry.get('url'))]
    origins = set()
    for value in urls:
        if not isinstance(value, str):
            raise RuntimeError('Missing or invalid Cloud Run origin')
        url = urlsplit(value)
        hostname = url.hostname or ''
        service_host = hostname.split('---')[-1]
        if (url.scheme != 'https' or url.netloc != hostname or not hostname.endswith('.run.app')
                or not service_host.startswith(name + '-') or url.path not in ('', '/')
                or url.query or url.fragment):
            raise RuntimeError('Unsafe Cloud Run origin in asset CORS configuration')
        origins.add('https://' + hostname)
    return sorted(origins)


def configure_asset_cors():
    """Repair the existing public asset bucket without rebuilding or publishing."""
    services = [gcloud('run', 'services', 'describe', name, '--region=' + CFG['region'])
                for name in (CFG['public_service'], CFG['preview_service'])]
    origins = sorted({origin for service in services for origin in service_origins(service)})
    desired = [{'origin': origins, 'method': ['GET', 'HEAD'],
                'responseHeader': ['Content-Type', 'ETag'], 'maxAgeSeconds': 3600}]
    bucket = 'gs://' + CFG['assets_bucket']
    # Formatted gcloud metadata omits the project owner; use raw API keys.
    before = gcloud('storage', 'buckets', 'describe', bucket, '--raw')
    if before.get('name') != CFG['assets_bucket'] or str(before.get('projectNumber')) != CFG['project_number']:
        raise RuntimeError('Asset bucket is not owned by the selected project')
    previous = before.get('cors', [])
    save('cors-before.json', previous)
    save('cors.json', desired)
    # The provider may reorder origins or headers in its readback.
    def normalized(rules):
        return sorted(json.dumps({key: sorted(value) if isinstance(value, list) else value
                                  for key, value in rule.items()}, sort_keys=True) for rule in rules)
    changed = normalized(previous) != normalized(desired)
    if changed:
        gcloud('storage', 'buckets', 'update', bucket, '--cors-file=' + str(EVIDENCE / 'cors.json'))
    after = gcloud('storage', 'buckets', 'describe', bucket, '--raw')
    if normalized(after.get('cors', [])) != normalized(desired):
        raise RuntimeError('Asset CORS configuration could not be verified')
    result = {'origins': origins, 'changed': changed, 'verified': True}
    save('cors-readback.json', result)
    return result


def provision():
    preflight()
    gcloud('services', 'enable', 'run.googleapis.com', 'firestore.googleapis.com',
           'storage.googleapis.com', 'artifactregistry.googleapis.com', 'cloudbuild.googleapis.com',
           'iam.googleapis.com', 'iamcredentials.googleapis.com', 'billingbudgets.googleapis.com')
    for name in ('portal', 'builder', 'uploader', 'publisher'):
        email = service_account(name)
        if gcloud('iam', 'service-accounts', 'describe', email, check=False) is None:
            gcloud('iam', 'service-accounts', 'create', 'guide2build-' + name,
                   '--display-name=Guide2Build ' + name)
        # No keys. Only the approved account can impersonate the narrowly scoped local roles.
        if name in ('uploader', 'publisher'):
            gcloud('iam', 'service-accounts', 'add-iam-policy-binding', email,
                   '--member=user:' + CFG['administrator'], '--role=roles/iam.serviceAccountTokenCreator')
        gcloud('iam', 'service-accounts', 'add-iam-policy-binding', email,
               '--member=user:' + CFG['administrator'], '--role=roles/iam.serviceAccountUser')
    for database in (CFG['database'], CFG['request_database']):
        existing = gcloud('firestore', 'databases', 'describe', '--database=' + database, check=False)
        if existing is None:
            gcloud('firestore', 'databases', 'create', '--database=' + database,
                   '--location=' + CFG['region'], '--type=firestore-native', '--delete-protection')
        elif existing.get('locationId') != CFG['region']:
            raise RuntimeError('Existing dedicated database has wrong region')
    for field in ('staging_bucket', 'assets_bucket', 'build_bucket'):
        name = CFG[field]
        existing = gcloud('storage', 'buckets', 'describe', 'gs://' + name, check=False)
        if existing is None:
            args = ['storage', 'buckets', 'create', 'gs://' + name,
                    '--location=' + CFG['region'], '--uniform-bucket-level-access']
            if field != 'assets_bucket':
                args.append('--public-access-prevention')
            gcloud(*args)
        elif str(existing.get('project_number')) != CFG['project_number']:
            raise RuntimeError('Bucket is not owned by the selected project')
        gcloud('storage', 'buckets', 'update', 'gs://' + name, '--update-labels=app=guide2build')
    if gcloud('artifacts', 'repositories', 'describe', CFG['repository'],
              '--location=' + CFG['region'], check=False) is None:
        gcloud('artifacts', 'repositories', 'create', CFG['repository'], '--repository-format=docker',
               '--location=' + CFG['region'], '--labels=app=guide2build')
    portal = 'serviceAccount:' + service_account('portal')
    project_role(portal, 'roles/datastore.viewer', CFG['database'])
    project_role(portal, 'roles/datastore.user', CFG['request_database'])
    project_role('serviceAccount:' + service_account('uploader'), 'roles/datastore.user', CFG['request_database'])
    project_role('serviceAccount:' + service_account('publisher'), 'roles/datastore.user', CFG['database'])
    builder = 'serviceAccount:' + service_account('builder')
    project_role(builder, 'roles/logging.logWriter')
    gcloud('artifacts', 'repositories', 'add-iam-policy-binding', CFG['repository'],
           '--location=' + CFG['region'], '--member=' + builder, '--role=roles/artifactregistry.writer')
    bucket_role(CFG['build_bucket'], builder, 'roles/storage.objectViewer')
    bucket_role(CFG['staging_bucket'], 'serviceAccount:' + service_account('uploader'), 'roles/storage.objectCreator')
    bucket_role(CFG['staging_bucket'], 'serviceAccount:' + service_account('uploader'), 'roles/storage.objectViewer')
    bucket_role(CFG['staging_bucket'], 'serviceAccount:' + service_account('publisher'), 'roles/storage.objectViewer')
    bucket_role(CFG['assets_bucket'], 'serviceAccount:' + service_account('publisher'), 'roles/storage.objectCreator')
    bucket_role(CFG['assets_bucket'], 'serviceAccount:' + service_account('publisher'), 'roles/storage.objectViewer')
    # Approved asset bucket contains only allowlisted, approved tutorial bytes. Never change org policy.
    bucket_role(CFG['assets_bucket'], 'allUsers', 'roles/storage.objectViewer')
    save('provisioned.json', {'settings': CFG, 'time': time.time(), 'tutorials_published': 0})


def budget():
    if (EVIDENCE / 'budget-console.json').exists():
        print('Project-scoped budget already recorded from the Cloud Console. Use that budget to review or change alerts; no duplicate created.')
        return
    state = preflight()
    billing = state['billing']['billingAccountName'].split('/')[-1]
    account = gcloud('billing', 'accounts', 'describe', billing)
    currency = account.get('currencyCode', 'CHF')
    amount = Decimal('10')
    rate_evidence = None
    if currency != 'USD':
        url = 'https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml'
        with urllib.request.urlopen(url, timeout=30, context=ssl.create_default_context(cafile=certifi.where())) as response:
            data = response.read(200000)
        root = ET.fromstring(data)
        rates = {e.attrib['currency']: Decimal(e.attrib['rate']) for e in root.iter() if 'currency' in e.attrib}
        amount = (amount * rates[currency] / rates['USD']).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
        rate_evidence = {'url': url, 'date': next(e.attrib['time'] for e in root.iter() if 'time' in e.attrib),
                         'usd': str(rates['USD']), currency: str(rates[currency])}
    name = 'Guide2Build conservative project cost alert'
    existing = gcloud('billing', 'budgets', 'list', '--billing-account=' + billing)
    matches = [b for b in existing if b.get('displayName') == name]
    args = ['billing', 'budgets', 'update', matches[0]['name']] if matches else ['billing', 'budgets', 'create']
    result = gcloud(*args, '--billing-account=' + billing, '--display-name=' + name,
                    '--budget-amount=' + str(amount) + currency, '--filter-projects=' + CFG['project_number'],
                    '--threshold-rule=percent=0.5', '--threshold-rule=percent=0.8', '--threshold-rule=percent=1.0')
    save('budget.json', {'result': result, 'exchange': rate_evidence,
                        'scope': 'Entire shared project; conservative alerts also include existing workloads. Not a hard cap.'})


def deploy(preview_only=False, build_id=None):
    account_gate()
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
        raise RuntimeError('Commit tested changes locally before deployment')
    subprocess.run([sys.executable, 'tools/check.py'], cwd=ROOT, check=True)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    image = f'{CFG["region"]}-docker.pkg.dev/{CFG["project"]}/{CFG["repository"]}/web:{revision}'
    if build_id:
        build = gcloud('builds', 'describe', build_id)
        built_tag = build.get('substitutions', {}).get('_IMAGE', '')
        prefix = image.rsplit(':', 1)[0] + ':'
        import re
        if (build.get('status') != 'SUCCESS' or not built_tag.startswith(prefix)
                or not re.fullmatch('[a-f0-9]{40}', built_tag[len(prefix):])):
            raise RuntimeError('Only a successful Guide2Build build from a local commit can resume')
        built_revision = built_tag[len(prefix):]
        changes = subprocess.check_output(['git', 'diff', '--name-only', built_revision, revision],
                                          cwd=ROOT, text=True).splitlines()
        if any(path != 'tools/cloud.py' and not path.startswith(('docs/', 'tests/backend/')) for path in changes):
            raise RuntimeError('Application inputs changed since the build; rebuild required')
        revision, image = built_revision, built_tag
    else:
        build = gcloud('builds', 'submit', '.', '--config=deploy/cloudbuild.yaml', '--suppress-logs',
                       '--substitutions=_IMAGE=' + image,
                       '--service-account=projects/' + CFG['project'] + '/serviceAccounts/' + service_account('builder'),
                       '--gcs-source-staging-dir=gs://' + CFG['build_bucket'] + '/source')
    save('build-' + revision[:12] + '.json', build)
    built_images = build.get('results', {}).get('images', [])
    built_image = next((item for item in built_images if item.get('name') == image), None)
    if not built_image or not built_image.get('digest', '').startswith('sha256:'):
        raise RuntimeError('Build did not return the expected immutable image digest')
    image = image.rsplit(':', 1)[0] + '@' + built_image['digest']
    env = ','.join(['GUIDE2BUILD_PUBLIC_STORE=firestore', 'GOOGLE_CLOUD_PROJECT=' + CFG['project'],
                    'GUIDE2BUILD_FIRESTORE_DATABASE=' + CFG['database'],
                    'GUIDE2BUILD_REQUEST_DATABASE=' + CFG['request_database'],
                    'GUIDE2BUILD_PUBLIC_BUCKET=' + CFG['assets_bucket'],
                    'GUIDE2BUILD_ASSET_BASE_URL=https://storage.googleapis.com/' + CFG['assets_bucket'] + '/',
                    'GUIDE2BUILD_WEB_DIST=/app/apps/web/dist'])
    def release(service, public):
        previous = gcloud('run', 'services', 'describe', service, '--region=' + CFG['region'], check=False)
        save(service + '-before.json', previous)
        rollout_args = ['--no-traffic', '--tag=verify-' + revision[:12]] if previous and public else []
        result = gcloud('run', 'deploy', service, '--image=' + image, '--region=' + CFG['region'],
                        '--service-account=' + service_account('portal'), '--min=0', '--max=1',
                        '--cpu=1', '--memory=512Mi', '--concurrency=40', '--timeout=30', '--cpu-throttling',
                        '--set-env-vars=' + env, '--labels=app=guide2build',
                        '--allow-unauthenticated' if public else '--no-allow-unauthenticated', *rollout_args)
        save(service + '-deployed.json', result)
        # Configure all real aliases/tags before smoke checks or a traffic shift.
        # The initial preview deployment can precede creation of the public service.
        if public or gcloud('run', 'services', 'describe', CFG['public_service'],
                            '--region=' + CFG['region'], check=False) is not None:
            configure_asset_cors()
        if previous and public:
            tagged = next(t['url'] for t in result['status']['traffic'] if t.get('tag') == 'verify-' + revision[:12])
            smoke(tagged)
            gcloud('run', 'services', 'update-traffic', service, '--region=' + CFG['region'],
                   '--to-revisions=' + result['status']['latestReadyRevisionName'] + '=100')
        return result['status']['url']
    preview = release(CFG['preview_service'], False)
    gcloud('run', 'services', 'add-iam-policy-binding', CFG['preview_service'], '--region=' + CFG['region'],
           '--member=user:' + CFG['administrator'], '--role=roles/run.invoker')
    # ID token only enters an in-memory HTTP header, never console or evidence.
    result = subprocess.run([str(ROOT / 'var/tools/google-cloud-sdk/bin/gcloud'), 'auth', 'print-identity-token'],
                            env=environment(), capture_output=True, text=True, check=True)
    smoke(preview, result.stdout.strip())
    if not preview_only:
        public = release(CFG['public_service'], True)
        try:
            smoke(public)
        except Exception:
            before = json.loads((EVIDENCE / (CFG['public_service'] + '-before.json')).read_text())
            if before:
                rollback()
            else:
                gcloud('run', 'services', 'remove-iam-policy-binding', CFG['public_service'],
                       '--region=' + CFG['region'], '--member=allUsers', '--role=roles/run.invoker')
            raise
        save('live.json', {'url': public, 'preview_url': preview, 'revision': revision, 'image': image})
        print('Public website:', public)


def smoke(base, token=None):
    headers = {'Authorization': 'Bearer ' + token} if token else {}
    for path in ('/', '/api/v1/health', '/api/v1/config', '/api/v1/sets/30669'):
        request = urllib.request.Request(base + path, headers=headers)
        with urllib.request.urlopen(request, timeout=60, context=ssl.create_default_context(cafile=certifi.where())) as response:
            if response.status != 200:
                raise RuntimeError('Cloud smoke check failed: ' + path)
            content = response.read(2_000_000)
        if path == '/api/v1/config' and json.loads(content).get('mode') != 'public':
            raise RuntimeError('Refusing deployment of private/local app')
    print('Cloud smoke passed:', base)


def rollback():
    account_gate()
    path = EVIDENCE / (CFG['public_service'] + '-before.json')
    previous = json.loads(path.read_text()) if path.exists() else None
    if not previous:
        raise RuntimeError('No previous deployment exists to restore; inspect first deployment failure')
    traffic = previous.get('status', {}).get('traffic', [])
    revisions = ','.join(t['revisionName'] + '=' + str(t['percent']) for t in traffic if t.get('percent'))
    if not revisions:
        raise RuntimeError('No recorded previous traffic mapping')
    result = gcloud('run', 'services', 'update-traffic', CFG['public_service'], '--region=' + CFG['region'],
                    '--to-revisions=' + revisions)
    save('rollback.json', result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('preflight', 'provision', 'budget', 'deploy', 'preview', 'rollback', 'asset-cors'))
    p.add_argument('--apply', action='store_true', help='Execute approved cloud mutations')
    p.add_argument('--build-id', help='Resume deploy/preview from a successful existing build with unchanged application inputs')
    args = p.parse_args()
    if args.command != 'preflight' and not args.apply:
        print(json.dumps({'action': args.command, 'settings': CFG, 'dry_run': True}, indent=2))
        return 0
    try:
        if args.command == 'preflight':
            preflight()
            print('Account, project, billing and current resources verified; evidence saved.')
        elif args.command == 'provision':
            provision()
        elif args.command == 'budget':
            budget()
        elif args.command == 'rollback':
            rollback()
        elif args.command == 'asset-cors':
            account_gate()
            print(json.dumps(configure_asset_cors(), indent=2))
        else:
            deploy(preview_only=args.command == 'preview', build_id=args.build_id)
    except (RuntimeError, subprocess.CalledProcessError, OSError, ValueError) as e:
        print('BLOCKED:', str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
