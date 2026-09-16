"""Synthetic transport fixtures for the actual OpenAPI field names; never production data."""
import httpx
import pytest
from app.adapters.appsec import AppSec, scan_time
from app.adapters.sourcecraft import SourceError
from app.scoring import appsec_metrics

AT=1789549000
REPO='0199140f-4343-7c06-a7e3-b835c305b629'
SCAN='01890f3e-7b5c-7cc2-bc6f-3f5d8c9a1e4a'

def transport(empty=False,denied=False,incomplete=False,status='FINISHED'):
    def handler(request):
        assert request.url.host=='appsec.sourcecraft.tech'
        assert request.url.params['gitRepo']==REPO
        if denied:return httpx.Response(403)
        if request.url.path.endswith('/latest'):
            return httpx.Response(200,json={'uuid':SCAN,'status':987654}) # unmapped integer ignored
        if request.url.path.startswith('/v1/scans/'):
            return httpx.Response(200,json={'uuid':SCAN,'status':status,'timeFinished':(AT-1)*1000})
        q=request.url.params;kind=q['type']
        assert q['scanUuid']==SCAN and 'pageToken' in q
        assert all(k in q for k in ('description','file','rule','scanType','severity','status'))
        severity=q.get_list('severity')
        rows=[] if empty or ('HIGH' not in severity and severity!=['']) else [
            {'uuid':kind+'-group','publicId':42,'severity':-987,'status':999,'codeBlock':'DO NOT PERSIST'}]
        return httpx.Response(200,json={'data':rows,'totalSize':len(rows)+(1 if incomplete else 0),'nextPageToken':''})
    return httpx.MockTransport(handler)

def test_filtered_numeric_enums_and_source_only():
    with AppSec('token',transport=transport()) as api:r=api.collect(REPO,'org/repo',AT)
    assert r['status']=='ok'
    assert appsec_metrics(r,AT)['sast']['score']==75
    assert 'DO NOT PERSIST' not in str(r)
    assert r['sast']['findings'][0]['severity']=='high'

@pytest.mark.parametrize('kwargs',[{'empty':True},{'denied':True},{'incomplete':True},{'status':'FAILED'}])
def test_no_false_clean_result(kwargs):
    with AppSec('token',transport=transport(**kwargs)) as api:r=api.collect(REPO,'org/repo',AT)
    assert all(m['score'] is None for m in appsec_metrics(r,AT).values())

def test_scan_time_units_and_future():
    assert scan_time(AT*1000,AT)==AT
    assert scan_time(AT,AT)==AT
    with pytest.raises(SourceError):scan_time((AT+86400)*1000,AT)

def test_strict_pagination():
    def handler(r):
        token=r.url.params['pageToken']
        return httpx.Response(200,json={'data':[{'uuid':'second' if token else 'first'}],
            'totalSize':2,'nextPageToken':'' if token else 'next'})
    with AppSec('token',transport=httpx.MockTransport(handler)) as api:
        assert len(list(api.groups(REPO,SCAN,'SAST')))==2
