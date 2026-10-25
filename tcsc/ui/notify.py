# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import threading
import time

from . import bubble
from .. import settings, version

_RINGS = {
    "blue": (("#1c3a6e", "#224477", "#346192", "#4d89b6", "#719fe2",
              "#8998fa", "#8f91ff", "#8998fa", "#719fe2", "#4d89b6",
              "#346192", "#224477"), 0.07),
    "rainbow": (("#ff2626", "#ff6e26", "#ffb626", "#ffff26", "#b6ff26",
                 "#6eff26", "#26ff26", "#26ff6e", "#26ffb6", "#26ffff",
                 "#26b6ff", "#266eff", "#2626ff", "#6e26ff", "#b626ff",
                 "#ff26ff", "#ff26b6", "#ff266e"), 0.07),
    "flash": (("#8c0e0e", "#a33c10", "#d78915", "#fce519", "#c8f418",
               "#6cc513", "#2a970f", "#0e8f1b", "#11b352", "#17e7a8",
               "#19ffff", "#17a8e7", "#1152b3", "#0e1b8f", "#2a0f97",
               "#6c13c5", "#c818f4", "#fc19e5", "#d71589", "#a3103c"), 0.06),
    "candy": (("#ff8ac2", "#66e0d5", "#ffd166", "#b28aff"), 0.17),
}
PULSE_NAMES = {"blue": "深藍呼吸", "rainbow": "彩虹輪轉", "flash": "彩虹閃爍", "candy": "糖果跳格"}


class Notifier:
    def __init__(self, icon):
        self.icon = icon
        self.mute_until = 0.0
        self._anim = False

    def notify(self, msg):
        if not msg or time.time() < self.mute_until:
            return
        style = settings.get("notify_style") or "bubble"
        if style == "off":
            return
        try:
            if style == "bubble" and bubble.show(msg):
                return
        except Exception:
            pass
        try:
            self.icon.notify(msg, version.APP_TITLE)
        except Exception:
            pass

    def mute(self, seconds=1.5):
        self.mute_until = time.time() + seconds

    def bubble_only(self, msg, kind="info"):
        if (settings.get("notify_style") or "bubble") != "bubble":
            return
        try:
            bubble.show(msg, kind)
        except Exception:
            pass

    def calc_begin(self):
        if (settings.get("notify_style") or "bubble") != "bubble":
            return
        try:
            bubble.show("讀字中…", "info")
        except Exception:
            return
        self._anim = True
        ring, iv = _RINGS.get(settings.get("calc_pulse") or "candy", _RINGS["candy"])

        def pump():
            t0 = time.monotonic()
            i = 0
            while self._anim and time.monotonic() - t0 < 30:
                time.sleep(iv)
                if not self._anim:
                    break
                try:
                    if not bubble.tick(dot=ring[i % len(ring)]):
                        return
                except Exception:
                    return
                i += 1
        threading.Thread(target=pump, daemon=True).start()

    def calc_tick(self, text):
        try:
            bubble.tick(text=text)
        except Exception:
            pass

    def calc_end(self):
        self._anim = False
