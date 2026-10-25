# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import ctypes
import ctypes.wintypes as wt
import threading

SEL, NOSEL, UNKNOWN = "sel", "nosel", "unknown"

_u32 = ctypes.WinDLL("user32", use_last_error=True)
_ole = ctypes.WinDLL("ole32")
_olea = ctypes.WinDLL("oleaut32")

_u32.GetForegroundWindow.restype = wt.HWND
_u32.GetWindowThreadProcessId.argtypes = (wt.HWND, ctypes.c_void_p)
_u32.GetWindowThreadProcessId.restype = wt.DWORD
_u32.GetGUIThreadInfo.argtypes = (wt.DWORD, ctypes.c_void_p)
_u32.GetGUIThreadInfo.restype = wt.BOOL
_u32.GetClassNameW.argtypes = (wt.HWND, ctypes.c_wchar_p, ctypes.c_int)
_u32.GetClassNameW.restype = ctypes.c_int
_u32.SendMessageTimeoutW.argtypes = (wt.HWND, ctypes.c_uint, ctypes.c_void_p,
                                     ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint,
                                     ctypes.c_void_p)
_u32.SendMessageTimeoutW.restype = ctypes.c_size_t

_ole.CoInitializeEx.argtypes = (ctypes.c_void_p, wt.DWORD)
_ole.CoInitializeEx.restype = ctypes.c_long
_ole.CoUninitialize.argtypes = ()
_ole.CoCreateInstance.argtypes = (ctypes.c_void_p, ctypes.c_void_p, wt.DWORD,
                                  ctypes.c_void_p, ctypes.c_void_p)
_ole.CoCreateInstance.restype = ctypes.c_long
_olea.SysStringLen.argtypes = (ctypes.c_void_p,)
_olea.SysStringLen.restype = ctypes.c_uint
_olea.SysFreeString.argtypes = (ctypes.c_void_p,)

_EM_GETSEL = 0x00B0
_SMTO_ABORTIFHUNG = 0x0002
_CLSCTX_INPROC_SERVER = 0x1
_UIA_TextPatternId = 10014


class _GUID(ctypes.Structure):
    _fields_ = (("d1", ctypes.c_uint32), ("d2", ctypes.c_uint16),
                ("d3", ctypes.c_uint16), ("d4", ctypes.c_ubyte * 8))


def _guid(s):
    p = s.split("-")
    g = _GUID(int(p[0], 16), int(p[1], 16), int(p[2], 16))
    g.d4 = (ctypes.c_ubyte * 8)(*bytes.fromhex(p[3] + p[4]))
    return g


_CLSID_CUIA = _guid("ff48dba4-60ef-4201-aa87-54103eef594e")
_IID_IUIA = _guid("30cbe57d-d9d0-452a-ab13-7ac5ac4825ee")
_IID_TEXTPAT = _guid("32eba289-3583-42c9-9c59-3b6d9a1e9b6a")


def _vt(ptr, idx, *argtypes):
    vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)
    return proto(vtbl[idx])


def _release(ptr):
    if ptr and ptr.value:
        try:
            vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
            ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])(ptr)
        except Exception:
            pass


class _GTI(ctypes.Structure):
    _fields_ = (("cbSize", wt.DWORD), ("flags", wt.DWORD), ("hwndActive", wt.HWND),
                ("hwndFocus", wt.HWND), ("hwndCapture", wt.HWND),
                ("hwndMenuOwner", wt.HWND), ("hwndMoveSize", wt.HWND),
                ("hwndCaret", wt.HWND), ("rcCaret", wt.RECT))


def _focus_hwnd():
    fg = _u32.GetForegroundWindow()
    if not fg:
        return 0
    tid = _u32.GetWindowThreadProcessId(fg, None)
    gti = _GTI()
    gti.cbSize = ctypes.sizeof(_GTI)
    if tid and _u32.GetGUIThreadInfo(tid, ctypes.byref(gti)) and gti.hwndFocus:
        return gti.hwndFocus
    return fg


_EDIT_CLASSES = ("edit", "richedit", "scintilla", "tmemo", "tedit")


def _em_getsel(hwnd):
    buf = ctypes.create_unicode_buffer(64)
    if not hwnd or not _u32.GetClassNameW(hwnd, buf, 64):
        return None
    if not buf.value.lower().startswith(_EDIT_CLASSES):
        return None
    s, e, res = wt.DWORD(0), wt.DWORD(0), ctypes.c_size_t(0)
    ok = _u32.SendMessageTimeoutW(hwnd, _EM_GETSEL, ctypes.byref(s), ctypes.byref(e),
                                  _SMTO_ABORTIFHUNG, 50, ctypes.byref(res))
    if not ok:
        return None
    return SEL if s.value != e.value else NOSEL


def _uia_sel_from_elem(elem):
    patt, tp, arr = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
    try:
        if _vt(elem, 16, ctypes.c_int, ctypes.c_void_p)(
                elem, _UIA_TextPatternId, ctypes.byref(patt)) or not patt.value:
            return UNKNOWN
        if _vt(patt, 0, ctypes.c_void_p, ctypes.c_void_p)(
                patt, ctypes.byref(_IID_TEXTPAT), ctypes.byref(tp)) or not tp.value:
            return UNKNOWN
        if _vt(tp, 5, ctypes.c_void_p)(tp, ctypes.byref(arr)) or not arr.value:
            return UNKNOWN
        n = ctypes.c_int(0)
        if _vt(arr, 3, ctypes.c_void_p)(arr, ctypes.byref(n)):
            return UNKNOWN
        if n.value <= 0:
            return NOSEL
        for i in range(min(n.value, 2)):
            rng = ctypes.c_void_p()
            if _vt(arr, 4, ctypes.c_int, ctypes.c_void_p)(
                    arr, i, ctypes.byref(rng)) or not rng.value:
                continue
            try:
                bstr = ctypes.c_void_p()
                if _vt(rng, 12, ctypes.c_int, ctypes.c_void_p)(rng, 8, ctypes.byref(bstr)):
                    continue
                try:
                    if bstr.value and _olea.SysStringLen(bstr) > 0:
                        return SEL
                finally:
                    if bstr.value:
                        _olea.SysFreeString(bstr)
            finally:
                _release(rng)
        return NOSEL
    except Exception:
        return UNKNOWN
    finally:
        for p in (arr, tp, patt):
            _release(p)


def _uia_sel_text(elem):
    patt, tp, arr, rng = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
    try:
        if _vt(elem, 16, ctypes.c_int, ctypes.c_void_p)(
                elem, _UIA_TextPatternId, ctypes.byref(patt)) or not patt.value:
            return None
        if _vt(patt, 0, ctypes.c_void_p, ctypes.c_void_p)(
                patt, ctypes.byref(_IID_TEXTPAT), ctypes.byref(tp)) or not tp.value:
            return None
        if _vt(tp, 5, ctypes.c_void_p)(tp, ctypes.byref(arr)) or not arr.value:
            return None
        n = ctypes.c_int(0)
        if _vt(arr, 3, ctypes.c_void_p)(arr, ctypes.byref(n)):
            return None
        if n.value <= 0:
            return ""
        if _vt(arr, 4, ctypes.c_int, ctypes.c_void_p)(arr, 0, ctypes.byref(rng)) or not rng.value:
            return None
        bstr = ctypes.c_void_p()
        if _vt(rng, 12, ctypes.c_int, ctypes.c_void_p)(rng, -1, ctypes.byref(bstr)):
            return None
        try:
            return ctypes.wstring_at(bstr.value, _olea.SysStringLen(bstr)) if bstr.value else ""
        finally:
            if bstr.value:
                _olea.SysFreeString(bstr)
    except Exception:
        return None
    finally:
        for p in (rng, arr, tp, patt):
            _release(p)


def _with_uia(get_elem, read=_uia_sel_from_elem, unknown=UNKNOWN):
    hr = _ole.CoInitializeEx(None, 0)
    inited = hr in (0, 1)
    uia, elem = ctypes.c_void_p(), ctypes.c_void_p()
    try:
        if _ole.CoCreateInstance(ctypes.byref(_CLSID_CUIA), None, _CLSCTX_INPROC_SERVER,
                                 ctypes.byref(_IID_IUIA), ctypes.byref(uia)) or not uia.value:
            return unknown
        if get_elem(uia, elem) or not elem.value:
            return unknown
        return read(elem)
    except Exception:
        return unknown
    finally:
        _release(elem)
        _release(uia)
        if inited:
            _ole.CoUninitialize()


def _uia_probe():
    return _with_uia(lambda uia, elem: _vt(uia, 8, ctypes.c_void_p)(uia, ctypes.byref(elem)))


def _uia_probe_hwnd(hwnd):
    return _with_uia(lambda uia, elem: _vt(uia, 6, ctypes.c_void_p, ctypes.c_void_p)(
        uia, hwnd, ctypes.byref(elem)))


def wake_a11y():
    try:
        fg = _u32.GetForegroundWindow()
        if not fg:
            return False
        targets = [fg]

        @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        def _cb(h, _l):
            buf = ctypes.create_unicode_buffer(64)
            _u32.GetClassNameW(h, buf, 64)
            if buf.value.startswith("Chrome_RenderWidgetHostHWND"):
                targets.append(h)
            return True

        _u32.EnumChildWindows(fg, _cb, 0)
        if len(targets) < 2:
            return False
        _u32.SendMessageTimeoutW.restype = ctypes.c_ssize_t
        _u32.SendMessageTimeoutW.argtypes = (wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM,
                                             wt.UINT, wt.UINT,
                                             ctypes.POINTER(ctypes.c_size_t))
        out = ctypes.c_size_t()
        for h in targets[1:]:
            _u32.SendMessageTimeoutW(h, 0x003D, 0, -4, 0x0002, 200,
                                     ctypes.byref(out))
        return True
    except Exception:
        return False


_LASTF = {"why": ""}


def _fail(why):
    _LASTF["why"] = why
    return None


def last_fail():
    return _LASTF["why"]


def _range_read(rng, endpoint, count):
    cl = ctypes.c_void_p()
    if _vt(rng, 3, ctypes.c_void_p)(rng, ctypes.byref(cl)) or not cl.value:
        return None
    try:
        if count:
            moved = ctypes.c_int(0)
            if _vt(cl, 14, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p)(
                    cl, endpoint, 0, count, ctypes.byref(moved)):
                return None
        bstr = ctypes.c_void_p()
        if _vt(cl, 12, ctypes.c_int, ctypes.c_void_p)(cl, -1, ctypes.byref(bstr)):
            return None
        if not bstr.value:
            return ""
        try:
            return ctypes.wstring_at(bstr.value, _olea.SysStringLen(bstr))
        finally:
            _olea.SysFreeString(bstr)
    finally:
        _release(cl)


def _looks_poison(text):
    if not text:
        return False
    return any("\ue000" <= ch <= "\uf8ff" for ch in text)


def _caret_context_inner(back, fwd):
    hr = _ole.CoInitializeEx(None, 0)
    inited = hr in (0, 1)
    uia, elem = ctypes.c_void_p(), ctypes.c_void_p()
    patt, tp, arr, rng = (ctypes.c_void_p(), ctypes.c_void_p(),
                          ctypes.c_void_p(), ctypes.c_void_p())
    try:
        if _ole.CoCreateInstance(ctypes.byref(_CLSID_CUIA), None, _CLSCTX_INPROC_SERVER,
                                 ctypes.byref(_IID_IUIA), ctypes.byref(uia)) or not uia.value:
            return _fail("COM失敗")
        if _vt(uia, 8, ctypes.c_void_p)(uia, ctypes.byref(elem)) or not elem.value:
            return _fail("無焦點元素")
        if _vt(elem, 16, ctypes.c_int, ctypes.c_void_p)(
                elem, _UIA_TextPatternId, ctypes.byref(patt)) or not patt.value:
            return _fail("無TextPattern")
        if _vt(patt, 0, ctypes.c_void_p, ctypes.c_void_p)(
                patt, ctypes.byref(_IID_TEXTPAT), ctypes.byref(tp)) or not tp.value:
            return _fail("QI失敗")
        if _vt(tp, 5, ctypes.c_void_p)(tp, ctypes.byref(arr)) or not arr.value:
            return _fail("選取查詢失敗")
        n = ctypes.c_int(0)
        if _vt(arr, 3, ctypes.c_void_p)(arr, ctypes.byref(n)) or n.value <= 0:
            return _fail("選取空(0範圍)")
        if _vt(arr, 4, ctypes.c_int, ctypes.c_void_p)(arr, 0, ctypes.byref(rng)) or not rng.value:
            return _fail("取範圍失敗")
        sel = _range_read(rng, 1, 0) or ""
        if len(sel) > 300:
            return _fail("巨型反白")
        raw_b = _range_read(rng, 0, -back)
        raw_a = _range_read(rng, 1, +fwd)
        if raw_b is None or raw_a is None:
            return _fail("取字失敗")
        before = raw_b[:len(raw_b) - len(sel)] if sel and raw_b.endswith(sel) else raw_b
        after = raw_a[len(sel):] if sel and raw_a.startswith(sel) else raw_a
        if _looks_poison(before[-80:]) or _looks_poison(after[:80]):
            return _fail("毒偵測(UI外殼字)")
        return before, after
    except Exception:
        return _fail("例外")
    finally:
        for p in (rng, arr, tp, patt, elem, uia):
            _release(p)
        if inited:
            _ole.CoUninitialize()


def caret_context(back=80, fwd=80, timeout=0.35):
    out = {"v": None}

    def run():
        out["v"] = _caret_context_inner(back, fwd)
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout)
    if out["v"] is None and t.is_alive():
        _LASTF["why"] = f"逾時>{timeout}s(app忙/樹在蓋)"
    return out["v"]


_TU_PARAGRAPH = 4


def _rng_clone(rng):
    c = ctypes.c_void_p()
    if _vt(rng, 3, ctypes.c_void_p)(rng, ctypes.byref(c)) or not c.value:
        return None
    return c


def _caret_paragraph_inner():
    hr = _ole.CoInitializeEx(None, 0)
    inited = hr in (0, 1)
    uia, elem = ctypes.c_void_p(), ctypes.c_void_p()
    patt, tp, arr, rng = (ctypes.c_void_p(), ctypes.c_void_p(),
                          ctypes.c_void_p(), ctypes.c_void_p())
    para, pb, pa = None, None, None
    try:
        if _ole.CoCreateInstance(ctypes.byref(_CLSID_CUIA), None, _CLSCTX_INPROC_SERVER,
                                 ctypes.byref(_IID_IUIA), ctypes.byref(uia)) or not uia.value:
            return _fail("COM失敗")
        if _vt(uia, 8, ctypes.c_void_p)(uia, ctypes.byref(elem)) or not elem.value:
            return _fail("無焦點元素")
        if _vt(elem, 16, ctypes.c_int, ctypes.c_void_p)(
                elem, _UIA_TextPatternId, ctypes.byref(patt)) or not patt.value:
            return _fail("無TextPattern")
        if _vt(patt, 0, ctypes.c_void_p, ctypes.c_void_p)(
                patt, ctypes.byref(_IID_TEXTPAT), ctypes.byref(tp)) or not tp.value:
            return _fail("QI失敗")
        if _vt(tp, 5, ctypes.c_void_p)(tp, ctypes.byref(arr)) or not arr.value:
            return _fail("選取查詢失敗")
        n = ctypes.c_int(0)
        if _vt(arr, 3, ctypes.c_void_p)(arr, ctypes.byref(n)) or n.value <= 0:
            return _fail("選取空(0範圍)")
        if _vt(arr, 4, ctypes.c_int, ctypes.c_void_p)(arr, 0, ctypes.byref(rng)) or not rng.value:
            return _fail("取範圍失敗")
        sel = _range_read(rng, 1, 0) or ""
        if len(sel) > 300:
            return _fail("巨型反白")
        para = _rng_clone(rng)
        if para is None:
            return _fail("複製範圍失敗")
        if _vt(para, 6, ctypes.c_int)(para, _TU_PARAGRAPH):
            return _fail("段落展開失敗")
        whole = _range_read(para, 1, 0)
        if whole is None or len(whole) > 4000:
            return _fail("段落爆走>4000")
        pb, pa = _rng_clone(para), _rng_clone(para)
        if pb is None or pa is None:
            return _fail("複製範圍失敗")
        if _vt(pb, 15, ctypes.c_int, ctypes.c_void_p, ctypes.c_int)(pb, 1, rng, 0):
            return _fail("端點移動失敗")
        if _vt(pa, 15, ctypes.c_int, ctypes.c_void_p, ctypes.c_int)(pa, 0, rng, 1):
            return _fail("端點移動失敗")
        before = _range_read(pb, 1, 0)
        after = _range_read(pa, 1, 0)
        if before is None or after is None:
            return _fail("段內取字失敗")
        if _looks_poison(before[-80:]) or _looks_poison(after[:80]):
            return _fail("毒偵測(UI外殼字)")
        return before, after
    except Exception:
        return _fail("例外")
    finally:
        for p in (pb, pa, para, rng, arr, tp, patt, elem, uia):
            if p is not None:
                _release(p)
        if inited:
            _ole.CoUninitialize()


def caret_paragraph(timeout=0.35):
    out = {"v": None}

    def run():
        out["v"] = _caret_paragraph_inner()
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout)
    if out["v"] is None and t.is_alive():
        _LASTF["why"] = f"逾時>{timeout}s(app忙/樹在蓋)"
    return out["v"]


def _probe_inner():
    hwnd = _focus_hwnd()
    r = _em_getsel(hwnd)
    if r is not None:
        return r
    return _uia_probe()


def probe(timeout=0.6):
    out = {"v": UNKNOWN}

    def run():
        try:
            out["v"] = _probe_inner()
        except Exception:
            pass
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout)
    return out["v"]


def _em_sel_len(hwnd):
    buf = ctypes.create_unicode_buffer(64)
    if not hwnd or not _u32.GetClassNameW(hwnd, buf, 64):
        return None
    if not buf.value.lower().startswith(("edit", "richedit", "tmemo", "tedit")):
        return None
    s, e, res = wt.DWORD(0), wt.DWORD(0), ctypes.c_size_t(0)
    if not _u32.SendMessageTimeoutW(hwnd, _EM_GETSEL, ctypes.byref(s), ctypes.byref(e),
                                    _SMTO_ABORTIFHUNG, 50, ctypes.byref(res)):
        return None
    return abs(e.value - s.value)


def sel_length(timeout=0.3):
    out = {"v": None}

    def run():
        try:
            n = _em_sel_len(_focus_hwnd())
            if n is None:
                t = _with_uia(lambda uia, elem: _vt(uia, 8, ctypes.c_void_p)(uia, ctypes.byref(elem)),
                              read=_uia_sel_text, unknown=None)
                if t is not None:
                    n = len(t) - t.count("\r\n")
            out["v"] = n
        except Exception:
            pass
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout)
    return out["v"]


def probe_hwnd(hwnd, timeout=0.6):
    out = {"v": UNKNOWN}

    def run():
        try:
            r = _em_getsel(hwnd)
            out["v"] = r if r is not None else _uia_probe_hwnd(hwnd)
        except Exception:
            pass
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout)
    return out["v"]


if __name__ == "__main__":
    import sys
    import time as _t
    sys.stdout.reconfigure(encoding="utf-8")
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    for _ in range(n):
        hw = _focus_hwnd()
        buf = ctypes.create_unicode_buffer(64)
        _u32.GetClassNameW(hw, buf, 64) if hw else None
        t0 = _t.perf_counter()
        v = probe()
        ms = (_t.perf_counter() - t0) * 1000
        print(f"{v:8s}  {ms:7.1f}ms  hwnd={hw:#x}  class={buf.value}")
        _t.sleep(0.7)
