import json
import pytest
from src import qa_application_publisher as publisher
from src.rollover import Target
TARGET = Target(2026, 6)


@pytest.fixture
def harness(tmp_path, monkeypatch):
    source = tmp_path / 'source'; source.mkdir()
    checkout = tmp_path / 'checkout'; checkout.mkdir()
    (source / publisher.FILES[-1]).write_text(json.dumps({'availability_certificate': {'schema_version': 2}}))
    import src.rollover as rollover
    monkeypatch.setattr(rollover, "validate_target", lambda *args: None)
    monkeypatch.setattr(rollover, "verify_readers", lambda *args: {})
    calls = []
    def git(path, *args):
        calls.append(args)
        return {('remote','get-url','origin'):publisher.REMOTE,
                ('branch','--show-current'):publisher.BRANCH,
                ('status','--porcelain'):'',
                ('rev-parse','HEAD'):'a'*40,
                ('ls-remote','origin','refs/heads/'+publisher.BRANCH):'a'*40+'\trefs/heads/'+publisher.BRANCH}.get(args, '')
    monkeypatch.setattr(publisher, 'git', git)
    def stage(src, dest, observation, matches):
        dest.mkdir()
        for filename in publisher.FILES:
            (dest / filename).write_bytes(b'validated-fixture')
        return {'record_counts': {'four': 1, 'six': 1}}
    monkeypatch.setattr(publisher, 'stage_context', stage)
    def manifest(dest, revision):
        (dest / 'publication_manifest.json').write_text('{}')
        return {'revision': revision}
    monkeypatch.setattr(publisher, 'write_manifest', manifest)
    return source, checkout, calls, git


def test_dry_run_never_mutates_checkout(harness):
    source, checkout, calls, _ = harness
    assert publisher.publish(source, checkout, {}, target=TARGET)['status'] == 'validated-not-published'
    assert list(checkout.iterdir()) == []
    assert not any(c[0] in {'add','commit','push'} for c in calls)


def test_two_assets_then_pointer_one_nonforce_push(harness):
    source, checkout, calls, _ = harness
    assert publisher.publish(source, checkout, {}, push=True, target=TARGET)['status'] == 'published'
    assert len([c for c in calls if c[0]=='commit']) == 2
    assert [c for c in calls if c[0]=='push'] == [('push','origin','HEAD:refs/heads/qa-app-data')]
    assert all((checkout/'data/processed'/f).exists() for f in publisher.FILES)


@pytest.mark.parametrize('failure', ['validation', 'manifest', 'concurrent'])
def test_failure_before_push_keeps_remote_last_good(harness, monkeypatch, failure):
    source, checkout, calls, original = harness
    def fail(*args):
        raise ValueError('injected failure')
    if failure == 'validation':
        monkeypatch.setattr(publisher, 'stage_context', fail)
    elif failure == 'manifest':
        monkeypatch.setattr(publisher, 'write_manifest', fail)
    else:
        def git(path, *args):
            result = original(path, *args)
            return 'b'*40+'\trefs/heads/qa-app-data' if args[0]=='ls-remote' else result
        monkeypatch.setattr(publisher, 'git', git)
    with pytest.raises(ValueError):
        publisher.publish(source, checkout, {}, push=True, target=TARGET)
    assert not any(c[0]=='push' for c in calls)


@pytest.mark.parametrize('metadata', [{'publication_allowed':False}, {}])
def test_incomplete_baseline_cannot_publish(harness, metadata):
    source, checkout, calls, _ = harness
    (source/publisher.FILES[-1]).write_text(json.dumps(metadata))
    with pytest.raises(ValueError):
        publisher.publish(source, checkout, {}, push=True, target=TARGET)
    assert not any(c[0]=='commit' for c in calls)


def test_production_remote_rejected(harness, monkeypatch):
    source, checkout, calls, original = harness
    def git(path, *args):
        result = original(path, *args)
        return 'https://github.com/breckengalliher/fantasy-football-decision-lab.git' if args[0]=='remote' else result
    monkeypatch.setattr(publisher, 'git', git)
    with pytest.raises(ValueError, match='isolated'):
        publisher.publish(source, checkout, {}, push=True, target=TARGET)
    assert not (checkout/'data').exists()
