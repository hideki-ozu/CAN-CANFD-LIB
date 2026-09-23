#!/usr/bin/env python3
"""Export local source changes without staging files or including build products."""
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUFFIXES = {'.cc', '.h', '.ned', '.msg', '.md', '.ini', '.sh', '.py'}
for name in ('CoRE4INET', 'FiCo4OMNeT', 'SignalsAndGateways'):
    repo = ROOT / 'upstream' / name
    patch = subprocess.check_output(['git', 'diff', '--binary', 'HEAD'], cwd=repo)
    untracked = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '-z'], cwd=repo)
    for relative in sorted(x.decode() for x in untracked.split(b'\0') if x):
        path = pathlib.Path(relative)
        if any(part in {'results', 'out', 'out-inet4'} for part in path.parts):
            continue
        if path.name.endswith(('_m.cc', '_m.h')):
            continue
        if path.suffix not in SUFFIXES and path.name not in {'Makefile.inet4', 'README'}:
            continue
        change = subprocess.run(['git', 'diff', '--no-index', '--binary', '--', '/dev/null', relative],
                                cwd=repo, stdout=subprocess.PIPE, check=False)
        if change.returncode not in (0, 1):
            raise RuntimeError(f'Cannot export {relative}')
        patch += change.stdout
    (ROOT / 'patches' / (name + '.patch')).write_bytes(patch)
    print(name, len(patch), 'bytes')
