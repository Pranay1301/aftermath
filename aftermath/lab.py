"""Run a fair fixture matrix: fresh independent state for every policy/cut.

The first worker is a real subprocess. At the selected cut it SIGKILLs
itself. A new process then resumes against the same two databases.
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from .store import initialize, snapshot
from .worker import CUTS, POLICIES


def run_case(root, policy, contract, crash):
    initialize(root)
    command = [sys.executable, '-m', 'aftermath.worker', '--root', str(root), '--policy', policy, '--contract', contract]
    first = subprocess.run(command + (['--crash', crash] if crash else []), capture_output=True, text=True, timeout=10)
    expected = -9 if crash else 0
    if first.returncode != expected:
        raise RuntimeError(f'first worker exit {first.returncode}, expected {expected}: {first.stderr}')
    second = subprocess.run(command, capture_output=True, text=True, timeout=10)
    if second.returncode:
        raise RuntimeError(second.stderr)
    recovery = json.loads(second.stdout)
    state = snapshot(root)
    count = len(state['effects'])
    success = recovery['status'] == 'done' and count == 1
    held = recovery['status'] == 'held'
    return {'policy': policy, 'contract': contract, 'cut': crash or 'none',
            'exit_code': first.returncode, 'recovery': recovery, 'effect_count': count,
            'duplicate': count > 1, 'completed_once': success, 'held': held,
            'false_success': recovery['status'] == 'done' and count != 1,
            'safe_outcome': success or (held and count <= 1), **state}


def matrix():
    results = []
    for contract in ['keyed', 'searchable', 'opaque']:
        for crash in [None] + CUTS:
            for policy in POLICIES:
                with tempfile.TemporaryDirectory(prefix='aftermath-') as root:
                    results.append(run_case(root, policy, contract, crash))
    totals = {}
    for policy in POLICIES:
        rows = [r for r in results if r['policy'] == policy]
        totals[policy] = {k: sum(r[k] for r in rows) for k in ['completed_once','duplicate','held','false_success','safe_outcome']}
        totals[policy]['cases'] = len(rows)
    return {'schema_version': 1, 'kind': 'executed deterministic crash matrix',
            'model_calls': 0, 'external_calls': 0, 'cuts': ['none'] + CUTS,
            'totals': totals, 'results': results}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', default='evidence/matrix.json')
    args = p.parse_args()
    result = matrix()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2))
    print(json.dumps(result['totals'], indent=2))


if __name__ == '__main__':
    main()
