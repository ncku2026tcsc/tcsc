# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
GROUPS = [
    ("glyph_tai", ("台", "臺")),
    ("glyph_li", ("裡", "裏")),
    ("glyph_shen", ("什", "甚")),
    ("glyph_bu", ("布", "佈")),
    ("glyph_chi", ("痴", "癡")),
]

WORD_GROUPS = [
    ("glyph_kaoyao", ("靠夭", "靠腰", "靠么", "靠邀")),
]

_BU_WORDS = ["宣布", "公布", "發布", "頒布", "分布", "遍布", "密布", "散布",
             "擺布", "布局", "布署", "布置", "布陣", "布告", "布達", "布防"]

_BPMF = set(chr(c) for c in range(0x3105, 0x3130)) | set("ˊˇˋ˙ㆠㆡㆢ")


def fix_bpmf_yi(text: str) -> str:
    if not text or "ㄧ" not in text:
        return text
    out = list(text)
    for i, ch in enumerate(text):
        if ch != "ㄧ":
            continue
        prev = text[i - 1] if i > 0 else ""
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if prev in _BPMF or nxt in _BPMF:
            continue
        out[i] = "一"
    return "".join(out)


_BPMF_LETTERS = _BPMF - set("ˊˇˋ˙")


def fix_bpmf_tone(text: str) -> str:
    if not text or not any(c in "ˊˇˋ˙" for c in text):
        return text
    out = []
    for i, ch in enumerate(text):
        if ch in "ˊˇˋ˙":
            prev = text[i - 1] if i > 0 else ""
            nxt = text[i + 1] if i + 1 < len(text) else ""
            if prev not in _BPMF_LETTERS and nxt not in _BPMF_LETTERS:
                continue
        out.append(ch)
    return "".join(out)


def apply_pref(text: str, tai="", li="", shen="", bu="", chi="", words=None) -> str:
    if not text:
        return text
    for key, grp in WORD_GROUPS:
        tgt = (words or {}).get(key) or ""
        if tgt in grp:
            for w in grp:
                if w != tgt:
                    text = text.replace(w, tgt)
    if tai == "台":
        text = text.replace("臺", "台")
    elif tai == "臺":
        text = text.replace("台", "臺")
    if li == "裡":
        text = text.replace("裏", "裡")
    elif li == "裏":
        text = text.replace("裡", "裏")
    if shen == "什":
        text = text.replace("甚麼", "什麼")
    elif shen == "甚":
        text = text.replace("什麼", "甚麼")
    if bu == "布":
        text = text.replace("佈", "布")
    elif bu == "佈":
        for w in _BU_WORDS:
            text = text.replace(w, w.replace("布", "佈"))
    if chi == "痴":
        text = text.replace("癡", "痴")
    elif chi == "癡":
        text = text.replace("痴", "癡")
    return text
