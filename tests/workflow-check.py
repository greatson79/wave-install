#!/usr/bin/env python3
"""Local workflow contract check; complements actionlint, never dispatches CI."""
import argparse
from pathlib import Path
import sys
import re

import yaml

ROOT = Path(__file__).resolve().parents[1]
RELEASE_GATE = "github.event_name == 'workflow_dispatch' && inputs.release_smoke"


class UniqueLoader(yaml.BaseLoader):
    def construct_mapping(self, node, deep=False):
        mapping = {}
        for key, value in node.value:
            name = self.construct_object(key, deep=deep)
            if name in mapping:
                raise ValueError(f'duplicate YAML key: {name}')
            mapping[name] = self.construct_object(value, deep=deep)
        return mapping


def load(path):
    return yaml.load(Path(path).read_text(encoding='utf-8-sig'), Loader=UniqueLoader)


def is_live_pin(command):
    return bool(re.search(r"(?m)^\s*(?:bash\s+)?(?:\./)?tests/win-pin-release\.sh(?:\s|$)", command))


def validate(workflow):
    errors = []
    def need(condition, message):
        if not condition:
            errors.append(message)
    triggers = workflow.get('on', {})
    need(set(triggers) == {'push', 'pull_request', 'workflow_dispatch'}, 'trigger set changed')
    inputs = triggers.get('workflow_dispatch', {}).get('inputs', {})
    smoke = inputs.get('release_smoke', {})
    need(smoke.get('type') == 'boolean' and smoke.get('default') == 'false', 'release smoke must be opt-in boolean')
    for field in ('terminal_tag', 'expected_installer_sha256'):
        need(inputs.get(field, {}).get('required') == 'false', f'{field} must not block pin-free dispatch')
    need(workflow.get('permissions') == {'contents': 'read'}, 'workflow requires read-only token')
    jobs = workflow.get('jobs', {})
    contract = jobs.get('bootstrap-contract', {})
    need(contract.get('runs-on') == '${{ matrix.os }}', 'contract must use OS matrix')
    strategy = contract.get('strategy', {})
    need(strategy.get('fail-fast') == 'false', 'matrix failures must not hide other platform results')
    need(set(strategy.get('matrix', {}).get('os', [])) == {'windows-latest', 'macos-latest'}, 'Windows/macOS runner matrix missing')
    steps = contract.get('steps', [])
    need(bool(steps) and steps[0].get('uses', '').startswith('actions/checkout@'), 'checkout must be first')
    for index, platform, shell in ((1, 'Windows', 'cmd'), (2, 'macOS', 'bash')):
        step = steps[index] if len(steps) > index else {}
        need(step.get('if') == f"runner.os == '{platform}'" and step.get('shell') == shell
             and 'tests/ps-balance.py' in step.get('run', ''), f'{platform} delimiter precheck must be first executable check')
    need(any(s.get('shell') == 'powershell' and s.get('if') == "runner.os == 'Windows'"
             and 'ParseFile' in s.get('run', '') for s in steps), 'native Windows PowerShell 5.1 parse missing')
    need(any(s.get('shell') == 'pwsh' and not s.get('if') and 'ParseFile' in s.get('run', '') for s in steps), 'native PowerShell 7 parse missing')
    commands = '\n'.join(s.get('run', '') for s in steps)
    for required in ('tests/help-rules-check.py', 'tests/test_windows_checks.py', 'tests/win-pin-mutate.py',
                     'tests/test_workflow_contract.py', 'tests/test_windows_bootstrap.py'):
        need(required in commands, f'missing contract check: {required}')
    for step in steps:
        if is_live_pin(step.get('run', '')):
            need(step.get('if') == RELEASE_GATE, 'live release pin check must be opt-in')
    need(any(is_live_pin(s.get('run', '')) for s in steps), 'release pin gate missing')
    signed = jobs.get('signed-install', {})
    need(signed.get('if') == RELEASE_GATE, 'real installation must be opt-in')
    need(signed.get('needs') == 'bootstrap-contract', 'real installation must depend on contract matrix')
    need(signed.get('runs-on') == 'windows-latest', 'NSIS installation requires Windows')
    signed_steps = signed.get('steps', [])
    need(len(signed_steps) > 1 and signed_steps[1].get('shell') == 'cmd'
         and 'tests/ps-balance.py' in signed_steps[1].get('run', ''), 'signed job precheck must precede PowerShell')
    for job in jobs.values():
        need(job.get('continue-on-error') in (None, 'false', False), 'job must propagate failures')
        for step in job.get('steps', []):
            need(step.get('continue-on-error') in (None, 'false', False), 'step must propagate failures')
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('workflow', nargs='?', type=Path, default=ROOT/'.github/workflows/windows-smoke.yml')
    args = parser.parse_args()
    try:
        errors = validate(load(args.workflow))
    except (OSError, ValueError, yaml.YAMLError, AttributeError, TypeError) as exc:
        errors = [str(exc)]
    for error in errors:
        print(f'FAIL: {error}', file=sys.stderr)
    if not errors:
        print('PASS: OS matrix / first precheck / native parsers / pin-free dispatch / release dependency')
    return int(bool(errors))

if __name__ == '__main__':
    sys.exit(main())
