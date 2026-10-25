# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import ctypes
from ctypes import wintypes
import threading
import time

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
WM_HOTKEY = 0x0312
WM_APP = 0x8000
_HK_PAUSE = WM_APP + 1
_HK_RESUME = WM_APP + 2
_HK_KEYPASS = WM_APP + 3
_HK_REBIND = WM_APP + 4
VK_F1 = 0x70
MOD_NOREPEAT = 0x4000
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004


def run_hotkey_loop(vk: int, callback, hotkey_id: int = 1, modifiers: int = MOD_NOREPEAT):
    if not _user32.RegisterHotKey(None, hotkey_id, modifiers, vk):
        raise OSError("RegisterHotKey 失敗（該鍵可能已被其他程式佔用）")
    try:
        msg = wintypes.MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == WM_HOTKEY and msg.wParam == hotkey_id:
                try:
                    callback()
                except Exception:
                    pass
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))
    finally:
        _user32.UnregisterHotKey(None, hotkey_id)


def start_hotkey_thread(vk: int, callback, **kw) -> threading.Thread:
    t = threading.Thread(target=run_hotkey_loop, args=(vk, callback), kwargs=kw, daemon=True)
    t.start()
    return t


VK_F2 = 0x71
VK_F3 = 0x72
VK_F4 = 0x73
VK_F5 = 0x74
VK_F6 = 0x75
VK_F7 = 0x76
VK_F8 = 0x77
VK_F9 = 0x78
VK_F10 = 0x79
VK_F11 = 0x7A
VK_F12 = 0x7B
VK_TAB = 0x09

VK_NAMES = {VK_F1: "F1", VK_F2: "F2", VK_F3: "F3", VK_F4: "F4", VK_F5: "F5",
            VK_F6: "F6", VK_F7: "F7", VK_F8: "F8", VK_F9: "F9", VK_F10: "F10",
            VK_F11: "F11", VK_F12: "F12", VK_TAB: "Tab"}


class _KI(ctypes.Structure):
    _fields_ = (("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)))


class _MI(ctypes.Structure):
    _fields_ = (("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)))


class _IU(ctypes.Union):
    _fields_ = (("ki", _KI), ("mi", _MI))


class _INPUT(ctypes.Structure):
    _fields_ = (("type", wintypes.DWORD), ("u", _IU))


def _tap_key(vk):
    seq = (_INPUT * 2)()
    for j, up in enumerate((0, 2)):
        seq[j].type = 1
        seq[j].u.ki = _KI(vk, 0, up, 0, None)
    _user32.SendInput(2, seq, ctypes.sizeof(_INPUT))


class HotkeyController:

    def __init__(self):
        self.tid = None
        self.paused = False
        self.failed_vks = None
        self.rebuild_fn = None
        self.on_error = None

    def pause(self):
        if self.tid is not None and not self.paused:
            self.paused = True
            _user32.PostThreadMessageW(self.tid, _HK_PAUSE, 0, 0)

    def resume(self):
        if self.tid is not None and self.paused:
            self.paused = False
            _user32.PostThreadMessageW(self.tid, _HK_RESUME, 0, 0)

    def toggle(self):
        self.resume() if self.paused else self.pause()

    def key_pass(self, vk, mods=0):
        if self.tid is not None:
            _user32.PostThreadMessageW(self.tid, _HK_KEYPASS, vk, mods)

    def rebind(self):
        if self.tid is not None:
            _user32.PostThreadMessageW(self.tid, _HK_REBIND, 0, 0)


def _vk_mods(key):
    return key if isinstance(key, tuple) else (key, 0)


def key_name(key):
    vk, mods = _vk_mods(key)
    pre = ("Ctrl+" if mods & MOD_CONTROL else "") + ("Alt+" if mods & MOD_ALT else "") \
        + ("Shift+" if mods & MOD_SHIFT else "")
    return pre + VK_NAMES.get(vk, hex(vk))


def _register(bindings: dict, modifiers: int) -> dict:
    reg = {}
    for i, (key, cb) in enumerate(bindings.items(), start=1):
        vk, extra = _vk_mods(key)
        if _user32.RegisterHotKey(None, i, modifiers | extra, vk):
            reg[i] = (vk, cb)
    return reg


def run_hotkeys_loop(bindings: dict, modifiers: int = MOD_NOREPEAT, controller=None,
                     keep_vks=()):
    keep = set(keep_vks)
    msg = wintypes.MSG()
    _user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)
    if controller is not None:
        controller.tid = _kernel32.GetCurrentThreadId()
    registered = _register(bindings, modifiers)
    if controller is not None:
        controller.failed_vks = [key for i, key in enumerate(bindings, start=1)
                                 if i not in registered]
    def _oops(where, e):
        try:
            if controller is not None and controller.on_error:
                controller.on_error(f"hotkey 迴圈例外@{where}: {e!r}")
        except Exception:
            pass

    try:
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
          try:
            m = msg.message
            if m == WM_HOTKEY and msg.wParam in registered:
                try:
                    registered[msg.wParam][1]()
                except Exception as e:
                    _oops("callback", e)
            elif m == _HK_PAUSE:
                for i in list(registered):
                    vk, _cb = registered[i]
                    if vk in keep:
                        continue
                    _user32.UnregisterHotKey(None, i)
                    del registered[i]
            elif m == _HK_RESUME:
                for i, (key, cb) in enumerate(bindings.items(), start=1):
                    if i in registered:
                        continue
                    vk, extra = _vk_mods(key)
                    if _user32.RegisterHotKey(None, i, modifiers | extra, vk):
                        registered[i] = (vk, cb)
            elif m == _HK_REBIND:
                if controller is not None and controller.rebuild_fn:
                    new = controller.rebuild_fn()
                    bindings.clear()
                    bindings.update(new)
                for i in list(registered):
                    _user32.UnregisterHotKey(None, i)
                registered = {}
                if controller is None or not controller.paused:
                    registered = _register(bindings, modifiers)
                if controller is not None:
                    controller.failed_vks = [key for i, key in enumerate(bindings, start=1)
                                             if i not in registered]
            elif m == _HK_KEYPASS:
                vk_, mods_ = int(msg.wParam), int(msg.lParam)
                for i, key in enumerate(bindings, start=1):
                    kvk, kmods = _vk_mods(key)
                    if kvk != vk_ or kmods != mods_:
                        continue
                    if i in registered:
                        _user32.UnregisterHotKey(None, i)
                        del registered[i]
                        _tap_key(vk_)
                        time.sleep(0.05)
                        if _user32.RegisterHotKey(None, i, modifiers | kmods, vk_):
                            registered[i] = (kvk, bindings[key])
                    break
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))
          except Exception as e:
            _oops("loop", e)
    finally:
        for i in registered:
            _user32.UnregisterHotKey(None, i)


def start_hotkeys_thread(bindings: dict, **kw) -> HotkeyController:
    controller = HotkeyController()
    t = threading.Thread(target=run_hotkeys_loop, args=(bindings,),
                         kwargs={**kw, "controller": controller}, daemon=True)
    controller.thread = t
    t.start()
    return controller
