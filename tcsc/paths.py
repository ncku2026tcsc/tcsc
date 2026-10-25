# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import os
import sys


def _root() -> str:
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


ROOT = _root()
DATA = os.path.join(ROOT, "data")
MODELS = os.path.join(ROOT, "models")
USER = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "tcsc")
LOGS = os.path.join(USER, "logs")


def data(name: str) -> str:
    return os.path.join(DATA, name)


def model(name: str) -> str:
    return os.path.join(MODELS, name)


def user(name: str) -> str:
    try:
        os.makedirs(USER, exist_ok=True)
    except OSError:
        pass
    return os.path.join(USER, name)


def log(name: str) -> str:
    try:
        os.makedirs(LOGS, exist_ok=True)
    except OSError:
        pass
    return os.path.join(LOGS, name)
