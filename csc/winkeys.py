# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""Win32 SendInput 送鍵工具（虛擬鍵碼，修飾鍵正確按住；含 Unicode 打字）。

重點：
  - 組合鍵（Shift+Home / Ctrl+C…）用「單一次 SendInput 陣列」原子送出，
    確保修飾鍵在主鍵按下期間確實按住（分開呼叫常常併不上 → 只剩主鍵）。
  - Home/End/方向鍵等是 extended key，加 KEYEVENTF_EXTENDEDKEY 旗標。
  - dwExtraInfo 一律給 NULL，避免 ctypes 物件生命週期造成的野指標。
  - type_text 用 KEYEVENTF_UNICODE 直接送字元（繞過注音 IME，覆蓋目前選取區）。
"""
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
    # union 須以最大成員(MOUSEINPUT)為準，否則 sizeof(INPUT) 不符 → SendInput 失敗回傳 0
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
# 需要 extended-key 旗標的鍵：PgUp/PgDn/End/Home/方向鍵/Ins/Del
_EXTENDED = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E}


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
    """一次 SendInput 送出 [mod↓, key↓, key↑, mod↑]，確保修飾鍵全程按住。"""
    return _send([_evt(mod_vk), _evt(key_vk), _evt(key_vk, up=True), _evt(mod_vk, up=True)]) == 4


def chord(*vks: int) -> bool:
    """依序按下所有鍵、再反序放開，一次原子送出（用於 Ctrl+Shift+C 等多修飾鍵組合）。"""
    downs = [_evt(v) for v in vks]
    ups = [_evt(v, up=True) for v in reversed(vks)]
    return _send(downs + ups) == len(vks) * 2


def tap(vk: int) -> None:
    _send([_evt(vk), _evt(vk, up=True)])


def select_left(n: int) -> int:
    """一次 SendInput 原子送出 [Shift↓, (←↓ ←↑)×n, Shift↑] 反白游標前 n 格。
    相對「Shift 按住、跑 n 圈逐次送 ←」：Shift 只被按住單一注入（~1ms）而非數十毫秒，
    避免這段期間使用者實體按鍵與注入的 Shift 併成「Shift+鍵」而漏給前景程式（如 Shift+F1）。"""
    events = [_evt(VK_SHIFT)]
    for _ in range(n):
        events.append(_evt(VK_LEFT))
        events.append(_evt(VK_LEFT, up=True))
    events.append(_evt(VK_SHIFT, up=True))
    return _send(events)


def type_text(text: str, delay: float = 0.003) -> None:
    """以 Unicode 直接送出字元（繞過 IME，覆蓋目前選取區）。
    BMP 以外（emoji…）拆成 UTF-16 代理對送出，否則會整個消失。"""
    for ch in text:
        code = ord(ch)
        if code > 0xFFFF:                       # 非 BMP → 送高/低代理對
            v = code - 0x10000
            hi, lo = 0xD800 + (v >> 10), 0xDC00 + (v & 0x3FF)
            _send([_unicode_evt(hi), _unicode_evt(hi, up=True)])
            _send([_unicode_evt(lo), _unicode_evt(lo, up=True)])
        else:
            _send([_unicode_evt(code), _unicode_evt(code, up=True)])
        time.sleep(delay)


def has_ime_punct(s: str) -> bool:
    """文字是否含『會被新注音(中文模式)當組字吃掉』的全形/CJK 標點 → 含則別用 type_text 直接打、改剪貼簿。
    用 SendInput Unicode 注入這類標點時，TSF 注音會攔截成組字（留底線、把後續內容吃掉）。
    涵蓋範圍（放寬：不只括弧，所有全形標點）：
      U+3000–U+303F  CJK 標點：。、「」『』（半）《》【】〈〉〔〕〜 等
      U+FF00–U+FFEF  全形 ASCII：？ ！ ： ； （ ） ， 等（含全形數字/字母，罕見、貼上無害）
      U+2010–U+2027  一般標點：— – … ‘ ’ “ ”
    半形 ASCII 標點（. , ? ! …）在注音不組字、用 type_text 安全 → 不列入（以免英數文字也被迫走剪貼簿）。"""
    for ch in (s or ""):
        o = ord(ch)
        if o == 0x3000:                       # 全形空格：注音不組字、打字安全 → 不算（否則空格分隔的字都被迫走剪貼簿）
            continue
        if 0x3000 <= o <= 0x303F or 0xFF00 <= o <= 0xFFEF or 0x2010 <= o <= 0x2027:
            return True
    return False


# ===== 輸入法切換 / 視窗搜尋（給 F6 框「開窗即切繁中注音」用）=====
# 兩步：
#   (1) 切鍵盤配置到繁中(zh-TW＝微軟新注音)：LoadKeyboardLayout + WM_INPUTLANGCHANGEREQUEST。
#   (2) 進中文模式：新注音是 TSF 輸入法、**不甩 IMM32 ImmSetConversionStatus**（實測切了仍英數）。
#       它的「中/英」切換預設就是敲一下 Shift；切配置後預設停在英數，故補一下 Shift 即進中文。
# 64-bit 下 HKL 是指標大小，務必設好 restype/argtypes 否則 handle 會被截成 32-bit 變垃圾。
from ctypes import wintypes  # noqa: E402

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
_KLID_ZH_TW = "00000404"            # 繁中（Traditional Chinese）鍵盤配置


def switch_to_bopomofo(hwnd, klid: str = _KLID_ZH_TW, press_shift: bool = True) -> bool:
    """把 hwnd 切到繁中注音輸入法（鍵盤配置）。press_shift=True 時再敲一下 Shift 進中文模式。
    新注音是 TSF、不甩 IMM32 設模式，故中文模式只能靠模擬它的「中/英」熱鍵(Shift)。
    Shift 是『切換』非『設定』：若該情境本來就在中文會被切成英數，故 press_shift 預設可由呼叫端關閉。"""
    try:
        hkl = _u32.LoadKeyboardLayoutW(klid, _KLF_ACTIVATE)
        if hkl:
            _u32.PostMessageW(hwnd, _WM_INPUTLANGCHANGEREQUEST, _INPUTLANGCHANGE_FORWARD, hkl)
    except Exception:
        return False
    if press_shift:
        time.sleep(0.35)                # 等配置真的切到新注音，再切中文模式
        tap(VK_SHIFT)                   # 新注音：敲一下 Shift = 中/英切換 → 進中文
    return True


_EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_u32.EnumWindows.argtypes = (_EnumProc, wintypes.LPARAM)


def find_window_by_title_substr(substr: str) -> int:
    """找一個標題含 substr 的可見頂層視窗，回傳 hwnd（int）或 0。"""
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
