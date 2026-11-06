#!/usr/bin/env python3
"""Fail before replacing a reviewed upstream module; no environment/data reads."""
import argparse
import hashlib
import json
import pathlib
import sys


def check(upstream, replacement, policy_path):
    policy = json.loads(pathlib.Path(policy_path).read_text())
    upstream_sha = hashlib.sha256(pathlib.Path(upstream).read_bytes()).hexdigest()
    replacement_sha = hashlib.sha256(pathlib.Path(replacement).read_bytes()).hexdigest()
    if replacement_sha != policy['patched_file_sha256']:
        raise ValueError('Maintenance patch differs from its reviewed hash; update policy and tests after review.')
    if upstream_sha not in policy['allowed_upstream_sha256']:
        raise ValueError(
            'UPSTREAM_MODULE_CHANGED: apps/base/dependencies.py no longer matches the reviewed upstream module. '
            'Do not overwrite upstream fixes. Compare its changes, adapt the patch, rerun tests, then update policy. '
            'This build stops before overlay; previously published latest is retained. '
            'Observed SHA256=' + upstream_sha
        )
    return {'status': 'PASS', 'upstream_module_sha256': upstream_sha, 'patch_sha256': replacement_sha}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', required=True)
    parser.add_argument('--replacement', required=True)
    parser.add_argument('--policy', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.upstream, args.replacement, args.policy)))
    except (OSError, ValueError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
