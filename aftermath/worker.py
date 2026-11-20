"""Execute one already-authorized fictional operation, with real crash cuts.

Planner independence is deliberate: an LLM proposal does not establish
whether an external write completed. This layer owns execution only.
"""
import argparse
import fcntl
import json
import os
import signal
from pathlib import Path
from .provider import Provider, Conflict
from .store import connect, event, fingerprint, initialize

CUTS = ['before_intent', 'after_intent', 'before_effect', 'during_effect', 'after_effect', 'after_receipt']
POLICIES = ['blind', 'receipt', 'guarded']
DEFAULT_PAYLOAD = {'tool': 'dispatch_demo_parcel', 'parcel': 'DEMO-42', 'destination': 'fictional test bench'}


def cut(root, requested, here):
    if requested == here:
        event(root, 'crash', 'SIGKILL at ' + here)
        os.kill(os.getpid(), signal.SIGKILL)


def set_state(root, op, state, receipt=None, reason=None):
    with connect(Path(root) / 'ledger.sqlite') as db:
        db.execute('UPDATE operations SET state=?,receipt=?,reason=? WHERE id=?', (state, receipt, reason, op))


def execute(root, policy, contract, crash=None, op='operation-42', payload=None):
    if policy not in POLICIES or crash not in [None] + CUTS:
        raise ValueError('invalid policy or crash cut')
    payload = DEFAULT_PAYLOAD if payload is None else payload
    initialize(root)
    # One coordinator per operation set. This lock is process-scoped and
    # automatically released by the OS on SIGKILL; it does not lock provider DB.
    with open(Path(root) / 'worker.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _execute(root, policy, contract, crash, op, payload)


def _execute(root, policy, contract, crash, op, payload):
    provider = Provider(root, contract)
    fp = fingerprint(payload)
    event(root, 'start', f'{policy} policy / {contract} provider')
    cut(root, crash, 'before_intent')
    with connect(Path(root) / 'ledger.sqlite') as db:
        prior = db.execute('SELECT * FROM operations WHERE id=?', (op,)).fetchone()
        if prior and prior['fingerprint'] != fp:
            event(root, 'rejected', 'operation ID reused with different payload')
            return {'status': 'rejected', 'reason': 'payload conflict'}
        if not prior:
            db.execute('INSERT INTO operations VALUES(?,?,?,NULL,NULL)', (op, fp, 'prepared'))
    if policy != 'blind' and prior and prior['receipt'] is not None:
        event(root, 'cache_hit', f"local receipt {prior['receipt']}")
        return {'status': 'done', 'receipt': prior['receipt']}
    cut(root, crash, 'after_intent')
    receipt = None
    if policy == 'guarded' and prior and prior['state'] in {'dispatching', 'held'}:
        if contract == 'opaque':
            set_state(root, op, 'held', reason='provider outcome cannot be verified')
            event(root, 'held', 'Ambiguous prior dispatch. No retry and no success claim.')
            return {'status': 'held', 'reason': 'unknown external outcome'}
        if contract in {'searchable', 'eventual'}:
            try:
                receipt = provider.lookup(op, payload)
            except Conflict as exc:
                set_state(root, op, 'held', reason=str(exc))
                event(root, 'held', str(exc))
                return {'status': 'held', 'reason': str(exc)}
            event(root, 'reconcile', ('lagged lookup: ' if contract == 'eventual' else 'strongly consistent lookup: ') + (f'receipt {receipt}' if receipt else 'absent'))
            if contract == 'eventual' and receipt is None:
                set_state(root, op, 'held', reason='negative lagged lookup does not prove no effect')
                event(root, 'held', 'No fresh positive evidence. No retry and no success claim.')
                return {'status': 'held', 'reason': 'negative lagged lookup is inconclusive'}
        else:
            event(root, 'reconcile', 'retry with the same provider-enforced idempotency key')
    set_state(root, op, 'dispatching')
    event(root, 'intent', 'durable dispatch marker, before provider call')
    cut(root, crash, 'before_effect')
    if receipt is None:
        receipt = provider.perform(op, payload, before_commit=lambda: cut(root, crash, 'during_effect'))
        event(root, 'provider_return', f'provider returned receipt {receipt}')
    cut(root, crash, 'after_effect')
    set_state(root, op, 'done', receipt)
    event(root, 'receipt', f'durable local receipt {receipt}')
    cut(root, crash, 'after_receipt')
    event(root, 'done', 'confirmed from provider receipt')
    return {'status': 'done', 'receipt': receipt}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--policy', choices=POLICIES, required=True)
    parser.add_argument('--contract', choices=['keyed','searchable','opaque','eventual'], required=True)
    parser.add_argument('--crash', choices=CUTS)
    args = parser.parse_args()
    print(json.dumps(execute(args.root, args.policy, args.contract, args.crash)))


if __name__ == '__main__':
    main()
