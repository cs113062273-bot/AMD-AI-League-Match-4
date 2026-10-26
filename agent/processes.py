"""Bound the entire retrieval process tree, including optional browser descendants."""
import os
import signal
import subprocess


def stop_started_process(process):
    """Stop a process tree created by this application, including Windows venv redirectors."""
    if process.poll() is None:
        if os.name=='nt':
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,timeout=5,creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            try:os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
        try:process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            if os.name!='nt':
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
            else:process.kill()
            process.wait(timeout=3)


def windows_job(process):
    import ctypes as C
    from ctypes import wintypes as W
    class Basic(C.Structure):
        _fields_=[('per_process',C.c_int64),('per_job',C.c_int64),('flags',W.DWORD),
            ('min_working',C.c_size_t),('max_working',C.c_size_t),('active',W.DWORD),
            ('affinity',C.c_size_t),('priority',W.DWORD),('scheduling',W.DWORD)]
    class IO(C.Structure):
        _fields_=[(name,C.c_uint64) for name in ['read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes']]
    class Extended(C.Structure):
        _fields_=[('basic',Basic),('io',IO),('process_memory',C.c_size_t),('job_memory',C.c_size_t),
            ('peak_process',C.c_size_t),('peak_job',C.c_size_t)]
    kernel=C.WinDLL('kernel32',use_last_error=True)
    kernel.CreateJobObjectW.restype=W.HANDLE
    kernel.SetInformationJobObject.argtypes=[W.HANDLE,C.c_int,C.c_void_p,W.DWORD]
    kernel.AssignProcessToJobObject.argtypes=[W.HANDLE,W.HANDLE]
    kernel.CloseHandle.argtypes=[W.HANDLE]
    handle=kernel.CreateJobObjectW(None,None)
    if not handle:raise C.WinError(C.get_last_error())
    limits=Extended();limits.basic.flags=0x2000 | 0x100 | 0x200  # KILL_ON_JOB_CLOSE | PROCESS_MEMORY | JOB_MEMORY
    limits.process_memory=3*1024**3
    limits.job_memory=3*1024**3
    if not kernel.SetInformationJobObject(handle,9,C.byref(limits),C.sizeof(limits)) or not kernel.AssignProcessToJobObject(handle,W.HANDLE(process._handle)):
        error=C.WinError(C.get_last_error());kernel.CloseHandle(handle);raise error
    return kernel,handle


def run_bounded(command, *, input, cwd, env, timeout):
    process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        cwd=cwd,env=env,start_new_session=os.name!='nt',
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    job=None
    def terminate_tree():
        nonlocal job
        if job:
            kernel,handle=job;kernel.CloseHandle(handle);job=None
        elif os.name!='nt':
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        elif process.poll() is None:
            process.kill()
    try:
        if os.name=='nt':job=windows_job(process)
        try:
            stdout,stderr=process.communicate(input=input,timeout=timeout)
        except subprocess.TimeoutExpired:
            terminate_tree();process.communicate(timeout=3)
            raise
        return subprocess.CompletedProcess(command,process.returncode,stdout,stderr)
    finally:
        terminate_tree()
        if process.poll() is None:process.kill();process.wait(timeout=3)
