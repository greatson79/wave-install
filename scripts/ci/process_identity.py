"""Read-only Windows process snapshots; missing short-lived callers remain unmeasured."""
import ctypes
from ctypes import wintypes
import os
import shlex
import threading
import time


def parent_chain(pid, table):
    chain, seen = [], set()
    while pid and pid not in seen and pid in table:
        seen.add(pid)
        row = dict(table[pid])
        chain.append(row)
        pid = row['parent_pid']
    return chain


def windows_snapshot():
    if os.name != 'nt':
        raise RuntimeError('Windows Toolhelp process snapshot unavailable on this OS')
    class Entry(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('usage', wintypes.DWORD),
                    ('pid', wintypes.DWORD), ('heap', ctypes.c_size_t),
                    ('module', wintypes.DWORD), ('threads', wintypes.DWORD),
                    ('ppid', wintypes.DWORD), ('priority', wintypes.LONG),
                    ('flags', wintypes.DWORD), ('exe', wintypes.WCHAR * 260)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    table = {}
    try:
        entry = Entry()
        entry.size = ctypes.sizeof(entry)
        ok = kernel.Process32FirstW(handle, ctypes.byref(entry))
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())
        while ok:
            table[entry.pid] = dict(pid=entry.pid, parent_pid=entry.ppid, executable=entry.exe)
            ok = kernel.Process32NextW(handle, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(handle)
    return table


class ProcessObserver:
    def __init__(self):
        self.stop_event = threading.Event()
        self.records = {}
        self.errors = []
        self.root_pid = None
        self.snapshot_count = 0
        self.root_sample_count = 0
        self.root_seen_count = 0
        self.root_snapshots = []
        self.thread = threading.Thread(target=self.collect, daemon=True)

    def collect(self):
        while not self.stop_event.is_set():
            try:
                table = windows_snapshot()
                self.record_snapshot(table)
            except Exception as exc:
                self.errors.append(repr(exc))
                return
            self.stop_event.wait(0.005)

    def set_root(self, pid):
        self.root_pid = pid

    def record_snapshot(self, table):
        self.snapshot_count += 1
        observed_at = time.time()
        root_pid = self.root_pid
        if root_pid is not None:
            self.root_sample_count += 1
            present = root_pid in table
            self.root_seen_count += int(present)
            # Preserve first observation and presence transitions, avoiding full process dumps.
            if not self.root_snapshots or self.root_snapshots[-1]['present'] != present:
                self.root_snapshots.append(dict(observed_at=observed_at, root_pid=root_pid,
                                                present=present, parent_chain=parent_chain(root_pid, table)))
        for pid, row in table.items():
            if row['executable'].lower() == 'cys.exe':
                chain = parent_chain(pid, table)
                key = tuple(item['pid'] for item in chain)
                self.records.setdefault(key, dict(observed_at=observed_at, caller_pid=pid, parent_chain=chain))

    def start(self):
        self.thread.start()

    def finish(self, root_pid):
        self.stop_event.set()
        self.thread.join(timeout=5)
        records = [row for row in self.records.values()
                   if root_pid in [p['pid'] for p in row['parent_chain']]]
        unassociated = [row for row in self.records.values()
                        if root_pid not in [p['pid'] for p in row['parent_chain']]]
        return dict(root_pid=root_pid, cys_processes=records,
                    unassociated_cys_processes=unassociated,
                    unassociated_note='Observed during the window only; no relationship to this probe is established.',
                    snapshot_count=self.snapshot_count, root_sample_count=self.root_sample_count,
                    root_seen_count=self.root_seen_count, root_snapshots=self.root_snapshots,
                    errors=self.errors,
                    state='observed' if records else 'unmeasured',
                    limitation='Read-only polling may miss short-lived cys processes; PID is OS-observed, not daemon RPC payload. No absence conclusion is permitted.')


def claim_probe_scripts(cys_path, timeout_path=None):
    """Use the path emitted by this Bash's command -v; do not invent MSYS paths."""
    command = shlex.quote(cys_path) + ' claim-role master'
    capture_tail = ''' 2>&1); claim_rc=$?; printf '%s\n' "$claim_out"; exit "$claim_rc"'''
    scripts = {'bash-claim-direct': command + '; claim_rc=$?; exit "$claim_rc"',
               'bash-claim-substitution': 'claim_out=$(' + command + capture_tail}
    if timeout_path:
        scripts['bash-claim-timeout-substitution'] = ('claim_out=$(' + shlex.quote(timeout_path)
            + ' 2 ' + command + capture_tail)
    return scripts
