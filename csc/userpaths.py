# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""個人資料路徑（自學詞、記錄）。

關鍵：exe(frozen) 不能把個人資料放在 `_internal/`——PyInstaller 重建(--clean)會整個清掉、
換版也會丟、還會被打包進發布 zip（個資外洩）。改放 `%APPDATA%\\tcsc\\`（用英文夾名，
避免中文路徑在某些環境出狀況）：重建/換版都留著、不進 zip。原始碼(daily) 仍用專案 data/、logs/。
"""
import os
import sys


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _app_base() -> str:
    """個人資料根：exe → %APPDATA%\\tcsc；原始碼 → 專案根。"""
    if _is_frozen():
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "tcsc")
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ensure(d: str) -> str:
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def user_data_dir() -> str:
    """自學詞放這：exe → %APPDATA%\\tcsc；原始碼 → 專案 data/。"""
    return _ensure(_app_base() if _is_frozen() else os.path.join(_app_base(), "data"))


def logs_dir() -> str:
    """記錄放這：exe → %APPDATA%\\tcsc\\logs；原始碼 → 專案 logs/。"""
    return _ensure(os.path.join(_app_base(), "logs"))


def userforce_path() -> str:
    return os.path.join(user_data_dir(), "userforce.txt")


def userwords_path() -> str:
    return os.path.join(user_data_dir(), "userwords.txt")
