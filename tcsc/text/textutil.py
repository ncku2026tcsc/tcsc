# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/tcsc2026/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
from .. import symbols

_NEWLINES = symbols.NEWLINES


def utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def split_tail_unit(window: str):
    for i in range(len(window) - 1, -1, -1):
        if window[i] in _NEWLINES:
            window = window[i + 1:]
            break
    delim = symbols.breaks()
    tail = ""
    s = window
    while s and s[-1] in delim:
        tail = s[-1] + tail
        s = s[:-1]
    idx = -1
    for ch in delim:
        p = s.rfind(ch)
        if p > idx:
            idx = p
    return s[idx + 1:], tail


def split_units_tail(window: str, max_n: int = 9):
    out = []
    s = window
    while s and len(out) < max_n:
        unit, tail = split_tail_unit(s)
        if not unit.strip():
            break
        out.append((unit, tail))
        s = s[: len(s) - len(unit) - len(tail)]
    return out


def split_prev_unit(window: str):
    unit, tail = split_tail_unit(window)
    cur = unit + tail
    s = window[: len(window) - len(cur)]
    delim = symbols.breaks()
    mid = ""
    while s and s[-1] in delim:
        mid = s[-1] + mid
        s = s[:-1]
    idx = -1
    for ch in delim:
        p = s.rfind(ch)
        if p > idx:
            idx = p
    return s[idx + 1:], mid, cur


def split_next_unit(after: str):
    delim = symbols.breaks()
    i = 0
    while i < len(after) and after[i] in delim:
        i += 1
    mid = after[:i]
    j = i
    while j < len(after) and after[j] not in delim:
        j += 1
    return mid, after[i:j]
