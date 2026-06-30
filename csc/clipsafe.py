# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""剪貼簿『貼上取代』的安全還原（v2.32：根治偶發貼到舊內容）。

陳年 bug：校正後 Ctrl+V 偶爾貼出『上一次剪貼簿的內容』，通知卻顯示正確（通知是另算的）。
v22 已修『寫入端』（_set_clip_confirm 確認新內容真的寫進剪貼簿才貼）；本模組修『讀取端』：

  舊流程：存舊clip → 寫新clip → Ctrl+V → sleep(固定) → 還原舊clip
  讀取端競態：有些程式讀剪貼簿較慢，等我們 sleep 完把舊內容還原回去後它才真的讀 → 貼到舊內容。

修法：Ctrl+V 後**不立刻還原**，讓校正後的新內容在剪貼簿多留 RESTORE_DELAY 秒（慢的程式也讀得到
正確內容），再用背景執行緒還原使用者原本的剪貼簿。配「世代守衛」：
  - 每次 begin_paste 先把世代 +1 → 任何在途的舊還原會看到世代變了而放棄（連續校正不互相蓋）。
  - 只有「沒有待還原」時才重抓使用者剪貼簿（_clip_user）；連續校正時沿用先前記住的真原內容，
    避免把『上一次的校正結果』誤當使用者剪貼簿還原回去。

用法（呼叫端，需具備 _get_clip/_set_clip/_set_clip_confirm）：
    if not clipsafe.begin_paste(self, new_text):
        raise RuntimeError("剪貼簿被佔用，沒貼成功，請再按一次")
    ... 反白目標 + Ctrl+V（貼上前可再 clipsafe.reconfirm(self, new_text)）...
    clipsafe.end_paste(self)
"""
import threading
import time

RESTORE_DELAY = 0.8        # Ctrl+V 後新內容保留在剪貼簿的秒數（給慢的程式讀完才還原）


def _anomaly(tag, detail=""):
    """輕量記錄異常（只在漂移/寫入失敗時呼叫，平時不寫檔）。最佳努力、永不致命。"""
    try:
        import os
        from .userpaths import logs_dir
        d = logs_dir()
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "clip_anomaly.log"), "a", encoding="utf-8") as f:
            f.write(f"{tag}\t{detail}\n")
    except Exception:
        pass


def begin_paste(app, new_text) -> bool:
    """記住使用者剪貼簿（只在沒有待還原時）、把 new_text 寫進剪貼簿並確認。回 True=可貼。"""
    app._clip_gen = getattr(app, "_clip_gen", 0) + 1        # 讓任何在途的舊還原失效
    if not getattr(app, "_clip_pending", False):
        app._clip_user = app._get_clip()                   # 真正的使用者剪貼簿（非上一次的校正結果）
    if not app._set_clip_confirm(new_text):                # 寫入端：沒寫進去就別硬貼舊內容
        app._set_clip(getattr(app, "_clip_user", ""))
        _anomaly("set_fail")
        return False
    return True


def reconfirm(app, new_text) -> None:
    """貼上前再確認剪貼簿仍是 new_text（殺 confirm→Ctrl+V 之間被別程式蓋掉的漂移）。"""
    if app._get_clip() != new_text:
        _anomaly("drift_before_paste")
        app._set_clip_confirm(new_text)


def end_paste(app) -> None:
    """延遲還原使用者剪貼簿（世代守衛）：保留新內容 RESTORE_DELAY 秒後，若無更新的貼上才還原。"""
    app._clip_pending = True
    gen = app._clip_gen
    user = getattr(app, "_clip_user", "")

    def worker():
        time.sleep(RESTORE_DELAY)
        if app._clip_gen == gen:               # 沒有更新的貼上 → 由我負責還原
            app._set_clip(user)
            app._clip_pending = False
    threading.Thread(target=worker, daemon=True).start()
