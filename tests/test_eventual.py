import pytest
from aftermath.eventual_lab import case
from aftermath.lab import run_case
from aftermath.provider import Provider, Conflict
from aftermath.store import initialize, snapshot
from aftermath.worker import CUTS, POLICIES, execute, DEFAULT_PAYLOAD


@pytest.mark.parametrize('policy', POLICIES)
@pytest.mark.parametrize('cut', [None] + CUTS)
def test_eventual_crash_matrix(tmp_path, policy, cut):
    row = case(tmp_path, policy, cut)
    before, after = row['before_visibility'], row['after_visibility']
    assert before['exit_code'] == (-9 if cut else 0)
    if policy == 'guarded':
        assert not before['duplicate'] and not after['duplicate']
        if cut in ['before_effect', 'during_effect', 'after_effect']:
            assert before['held']
        else:
            assert before['completed_once']
        if cut in ['before_effect', 'during_effect']:
            assert after['held'] and after['effect_count'] == 0
        else:
            assert after['completed_once']
    elif policy == 'receipt':
        assert before['duplicate'] == (cut == 'after_effect')
        assert after['duplicate'] == (cut == 'after_effect')
    else:
        assert after['duplicate']  # one more blind redelivery after replication


def test_committed_effect_hidden_until_barrier(tmp_path):
    initialize(tmp_path)
    p = Provider(tmp_path, 'eventual')
    receipt = p.perform('op', {'a': 1})
    assert len(snapshot(tmp_path)['effects']) == 1
    assert p.lookup('op', {'a': 1}) is None
    p.reveal()
    assert p.lookup('op', {'a': 1}) == receipt


def test_repeated_negative_query_never_dispatches_again(tmp_path):
    run_case(tmp_path, 'guarded', 'eventual', 'after_effect')
    for _ in range(4):
        assert execute(tmp_path, 'guarded', 'eventual')['status'] == 'held'
    assert len(snapshot(tmp_path)['effects']) == 1


def test_revealed_receipt_resolves_hold(tmp_path):
    run_case(tmp_path, 'guarded', 'eventual', 'after_effect')
    Provider(tmp_path, 'eventual').reveal()
    assert execute(tmp_path, 'guarded', 'eventual')['status'] == 'done'
    assert len(snapshot(tmp_path)['effects']) == 1


def test_barrier_is_not_permission_to_retry_absent_effect(tmp_path):
    run_case(tmp_path, 'guarded', 'eventual', 'during_effect')
    Provider(tmp_path, 'eventual').reveal()
    assert execute(tmp_path, 'guarded', 'eventual')['status'] == 'held'
    assert not snapshot(tmp_path)['effects']


def test_multiple_visible_matches_hold(tmp_path):
    run_case(tmp_path, 'guarded', 'eventual', 'after_effect')
    p = Provider(tmp_path, 'eventual')
    p.perform('operation-42', DEFAULT_PAYLOAD)
    p.reveal()
    r = execute(tmp_path, 'guarded', 'eventual')
    assert r['status'] == 'held' and 'multiple' in r['reason']


def test_visible_wrong_payload_rejected(tmp_path):
    initialize(tmp_path)
    p = Provider(tmp_path, 'eventual')
    p.perform('op', {'a': 1})
    p.reveal()
    with pytest.raises(Conflict):
        p.lookup('op', {'a': 2})


def test_reveal_idempotent(tmp_path):
    initialize(tmp_path)
    p = Provider(tmp_path, 'eventual')
    p.perform('op', {})
    p.reveal(); p.reveal()
    assert p.lookup('op', {}) == 1


def test_barrier_does_not_reveal_later_effects(tmp_path):
    initialize(tmp_path)
    p = Provider(tmp_path, 'eventual')
    p.reveal()
    p.perform('op', {})
    assert p.lookup('op', {}) is None
