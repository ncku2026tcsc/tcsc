# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""版本號單一來源（single source of truth）。

只改這裡，下列全部跟著更新，不會再有「標題卡舊版本」的問題：
  - APP_TITLE（tray_app_v12.py / app_exe.py）＝ f"繁中自動選字 {VERSION}"（通知標題 / tray tooltip / 說明標題）
  - build_exe.ps1 的打包版本（zip 檔名）＝ 讀本檔的 VERSION
發新版時：改這一行 → 重建即可。
"""
VERSION = "v2.63"   # auto學字改 approach 1：換新句才結算學最後答案（不在中途學）；框同步
