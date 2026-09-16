"""Same-origin FastAPI + UI. Every personal read revalidates upstream permission."""
import base64
import hashlib
import json
import secrets
import html
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, FileResponse, Response, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from redis import Redis
from sqlalchemy import select, text, func
from . import config
from .db import Session, Repo, Analysis, Account, Job, migrate, now
from .adapters.sourcecraft import SourceCraft, SourceError, validate_slug
from .queue import enqueue
from .report import markdown

cache=Redis.from_url(config.REDIS_URL,decode_responses=True)

@asynccontextmanager
async def lifespan(app):
    migrate()
    yield

app=FastAPI(title='SourceCraft Repo Health',version='1.0.0',lifespan=lifespan)

@app.exception_handler(SourceError)
async def source_error(request,exc):
    from fastapi.responses import JSONResponse
    return JSONResponse({'detail':exc.reason},status_code=503 if exc.retryable else 403)

@app.middleware('http')
async def security_headers(request,call_next):
    # Exact Origin required for browser mutations; no permissive CORS.
    if request.method in ('POST','PUT','PATCH','DELETE') and request.headers.get('origin')!=config.PUBLIC_ORIGIN:
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail':'origin_mismatch'},status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    response.headers['Cache-Control']='no-store'
    return response

def session(request,required=True):
    sid=request.cookies.get('rh_session','')
    value=cache.get('session:'+hashlib.sha256(sid.encode()).hexdigest()) if sid else None
    if not value:
        if required:raise HTTPException(401,'login_required')
        return None
    return json.loads(value)

def account_token(db,user):
    account=db.get(Account,user['id'])
    if not account or not account.token:raise HTTPException(409,'sourcecraft_token_required')
    return config.cipher().decrypt(account.token.encode()).decode()

def csrf(request,user):
    if not secrets.compare_digest(request.headers.get('x-csrf-token',''),user['csrf']):raise HTTPException(403,'csrf_failed')

def authorize(db,repo,request):
    if repo.scope=='public':token=config.SOURCECRAFT_TOKEN
    else:
        user=session(request)
        if user['id']!=repo.scope:raise HTTPException(404,'not_found')
        token=account_token(db,user)
    if not token:raise HTTPException(503,'sourcecraft_token_required')
    with SourceCraft(token,cache) as api:
        live=api.repository(repo.slug)
    if repo.scope=='public' and live.get('visibility')!='public':raise HTTPException(404,'not_found')
    return live

@app.get('/health/live')
def live():return {'status':'ok'}

@app.get('/health/ready')
def ready():
    try:
        with Session() as db:db.execute(text('SELECT 1'))
        cache.ping()
    except Exception:raise HTTPException(503,'dependencies_unavailable') from None
    return {'status':'ok','sourcecraft_configured':bool(config.SOURCECRAFT_TOKEN),
            'oauth_configured':bool(config.CLIENT_ID),'scheduler_active':bool(cache.get('scheduler-heartbeat'))}

@app.get('/auth/login')
def login():
    if not config.CLIENT_ID:raise HTTPException(503,'yandex_oauth_not_configured')
    state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(48);browser=secrets.token_urlsafe(32)
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    cache.setex('oauth:'+state,600,json.dumps({'verifier':verifier,'browser':hashlib.sha256(browser.encode()).hexdigest()}))
    response=RedirectResponse('https://oauth.yandex.ru/authorize?'+urlencode({'response_type':'code','client_id':config.CLIENT_ID,
            'redirect_uri':config.PUBLIC_ORIGIN+'/auth/callback','state':state,'code_challenge':challenge,'code_challenge_method':'S256'}))
    response.set_cookie('rh_oauth',browser,max_age=600,httponly=True,secure=config.SECURE_COOKIE,samesite='lax')
    return response

@app.get('/auth/callback')
def callback(request:Request,state:str='',code:str=''):
    raw=cache.getdel('oauth:'+state)
    if not raw or not code:raise HTTPException(400,'invalid_oauth_state')
    data=json.loads(raw);actual=hashlib.sha256(request.cookies.get('rh_oauth','').encode()).hexdigest()
    if not secrets.compare_digest(actual,data['browser']):raise HTTPException(400,'oauth_browser_mismatch')
    try:
        with httpx.Client(timeout=20,follow_redirects=False) as client:
            r=client.post('https://oauth.yandex.ru/token',data={'grant_type':'authorization_code','code':code,
                'client_id':config.CLIENT_ID,'client_secret':config.CLIENT_SECRET,'code_verifier':data['verifier']})
            r.raise_for_status();oauth_token=r.json()['access_token']
            r=client.get('https://login.yandex.ru/info',params={'format':'json'},headers={'Authorization':'OAuth '+oauth_token})
            r.raise_for_status();profile=r.json()
    except (httpx.HTTPError,KeyError,ValueError):raise HTTPException(502,'oauth_exchange_failed') from None
    user_id='yandex:'+str(profile['id'])
    with Session.begin() as db:
        account=db.get(Account,user_id)
        if not account:db.add(Account(id=user_id,display_name=profile.get('display_name') or profile.get('login') or 'Пользователь'))
    old=request.cookies.get('rh_session')
    if old:cache.delete('session:'+hashlib.sha256(old.encode()).hexdigest())
    sid=secrets.token_urlsafe(48)
    cache.setex('session:'+hashlib.sha256(sid.encode()).hexdigest(),8*3600,json.dumps({'id':user_id,'csrf':secrets.token_urlsafe(32)}))
    response=RedirectResponse('/?view=mine',status_code=303)
    response.set_cookie('rh_session',sid,max_age=8*3600,httponly=True,secure=config.SECURE_COOKIE,samesite='lax')
    response.delete_cookie('rh_oauth')
    return response

@app.get('/api/me')
def me(request:Request):
    user=session(request,False)
    if not user:return {'authenticated':False,'oauth_configured':bool(config.CLIENT_ID)}
    with Session() as db:
        a=db.get(Account,user['id'])
        return {'authenticated':True,'name':a.display_name,'connected':bool(a.token),'csrf':user['csrf']}

class Credential(BaseModel):
    token:str=Field(min_length=10,max_length=4096)

@app.post('/api/me/sourcecraft')
def connect(body:Credential,request:Request):
    user=session(request);csrf(request,user)
    with SourceCraft(body.token,cache) as api:api.get('/user',cache=False)
    with Session.begin() as db:db.get(Account,user['id']).token=config.cipher().encrypt(body.token.encode()).decode()
    return {'connected':True}

@app.delete('/api/me/sourcecraft')
def disconnect(request:Request):
    user=session(request);csrf(request,user)
    with Session.begin() as db:db.get(Account,user['id']).token=None
    return {'connected':False}

@app.post('/auth/logout')
def logout(request:Request):
    user=session(request);csrf(request,user)
    cache.delete('session:'+hashlib.sha256(request.cookies['rh_session'].encode()).hexdigest())
    response=Response(status_code=204);response.delete_cookie('rh_session');return response

@app.get('/api/me/repositories')
def my_repos(request:Request,org:str):
    user=session(request)
    with Session() as db:token=account_token(db,user)
    try:
        with SourceCraft(token,cache) as api:
            rows=[]
            for repo in api.repositories(org):
                rows.append({'slug':org+'/'+repo['slug'],'visibility':repo.get('visibility')})
                if len(rows)>=2000:break
        return {'items':rows,'limit':2000,'organization_scoped':True}
    except ValueError:raise HTTPException(422,'invalid_org') from None

class Analyze(BaseModel):
    slug:str=Field(max_length=256)

@app.post('/api/analyses',status_code=202)
def analyze(body:Analyze,request:Request):
    user=session(request);csrf(request,user)
    try:slug=validate_slug(body.slug)
    except ValueError:raise HTTPException(422,'invalid_slug') from None
    if not cache.set('submit:'+user['id'],'1',nx=True,ex=10):raise HTTPException(429,'try_again_in_10_seconds')
    with Session.begin() as db:
        token=account_token(db,user)
        with SourceCraft(token,cache) as api:meta=api.repository(slug)
        repo=db.scalar(select(Repo).where(Repo.slug==slug,Repo.scope==user['id']))
        if not repo:
            repo=Repo(slug=slug,scope=user['id'],metadata_json=meta);db.add(repo);db.flush()
        job=enqueue(db,repo)
        return {'job_id':job.id,'repo_id':repo.id,'state':job.state}

@app.get('/api/jobs/{job_id}')
def job_status(job_id:str,request:Request):
    with Session() as db:
        job=db.get(Job,job_id)
        if not job:raise HTTPException(404,'not_found')
        repo=db.get(Repo,job.repo_id);authorize(db,repo,request)
        return {'id':job.id,'repo_id':repo.id,'state':job.state,'attempts':job.attempts,'error':job.error,'finished_at':job.finished_at}

@app.get('/api/repositories/{repo_id}')
def detail(repo_id:str,request:Request):
    with Session() as db:
        repo=db.get(Repo,repo_id)
        if not repo:raise HTTPException(404,'not_found')
        meta=authorize(db,repo,request)
        result=db.get(Analysis,repo.latest_id) if repo.latest_id else None
        history=db.scalars(select(Analysis).where(Analysis.repo_id==repo.id).order_by(Analysis.created_at.desc()).limit(30)).all()
        jobs=db.scalars(select(Job).where(Job.repo_id==repo.id).order_by(Job.created_at.desc()).limit(1)).all()
        return {'id':repo.id,'slug':repo.slug,'metadata':meta,'result':result.result if result else None,
          'history':[{'date':h.created_at,'score':h.score,'coverage':h.coverage} for h in history],
          'last_job':{'state':jobs[0].state,'error':jobs[0].error} if jobs else None}

@app.get('/api/repositories/{repo_id}/report.md')
def report(repo_id:str,request:Request):
    item=detail(repo_id,request)
    if not item['result']:raise HTTPException(409,'analysis_not_ready')
    return Response(markdown(item['slug'],item['result']),media_type='text/markdown; charset=utf-8',
                    headers={'Content-Disposition':'attachment; filename="repo-health.md"'})

@app.get('/api/leaderboard')
def leaderboard(request:Request,language:str='',sort:str='score',partial:bool=True,offset:int=0,limit:int=50):
    if sort not in ('score','likes','activity') or offset<0 or not 1<=limit<=100:raise HTTPException(422,'invalid_query')
    rows=[]
    with Session() as db:
        query=select(Repo,Analysis).join(Analysis,Repo.latest_id==Analysis.id).where(Repo.scope=='public')
        if not partial:
            query=query.where(Analysis.result['rank_eligible'].as_boolean()==True,Analysis.created_at>=now()-8*86400)
        if language:query=query.where(Repo.metadata_json['language']['name'].as_string()==language)
        ordering={'score':Analysis.score,'likes':Repo.metadata_json['_health_likes'].as_integer(),
                  'activity':Repo.metadata_json['last_updated'].as_string()}[sort]
        total=db.scalar(select(func.count()).select_from(query.subquery()))
        # Database pagination first: at most `limit` permission checks, not a whole-platform scan.
        query=query.order_by(ordering.desc().nulls_last(),Repo.slug).offset(offset).limit(limit)
        for repo,a in db.execute(query):
            try:meta=authorize(db,repo,request)
            except (SourceError,HTTPException):continue
            counts=meta.get('rating',{}).get('reaction_counts',[])
            likes=sum(int(c['count']) for c in counts if c.get('type')=='positive_low')
            rows.append({'id':repo.id,'slug':repo.slug,'score':a.score,'coverage':a.coverage,'likes':likes,
                         'language':meta.get('language',{}).get('name'),'last_activity':meta.get('last_updated'),
                         'analyzed_at':a.created_at,'eligible':a.result['rank_eligible']})
    return {'items':rows,'total':total,'offset':offset,'limit':limit,
            'scope':'Каталог SourceCraft' if config.DISCOVERY_MODE=='all' else 'Настроенные организации SourceCraft',
            'configured':bool(config.SOURCECRAFT_TOKEN)}

@app.get('/catalog', response_class=HTMLResponse)
def catalogue_no_js(request:Request, offset:int=0):
    """Accessible fallback: same authorization checks and no client-side JS dependency."""
    data=leaderboard(request, partial=True, offset=offset, limit=20)
    rows=[]
    for r in data['items']:
        label='Подтверждённая' if r['eligible'] else 'Предварительная'
        rows.append('<tr><td>'+html.escape(r['slug'])+'</td><td>'+str(r['score'])+
                    '</td><td>'+str(r['coverage'])+'%</td><td>'+label+'</td><td><a href="/api/repositories/'+
                    html.escape(r['id'],quote=True)+'/report.md">Отчёт Markdown</a></td></tr>')
    next_link='<a href="/catalog?offset='+str(offset+20)+'">Следующая страница →</a>' if offset+20<data['total'] else ''
    return '<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Каталог SourceCraft</title><link rel="stylesheet" href="/static/style.css"><main><a href="/">← Полный интерфейс</a><h1>Репозитории SourceCraft</h1><p>Проанализировано: '+str(data['total'])+'</p><div class="table-wrap"><table><thead><tr><th>Репозиторий</th><th>Score</th><th>Покрытие</th><th>Статус</th><th>Выгрузка</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'+next_link+'</main></html>'

@app.get('/metrics')
def metrics():
    # Infrastructure metrics only: no private repository names or per-repo values.
    with Session() as db:
        states=db.execute(select(Job.state,func.count()).group_by(Job.state)).all()
    return Response('\n'.join(f'repo_health_jobs{{state="{s}"}} {n}' for s,n in states)+'\n',media_type='text/plain')

STATIC=Path(__file__).parent/'static'
@app.get('/assets/repo-health-v2.js')
def ui_script():
    return FileResponse(STATIC/'app.js',media_type='text/javascript; charset=utf-8')

app.mount('/static',StaticFiles(directory=STATIC),name='static')
@app.get('/')
def index():return FileResponse(STATIC/'index.html')
