# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import ctypes
import threading
import time
from ctypes import wintypes

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_ole32 = ctypes.WinDLL("ole32")
_oleacc = ctypes.WinDLL("oleacc")
_oleaut = ctypes.WinDLL("oleaut32")

_OBJID_CLIENT = wintypes.DWORD(0xFFFFFFFC)
_VT_EMPTY, _VT_I4, _VT_DISPATCH = 0, 3, 9


class _GUID(ctypes.Structure):
    _fields_ = [("d1", ctypes.c_uint32), ("d2", ctypes.c_uint16),
                ("d3", ctypes.c_uint16), ("d4", ctypes.c_ubyte * 8)]


def _guid(s):
    g = _GUID()
    _ole32.CLSIDFromString(ctypes.c_wchar_p(s), ctypes.byref(g))
    return g


_IID_IAccessible = _guid("{618736E0-3C3D-11CF-810C-00AA00389B71}")
_IID_IServiceProvider = _guid("{6D5140C1-7436-11CE-8034-00AA006009FA}")
_IID_IAccessible2 = _guid("{E89F726E-C4F4-4C19-BB19-B647D7FA8478}")
_IID_IAccessibleText = _guid("{24FD2FFB-3AAD-4A08-8335-A3AD89C0FB4B}")
_IID_IAccessibleEditableText = _guid("{A59AA09A-7011-4B65-939D-32B1FB5547E3}")
_IID_IAccessibleHypertext = _guid("{6B4F8BBF-F1F2-418A-B35E-A195BC4103B9}")

_oleacc.AccessibleObjectFromWindow.argtypes = [
    wintypes.HWND, wintypes.DWORD, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
_oleacc.AccessibleObjectFromWindow.restype = ctypes.c_long
_oleaut.SysAllocString.argtypes = [ctypes.c_wchar_p]
_oleaut.SysAllocString.restype = ctypes.c_void_p
_oleaut.SysFreeString.argtypes = [ctypes.c_void_p]
_oleaut.SysStringLen.argtypes = [ctypes.c_void_p]
_oleaut.SysStringLen.restype = ctypes.c_uint


class _VARIANT(ctypes.Structure):
    _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort),
                ("r2", ctypes.c_ushort), ("r3", ctypes.c_ushort),
                ("val", ctypes.c_void_p), ("pad", ctypes.c_void_p)]


def _vt(ptr, idx, *argtypes):
    vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    ft = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)
    return ft(vtbl[idx])


def _release(p):
    try:
        v = p.value if hasattr(p, "value") else p
        if v:
            _vt(p, 2)(p)
    except Exception:
        pass


def _qi(ptr, iid):
    out = ctypes.c_void_p()
    hr = _vt(ptr, 0, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p))(
        ptr, ctypes.byref(iid), ctypes.byref(out))
    return out if (hr == 0 and out.value) else None


class _GTI(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("hwndActive", wintypes.HWND), ("hwndFocus", wintypes.HWND),
                ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
                ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND),
                ("rcCaret", wintypes.RECT)]


def _focus_hwnd():
    fg = _user32.GetForegroundWindow()
    tid = _user32.GetWindowThreadProcessId(fg, None)
    gti = _GTI()
    gti.cbSize = ctypes.sizeof(_GTI)
    if _user32.GetGUIThreadInfo(tid, ctypes.byref(gti)) and gti.hwndFocus:
        return gti.hwndFocus
    return fg


def _focused_acc():
    hwnd = _focus_hwnd()
    p = ctypes.c_void_p()
    hr = _oleacc.AccessibleObjectFromWindow(hwnd, _OBJID_CLIENT,
                                            ctypes.byref(_IID_IAccessible),
                                            ctypes.byref(p))
    if hr or not p.value:
        return None
    cur = p
    for _ in range(16):
        var = _VARIANT()
        hr = _vt(cur, 18, ctypes.POINTER(_VARIANT))(cur, ctypes.byref(var))
        if hr or var.vt != _VT_DISPATCH or not var.val:
            break
        child = _qi(ctypes.c_void_p(var.val), _IID_IAccessible)
        _release(ctypes.c_void_p(var.val))
        if not child:
            break
        _release(cur)
        cur = child
    return cur


def _text_ifaces(acc, need_edit):
    sp = _qi(acc, _IID_IServiceProvider)
    if not sp:
        return None, None, "無 IServiceProvider＝這裡沒有 IA2"
    ia2 = ctypes.c_void_p()
    hr = _vt(sp, 3, ctypes.POINTER(_GUID), ctypes.POINTER(_GUID),
             ctypes.POINTER(ctypes.c_void_p))(
        sp, ctypes.byref(_IID_IAccessible2), ctypes.byref(_IID_IAccessible2),
        ctypes.byref(ia2))
    _release(sp)
    if hr or not ia2.value:
        return None, None, "QueryService(IA2) 失敗＝無障礙樹沒醒（再按一次多半就通）或非 IA2 場地"
    txt = _qi(ia2, _IID_IAccessibleText)
    edit = _qi(ia2, _IID_IAccessibleEditableText) if need_edit else None
    _release(ia2)
    if not txt:
        _release(edit)
        return None, None, "焦點元素沒有 IAccessibleText＝不是文字框"
    if need_edit and not edit:
        _release(txt)
        return None, None, "沒有 IAccessibleEditableText＝這個編輯器不支援直改"
    return txt, edit, ""


def _u16len(s):
    return len(s.encode("utf-16-le")) // 2


def _get_text(txt, a, b):
    if b <= a:
        return ""
    bs = ctypes.c_void_p()
    hr = _vt(txt, 10, ctypes.c_long, ctypes.c_long,
             ctypes.POINTER(ctypes.c_void_p))(txt, a, b, ctypes.byref(bs))
    if hr:
        return None
    if not bs.value:
        return ""
    try:
        return ctypes.wstring_at(bs.value, _oleaut.SysStringLen(bs))
    finally:
        _oleaut.SysFreeString(bs)


def _long_prop(txt, slot):
    v = ctypes.c_long(-1)
    hr = _vt(txt, slot, ctypes.POINTER(ctypes.c_long))(txt, ctypes.byref(v))
    return v.value if hr == 0 else None


def _with_timeout(fn, timeout, hang_result):
    out = {"v": hang_result}

    def run():
        _ole32.CoInitializeEx(None, 0)
        inited = True
        try:
            out["v"] = fn()
        except Exception as e:
            out["v"] = (None, f"例外 {type(e).__name__}") if isinstance(hang_result, tuple) \
                else f"例外 {type(e).__name__}"
        finally:
            if inited:
                _ole32.CoUninitialize()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout)
    return out["v"]


_EMBED = "￼"
_VT_UNKNOWN = 13


def _u16_positions(s, ch):
    out, off = [], 0
    for c in s:
        if c == ch:
            out.append(off)
        off += 2 if ord(c) > 0xFFFF else 1
    return out


def _child_text_at(txt, char_index):
    ht = _qi(txt, _IID_IAccessibleHypertext)
    if not ht:
        return None
    try:
        idx = ctypes.c_long(-1)
        hr = _vt(ht, 24, ctypes.c_long, ctypes.POINTER(ctypes.c_long))(
            ht, char_index, ctypes.byref(idx))
        if hr or idx.value < 0:
            return None
        link = ctypes.c_void_p()
        hr = _vt(ht, 23, ctypes.c_long, ctypes.POINTER(ctypes.c_void_p))(
            ht, idx.value, ctypes.byref(link))
        if hr or not link.value:
            return None
        try:
            var = _VARIANT()
            hr = _vt(link, 9, ctypes.c_long, ctypes.POINTER(_VARIANT))(
                link, 0, ctypes.byref(var))
            if hr or var.vt not in (_VT_DISPATCH, _VT_UNKNOWN) or not var.val:
                return None
            unk = ctypes.c_void_p(var.val)
            child = _qi(unk, _IID_IAccessibleText)
            if not child:
                sp = _qi(unk, _IID_IServiceProvider)
                if sp:
                    ia2 = ctypes.c_void_p()
                    if not _vt(sp, 3, ctypes.POINTER(_GUID), ctypes.POINTER(_GUID),
                               ctypes.POINTER(ctypes.c_void_p))(
                            sp, ctypes.byref(_IID_IAccessible2),
                            ctypes.byref(_IID_IAccessible2), ctypes.byref(ia2)) \
                            and ia2.value:
                        child = _qi(ia2, _IID_IAccessibleText)
                        _release(ia2)
                    _release(sp)
            _release(unk)
            return child
        finally:
            _release(link)
    finally:
        _release(ht)


def _descend_caret(txt, max_hops=8):
    cur = txt
    hops = 0
    while hops < max_hops:
        caret = _long_prop(cur, 5)
        n = _long_prop(cur, 17) or 0
        s = _get_text(cur, 0, min(n, 400)) or ""
        if _EMBED not in s:
            return cur, caret, hops
        cands = []
        if caret is not None and caret >= 0:
            cands += [caret, caret - 1]
        cands += _u16_positions(s, _EMBED)
        best, best_caret = None, None
        seen = set()
        for ci in cands:
            if ci is None or ci < 0 or ci in seen:
                continue
            seen.add(ci)
            child = _child_text_at(cur, ci)
            if not child:
                continue
            cc = _long_prop(child, 5)
            if cc is not None and cc >= 0:
                if best:
                    _release(best)
                best, best_caret = child, cc
                break
            if best is None:
                best, best_caret = child, cc
            else:
                _release(child)
        if not best:
            return cur, caret, hops
        _release(cur)
        cur, hops = best, hops + 1
    return cur, _long_prop(cur, 5), hops


def _sel_range(txt):
    n = ctypes.c_long(0)
    if _vt(txt, 7, ctypes.POINTER(ctypes.c_long))(txt, ctypes.byref(n)) or n.value <= 0:
        return None
    a, b = ctypes.c_long(-1), ctypes.c_long(-1)
    hr = _vt(txt, 9, ctypes.c_long, ctypes.POINTER(ctypes.c_long),
             ctypes.POINTER(ctypes.c_long))(txt, 0, ctypes.byref(a), ctypes.byref(b))
    if hr or a.value < 0 or b.value <= a.value:
        return None
    return a.value, b.value


def _read(where, span, timeout):

    def work():
        acc = _focused_acc()
        if not acc:
            return None, "拿不到焦點元素（MSAA）"
        try:
            txt, _e, why = _text_ifaces(acc, need_edit=False)
            if not txt:
                return None, why
            txt, caret, _hops = _descend_caret(txt)
            try:
                if where == "sel":
                    r = _sel_range(txt)
                    if r is None:
                        return "", "沒有選取"
                    a, b = r
                else:
                    if caret is None or caret < 0:
                        return None, "讀不到游標位置（caret=-1）"
                    if where == "before":
                        a, b = max(0, caret - span), caret
                    else:
                        n = _long_prop(txt, 17)
                        a, b = caret, (min(caret + span, n) if n is not None else caret + span)
                s = _get_text(txt, a, b)
                if s is None:
                    return None, "get_text 失敗"
                return s, ""
            finally:
                _release(txt)
        finally:
            _release(acc)

    return _with_timeout(work, timeout, (None, f"逾時>{timeout}s（app 忙）"))


def read_before_caret(back=200, timeout=0.6):
    return _read("before", back, timeout)


def read_after_caret(fwd=50, timeout=0.6):
    return _read("after", fwd, timeout)


def read_selection(timeout=0.6):
    return _read("sel", 0, timeout)


def _replace(where, old, new, timeout):

    def work():
        acc = _focused_acc()
        if not acc:
            return "拿不到焦點元素（MSAA）"
        try:
            txt, _e0, why = _text_ifaces(acc, need_edit=False)
            if not txt:
                return why
            txt, caret, _hops = _descend_caret(txt)
            edit = _qi(txt, _IID_IAccessibleEditableText)
            try:
                if not edit:
                    return "游標節點沒有 IAccessibleEditableText＝不支援直改"
                if where == "sel":
                    r = _sel_range(txt)
                    if r is None:
                        return "沒有選取"
                    a, b = r
                else:
                    if caret is None or caret < 0:
                        return "讀不到游標位置"
                    if where == "before":
                        a, b = caret - _u16len(old), caret
                        if a < 0:
                            return "游標前不足舊字長度"
                    else:
                        a, b = caret, caret + _u16len(old)
                cur = _get_text(txt, a, b)
                if cur != old:
                    return "內容對不上（現場≠剛抓的）"
                bstr = _oleaut.SysAllocString(new)
                try:
                    pb = ctypes.c_void_p(bstr)
                    hr = _vt(edit, 8, ctypes.c_long, ctypes.c_long,
                             ctypes.POINTER(ctypes.c_void_p))(
                        edit, a, b, ctypes.byref(pb))
                finally:
                    _oleaut.SysFreeString(bstr)
                if hr:
                    return f"replaceText 失敗 hr=0x{hr & 0xFFFFFFFF:08X}"
                n16 = _u16len(new)
                _vt(txt, 15, ctypes.c_long)(txt, a if where == "after" else a + n16)
                for pause in (0.0, 0.06, 0.12):
                    if pause:
                        time.sleep(pause)
                    acc2 = _focused_acc()
                    if not acc2:
                        continue
                    try:
                        t2, _e2, _w2 = _text_ifaces(acc2, need_edit=False)
                        if not t2:
                            continue
                        t2, c2, _h2 = _descend_caret(t2)
                        try:
                            if c2 is None or c2 < 0:
                                continue
                            if c2 >= n16 and _get_text(t2, c2 - n16, c2) == new:
                                return ""
                            if _get_text(t2, c2, c2 + n16) == new:
                                return ""
                        finally:
                            _release(t2)
                    finally:
                        _release(acc2)
                return "寫後驗不過（回報成功但內容不對）"
            finally:
                _release(txt)
                _release(edit)
        finally:
            _release(acc)

    return _with_timeout(work, timeout, f"逾時>{timeout}s（app 忙）")


def read_node(timeout=0.8):

    def work():
        acc = _focused_acc()
        if not acc:
            return None, None, "拿不到焦點元素（MSAA）"
        try:
            txt, _e, why = _text_ifaces(acc, need_edit=False)
            if not txt:
                return None, None, why
            txt, caret, _hops = _descend_caret(txt)
            try:
                n = _long_prop(txt, 17)
                if n is None or n < 0:
                    return None, caret, "讀不到字數"
                s = _get_text(txt, 0, n)
                if s is None:
                    return None, caret, "get_text 失敗"
                return s, caret, ""
            finally:
                _release(txt)
        finally:
            _release(acc)

    return _with_timeout(work, timeout, (None, None, f"逾時>{timeout}s（app 忙）"))


def set_caret(offset, timeout=0.5):

    def work():
        acc = _focused_acc()
        if not acc:
            return False
        try:
            txt, _e, _why = _text_ifaces(acc, need_edit=False)
            if not txt:
                return False
            txt, _caret, _hops = _descend_caret(txt)
            try:
                return _vt(txt, 15, ctypes.c_long)(txt, offset) == 0
            finally:
                _release(txt)
        finally:
            _release(acc)

    return _with_timeout(work, timeout, False)


def u16_offset(s, idx):
    return _u16len(s[:idx])


def replace_before_caret(old, new, timeout=0.9):
    return _replace("before", old, new, timeout)


def replace_after_caret(old, new, timeout=0.9):
    return _replace("after", old, new, timeout)


def replace_selection(old, new, timeout=0.9):
    return _replace("sel", old, new, timeout)


def caret_editable(timeout=0.5):

    def work():
        acc = _focused_acc()
        if not acc:
            return None
        try:
            txt, _e, why = _text_ifaces(acc, need_edit=False)
            if not txt:
                return None
            txt, _caret, _hops = _descend_caret(txt)
            edit = _qi(txt, _IID_IAccessibleEditableText)
            try:
                return bool(edit)
            finally:
                _release(txt)
                _release(edit)
        finally:
            _release(acc)

    r = _with_timeout(work, timeout, None)
    return r if isinstance(r, bool) else None


if __name__ == "__main__":
    import sys
    import time
    sys.stdout.reconfigure(encoding="utf-8")
    do_write = "--write" in sys.argv
    print("15 秒。切到瀏覽器的輸入框打幾個字停著（游標留在字尾）。"
          + ("這輪含寫入測試：拿最後一個字原樣換掉自己＝畫面不會變。" if do_write else ""))
    def _peek():
        acc = _focused_acc()
        if not acc:
            return "✗ 拿不到焦點元素"
        try:
            txt, _e0, why = _text_ifaces(acc, need_edit=False)
            if not txt:
                return "✗ " + why
            txt, caret, hops = _descend_caret(txt)
            edit = _qi(txt, _IID_IAccessibleEditableText)
            try:
                n = _long_prop(txt, 17)
                s = _get_text(txt, 0, min(n or 0, 60)) if n else ""
                return (f"潛{hops}層 caret={caret} nChars={n} "
                        f"edit={'有' if edit else '無'} text={s!r}")
            finally:
                _release(txt)
                _release(edit)
        finally:
            _release(acc)

    ttl = ctypes.create_unicode_buffer(80)
    t0 = time.time()
    wrote = False
    while time.time() - t0 < 20:
        _user32.GetWindowTextW(_user32.GetForegroundWindow(), ttl, 80)
        info = _with_timeout(_peek, 0.6, "✗ 逾時")
        print(f"{time.time()-t0:5.1f}s  [{ttl.value[:24]}]  {info}", flush=True)
        if do_write and not wrote and isinstance(info, str) and "edit=有" in info:
            text, why = read_before_caret(back=4)
            if text:
                wrote = True
                ch = text[-1]
                r = replace_before_caret(ch, ch)
                print(f"        寫入測試（{ch!r}→{ch!r}）："
                      f"{'✓ 成功' if r == '' else '✗ ' + r}", flush=True)
        time.sleep(0.5)
    print("結束。")
