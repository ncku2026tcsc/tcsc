# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""注音輸入法錯字校正引擎。

模式：
  - 自動：correct(text)
  - 提示：correct(text, look_back=n, n_errors=m)
          look_back = 錯字在「最後 n 個字」之內（對應按 F<n>）
          n_errors  = 範圍內剛好 m 個錯（對應再按 F<m>）

防呆（guard）：IME 錯字一定是同音字，所以任何「非同音」的改寫一律擋下，
還原為原字——這能擋住 LLM 把詞語整個改寫（如 學效→學習）的毛病。
"""
from dataclasses import dataclass, field

from .model import LlamaCorrector
from .postprocess import clean_output, enforce_same_length
from . import phonetics

SYSTEM = (
    "你是繁體中文「注音輸入法選字校正」助手。"
    "使用者用注音打字，可能把字選成『同音的別字』（例如 在/再、效/校、記/計）。"
    "你的工作是把選錯的同音字改回正確的字。嚴格規則："
    "(1) 只能把字替換成『讀音相同』的字；"
    "(2) 不可改寫詞語、不可增字或刪字、不可更動沒打錯的字；"
    "(3) 句子長度需與原句完全相同。"
    "只輸出改正後的完整句子，不要任何解釋、引號或多餘文字。"
)


@dataclass
class Change:
    pos: int          # 0-based 位置
    src: str          # 原字
    dst: str          # 改成的字
    homophone: bool   # 是否同音


@dataclass
class Result:
    text: str
    corrected: str
    changes: list = field(default_factory=list)
    rejected: list = field(default_factory=list)
    raw: str = ""

    @property
    def changed(self) -> bool:
        return self.corrected != self.text


def _build_user(text: str, look_back, n_errors) -> str:
    lines = []
    if look_back is not None:
        lines.append(f"錯字就在「最後 {look_back} 個字」之內，其餘部分正確、請勿更動。")
    if n_errors is not None:
        if n_errors == 0:
            lines.append("這句話沒有打錯字，請原樣輸出。")
        else:
            lines.append(f"這裡面剛好有 {n_errors} 個字打錯（皆為選錯的同音字）。")
    lines.append("請改正並只輸出完整句子：")
    lines.append(text)
    return "\n".join(lines)


class Corrector:
    def __init__(self, model=None, **kw):
        self.model = model if model is not None else LlamaCorrector(**kw)

    def correct(self, text: str, look_back=None, n_errors=None, guard: bool = True) -> Result:
        text = text.strip()
        if not text:
            return Result(text, text)

        user = _build_user(text, look_back, n_errors)
        raw = self.model.chat(user, system=SYSTEM, max_tokens=len(text) + 32)
        aligned, _ = enforce_same_length(text, clean_output(raw))

        n = len(text)
        win_lo = n - look_back if look_back else 0
        out = list(text)
        changes, rejected = [], []
        for i, (a, b) in enumerate(zip(text, aligned)):
            if a == b:
                continue
            c = Change(i, a, b, phonetics.same_sound(a, b))
            if (i >= win_lo) and (c.homophone or not guard):
                out[i] = b
                changes.append(c)
            else:
                rejected.append(c)   # 非同音、或超出提示範圍 -> 擋下
        return Result(text, "".join(out), changes, rejected, raw)
