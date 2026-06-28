# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""詞級同音索引：McBopomofo 詞庫 (BPMFMappings.txt) + 詞頻 (phrase.occ)。

BPMFMappings.txt 每行： 詞 注音1 注音2 …（含聲調，空白分隔）
phrase.occ      每行： 詞 出現次數

提供：
  reading_seqs(word)            -> {注音序列 tuple}
  homophone_words(word, limit)  -> [同音詞]（注音序列完全相同、依詞頻排序、不含自身）
  freq(word)                    -> 詞頻
純繁體（big5 來源）、含聲調。
"""
import os

_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_MAP = os.path.join(_DIR, "BPMFMappings.txt")
_OCC = os.path.join(_DIR, "phrase.occ")
_USER = os.path.join(_DIR, "userwords.txt")   # 使用者造詞（高優先）
_USERWORD_FREQ = 2000
_USERFORCE = os.path.join(_DIR, "userforce.txt")   # F2 自學詞（兩段式）
_SOFT_FREQ = 3000              # soft：中高先驗（通常贏、BERT 仍可翻盤）
_HARD_FREQ = 1_000_000_000     # hard：凌駕（log≈20.7，蓋過 BERT 流暢度）

_word2seqs: dict = {}   # 詞 -> {注音序列 tuple}
_seq2words: dict = {}   # 注音序列 tuple -> [詞]
_freq: dict = {}        # 詞 -> 次數
_userforce_freq: dict = {}   # 自學詞 -> 額外詞頻（與 _freq 分開，方便熱重載/移除）
_uf_pool: list = []          # 自學詞加進 _seq2words 的 (詞, seq)，供乾淨重載
_loaded = False


def _load() -> None:
    global _loaded
    if _loaded:
        return
    if os.path.exists(_OCC):
        with open(_OCC, encoding="utf-8") as f:
            for line in f:
                p = line.split()
                if len(p) >= 2 and p[-1].lstrip("-").isdigit():
                    _freq[p[0]] = int(p[-1])
    with open(_MAP, encoding="utf-8") as f:
        for line in f:
            p = line.split()
            if len(p) < 2:
                continue
            word, seq = p[0], tuple(p[1:])
            if len(word) != len(seq):       # 詞字數需等於注音數
                continue
            seqs = _word2seqs.setdefault(word, set())
            if seq not in seqs:
                seqs.add(seq)
                _seq2words.setdefault(seq, []).append(word)
    for words in _seq2words.values():       # 同音詞依詞頻排序
        words.sort(key=lambda w: _freq.get(w, 0), reverse=True)
    _load_userwords()
    _apply_userforce()
    _loaded = True


def _load_userwords() -> None:
    """載入使用者造詞（data/userwords.txt：詞<TAB>注音空白分隔）。給高詞頻、排在候選最前。"""
    if not os.path.exists(_USER):
        return
    with open(_USER, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if "\t" not in line:
                continue
            word, reads = line.split("\t", 1)
            seq = tuple(reads.split())
            if not word or len(word) != len(seq):
                continue
            _word2seqs.setdefault(word, set()).add(seq)
            lst = _seq2words.setdefault(seq, [])
            if word in lst:
                lst.remove(word)
            lst.insert(0, word)                          # 造詞排最前（優先）
            if _freq.get(word, 0) < _USERWORD_FREQ:
                _freq[word] = _USERWORD_FREQ


def _apply_userforce() -> None:
    """讀 data/userforce.txt：把自學詞加進候選池(排最前) + 依 tier 給額外詞頻。"""
    if not os.path.exists(_USERFORCE):
        return
    with open(_USERFORCE, encoding="utf-8") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 3 or not p[0]:
                continue
            word, seq, tier = p[0], tuple(p[1].split()), p[2]
            if len(word) != len(seq):
                continue
            _word2seqs.setdefault(word, set()).add(seq)
            lst = _seq2words.setdefault(seq, [])
            if word in lst:
                lst.remove(word)
            lst.insert(0, word)                 # 自學詞排最前
            _uf_pool.append((word, seq))
            add = _HARD_FREQ if tier == "hard" else _SOFT_FREQ
            _userforce_freq[word] = max(_userforce_freq.get(word, 0), add)


def reload_userforce() -> None:
    """熱重載自學詞（F2 學完即時生效）：先撤掉上次套用的，再重讀。"""
    _load()
    for word, seq in _uf_pool:
        if word in _seq2words.get(seq, []):
            _seq2words[seq].remove(word)
        s = _word2seqs.get(word)
        if s:
            s.discard(seq)
    _uf_pool.clear()
    _userforce_freq.clear()
    _apply_userforce()


def reading_seqs(word: str) -> set:
    _load()
    return _word2seqs.get(word, set())


def homophone_words(word: str, limit: int = 15) -> list:
    _load()
    out, seen = [], {word}
    for seq in reading_seqs(word):
        for w in _seq2words.get(seq, []):
            if w not in seen:
                seen.add(w)
                out.append(w)
    return out[:limit]


def words_by_reading(seq) -> list:
    """給注音序列(tuple)，回傳該讀音的所有真詞（依詞頻排序）。
    用於把『打錯的非詞』(如 工課) 反查回同音的真詞 (功課)。"""
    _load()
    return _seq2words.get(tuple(seq), [])


def freq(word: str) -> int:
    _load()
    return _freq.get(word, 0) + _userforce_freq.get(word, 0)
