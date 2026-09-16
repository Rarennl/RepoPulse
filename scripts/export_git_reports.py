"""Public Git-only reports; unavailable REST/AppSec fields remain missing."""
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.adapters.git_metrics import collect_git
from app.scoring import calculate
from app.report import markdown

def export(slug):
    at=time.time();metrics,diagnostics=collect_git(slug,at)
    result=calculate(metrics,at)
    result['diagnostics']={'git':{'status':'ok',**diagnostics},
      'rest':{'status':'unavailable','reason':'Git-only report; no SourceCraft PAT provided'},
      'appsec':{'status':'unavailable','reason':'No verified AppSec results interface'}}
    output=Path('reports/live');output.mkdir(exist_ok=True,parents=True)
    stem=slug.replace('/','--')
    (output/(stem+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    (output/(stem+'.md')).write_text(markdown(slug,result))
    print(json.dumps({'slug':slug,'score':result['score'],'coverage':result['coverage'],'head':diagnostics['head']}))

if __name__=='__main__':
    for slug in sys.argv[1:]:export(slug)
