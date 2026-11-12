from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def run_process(argv: list[str],cwd: Path,output: Path,*,timeout=300,log_bytes=64*1024*1024,
                env=None,address_space_mib=None):
    """Execute an explicitly trusted command; resource controls are not a sandbox."""
    if not argv or not all(isinstance(x,str) and '\x00' not in x for x in argv):raise ValueError('Invalid argv')
    if not 0<timeout<=86400:raise ValueError('timeout must be 1..86400 seconds')
    if address_space_mib is not None:
        if sys.platform!='linux':raise ValueError('Address-space enforcement is implemented only on Linux')
        if type(address_space_mib) is not int or address_space_mib<64:raise ValueError('address_space_mib must be at least 64')
        argv=[sys.executable,'-m','repo_intel.limit_exec',str(address_space_mib),'--',*argv]
    output.mkdir(parents=True,exist_ok=True,mode=0o700)
    outpath,errpath=output/'stdout.log',output/'stderr.log'
    started=time.monotonic();reason=None
    with outpath.open('wb') as out,errpath.open('wb') as err:
        proc=subprocess.Popen(argv,cwd=cwd,stdin=subprocess.DEVNULL,stdout=out,stderr=err,env=env,
            start_new_session=os.name!='nt')
        while proc.poll() is None:
            if time.monotonic()-started>timeout:reason='timeout'
            elif outpath.stat().st_size+errpath.stat().st_size>log_bytes:reason='log_budget'
            if reason:
                if os.name!='nt':
                    try:os.killpg(proc.pid,signal.SIGTERM)
                    except ProcessLookupError:pass
                else:proc.terminate()
                try:proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    if os.name!='nt':
                        try:os.killpg(proc.pid,signal.SIGKILL)
                        except ProcessLookupError:pass
                    else:proc.kill()
                    proc.wait(timeout=5)
                break
            time.sleep(.03)
    return {'exit_code':proc.returncode,'termination_reason':reason,'seconds':round(time.monotonic()-started,4),
        'stdout':str(outpath),'stderr':str(errpath),'address_space_mib':address_space_mib,
        'sandboxed':False}
