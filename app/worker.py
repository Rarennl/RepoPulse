import logging
import threading
import time
from sqlalchemy import select
from .db import Session, Repo, Account, Analysis, Job, now, migrate
from .config import SOURCECRAFT_TOKEN, cipher, REDIS_URL
from .queue import claim, heartbeat
from .collector import collect
from .adapters.sourcecraft import SourceError
from redis import Redis

logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')

def run_once(cache):
    item=claim()
    if not item: return False
    job_id,repo_id,fence=item; stop=threading.Event()
    def maintain():
        while not stop.wait(20):
            if not heartbeat(job_id,fence): return
    thread=threading.Thread(target=maintain,daemon=True);thread.start()
    try:
        with Session() as db:
            repo=db.get(Repo,repo_id); public=repo.scope=='public'
            account=None if public else db.get(Account,repo.scope)
            token=SOURCECRAFT_TOKEN if public else (cipher().decrypt(account.token.encode()).decode() if account and account.token else '')
            slug=repo.slug
        if not token: raise SourceError('sourcecraft_token_required')
        metadata,result=collect(slug,token,cache,now(),public)
        metadata['_health_likes']=sum(int(c['count']) for c in metadata.get('rating',{}).get('reaction_counts',[]) if c.get('type')=='positive_low')
        with Session.begin() as db:
            job=db.scalar(select(Job).where(Job.id==job_id).with_for_update())
            if job.lease_token!=fence or job.state!='running': return True
            repo=db.get(Repo,repo_id)
            analysis=Analysis(repo_id=repo_id,score=result['score'],coverage=result['coverage'],result=result)
            db.add(analysis);db.flush()
            repo.latest_id=analysis.id;repo.metadata_json=metadata
            job.state='succeeded';job.finished_at=now();job.error=None
        logging.info('analysis_succeeded job=%s',job_id)
    except Exception as exc:
        # Never persist raw upstream response, token, source content or stack locals.
        reason=exc.reason if isinstance(exc,SourceError) else 'internal_error'
        retryable=isinstance(exc,SourceError) and exc.retryable
        with Session.begin() as db:
            job=db.scalar(select(Job).where(Job.id==job_id).with_for_update())
            if job.lease_token==fence:
                job.error=reason
                job.state='queued' if retryable and job.attempts<4 else 'failed'
                job.available_at=now()+min(3600,30*2**job.attempts)
                if job.state=='failed':job.finished_at=now()
        logging.warning('analysis_failed job=%s reason=%s',job_id,reason)
    finally:
        stop.set();thread.join(timeout=2)
    return True

if __name__=='__main__':
    migrate();cache=Redis.from_url(REDIS_URL,decode_responses=True)
    while True:
        try:
            if not run_once(cache):time.sleep(2)
        except Exception:
            logging.error('worker_dependency_unavailable');time.sleep(5)
