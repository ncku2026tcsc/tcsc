# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import threading
import time

RESTORE_DELAY = 0.8
RESTORE_AFTER = 30


def _anomaly(tag, detail=""):
    try:
        import os
        from ..engine.userpaths import logs_dir
        d = logs_dir()
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "clip_anomaly.log"), "a", encoding="utf-8") as f:
            f.write(f"{tag}\t{detail}\n")
    except Exception:
        pass


def begin_paste(app, new_text) -> bool:
    app._clip_gen = getattr(app, "_clip_gen", 0) + 1
    current = app._get_clip()
    if current and current != getattr(app, "_our_last_clip", None):
        app._clip_user = current
    if not app._set_clip_confirm(new_text):
        app._set_clip(getattr(app, "_clip_user", ""))
        _anomaly("set_fail")
        return False
    app._our_last_clip = new_text
    return True


def reconfirm(app, new_text) -> None:
    if app._get_clip() != new_text:
        _anomaly("drift_before_paste")
        app._set_clip_confirm(new_text)


def end_paste(app) -> None:
    from .. import settings

    if settings.get("auto_clear_clip"):
        app._clip_pending = True
        gen = app._clip_gen

        def clear_worker():
            time.sleep(RESTORE_DELAY)
            if app._clip_gen == gen:
                app._set_clip("")
                app._clip_pending = False
        threading.Thread(target=clear_worker, daemon=True).start()

    if settings.get("auto_restore_clip"):
        gen2 = app._clip_gen

        def restore_worker():
            time.sleep(RESTORE_AFTER)
            if app._clip_gen != gen2:
                return
            cur = app._get_clip()
            if cur == "" or cur == getattr(app, "_our_last_clip", None):
                app._set_clip(getattr(app, "_clip_user", ""))
        threading.Thread(target=restore_worker, daemon=True).start()
