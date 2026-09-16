import fakeredis
import httpx
from sqlalchemy import select,func
from app import scheduler
from app.db import Base,engine,Session,Repo,Job
from app.adapters.sourcecraft import SourceCraft

def test_global_discovery_pagination_and_repeated_repository(monkeypatch):
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    monkeypatch.setattr(scheduler,'DISCOVERY_MODE','all')
    cache=fakeredis.FakeRedis(decode_responses=True)
    calls=[]
    def handler(r):
        assert r.url.path=='/repos'
        assert r.url.params['sort_by']=='created_at'
        token=r.url.params.get('page_token','');calls.append(token)
        repo={'id':'x','slug':'repo','organization':{'slug':'other-org'},'visibility':'public'}
        return httpx.Response(200,json={'repositories':[repo], 'next_page_token':'' if token else 'next'})
    with SourceCraft('token',transport=httpx.MockTransport(handler)) as api:
        scheduler.discover_batch(cache,api)
        scheduler.discover_batch(cache,api)
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(Repo))==1
        assert db.scalar(select(func.count()).select_from(Job))==1
    assert calls==['','next']
