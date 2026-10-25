# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import io
import json
import os
import threading

from . import config, paths

SPEC = (
    ("grab_mode", "auto"),
    ("ia2_browser", False),
    ("write_mode", "paste"),
    ("sym_write", "follow"),
    ("log_on", True),
    ("log_detail", False),
    ("log_keep_days", 30),
    ("update_check", False),

    ("update_last", 0.0),
    ("tray_promote", True),
    ("f10_stack", True),
    ("garble_on", True),
    ("garble_ime", True),
    ("garble_rerank", True),
    ("garble_single", True),
    ("mode_keys", True),
    ("firstrun_done", False),
    ("xuci_key", True),
    ("xuci_de", False),
    ("pron_key", True),
    ("respell_prop", 0),
    ("escort_shipped", True),
    ("f7_lock", True),
    ("f7_direct", True),
    ("pron_rank", True),
    ("pron_f8_rare", False),
    ("autokey_refill", True),
    ("auto_verify", True),
    ("notify_route", False),
    ("ime_commit", True),
    ("term_auto", True),
    ("esc_mode", "double"),
    ("notify_style", "bubble"),
    ("bubble_pin", False),
    ("bubble_thru", False),
    ("bubble_arena", True),
    ("bubble_face", "white"),
    ("bubble_face_custom", "#87bacb"),
    ("calc_pulse", "candy"),
    ("bubble_pos", "fixed"),
    ("bubble_off_x", 40),
    ("bubble_off_y", 40),
    ("bubble_hold_level", 4),
    ("bubble_size_level", 5),
    ("glyph_bpmf_yi", True),
    ("glyph_bpmf_tone", True),
    ("movers_on", True),
    ("symkeys_on", True),
    ("enter_unify_on", True),
    ("tab_f1", False),
    ("key_overrides", {}),
    ("sym_user", {}),
    ("sym_off", []),
    ("tutorial_seen", False),
    ("tutorial_invited", False),
    ("tutorial_f1n", 0),
    ("box_dark", True),
    ("dev_mode", False),
    ("dev_mode_until", 0.0),
    ("vocab_packs_off", []),
    ("escort_show_builtin", False),
    ("bubble_x", 0),
    ("bubble_y", 0),
    ("pron_ni", ""),
    ("pron_ta", ""),
    ("glyph_tai", ""),
    ("glyph_li", "裡"),
    ("glyph_shen", "什"),
    ("glyph_bu", "布"),
    ("glyph_chi", ""),
    ("glyph_kaoyao", ""),
)
_DEFAULTS = dict(SPEC)
FILE = paths.user("app_settings.json")

_lock = threading.Lock()
_cache = None


def _load() -> dict:
    global _cache
    if _cache is None:
        d = {}
        try:
            with io.open(FILE, encoding="utf-8") as f:
                raw = json.load(f)
            d = {k: v for k, v in raw.items() if k in _DEFAULTS}
            if raw.get("grab_mode") == "ia2":
                d["grab_mode"], d["ia2_browser"] = "auto", True
        except (OSError, ValueError):
            pass
        _cache = d
    return _cache


def get(key: str, default=None):
    with _lock:
        d = _load()
    if key in d:
        return d[key]
    if key in _DEFAULTS:
        return _DEFAULTS[key]
    if key in config.FIXED:
        return config.FIXED[key]
    return default


def set(key: str, value) -> None:
    if key not in _DEFAULTS:
        raise KeyError(f"{key} 不是設定鍵（常數在 config.FIXED；要變成設定請加進 settings.SPEC）")
    with _lock:
        d = _load()
        d[key] = value
        tmp = FILE + ".tmp"
        with io.open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        os.replace(tmp, FILE)


def reset() -> None:
    global _cache
    with _lock:
        _cache = {}
        try:
            os.remove(FILE)
        except OSError:
            pass


def sp(base: float) -> float:
    return base * 0.25


def all_user() -> dict:
    with _lock:
        d = _load()
    out = dict(_DEFAULTS)
    out.update(d)
    return out
