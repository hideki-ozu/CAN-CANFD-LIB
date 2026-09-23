#!/usr/bin/env python3
"""Fetch pinned official sources; preserve existing checkouts and apply local ports."""
import argparse
import hashlib
import json
import pathlib
import subprocess
import tarfile
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--with-omnetpp', action='store_true', help='Also download the optional Ubuntu/WSL bundled runtime (not needed for an existing installation)')
args = parser.parse_args()
manifest = json.loads((ROOT / 'sources.lock.json').read_text())
(ROOT / 'upstream').mkdir(exist_ok=True)
(ROOT / 'tools').mkdir(exist_ok=True)
(ROOT / 'downloads').mkdir(exist_ok=True)
for name, entry in manifest['repositories'].items():
    repo = ROOT / 'upstream' / name
    if not repo.exists():
        subprocess.run(['git', 'init', str(repo)], check=True)
        subprocess.run(['git', '-C', str(repo), 'remote', 'add', 'origin', entry['url']], check=True)
        subprocess.run(['git', '-C', str(repo), 'fetch', '--depth', '1', 'origin', entry['commit']], check=True)
        subprocess.run(['git', '-C', str(repo), 'checkout', '--detach', 'FETCH_HEAD'], check=True)
    actual = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != entry['commit']:
        raise SystemExit(f'{name}: existing HEAD differs from lock; preserving it, please inspect')
    patch = ROOT / 'patches' / (name + '.patch')
    if patch.exists() and patch.stat().st_size:
        cmd = ['git', '-C', str(repo), 'apply']
        if subprocess.run(cmd + ['--reverse', '--check', str(patch)], stderr=subprocess.DEVNULL).returncode == 0:
            continue
        subprocess.run(cmd + ['--check', str(patch)], check=True)
        subprocess.run(cmd + [str(patch)], check=True)
entry = manifest['omnetpp']
install = ROOT / 'tools' / entry['directory']
if args.with_omnetpp and not install.exists():
    if not hasattr(tarfile, "data_filter"):
        raise SystemExit("Optional runtime extraction requires Python with tarfile.data_filter (Python 3.12 recommended).")
    archive = ROOT / 'downloads' / entry['archive']
    if not archive.exists():
        urllib.request.urlretrieve(entry['url'], archive)
    with archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != entry['sha256']:
        raise SystemExit('OMNeT++ archive checksum mismatch')
    with tarfile.open(archive) as bundle:
        bundle.extractall(ROOT / 'tools', filter='data')
print('Pinned model sources ready. Run scripts/build-libraries.sh, then make test.')
