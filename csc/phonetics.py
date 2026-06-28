# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""注音同音資料 —— 以 McBopomofo 的 BPMFBase.txt 為唯一來源。

來源：openvanilla/McBopomofo，Source/Data/BPMFBase.txt
特性（取代先前 pypinyin 方案的三個問題）：
  1. 全部 big5 編碼 => 純繁體，結構上不含簡體字
  2. 注音「含聲調」 => 同調同音才算同音，貼近新注音實際錯誤
  3. 同一讀音內大致依頻率排序 => 候選字直接取前 N 個即可

每行格式： 字 注音(含聲調) 拼音 頻欄 big5
例：       像 ㄒㄧㄤˋ xiang4 vu;4 big5
"""
import os

_DATA = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "BPMFBase.txt",
)

# 注音符號本身的 Unicode 範圍（ㄅ..ㄩ 等），用來略過字表裡的符號條目
_ZHUYIN = set(range(0x3105, 0x312E))

_char2readings: dict[str, set[str]] = {}   # 字 -> {含聲調注音}
_reading2chars: dict[str, list[str]] = {}  # 含聲調注音 -> [字]（檔案順序≈頻率）
_loaded = False


def _load(path: str = _DATA) -> None:
    global _loaded
    if _loaded:
        return
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"找不到注音字表 {path}；請先下載 McBopomofo 的 BPMFBase.txt 到 data/。"
        )
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) < 2:
                continue
            ch, bpmf = parts[0], parts[1]
            if len(ch) != 1 or ord(ch) in _ZHUYIN or ch == bpmf:
                continue  # 略過注音符號 / 標點等非漢字條目
            _char2readings.setdefault(ch, set()).add(bpmf)
            lst = _reading2chars.setdefault(bpmf, [])
            if ch not in lst:
                lst.append(ch)
    _loaded = True


def readings(ch: str) -> set:
    """回傳某字的所有含聲調注音（多音字會有多個）。"""
    _load()
    return _char2readings.get(ch, set())


def same_sound(a: str, b: str) -> bool:
    """兩字是否同音（含聲調，任一讀音相同即算）。"""
    _load()
    ra, rb = readings(a), readings(b)
    return bool(ra and rb and (ra & rb))


def homophones(ch: str, limit: int = 12) -> list:
    """回傳某字的同音候選字（純繁體、同聲調、依頻率），不含自身。"""
    _load()
    seen, out = {ch}, []
    for r in readings(ch):
        for c in _reading2chars.get(r, []):
            if c not in seen:
                seen.add(c)
                out.append(c)
    return out[:limit]
