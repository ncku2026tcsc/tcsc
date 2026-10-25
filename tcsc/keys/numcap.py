# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import ctypes
import threading
import time

import ctypes.wintypes as wt

from .enterguard import (_HOOKPROC, _KBDLLHOOKSTRUCT, _MOD_VKS, _QS_ALLINPUT,
                         _u32, LLKHF_INJECTED, WH_KEYBOARD_LL)

_KEY_DOWNS = (0x0100, 0x0104)
_KEY_UPS = (0x0101, 0x0105)
_DIGITS = {**{0x30 + i: i for i in range(10)},
           **{0x60 + i: i for i in range(10)}}
LLKHF_EXTENDED = 0x01
_NUMNAV = {0x23: 1, 0x28: 2, 0x22: 3, 0x25: 4, 0x0C: 5,
           0x27: 6, 0x24: 7, 0x26: 8, 0x21: 9, 0x2D: 0}
_SHIFT_VKS = (0x10, 0xA0, 0xA1)


class ModWatch:

    _CTRL = frozenset((0x11, 0xA2, 0xA3))
    _ALT = frozenset((0x12, 0xA4, 0xA5))
    _SHIFT = frozenset((0x10, 0xA0, 0xA1))

    def __init__(self):
        self.ctrl = None
        self.alt = None
        self.shift = None
        self.ok = False
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(0.2)
        return self

    def stop(self):
        self._stop.set()

    def _run(self):
        me = self

        @_HOOKPROC
        def proc(nCode, wParam, lParam):
            if nCode == 0 and (wParam in _KEY_DOWNS or wParam in _KEY_UPS):
                kb = ctypes.cast(lParam, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
                if not (kb.flags & LLKHF_INJECTED):
                    d = wParam in _KEY_DOWNS
                    vk = kb.vkCode
                    if vk in me._CTRL:
                        me.ctrl = d
                    elif vk in me._ALT:
                        me.alt = d
                    elif vk in me._SHIFT:
                        me.shift = d
            return _u32.CallNextHookEx(None, nCode, wParam, lParam)

        self._proc = proc
        hook = _u32.SetWindowsHookExW(WH_KEYBOARD_LL, proc, None, 0)
        self.ok = bool(hook)
        self._ready.set()
        if not hook:
            return
        try:
            msg = wt.MSG()
            end = time.time() + 30.0
            while not self._stop.is_set() and time.time() < end:
                _u32.MsgWaitForMultipleObjects(0, None, 0, 30, _QS_ALLINPUT)
                while _u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    pass
        finally:
            _u32.UnhookWindowsHookEx(hook)


class Capture:

    def __init__(self, timeout=1.5, ignore_vks=(), chord_vks=()):
        self.timeout = timeout
        self._ignore = frozenset(ignore_vks)
        self._chord = tuple(chord_vks)
        self._res = {"d": None, "vk": None}
        self._stop = threading.Event()
        self._done = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def cancel(self):
        self._stop.set()

    def result(self):
        self._done.wait(self.timeout + 0.6)
        self._stop.set()
        return self._res["d"]

    def _run(self):
        res, stop, done = self._res, self._stop, self._done
        ignore = self._ignore
        chord = self._chord
        shift_up_t = [0]

        @_HOOKPROC
        def proc(nCode, wParam, lParam):
            if nCode == 0 and not stop.is_set():
                kb = ctypes.cast(lParam, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
                if not (kb.flags & LLKHF_INJECTED):
                    if wParam in _KEY_DOWNS:
                        if res["vk"] is None and kb.vkCode not in ignore:
                            d = _DIGITS.get(kb.vkCode)
                            if (d is None and not (kb.flags & LLKHF_EXTENDED)
                                    and 0 <= kb.time - shift_up_t[0] <= 100):
                                d = _NUMNAV.get(kb.vkCode)
                            if (d is not None and chord
                                    and not any(_u32.GetAsyncKeyState(v) & 0x8000
                                                for v in chord)):
                                d = None
                            if d is not None:
                                res["d"] = d or 10
                                res["vk"] = kb.vkCode
                                done.set()
                                return 1
                            if kb.vkCode not in _MOD_VKS:
                                done.set()
                                stop.set()
                    elif wParam in _KEY_UPS:
                        if kb.vkCode in _SHIFT_VKS:
                            shift_up_t[0] = kb.time
                        if kb.vkCode == res["vk"]:
                            stop.set()
                            return 1
            return _u32.CallNextHookEx(None, nCode, wParam, lParam)

        hook = _u32.SetWindowsHookExW(WH_KEYBOARD_LL, proc, None, 0)
        if not hook:
            done.set()
            stop.set()
            return
        try:
            msg = wt.MSG()
            end = time.time() + self.timeout
            while not stop.is_set() and time.time() < end:
                _u32.MsgWaitForMultipleObjects(0, None, 0, 30, _QS_ALLINPUT)
                while _u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    pass
        finally:
            done.set()
            stop.set()
            _u32.UnhookWindowsHookEx(hook)


def capture_digit(timeout=1.2):
    cap = Capture(timeout)
    cap.start()
    return cap.result()


_ARROWS = {0x25: "left", 0x27: "right"}


class AimCapture:

    def __init__(self, on_left, on_right, on_digit, timeout=15.0):
        self._cb = {"left": on_left, "right": on_right}
        self._digit = on_digit
        self.timeout = timeout
        self._stop = threading.Event()
        self._fired = [False]
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def cancel(self):
        self._stop.set()

    def wait(self):
        t = self._thread
        if t is not None:
            t.join(self.timeout + 2.5)
        self._stop.set()
        return self._fired[0]

    @staticmethod
    def _both_held():
        return bool(_u32.GetAsyncKeyState(0x11) & 0x8000
                    and _u32.GetAsyncKeyState(0x10) & 0x8000)

    def _run(self):
        stop, fired = self._stop, self._fired
        cb, on_digit = self._cb, self._digit
        eaten = set()

        @_HOOKPROC
        def proc(nCode, wParam, lParam):
            if nCode == 0 and not stop.is_set():
                kb = ctypes.cast(lParam, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
                if not (kb.flags & LLKHF_INJECTED):
                    vk = kb.vkCode
                    if wParam in _KEY_DOWNS:
                        if vk in _MOD_VKS or vk in (0x09, 0x20, 0xDC, 0x0D, 0xBB):
                            pass
                        elif self._both_held():
                            arrow = _ARROWS.get(vk)
                            d = _DIGITS.get(vk)
                            rep = vk in eaten
                            if arrow is not None:
                                eaten.add(vk)
                                try:
                                    cb[arrow](rep)
                                except Exception:
                                    pass
                                return 1
                            if d is not None:
                                eaten.add(vk)
                                if not rep:
                                    try:
                                        on_digit(d or 10)
                                    except Exception:
                                        pass
                                return 1
                            stop.set()
                        else:
                            stop.set()
                    elif wParam in _KEY_UPS and vk in eaten:
                        eaten.discard(vk)
                        return 1
            return _u32.CallNextHookEx(None, nCode, wParam, lParam)

        hook = _u32.SetWindowsHookExW(WH_KEYBOARD_LL, proc, None, 0)
        if not hook:
            return
        try:
            msg = wt.MSG()
            end = time.time() + self.timeout
            while not stop.is_set() and time.time() < end:
                if not self._both_held():
                    grace = time.time() + 2.0
                    while time.time() < grace:
                        if not (_u32.GetAsyncKeyState(0x11) & 0x8000
                                or _u32.GetAsyncKeyState(0x10) & 0x8000
                                or _u32.GetAsyncKeyState(0x12) & 0x8000):
                            fired[0] = True
                            break
                        _u32.MsgWaitForMultipleObjects(0, None, 0, 20, _QS_ALLINPUT)
                        while _u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                            pass
                    stop.set()
                    break
                _u32.MsgWaitForMultipleObjects(0, None, 0, 30, _QS_ALLINPUT)
                while _u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    pass
        finally:
            stop.set()
            _u32.UnhookWindowsHookEx(hook)
