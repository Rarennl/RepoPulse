import httpx
import pytest
from app.adapters.sourcecraft import SourceCraft,SourceError,validate_slug

def test_pagination_10000_files_streamed():
    calls=[]
    def handler(request):
        page=int(request.url.params.get('page_token',0));calls.append(page)
        return httpx.Response(200,json={'trees':[{'path':f'{page}-{i}.py','type':'file'} for i in range(100)],
            'next_page_token':str(page+1) if page<99 else ''})
    with SourceCraft('test',transport=httpx.MockTransport(handler)) as api:
        assert sum(1 for _ in api.pages('/repos/o/r/trees','trees'))==10000
    assert len(calls)==100

def test_repeated_cursor_fails():
    with SourceCraft('test',transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'items':[],'next_page_token':'same'}))) as api:
        with pytest.raises(SourceError,match='pagination_cycle'):list(api.pages('/x','items'))

def test_403_never_becomes_empty():
    with SourceCraft('test',transport=httpx.MockTransport(lambda r:httpx.Response(403))) as api:
        with pytest.raises(SourceError,match='forbidden'):list(api.pages('/x','items'))

def test_retry_then_success(monkeypatch):
    monkeypatch.setattr('app.adapters.sourcecraft.time.sleep',lambda s:None);calls=[]
    def handler(r):
        calls.append(1);return httpx.Response(503) if len(calls)<3 else httpx.Response(200,json={'ok':True})
    with SourceCraft('test',transport=httpx.MockTransport(handler)) as api:assert api.get('/x')['ok']
    assert len(calls)==3

@pytest.mark.parametrize('slug',['../x','https://evil/a','a/b/c','-option/repo','a/b?token=x'])
def test_reject_external_paths(slug):
    with pytest.raises(ValueError):validate_slug(slug)

def test_cache_credentials_isolated():
    import fakeredis
    cache=fakeredis.FakeRedis(decode_responses=True)
    def handler(r):return httpx.Response(200,json={'credential':r.headers['authorization']})
    with SourceCraft('one',cache,httpx.MockTransport(handler)) as a,SourceCraft('two',cache,httpx.MockTransport(handler)) as b:
        assert a.get('/x')!=b.get('/x')
