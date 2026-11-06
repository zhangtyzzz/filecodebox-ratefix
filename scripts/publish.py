#!/usr/bin/env python3
"""Publish the two already-tested images; latest is the final mutation."""
import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess

from registry import Registry


def run(args):
    process = subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return process.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', default='build/candidates')
    parser.add_argument('--preparation', default='build/preparation.json')
    args = parser.parse_args()
    plan = json.loads(pathlib.Path(args.preparation).read_text())
    repository = plan['image_repository']
    if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]*/[a-z0-9][a-z0-9_.-]*', repository):
        raise ValueError('Invalid image repository')
    run_id = os.environ['GITHUB_RUN_ID']
    attempt = os.environ['GITHUB_RUN_ATTEMPT']
    if not run_id.isdigit() or not attempt.isdigit():
        raise ValueError('Invalid workflow run identifier')
    base = 'ghcr.io/' + repository
    registry = None  # The package may not exist before the first architecture push.
    expected_configs = {}
    # Validate both artifacts before pushing either. No rebuilding occurs here.
    for arch in ['amd64', 'arm64']:
        folder = pathlib.Path(args.artifacts) / ('candidate-' + arch)
        result = json.loads((folder / 'result.json').read_text())
        archive = folder / ('filecodebox-' + arch + '.tar')
        if result['architecture'] != arch or result['maintenance_revision'] != plan['maintenance_revision']:
            raise ValueError('Artifact provenance fields do not match this preparation')
        if result['upstream_digest'] != plan['base_digest'] or not result['unit_tests_passed'] or not result['fresh_boot_passed']:
            raise ValueError('Artifact did not pass all required checks')
        with archive.open('rb') as source:
            checksum = hashlib.file_digest(source, 'sha256').hexdigest()
        if checksum != result['archive_sha256']:
            raise ValueError('Image archive checksum mismatch')
        run(['docker', 'load', '--input', str(archive)])
        image = json.loads(run(['docker', 'image', 'inspect', 'filecodebox-candidate:' + arch]))[0]
        if image['Id'] != result['image_id'] or image['Architecture'] != arch:
            raise ValueError('Loaded image differs from the tested image')
        labels = image['Config']['Labels']
        if labels['io.filecodebox.maintenance.base.digest'] != plan['base_digest']:
            raise ValueError('Loaded image has the wrong upstream digest')
        if labels['org.opencontainers.image.revision'] != plan['maintenance_revision']:
            raise ValueError('Loaded image has the wrong maintenance revision')
        expected_configs[arch] = image['Id']
    manifests = {}
    for arch in ['amd64', 'arm64']:
        tag = 'build-' + run_id + '-' + attempt + '-' + arch
        run(['docker', 'tag', 'filecodebox-candidate:' + arch, base + ':' + tag])
        run(['docker', 'push', base + ':' + tag])
        if registry is None:
            registry = Registry('ghcr.io', repository, os.environ['GITHUB_ACTOR'], os.environ['GHCR_TOKEN'])
        digest, manifest = registry.manifest(tag)
        if manifest.get('config', {}).get('digest') != expected_configs[arch]:
            raise ValueError('Published architecture differs from tested image')
        manifests[arch] = digest
    candidate_tag = 'build-' + run_id + '-' + attempt
    run(['docker', 'buildx', 'imagetools', 'create', '--tag', base + ':' + candidate_tag]
        + [base + '@' + manifests[arch] for arch in ['amd64', 'arm64']])
    candidate_digest, index = registry.manifest(candidate_tag)
    selected = registry.platforms(index)
    if selected != manifests:
        raise ValueError('Multi-platform index does not exactly match the two tested image manifests')
    if len(index['manifests']) != 2:
        raise ValueError('Unexpected additional platforms in candidate index')
    summary = {'candidate': base + '@' + candidate_digest, 'platforms': manifests,
               'tested_image_configs': expected_configs, 'upstream_digest': plan['base_digest'],
               'maintenance_revision': plan['maintenance_revision'], 'latest_promotion_ready': True}
    pathlib.Path('build/publication-ready.json').write_text(json.dumps(summary, indent=2) + '\n')
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as output:
        output.write('Both native platforms passed all 15 limiter/proxy tests and a fresh isolated HTTP boot.\n\n')
        output.write('Candidate: `' + base + '@' + candidate_digest + '`\n\n')
        output.write('Upstream input: `' + plan['base_image'] + '`\n\n')
        output.write('Promoting this already-tested index to `latest` as the final registry mutation.\n')
    # All build/test/manifest validation is complete. Never push latest earlier.
    run(['docker', 'buildx', 'imagetools', 'create', '--tag', base + ':latest', base + '@' + candidate_digest])
    print(json.dumps({'status': 'LATEST_PUBLISHED', 'image': base + ':latest',
                      'tested_candidate_digest': candidate_digest}))


if __name__ == '__main__':
    main()
