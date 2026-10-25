# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import math

from . import phonetics, wordphon
from .. import config

_SINGLE_SCORE = 0.5
_SEQ_CAP = 64


def _span_reading_words(span: str, unlock=frozenset()):
    own = wordphon.seqs_of(span)
    src_word = bool(own) and config.ENGINE.get("word_escape_src_word", True)
    if config.ENGINE.get("word_escape_raw", True):
        locked = config.ENGINE.get("word_escape_locked", "")
        per = []
        for j, c in enumerate(span):
            act = sorted(phonetics.readings(c))
            if c in locked and j not in unlock:
                per.append(act)
            elif src_word:
                per.append(act)
            else:
                per.append(act + sorted(phonetics.raw_readings(c) - set(act)))
    else:
        per = [sorted(phonetics.readings(c)) for c in span]
    if any(not r for r in per):
        return []
    seqs = [()]
    for rs in per:
        seqs = [s + (r,) for s in seqs for r in rs][:_SEQ_CAP]
    for s in own:
        if s not in seqs:
            seqs.append(s)
    seen, out = set(), []
    for seq in seqs:
        for w in wordphon.words_by_reading(seq):
            if len(w) == len(span) and w not in seen:
                seen.add(w)
                out.append(w)
    return out


def segment(text: str, max_word_len: int = 4):
    n = len(text)
    if n == 0:
        return []
    NEG = float("-inf")
    best = [NEG] * (n + 1)
    best[0] = 0.0
    back = [-1] * (n + 1)
    info = [None] * (n + 1)

    for j in range(1, n + 1):
        for L in range(1, min(max_word_len, j) + 1):
            i = j - L
            span = text[i:j]
            if L == 1:
                score, words = _SINGLE_SCORE, None
            else:
                words = _span_reading_words(span)
                if not words:
                    continue
                f = max(wordphon.freq(w) for w in words)
                score = math.log(1 + f)
            if best[i] + score > best[j]:
                best[j] = best[i] + score
                back[j] = i
                info[j] = (span, words)

    units = []
    j = n
    while j > 0:
        i = back[j]
        span, words = info[j]
        units.append((i, j, span, words))
        j = i
    units.reverse()
    return units
