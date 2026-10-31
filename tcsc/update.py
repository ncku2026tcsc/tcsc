# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/tcsc2026/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import ctypes
import json
import re
import time
import urllib.request

from . import settings, version

API = "https://api.github.com/repos/tcsc2026/tcsc/releases/latest"
PAGE = "https://github.com/tcsc2026/tcsc/releases/latest"
DAY = 24 * 3600


def _ver(tag):
    return tuple(int(x) for x in re.findall(r"\d+", tag or ""))


def _agent():
    return f"tcsc-update-check/{version.VERSION}"


def _get_python(timeout):
    req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json", "User-Agent": _agent()})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _get_windows(timeout):
    v, vp, ul = ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_ulong
    net = ctypes.WinDLL("wininet", use_last_error=True)
    net.InternetOpenW.restype = net.InternetOpenUrlW.restype = vp
    net.InternetOpenW.argtypes = (v, ul, v, v, ul)
    net.InternetOpenUrlW.argtypes = (vp, v, v, ul, ul, ctypes.c_size_t)
    net.InternetReadFile.argtypes = (vp, vp, ul, ctypes.POINTER(ul))
    net.InternetSetOptionW.argtypes = (vp, ul, vp, ul)
    net.InternetCloseHandle.argtypes = (vp,)
    h = net.InternetOpenW(_agent(), 0, None, None, 0)
    if not h:
        raise ctypes.WinError(ctypes.get_last_error())
    u = None
    try:
        ms = ul(int(timeout * 1000))
        for opt in (2, 5, 6):
            net.InternetSetOptionW(h, opt, ctypes.byref(ms), ctypes.sizeof(ms))
        u = net.InternetOpenUrlW(h, API, "Accept: application/vnd.github+json\r\n", 0xFFFFFFFF, 0x84800200, 0)
        if not u:
            raise ctypes.WinError(ctypes.get_last_error())
        out, buf, got = b"", ctypes.create_string_buffer(65536), ul(0)
        while net.InternetReadFile(u, buf, 65536, ctypes.byref(got)) and got.value:
            out += buf.raw[:got.value]
        return out
    finally:
        if u:
            net.InternetCloseHandle(u)
        net.InternetCloseHandle(h)


def _note(msg):
    try:
        from .engine import crashlog
        crashlog.log(msg)
    except Exception:
        pass


def latest(timeout=6.0):
    for get in (_get_python, _get_windows):
        try:
            d = json.loads(get(timeout).decode("utf-8"))
        except Exception as e:
            _note(f"檢查更新 {get.__name__} 失敗：{e!r}")
            continue
        tag = d.get("tag_name") if isinstance(d, dict) else None
        if tag and _ver(tag):
            return tag, d.get("html_url") or PAGE
        _note(f"檢查更新 {get.__name__} 回應不對：{str(d)[:120]}")
    return None


def newer(tag, cur=None):
    return _ver(tag) > _ver(cur or version.VERSION)


def due():
    return bool(settings.get("update_check", True)) and time.time() - float(settings.get("update_last") or 0) >= DAY


def mark():
    settings.set("update_last", time.time())
