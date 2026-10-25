# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import base64
import ctypes
import ctypes.wintypes as wt

PREFIX = "~"
_ENTROPY = b"tcsc-logs-v1"
_UI_FORBIDDEN = 0x1


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


_crypt = ctypes.WinDLL("crypt32", use_last_error=True)
_kernel = ctypes.WinDLL("kernel32", use_last_error=True)
_crypt.CryptProtectData.argtypes = [ctypes.POINTER(_Blob), wt.LPCWSTR, ctypes.POINTER(_Blob), ctypes.c_void_p,
                                    ctypes.c_void_p, wt.DWORD, ctypes.POINTER(_Blob)]
_crypt.CryptUnprotectData.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.POINTER(_Blob), ctypes.c_void_p,
                                      ctypes.c_void_p, wt.DWORD, ctypes.POINTER(_Blob)]
_kernel.LocalFree.argtypes = [ctypes.c_void_p]


def _blob(b):
    buf = ctypes.create_string_buffer(b, len(b))
    return _Blob(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _call(fn, data):
    inb, _keep = _blob(data)
    ent, _keep2 = _blob(_ENTROPY)
    out = _Blob()
    if not fn(ctypes.byref(inb), None, ctypes.byref(ent), None, None, _UI_FORBIDDEN, ctypes.byref(out)):
        return None
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        _kernel.LocalFree(out.pbData)


def seal(text: str) -> str:
    raw = _call(_crypt.CryptProtectData, text.encode("utf-8"))
    if raw is None:
        raise OSError("DPAPI 加密失敗")
    return PREFIX + base64.b64encode(raw).decode("ascii")


def unseal(line: str):
    line = line.rstrip("\r\n")
    if not line.startswith(PREFIX):
        return line
    try:
        raw = _call(_crypt.CryptUnprotectData, base64.b64decode(line[1:]))
    except Exception:
        return None
    return None if raw is None else raw.decode("utf-8", errors="replace")


def is_sealed(line: str) -> bool:
    return line.startswith(PREFIX)
