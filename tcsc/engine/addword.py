# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/tcsc2026/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import itertools
import math

from . import phonetics

_FONT = "Microsoft JhengHei"
MAX_GEN = 4096


def reading_combos(word: str):
    from . import reading_filter, wordphon
    w = reading_filter._compute_weights()
    per = [sorted(phonetics.raw_readings(c) or phonetics.readings(c), key=lambda r, c=c: -w.get(c, {}).get(r, 0))
           for c in word]
    if not all(per):
        return []

    def score(seq):
        return sum(math.log1p(w.get(c, {}).get(r, 0)) for c, r in zip(word, seq))
    known = [tuple(s) for s in wordphon.seqs_of(word) if len(s) == len(word)]
    rest = [tuple(x) for x in itertools.islice(itertools.product(*per), MAX_GEN) if tuple(x) not in known]
    return sorted(known, key=lambda s: -score(s)) + sorted(rest, key=lambda s: -score(s))


def parse_reading(text: str, word: str):
    seq = tuple(text.split())
    if len(seq) != len(word):
        return None
    for syl in seq:
        if not any(0x3105 <= ord(c) <= 0x3129 for c in syl):
            return None
        if any(not (0x3105 <= ord(c) <= 0x3129 or c in "ˊˇˋ˙") for c in syl):
            return None
    return seq
