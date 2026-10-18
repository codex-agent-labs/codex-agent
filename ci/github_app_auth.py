"""Renewable, repository-scoped read credentials; never artifact authority.

The protected caller supplies the App identity and private key file. Existing
receipt, signature, source and transport verification remain mandatory.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
from threading import Lock
import time
import urllib.parse
import urllib.request

import reuse

REPOSITORY = 'codex-agent-labs/codex-agent'
REPOSITORY_ID = 1320780624
PERMISSIONS = {'actions': 'read', 'contents': 'read'}
ENVIRONMENT = ('CODEX_AGENT_READ_APP_ID', 'CODEX_AGENT_READ_INSTALLATION_ID',
               'CODEX_AGENT_READ_APP_KEY_FILE')
_lock = Lock()
_cached = None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _encoded(value):
    return base64.urlsafe_b64encode(value).rstrip(b'=')


def _mint(configuration):
    app, installation, key = configuration
    now = int(time.time())
    message = b'.'.join(_encoded(json.dumps(value, separators=(',', ':')).encode())
                        for value in ({'alg': 'RS256', 'typ': 'JWT'},
                                      {'iat': now - 60, 'exp': now + 540, 'iss': app}))
    signed = subprocess.run(['openssl', 'dgst', '-sha256', '-sign', key],
                            input=message, capture_output=True, check=False)
    if signed.returncode:
        raise ValueError('GitHub read App JWT signing failed')
    jwt = (message + b'.' + _encoded(signed.stdout)).decode('ascii')
    request = urllib.request.Request(
        f'https://api.github.com/app/installations/{installation}/access_tokens',
        data=json.dumps({'repository_ids': [REPOSITORY_ID], 'permissions': PERMISSIONS}).encode(),
        headers={'Authorization': f'Bearer {jwt}', 'Accept': 'application/vnd.github+json',
                 'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': 'application/json'})
    with urllib.request.build_opener(_NoRedirect()).open(request, timeout=60) as response:
        value = json.loads(response.read(1024 * 1024))
    permissions = value.get('permissions', {})
    repositories = value.get('repositories', [])
    if (permissions != {**PERMISSIONS, 'metadata': 'read'}
            or len(repositories) != 1 or repositories[0].get('id') != REPOSITORY_ID
            or repositories[0].get('full_name') != REPOSITORY):
        raise ValueError('GitHub read App token has unexpected repository or permission scope')
    token = value.get('token', '')
    if not isinstance(token, str) or re.fullmatch(r'[A-Za-z0-9_]{20,255}', token) is None:
        raise ValueError('GitHub read App returned an invalid token')
    expires = datetime.strptime(value['expires_at'], '%Y-%m-%dT%H:%M:%SZ').replace(
        tzinfo=timezone.utc).timestamp()
    if not time.time() + 300 < expires <= time.time() + 3660:
        raise ValueError('GitHub read App returned an invalid token lifetime')
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        print(f'::add-mask::{token}', flush=True)
    from runtime_reference_transport import count
    count('githubAppTokenRenewals')
    return token, expires


def token_for(url, fallback):
    """Replace only official same-repository Actions/Git reads, before expiry."""
    global _cached
    parsed = urllib.parse.urlsplit(url)
    prefix = f'/repos/{REPOSITORY}/'
    if (parsed.scheme != 'https' or parsed.netloc != 'api.github.com'
            or not parsed.path.startswith(prefix)
            or parsed.path[len(prefix):].split('/')[0] not in {'actions', 'git', 'contents', 'commits'}):
        return fallback
    configuration = tuple(os.environ.get(name, '') for name in ENVIRONMENT)
    if not any(configuration):
        return fallback
    app, installation, key = configuration
    if (not all(configuration) or not re.fullmatch(r'[1-9][0-9]{0,19}', app)
            or not re.fullmatch(r'[1-9][0-9]{0,19}', installation)
            or not Path(key).is_absolute() or Path(key).resolve(strict=True) != Path(key)
            or not Path(key).is_file()):
        raise ValueError('GitHub read App caller configuration is incomplete or invalid')
    if os.name != 'nt' and Path(key).stat().st_mode & 0o077:
        raise ValueError('GitHub read App private key must not be accessible to other users')
    from runtime_reference_transport import count
    count('githubAppReadRequests')
    with _lock:
        if _cached is None or _cached[0] != configuration or _cached[2] <= time.time() + 300:
            token, expires = _mint(configuration)
            _cached = configuration, token, expires
        return _cached[1]


def api_json(url, token):
    return reuse.api_json(url, token_for(url, token))


def paginated_items(url, key, token):
    # Renew at each page, not merely at the beginning of a long discovery call.
    result, page = [], 1
    separator = '&' if '?' in url else '?'
    while True:
        value = api_json(f'{url}{separator}per_page=100&page={page}', token).get(key)
        if not isinstance(value, list):
            raise ValueError(f'GitHub response is missing {key}')
        result.extend(value)
        if len(value) < 100:
            return result
        page += 1


def download_artifact(artifact, token):
    return reuse.download_artifact(artifact, token_for(artifact['archive_download_url'], token))


def download_artifact_to_file(artifact, token, destination, *, max_bytes):
    return reuse.download_artifact_to_file(artifact,
        token_for(artifact['archive_download_url'], token), destination, max_bytes=max_bytes)
