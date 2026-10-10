"""Install the verified Google SDK archive under var/tools without changing shell profiles."""
from pathlib import Path
import hashlib
import json
import platform
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-darwin-arm.tar.gz'
SHA256 = '8d9a37edebadca3428a0823410c0451949221a373429b4032af8b344442f3333'


def main():
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise SystemExit('This verified archive targets Apple silicon macOS only.')
    directory = ROOT / 'var/tools'
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / 'google-cloud-cli-current.tar.gz'
    if not archive.exists():
        with urllib.request.urlopen(URL, timeout=60) as response, archive.open('wb') as output:
            while block := response.read(1024 * 1024):
                output.write(block)
                if output.tell() > 150 * 1024 * 1024:
                    raise SystemExit('SDK archive exceeds size limit')
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual != SHA256:
        raise SystemExit('SDK checksum changed. Verify the current Google install page before updating the pin.')
    if not (directory / 'google-cloud-sdk').exists():
        with tarfile.open(archive) as source:
            source.extractall(directory, filter='data')
    receipt = {'url': URL, 'sha256': actual, 'version': '587.0.0',
               'verified_against': 'https://docs.cloud.google.com/sdk/docs/install-sdk',
               'shell_profile_modified': False}
    (directory / 'sdk-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('Verified project-local SDK ready: var/tools/google-cloud-sdk/bin/gcloud')


if __name__ == '__main__':
    main()
