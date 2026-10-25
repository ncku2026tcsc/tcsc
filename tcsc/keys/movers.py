# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import threading
import time

from . import numcap
from .. import settings, symbols
from ..engine import crashlog
from ..text import selprobe, win, winkeys as wk

VK_LEFT, VK_RIGHT, VK_UP, VK_DOWN = win.VK_LEFT, win.VK_RIGHT, win.VK_UP, win.VK_DOWN
_NL = symbols.NEWLINES
_GHOSTS = "\ufffc\ufffd\u200b\u200c\u200d\ufeff\u2060\u00ad"
DBL_WIN = 0.35
NUM_WIN = 1.6


def block_steps(text, left):
    stops = symbols.move_stops()
    if left:
        i = len(text)
        while i > 0 and text[i - 1] in stops:
            if text[i - 1] in _NL:
                return 0
            i -= 1
        while i > 0 and text[i - 1] not in stops:
            i -= 1
        span = text[i:]
    else:
        j = 0
        while j < len(text) and text[j] in stops:
            if text[j] in _NL:
                return 0
            j += 1
        while j < len(text) and text[j] not in stops:
            j += 1
        span = text[:j]
    return min(len(span), 120)


def para_steps(text, up):
    lines = text.split("\n")

    def blank(s):
        return not s.strip().strip(_GHOSTS)

    if up:
        i = len(lines) - 1
        while i >= 0 and blank(lines[i]):
            i -= 1
        if i < 0:
            return 0
        while i >= 0 and not blank(lines[i]):
            i -= 1
        tgt = i if i >= 0 else 0
        return (len(lines) - 1) - tgt
    i, n = 0, len(lines)
    while i < n and blank(lines[i]):
        i += 1
    if i >= n:
        return 0
    while i < n and not blank(lines[i]):
        i += 1
    return i if i < n else n - 1


def _ctx(back=80, fwd=80):
    ctx = selprobe.caret_paragraph()
    if ctx is not None:
        return (ctx[0][-back:] if back else "", ctx[1][:fwd] if fwd else "")
    return selprobe.caret_context(back=back, fwd=fwd)


class Movers:
    def __init__(self, busy_fn, tut=None):
        self._busy = busy_fn
        self._tut = tut or (lambda ev: None)
        self._last = (None, 0.0)
        self._cap = None
        self._revived = None

    def _revive(self, read_fn):
        fgp = win.foreground_process()
        if fgp in win.CONSOLES or fgp in win.UIA_DEAF:
            return None
        fg = win.foreground_hwnd()
        if self._revived and self._revived[0] == fg and time.monotonic() - self._revived[1] < 20.0:
            return None
        self._revived = (fg, time.monotonic())
        crashlog.log("移動者修復（推撞→眨眼→輪詢）")
        win.ntap(VK_LEFT, 1)
        win.ntap(VK_RIGHT, 1)
        time.sleep(0.08)
        ctx = read_fn()
        if ctx is None:
            win.focus_blink(fg)
            win.ntap(VK_LEFT, 1)
            win.ntap(VK_RIGHT, 1)
            time.sleep(0.08)
            ctx = read_fn()
        if ctx is None:
            t0 = time.monotonic()
            while time.monotonic() - t0 < 2.0:
                if selprobe._uia_probe() != selprobe.UNKNOWN:
                    break
                time.sleep(0.25)
            ctx = read_fn()
        crashlog.log(f"移動者修復後={'成' if ctx is not None else '敗'}")
        return ctx

    def _dbl(self, key_id):
        now = time.monotonic()
        last_id, last_t = self._last
        self._last = (key_id, now)
        if self._cap is not None:
            try:
                self._cap.cancel()
            except Exception:
                pass
        return last_id == key_id and (now - last_t) <= DBL_WIN

    def _count_then(self, gesture_vk, first, more):
        def go():
            cap = numcap.Capture(NUM_WIN, ignore_vks=(gesture_vk,))
            self._cap = cap
            cap.start()
            first()
            n = cap.result()
            if self._cap is cap:
                self._cap = None
            if n and n > 1:
                more(n - 1)
                self._tut("mover_num")
        threading.Thread(target=go, daemon=True).start()

    def on_move(self, vk):
        if self._busy():
            return
        if self._dbl(("mv", vk)):
            if vk in (VK_UP, VK_DOWN):
                threading.Thread(target=self._vjump, args=(vk,), daemon=True).start()
            else:
                threading.Thread(target=self._block_jump, args=(vk,), daemon=True).start()
            self._tut("mover_dbl")
            return
        self._tut("mover_tap_sel" if win.shift_down() else "mover_tap")
        self._count_then(vk, lambda: win.ntap(vk), lambda k: win.ntap(vk, k))

    def _block_jump(self, vk):
        st = win.mods_hold()
        try:
            ctx = _ctx()
            if ctx is None:
                ctx = self._revive(_ctx)
            if ctx is None:
                wk.combo(wk.VK_CONTROL, vk)
                return
            before, after = ctx
            k = block_steps(before if vk == VK_LEFT else after, vk == VK_LEFT)
            if k <= 0:
                wk.combo(wk.VK_CONTROL, vk)
                return
            for _ in range(k):
                wk.tap(vk)
                time.sleep(0.008)
        finally:
            win.mods_release(st)

    def _vjump(self, vk):
        up = vk == VK_UP
        k = 0
        rd = lambda: selprobe.caret_context(back=400, fwd=400)
        ctx = rd()
        if ctx is None:
            ctx = self._revive(rd)
        if ctx is not None:
            k = para_steps(ctx[0] if up else ctx[1], up)
        if not (0 < k <= 120):
            k = 5
        win.ntap(vk, k, iv=0.008)

    def on_delete(self, right):
        if self._busy():
            return
        self._tut("mover_del")
        vk = win.VK_DEL if right else win.VK_BACK
        if self._dbl(("del", right)):
            threading.Thread(target=self._block_del, args=(right,), daemon=True).start()
            return
        self._count_then(win.VK_BACK, lambda: self._del_tap(vk), lambda k: self._del_tap(vk, k))

    def _del_tap(self, vk, n=1):
        st = win.mods_hold()
        sh = win.shift_down()
        if sh:
            wk.key(win.VK_SHIFT, up=True)
        try:
            for _ in range(n):
                wk.tap(vk)
                time.sleep(0.008)
        finally:
            win.shift_back(st[2], sh)
            win.mods_release(st)

    def _block_del(self, right):
        st = win.mods_hold()
        sh = win.shift_down()
        if sh:
            wk.key(win.VK_SHIFT, up=True)
        try:
            ctx = _ctx()
            if ctx is None:
                ctx = self._revive(_ctx)
            vk = win.VK_DEL if right else win.VK_BACK
            if ctx is None:
                wk.combo(wk.VK_CONTROL, vk)
                return
            before, after = ctx
            k = min(block_steps(after if right else before, not right), 60)
            if k <= 0:
                wk.combo(wk.VK_CONTROL, vk)
                return
            for _ in range(k):
                wk.tap(vk)
                time.sleep(0.008)
        finally:
            win.shift_back(st[2], sh)
            win.mods_release(st)
