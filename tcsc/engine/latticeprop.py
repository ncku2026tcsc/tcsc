# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import math

from .. import datafs as _datafs

MAX_EDITS = 3
TOP_PATHS = 3
KEEP_BONUS = 6.0
CAND_PER_POS = 8
DELTA = 0.0

_big = None


def _load():
    global _big
    if _big is None:
        _big = {}
        try:
            with _datafs.open_text("char_bigram.tsv") as f:
                for line in f:
                    if line.startswith("#"):
                        continue
                    p = line.rstrip("\n").split("\t")
                    if len(p) >= 2 and len(p[0]) == 2:
                        try:
                            _big[p[0]] = int(p[1])
                        except ValueError:
                            pass
        except Exception:
            pass
    return _big


def paths(clause, cands_at, top=TOP_PATHS):
    big = _load()
    n = len(clause)
    if not big or n < 2:
        return []
    opts = []
    for i, ch in enumerate(clause):
        cs = [ch] + [c for c in cands_at(i) if c != ch][:CAND_PER_POS]
        opts.append(cs)

    def tr(a, b):
        return math.log(1 + big.get(a + b, 0))

    layers = []
    layer = {}
    for ci, c in enumerate(opts[0]):
        e = 0 if c == clause[0] else 1
        if e <= MAX_EDITS:
            layer[(ci, e)] = ((KEEP_BONUS if e == 0 else 0.0), None)
    layers.append(layer)
    for i in range(1, n):
        nxt = {}
        for ci, c in enumerate(opts[i]):
            de = 0 if c == clause[i] else 1
            bonus = KEEP_BONUS if de == 0 else 0.0
            for (pci, pe), (psc, _bk) in layer.items():
                e = pe + de
                if e > MAX_EDITS:
                    continue
                sc = psc + tr(opts[i - 1][pci], c) + bonus
                key = (ci, e)
                if key not in nxt or sc > nxt[key][0]:
                    nxt[key] = (sc, (pci, pe))
        layer = nxt
        layers.append(layer)
        if not layer:
            return []

    best_per_e = {}
    s0 = None
    for key, (sc, _bk) in layer.items():
        e = key[1]
        if e == 0:
            s0 = sc if s0 is None else max(s0, sc)
        if e >= 1 and (e not in best_per_e or sc > best_per_e[e][0]):
            best_per_e[e] = (sc, key)
    out, seen = [], set()
    for e in sorted(best_per_e):
        sc, key = best_per_e[e]
        if DELTA is not None and s0 is not None and (s0 - sc) > DELTA + KEEP_BONUS * e:
            continue
        chars, k = [], key
        for i in range(n - 1, -1, -1):
            chars.append(opts[i][k[0]])
            k = layers[i][k][1]
        s = "".join(reversed(chars))
        if s != clause and s not in seen:
            seen.add(s)
            out.append((sc, s))
        if len(out) >= top:
            break
    return out
