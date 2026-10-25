# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import ctypes
import threading
import time

from .. import settings

_u32 = ctypes.windll.user32
VK_ESC = 0x1B
_POLL = 0.025
_ARM_S = 3.0

_state = {"active": 0, "epoch": 0, "thread": None, "hooked": 0,
          "wake": threading.Event(), "lock": threading.Lock(),
          "notify": None, "on_stop": None, "enabled": lambda: True}
_tl = threading.local()


def _mode():
    m = settings.get("esc_mode")
    if m in ("single", "double", "block", "off"):
        return m
    if not settings.get("esc_stop", True):
        return "block"
    return "single" if settings.get("esc_stop_single") else "double"


def _single():
    return _mode() == "single"


class EStop(Exception):
    pass


def wire(notify_fn, on_stop_fn, enabled_fn):
    _state["notify"] = notify_fn
    _state["on_stop"] = on_stop_fn
    _state["enabled"] = enabled_fn


def begin():
    if _mode() not in ("single", "double") or not _state["enabled"]():
        _tl.tok = None
        return
    with _state["lock"]:
        _state["active"] += 1
        _tl.tok = _state["epoch"]
        t = _state["thread"]
        if t is None or not t.is_alive():
            t = threading.Thread(target=_watch, daemon=True)
            _state["thread"] = t
            t.start()
        _state["wake"].set()


def end():
    with _state["lock"]:
        if _state["active"] > 0:
            _state["active"] -= 1
    _tl.tok = None


def check():
    tok = getattr(_tl, "tok", None)
    if tok is not None and _state["epoch"] != tok:
        raise EStop()


def hook_press():
    if _state["active"] <= 0 or _mode() not in ("single", "double"):
        return False
    _state["hooked"] += 1
    return True


def _fire_stop():
    with _state["lock"]:
        _state["epoch"] += 1
    fn = _state["on_stop"]
    if fn:
        try:
            fn()
        except Exception:
            pass


def _watch():
    prev = True
    armed_t = 0.0
    seen_hp = _state["hooked"]
    while True:
        if _state["active"] <= 0:
            _state["wake"].clear()
            armed_t = 0.0
            prev = True
            _state["wake"].wait()
            seen_hp = _state["hooked"]
            continue
        down = bool(_u32.GetAsyncKeyState(VK_ESC) & 0x8000)
        edges = 1 if (down and not prev) else 0
        prev = down
        hp = _state["hooked"]
        edges += hp - seen_hp
        seen_hp = hp
        for _ in range(edges):
            now = time.monotonic()
            if _single():
                armed_t = 0.0
                _fire_stop()
                break
            if armed_t and now - armed_t <= _ARM_S:
                armed_t = 0.0
                _fire_stop()
            else:
                armed_t = now
                fn = _state["notify"]
                if fn:
                    try:
                        fn("再按一次 Esc＝緊急停止這一輪")
                    except Exception:
                        pass
        time.sleep(_POLL)
