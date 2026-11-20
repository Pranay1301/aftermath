import json
import subprocess
import sys
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import pytest
from aftermath.lab import run_case
from aftermath.store import initialize, snapshot, fingerprint
from aftermath.worker import CUTS, POLICIES, execute, DEFAULT_PAYLOAD
from aftermath.provider import Provider, Conflict


@pytest.mark.parametrize('policy', POLICIES)
@pytest.mark.parametrize('contract', ['keyed','searchable','opaque'])
@pytest.mark.parametrize('cut', [None] + CUTS)
def test_crash_matrix(tmp_path, policy, contract, cut):
    row = run_case(tmp_path, policy, contract, cut)
    assert row['exit_code'] == (-9 if cut else 0)
    if policy == 'guarded':
        assert row['safe_outcome']
        assert not row['duplicate']
        assert not row['false_success']
        if contract == 'opaque' and cut in ['before_effect','during_effect','after_effect']:
            assert row['held']
        else:
            assert row['completed_once']
    elif contract == 'keyed':
        assert row['completed_once']
    elif policy == 'receipt':
        assert row['duplicate'] == (cut == 'after_effect')
    else:
        assert row['duplicate'] == (cut in [None,'after_effect','after_receipt'])


def test_same_id_different_payload_is_rejected(tmp_path):
    execute(tmp_path, 'guarded', 'keyed')
    assert execute(tmp_path, 'guarded', 'keyed', payload={'different':True})['status'] == 'rejected'
    assert len(snapshot(tmp_path)['effects']) == 1


def test_provider_rejects_key_payload_mismatch(tmp_path):
    initialize(tmp_path)
    p = Provider(tmp_path,'keyed')
    p.perform('x', {'a':1})
    with pytest.raises(Conflict):
        p.perform('x', {'a':2})
    assert len(snapshot(tmp_path)['effects']) == 1


def test_provider_contracts_have_different_semantics(tmp_path):
    initialize(tmp_path)
    p = Provider(tmp_path,'opaque')
    with pytest.raises(NotImplementedError):
        p.lookup('x',{})
    p.perform('x',{})
    p.perform('x',{})
    assert len(snapshot(tmp_path)['effects']) == 2


def test_concurrent_guarded_workers_share_one_receipt(tmp_path):
    initialize(tmp_path)
    cmd = [sys.executable,'-m','aftermath.worker','--root',str(tmp_path),
           '--policy','guarded','--contract','searchable']
    def launch(_):
        return subprocess.run(cmd,capture_output=True,text=True,timeout=15)
    with ThreadPoolExecutor(max_workers=8) as pool:
        runs = list(pool.map(launch,range(8)))
    assert all(p.returncode == 0 for p in runs)
    assert {json.loads(p.stdout)['receipt'] for p in runs} == {1}
    assert len(snapshot(tmp_path)['effects']) == 1


def test_reconciliation_rejects_ambiguous_multiple_matches(tmp_path):
    row = run_case(tmp_path,'guarded','opaque','after_effect')
    Provider(tmp_path,'searchable').perform('operation-42',DEFAULT_PAYLOAD)
    result = execute(tmp_path,'guarded','searchable')
    assert result['status'] == 'held'
    assert 'multiple' in result['reason']


def test_hold_is_sticky_without_evidence(tmp_path):
    run_case(tmp_path,'guarded','opaque','after_effect')
    for _ in range(3):
        assert execute(tmp_path,'guarded','opaque')['status'] == 'held'
    assert len(snapshot(tmp_path)['effects']) == 1


def test_uncommitted_provider_transaction_rolls_back(tmp_path):
    row=run_case(tmp_path,'guarded','opaque','during_effect')
    assert row['effect_count']==0
    assert row['held']  # no lookup means absence cannot be assumed by worker


def test_payload_hash_is_canonical():
    assert fingerprint({'a':1,'b':2}) == fingerprint({'b':2,'a':1})
    assert fingerprint({'a':1}) != fingerprint({'a':2})


def test_completed_event_ids_are_ordered(tmp_path):
    execute(tmp_path,'guarded','keyed')
    events=snapshot(tmp_path)['events']
    assert [e['seq'] for e in events] == list(range(1,len(events)+1))
    assert events[-1]['phase'] == 'done'
