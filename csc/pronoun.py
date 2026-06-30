# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""目標人稱用字偏好：把校正後文字裡的代名詞，強制換成使用者指定的字。

UI＝7 個字、分兩組、各勾一個：
  ㄋㄧˇ 組：你 / 妳
  ㄊㄚ  組：他 / 她 / 它 / 牠 / 祂
兩組獨立（pron_ni、pron_ta）。為什麼用「強制字串替換 + 黑名單」而非詞頻加分/斷詞器：
  - 詞頻加分翻不動、大加分又誤改「吉他→吉她」；斷詞器把「愛他」併詞漏換、「維他命」誤切誤換。
  - 強制替換最可控；黑名單擋掉 其他/吉他/維他命… 即 100% 準。
人稱目標只換「同類」：選 他/她 只在 他↔她 之間換（不動 它/牠/祂）；選 牠 才把 他她它→牠。
"""

NI = ["你", "妳"]
TA = ["他", "她", "它", "牠", "祂"]

# 選定某字後，要把哪些「同音同類」字換成它（不亂換不相干的指稱）
_NI_MAP = {"你": {"妳": "你"}, "妳": {"你": "妳"}}
_TA_MAP = {
    "他": {"她": "他"},                                  # 一般／男性人稱
    "她": {"他": "她"},                                  # 女性人稱
    "它": {"他": "它", "她": "它"},                      # 物
    "牠": {"他": "牠", "她": "牠", "它": "牠"},           # 獸
    "祂": {"他": "祂", "她": "祂"},                      # 神
}

# 非代名詞詞：詞裡的「你/他/它」是構詞用字、不是代名詞 → 不替換
_BLOCK = [
    "其他", "其它", "吉他", "維他命", "他人", "他鄉", "他日", "利他", "排他",
    "他者", "他律", "他山之石", "他國", "他方", "他處", "他殺", "他遷", "他用",
    "迷你",
]


def apply_pref(text: str, ni: str = "", ta: str = "") -> str:
    """把 text 裡『不在黑名單詞內』的代名詞，依 ni（你/妳）、ta（他她它牠祂）強制替換。
    ni/ta 空字串＝該組不動。純字串替換，不靠 BERT/詞頻。"""
    mapping = {}
    if ni in _NI_MAP:
        mapping.update(_NI_MAP[ni])
    if ta in _TA_MAP:
        mapping.update(_TA_MAP[ta])
    if not text or not mapping:
        return text
    protected = [False] * len(text)
    for w in _BLOCK:                       # 標記黑名單詞佔用的位置（這些不換）
        start = 0
        while True:
            idx = text.find(w, start)
            if idx < 0:
                break
            for k in range(idx, idx + len(w)):
                protected[k] = True
            start = idx + 1
    out = list(text)
    for i, ch in enumerate(text):
        if not protected[i] and ch in mapping:
            out[i] = mapping[ch]
    return "".join(out)
