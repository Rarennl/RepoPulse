"""Build a source-only archive. Never package local credentials, DBs or caches."""
import hashlib
import json
from pathlib import Path
import zipfile

root=Path(__file__).resolve().parents[1]
excluded={'.git','__pycache__','.pytest_cache','.venv','node_modules','artifacts'}
files=[p for p in root.rglob('*') if p.is_file() and not excluded.intersection(p.relative_to(root).parts)
       and p.name not in ('.env','MANIFEST.sha256.json') and p.suffix not in ('.pyc','.db','.key')]
manifest={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
out=root.parent/'SourceCraft-Repo-Health.zip'
with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as z:
    for p in sorted(files):z.write(p,Path('repo-health')/p.relative_to(root))
    z.writestr('repo-health/MANIFEST.sha256.json',json.dumps(manifest,indent=2))
with zipfile.ZipFile(out) as z:assert z.testzip() is None
print(f'{out}: {len(files)+1} files, {out.stat().st_size} bytes')
