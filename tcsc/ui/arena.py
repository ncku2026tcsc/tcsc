# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/tcsc2026/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
_SUB = "₀₁₂₃₄₅₆₇₈₉"


def _sub(n):
    return "".join(_SUB[int(d)] for d in str(n))


def diff_slots(orig, cand):
    if len(orig) != len(cand):
        return None
    return [i for i, (a, b) in enumerate(zip(orig, cand)) if a != b]


def single_slot(orig, ranked):
    slot = None
    for c in ranked:
        d = diff_slots(orig, c)
        if d is None:
            return None
        if not d:
            continue
        if len(d) != 1:
            return None
        if slot is None:
            slot = d[0]
        elif slot != d[0]:
            return None
    return slot


DEAD = "·"


def label(orig, cand):
    d = diff_slots(orig, cand)
    if d is None:
        return None
    return "".join(cand[i] for i in d) if d else "原"


def board(orig, ranked, idx=0, dead=(), max_show=12, numbered=True):
    seen, cells, n_show = set(), [], 0
    for n, c in enumerate(ranked):
        lb = label(orig, c)
        if lb is None:
            return None
        if lb in seen:
            continue
        seen.add(lb)
        n_show += 1
        if n_show > max_show:
            cells.append("…")
            break
        if n in dead:
            cells.append(DEAD)
        elif n == idx:
            cells.append(f"[{lb}]")
        elif not numbered:
            cells.append(lb)
        else:
            step = (n - idx) % max(1, len(ranked))
            cells.append(lb + (_sub(step) if step else ""))
    return " ".join(cells)


def arena(orig, ranked, idx=0, dead=(), max_show=8, numbered=True):
    slot = single_slot(orig, ranked)
    if slot is None:
        return None
    seen, cells = set(), []
    for n, c in enumerate(ranked):
        ch = orig[slot] if not diff_slots(orig, c) else c[slot]
        if ch in seen:
            continue
        seen.add(ch)
        if n in dead:
            cells.append(ch + "̶")
        elif n == idx:
            cells.append(f"[{ch}]")
        elif not numbered:
            cells.append(ch)
        else:
            step = (n - idx) % max(1, len(ranked))
            cells.append(ch + (_sub(step) if step else ""))
        if len(cells) >= max_show:
            cells.append("…")
            break
    return " ".join(cells)


def drawn(orig, ranked, max_show=12):
    seen, out = set(), []
    for n, c in enumerate(ranked):
        lb = label(orig, c)
        if lb is None or lb in seen:
            continue
        seen.add(lb)
        out.append(n)
        if len(out) >= max_show:
            break
    return out


def beat1(orig, ranked):
    return board(orig, ranked, idx=-1, dead=(), numbered=False)


def beat2(orig, ranked, alive):
    dead = {i for i in range(len(ranked)) if i not in alive}
    return board(orig, ranked, idx=-1, dead=dead, numbered=False)


def beat3(orig, ranked, idx=0):
    from . import editfmt
    cur = ranked[idx]
    ch = editfmt.diff(orig, cur)
    head = editfmt.fmt_edits(ch) if ch else "原句不動"
    return head, board(orig, ranked, idx=idx)
