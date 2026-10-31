# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/tcsc2026/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import itertools

GROUPS = ("的得地", "在再")
ZAI = ("在再",)
MAX_POS = 3
FIXED = ("覺得 記得 值得 獲得 得到 取得 懂得 曉得 難得 得分 得意 心得 免得 捨得 顯得 使得 贏得 不得 得了 "
         "地方 地點 地區 地址 地圖 地球 地上 地下 土地 當地 本地 各地 場地 基地 天地 地位 地鐵 地震 地板 地面 "
         "目的 的確 的士 標的 "
         "現在 存在 實在 在乎 自在 所在 在意 在職 正在 好在 內在 外在 潛在 在於 "
         "再見 再三 再次 再度 再生 再者").split()


def positions(text, groups=GROUPS):
    locked = set()
    for w in FIXED:
        start = text.find(w)
        while start >= 0:
            locked.update(range(start, start + len(w)))
            start = text.find(w, start + 1)
    out = [(i, g) for i, ch in enumerate(text) for g in groups if ch in g and i not in locked]
    return out[-MAX_POS:]


def variants(text, groups=GROUPS):
    pos = positions(text, groups)
    out = []
    for combo in itertools.product(*[g for _i, g in pos]):
        s = list(text)
        for (i, _g), ch in zip(pos, combo):
            s[i] = ch
        s = "".join(s)
        if s != text:
            out.append(s)
    return out
