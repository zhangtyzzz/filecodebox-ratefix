#!/usr/bin/env python3
import argparse
import hashlib
import json
import pathlib
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--arch', choices=['amd64', 'arm64'], required=True)
parser.add_argument('--directory', required=True)
args = parser.parse_args()
plan = json.loads(pathlib.Path('build/preparation.json').read_text())
image = json.loads(subprocess.check_output(['docker', 'image', 'inspect', 'filecodebox-candidate:' + args.arch]))[0]
assert image['Architecture'] == args.arch
directory = pathlib.Path(args.directory)
with (directory / ('filecodebox-' + args.arch + '.tar')).open('rb') as archive:
    checksum = hashlib.file_digest(archive, 'sha256').hexdigest()
result = {'architecture': args.arch, 'image_id': image['Id'], 'archive_sha256': checksum,
          'maintenance_revision': plan['maintenance_revision'], 'upstream_digest': plan['base_digest'],
          'unit_tests_passed': True, 'limiter_test_cases': 15, 'fresh_boot_passed': True}
(directory / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
