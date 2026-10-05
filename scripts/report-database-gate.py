"""Publish known check names and booleans, never endpoint/credential details."""
import json
import os
from pathlib import Path
import re
import sys


def report(mode, files):
    if mode not in ('native-baseline', 'azure-candidate') or len(files) != 2:
        raise ValueError()
    lines = [f'### Database gate: {mode}', '',
        'Native baseline checks the harness. Azure candidate results require offer readback and lifecycle evidence before selection.', '',
        '| Suite | Check | Result |', '| --- | --- | --- |']
    passed = True
    for index, filename in enumerate(files):
        item = json.loads(Path(filename).read_text())
        if item['backend'] != mode or item['backendSelected'] is not False or type(item['passed']) is not bool:
            raise ValueError()
        checks = item['checks']
        if not checks or any(not re.fullmatch('[a-zA-Z0-9_]+', k) or type(v) is not bool for k,v in checks.items()):
            raise ValueError()
        for key, value in sorted(checks.items()):
            lines.append(f"| {'.NET' if index == 0 else 'Payments'} | {key} | {'PASS' if value else 'FAIL'} |")
        passed = passed and item['passed'] and all(checks.values())
    lines.extend(['', 'No backend has been selected.', ''])
    return '\n'.join(lines), passed


if __name__ == '__main__':
    try:
        output, passed = report(sys.argv[1], sys.argv[2:])
        print(output)
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as file: file.write(output)
        raise SystemExit(0 if passed else 1)
    except (ValueError, KeyError, TypeError, OSError):
        raise SystemExit('Cannot produce a successful redacted database-gate report.')
