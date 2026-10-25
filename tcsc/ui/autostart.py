# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import os
import sys

try:
    import winreg
except ImportError:
    winreg = None

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "算字大師"
_OLD_NAMES = ()


def _command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    exe = sys.executable
    if os.path.basename(exe).lower() == "python.exe":
        pw = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.exists(pw):
            exe = pw
    return f'"{exe}" "{os.path.abspath(sys.argv[0])}"'


def is_enabled() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            for name in (_VALUE_NAME,) + _OLD_NAMES:
                try:
                    winreg.QueryValueEx(k, name)
                    return True
                except OSError:
                    pass
        return False
    except OSError:
        return False


def enable() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            winreg.SetValueEx(k, _VALUE_NAME, 0, winreg.REG_SZ, _command())
            for old in _OLD_NAMES:
                try:
                    winreg.DeleteValue(k, old)
                except OSError:
                    pass
        return True
    except OSError:
        return False


def disable() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            for name in (_VALUE_NAME,) + _OLD_NAMES:
                try:
                    winreg.DeleteValue(k, name)
                except FileNotFoundError:
                    pass
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


def toggle() -> bool:
    if is_enabled():
        disable()
        return False
    enable()
    return True
