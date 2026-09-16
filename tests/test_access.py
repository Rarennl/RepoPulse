import hashlib
import json
import fakeredis
import pytest
from fastapi.testclient import TestClient
from app import main,config
from app.db import Base,engine,Session,Account,Repo,Analysis,migrate
from app.scoring import calculate
from app.adapters.sourcecraft import SourceError

@pytest.fixture
def setup(monkeypatch):
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    cache=fakeredis.FakeRedis(decode_responses=True);monkeypatch.setattr(main,'cache',cache)
    with Session.begin() as db:
        for u in ('alice','bob'):db.add(Account(id=u,display_name=u,token=config.cipher().encrypt(b'personal-test-token').decode()))
        repo=Repo(id='private',slug='org/secret',scope='alice',metadata_json={'visibility':'private'},latest_id='analysis')
        db.add(repo);db.add(Analysis(id='analysis',repo_id='private',score=None,coverage=0,result=calculate({},1)))
    for u in ('alice','bob'):cache.set('session:'+hashlib.sha256(u.encode()).hexdigest(),json.dumps({'id':u,'csrf':'csrf'}))
    monkeypatch.setattr(main.SourceCraft,'repository',lambda self,slug:{'visibility':'private','slug':'secret'})
    return TestClient(main.app),cache

@pytest.mark.parametrize('path',['/api/repositories/private','/api/repositories/private/report.md'])
def test_other_user_cannot_read(setup,path):
    client,_=setup;client.cookies.set('rh_session','bob')
    assert client.get(path).status_code==404

def test_owner_report_and_revocation(setup,monkeypatch):
    client,_=setup;client.cookies.set('rh_session','alice')
    assert client.get('/api/repositories/private/report.md').status_code==200
    def revoked(*args):raise SourceError('forbidden')
    monkeypatch.setattr(main.SourceCraft,'repository',revoked)
    assert client.get('/api/repositories/private/report.md').status_code==403

def test_private_not_in_public_list(setup):
    client,_=setup
    assert client.get('/api/leaderboard?partial=true').json()['items']==[]

def test_csrf_and_origin(setup):
    client,_=setup;client.cookies.set('rh_session','alice')
    assert client.post('/api/analyses',json={'slug':'o/r'}).status_code==403
    assert client.post('/api/analyses',headers={'Origin':config.PUBLIC_ORIGIN},json={'slug':'o/r'}).status_code==403

def test_oauth_state_single_use_bound_to_browser(setup):
    client,cache=setup;cache.set('oauth:abc',json.dumps({'browser':'bad','verifier':'x'}))
    assert client.get('/auth/callback?state=abc&code=fake').status_code==400
    assert cache.get('oauth:abc') is None

def test_js_asset_mime_and_no_js_catalogue(setup):
    client,_=setup
    r=client.get('/assets/repo-health-v2.js')
    assert r.status_code==200 and r.headers['content-type'].startswith('text/javascript')
    assert r.headers['cache-control']=='no-store'
    assert '/assets/repo-health-v2.js' in client.get('/').text
    assert 'id="partial" checked' in client.get('/').text
    assert 'org/secret' not in client.get('/catalog').text

def test_partial_visible_by_default_and_in_server_catalogue(setup,monkeypatch):
    client,_=setup
    monkeypatch.setattr(config,'SOURCECRAFT_TOKEN','test-public-token')
    monkeypatch.setattr(main.SourceCraft,'repository',lambda self,slug:{'visibility':'public','slug':'visible'})
    with Session.begin() as db:
        db.add(Repo(id='public',slug='org/visible',scope='public',metadata_json={},latest_id='public-analysis'))
        db.add(Analysis(id='public-analysis',repo_id='public',score=None,coverage=0,result=calculate({},1)))
    assert client.get('/api/leaderboard').json()['items'][0]['slug']=='org/visible'
    assert client.get('/api/leaderboard?partial=false').json()['items']==[]
    assert 'org/visible' in client.get('/catalog').text
    assert 'org/secret' not in client.get('/catalog').text
