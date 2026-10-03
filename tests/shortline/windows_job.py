"""Own a Windows subprocess tree with a kill-on-close Job object.

The small launcher waits for a stdin gate before creating its child. This closes
Popen -> AssignProcessToJobObject's race without changing the child's command.
"""
import ctypes
from ctypes import wintypes
import os
import subprocess
import sys


class _BasicLimit(ctypes.Structure):
    _fields_ = [('PerProcessUserTimeLimit', ctypes.c_longlong),
                ('PerJobUserTimeLimit', ctypes.c_longlong),
                ('LimitFlags', wintypes.DWORD),
                ('MinimumWorkingSetSize', ctypes.c_size_t),
                ('MaximumWorkingSetSize', ctypes.c_size_t),
                ('ActiveProcessLimit', wintypes.DWORD),
                ('Affinity', ctypes.c_size_t),
                ('PriorityClass', wintypes.DWORD),
                ('SchedulingClass', wintypes.DWORD)]


class _IOCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        'ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
        'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]


class _ExtendedLimit(ctypes.Structure):
    _fields_ = [('BasicLimitInformation', _BasicLimit),
                ('IoInfo', _IOCounters), ('ProcessMemoryLimit', ctypes.c_size_t),
                ('JobMemoryLimit', ctypes.c_size_t),
                ('PeakProcessMemoryUsed', ctypes.c_size_t),
                ('PeakJobMemoryUsed', ctypes.c_size_t)]


def _kernel():
    if os.name != 'nt':
        raise RuntimeError('Windows Job objects require Windows')
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    signatures = {
        'CreateJobObjectW': ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
        'SetInformationJobObject': ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
        'AssignProcessToJobObject': ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
        'OpenProcess': ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        'WaitForSingleObject': ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        'CloseHandle': ([wintypes.HANDLE], wintypes.BOOL),
    }
    for name, (args, result) in signatures.items():
        fn = getattr(api, name)
        fn.argtypes, fn.restype = args, result
    return api


# stdin EOF/anything other than the gate exits before any descendant exists.
_LAUNCHER = (
    "import subprocess,sys; "
    "gate=sys.stdin.buffer.read(1); "
    "sys.exit(subprocess.call(sys.argv[1:], stdin=subprocess.DEVNULL) if gate==b'G' else 125)"
)


def run_in_job(args, *, timeout, cwd=None, env=None):
    api = _kernel()
    job = api.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    process = None
    try:
        limits = _ExtendedLimit()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not api.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise ctypes.WinError(ctypes.get_last_error())
        process = subprocess.Popen([sys.executable, '-I', '-c', _LAUNCHER, *args],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=cwd, env=env)
        if not api.AssignProcessToJobObject(job, wintypes.HANDLE(int(process._handle))):
            # The gate is still closed: only our launcher exists, so kill is safe.
            error = ctypes.WinError(ctypes.get_last_error())
            process.kill()
            process.communicate(timeout=10)
            raise error
        try:
            stdout, stderr = process.communicate(input=b'G', timeout=timeout)
        except subprocess.TimeoutExpired:
            # Closing this one owned Job atomically terminates all its descendants.
            if not api.CloseHandle(job):
                raise ctypes.WinError(ctypes.get_last_error())
            job = None
            stdout, stderr = process.communicate(timeout=10)
            raise subprocess.TimeoutExpired(args, timeout, output=stdout, stderr=stderr)
        return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
    finally:
        if job:
            if not api.CloseHandle(job):
                raise ctypes.WinError(ctypes.get_last_error())
        if process:
            # Bounded even if an unexpected pipe/OS error occurs.
            try:
                process.communicate(timeout=10)
            finally:
                for pipe in (process.stdin, process.stdout, process.stderr):
                    if pipe and not pipe.closed:
                        pipe.close()


def verify_timeout_tree():
    """Measure that both child and grandchild die on timeout, using their PIDs."""
    child_code = "import os,time; print('CHILD_PID='+str(os.getpid()),flush=True); time.sleep(120)"
    parent_code = (
        "import os,subprocess,sys; print('PARENT_PID='+str(os.getpid()),flush=True); "
        "subprocess.run([sys.executable,'-I','-c',sys.argv[1]],check=True)"
    )
    try:
        run_in_job([sys.executable, '-I', '-c', parent_code, child_code], timeout=3)
    except subprocess.TimeoutExpired as error:
        output = error.output.decode('ascii')
    else:
        raise AssertionError('timeout tree unexpectedly completed')
    pids = {}
    for line in output.splitlines():
        name, _, value = line.partition('=')
        if name in ('PARENT_PID', 'CHILD_PID'):
            pids[name] = int(value)
    if len(pids) != 2:
        raise AssertionError('timeout test did not observe both PIDs: ' + output)
    api = _kernel()
    for pid in pids.values():
        handle = api.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE only
        if not handle:
            # ERROR_INVALID_PARAMETER means this PID no longer exists.
            if ctypes.get_last_error() != 87:
                raise ctypes.WinError(ctypes.get_last_error())
            continue
        try:
            if api.WaitForSingleObject(handle, 10000) != 0:
                raise AssertionError('owned process survived Job close: ' + str(pid))
        finally:
            api.CloseHandle(handle)
    return {'assertions': 'PASS', 'pids': pids, 'timeout_seconds': 3}
