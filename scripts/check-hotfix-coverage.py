#!/usr/bin/env python3
"""Gate B: discover upload evidence; require every historical hotfix patch before pinning."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def patch_id(repo, commit, reverse=False):
    patch = git(repo, 'diff', '--binary', commit, commit + '^') if reverse else git(repo, 'show', '--pretty=format:', '--binary', commit)
    result = subprocess.check_output(['git', 'patch-id', '--stable'], input=patch).split()
    return result[0].decode() if result else ''


def normalize(data):
    text = data.decode('utf-8-sig').replace('\r\n', '\n')
    for variable in ('BundleUrl', 'BundleSha256', 'BootstrapUrl', 'BootstrapSha256'):
        text = re.sub(r'(?m)^(\$' + variable + r'\s*=.*?else\s*\{\s*)[^\r\n]+', r'\1<RELEASE VALUE>', text)
    # win-start stores the pinned bootstrap values as literals, unlike bootstrap.ps1.
    text = re.sub(r'https://github.com/[^\s\x27\x22]+/bootstrap.ps1|__WAVE_BOOTSTRAP_URL__', '<BOOTSTRAP URL>', text)
    text = re.sub(r'[a-f0-9]{64}|__WAVE_BOOTSTRAP_SHA256__', '<SHA256>', text)
    return text


def discover(round_root, history):
    commits = git(history, 'rev-list', '--reverse', 'aab5f1d..8591f09').decode().split()
    evidence = []
    for directory in sorted(round_root.glob('release*/UPLOAD_hf*')):
        sources = {}
        for asset in sorted(directory.iterdir()):
            if not asset.is_file() or asset.name == 'SHA256SUMS':
                continue
            data = asset.read_bytes()
            if asset.suffix == '.zip':
                with zipfile.ZipFile(asset) as archive:
                    members = [n for n in archive.namelist() if n.endswith('/bootstrap.ps1')]
                    if len(members) != 1:
                        raise ValueError('one bootstrap required: ' + str(asset))
                    content = archive.read(members[0])
                path = 'bootstrap.ps1'
            else:
                path, content = asset.name, data
            matches = [c for c in commits if normalize(git(history, 'show', c + ':' + path)) == normalize(content)]
            sources[asset.name] = matches[0] if matches else 'MISSING'
            evidence.append(dict(asset=asset.name, release='v0.3.3', evidence=str(asset.relative_to(round_root)),
                                 sha256=hashlib.sha256(data).hexdigest(), source_commit=sources[asset.name],
                                 normalized_sha256=hashlib.sha256(normalize(content).encode()).hexdigest(),
                                 binding='earliest exact normalized source match; ZIP bootstrap member only'))
        sums = directory / 'SHA256SUMS'
        if sums.is_file():
            evidence.append(dict(asset=sums.name, release='v0.3.3', evidence=str(sums.relative_to(round_root)),
                                 sha256=hashlib.sha256(sums.read_bytes()).hexdigest(),
                                 source_commit=','.join(sorted(set(sources.values()))) or 'MISSING',
                                 binding='checksum manifest derived from sibling assets'))
    if not evidence:
        raise ValueError('no upload evidence discovered')
    return dict(base='aab5f1d', tip='8591f09', patches=[dict(commit=c, patch_id=patch_id(history, c),
                reverse_patch_id=patch_id(history, c, reverse=True)) for c in commits], assets=evidence)


def audit(repo, manifest):
    commits = git(repo, 'rev-list', 'HEAD').decode().split()
    # Check patch identity, so cherry-picks are accepted without weakening content coverage.
    directions = {}
    for row in manifest['patches']:
        directions[row['patch_id']] = (row['commit'], True)
        directions[row['reverse_patch_id']] = (row['commit'], False)
    latest = {}
    for commit in commits:
        match = directions.get(patch_id(repo, commit))
        if match:
            latest.setdefault(*match)
        if len(latest) == len(manifest['patches']):
            break
    missing = [row['commit'] for row in manifest['patches'] if not latest.get(row['commit'])]
    print('| asset | release | SHA256 | source commit | evidence |')
    print('| --- | --- | --- | --- | --- |')
    for row in manifest['assets']:
        print('| ' + ' | '.join(row[key] for key in ('asset', 'release', 'sha256', 'source_commit', 'evidence')) + ' |')
    print('MISSING patches: ' + (', '.join(missing) or 'none'))
    unresolved = [r['evidence'] for r in manifest['assets'] if 'MISSING' in r['source_commit']]
    print('MISSING source bindings: ' + (', '.join(unresolved) or 'none'))
    return bool(missing or unresolved)


def published_gaps(directory, manifest):
    print('| published asset | release | SHA256 | hotfix source commit |')
    print('| --- | --- | --- | --- |')
    for path in sorted(directory.iterdir()):
        if path.name not in {r['asset'] for r in manifest['assets']} or path.name == 'SHA256SUMS':
            continue
        data = path.read_bytes()
        content = data
        if path.suffix == '.zip':
            with zipfile.ZipFile(path) as archive:
                members = [n for n in archive.namelist() if n.endswith('/bootstrap.ps1')]
                if len(members) != 1:
                    raise ValueError('published ZIP bootstrap missing/ambiguous')
                content = archive.read(members[0])
        fingerprint = hashlib.sha256(normalize(content).encode()).hexdigest()
        matches = sorted({r['source_commit'] for r in manifest['assets']
                          if r['asset'] == path.name and r.get('normalized_sha256') == fingerprint})
        print('| ' + ' | '.join((path.name, 'v0.3.5', hashlib.sha256(data).hexdigest(), ','.join(matches) or 'MISSING')) + ' |')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'docs/hotfix-uploads.json')
    parser.add_argument('--discover', type=Path)
    parser.add_argument('--history', type=Path)
    parser.add_argument('--published', type=Path)
    args = parser.parse_args()
    if args.discover:
        if not args.history:
            parser.error('--history required for discovery')
        args.manifest.write_text(json.dumps(discover(args.discover, args.history), indent=2) + '\n')
    manifest = json.loads(args.manifest.read_text())
    if args.published:
        published_gaps(args.published, manifest)
    raise SystemExit(audit(args.root, manifest))
