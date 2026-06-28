# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""候選端的兩道『手術刀』，不動原始字表、可開關、可量化驗證。

(1) 多音字收斂 active_readings(ch, ratio)：
    用詞庫(2 字以上真詞)反推每個字各讀音的『詞頻加權使用量』，
    砍掉幾乎沒有任何詞在用的『奇怪讀音』。只影響候選產生，不碰 BPMFBase。
    例：解=ㄐㄧㄝˇ(30817)/ㄐㄧㄝˋ(19)/ㄒㄧㄝˋ(0) → 只留 ㄐㄧㄝˇ，斷開「解→界」。

(2) 句尾語助詞守門：句尾的 嗎/呢/吧/啊… 幾乎不可能是別的字，
    直接擋掉對它的同音替換（零龜縮：沒有任何正當修正會被擋）。
"""
from collections import defaultdict

from csc import phonetics, wordphon

_weights = None          # ch -> {reading: 詞頻加權}
_active_cache = {}       # (ch, ratio) -> set(readings)


def _compute_weights():
    global _weights
    if _weights is not None:
        return _weights
    wordphon._load()
    phonetics._load()
    w = defaultdict(lambda: defaultdict(float))
    for word, seqs in wordphon._word2seqs.items():
        if len(word) < 2:                       # 單字不算讀音證據
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
    """該字『實際有人用』的讀音集合。詞庫裡完全沒出現的字 → 全保留（無證據不亂砍）。"""
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
            if not out:                          # 保底：至少留最常用的那個讀音
                out = {max(ws, key=ws.get)}
    _active_cache[key] = out
    return out


def same_sound(a: str, b: str, ratio: float = 0.02) -> bool:
    """收斂版同音：兩字的『實際讀音』集合有交集才算同音。"""
    ra, rb = active_readings(a, ratio), active_readings(b, ratio)
    return bool(ra and rb and (ra & rb))


# ---- 句尾語助詞守門 ----
SENTENCE_FINAL_PARTICLES = set("嗎呢吧啊啦喔嘛唷耶哦欸喲囉咧呀哇")


def is_guarded_particle(clause: str, i: int) -> bool:
    """clause 第 i 個字是不是『句尾語助詞』：它本身是助詞，且其後到子句尾都是助詞。"""
    if clause[i] not in SENTENCE_FINAL_PARTICLES:
        return False
    return all(c in SENTENCE_FINAL_PARTICLES for c in clause[i + 1:])
