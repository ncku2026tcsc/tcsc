# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""使用者自學詞庫（反白→F7 學詞）。檔案：%APPDATA%\\tcsc\\userforce.txt（exe）或專案 data/（原始碼）。

每行： 詞 <TAB> 注音空白分隔 <TAB> 段數(1~6)
  - 一個詞可能有多行（多音字 → 多個注音序列，全部登錄，命中任一即可）。
  - 段數由 wordphon 映射成「額外詞頻加成」，疊加在 BERT 流暢度分數上（BERT 不選字、只打分，
    最後總分高者贏）→ 加分可漸進，不必極端。

多段式（取代舊的 soft/hard 兩段）：
  - 每對同詞按一次 F7 → 段數 +1（詞頻 ×8、log 約 +2 分），逐步往上爬到贏，不一步跳極端。
  - 一律封頂 6 段（含單字；單字加太兇可能把同音其他詞改壞，但漸進可控，由使用者自行斟酌）。
  - 無痛遷移：舊檔的 soft→1 段、hard→6 段。
注音用「每字所有讀音的乘積」登錄（多音字也命中），與 segmenter 候選生成同源。
"""
import os

from . import phonetics
from .userpaths import userforce_path

_FILE = userforce_path()
_CAP = 8            # 多音字讀音組合上限
_MAX_LEVEL = 10    # 最高段（含單字）；2026-07-01 上限拉到 10


def derive_seqs(word: str):
    """回傳該詞的所有注音序列（每字讀音的乘積，cap 上限）。含無注音字元則回 []。"""
    per = [sorted(phonetics.readings(c)) for c in word]
    if not per or any(not r for r in per):
        return []
    seqs = [()]
    for rs in per:
        seqs = [s + (r,) for s in seqs for r in rs][:_CAP]
    return seqs


def _level_of(field: str) -> int:
    """欄位 → 段數（含舊格式遷移：soft→1、hard→6）。"""
    if field == "soft":
        return 1
    if field == "hard":
        return _MAX_LEVEL
    try:
        return max(1, min(_MAX_LEVEL, int(field)))
    except (ValueError, TypeError):
        return 1


def cap_for(word: str) -> int:
    return _MAX_LEVEL


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
    os.makedirs(os.path.dirname(_FILE), exist_ok=True)
    with open(_FILE, "w", encoding="utf-8") as f:
        for word, reads, lvl in rows:
            f.write(f"{word}\t{reads}\t{lvl}\n")


def entries_by_word() -> dict:
    """{詞: 段數}（依首次出現順序；舊 soft/hard 自動換算）。"""
    out = {}
    for word, _reads, field in _read_rows():
        if word not in out:
            out[word] = _level_of(field)
    return out


def learn(word: str):
    """學／加強一個詞。回傳 (status, level, msg)。
    status: ok（學了/加強了，level=新段數） / maxed（已達上限） / nochar。"""
    word = word.strip()
    seqs = derive_seqs(word)
    if not seqs:
        return ("nochar", None, "含沒有注音的字元（英數/emoji），無法學習")
    cur = entries_by_word().get(word, 0)
    cap = cap_for(word)
    if cur >= cap:
        return ("maxed", cur, f"已達最高強度 {cur}/{cap}")
    new = cur + 1
    rows = [r for r in _read_rows() if r[0] != word]            # 移除舊的同詞列
    for seq in seqs:
        rows.append((word, " ".join(seq), str(new)))
    _write_rows(rows)
    return ("ok", new, "")


def set_level(word: str, n: int) -> int:
    """把一個詞直接設成第 n 段（夾在 0~_MAX_LEVEL；0＝移除/忘記）。回傳實際設定的段數。
    供管理介面用 −/＋ 直接調等級（比連按 learn/demote 省事、且一次落地）。"""
    word = word.strip()
    n = max(0, min(_MAX_LEVEL, int(n)))
    rows = [r for r in _read_rows() if r[0] != word]           # 先移除舊的同詞列
    if n >= 1:
        for seq in derive_seqs(word):
            rows.append((word, " ".join(seq), str(n)))
    _write_rows(rows)
    return n


def demote(word: str) -> int:
    """降一段；降到 0 就移除（忘記）。回傳新段數（0=已移除）。"""
    cur = entries_by_word().get(word, 0)
    if cur <= 0:
        return 0
    new = cur - 1
    rows = [r for r in _read_rows() if r[0] != word]
    if new >= 1:
        for seq in derive_seqs(word):
            rows.append((word, " ".join(seq), str(new)))
    _write_rows(rows)
    return new


def _words_covering(text: str, diffs):
    """text 經 segment 後，覆蓋到任一差異位置的『詞』（去重、保序）。"""
    from . import segmenter
    out, seen = [], set()
    for (i0, i1, span, _w) in segmenter.segment(text):
        if span not in seen and any(i0 <= d < i1 for d in diffs):
            seen.add(span)
            out.append(span)
    return out


def _candidates_for(gold: str, i: int):
    """差異位置 i 附近（視窗 ±2，最多 5 字）的候選詞：**視窗內所有 1~4 字子字串都列**，去重。
    排序：含改動位置 i 的排前面、其餘在後；各組內 2/3/4 字詞優先、單字最後。
    為何不只列『含 i 的窗』：使用者要重挑詞邊界時，鄰近沒蓋到 i 的單字/雙詞（如『詞庫加分』改『加』
    時的『詞庫』『詞』『庫』『分』）也該能選——『有出現的字都應該在選項內』。"""
    lo = max(0, i - 2)
    hi = min(len(gold), i + 3)                         # 視窗 [lo, hi)
    cont, other, seen = [], [], set()
    for L in (2, 3, 4, 1):                             # 詞優先（2~4），單字最後
        for start in range(lo, hi - L + 1):
            w = gold[start:start + L]
            if not w or w in seen:
                continue
            seen.add(w)
            (cont if start <= i < start + L else other).append(w)
    return cont + other                               # 含改動位置 i 的排前面


def auto_learn_from_diff(wrong: str, gold: str):
    """雙向自動學詞 + 新詞待確認。回傳 {"up":[(詞,段,[候選...])], "down":[(詞,段)], "pending":[[候選...], ...]}。
       up 多帶一個『候選清單』：自動學常斷錯字，供系統匣「剛剛學的字」重挑（目前學到的擺第一）。
      - gold 差異處落在『詞庫有的多字詞』→ 直接升一段(up)。
      - 落在『單字單元』(＝詞庫沒有的新詞、邊界不明) → 不亂學，改列候選詞(pending)讓使用者選。
      - wrong 差異處的『本來就學過的詞』→ 降一段(down，制衡過度修正；降到 0 就忘掉)。
    防呆只看『同長度』：長度不同＝改寫/別句，跳過。不過濾讀音——一個字本就多種讀音、資料也未必齊全，
    逐字比同音會誤殺真正的修正（乏 ㄈㄚˊ→發 ㄈㄚ）；校正器選字本身也沒這層過濾。"""
    empty = {"up": [], "down": [], "pending": []}
    if not wrong or not gold or len(wrong) != len(gold):
        return empty
    diffs = [i for i in range(len(gold)) if wrong[i] != gold[i]]
    if not diffs:
        return empty
    from . import segmenter
    learned_before = set(entries_by_word())
    up, pending, seen_pos = [], [], set()
    for (i0, i1, span, _w) in segmenter.segment(gold):
        covered = [d for d in diffs if i0 <= d < i1]
        if not covered:
            continue
        if len(span) > 1:                              # 詞庫有的詞 → 直接學
            _st, lv, _msg = learn(span)
            if lv:
                cands = [span]                          # 重挑用候選：目前學到的詞擺第一
                for d in covered:
                    for c in _candidates_for(gold, d):
                        if c not in cands:
                            cands.append(c)
                up.append((span, lv, cands))
        else:                                          # 單字單元 → 新詞、邊界不明 → 列候選待確認
            for d in covered:
                if d not in seen_pos:
                    seen_pos.add(d)
                    pending.append(_candidates_for(gold, d))
    down = []
    for w in _words_covering(wrong, diffs):
        if w in learned_before:                        # 只降『本來就學過、這次卻害改錯』的詞
            down.append((w, demote(w)))
    return {"up": up, "down": down, "pending": pending}


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


def export_words(path: str) -> int:
    """把目前自學詞匯出成純文字『詞<TAB>等級』（每行一詞、依現有順序）。回傳匯出詞數。
    只匯出詞＋等級（不含注音序列）→ 匯入時在對方機器用 set_level 重新推導，跨機通用、人也看得懂。"""
    entries = entries_by_word()
    with open(path, "w", encoding="utf-8") as f:
        for word, lv in entries.items():
            f.write(f"{word}\t{lv}\n")
    return len(entries)


def import_words(path: str):
    """從檔匯入自學詞；**同詞取較高等級**（不會把既有較高值降下來）。回傳 (新增, 提升, 不變)。
    相容三種行格式：`詞`、`詞<TAB>等級`、`詞<TAB>注音<TAB>段數`（舊 userforce）——一律取詞＋最後一欄當等級。
    檔內若同詞多行（如多音字 userforce）也先取檔內較高，再與現有比較。"""
    parsed = {}                                    # {詞: 檔內較高等級}
    with open(path, encoding="utf-8") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            word = (p[0] if p else "").strip()
            if not word:
                continue
            field = p[-1] if len(p) >= 2 else "1"  # 兩欄→等級、三欄→段數、單欄→預設 1
            parsed[word] = max(parsed.get(word, 0), _level_of(field))
    cur = entries_by_word()
    added = raised = same = 0
    for word, lv in parsed.items():
        old = cur.get(word, 0)
        new = max(old, lv)                         # 重複取較高等級
        if new == old:
            same += 1
            continue
        if set_level(word, new) >= 1:              # 推導得到注音序列才算數（含無注音字則跳過）
            raised += 1 if old else 0
            added += 0 if old else 1
        else:
            same += 1                              # 無法推導（英數/emoji）→ 視為不變
    return (added, raised, same)
