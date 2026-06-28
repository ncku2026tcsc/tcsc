# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""文字單位/長度小工具（純函式，給 tray/exe 共用，避免兩邊各寫一份漂移）。

兩個 F1 bug 的修法基礎：
  - utf16_len：Windows 編輯框的游標多半按「UTF-16 單元」移動（emoji=2 單元），
    送 Shift+← 取代時要用這個數，否則 emoji 會選歪、消失。
  - split_tail_unit：游標停在標點上時，要先剝掉尾端標點往前看真正的字，
    並把尾端標點原樣保留（回填時不重打、不會被 IME 吃）。
"""

DELIM = "，。！？；：、,.!?;:　 \t\n"


def utf16_len(s: str) -> int:
    """字串的 UTF-16 碼元數（BMP=1，emoji/代理對=2）；對應 Windows 游標移動格數。"""
    return len(s.encode("utf-16-le")) // 2


def split_tail_unit(window: str):
    """回傳 (unit, tail)。
      tail ：尾端連續的標點/空白（游標停在標點上時就是這些）。
      unit ：tail 之前、上一個標點之後的那段（真正要修的字）。
    例：'你好嗎，' -> ('你好嗎', '，')；'城市，世界，' -> ('世界', '，')。"""
    tail = ""
    s = window
    while s and s[-1] in DELIM:
        tail = s[-1] + tail
        s = s[:-1]
    idx = -1
    for ch in DELIM:
        p = s.rfind(ch)
        if p > idx:
            idx = p
    return s[idx + 1:], tail
