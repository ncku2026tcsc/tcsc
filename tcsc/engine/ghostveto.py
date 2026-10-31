# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/tcsc2026/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
from .. import datafs

P = 1.0
EXEMPT = "off"
_att = None


def _load():
    global _att
    if _att is None:
        _att = set()
        try:
            with datafs.open_text("char_bigram.tsv") as f:
                for line in f:
                    if line.startswith("#"):
                        continue
                    k = line.split("\t", 1)[0]
                    if len(k) == 2:
                        _att.add(k)
        except Exception:
            pass
    return _att


def _cjk(c):
    return c is not None and "一" <= c <= "鿿"


def pen(cand_ch, src_ch, left, right):
    att = _load()
    if not att:
        return 0.0
    lf = rf = 1.0
    if EXEMPT in ("half", "full"):
        from . import wordphon
        lw = _cjk(left) and wordphon.freq(left + cand_ch) > 0
        rw = _cjk(right) and wordphon.freq(cand_ch + right) > 0
        k = 0.0 if EXEMPT == "full" else 0.5
        if rw:
            lf = k
        if lw:
            rf = k
    total = 0.0
    if _cjk(left):
        if (left + cand_ch) in att:
            pass
        elif (left + src_ch) in att:
            total -= P * lf
        else:
            total -= P * 0.5 * lf
    if _cjk(right):
        if (cand_ch + right) in att:
            pass
        elif (src_ch + right) in att:
            total -= P * rf
        else:
            total -= P * 0.5 * rf
    return total
