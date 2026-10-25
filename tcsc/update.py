# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import json
import re
import time
import urllib.request

from . import settings, version

API = "https://api.github.com/repos/ncku2026tcsc/tcsc/releases/latest"
PAGE = "https://github.com/ncku2026tcsc/tcsc/releases/latest"
DAY = 24 * 3600


def _ver(tag):
    return tuple(int(x) for x in re.findall(r"\d+", tag or ""))


def latest(timeout=6.0):
    req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": f"tcsc-update-check/{version.VERSION}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    tag = d.get("tag_name") if isinstance(d, dict) else None
    if not tag or not _ver(tag):
        return None
    return tag, d.get("html_url") or PAGE


def newer(tag, cur=None):
    return _ver(tag) > _ver(cur or version.VERSION)


def due():
    return bool(settings.get("update_check", True)) and time.time() - float(settings.get("update_last") or 0) >= DAY


def mark():
    settings.set("update_last", time.time())
