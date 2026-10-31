# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/tcsc2026/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import ctypes
import os
import time
from ctypes import wintypes

from . import winkeys as wk
from .. import settings
from ..engine import crashlog, escstop

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

VK_LEFT, VK_RIGHT, VK_UP, VK_DOWN = 0x25, 0x27, 0x26, 0x28
VK_BACK, VK_DEL, VK_MENU, VK_SHIFT, VK_CONTROL = 0x08, 0x2E, 0x12, 0x10, 0x11
_ALL_MODS = (0x11, 0xA2, 0xA3, 0x12, 0xA4, 0xA5, 0x10, 0xA0, 0xA1, 0x5B, 0x5C)

CONSOLES = frozenset({
    "powershell.exe", "pwsh.exe", "cmd.exe", "windowsterminal.exe", "conhost.exe",
    "openconsole.exe", "wt.exe", "mobaxterm.exe", "wezterm-gui.exe", "alacritty.exe",
    "putty.exe", "kitty.exe", "windowsterminalpreview.exe"})
BROWSERS = frozenset({"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe",
                      "opera.exe", "vivaldi.exe", "arc.exe"})
UIA_DEAF = frozenset({"powerpnt.exe"})
COMPOSE_HIDDEN = frozenset({"line.exe"})
BLINK_FIRST = frozenset({"notepad.exe", "firefox.exe"})
IME_UNKNOWN = frozenset({"notepad.exe"})


def foreground_hwnd():
    return _user32.GetForegroundWindow()


def foreground_process() -> str:
    try:
        hwnd = _user32.GetForegroundWindow()
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        h = _kernel32.OpenProcess(0x1000, False, pid.value)
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(512)
            size = wintypes.DWORD(512)
            if _kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return buf.value.rsplit("\\", 1)[-1].lower()
        finally:
            _kernel32.CloseHandle(h)
    except Exception:
        pass
    return ""


def foreground_title() -> str:
    try:
        buf = ctypes.create_unicode_buffer(128)
        _user32.GetWindowTextW(_user32.GetForegroundWindow(), buf, 128)
        return buf.value
    except Exception:
        return ""


def is_own_foreground() -> bool:
    try:
        pid = ctypes.c_ulong()
        _user32.GetWindowThreadProcessId(_user32.GetForegroundWindow(), ctypes.byref(pid))
        return pid.value == os.getpid()
    except Exception:
        return False


def ime_candidates_open() -> bool:
    try:
        hw = _user32.FindWindowW("Windows.UI.Core.CoreWindow", "Microsoft Text Input Application")
        return bool(hw and _user32.IsWindowVisible(hw))
    except Exception:
        return False


def ime_chinese(hwnd) -> bool:
    try:
        imm = ctypes.windll.imm32
        imm.ImmGetDefaultIMEWnd.restype = wintypes.HWND
        imm.ImmGetDefaultIMEWnd.argtypes = (wintypes.HWND,)
        ime = imm.ImmGetDefaultIMEWnd(hwnd)
        if not ime or not _user32.SendMessageW(ime, 0x283, 0x5, 0):
            return False
        return bool(_user32.SendMessageW(ime, 0x283, 0x1, 0) & 0x1)
    except Exception:
        return False


def zh_layout(hwnd) -> bool:
    try:
        return (_user32.GetKeyboardLayout(_user32.GetWindowThreadProcessId(hwnd, None)) & 0xFFFF) == 0x0404
    except Exception:
        return False


def shift_down() -> bool:
    return bool(_user32.GetAsyncKeyState(VK_SHIFT) & 0x8000)


def mods_hold():
    ctl = _user32.GetAsyncKeyState(VK_CONTROL) & 0x8000
    alt = _user32.GetAsyncKeyState(VK_MENU) & 0x8000
    watch = None
    if ctl or alt or shift_down():
        try:
            from ..keys import numcap
            watch = numcap.ModWatch().start()
        except Exception:
            watch = None
    if ctl:
        wk.key(VK_CONTROL, up=True)
    if alt:
        wk.key(0xE8)
        wk.key(0xE8, up=True)
        wk.key(VK_MENU, up=True)
    return ctl, alt, watch


def mods_release(st):
    ctl, alt, watch = st
    if watch is not None:
        try:
            watch.stop()
            if watch.ok:
                if watch.alt is False:
                    alt = 0
                if watch.ctrl is False:
                    ctl = 0
        except Exception:
            pass
    if alt:
        wk.key(VK_MENU)
    if ctl:
        wk.key(VK_CONTROL)


def shift_back(watch, was_down):
    if not was_down:
        return
    if watch is not None and watch.ok and watch.shift is False:
        return
    wk.key(VK_SHIFT)


def ntap(vk, n=1, iv=0.01):
    st = mods_hold()
    try:
        for _ in range(n):
            escstop.check()
            wk.tap(vk)
            time.sleep(iv)
    finally:
        mods_release(st)


def release_all_mods():
    for v in _ALL_MODS:
        try:
            wk.key(v, up=True)
        except Exception:
            pass


def focus_blink(fg):
    alt = settings.get("blink_alt", False)
    try:
        shell = _user32.GetShellWindow() or _user32.GetDesktopWindow()
        tid_me = _kernel32.GetCurrentThreadId()
        tid_fg = _user32.GetWindowThreadProcessId(fg, None)
        _user32.AttachThreadInput(tid_me, tid_fg, True)
        try:
            if alt:
                wk.tap(VK_MENU)
            ok1 = _user32.SetForegroundWindow(shell)
            time.sleep(0.10)
            moved = _user32.GetForegroundWindow() != fg
            if alt:
                wk.tap(VK_MENU)
            ok2 = _user32.SetForegroundWindow(fg)
        finally:
            _user32.AttachThreadInput(tid_me, tid_fg, False)
        time.sleep(0.15)
        back = _user32.GetForegroundWindow() == fg
        crashlog.log(f"焦點眨眼{'（按 Alt）' if alt else ''} 出={bool(ok1)} 真的動了={moved} 回={bool(ok2)} 落回原窗={back}")
    except Exception as e:
        crashlog.log(f"焦點眨眼炸裂 {type(e).__name__}: {e}")
