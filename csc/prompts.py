# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""f1~f4 四種 prompt 實驗條件的 user-message 建構器。

f1：baseline（直接修正，zero-shot）            —— 可部署
f2：+ 告知錯字數量 N（使用黃金答案）           —— oracle 上界，不可當部署效能
f3：分段 + 前文視窗（由 pipeline 負責切割）     —— 可部署
f4：+ 混淆集候選字提示                          —— 可部署
"""
from .confusion import format_hint


def build_f1(sentence: str) -> str:
    return f"請改正下面句子中的錯字，只輸出改正後的句子：\n{sentence}"


def build_f2(sentence: str, n_errors: int) -> str:
    if n_errors == 0:
        return f"下面這句話「沒有錯字」，請原樣輸出，不要更動任何字：\n{sentence}"
    return (
        f"下面這句話剛好有 {n_errors} 個錯字。"
        f"請只改正這 {n_errors} 個錯字，其餘字保持不變，只輸出改正後的句子：\n{sentence}"
    )


def build_f3_segment(segment: str, left_context: str) -> str:
    ctx = f"（前文參考：…{left_context}）\n" if left_context else ""
    return (
        "請只改正下面這個片段中的錯字，輸出改正後的「片段」即可，"
        f"長度需與原片段完全相同：\n{ctx}片段：{segment}"
    )


def build_f4(sentence: str) -> str:
    hints = format_hint(sentence)
    hint_line = f"候選字參考：{hints}\n" if hints else ""
    return (
        "請改正下面句子中的錯字。若某字疑似錯字，"
        "請優先從其「音近/形近候選字」中挑選最合理者，並保持句子長度不變。"
        f"只輸出改正後的句子：\n{hint_line}句子：{sentence}"
    )
