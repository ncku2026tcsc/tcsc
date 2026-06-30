# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""崩潰/例外捕捉，把『隨機閃退』的現場寫進 logs/crash.log。

為什麼需要：exe 是 windowed(無主控台)，C 級崩潰(access violation，常見於 Tk/Tcl 在非主緒
被呼叫)會讓行程直接消失、不留任何訊息。faulthandler 連這種致命錯誤都能攔下，把當下**所有
執行緒的 Python 堆疊**寫到檔案；再配 sys.excepthook / threading.excepthook 捕捉一般未處理例外，
以及 log() 留麵包屑(F1/F6…)，下次閃退就能對到「最後做了什麼 + 死在哪」。
"""
import datetime
import faulthandler
import os
import sys
import threading
import traceback

from .userpaths import logs_dir
_DIR = logs_dir()   # exe → %APPDATA%\tcsc\logs；原始碼 → 專案 logs/
_FILE = os.path.join(_DIR, "crash.log")
_fh = None
_lock = threading.Lock()
_installed = False


def _emit(text: str) -> None:
    with _lock:
        try:
            if _fh is not None:
                _fh.write(text)
                _fh.flush()
            else:
                with open(_FILE, "a", encoding="utf-8") as f:
                    f.write(text)
        except Exception:
            pass


def install() -> None:
    """在進入點 main() 最前面呼叫一次。"""
    global _fh, _installed
    if _installed:
        return
    _installed = True
    try:
        os.makedirs(_DIR, exist_ok=True)
        _fh = open(_FILE, "a", encoding="utf-8", buffering=1)   # 行緩衝，崩潰前也寫得進去
    except Exception:
        _fh = None
    _emit(f"\n==== session start {datetime.datetime.now():%Y-%m-%d %H:%M:%S} ====\n")
    try:
        if _fh is not None:
            faulthandler.enable(file=_fh, all_threads=True)     # 攔 C 級致命錯誤(含 access violation)
    except Exception:
        pass

    _orig = sys.excepthook

    def _excepthook(t, v, tb):
        _emit("---- uncaught (main) ----\n" + "".join(traceback.format_exception(t, v, tb)))
        try:
            _orig(t, v, tb)                                     # 保留原本(PyInstaller 的崩潰對話框)
        except Exception:
            pass

    sys.excepthook = _excepthook

    def _threadhook(args):
        nm = args.thread.name if args.thread else "?"
        _emit(f"---- uncaught (thread {nm}) ----\n"
              + "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))

    try:
        threading.excepthook = _threadhook                      # Py3.8+：背景緒未處理例外
    except Exception:
        pass


def log(msg: str) -> None:
    """留麵包屑（哪個熱鍵被按、框開了沒），對崩潰前的最後動作。"""
    _emit(f"[{datetime.datetime.now():%H:%M:%S}] {msg}\n")
