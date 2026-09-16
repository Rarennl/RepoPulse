"""Generate 3 reports ONLY from real SourceCraft data; no synthetic fallback."""
import json
import os
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.adapters.sourcecraft import SourceCraft
from app.collector import collect
from app.report import markdown

def main():
    token=os.getenv('SOURCECRAFT_TOKEN')
    if not token:raise SystemExit('SOURCECRAFT_TOKEN required. No reports were fabricated.')
    org=os.getenv('REPORT_ORG','sourcecraft');out=Path('reports/live');out.mkdir(parents=True,exist_ok=True)
    with SourceCraft(token) as api:
        count=0
        for meta in api.repositories(org):
            if meta.get('visibility')!='public':continue
            slug=org+'/'+meta['slug'];_,result=collect(slug,token,None,time.time(),public=True)
            stem=slug.replace('/','--')
            (out/(stem+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2))
            (out/(stem+'.md')).write_text(markdown(slug,result))
            print('Exported',slug);count+=1
            if count==3:break
        if count<3:raise SystemExit(f'Only {count} public repositories available; need 3 for acceptance.')
if __name__=='__main__':main()
