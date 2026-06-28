# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""自建『讀音斷詞器』（不靠 jieba）。

原理：注音錯字「唸對、選錯」，所以讀音序列可靠、字才錯。
於是用每字讀音 + McBopomofo 詞庫，對「讀音序列」做 DAG 最佳路徑斷詞
（最大化選到的真詞之詞頻和），即使字打錯了也能正確切出單位
（工課 → 一個單位，讀音 ㄍㄨㄥ ㄎㄜˋ 命中真詞 功課/公克/攻克）。

segment(text) -> [(start, end, span, cand_words)]
  span        ：原字串片段
  cand_words  ：與該片段同音的真詞清單（依詞頻，含/不含原 span 皆可能）；單字單位為 None
"""
import math

from . import phonetics, wordphon

_SINGLE_SCORE = 0.5   # 單字 fallback 的基礎分


def _span_reading_words(span: str):
    """這個 span 依其讀音對應到的同長度真詞（依詞頻排序）。空=不像任何詞。"""
    per = [sorted(phonetics.readings(c)) for c in span]
    if any(not r for r in per):
        return []
    seqs = [()]
    for rs in per:
        seqs = [s + (r,) for s in seqs for r in rs][:12]   # cap 多音字組合
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
    info = [None] * (n + 1)   # info[j] = (span, cand_words or None)

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
                score = math.log(1 + f)        # 偏好高詞頻真詞
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
