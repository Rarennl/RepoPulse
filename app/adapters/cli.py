"""Optional isolated SourceCraft CLI wrapper with bounded output and no shell."""
import json
import os
import selectors
import signal
import subprocess
import time
from .sourcecraft import SLUG, validate_slug, SourceError

class SourceCraftCLI:
    def __init__(self, executable='src'):
        self.executable = executable
    def _run(self, args):
        # Operator provisions an isolated `src init` profile. No AI or mutation commands.
        process=None
        try:
            process=subprocess.Popen([self.executable,*args,'--json'],stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True,bufsize=0)
            data=bytearray();deadline=time.monotonic()+60
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout,selectors.EVENT_READ)
                while True:
                    remaining=deadline-time.monotonic()
                    if remaining<=0:raise SourceError('cli_timeout')
                    events=selector.select(remaining)
                    if not events:raise SourceError('cli_timeout')
                    chunk=os.read(process.stdout.fileno(),65536)
                    if not chunk:break
                    data.extend(chunk)
                    if len(data)>8*1024*1024:raise SourceError('cli_output_limit')
            process.wait(timeout=max(.01,deadline-time.monotonic()))
            if process.returncode:raise SourceError('cli_failed')
            return json.loads(data)
        except (OSError,subprocess.SubprocessError,ValueError):
            raise SourceError('cli_unavailable') from None
        finally:
            if process:
                if process.poll() is None:
                    try:os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                process.wait();process.stdout.close()
    def repositories(self,organization):
        if not SLUG.fullmatch(organization):raise ValueError('Invalid organization')
        return self._run(['repo','list',organization])
    def issues(self,slug):
        return self._run(['issue','list','--repo',validate_slug(slug)])
