"""QA-only bridge from guarded observations to the real atomic app publisher.

Requires a complete, same-week approved snapshot. Does not rebuild projections,
certify availability, or permit publishing review-only numerical experiments.
Use a disposable checkout on qa-app-data; a failed push never force-updates it.
"""
import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from src.publication import FILES, write_manifest
from src.qa_provider_publication import stage_context

REMOTE = 'https://github.com/breckengalliher/sdl-release-qa-scheduler.git'
BRANCH = 'qa-app-data'


def git(checkout, *args):
    return subprocess.check_output(['git', *args], cwd=checkout,
                                   stderr=subprocess.PIPE, timeout=120).decode().strip()


def publish(source, checkout, observation, matches=(), push=False, *, target):
    checkout = Path(checkout).resolve()
    if (git(checkout, 'remote', 'get-url', 'origin') != REMOTE
            or git(checkout, 'branch', '--show-current') != BRANCH):
        raise ValueError('Only the isolated QA application-data branch is allowed')
    if git(checkout, 'status', '--porcelain'):
        raise ValueError('Use a clean disposable checkout; preserve pending changes')
    metadata = json.loads((Path(source) / FILES[-1]).read_text())
    if metadata.get('publication_allowed') is False:
        raise ValueError('Review-only projections cannot be published')
    # Never promote provider observations to official availability. Require the
    # existing reviewed certificate (including its globally restricted policy).
    if not metadata.get('availability_certificate'):
        raise ValueError('A reviewed availability certificate or restricted policy is required')
    previous = git(checkout, 'rev-parse', 'HEAD')
    with tempfile.TemporaryDirectory(prefix='sdl-qa-publish-') as temporary:
        staged = Path(temporary) / 'snapshot'
        validation = stage_context(source, staged, observation, matches)
        from src.rollover import validate_target
        validate_target(staged, target)
        receipt = {'status': 'validated-not-published', 'previous_revision': previous,
                   'record_counts': validation['record_counts'], 'production_modified': False}
        if not push:
            return receipt
        # Check remote before mutating the disposable checkout. The final push
        # is a non-force compare against ancestry, rejecting competing writers.
        remote = git(checkout, 'ls-remote', 'origin', 'refs/heads/' + BRANCH)
        if not remote or remote.split()[0] != previous:
            raise ValueError('QA publication advanced; restart from its latest snapshot')
        destination = checkout / 'data' / 'processed'
        destination.mkdir(parents=True, exist_ok=True)
        for filename in FILES:
            shutil.copy2(staged / filename, destination / filename)
        git(checkout, 'add', '-f', *['data/processed/' + f for f in FILES])
        git(checkout, 'commit', '-m', 'QA validated scoring assets [skip ci]')
        revision = git(checkout, 'rev-parse', 'HEAD')
        manifest = write_manifest(destination, revision)
        from src.rollover import verify_readers
        verify_readers(destination, manifest, target)
        git(checkout, 'add', '-f', 'data/processed/publication_manifest.json')
        git(checkout, 'commit', '-m', 'QA atomic scoring publication pointer [skip ci]')
        git(checkout, 'push', 'origin', 'HEAD:refs/heads/' + BRANCH)
        return dict(receipt, status='published', asset_revision=revision,
                    pointer_revision=git(checkout, 'rev-parse', 'HEAD'), manifest=manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--checkout', required=True)
    parser.add_argument('--observation', required=True)
    parser.add_argument('--matches', required=True)
    parser.add_argument('--receipt', required=True)
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--season', type=int, required=True)
    parser.add_argument('--week', type=int, required=True)
    args = parser.parse_args()
    try:
        from src.rollover import Target
        result = publish(args.source, args.checkout,
                         json.loads(Path(args.observation).read_text()),
                         json.loads(Path(args.matches).read_text()), args.publish,
                         target=Target(args.season, args.week))
    except Exception as error:
        # No request URLs, tokens, subprocess stderr, or credential material.
        Path(args.receipt).write_text(json.dumps({'status': 'failed',
            'error_type': type(error).__name__, 'production_modified': False}))
        raise SystemExit('QA publication failed; inspect validated inputs and checkout') from None
    Path(args.receipt).write_text(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
