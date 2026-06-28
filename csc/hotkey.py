# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""全域熱鍵：Win32 RegisterHotKey + 訊息迴圈。

為何不用 keyboard 套件：它裝低階鍵盤掛鉤(WH_KEYBOARD_LL)，會與我們的 SendInput
注入互相干擾——複製失效、且 suppress 後熱鍵只觸發一次。RegisterHotKey 走 OS 熱鍵
機制，每次按都乾淨地發 WM_HOTKEY，且不影響 SendInput。
"""
import ctypes
from ctypes import wintypes
import threading

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
WM_HOTKEY = 0x0312
WM_APP = 0x8000
_HK_PAUSE = WM_APP + 1      # 暫停：取消註冊所有熱鍵（前景程式才拿得回那些鍵）
_HK_RESUME = WM_APP + 2     # 恢復：重新註冊
VK_F1 = 0x70
MOD_NOREPEAT = 0x4000   # 按住不重複觸發


def run_hotkey_loop(vk: int, callback, hotkey_id: int = 1, modifiers: int = MOD_NOREPEAT):
    """在『目前執行緒』註冊熱鍵並跑訊息迴圈（阻塞）。每次按鍵呼叫 callback。"""
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
VK_F9 = 0x78
VK_F10 = 0x79
VK_F12 = 0x7B            # 註：F12 為 Windows 保留鍵，RegisterHotKey 一定失敗，勿用


class HotkeyController:
    """暫停/恢復全域熱鍵：透過 PostThreadMessage 通知熱鍵迴圈緒『取消/重新註冊』。
    暫停必須真的 UnregisterHotKey（前景程式才拿得回 F1~F12 等鍵；只靠 flag 略過沒用，
    OS 仍會把鍵吃掉）。"""

    def __init__(self):
        self.tid = None
        self.paused = False

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


def _register(bindings: dict, modifiers: int) -> dict:
    reg = {}
    for i, (vk, cb) in enumerate(bindings.items(), start=1):
        if _user32.RegisterHotKey(None, i, modifiers, vk):
            reg[i] = (vk, cb)
    return reg


def run_hotkeys_loop(bindings: dict, modifiers: int = MOD_NOREPEAT, controller=None,
                     keep_vks=()):
    """bindings: {vk: callback}；一次註冊多個熱鍵並跑訊息迴圈（阻塞）。
    controller：可選，支援暫停/恢復（收到 _HK_PAUSE/_HK_RESUME 時取消/重新註冊）。
    keep_vks：暫停時**不**取消的鍵（例如 F9 暫停切換鍵本身——否則暫停後就無法用它解除）。"""
    keep = set(keep_vks)
    msg = wintypes.MSG()
    _user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)   # 先建立訊息佇列，避免 PostThreadMessage 丟失
    if controller is not None:
        controller.tid = _kernel32.GetCurrentThreadId()
    registered = _register(bindings, modifiers)               # {id: (vk, cb)}
    if not registered:
        raise OSError("RegisterHotKey 全部失敗（鍵可能被佔用）")
    try:
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            m = msg.message
            if m == WM_HOTKEY and msg.wParam in registered:
                try:
                    registered[msg.wParam][1]()
                except Exception:
                    pass
            elif m == _HK_PAUSE:
                for i in list(registered):
                    vk, _cb = registered[i]
                    if vk in keep:                            # 保留（F9 暫停鍵本身）
                        continue
                    _user32.UnregisterHotKey(None, i)
                    del registered[i]
            elif m == _HK_RESUME:
                have = {vk for (vk, _cb) in registered.values()}
                for i, (vk, cb) in enumerate(bindings.items(), start=1):
                    if vk in have:                            # 沒被取消的（含 keep）不重複註冊
                        continue
                    if _user32.RegisterHotKey(None, i, modifiers, vk):
                        registered[i] = (vk, cb)
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))
    finally:
        for i in registered:
            _user32.UnregisterHotKey(None, i)


def start_hotkeys_thread(bindings: dict, **kw) -> HotkeyController:
    """啟動熱鍵迴圈緒；回傳 HotkeyController（可 pause/resume/toggle）。"""
    controller = HotkeyController()
    t = threading.Thread(target=run_hotkeys_loop, args=(bindings,),
                         kwargs={**kw, "controller": controller}, daemon=True)
    t.start()
    return controller
