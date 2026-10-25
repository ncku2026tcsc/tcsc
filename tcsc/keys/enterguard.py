# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import ctypes
import ctypes.wintypes as wt
import threading
import time

WH_KEYBOARD_LL = 13
_KEY_MSGS = (0x0100, 0x0101, 0x0104, 0x0105)
_KEY_DOWNS = (0x0100, 0x0104)
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
LLKHF_INJECTED = 0x10
GUARD_MAX = 6.0

_MOD_VKS = frozenset({0x10, 0x11, 0x12, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0x5B, 0x5C})
_FKEY_VKS = frozenset(range(0x70, 0x7B)) - {0x73, 0x74}
_CMD_VKS = (0x11, 0x12, 0x5B, 0x5C)
_NAV_VKS = frozenset({0x25, 0x26, 0x27, 0x28, 0x08})

_u32 = ctypes.WinDLL("user32", use_last_error=True)

_HOOKPROC = ctypes.WINFUNCTYPE(wt.LPARAM, ctypes.c_int, wt.WPARAM, wt.LPARAM)
_u32.SetWindowsHookExW.argtypes = (ctypes.c_int, _HOOKPROC, wt.HINSTANCE, wt.DWORD)
_u32.SetWindowsHookExW.restype = wt.HHOOK
_u32.CallNextHookEx.argtypes = (wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM)
_u32.CallNextHookEx.restype = wt.LPARAM
_u32.UnhookWindowsHookEx.argtypes = (wt.HHOOK,)
_u32.UnhookWindowsHookEx.restype = wt.BOOL
_u32.MsgWaitForMultipleObjects.argtypes = (wt.DWORD, ctypes.c_void_p, wt.BOOL, wt.DWORD, wt.DWORD)
_u32.MsgWaitForMultipleObjects.restype = wt.DWORD
_QS_ALLINPUT = 0x04FF


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wt.DWORD), ("scanCode", wt.DWORD),
                ("flags", wt.DWORD), ("time", wt.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


def _should_block(vk, flags, cmd_down_fn=None):
    if flags & LLKHF_INJECTED:
        return False
    if vk in _MOD_VKS:
        return False
    if vk in _FKEY_VKS:
        return False
    if vk == 0x0D:
        return False
    if (cmd_down_fn or _cmd_mod_down)():
        return vk in _NAV_VKS
    return True


def _record(me, kb):
    a = _u32.GetAsyncKeyState
    with me.tape_lock:
        me.tape.append((kb.vkCode, kb.scanCode, bool(kb.flags & LLKHF_EXTENDED),
                        bool(a(VK_SHIFT) & 0x8000), time.time(),
                        bool(a(0x11) & 0x8000), bool(a(0x12) & 0x8000),
                        bool((a(0x5B) | a(0x5C)) & 0x8000)))


def _esc_mode():
    try:
        from ..engine import escstop
        return escstop._mode()
    except Exception:
        return "block"


def _cmd_mod_down():
    return any(_u32.GetAsyncKeyState(k) & 0x8000 for k in _CMD_VKS)


def _esc_signal():
    try:
        from ..engine import escstop
        m = escstop._mode()
        if m == "off":
            return None
        if m in ("single", "double"):
            return escstop.hook_press()
        return False
    except Exception:
        return False


class _Hook:

    def __init__(self):
        self.blocked = 0
        self.blocked_enter = 0
        self.tape = []
        self.tape_lock = threading.Lock()
        self.esc_pass = True
        self.hook_ok = False
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = None

    def _run(self):
        me = self

        @_HOOKPROC
        def proc(nCode, wParam, lParam):
            if nCode == 0 and wParam in _KEY_MSGS:
                kb = ctypes.cast(lParam, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
                if kb.vkCode == VK_ESCAPE and not (kb.flags & LLKHF_INJECTED):
                    if wParam in _KEY_DOWNS:
                        held = bool(_u32.GetAsyncKeyState(VK_ESCAPE) & 0x8000)
                        sig = _esc_signal()
                        me.esc_pass = (sig is None) or held
                        if sig:
                            return 1
                        if sig is None:
                            return _u32.CallNextHookEx(None, nCode, wParam, lParam)
                        me.blocked += 1
                        if _esc_mode() != "block":
                            _record(me, kb)
                        return 1
                    if getattr(me, "esc_pass", False):
                        return _u32.CallNextHookEx(None, nCode, wParam, lParam)
                    return 1
                if _should_block(kb.vkCode, kb.flags):
                    if wParam in _KEY_DOWNS:
                        me.blocked += 1
                        if kb.vkCode == VK_RETURN:
                            me.blocked_enter += 1
                        _record(me, kb)
                        return 1
                    if _u32.GetAsyncKeyState(kb.vkCode) & 0x8000:
                        return _u32.CallNextHookEx(None, nCode, wParam, lParam)
                    return 1
            return _u32.CallNextHookEx(None, nCode, wParam, lParam)

        self._proc = proc
        hook = _u32.SetWindowsHookExW(WH_KEYBOARD_LL, proc, None, 0)
        self.hook_ok = bool(hook)
        self._ready.set()
        if not hook:
            return
        try:
            msg = wt.MSG()
            end = time.time() + GUARD_MAX
            while not self._stop.is_set() and time.time() < end:
                _u32.MsgWaitForMultipleObjects(0, None, 0, 50, _QS_ALLINPUT)
                while _u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    pass
        finally:
            _u32.UnhookWindowsHookEx(hook)

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=1.0)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)


_lock = threading.RLock()
_shared = None
_refs = 0

VK_SHIFT = 0x10
VK_BACK = 0x08
VK_TAB = 0x09
LLKHF_EXTENDED = 0x01
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_EXTENDEDKEY = 0x0001

REFILL_MAX = 40
REFILL_WINDOW = 15.0
REFILL_ROUNDS = 6
TYPEMATIC_MS = 0.055

_NO_REFILL = frozenset({
    VK_TAB, VK_ESCAPE,
    0x21, 0x22, 0x23, 0x24,
    0x25, 0x26, 0x27, 0x28,
    0x2D, 0x2E, 0x5B, 0x5C, 0x2C,
}) | frozenset(range(0x70, 0x88))


class _INPUT_KI(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.POINTER(wt.ULONG))]


class _INPUT_MI(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", wt.DWORD),
                ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ctypes.POINTER(wt.ULONG))]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", _INPUT_KI), ("mi", _INPUT_MI)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _U)]


_u32.SendInput.argtypes = (ctypes.c_uint, ctypes.c_void_p, ctypes.c_int)
_u32.SendInput.restype = ctypes.c_uint


def _send_key(vk, scan, ext, down):
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if ext else 0)
    if not down:
        flags |= KEYEVENTF_KEYUP
    inp = _INPUT(type=1)
    inp.ki = _INPUT_KI(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=None)
    return _u32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT)) == 1






_MOD_SCAN = ((0x11, 0x1D, False), (0x12, 0x38, False), (0x5B, 0x5B, True), (VK_SHIFT, 0x2A, False))


def _held_mods():
    return [m for m in _MOD_SCAN if _u32.GetAsyncKeyState(m[0]) & 0x8000]


def refill(h, hwnd0=None, allow_back=True, log=None):
    done = lost = 0
    err = 0
    for _round in range(REFILL_ROUNDS):
        with h.tape_lock:
            rows, h.tape = h.tape, []
        if not rows:
            break
        if log:
            now = time.time()
            log(f"補鍵細節 第{_round + 1}輪：{len(rows)} 顆 vk={[hex(r[0]) for r in rows][:24]} "
                f"最早 {now - rows[0][4]:.2f}s 前、最晚 {now - rows[-1][4]:.2f}s 前")
        held = _held_mods()
        for vk, scan, ext in held:
            _send_key(vk, scan, ext, False)
        try:
            for row in rows:
                vk, scan, ext, shift = row[0], row[1], row[2], row[3]
                ctrl, alt, winm = (row[5], row[6], row[7]) if len(row) >= 8 else (False, False, False)
                mods = [m for m, on in zip(_MOD_SCAN, (ctrl, alt, winm, shift)) if on]
                for m in mods:
                    _send_key(m[0], m[1], m[2], True)
                ok = _send_key(vk, scan, ext, True)
                ok = _send_key(vk, scan, ext, False) and ok
                for m in reversed(mods):
                    _send_key(m[0], m[1], m[2], False)
                if ok:
                    done += 1
                else:
                    lost += 1
                    err = err or ctypes.get_last_error()
                time.sleep(0.004)
        finally:
            for vk, scan, ext in held:
                _send_key(vk, scan, ext, True)
        time.sleep(0.03)
    if log and (done or lost):
        log(f"補鍵 {done} 顆" + (f"；{lost} 顆系統不收（錯誤碼 {err}）" if lost else ""))
    return done, lost, (f"系統不收（錯誤碼 {err}）" if lost else "")




class guard:

    def __init__(self, refill_keys=False, allow_back=True, log=None):
        self.is_owner = False
        self._h = None
        self._base = 0
        self._base_enter = 0
        self._bi = False
        self._refill = refill_keys
        self._allow_back = allow_back
        self._log = log
        self._hwnd0 = 0
        self.refilled = 0
        self.refill_dropped = 0
        self.refill_reason = ""

    def __enter__(self):
        global _shared, _refs
        with _lock:
            _refs += 1
            if _shared is None:
                _shared = _Hook()
                _shared.start()
                self.is_owner = True
            self._h = _shared
            self._base = _shared.blocked
            self._base_enter = _shared.blocked_enter
        if self.is_owner:
            try:
                self._hwnd0 = _u32.GetForegroundWindow()
            except Exception:
                self._hwnd0 = 0
        if self.is_owner and not self._h.hook_ok:
            if self._log:
                self._log("護欄鉤子掛不上，改用 BlockInput（這段時間按的鍵錄不到、補不回來）")
            try:
                self._bi = bool(_u32.BlockInput(True))
            except Exception:
                self._bi = False
        return self

    @property
    def blocked(self):
        return (self._h.blocked - self._base) if self._h else 0

    @property
    def blocked_enter(self):
        return (self._h.blocked_enter - self._base_enter) if self._h else 0

    def __exit__(self, *exc):
        global _shared, _refs
        if self._refill and self.is_owner and self._h is not None:
            try:
                self.refilled, self.refill_dropped, self.refill_reason = refill(
                    self._h, self._hwnd0, self._allow_back, self._log)
            except Exception as e:
                if self._log:
                    self._log(f"補鍵失敗：{e}")
        if self._bi:
            try:
                _u32.BlockInput(False)
            except Exception:
                pass
        with _lock:
            _refs -= 1
            if _refs <= 0:
                if _shared is not None:
                    _shared.stop()
                _shared = None
                _refs = 0
        return False
