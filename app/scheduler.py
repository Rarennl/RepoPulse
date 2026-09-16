"""Daily discovery for configured organizations; daily analyses, seven-day idle cadence."""
import logging
import time
from sqlalchemy import select, delete
from redis import Redis
from .db import Session, Repo, Analysis, Job, now, migrate
from .config import SOURCECRAFT_TOKEN, ORG_SLUGS, REDIS_URL, DISCOVERY_MODE
from .adapters.sourcecraft import SourceCraft, SourceError, validate_slug
from .collector import timestamp
from .queue import enqueue

logging.basicConfig(level=logging.INFO)

def remember(meta, org=None):
    if meta.get('visibility') != 'public': return
    org = org or meta.get('organization',{}).get('slug')
    try: slug = validate_slug(str(org)+'/'+str(meta['slug']))
    except (KeyError,ValueError): raise SourceError('discovery_invalid_repository') from None
    with Session.begin() as db:
        repo=db.scalar(select(Repo).where(Repo.slug==slug,Repo.scope=='public'))
        if not repo:
            repo=Repo(slug=slug,scope='public',metadata_json=meta); db.add(repo); db.flush()
        # Commit each repo together with its task; a crash/repeated page is idempotent.
        if not repo.latest_id: enqueue(db,repo)

def discover_batch(cache, api):
    key='discovery:v2:'+DISCOVERY_MODE
    if cache.get(key+':done'): return
    if DISCOVERY_MODE == 'all':
        cursor=cache.get(key+':cursor') or ''
        for _ in range(10):
            page=api.discover_page(cursor)
            for meta in page.get('repositories',[]):remember(meta)
            next_cursor=page.get('next_page_token') or ''
            if not next_cursor:
                cache.delete(key+':cursor')
                cache.setex(key+':done',86400,'1')
                return
            if next_cursor==cursor:raise SourceError('discovery_cursor_cycle')
            cache.set(key+':cursor',next_cursor)
            cursor=next_cursor
    elif DISCOVERY_MODE == 'organizations':
        for org in ORG_SLUGS:
            for meta in api.repositories(org):remember(meta,org)
        cache.setex(key+':done',86400,'1')
    else:raise SourceError('invalid_discovery_mode')

def tick(cache):
    # Redis lock prevents duplicate discovery across scheduler replicas.
    with cache.lock('scheduler-lock',timeout=3600,blocking_timeout=1):
        if SOURCECRAFT_TOKEN:
            with SourceCraft(SOURCECRAFT_TOKEN,cache) as api:
                try: discover_batch(cache,api)
                except SourceError as exc: logging.warning('discovery_failed reason=%s',exc.reason)
        with Session.begin() as db:
            for repo in db.scalars(select(Repo).execution_options(yield_per=100)):
                last=timestamp(repo.metadata_json.get('last_updated'))
                cadence=7*86400 if last and now()-last>180*86400 else 86400
                latest_result=db.get(Analysis,repo.latest_id) if repo.latest_id else None
                upgrade=latest_result and latest_result.result.get('integration_version')!=2
                if now()-repo.last_attempt>cadence or (upgrade and now()-repo.last_attempt>3600): enqueue(db,repo)
            # Retain 90 days of history, always retaining each repository's latest result.
            latest=select(Repo.latest_id).where(Repo.latest_id.is_not(None))
            db.execute(delete(Analysis).where(Analysis.created_at<now()-90*86400,Analysis.id.not_in(latest)))
            db.execute(delete(Job).where(Job.finished_at<now()-30*86400))
        cache.setex('scheduler-heartbeat',600,str(now()))

if __name__=='__main__':
    migrate(); cache=Redis.from_url(REDIS_URL,decode_responses=True)
    while True:
        try:tick(cache)
        except Exception as exc:logging.warning('scheduler_iteration_failed type=%s',type(exc).__name__)
        time.sleep(300)
