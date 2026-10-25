# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
from collections import namedtuple

from . import ia2text, win
from .. import settings

Plan = namedtuple("Plan", "grab write layer auto base")

GRAB_CHOICES = ("auto", "uia", "clip")
WRITE_CHOICES = ("paste", "type", "backspace")

_state = {"grab": "", "write": "", "layer": ""}


def plan() -> Plan:
    g = settings.get("grab_mode") or "auto"
    g = g if g in GRAB_CHOICES else "auto"
    w = settings.get("write_mode") or "paste"
    w = w if w in WRITE_CHOICES else "paste"
    auto = g == "auto"
    proc = win.foreground_process()
    if settings.get("term_auto") and proc in win.CONSOLES:
        return Plan("uia", "backspace", "終端機", auto, "backspace")
    if settings.get("ia2_browser") and proc in win.BROWSERS:
        if ia2text.caret_editable() is not False:
            return Plan("ia2", "ia2", "IA2", auto, w)
    return Plan(g, w, "", auto, w)


def note_grab(channel: str, layer: str = ""):
    _state["grab"], _state["layer"], _state["write"] = channel, layer, ""


def note_write(used: str):
    _state["write"] = used


def grab_channel() -> str:
    g = _state["grab"]
    return f"term:{g}" if _state["layer"] == "終端機" else g


_G = {"uia": "UIA", "clip": "剪貼簿", "uia→clip": "UIA 讀不到→剪貼簿", "ia2": "IA2", "sel": "反白",
      "ia2→uia": "IA2 讀不到→UIA", "ia2→uia→clip": "IA2、UIA 讀不到→剪貼簿", "ia2→sel": "IA2 讀不到→反白"}
_W = {"paste": "貼上", "type": "打字", "backspace": "退格重打", "ia2": "IA2 直改",
      "ia2→paste": "IA2 寫不進→貼上", "ia2→type": "IA2 寫不進→打字",
      "ia2+paste": "IA2 字被吃掉→補貼上", "ia2+type": "IA2 字被吃掉→補打字"}


def tail() -> str:
    return label() if settings.get("notify_route", False) else ""


def label() -> str:
    g = _state["grab"]
    if not g:
        return ""
    parts = [_G.get(g, g)]
    if _state["write"]:
        parts.append(_W.get(_state["write"], _state["write"]))
    head = f"{_state['layer']}｜" if _state["layer"] else ""
    return "〔" + head + "→".join(parts) + "〕"
