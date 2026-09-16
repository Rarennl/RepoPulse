"""Durable Postgres queue: SKIP LOCKED leases + fencing tokens, safe at-least-once."""
from sqlalchemy import select, update, or_, and_
from .db import Session, Repo, Job, now, uid

def enqueue(db, repo):
    # Lock the parent row to serialize concurrent POST and scheduler requests.
    db.execute(select(Repo).where(Repo.id==repo.id).with_for_update()).scalar_one()
    pending=db.scalar(select(Job).where(Job.repo_id==repo.id,Job.state.in_(['queued','running'])))
    if pending: return pending
    job=Job(repo_id=repo.id); db.add(job); repo.last_attempt=now(); db.flush(); return job

def claim():
    with Session.begin() as db:
        job=db.scalar(select(Job).where(or_(and_(Job.state=='queued',Job.available_at<=now()),
                 and_(Job.state=='running',Job.lease_until<now()))).order_by(Job.created_at).with_for_update(skip_locked=True).limit(1))
        if not job: return None
        if job.attempts>=4:
            job.state='failed';job.error='retry_budget_exhausted';job.finished_at=now();return None
        job.state='running';job.attempts+=1;job.lease_until=now()+120;job.lease_token=uid()
        return job.id,job.repo_id,job.lease_token

def heartbeat(job_id,token):
    with Session.begin() as db:
        return db.execute(update(Job).where(Job.id==job_id,Job.state=='running',Job.lease_token==token)
                          .values(lease_until=now()+120)).rowcount==1
