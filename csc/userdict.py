# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""使用者自學詞庫（F2 反白學詞）。檔案：data/userforce.txt。

每行： 詞 <TAB> 注音空白分隔 <TAB> tier(soft|hard)
  - 一個詞可能有多行（多音字 → 多個注音序列，全部登錄，命中任一即可）。
  - tier 由 wordphon 映射成詞頻高度（soft=中高先驗、hard=凌駕），故不必改評分程式。

兩段式（依使用者定案）：
  - 第一次學某詞 → soft（強先驗，通常贏但 BERT 仍可翻盤）。
  - 對同一詞再學一次 → 升級 hard（讀音吻合就強制勝出）。
  - 單字不開放 hard（裸字會過度修正，如 ㄘㄨㄟˋ 全變「脆」會把「翠綠」改壞）。
注音用「每字所有讀音的乘積」登錄（多音字也命中），與 segmenter 候選生成同源。
"""
import os

from . import phonetics

_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_FILE = os.path.join(_DIR, "userforce.txt")
_CAP = 8   # 多音字讀音組合上限


def derive_seqs(word: str):
    """回傳該詞的所有注音序列（每字讀音的乘積，cap 上限）。含無注音字元則回 []。"""
    per = [sorted(phonetics.readings(c)) for c in word]
    if not per or any(not r for r in per):
        return []
    seqs = [()]
    for rs in per:
        seqs = [s + (r,) for s in seqs for r in rs][:_CAP]
    return seqs


def _read_rows():
    rows = []
    if not os.path.exists(_FILE):
        return rows
    with open(_FILE, encoding="utf-8") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) >= 3 and p[0]:
                rows.append((p[0], p[1], p[2]))
    return rows


def _write_rows(rows):
    os.makedirs(_DIR, exist_ok=True)
    with open(_FILE, "w", encoding="utf-8") as f:
        for word, reads, tier in rows:
            f.write(f"{word}\t{reads}\t{tier}\n")


def entries_by_word() -> dict:
    """{詞: tier}（依首次出現順序）。"""
    out = {}
    for word, _reads, tier in _read_rows():
        out.setdefault(word, tier)
    return out


def learn(word: str):
    """學一個詞。回傳 (status, tier, msg)。
    status: ok / upgraded / nochar / single_no_hard / already_hard。"""
    word = word.strip()
    seqs = derive_seqs(word)
    if not seqs:
        return ("nochar", None, "含沒有注音的字元（英數/emoji），無法學習")

    by_word = entries_by_word()
    if word not in by_word:
        tier, status = "soft", "ok"
    elif by_word[word] == "soft":
        if len(word) == 1:
            return ("single_no_hard", "soft", "單字不開放升級為強制（會把同音的其他詞改壞）")
        tier, status = "hard", "upgraded"
    else:
        return ("already_hard", "hard", "已是強制等級")

    rows = [r for r in _read_rows() if r[0] != word]            # 移除舊的同詞列
    for seq in seqs:
        rows.append((word, " ".join(seq), tier))
    _write_rows(rows)
    return (status, tier, "")


def remove(word: str) -> bool:
    rows = _read_rows()
    kept = [r for r in rows if r[0] != word]
    if len(kept) == len(rows):
        return False
    _write_rows(kept)
    return True


def clear() -> int:
    n = len(entries_by_word())
    _write_rows([])
    return n
