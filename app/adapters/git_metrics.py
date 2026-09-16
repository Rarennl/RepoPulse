"""Bounded public Git analysis without checkout, hooks, LFS or code execution."""
import os
import re
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import quote
from ..scoring import metric, missing
from .sourcecraft import validate_slug, SourceError

SOURCE_EXT = {'.py','.js','.ts','.tsx','.jsx','.go','.rs','.java','.c','.cc','.cpp','.h','.cs','.rb','.php','.kt','.swift','.sh','.sql'}
EXCLUDED = {'vendor','node_modules','.git','dist','build','generated','third_party'}
TODO = re.compile(r'\b(?:TODO|FIXME)\b')

class GitReader:
    def __init__(self, directory, timeout=600, byte_limit=1024*1024*1024):
        self.directory=directory; self.deadline=time.monotonic()+timeout
        self.byte_limit=byte_limit; self.processes=[]; self.stop=threading.Event(); self.failure=None
        self.env={**os.environ,'GIT_TERMINAL_PROMPT':'0','GIT_CONFIG_NOSYSTEM':'1',
                  'GIT_CONFIG_GLOBAL':'/dev/null','GIT_LFS_SKIP_SMUDGE':'1'}
        self.thread=threading.Thread(target=self._watch,daemon=True); self.thread.start()
    def _watch(self):
        while not self.stop.wait(1):
            try:
                size=sum(p.stat().st_size for p in Path(self.directory).rglob('*') if p.is_file())
                if size>self.byte_limit or time.monotonic()>self.deadline:
                    self.failure='git_resource_limit'
                    for p in self.processes:
                        if p.poll() is None:
                            try: os.killpg(p.pid,signal.SIGKILL)
                            except ProcessLookupError: pass
                    return
            except FileNotFoundError: pass
    def start(self,args,stdin=None):
        if self.failure or time.monotonic()>self.deadline: raise SourceError('git_resource_limit')
        p=subprocess.Popen(['git','-c','protocol.file.allow=never','-c','http.followRedirects=false',
                            '-c','core.hooksPath=/dev/null',*args],cwd=self.directory,env=self.env,
                           stdin=stdin or subprocess.DEVNULL,stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL,start_new_session=True)
        self.processes.append(p); return p
    def run(self,args,limit=2*1024*1024):
        p=self.start(args); out=p.stdout.read(limit+1)
        if len(out)>limit:
            p.kill(); p.wait(); raise SourceError('git_output_limit')
        p.wait()
        if self.failure: raise SourceError(self.failure)
        if p.returncode: raise SourceError('git_unavailable')
        return out
    def records(self,args,delimiter=b'\n'):
        p=self.start(args); buffer=b''
        while chunk:=p.stdout.read(65536):
            buffer+=chunk
            while delimiter in buffer:
                line,buffer=buffer.split(delimiter,1); yield line
            if len(buffer)>2*1024*1024: raise SourceError('git_record_limit')
        if buffer: yield buffer
        p.wait()
        if self.failure: raise SourceError(self.failure)
        if p.returncode: raise SourceError('git_unavailable')
    def close(self):
        self.stop.set()
        for p in self.processes:
            if p.poll() is None:
                try: os.killpg(p.pid,signal.SIGKILL)
                except ProcessLookupError: pass
            p.wait()
            if p.stdout: p.stdout.close()
            if p.stdin: p.stdin.close()
        self.thread.join(timeout=2)

def collect_git(slug,at,token=None):
    validate_slug(slug)
    # Never accept a clone URL from the browser or API; origin is fixed.
    with tempfile.TemporaryDirectory(prefix='repo-health-') as root:
        g=GitReader(root)
        if token:
            # The credential is passed in child environment, never argv, URL or disk.
            askpass=Path(root)/'askpass.py'
            askpass.write_text('#!/usr/bin/env python3\nimport os\nprint(os.environ["RH_GIT_TOKEN"])\n')
            askpass.chmod(0o700)
            g.env.update(GIT_ASKPASS=str(askpass), RH_GIT_TOKEN=token)
        try:
            g.run(['clone','--bare','--filter=blob:none','--single-branch','--',
                   'https://git@git.sourcecraft.dev/'+slug+'.git','repo.git'])
            git=['--git-dir=repo.git']
            head=g.run(git+['rev-parse','HEAD']).decode().strip()
            base='https://sourcecraft.dev/'+slug
            fact=[{'label':'Git snapshot '+head,'url':base}]
            docs={}; code={}; activity={}
            weeks=set(); authors=set(); latest=None; commits=0
            # --numstat allows empty commits to be excluded. No commit message or email is persisted.
            pending=None; meaningful=False
            def consume():
                nonlocal latest,commits
                if pending and meaningful:
                    ts,author=pending
                    if ts>at: return
                    latest=max(latest or 0,ts); commits+=1
                    weeks.add(int((at-ts)//(7*86400))); authors.add(author)
            for raw in g.records(git+['log','--since='+datetime.fromtimestamp(at-90*86400,timezone.utc).isoformat(),
                                      '--format=@@%ct %ae','--numstat','HEAD']):
                line=raw.decode('utf-8','replace')
                if line.startswith('@@'):
                    consume(); parts=line[2:].split(' ',1); pending=(int(parts[0]),parts[-1]); meaningful=False
                elif re.match(r'^(?:\d+|-)\t(?:\d+|-)\t',line): meaningful=True
            consume()
            activity['active_weeks']=metric(len(weeks),min(100,100*len(weeks)/8),fact)
            activity['contributors']=metric(len(authors),min(100,100*len(authors)/3),fact)
            if latest:
                days=(at-latest)/86400
                activity['recency']=metric(round(days,2),max(0,min(100,100*(1-(days-14)/166))),fact)
            else:
                # Zero meaningful commits in a complete 90d window is a fact, not a failure.
                activity['recency']=metric('Нет содержательных коммитов за 90 дней',0,fact)
            batch=g.start(git+['cat-file','--batch'],stdin=subprocess.PIPE)
            line_count=todo_count=file_count=large=bytes_read=0; skipped=0; todo_files=[]; readme=None; readme_skipped=False
            doc_names={}; blame_old=blame_total=0
            for raw in g.records(git+['ls-tree','-rlz','HEAD'],b'\0'):
                header,path_raw=raw.split(b'\t',1)
                mode,kind,sha,size=header.split()
                if kind!=b'blob' or mode not in (b'100644',b'100755'): continue
                path=path_raw.decode('utf-8','replace'); name=path.lower()
                if '/' not in name or name.startswith('.sourcecraft/'):
                    doc_names[name]=path
                source=Path(path).suffix.lower() in SOURCE_EXT and not any(x in EXCLUDED for x in Path(path).parts)
                is_readme='/' not in name and name.startswith('readme')
                if not source and not is_readme: continue
                if int(size)>1024*1024 or bytes_read+int(size)>256*1024*1024:
                    if source: skipped+=1
                    if is_readme: readme_skipped=True
                    continue
                batch.stdin.write(sha+b'\n'); batch.stdin.flush()
                response=batch.stdout.readline().split()
                if len(response)!=3: raise SourceError('git_blob_unavailable')
                count=int(response[2]); content=batch.stdout.read(count); batch.stdout.read(1)
                if len(content)!=count: raise SourceError('git_blob_truncated')
                bytes_read+=count
                if b'\x00' in content: continue
                text=content.decode('utf-8','replace')
                if is_readme: readme=text
                if source:
                    lines=text.splitlines(); n=len(lines); todos=sum(bool(TODO.search(l)) for l in lines)
                    line_count+=n; file_count+=1; large+=n>1000; todo_count+=todos
                    if todos: todo_files.append(path)
                # content/text live only for one file and are never written to the DB.
            for key,pattern in [('license',r'^(license|licence|copying)(\..*)?$'),('contributing',r'^contributing(\..*)?$'),('codeowners',r'^(\.sourcecraft/)?codeowners$')]:
                paths=[v for k,v in doc_names.items() if re.match(pattern,k)]
                docs[key]=metric(bool(paths),100 if paths else 0,[{'label':(', '.join(paths) if paths else 'Отсутствует '+key)+' @ '+head,'url':base}])
            docs['readme']=missing('README превышает бюджет чтения') if readme_skipped else metric(bool(readme and len(readme.strip())>=100),100 if readme and len(readme.strip())>=100 else 0,fact)
            if readme is not None:
                docs['runbook']=metric(bool(re.search(r'install|quick.?start|запуск|установ',readme,re.I)),100 if re.search(r'install|quick.?start|запуск|установ',readme,re.I) else 0,fact,note='Эвристика текста, команды не выполнялись')
                docs['testguide']=metric(bool(re.search(r'test|build|тест|сборк',readme,re.I)),100 if re.search(r'test|build|тест|сборк',readme,re.I) else 0,fact,note='Эвристика текста, команды не выполнялись')
            if not skipped and line_count:
                density=1000*todo_count/line_count
                code['todo_density']=metric(round(density,4),max(0,100-10*density),fact)
                code['large_files']=metric(round(large/file_count,4),100*(1-large/file_count),fact)
            else:
                code['todo_density']=missing(f'Неполный охват кода: пропущено {skipped} файлов; строк {line_count}')
                code['large_files']=missing('Нет полного измерения исходных файлов')
            if not skipped and not todo_files and line_count:
                code['old_todo']=metric(0,100,fact)
            elif not skipped and len(todo_files)<=50:
                for path in todo_files:
                    origin_ts=None
                    for raw in g.records(git+['blame','--line-porcelain','HEAD','--',path]):
                        line=raw.decode('utf-8','replace')
                        if line.startswith('author-time '): origin_ts=int(line.split()[1])
                        if line.startswith('\t') and TODO.search(line):
                            blame_total+=1; blame_old+=bool(origin_ts and at-origin_ts>180*86400)
                code['old_todo']=metric(blame_old/blame_total,100*(1-blame_old/blame_total),fact) if blame_total else missing('Blame не установил возраст')
            else: code['old_todo']=missing('Лимит blame: 50 файлов; возраст не экстраполируется')
            configured=any(p in doc_names for p in ('.sourcecraft/ci.yaml','.sourcecraft/ci.yml'))
            ci={'configured':metric(configured,100 if configured else 0,fact)}
            return {'docs':docs,'code':code,'activity':activity,'ci':ci}, {'head':head,'files':file_count,'lines':line_count,'skipped_files':skipped,'commits_90d':commits,'bytes_read':bytes_read}
        finally: g.close()
