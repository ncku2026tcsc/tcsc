# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""開機自動啟動（可逆）：寫/刪 HKCU 的 Run 機碼。

HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run 是**每使用者**的開機啟動清單，
免系統管理員權限；勾＝寫一筆值、取消＝刪該筆值，完全可逆。
啟動指令自動判斷：打包的 exe → 直接它自己；從原始碼跑 → pythonw(無主控台) + 進入點腳本。
"""
import os
import sys

try:
    import winreg
except ImportError:                      # 非 Windows（理論上不會）
    winreg = None

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "繁中自動選字"             # Run 清單裡的名稱


def _command() -> str:
    """開機要執行的命令列。"""
    if getattr(sys, "frozen", False):                    # PyInstaller 打包：就是 exe 自己
        return f'"{sys.executable}"'
    exe = sys.executable                                  # 原始碼：盡量用 pythonw(無主控台)
    if os.path.basename(exe).lower() == "python.exe":
        pw = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.exists(pw):
            exe = pw
    return f'"{exe}" "{os.path.abspath(sys.argv[0])}"'


def is_enabled() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            winreg.QueryValueEx(k, _VALUE_NAME)
        return True
    except OSError:                                       # 含 FileNotFoundError（沒這筆）
        return False


def enable() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            winreg.SetValueEx(k, _VALUE_NAME, 0, winreg.REG_SZ, _command())
        return True
    except OSError:
        return False


def disable() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, _VALUE_NAME)
        return True
    except FileNotFoundError:
        return True                                       # 本來就沒有＝已是停用
    except OSError:
        return False


def toggle() -> bool:
    """切換並回傳切換後是否為「開」。"""
    if is_enabled():
        disable()
        return False
    enable()
    return True
