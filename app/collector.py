"""Normalize source facts; do not confuse an unavailable endpoint with empty data."""
import statistics
from datetime import datetime
from .adapters.sourcecraft import SourceCraft, SourceError
from .adapters.git_metrics import collect_git
from .scoring import metric, missing, calculate, appsec_metrics
from .adapters.appsec import AppSec
from . import config

def timestamp(value):
    if not value: return None
    try: return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
    except (ValueError,TypeError): return None

def collect(slug, token, cache, at, public=False):
    metrics={}; diagnostics={}; base='https://sourcecraft.dev/'+slug
    with SourceCraft(token,cache) as api:
        repository=api.repository(slug)
        if public and repository.get('visibility')!='public': raise SourceError('not_public')
        path='/repos/'+slug
        fact=[{'label':'Дерево репозитория на дату анализа','url':base}]
        try:
            found=set(); files=0
            for t in api.pages(path+'/trees','trees',{'recursive':'true'}):
                p=t.get('path','').lower()
                if t.get('type') in ('file','executable'):
                    files+=1
                    if '/' not in p or p in ('.sourcecraft/ci.yaml','.sourcecraft/ci.yml','.sourcecraft/codeowners'):
                        found.add(p)
            metrics['docs']={}
            for key,predicate in [('readme',lambda p:p.startswith('readme')),
                                  ('license',lambda p:p.split('.')[0] in ('license','licence','copying')),
                                  ('contributing',lambda p:p.startswith('contributing')),
                                  ('codeowners',lambda p:p in ('codeowners','.sourcecraft/codeowners'))]:
                paths=[p for p in found if predicate(p)]
                metrics['docs'][key]=metric(bool(paths),100 if paths else 0,
                    [{'label':', '.join(paths) if paths else key+': не найден в полном дереве','url':base}],
                    note='Наличие файла; содержимое ещё не проверено')
            configured=bool(found & {'.sourcecraft/ci.yaml','.sourcecraft/ci.yml'})
            metrics['ci']={'configured':metric(configured,100 if configured else 0,fact)}
            diagnostics['tree']={'status':'ok','file_count':files}
        except SourceError as e: diagnostics['tree']={'status':e.reason}
        try:
            # Keep only the last 100 completed runs, regardless of upstream page order.
            runs=[]; total=0
            for r in api.pages(path+'/cicd/runs','runs'):
                total+=1; dates=r.get('dates',{}); ended=timestamp(dates.get('finished_at'))
                if r.get('status') not in ('success','failed','timeout') or not ended: continue
                if not at-90*86400<=ended<=at: continue
                runs.append((ended,str(r.get('slug','')),r['status'],timestamp(dates.get('started_at'))))
                runs.sort(reverse=True); runs=runs[:100]
            ci=metrics.setdefault('ci',{})
            facts=[{'label':f'Pipeline {r[1]}: {r[2]}','url':base+'/ci'} for r in runs[:10]]
            if runs:
                success=sum(r[2]=='success' for r in runs)/len(runs)
                ci['success_rate']=metric(round(success,4),100*success,facts,note=f'{len(runs)} завершённых запусков, окно 90 дней')
                half=len(runs)//2
                if half>=5:
                    new=sum(r[2]=='success' for r in runs[:half])/half
                    old=sum(r[2]=='success' for r in runs[half:])/(len(runs)-half)
                    ci['stability']=metric(round(new-old,4),100*(1-max(0,old-new)),facts)
                durations=[r[0]-r[3] for r in runs if r[3] and r[0]>=r[3]]
                diagnostics['ci']={'status':'ok','runs_total':total,'sample':len(runs),'success_rate':success,
                    'duration_median_seconds':statistics.median(durations) if durations else None}
            else:
                ci['success_rate']=missing('Нет завершённых запусков за 90 дней')
                diagnostics['ci']={'status':'ok','runs_total':total,'sample':0}
        except SourceError as e: diagnostics['ci']={'status':e.reason}
        try:
            opened=closed=stale=0; times=[]; response_hours=[]; response_complete=True; blocked=0; links_complete=True
            created_recent=closed_recent=0; issues_count=0; facts=[]
            for issue in api.pages(path+'/issues','issues'):
                # A public repo can contain private issues; public report must exclude them.
                if public and issue.get('visibility')!='public': continue
                issues_count+=1
                st=issue.get('status',{}).get('status_type')
                done=st in ('completed','cancelled')
                created=timestamp(issue.get('created_at')); updated=timestamp(issue.get('updated_at'))
                completed=timestamp(issue.get('completed_at'))
                closed+=done; opened+=not done
                old=not done and updated and at-updated>90*86400
                stale+=bool(old)
                created_recent+=bool(created and at-30*86400<=created<=at)
                closed_recent+=bool(completed and at-30*86400<=completed<=at)
                if done and completed and created and completed>=created: times.append((completed-created)/86400)
                if len(times)>100000: raise SourceError('issue_aggregation_budget')
                issue_url=base+'/issues/'+str(issue.get('slug',''))
                if old and len(facts)<10: facts.append({'label':'Issue '+str(issue.get('slug'))+': без обновлений >90 дней','url':issue_url})
                if issues_count<=100:
                    ipath=path+'/issues/'+str(issue['slug'])
                    try:
                        first=None
                        for comment in api.pages(ipath+'/comments','issue_comments'):
                            ct=timestamp(comment.get('created_at'))
                            if comment.get('author',{}).get('id')!=issue.get('author',{}).get('id') and ct and created and ct>=created:
                                first=min(first or ct,ct)
                        # No reply is right-censored, not a zero-duration successful response.
                        if created and created<=at: response_hours.append(((first or at)-created)/3600)
                    except SourceError: response_complete=False
                    try:
                        dependent=False
                        for relation in api.pages(ipath+'/issue_links','links'):
                            dependent |= relation.get('link_type')=='blocked_by'
                        blocked+=dependent
                    except SourceError: links_complete=False
                else:
                    response_complete=False; links_complete=False
            m={}
            aggregate_fact=[{'label':f'Issues: открыто {opened}, закрыто {closed}; дата {at}','url':base+'/issues'}]
            m['stale']=metric(stale/opened,100*(1-stale/opened),facts or aggregate_fact) if opened else missing('Нет открытых задач')
            m['closure']=metric(statistics.median(times),max(0,100*(1-statistics.median(times)/90)),aggregate_fact) if times else missing('Нет закрытых задач с датами')
            m['response']=metric(statistics.median(response_hours),max(0,100*(1-statistics.median(response_hours)/168)),aggregate_fact,
                                  note='Без ответа: возраст задачи на дату анализа (цензурирование)') if response_complete and response_hours else missing('Нет полного измерения первого ответа; максимум 100 задач')
            metrics['issues']=m
            diagnostics['issues']={'status':'ok','open':opened,'closed':closed,'created_30d':created_recent,
                 'closed_30d':closed_recent,'dependent_fraction':blocked/issues_count if links_complete and issues_count else None,'dependency_reason':'Полный обход связей до 100 задач; доля справочная, вне Score'}
        except SourceError as e: diagnostics['issues']={'status':e.reason}
        for resource,field in [('contributors','contributors'),('pulls','pull_requests'),('releases','releases')]:
            try:
                count=0; recent=0
                for row in api.pages(path+'/'+resource,field):
                    count+=1; date=timestamp(row.get('released_at') or row.get('created_at'))
                    recent+=bool(date and at-90*86400<=date<=at)
                diagnostics[resource]={'status':'ok','total':count,'created_90d':recent}
            except SourceError as e: diagnostics[resource]={'status':e.reason}
        if config.APPSEC_ENABLED:
            # Never use a shared AppSec service credential for a user's private analysis.
            security_token = (config.APPSEC_TOKEN or token) if public else token
            with AppSec(security_token, cache, auth_scheme=config.APPSEC_AUTH_SCHEME) as security:
                security_data = security.collect(repository.get('id'), slug, at)
            metrics['security'] = appsec_metrics(security_data, at)
            diagnostics['appsec'] = {**security_data['diagnostics'], 'status':security_data['status'],
                                      'reason':security_data.get('reason')}
        else:
            metrics['security'] = appsec_metrics({'reason':'AppSec отключён в настройках'}, at)
            diagnostics['appsec'] = {'status':'disabled'}
        # API permission was checked above. Git asks for the same owner's PAT.
        try:
            git_metrics,git_info=collect_git(slug,at,token=token if not public else None)
            for c,items in git_metrics.items(): metrics.setdefault(c,{}).update(items)
            diagnostics['git']={'status':'ok',**git_info}
        except (SourceError,OSError) as e:
            diagnostics['git']={'status':e.reason if isinstance(e,SourceError) else 'git_unavailable'}
    result=calculate(metrics,at); result['diagnostics']=diagnostics; result['integration_version']=2
    return repository,result
