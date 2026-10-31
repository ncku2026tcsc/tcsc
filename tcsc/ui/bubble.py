# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/tcsc2026/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import ctypes
import ctypes.wintypes as wt
import queue
import threading

_q = queue.Queue()
_state = {"thread": None, "dead": False}
_u32 = ctypes.WinDLL("user32", use_last_error=True)
_u32.GetWindowLongPtrW.restype = ctypes.c_longlong
_u32.GetWindowLongPtrW.argtypes = (wt.HWND, ctypes.c_int)
_u32.SetWindowLongPtrW.restype = ctypes.c_longlong
_u32.SetWindowLongPtrW.argtypes = (wt.HWND, ctypes.c_int, ctypes.c_longlong)
_u32.GetWindowThreadProcessId.restype = wt.DWORD
_u32.GetWindowThreadProcessId.argtypes = (wt.HWND, ctypes.c_void_p)

_COLORS = {"ok": "#3fb950", "info": "#58a6ff", "warn": "#d29922", "block": "#f85149"}
_BG, _FG = "#2b2b2b", "#e6e6e6"

_FACES = {
    "dark":    ("#2b2b2b", "深灰"),
    "white":   ("#FFFFFF", "白"),
    "cream":   ("#F5EDDC", "米・奶油"),
    "khaki":   ("#7D6B52", "深卡其"),
    "violet":  ("#8B5CF6", "紫"),
    "fuchsia": ("#D946EF", "洋紅"),
    "pink":    ("#F0669E", "粉紅"),
    "rose":    ("#FB5D75", "玫瑰"),
    "orange":  ("#FB8C3C", "橘"),
    "emerald": ("#10B981", "翠"),
    "teal":    ("#0EA5B7", "青"),
    "indigo":  ("#6366F1", "靛藍"),
}
_FACE_GROUPS = (("彩色", ("violet", "fuchsia", "pink", "rose",
                          "orange", "emerald", "teal", "indigo")),
                ("淺色", ("white", "cream")),
                ("深色", ("dark", "khaki")))
_DOT_ON_DARK = {"ok": "#C8FFD9", "info": "#DCEBFF",
                "warn": "#FFF0B8", "block": "#FFD9D2"}
_DOT_ON_LIGHT = {"ok": "#1a7f37", "info": "#0969da",
                 "warn": "#9a6700", "block": "#cf222e"}
_DOT_LEGACY = _COLORS


def _lum(hexs):
    try:
        r, g, b = (int(hexs[i:i + 2], 16) / 255 for i in (1, 3, 5))
    except Exception:
        return 0.0
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def face_now():
    bg = None
    try:
        from .. import settings as _s
        key = _s.get("bubble_face") or "dark"
        if key == "custom":
            bg = (_s.get("bubble_face_custom") or "").strip() or None
        elif key in _FACES:
            bg = _FACES[key][0]
    except Exception:
        bg = None
    if not (bg and len(bg) == 7 and bg[0] == "#"):
        bg = _BG
    if bg == _BG:
        return bg, _FG, _DOT_LEGACY, None
    if _lum(bg) > 0.45:
        return bg, "#565E68", _DOT_ON_LIGHT, "#cfc9bb"
    return bg, "#FFFFFF", _DOT_ON_DARK, None
_EX_THRU = 0x00000020


def _apply_thru(hwnd):
    try:
        from .. import settings
        on = bool(settings.get("bubble_thru"))
        ex = _u32.GetWindowLongPtrW(hwnd, -20)
        nx = (ex | _EX_THRU) if on else (ex & ~_EX_THRU)
        if nx != ex:
            _u32.SetWindowLongPtrW(hwnd, -20, nx)
    except Exception:
        pass


class _GUITHREADINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("flags", wt.DWORD), ("hwndActive", wt.HWND),
                ("hwndFocus", wt.HWND), ("hwndCapture", wt.HWND), ("hwndMenuOwner", wt.HWND),
                ("hwndMoveSize", wt.HWND), ("hwndCaret", wt.HWND), ("rcCaret", wt.RECT)]


def _infer_kind(msg):
    if any(w in msg for w in ("失敗", "錯誤", "擋下", "拒", "沒收", "取消寫回")):
        return "block"
    if any(w in msg for w in ("沒有", "沒抓到", "抓不到", "先按", "行首", "空行",
                              "再按一次", "請", "免按", "稍後")):
        return "warn"
    if "→" in msg or msg.startswith("已") or "已修正" in msg or "回到" in msg:
        return "ok"
    return "info"


_HOLD_MULT = {1: 0.5, 2: 0.75, 3: 1.0, 4: 1.5, 5: 2.5}


def _hold_ms(msg):
    head, _, tail = msg.partition("｜")
    n = len(head) + min(len(tail) // 3, 20)
    try:
        from .. import settings as _s
        m = _HOLD_MULT.get(int(_s.get("bubble_hold_level") or 3), 1.0)
    except Exception:
        m = 1.0
    return int(max(2200, min(6000, 1200 + 55 * n)) * m)


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT),
                ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]


def _workarea(hint_pt=None):
    try:
        if hint_pt is not None:
            mon = _u32.MonitorFromPoint(wt.POINT(hint_pt[0], hint_pt[1]), 2)
        else:
            fg = _u32.GetForegroundWindow()
            mon = _u32.MonitorFromWindow(fg, 2) if fg else None
        if mon:
            mi = _MONITORINFO()
            mi.cbSize = ctypes.sizeof(_MONITORINFO)
            if _u32.GetMonitorInfoW(mon, ctypes.byref(mi)):
                return mi.rcWork
    except Exception:
        pass
    wa = wt.RECT()
    _u32.SystemParametersInfoW(0x0030, 0, ctypes.byref(wa), 0)
    return wa


def _anchor(w, h, mode):
    try:
        if mode == "fixed":
            from .. import settings as _s
            x, y = _s.get("bubble_x"), _s.get("bubble_y")
            if isinstance(x, int) and isinstance(y, int):
                wa = _workarea((x, y))
                return (max(wa.left, min(x, wa.right - w - 8)),
                        max(wa.top, min(y, wa.bottom - h - 8)))
        wa = _workarea()
        if mode == "corner_bl":
            return wa.left + 16, wa.bottom - h - 16
        if mode == "corner_tr":
            return wa.right - w - 16, wa.top + 16
        if mode == "corner_tl":
            return wa.left + 16, wa.top + 16
        if mode not in ("corner", "fixed"):
            fg = _u32.GetForegroundWindow()
            if fg:
                tid = _u32.GetWindowThreadProcessId(fg, None)
                gti = _GUITHREADINFO()
                gti.cbSize = ctypes.sizeof(_GUITHREADINFO)
                if _u32.GetGUIThreadInfo(tid, ctypes.byref(gti)) and gti.hwndCaret:
                    pt = wt.POINT(gti.rcCaret.left, gti.rcCaret.bottom)
                    _u32.ClientToScreen(gti.hwndCaret, ctypes.byref(pt))
                    if pt.x or pt.y:
                        from .. import settings as _s
                        ox = int(_s.get("bubble_off_x") or 0)
                        oy = int(_s.get("bubble_off_y") or 0)
                        x, y = pt.x + 8 + ox, pt.y + 22 + oy
                        if y + h > wa.bottom - 8:
                            y = (pt.y - (gti.rcCaret.bottom - gti.rcCaret.top)
                                 - h - 26 + oy)
                        return (max(wa.left + 8, min(x, wa.right - w - 8)),
                                max(wa.top + 8, y))
                r = wt.RECT()
                if _u32.GetWindowRect(fg, ctypes.byref(r)) and r.right - r.left > 120:
                    return (max(wa.left + 8, min(r.right - w - 24, wa.right - w - 8)),
                            max(wa.top + 8, min(r.bottom - h - 48, wa.bottom - h - 8)))
        return wa.right - w - 16, wa.bottom - h - 16
    except Exception:
        return 60, 60


def _run():
    try:
        try:
            _u32.SetThreadDpiAwarenessContext(ctypes.c_ssize_t(-4))
        except Exception:
            pass
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.0)
        root.configure(bg=_BG)
        root.update_idletasks()
        hwnd0 = _u32.GetParent(root.winfo_id()) or root.winfo_id()
        try:
            _u32.GetDpiForWindow.restype = wt.UINT
            _u32.GetDpiForWindow.argtypes = (wt.HWND,)
            dpi = _u32.GetDpiForWindow(hwnd0) or 96
        except Exception:
            dpi = 96
        s = dpi / 96.0
        try:
            root.tk.call("tk", "scaling", dpi / 72.0)
        except Exception:
            pass
        row = tk.Frame(root, bg=_BG)
        row.pack(padx=int(12 * s), pady=int(7 * s))
        dot = tk.Label(row, text="●", font=("Microsoft JhengHei", 10), bg=_BG)
        dot.pack(side="left", padx=(0, int(7 * s)))
        lbl = tk.Label(row, font=("Microsoft JhengHei", 12), bg=_BG, fg=_FG,
                       justify="left", wraplength=int(460 * s))
        lbl.pack(side="left")
        root.update_idletasks()

        hwnd = _u32.GetParent(root.winfo_id()) or root.winfo_id()
        try:
            pref = ctypes.c_int(2)
            ctypes.WinDLL("dwmapi").DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(pref), 4)
        except Exception:
            pass
        GWL_EXSTYLE = -20
        ex = _u32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        _u32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE,
                               ex | 0x08000000 | 0x00000080)

        st = {"gen": 0}

        def fade(to, gen, step=0.18, then=None):
            if st["gen"] != gen:
                return
            cur = float(root.attributes("-alpha"))
            nxt = min(to, cur + step) if to > cur else max(to, cur - step)
            root.attributes("-alpha", nxt)
            if abs(nxt - to) > 0.01:
                root.after(16, fade, to, gen, step, then)
            elif then:
                then()

        def _size_mult():
            try:
                from .. import settings as _s
                lv = int(_s.get("bubble_size_level") or 3)
            except Exception:
                lv = 3
            return (0.8, 0.9, 1.0, 1.2, 1.45)[max(1, min(5, lv)) - 1]

        def show(msg, kind):
            _apply_thru(hwnd)
            bg, fg, dots, border = face_now()
            if st.get("face") != (bg, fg, border):
                st["face"] = (bg, fg, border)
                dot.configure(bg=bg)
                lbl.configure(bg=bg, fg=fg)
                row.configure(bg=bg)
                if border:
                    root.configure(bg=border)
                    row.pack_configure(padx=1, pady=1, ipadx=0, ipady=0)
                    dot.pack_configure(padx=(int(11 * s), int(7 * s)), pady=int(6 * s))
                    lbl.pack_configure(padx=(0, int(11 * s)), pady=int(6 * s))
                else:
                    root.configure(bg=bg)
                    row.pack_configure(padx=int(12 * s), pady=int(7 * s), ipadx=0, ipady=0)
                    dot.pack_configure(padx=(0, int(7 * s)), pady=0)
                    lbl.pack_configure(padx=0, pady=0)
            m = _size_mult()
            lbl.configure(font=("Microsoft JhengHei", max(8, round(12 * m))),
                          wraplength=int(460 * s * m))
            dot.configure(font=("Microsoft JhengHei", max(7, round(10 * m))))
            st["gen"] += 1
            gen = st["gen"]
            dot.configure(fg=dots.get(kind, dots["info"]))
            lbl.configure(text=msg)
            root.update_idletasks()
            w, h = root.winfo_reqwidth(), root.winfo_reqheight()
            from .. import settings as _s
            x, y = _anchor(w, h, _s.get("bubble_pos") or "auto")
            root.geometry(f"+{x}+{y}")
            root.deiconify()
            fade(0.94, gen)
            if not _s.get("bubble_pin"):
                root.after(_hold_ms(msg),
                           lambda: fade(0.0, gen, 0.12, root.withdraw))

        drag = {"px": 0, "py": 0, "moved": False}

        def d_start(e):
            st["gen"] += 1
            root.attributes("-alpha", 0.94)
            drag["px"] = e.x_root - root.winfo_x()
            drag["py"] = e.y_root - root.winfo_y()
            drag["moved"] = False

        def d_move(e):
            drag["moved"] = True
            root.geometry(f"+{e.x_root - drag['px']}+{e.y_root - drag['py']}")

        def d_end(e):
            from .. import settings as _s
            if not _s.get("bubble_pin"):
                gen = st["gen"]
                root.after(_hold_ms(lbl.cget("text") or ""),
                           lambda: fade(0.0, gen, 0.12, root.withdraw))

        for wgt in (root, row, dot, lbl):
            wgt.bind("<Button-1>", d_start)
            wgt.bind("<B1-Motion>", d_move)
            wgt.bind("<ButtonRelease-1>", d_end)

        def _invoke(it):
            fn = _state.get("menu_fn")

            def run():
                try:
                    icon = fn()[0] if fn else None
                    it(icon)
                except Exception:
                    pass
            threading.Thread(target=run, daemon=True).start()

        def _tkmenu_from(pmenu):
            m = tk.Menu(root, tearoff=0)
            try:
                items = list(pmenu.items)
            except Exception:
                items = []
            for it in items:
                try:
                    text = it.text
                except Exception:
                    text = None
                if text is None:
                    m.add_separator()
                    continue
                sub = getattr(it, "submenu", None)
                if sub is not None:
                    m.add_cascade(label=str(text), menu=_tkmenu_from(sub))
                    continue
                try:
                    chk = bool(it.checked)
                except Exception:
                    chk = False
                lab = ("✓ " if chk else "　　") + str(text)
                if getattr(it, "enabled", True):
                    m.add_command(label=lab, command=(lambda i=it: _invoke(i)))
                else:
                    m.add_command(label=lab, state="disabled")
            return m

        def r_click(e):
            fn = _state.get("menu_fn")
            if not fn:
                return
            m = None
            try:
                _icon, pmenu = fn()
                m = _tkmenu_from(pmenu)
                st["gen"] += 1
                root.attributes("-alpha", 0.94)
                m.tk_popup(e.x_root, e.y_root)
            except Exception:
                pass
            finally:
                if m is not None:
                    try:
                        m.grab_release()
                    except Exception:
                        pass

        for wgt in (root, row, dot, lbl):
            wgt.bind("<Button-3>", r_click)

        def tick(text, dotcolor):
            st["gen"] += 1
            gen = st["gen"]
            try:
                if text is not None:
                    lbl.configure(text=text)
                if dotcolor is not None:
                    if dotcolor in _COLORS:
                        dotcolor = face_now()[2].get(dotcolor, dotcolor)
                    dot.configure(fg=dotcolor)
                fade(0.94, gen)
            except Exception:
                pass
            from .. import settings as _s
            if not _s.get("bubble_pin"):
                root.after(_hold_ms(lbl.cget("text") or ""),
                           lambda: fade(0.0, gen, 0.12, root.withdraw))

        def poll():
            try:
                while True:
                    msg, kind = _q.get_nowait()
                    try:
                        if msg == "\x00TICK":
                            tick(*kind)
                        else:
                            show(msg, kind)
                    except Exception:
                        pass
            except queue.Empty:
                pass
            root.after(30, poll)

        poll()
        root.mainloop()
    except Exception:
        pass
    finally:
        _state["dead"] = True


def set_menu_provider(fn):
    _state["menu_fn"] = fn


def show(msg, kind=None):
    if _state["dead"] or not isinstance(msg, str) or not msg:
        return False
    if _state["thread"] is None or not _state["thread"].is_alive():
        _state["thread"] = threading.Thread(target=_run, daemon=True)
        _state["thread"].start()
    _q.put((msg, kind or _infer_kind(msg)))
    return True


def warmup():
    if _state["dead"]:
        return False
    if _state["thread"] is None or not _state["thread"].is_alive():
        _state["thread"] = threading.Thread(target=_run, daemon=True)
        _state["thread"].start()
    return True


def tick(text=None, dot=None):
    if _state["dead"] or _state["thread"] is None or not _state["thread"].is_alive():
        return False
    _q.put(("\x00TICK", (text, dot)))
    return True
