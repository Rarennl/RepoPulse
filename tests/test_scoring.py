import copy
import pytest
from app.scoring import calculate, metric, missing, appsec_metrics, RULES

AT=1789552800

def full(score=80):
    return {c:{k:metric(score,score,[{'label':'SYNTHETIC UNIT TEST','url':None}]) for k,*_ in rules} for c,rules in RULES.items()}

def test_missing_is_not_zero():
    result=calculate({},AT)
    assert result['score'] is None and result['coverage']==0 and not result['rank_eligible']
    data=full();data['security']={}
    result=calculate(data,AT)
    assert result['score']==80 and result['coverage']==80 and not result['rank_eligible']

def test_real_zero_is_penalty():
    data=full(100)
    for m in data['security'].values():m['score']=0
    assert calculate(data,AT)['score']==80

def test_nested_coverage_and_renormalization():
    r=calculate({'docs':{'codeowners':metric(True,100)}},AT)
    assert r['score']==100 and r['coverage']==0.8 and not r['rank_eligible']

def test_determinism_and_no_mutation():
    data=full(31);before=copy.deepcopy(data)
    assert calculate(data,AT)==calculate(data,AT)
    assert data==before

def test_recommendation_delta_matches_counterfactual():
    data=full(50);r=calculate(data,AT)
    rec=r['recommendations'][0];cat,key=rec['id'].split('.')
    improved=copy.deepcopy(data);improved[cat][key]['score']=100
    assert abs((calculate(improved,AT)['score']-r['score'])-rec['delta_score'])<=0.11

def test_no_recommendation_without_evidence():
    assert not calculate({'docs':{'license':metric(False,0)}},AT)['recommendations']

@pytest.mark.parametrize('score',[float('nan'),float('inf'),-1,101])
def test_bad_metric_rejected(score):
    with pytest.raises(ValueError):metric(1,score)

def test_appsec_must_be_complete_recent_and_real_source():
    from datetime import datetime,timezone
    scan={'status':'completed','complete':True,'completed_at':datetime.fromtimestamp(AT,timezone.utc).isoformat(),
          'id':'synthetic-scan','findings':[{'id':'test-vuln','severity':'critical','status':'open'}]}
    data={'source':'SourceCraft AppSec','sast':scan}
    assert appsec_metrics(data,AT)['sast']['score']==40
    assert appsec_metrics(data,AT+31*86400)['sast']['score'] is None
    data['source']='local mock scanner'
    assert appsec_metrics(data,AT)['sast']['score'] is None

def test_popularity_not_input():
    data=full();a=calculate(data,AT);data['likes']=100000000
    assert calculate(data,AT)['score']==a['score']
