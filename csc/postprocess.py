# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""輸出後處理：清乾淨 + 強制等長。

這是用 LLM 做 CSC 的關鍵一步——LLM 天性會改寫/增刪字，
但 CSC 假設輸入輸出等長、只替換。這裡把輸出強制對齊回原句長度。
"""
import difflib


def clean_output(text: str) -> str:
    """取第一個非空行，去除引號與前後空白。"""
    if not text:
        return ""
    for line in text.strip().splitlines():
        line = line.strip()
        if line:
            return line.strip("「」『』\"' 　").strip()
    return ""


def enforce_same_length(src: str, pred: str):
    """回傳 (與 src 等長的修正字串, raw_length_mismatch)。

    只套用「等長替換」區塊；任何增刪或不等長替換一律還原為原字，
    確保輸出長度 == len(src)。raw_length_mismatch 表示模型原始輸出長度
    與原句不同（可用於分析 LLM 過度改寫的比例）。
    """
    raw_mismatch = (len(pred) != len(src))
    if not raw_mismatch:
        return pred, False

    sm = difflib.SequenceMatcher(a=src, b=pred, autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            out.append(src[i1:i2])
        elif tag == "replace" and (i2 - i1) == (j2 - j1):
            out.append(pred[j1:j2])          # 等長替換，安全採用
        else:
            out.append(src[i1:i2])           # 增/刪/不等長 -> 保留原字
    result = "".join(out)
    if len(result) != len(src):              # 保底：完全還原
        return src, True
    return result, True
