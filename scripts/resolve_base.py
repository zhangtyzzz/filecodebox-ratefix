#!/usr/bin/env python3
"""Resolve one latest input and skip a scheduled rebuild when it is unchanged."""
import argparse
import json
import os
import pathlib
import re
import urllib.error

from registry import Registry

LABELS = ['org.opencontainers.image.version', 'org.opencontainers.image.revision',
          'org.opencontainers.image.filecodebox.frontend-2024-revision',
          'org.opencontainers.image.filecodebox.frontend-2023-revision']


def resolve(revision, image_repository):
    if not re.fullmatch(r'[a-f0-9]{40}', revision):
        raise ValueError('Expected full maintenance commit SHA')
    registry = Registry('docker.io', 'lanol/filecodebox')
    base_digest, index = registry.manifest('latest')
    platforms = registry.platforms(index)
    configs = {}
    metadata = []
    for architecture, manifest_digest in platforms.items():
        _, manifest = registry.manifest(manifest_digest)
        config = registry.config(manifest['config']['digest'])
        if config.get('architecture') != architecture or config.get('os') != 'linux':
            raise ValueError('Platform/config mismatch')
        labels = config.get('config', {}).get('Labels') or {}
        source = {name: labels.get(name) for name in LABELS}
        for key in LABELS[1:]:
            if not isinstance(source[key], str) or not re.fullmatch(r'[a-f0-9]{40}', source[key]):
                raise ValueError('Upstream lacks an exact source commit for ' + key)
        configs[architecture] = {'manifest': manifest_digest, 'config': manifest['config']['digest']}
        metadata.append(source)
    if metadata[0] != metadata[1]:
        raise ValueError('Upstream architectures describe different source revisions')
    build_needed = True
    reason = 'First publication or an upstream/maintenance revision changed'
    try:
        current = Registry('ghcr.io', image_repository, os.environ.get('GITHUB_ACTOR'),
                           os.environ.get('GITHUB_TOKEN'))
        _, own_index = current.manifest('latest')
        own_platforms = current.platforms(own_index)
        match = []
        for manifest_digest in own_platforms.values():
            _, manifest = current.manifest(manifest_digest)
            labels = current.config(manifest['config']['digest']).get('config', {}).get('Labels') or {}
            match.append(labels.get('io.filecodebox.maintenance.base.digest') == base_digest
                         and labels.get('org.opencontainers.image.revision') == revision)
        if all(match):
            build_needed = False
            reason = 'Published latest already has this upstream digest and maintenance commit'
    except urllib.error.HTTPError as error:
        if error.code not in [401, 403, 404]:
            raise
        reason = 'No readable maintenance latest yet; build and validate before attempting publication'
    return {'schema': 1, 'base_image': 'lanol/filecodebox@' + base_digest,
            'base_digest': base_digest, 'platforms': configs, 'upstream_labels': metadata[0],
            'maintenance_revision': revision, 'image_repository': image_repository,
            'build_needed': build_needed, 'reason': reason}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--image-repository', required=True)
    parser.add_argument('--output', default='build/preparation.json')
    parser.add_argument('--github-output')
    args = parser.parse_args()
    result = resolve(args.revision, args.image_repository.lower())
    path = pathlib.Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + '\n')
    if args.github_output:
        with open(args.github_output, 'a') as output:
            output.write('build_needed=' + str(result['build_needed']).lower() + '\n')
            output.write('base_image=' + result['base_image'] + '\n')
            output.write('base_digest=' + result['base_digest'] + '\n')
            output.write('upstream_revision=' + result['upstream_labels']['org.opencontainers.image.revision'] + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
