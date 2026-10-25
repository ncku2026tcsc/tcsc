# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
def diff(a, b):
    if len(a) == len(b):
        return [(i, x, y) for i, (x, y) in enumerate(zip(a, b)) if x != y]
    import difflib
    return [(i1, a[i1:i2], b[j1:j2])
            for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
            if op != "equal"]


def fmt_edits(changes, group=None):
    triples = sorted(changes, key=lambda t: t[0])
    if group is None:
        group = True
    if not group:
        return "、".join(f"{a}→{b}" for _, a, b in triples)
    runs = []
    for i, a, b in triples:
        if runs and i == runs[-1][0] + 1:
            runs[-1][0] = i
            runs[-1][1] += a
            runs[-1][2] += b
        else:
            runs.append([i, a, b])
    return "、".join(f"{o}→{n or '（刪）'}" for _, o, n in runs)
