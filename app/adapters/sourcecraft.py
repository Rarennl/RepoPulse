"""Read-only adapter for the checked-in official Swagger, fetched 2026-09-16."""
import hashlib
import json
import random
import re
import time
from urllib.parse import quote
import httpx
from ..config import API_BASE

class SourceError(Exception):
    def __init__(self, reason, retryable=False):
        super().__init__(reason)
        self.reason, self.retryable = reason, retryable

SLUG = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$')

def validate_slug(slug):
    if len(slug.split('/')) != 2 or not all(SLUG.fullmatch(s) for s in slug.split('/')):
        raise ValueError('Ожидается organization/repository')
    return slug

class SourceCraft:
    def __init__(self, token, cache=None, transport=None, *, service='platform', auth_scheme='Bearer'):
        self.token, self.cache = token, cache
        base = {'platform': API_BASE, 'appsec': 'https://appsec.sourcecraft.tech'}[service]
        self.namespace = hashlib.sha256((base + ':' + token).encode()).hexdigest()
        self.client = httpx.Client(base_url=base, timeout=20, follow_redirects=False,
                                   headers={'Authorization': f'{auth_scheme} {token}'} if token else {}, transport=transport)
    def close(self):
        self.client.close()
    def __enter__(self): return self
    def __exit__(self, *args): self.close()

    def get(self, path, params=None, cache=True):
        if not path.startswith('/') or path.startswith('//') or '..' in path:
            raise ValueError('Invalid API path')
        key = 'source:' + self.namespace + ':' + hashlib.sha256(
            json.dumps([path, params], sort_keys=True).encode()).hexdigest()
        # Only metadata and public calls may be cached by caller. No source bodies.
        if self.cache and cache:
            found = self.cache.get(key)
            if found: return json.loads(found)
        for attempt in range(4):
            if self.cache:
                # Shared 2 req/s per credential across all replicas.
                while not self.cache.set('rate:' + self.namespace, '1', nx=True, px=500):
                    time.sleep(0.1)
            try:
                with self.client.stream('GET', path, params=params) as response:
                    status = response.status_code
                    if status in (401, 403, 404):
                        raise SourceError({401:'unauthorized',403:'forbidden',404:'not_found'}[status])
                    if status == 429 or status >= 500:
                        retry = response.headers.get('retry-after', '')
                        delay = min(float(retry), 60) if retry.isdigit() else 2**attempt + random.random()
                        if attempt == 3: raise SourceError('upstream_unavailable', True)
                        time.sleep(delay)
                        continue
                    if status != 200: raise SourceError('upstream_http_' + str(status))
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > 8 * 1024 * 1024: raise SourceError('response_size_limit')
                    result = json.loads(data)
                    if not isinstance(result, dict): raise SourceError('schema_mismatch')
                    if self.cache and cache:
                        self.cache.setex(key, 300, json.dumps(result))
                    return result
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == 3: raise SourceError('upstream_timeout', True) from None
                time.sleep(2**attempt + random.random())
            except (ValueError, json.JSONDecodeError):
                raise SourceError('invalid_upstream_json') from None
        raise SourceError('upstream_unavailable', True)

    def pages(self, path, field, params=None, cache=False):
        params = dict(params or {}, page_size=100)
        previous = set()
        while True:
            data = self.get(path, params, cache=cache)
            rows = data.get(field, [])
            if not isinstance(rows, list): raise SourceError('schema_mismatch')
            for item in rows:
                if not isinstance(item, dict): raise SourceError('schema_mismatch')
                yield item
            token = data.get('next_page_token')
            if not token: break
            if token in previous: raise SourceError('pagination_cycle')
            previous.add(token)
            if len(previous) > 10000: raise SourceError('pagination_budget')
            params['page_token'] = token

    def repository(self, slug):
        return self.get('/repos/' + validate_slug(slug), cache=False)
    def repositories(self, org):
        if not SLUG.fullmatch(org): raise ValueError('Invalid organization')
        return self.pages('/orgs/' + quote(org, safe='') + '/repos', 'repositories')

    def discover_page(self, cursor=''):
        # Creation order is stable against rating manipulation. API is not a snapshot.
        return self.get('/repos', {'sort_by':'created_at', 'page_size':100,
                                  'page_token':cursor}, cache=False)

    def discover(self):
        return self.pages('/repos', 'repositories', {'sort_by':'created_at'})
