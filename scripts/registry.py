"""Small authenticated registry metadata reader; never logs bearer/password values."""
import base64
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request

ACCEPT = ','.join([
    'application/vnd.oci.image.index.v1+json',
    'application/vnd.docker.distribution.manifest.list.v2+json',
    'application/vnd.oci.image.manifest.v1+json',
    'application/vnd.docker.distribution.manifest.v2+json',
])


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != 'https':
            raise ValueError('Non-HTTPS registry redirect refused')
        result = super().redirect_request(req, fp, code, msg, headers, newurl)
        if urllib.parse.urlsplit(req.full_url).netloc != urllib.parse.urlsplit(newurl).netloc:
            result.remove_header('Authorization')
        return result


OPENER = urllib.request.build_opener(SafeRedirect())


def get(url, headers=None, max_bytes=2_000_000):
    request = urllib.request.Request(url, headers=headers or {})
    with OPENER.open(request, timeout=40) as response:
        data = response.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError('Registry metadata exceeded size limit')
        return data


def digest(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


class Registry:
    def __init__(self, registry, repository, username=None, password=None):
        if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]*/[a-z0-9][a-z0-9_.-]*', repository):
            raise ValueError('Invalid repository')
        if registry == 'docker.io':
            self.base = 'https://registry-1.docker.io/v2/' + repository
            auth = 'https://auth.docker.io/token?'
            service = 'registry.docker.io'
        elif registry == 'ghcr.io':
            self.base = 'https://ghcr.io/v2/' + repository
            auth = 'https://ghcr.io/token?'
            service = 'ghcr.io'
        else:
            raise ValueError('Registry is not allowed')
        headers = {}
        if username and password:
            encoded = base64.b64encode((username + ':' + password).encode()).decode()
            headers['Authorization'] = 'Basic ' + encoded
        auth += urllib.parse.urlencode({'service': service, 'scope': 'repository:' + repository + ':pull'})
        token = json.loads(get(auth, headers))['token']
        self.headers = {'Authorization': 'Bearer ' + token, 'Accept': ACCEPT}

    def manifest(self, reference):
        if not re.fullmatch(r'(sha256:[a-f0-9]{64}|[a-zA-Z0-9_.-]+)', reference):
            raise ValueError('Invalid manifest reference')
        data = get(self.base + '/manifests/' + reference, self.headers)
        if reference.startswith('sha256:') and digest(data) != reference:
            raise ValueError('Manifest digest mismatch')
        return digest(data), json.loads(data)

    def config(self, reference):
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', reference):
            raise ValueError('Invalid blob digest')
        data = get(self.base + '/blobs/' + reference, self.headers)
        if digest(data) != reference:
            raise ValueError('Config digest mismatch')
        return json.loads(data)

    def platforms(self, manifest):
        selected = {}
        if 'manifests' not in manifest:
            raise ValueError('Expected a multi-platform image index')
        for architecture in ['amd64', 'arm64']:
            matches = [m for m in manifest['manifests']
                       if m.get('platform', {}).get('os') == 'linux'
                       and m['platform'].get('architecture') == architecture]
            if len(matches) != 1:
                raise ValueError('Expected one Linux manifest for ' + architecture)
            selected[architecture] = matches[0]['digest']
        return selected
