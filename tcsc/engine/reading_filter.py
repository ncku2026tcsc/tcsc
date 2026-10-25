# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
from collections import defaultdict

from . import phonetics, wordphon

_weights = None
_active_cache = {}


def _compute_weights():
    global _weights
    if _weights is not None:
        return _weights
    wordphon._load()
    phonetics._load()
    w = defaultdict(lambda: defaultdict(float))
    for word, seqs in wordphon._word2seqs.items():
        if len(word) < 2:
            continue
        f = wordphon._freq.get(word, 0)
        for seq in seqs:
            if len(seq) != len(word):
                continue
            for ch, r in zip(word, seq):
                w[ch][r] += f
    _weights = w
    return w


def active_readings(ch: str, ratio: float = 0.02) -> set:
    key = (ch, ratio)
    if key in _active_cache:
        return _active_cache[key]
    allr = phonetics.readings(ch)
    ws = _compute_weights().get(ch)
    if not ws:
        out = set(allr)
    else:
        mx = max(ws.values())
        if mx <= 0:
            out = set(allr)
        else:
            out = {r for r in allr if ws.get(r, 0) >= mx * ratio}
            if not out:
                cand = {r: v for r, v in ws.items() if r in allr and v > 0}
                out = {max(cand, key=cand.get)} if cand else set(allr)
    out |= (phonetics.extra_readings(ch) & allr)
    _active_cache[key] = out
    return out


def same_sound(a: str, b: str, ratio: float = 0.02) -> bool:
    ra, rb = active_readings(a, ratio), active_readings(b, ratio)
    return bool(ra and rb and (ra & rb))


SENTENCE_FINAL_PARTICLES = set("嗎呢吧啊啦喔嘛唷耶哦欸喲囉咧呀哇咯嘍")
_MAMA = frozenset("嗎嘛")
_TARGETS_NO_MAMA = frozenset(SENTENCE_FINAL_PARTICLES - _MAMA)


def _guard_targets():
    try:
        from .. import settings
        if settings.get("unguard_mama"):
            return _TARGETS_NO_MAMA
    except Exception:
        pass
    return SENTENCE_FINAL_PARTICLES


def is_guarded_particle(clause: str, i: int, strict: bool = False) -> bool:
    targets = SENTENCE_FINAL_PARTICLES if strict else _guard_targets()
    if clause[i] not in targets:
        return False
    return all(c in SENTENCE_FINAL_PARTICLES for c in clause[i + 1:])
