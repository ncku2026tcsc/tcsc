# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""改字通知的「差異字串」格式化（v2.3b 實驗：通知合併顯示）。

舊（v2.3a，預設）：每個被改的字各自一段 →「勿→物、鞭→鞕」。
新（notify_group=True）：相鄰（連續位置）的改動黏成一段 →「勿鞭→物鞕」；
不相鄰的仍分開 →「勿鞭→物鞕、客→刻」。

差異資料同源（changes 帶的位置 index），這裡只決定「怎麼印」，純視覺，
不影響校正結果、也不影響寫進 logs 的內容。預設關；使用者在系統匣勾選才開，
存進 %APPDATA%\\tcsc\\settings.json（release 不含此檔 → 公眾吃預設關）。
"""


def fmt_edits(changes, group=None):
    """changes：可疊代的 (index, 原字, 新字)。回傳「原→新、…」字串。

    group=None → 讀設定 notify_group；False＝逐字分開（舊行為，逐位元等同）；
    True＝把位置相鄰的改動黏成一段。
    """
    triples = sorted(changes, key=lambda t: t[0])
    if group is None:
        try:
            from . import settings
            group = bool(settings.get("notify_group", False))
        except Exception:
            group = False
    if not group:
        return "、".join(f"{a}→{b}" for _, a, b in triples)
    runs = []                                   # 每段：[結尾index, 原字串, 新字串]
    for i, a, b in triples:
        if runs and i == runs[-1][0] + 1:       # 緊接上一段 → 黏在一起
            runs[-1][0] = i
            runs[-1][1] += a
            runs[-1][2] += b
        else:
            runs.append([i, a, b])
    return "、".join(f"{o}→{n}" for _, o, n in runs)
