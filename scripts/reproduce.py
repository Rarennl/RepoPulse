"""python scripts/reproduce.py reports/live/organization--repo.json"""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.scoring import calculate
r=json.loads(Path(sys.argv[1]).read_text());fresh=calculate(r['inputs'],r['analyzed_at'])
assert fresh['input_sha256']==r['input_sha256']
for key in ('score','coverage','categories','recommendations','rank_eligible'):assert fresh[key]==r[key],key
print('Reproduced:',fresh['score'],'coverage:',fresh['coverage'],'SHA256:',fresh['input_sha256'])
