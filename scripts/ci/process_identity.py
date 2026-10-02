"""Read-only Windows process snapshots; missing short-lived callers remain unmeasured."""
import ctypes
from ctypes import wintypes
import os
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
        self.thread = threading.Thread(target=self.collect, daemon=True)

    def collect(self):
        while not self.stop_event.is_set():
            try:
                table = windows_snapshot()
                for pid, row in table.items():
                    if row['executable'].lower() == 'cys.exe':
                        chain = parent_chain(pid, table)
                        key = tuple(item['pid'] for item in chain)
                        self.records.setdefault(key, dict(observed_at=time.time(), caller_pid=pid, parent_chain=chain))
            except Exception as exc:
                self.errors.append(repr(exc))
                return
            self.stop_event.wait(0.005)

    def start(self):
        self.thread.start()

    def finish(self, root_pid):
        self.stop_event.set()
        self.thread.join(timeout=5)
        records = [row for row in self.records.values()
                   if root_pid in [p['pid'] for p in row['parent_chain']]]
        return dict(root_pid=root_pid, cys_processes=records, errors=self.errors,
                    state='observed' if records else 'unmeasured',
                    limitation='Read-only polling may miss short-lived cys processes; PID is OS-observed, not daemon RPC payload. No absence conclusion is permitted.')
