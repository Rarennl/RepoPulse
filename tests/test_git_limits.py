"""Local synthetic boundary checks; not evidence of live SourceCraft connectivity."""
import subprocess
import time
from pathlib import Path
from app.adapters.git_metrics import GitReader

def test_stream_20000_commits(tmp_path):
    subprocess.run(['git','init','--bare',str(tmp_path/'repo.git')],check=True,capture_output=True)
    p=subprocess.Popen(['git','--git-dir='+str(tmp_path/'repo.git'),'fast-import','--quiet'],stdin=subprocess.PIPE,stderr=subprocess.PIPE)
    for i in range(20000):
        text=f'blob\nmark :{i*2+1}\ndata 2\nx\n\ncommit refs/heads/main\nmark :{i*2+2}\ncommitter Test <test@example.invalid> {1700000000+i} +0000\ndata 1\nx\nM 100644 :{i*2+1} file.txt\n\n'
        p.stdin.write(text.encode())
    p.stdin.close();assert p.wait(timeout=60)==0
    g=GitReader(str(tmp_path),timeout=30)
    try:
        assert sum(1 for _ in g.records(['--git-dir=repo.git','log','--format=%H','main']))==20000
    finally:g.close()

def test_500_mib_budget_detected_without_loading_file(tmp_path):
    g=GitReader(str(tmp_path),byte_limit=500*1024*1024)
    try:
        with (tmp_path/'large.pack').open('wb') as f:f.truncate(501*1024*1024)
        deadline=time.monotonic()+4
        while not g.failure and time.monotonic()<deadline:time.sleep(.1)
        assert g.failure=='git_resource_limit'
    finally:g.close()
