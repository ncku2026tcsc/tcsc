# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import ctypes
import time

_PUL = ctypes.POINTER(ctypes.c_ulong)


class _KBD(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", _PUL)]


class _MOUSE(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", _PUL)]


class _HW(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong), ("wParamL", ctypes.c_ushort),
                ("wParamH", ctypes.c_ushort)]


class _II(ctypes.Union):
    _fields_ = [("ki", _KBD), ("mi", _MOUSE), ("hi", _HW)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("ii", _II)]


_SendInput = ctypes.windll.user32.SendInput
_SendInput.argtypes = (ctypes.c_uint, ctypes.POINTER(_INPUT), ctypes.c_int)
_SendInput.restype = ctypes.c_uint

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

VK_SHIFT, VK_CONTROL, VK_HOME, VK_END, VK_C, VK_V = 0x10, 0x11, 0x24, 0x23, 0x43, 0x56
VK_LEFT = 0x25
VK_RIGHT = 0x27
_EXTENDED = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E}


VK_MENU = 0x12
_GetAsyncKeyState = ctypes.windll.user32.GetAsyncKeyState
_GetAsyncKeyState.argtypes = (ctypes.c_int,)
_GetAsyncKeyState.restype = ctypes.c_short


def is_down(vk: int) -> bool:
    return bool(_GetAsyncKeyState(vk) & 0x8000)


def wait_mods_up(timeout: float = 1.5, settle: float = 0.05) -> bool:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if not (is_down(VK_SHIFT) or is_down(VK_CONTROL) or is_down(VK_MENU)):
            time.sleep(settle)
            return True
        time.sleep(0.02)
    return False


def _evt(vk: int, up: bool = False) -> _INPUT:
    flags = (KEYEVENTF_EXTENDEDKEY if vk in _EXTENDED else 0) | (KEYEVENTF_KEYUP if up else 0)
    return _INPUT(type=1, ii=_II(ki=_KBD(vk, 0, flags, 0, None)))


def _unicode_evt(code: int, up: bool = False) -> _INPUT:
    flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0)
    return _INPUT(type=1, ii=_II(ki=_KBD(0, code, flags, 0, None)))


def _send(events) -> int:
    n = len(events)
    arr = (_INPUT * n)(*events)
    return _SendInput(n, arr, ctypes.sizeof(_INPUT))


def key(vk: int, up: bool = False) -> int:
    return _send([_evt(vk, up)])


def combo(mod_vk: int, key_vk: int) -> bool:
    return _send([_evt(mod_vk), _evt(key_vk), _evt(key_vk, up=True), _evt(mod_vk, up=True)]) == 4


def chord(*vks: int) -> bool:
    downs = [_evt(v) for v in vks]
    ups = [_evt(v, up=True) for v in reversed(vks)]
    return _send(downs + ups) == len(vks) * 2


def tap(vk: int) -> None:
    _send([_evt(vk), _evt(vk, up=True)])


PACE = 0.006


def _paced(vk: int, n: int, shift: bool) -> int:
    sent = 0
    for _ in range(n):
        ev = [_evt(vk), _evt(vk, up=True)]
        if shift:
            ev = [_evt(VK_SHIFT)] + ev + [_evt(VK_SHIFT, up=True)]
        sent += _send(ev)
        time.sleep(PACE)
    return sent


def select_left(n: int) -> int:
    return _paced(VK_LEFT, n, True)


def select_right(n: int) -> int:
    return _paced(VK_RIGHT, n, True)


def move(n: int) -> int:
    return _paced(VK_LEFT if n < 0 else VK_RIGHT, abs(n), False)


def select_span(back_n: int, total_n: int) -> int:
    return _paced(VK_LEFT, back_n, False) + _paced(VK_RIGHT, total_n, True)


def type_text(text: str, delay: float = 0.003) -> None:
    for ch in text:
        code = ord(ch)
        if code > 0xFFFF:
            v = code - 0x10000
            hi, lo = 0xD800 + (v >> 10), 0xDC00 + (v & 0x3FF)
            _send([_unicode_evt(hi), _unicode_evt(hi, up=True)])
            _send([_unicode_evt(lo), _unicode_evt(lo, up=True)])
        else:
            _send([_unicode_evt(code), _unicode_evt(code, up=True)])
        time.sleep(delay)


def has_ime_punct(s: str) -> bool:
    for ch in (s or ""):
        o = ord(ch)
        if o == 0x3000:
            continue
        if (0x3000 <= o <= 0x30FF or 0x31F0 <= o <= 0x31FF
                or 0xFF00 <= o <= 0xFFEF or 0x2010 <= o <= 0x2027):
            return True
    return False


from ctypes import wintypes

_u32 = ctypes.windll.user32

_u32.LoadKeyboardLayoutW.restype = wintypes.HKL
_u32.LoadKeyboardLayoutW.argtypes = (wintypes.LPCWSTR, wintypes.UINT)
_u32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_u32.IsWindowVisible.argtypes = (wintypes.HWND,)
_u32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
_u32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)

_WM_INPUTLANGCHANGEREQUEST = 0x0050
_INPUTLANGCHANGE_FORWARD = 0x0002
_KLF_ACTIVATE = 0x0001
_KLID_ZH_TW = "00000404"


def switch_to_bopomofo(hwnd, klid: str = _KLID_ZH_TW, press_shift: bool = True) -> bool:
    try:
        hkl = _u32.LoadKeyboardLayoutW(klid, _KLF_ACTIVATE)
        if hkl:
            _u32.PostMessageW(hwnd, _WM_INPUTLANGCHANGEREQUEST, _INPUTLANGCHANGE_FORWARD, hkl)
    except Exception:
        return False
    if press_shift:
        time.sleep(0.35)
        tap(VK_SHIFT)
    return True


_EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_u32.EnumWindows.argtypes = (_EnumProc, wintypes.LPARAM)


def find_window_by_title_substr(substr: str) -> int:
    found = []

    def _cb(hwnd, _lp):
        if _u32.IsWindowVisible(hwnd):
            n = _u32.GetWindowTextLengthW(hwnd)
            if n > 0:
                buf = ctypes.create_unicode_buffer(n + 1)
                _u32.GetWindowTextW(hwnd, buf, n + 1)
                if substr in buf.value:
                    found.append(hwnd)
                    return False
        return True

    _u32.EnumWindows(_EnumProc(_cb), 0)
    return found[0] if found else 0
