# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""簡易混淆集 (confusion set)：音近 / 形近字群組。

注意：這是「示範用」的小型內建集，用來展示 f4（混淆集提示）條件。
正式實驗時，請以完整混淆集取代 CONFUSION_GROUPS，例如：
  - SIGHAN 官方 confusion set
  - 用 pypinyin 取同音字 + 字形相似度（部件/筆畫）自建
介面 candidates() / format_hint() 不需更動。
"""

# 每一組內的字彼此音近或形近，常被混用。
CONFUSION_GROUPS = [
    "在再", "的得地", "做作坐座", "己已巳", "校效較笑孝", "籃藍籣攔欄",
    "飄漂瓢", "工功攻公", "趣取去", "須需鬚", "帳賬脹漲",
    "練鍊煉", "即既", "渡度踱鍍", "辨辦辯瓣辮", "候後后",
    "部步埠", "彩採睬踩綵", "賞償", "暴爆曝瀑", "進近晉",
    "包飽抱胞", "份分紛芬", "象像橡", "原源緣園圓", "畢必碧",
    "型形", "錄綠祿碌", "歷曆瀝", "權勸", "嚴顏",
    "燥躁澡", "幅福輻", "末未", "土士", "戊戌戍",
]

# 反向索引：字 -> 同組其餘候選字
_CHAR2CANDS: dict[str, set[str]] = {}
for _g in CONFUSION_GROUPS:
    for _c in _g:
        _CHAR2CANDS.setdefault(_c, set()).update(x for x in _g if x != _c)


def candidates(ch: str) -> list[str]:
    """回傳某字的音近/形近候選字（不含自身）。"""
    return sorted(_CHAR2CANDS.get(ch, set()))


def format_hint(sentence: str) -> str:
    """為句中出現、且在混淆集裡的字，產生精簡候選提示字串。"""
    parts, seen = [], set()
    for ch in sentence:
        if ch in _CHAR2CANDS and ch not in seen:
            seen.add(ch)
            parts.append(f"{ch}→[{'、'.join(candidates(ch))}]")
    return "；".join(parts)
