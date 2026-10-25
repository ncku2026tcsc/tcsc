# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import time

from . import clipsafe, textutil, winkeys as wk
from .. import settings

SENTINEL = "\x00__szds__\x00"
GRAB_CHARS = 50


def get_clip() -> str:
    import pyperclip
    try:
        return pyperclip.paste()
    except Exception:
        return ""


def set_clip(text) -> None:
    import pyperclip
    try:
        pyperclip.copy(text if text is not None else "")
    except Exception:
        pass


def set_clip_confirm(text, timeout=0.5) -> bool:
    deadline = time.time() + timeout
    while True:
        set_clip(text)
        time.sleep(0.03)
        if get_clip() == text:
            return True
        if time.time() >= deadline:
            return False


def poll_clip(timeout=0.9) -> str:
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        time.sleep(0.03)
        c = get_clip()
        if c and c != SENTINEL:
            return c
        last = c
    return last


class _Owner:
    _get_clip = staticmethod(get_clip)
    _set_clip = staticmethod(set_clip)
    _set_clip_confirm = staticmethod(set_clip_confirm)


_owner = _Owner()


def grab_window(n=GRAB_CHARS):
    for attempt in (0, 1):
        original = get_clip()
        set_clip(SENTINEL)
        time.sleep(0.06)
        wk.select_left(n)
        time.sleep(0.05)
        wk.combo(wk.VK_CONTROL, wk.VK_C)
        window = poll_clip()
        set_clip(original)
        wk.tap(wk.VK_RIGHT)
        if window and window != SENTINEL and window.strip():
            return window
        if attempt == 0:
            time.sleep(0.12)
    return None


def grab_selection(is_console=False, timeout=0.9):
    set_clip(SENTINEL)
    time.sleep(0.06)
    if is_console:
        wk.chord(wk.VK_CONTROL, wk.VK_SHIFT, wk.VK_C)
    else:
        wk.combo(wk.VK_CONTROL, wk.VK_C)
    return poll_clip(timeout)


def selection_text(is_console=False, timeout=0.9):
    saved = get_clip()
    sel = grab_selection(is_console, timeout)
    set_clip(saved)
    body = (sel or "").rstrip("\r\n")
    line_copy = (sel or "").endswith(("\n", "\r")) and "\n" not in body and "\r" not in body
    if not sel or sel == SENTINEL or not body.strip() or line_copy:
        return None
    return sel


def paste_selection(text, reselect=True):
    text = text.replace("\r\n", "\n").replace("\n", "\r\n")
    if not clipsafe.begin_paste(_owner, text):
        raise RuntimeError("剪貼簿被佔用，沒貼成功，請再按一次")
    clipsafe.reconfirm(_owner, text)
    wk.combo(wk.VK_CONTROL, wk.VK_V)
    time.sleep(settings.sp(0.12))
    if reselect:
        wk.select_left(textutil.utf16_len(text))
    clipsafe.end_paste(_owner)


def user_clip() -> str:
    return getattr(_owner, "_clip_user", "")
