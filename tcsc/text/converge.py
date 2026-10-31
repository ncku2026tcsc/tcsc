# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/tcsc2026/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import time

from . import ia2text, selprobe
from ..engine import crashlog, escstop

OK, LOST, STUCK, ABORTED = "ok", "lost", "stuck", "aborted"
ROUNDS = 3
DEADLINE = 3.0
_ZW = "​‌‍⁠﻿­"
_IGNORE = set(_ZW + " \t　  ")
_GHOSTS = "￼�"


def _line_before(text):
    text = text or ""
    k = max(text.rfind(c) for c in _GHOSTS)
    if k != -1:
        text = text[k + 1:]
    text = text.rstrip("\r\n")
    k = max(text.rfind("\r"), text.rfind("\n"))
    return text[k + 1:] if k != -1 else text


def _line_after(text):
    if text is None:
        return None
    return text.split("\r")[0].split("\n")[0]


def reader(kind, back, fwd=40):
    if kind == "ia2":
        def rd():
            b, _w = ia2text.read_before_caret(back=back, timeout=0.6)
            if b is None:
                return None
            a, _w = ia2text.read_after_caret(fwd=fwd, timeout=0.4)
            return _line_before(b), _line_after(a)
    else:
        def rd():
            ctx = selprobe.caret_context(back=back, fwd=fwd, timeout=0.35)
            if ctx is None:
                return None
            return _line_before(ctx[0]), _line_after(ctx[1])
    return rd


def read_after(kind, fwd=40):
    try:
        if kind == "ia2":
            a, _w = ia2text.read_after_caret(fwd=fwd, timeout=0.4)
            return _line_after(a)
        ctx = selprobe.caret_context(back=1, fwd=fwd, timeout=0.35)
        return _line_after(ctx[1]) if ctx else None
    except Exception:
        return None


def _settle(rd, prev=None, first=0.05, gap=0.10, patience=0.8):
    end = time.monotonic() + patience
    time.sleep(first)
    a = rd()
    while True:
        time.sleep(gap)
        b = rd()
        if a is None and b is None:
            return None
        if a == b and b is not None and (prev is None or b != prev or time.monotonic() >= end):
            return b
        if time.monotonic() >= end:
            return b if a == b else None
        a = b


def _align(before, head, lim):
    if before.startswith(head):
        return len(head)
    k = len(head)
    if k >= 4:
        hits = [i for i in range(max(k, len(before) - lim), len(before) + 1) if before[i - k:i] == head]
        if len(hits) == 1:
            return hits[0]
    return None


def _plausible(r, old, want):
    if len(r) > len(old) + 2 * len(want) + 4:
        return False
    pool = set(old) | set(want) | _IGNORE
    return all(c in pool for c in r)


def judge(cur, head, old, want, after0):
    if cur is None:
        return "lost", None, "讀不到現場"
    before, after = cur
    if after0 is not None and after is not None and after != after0:
        return "lost", None, f"游標後那一行變了（{crashlog.q(after0[:12])}→{crashlog.q(after[:12])}）"
    i = _align(before, head, len(old) + 2 * len(want) + 4)
    if i is None:
        return "lost", None, f"找不到原字前面那些字（{crashlog.q(head[-8:])}）"
    r = before[i:]
    if r == want:
        return "ok", r, ""
    if not _plausible(r, old, want):
        return "lost", r, f"差異那段說不通（{crashlog.q(r[-20:])}）"
    return "fix", r, ""


def run(app, rd, head, old, want, after0, modes, fix, prev=None, deadline=DEADLINE, stale_guard=False):
    t_end = time.monotonic() + deadline
    cur = _settle(rd, prev)
    acted = 0
    if stale_guard and prev is not None and cur == prev:
        crashlog.log("自動收斂：寫完現場跟寫前一模一樣（可能讀到舊畫面）→ 不動手")
        return LOST, 0
    while True:
        st, r, why = judge(cur, head, old, want, after0)
        if st == "ok":
            if acted:
                crashlog.log(f"自動收斂：第 {acted} 輪後對了")
            return OK, acted
        if st == "lost":
            crashlog.log(f"自動收斂：停手（{why}）動手 {acted} 次")
            return LOST, acted
        if acted >= ROUNDS or time.monotonic() >= t_end:
            crashlog.log(f"自動收斂：{acted} 輪還不對（現場尾段 {crashlog.q(r[-20:])}），停手")
            return STUCK, acted
        mode = modes[acted % len(modes)]
        crashlog.log(f"自動收斂 第 {acted + 1} 輪：現場 {crashlog.q(r)} ≠ 目標 {crashlog.q(want)} → 換掉（{mode}）")
        escstop.check()
        if not fix(app, r, want, mode):
            return ABORTED, acted
        acted += 1
        last = cur
        cur = _settle(rd, prev=last)
        if cur == last:
            crashlog.log("自動收斂：動手後現場完全沒變（讀到的東西不可信）→ 停手")
            return STUCK, acted
