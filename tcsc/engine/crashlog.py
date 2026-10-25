# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import datetime
import faulthandler
import os
import re
import sys
import threading
import traceback

from .. import paths

_DIR = paths.LOGS
_FILE = os.path.join(_DIR, "crash.log")
_fh = None
_lock = threading.Lock()
_installed = False
KEEP_LINES = 20000
_STAMP = re.compile(r"^(\[\d\d:\d\d:\d\d\] )(.*)$")
_SESSION = re.compile(r"^==== session start (\d{4}-\d\d-\d\d)")


def q(text) -> str:
    if text is None:
        return "None"
    text = str(text)
    try:
        from .. import logbook
        on = logbook.detail()
    except Exception:
        on = False
    return repr(text) if on else f"〈{len(text)}字〉"


def _seal(msg: str) -> str:
    try:
        from .. import vault
        return vault.seal(msg)
    except Exception:
        return msg


def unseal_line(line: str) -> str:
    m = _STAMP.match(line.rstrip("\r\n"))
    if not m or not m.group(2).startswith("~"):
        return line.rstrip("\r\n")
    from .. import vault
    t = vault.unseal(m.group(2))
    return m.group(1) + (t if t is not None else "（這台電腦解不開）")


def _keep_days() -> int:
    try:
        from .. import settings
        return int(settings.get("log_keep_days", 30) or 0)
    except Exception:
        return 30


def _tidy(keep_days=None) -> None:
    try:
        with open(_FILE, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return
    days = _keep_days() if keep_days is None else keep_days
    keep = lines
    if days > 0:
        cut = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
        start = next((i for i, ln in enumerate(lines) if (m := _SESSION.match(ln)) and m.group(1) >= cut), len(lines))
        keep = lines[start:]
    keep = keep[-KEEP_LINES:]
    out, changed = [], len(keep) != len(lines)
    for ln in keep:
        m = _STAMP.match(ln)
        if m and not m.group(2).startswith("~"):
            ln = m.group(1) + _seal(m.group(2))
            changed = True
        out.append(ln)
    if not changed:
        return
    tmp = _FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("".join(x + "\n" for x in out))
    os.replace(tmp, _FILE)


def clear() -> None:
    with _lock:
        try:
            if _fh is not None:
                _fh.seek(0)
                _fh.truncate()
            else:
                open(_FILE, "w", encoding="utf-8").close()
        except Exception:
            pass


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
    global _fh, _installed
    if _installed:
        return
    _installed = True
    try:
        os.makedirs(_DIR, exist_ok=True)
        try:
            _tidy()
        except Exception:
            pass
        _fh = open(_FILE, "a", encoding="utf-8", buffering=1)
    except Exception:
        _fh = None
    _emit(f"\n==== session start {datetime.datetime.now():%Y-%m-%d %H:%M:%S} ====\n")
    try:
        if _fh is not None:
            faulthandler.enable(file=_fh, all_threads=True)
    except Exception:
        pass

    _orig = sys.excepthook

    def _excepthook(t, v, tb):
        _emit("---- uncaught (main) ----\n" + "".join(traceback.format_exception(t, v, tb)))
        try:
            _orig(t, v, tb)
        except Exception:
            pass

    sys.excepthook = _excepthook

    def _threadhook(args):
        nm = args.thread.name if args.thread else "?"
        _emit(f"---- uncaught (thread {nm}) ----\n"
              + "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))

    try:
        threading.excepthook = _threadhook
    except Exception:
        pass


def log(msg: str) -> None:
    _emit(f"[{datetime.datetime.now():%H:%M:%S}] {_seal(str(msg))}\n")
