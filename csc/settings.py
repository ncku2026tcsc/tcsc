# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""使用者偏好（系統匣勾選）持久化：%APPDATA%\\tcsc\\settings.json（exe）或專案 data/（原始碼）。

記憶體快取、set 時即寫檔；關閉程式後仍記得。只讀已知鍵、壞檔不致命（回退預設）。
放 %APPDATA%（同自學詞）：重建/換版都留著、不進 zip——所以「預設關、但我這台開」靠這個達成：
release 不含 settings.json → 公眾吃預設；我按一次開 → 存進我的 %APPDATA%，只有我這台是開的。
"""
import json
import os

from .userpaths import user_data_dir
_DIR = user_data_dir()
_FILE = os.path.join(_DIR, "settings.json")
_DEFAULTS = {
    "auto_switch_ime": True,     # F6 開框自動切繁中注音（鍵盤配置）——預設開
    "auto_press_shift": False,   # F6 開框自動敲 Shift 切中文模式——不適用所有情境，預設關
    "auto_learn": False,         # F9 補 gold 時自動學差異詞（實驗）——預設關，使用者自行開啟
    "pron_ni": "",               # 人稱用字 ㄋㄧˇ 目標：""=不指定 / "你" / "妳"
    "pron_ta": "",               # 人稱用字 ㄊㄚ 目標：""=不指定 / "他"/"她"/"它"/"牠"/"祂"
    "notify_group": True,        # 改字通知：相鄰改動黏成一段——實測視覺較佳，v2.31 起預設開（可在系統匣關）
    "direct_type": False,        # 改字方式：False=剪貼簿貼上(相容、支援換行，預設)；True=直接打字(不經剪貼簿，但不支援換行)。v2.41 起預設剪貼簿
}
_cache = None


def _all() -> dict:
    global _cache
    if _cache is None:
        _cache = dict(_DEFAULTS)
        try:
            with open(_FILE, encoding="utf-8-sig") as f:   # utf-8-sig：容忍 BOM（某些編輯器/PowerShell 會加）
                loaded = json.load(f)
            if isinstance(loaded, dict):
                _cache.update({k: loaded[k] for k in _DEFAULTS if k in loaded})
        except Exception:
            pass
    return _cache


def get(key: str, default=None):
    return _all().get(key, _DEFAULTS.get(key, default))


def set(key: str, value) -> None:
    _all()[key] = value
    try:
        os.makedirs(_DIR, exist_ok=True)
        with open(_FILE, "w", encoding="utf-8") as f:
            json.dump(_all(), f, ensure_ascii=False, indent=2)
    except Exception:
        pass
