# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""使用者偏好（系統匣勾選）持久化：logs/settings.json。

記憶體快取、set 時即寫檔；關閉程式後仍記得。只讀已知鍵、壞檔不致命（回退預設）。
存在 logs/（與 error_cases.jsonl 同一個可寫目錄；data/ 在 exe 內是唯讀的 _MEIPASS）。
"""
import json
import os

_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
_FILE = os.path.join(_DIR, "settings.json")
_DEFAULTS = {
    "auto_switch_ime": True,     # F6 開框自動切繁中注音（鍵盤配置）——預設開
    "auto_press_shift": False,   # F6 開框自動敲 Shift 切中文模式——不適用所有情境，預設關
}
_cache = None


def _all() -> dict:
    global _cache
    if _cache is None:
        _cache = dict(_DEFAULTS)
        try:
            with open(_FILE, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                _cache.update({k: loaded[k] for k in _DEFAULTS if k in loaded})
        except Exception:
            pass
    return _cache


def get(key: str):
    return _all().get(key, _DEFAULTS.get(key))


def set(key: str, value) -> None:
    _all()[key] = value
    try:
        os.makedirs(_DIR, exist_ok=True)
        with open(_FILE, "w", encoding="utf-8") as f:
            json.dump(_all(), f, ensure_ascii=False, indent=2)
    except Exception:
        pass
