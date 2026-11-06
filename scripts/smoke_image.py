#!/usr/bin/env python3
"""Fresh, network-isolated boot check. No private data, credentials or host ports."""
import argparse
import json
import subprocess
import time
import uuid


def run(args, timeout=20):
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if p.returncode:
        raise RuntimeError('Container smoke-test command failed')
    return p.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image')
    args = parser.parse_args()
    name = 'filecodebox-ci-' + uuid.uuid4().hex[:12]
    created = False
    try:
        run(['docker', 'create', '--name', name, '--network', 'none', '--memory', '512m',
             '--cpus', '1', '--read-only', '--tmpfs', '/app/data:rw,size=32m',
             '--tmpfs', '/tmp:rw,size=32m', '-e', 'PYTHONDONTWRITEBYTECODE=1', args.image])
        created = True
        run(['docker', 'start', name])
        probe = '''import urllib.request,json
out={}
for path in ['/', '/health']:
 r=urllib.request.urlopen('http://127.0.0.1:12345'+path,timeout=3)
 assert r.status==200
 out[path]=r.status
 r.read()
print(json.dumps(out))
'''
        for _ in range(30):
            state = json.loads(run(['docker', 'inspect', name]))[0]
            if not state['State']['Running']:
                raise RuntimeError('Fresh test container stopped before readiness')
            try:
                result = json.loads(run(['docker', 'exec', name, 'python', '-c', probe]))
                assert state['RestartCount'] == 0
                print(json.dumps({'fresh_boot': 'PASS', 'http': result, 'published_ports': [],
                                  'network': 'none', 'real_upload_or_external_storage_tested': False}))
                return
            except RuntimeError:
                time.sleep(2)
        raise RuntimeError('Fresh HTTP readiness timed out')
    finally:
        if created:
            # Synthetic empty instance only; no production volumes or images removed.
            run(['docker', 'rm', '-f', name])


if __name__ == '__main__':
    main()
