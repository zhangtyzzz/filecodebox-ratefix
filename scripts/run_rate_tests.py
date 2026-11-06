#!/usr/bin/env python3
"""Run the real limiter suite and refuse accidental zero/missing test discovery."""
import argparse
import json
import pathlib
import unittest

parser = argparse.ArgumentParser()
parser.add_argument('--directory', required=True)
parser.add_argument('--policy', required=True)
args = parser.parse_args()
policy = json.loads(pathlib.Path(args.policy).read_text())
suite = unittest.defaultTestLoader.discover(args.directory, pattern='test_*.py')
count = suite.countTestCases()
if count != policy['expected_test_count']:
    raise SystemExit('Expected %d limiter/proxy tests, discovered %d; review the suite and policy together.'
                     % (policy['expected_test_count'], count))
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
