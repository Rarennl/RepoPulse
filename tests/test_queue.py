from app.db import Base,engine,Session,Repo,Job,now
from app.queue import enqueue,claim,heartbeat

def test_dedupe_reclaim_and_fence():
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    with Session.begin() as db:
        repo=Repo(slug='o/r',scope='public');db.add(repo);db.flush()
        a=enqueue(db,repo);b=enqueue(db,repo);assert a.id==b.id
    first=claim();assert first
    assert claim() is None
    with Session.begin() as db:db.get(Job,first[0]).lease_until=now()-1
    second=claim();assert second[2]!=first[2]
    assert not heartbeat(first[0],first[2])
    assert heartbeat(second[0],second[2])
