#!/usr/bin/env python3
"""Include corresponding public source archives for the vendor-labelled commits."""
import argparse
import hashlib
import json
import pathlib
import re
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preparation', default='build/preparation.json')
    parser.add_argument('--output', default='build/source')
    args = parser.parse_args()
    info = json.loads(pathlib.Path(args.preparation).read_text())
    out = pathlib.Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    labels = info['upstream_labels']
    sources = [
        ('FileCodeBox', 'org.opencontainers.image.revision'),
        ('FileCodeBoxFronted', 'org.opencontainers.image.filecodebox.frontend-2024-revision'),
        ('FileCodeBoxFronted2023', 'org.opencontainers.image.filecodebox.frontend-2023-revision'),
    ]
    records = []
    for repository, key in sources:
        revision = labels[key]
        if not re.fullmatch(r'[a-f0-9]{40}', revision):
            raise ValueError('Source revision is not a commit SHA')
        url = 'https://codeload.github.com/vastsa/' + repository + '/tar.gz/' + revision
        with urllib.request.urlopen(url, timeout=60) as response:
            body = response.read(50_000_001)
        if len(body) > 50_000_000 or not body.startswith(b'\x1f\x8b'):
            raise ValueError('Unexpected source archive')
        filename = repository + '-' + revision + '.tar.gz'
        (out / filename).write_bytes(body)
        records.append({'repository': 'vastsa/' + repository, 'revision': revision,
                        'url': url, 'file': filename, 'sha256': hashlib.sha256(body).hexdigest()})
    (out / 'sources.json').write_text(json.dumps(records, indent=2) + '\n')
    print(json.dumps({'source_archives_included': len(records)}))


if __name__ == '__main__':
    main()
