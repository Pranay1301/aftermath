"""Lagged outcome-query experiment. No network or real provider.

Run a real crash per cell, inspect recovery before/after an explicit fake
provider replication barrier. The barrier is not a sleep, poll or worker
assumption. Old 63-case evidence remains a separate historical artifact.
"""
import argparse
import json
import tempfile
from pathlib import Path
from .lab import run_case
from .provider import Provider
from .store import snapshot
from .worker import CUTS, POLICIES, execute


def case(root, policy, cut):
    before = run_case(root, policy, 'eventual', cut)
    Provider(root, 'eventual').reveal()
    recovered = execute(root, policy, 'eventual')
    state = snapshot(root)
    count = len(state['effects'])
    return {'policy': policy, 'cut': cut or 'none',
            'before_visibility': before,
            'after_visibility': {'recovery': recovered, 'effect_count': count,
                                 'duplicate': count > 1,
                                 'held': recovered['status'] == 'held',
                                 'completed_once': recovered['status'] == 'done' and count == 1,
                                 **state}}


def matrix():
    results = []
    for cut in [None] + CUTS:
        for policy in POLICIES:
            with tempfile.TemporaryDirectory(prefix='aftermath-lag-') as root:
                results.append(case(root, policy, cut))
    totals = {}
    for policy in POLICIES:
        rows = [r for r in results if r['policy'] == policy]
        totals[policy] = {
            phase: {k: sum(row[phase][k] for row in rows)
                    for k in ['completed_once', 'duplicate', 'held']}
            for phase in ['before_visibility', 'after_visibility']}
    return {'schema_version': 1, 'kind': 'executed lagged-query crash supplement',
            'model_calls': 0, 'external_calls': 0,
            'assumption': 'Lookup can hide committed effects until an explicit fixture replication barrier. Positive visible receipts are durable and exact; no pending remote requests exist in this fixture.',
            'totals': totals, 'results': results}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', default='evidence/eventual-matrix.json')
    args = p.parse_args()
    result = matrix()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2))
    print(json.dumps(result['totals'], indent=2))


if __name__ == '__main__':
    main()
