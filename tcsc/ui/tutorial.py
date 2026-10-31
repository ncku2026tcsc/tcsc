# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/tcsc2026/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import ctypes
import ctypes.wintypes as wt
import queue
import threading
import time

_u32 = ctypes.WinDLL("user32", use_last_error=True)
_g32 = ctypes.WinDLL("gdi32", use_last_error=True)
_u32.GetWindowLongPtrW.restype = ctypes.c_longlong
_u32.GetWindowLongPtrW.argtypes = (wt.HWND, ctypes.c_int)
_u32.SetWindowLongPtrW.restype = ctypes.c_longlong
_u32.SetWindowLongPtrW.argtypes = (wt.HWND, ctypes.c_int, ctypes.c_longlong)
_u32.SendMessageW.restype = ctypes.c_longlong
_u32.SendMessageW.argtypes = (wt.HWND, wt.UINT, ctypes.c_size_t, ctypes.c_longlong)
_u32.CreateWindowExW.restype = wt.HWND
_u32.CreateWindowExW.argtypes = (wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
                                 ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                 wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID)
_u32.GetParent.restype = wt.HWND
_u32.GetParent.argtypes = (wt.HWND,)
_u32.GetForegroundWindow.restype = wt.HWND
_g32.CreateFontW.restype = wt.HANDLE

_PALS = {True:  {"bg": "#1f1f1f", "fg": "#e6e6e6", "dim": "#9a9a9a",
                 "btn": "#3a3a3a", "sel": "#264f78", "ebg": 0x2b2b2b, "efg": 0xe6e6e6},
         False: {"bg": "#f4f4f4", "fg": "#111111", "dim": "#888888",
                 "btn": "#e3e3e3", "sel": "#b5d5ff", "ebg": 0xffffff, "efg": 0x111111}}
_ACC, _RED = "#3fb950", "#f85149"

_SENT_L1 = "這個城市跑步起來"
_SENT_L1_OK = "這個程式跑不起來"
_SENT_L2 = "溢波位評議剝柚起"
_SENT_L2_OK = "一波未平一波又起"
_SENT_L3 = "1u3bj6gji 5k4rm4"
_SENT_L3_OK = "比如說這句"
_FREE_SENTS = ("你燒等一下", "我過去在你", "這是值得還是衡的", "你拿去彥頤下")
_PLAY_TEXT = ("一、二、三，短的先跳。\r\n"
              "接著是一句很長很長中間完全沒有任何標點的句子讓你一口氣跳過去試試看。\r\n"
              "\r\n"
              "游標就是你的腳：整塊用雙擊、精準用報數。\r\n"
              "早上買了咖啡、麵包，還有一顆蘋果。\r\n"
              "往左跳一格、往右跳三格，標點是路標。\r\n"
              "\r\n"
              "反白靶場：圈住「我的排只剩下」按 F1 修修看。\r\n"
              "刪除沙包：這一行專門給刪除家族拆，隨便刪！\r\n"
              "\r\n"
              "練完這一段，左手就出師了。")

_q = queue.Queue()
_st = {"alive": False}
_drip = {"done": False}


def notify(event):
    try:
        if _st["alive"]:
            _q.put(event)
            return
        if event != "f1_ok" or _drip["done"]:
            return
        from .. import settings
        if settings.get("tutorial_invited"):
            _drip["done"] = True
            return
        if not settings.get("tutorial_seen"):
            return
        n = int(settings.get("tutorial_f1n") or 0) + 1
        settings.set("tutorial_f1n", n)
        if n >= 20:
            settings.set("tutorial_invited", True)
            _drip["done"] = True
            from . import bubble
            bubble.show("✨ F1 已上手！還有不用滑鼠的移動術——"
                        "系統匣右鍵 → 使用說明 → 快速移動教學")
    except Exception:
        pass


def start(warmup=None, on_close=None):
    return _launch(_LESSONS, warmup, on_close)


def start_movers():
    return _launch(_MOVER_LESSONS, None, None)


def _launch(lessons, warmup, on_close):
    if _st["alive"]:
        return None
    _st["alive"] = True
    while not _q.empty():
        try:
            _q.get_nowait()
        except Exception:
            break
    t = threading.Thread(target=_run, args=(lessons, warmup, on_close), daemon=True)
    t.start()
    return t


def _praise(msg):
    try:
        from . import bubble
        bubble.show(msg)
    except Exception:
        pass


def _mark_seen():
    try:
        from .. import settings
        settings.set("tutorial_seen", True)
    except Exception:
        pass


def _run(lessons, warmup, on_close):
    from .. import logbook
    dblwin_orig = None
    try:
        try:
            _u32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            pass
        if warmup is not None:
            threading.Thread(target=lambda: _swallow(warmup), daemon=True).start()
        logbook.TUTORIAL = True
        try:
            from .. import settings
            cur = float(settings.get("mover_dbl_win", 0.18) or 0.18)
            if cur < 0.35:
                dblwin_orig = cur
                settings.set("mover_dbl_win", 0.35)
        except Exception:
            pass
        _card(lessons)
    except Exception:
        pass
    finally:
        logbook.TUTORIAL = False
        if dblwin_orig is not None:
            try:
                from .. import settings
                settings.set("mover_dbl_win", dblwin_orig)
            except Exception:
                pass
        _st["alive"] = False
        if on_close is not None:
            _swallow(on_close)


def _swallow(fn):
    try:
        fn()
    except Exception:
        pass


_WS_CHILD, _WS_VISIBLE, _WS_BORDER = 0x40000000, 0x10000000, 0x00800000
_ES_AUTOHSCROLL, _EM_SETSEL = 0x80, 0x00B1
_ES_MULTILINE, _ES_AUTOVSCROLL, _WS_VSCROLL = 0x0004, 0x0040, 0x00200000
_EM_SETBKGNDCOLOR, _EM_SETCHARFORMAT, _SCF_ALL, _CFM_COLOR = 0x0443, 0x0444, 4, 0x40000000
_GWL_EXSTYLE, _WS_EX_NOACTIVATE = -20, 0x08000000
_SW_HIDE = 0


class _CHARFORMAT2W(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("dwMask", wt.DWORD), ("dwEffects", wt.DWORD),
                ("yHeight", ctypes.c_long), ("yOffset", ctypes.c_long),
                ("crTextColor", wt.COLORREF), ("bCharSet", ctypes.c_byte),
                ("bPitchAndFamily", ctypes.c_byte), ("szFaceName", ctypes.c_wchar * 32),
                ("wWeight", wt.WORD), ("sSpacing", ctypes.c_short),
                ("crBackColor", wt.COLORREF), ("lcid", wt.LCID), ("dwReserved", wt.DWORD),
                ("sStyle", ctypes.c_short), ("wKerning", wt.WORD),
                ("bUnderlineType", ctypes.c_byte), ("bAnimation", ctypes.c_byte),
                ("bRevAuthor", ctypes.c_byte), ("bReserved1", ctypes.c_byte)]


class _Edit:

    def __init__(self, parent_hwnd, x, y, w, h, text, px):
        cls = "EDIT"
        try:
            ctypes.WinDLL("Msftedit.dll")
            cls = "RICHEDIT50W"
        except Exception:
            pass
        self.rich = cls == "RICHEDIT50W"
        style = (_WS_CHILD | _WS_VISIBLE | _WS_BORDER
                 | _ES_MULTILINE | _ES_AUTOVSCROLL | _WS_VSCROLL)
        self.h = _u32.CreateWindowExW(0, cls, text, style,
                                      x, y, w, h, parent_hwnd, None, None, None)
        f = _g32.CreateFontW(-px, 0, 0, 0, 400, 0, 0, 0, 136, 0, 0, 5, 0,
                             "Microsoft JhengHei UI")
        _u32.SendMessageW(self.h, 0x30, f, 1)
        _u32.SendMessageW(self.h, _EM_SETSEL, 30000, 30000)

    def set_colors(self, bg, fgc):
        if not self.rich:
            return
        _u32.SendMessageW(self.h, _EM_SETBKGNDCOLOR, 0, bg)
        cf = _CHARFORMAT2W()
        cf.cbSize = ctypes.sizeof(_CHARFORMAT2W)
        cf.dwMask = _CFM_COLOR
        cf.crTextColor = fgc
        _u32.SendMessageW(self.h, _EM_SETCHARFORMAT, _SCF_ALL,
                          ctypes.cast(ctypes.byref(cf), ctypes.c_void_p).value)

    def text(self):
        n = _u32.GetWindowTextLengthW(self.h)
        buf = ctypes.create_unicode_buffer(n + 2)
        _u32.GetWindowTextW(self.h, buf, n + 1)
        return buf.value

    def set_text(self, s):
        _u32.SetWindowTextW(self.h, s)
        _u32.SendMessageW(self.h, _EM_SETSEL, 30000, 30000)

    def sel(self):
        a, b = wt.DWORD(), wt.DWORD()
        _u32.SendMessageW(self.h, 0x00B0,
                          ctypes.cast(ctypes.byref(a), ctypes.c_void_p).value,
                          ctypes.cast(ctypes.byref(b), ctypes.c_void_p).value)
        return a.value, b.value

    def caret_end(self):
        _u32.SendMessageW(self.h, _EM_SETSEL, 30000, 30000)

    def hide(self):
        _u32.ShowWindow(self.h, _SW_HIDE)

    def show_(self):
        _u32.ShowWindow(self.h, 5)


_LESSONS = [
    ("按一下 F1，選錯的字自己變對",
     "格子裡是新注音選錯的句子，游標已經在句尾。\n"
     "按 F1（鍵盤最上排）。第一次按會暖身幾秒。", "edit",
     [("F1", 0x70, "按我")]),
    ("算一半？按 F3 再算一遍",
     "先按 F1：通常會先改對一部分。\n"
     "還有字不對？按 F3，從現在這句再算一次。\n"
     "不對就再算，來回幾次就會對。", "iter",
     [("F1", 0x70, "①"), ("F3", 0x72, "②")]),
    ("忘了切中文？一樣按 F1",
     "這串是忘了切注音、直接打出來的英文。\n"
     "按 F1，變回中文。", "garble",
     [("F1", 0x70, "按我")]),
    ("學會了：只要記五顆鍵",
     "F1　選錯字就按，不對再按\n"
     "F2　按過頭退回上一個（Shift+F2 回到原本打的句子）\n"
     "F3　改對一部分，把目前算的再丟進去算一遍\n"
     "F7　人名、專有名詞：反白兩個字以上的詞，按 5 下教它\n"
     "F8　在、再選反了\n\n"
     "程式住在右下角，關掉這張卡也一直在。\n"
     "其他好用功能不用記：右下角圖示按右鍵 → 使用說明\n\n"
     "本程式開源、不營利、完全離線，\n"
     "你打的每個字都只留在你電腦裡。", "done", []),
]
_MOVER_LESSONS = [
    ("雙擊＝快速移動（本程式精華）",
     "格子換成一篇文章了。左手握緊 Ctrl+Alt——\n"
     "連點，雙擊！＝同一顆鍵快速點兩下（滑鼠雙擊的速度）\n"
     "雙擊 ←＝一口氣跳到上一個標點（→＝往右跳）。\n"
     "點太慢＝只走一格，下面會教你。", "jump",
     [("Ctrl", 0x11, "握住"), ("Alt", 0x12, "握住"), ("←", 0x25, "快速按兩下・連點"),
      ("→", 0x27, "快速按兩下・連點")]),
    ("跳段落",
     "Ctrl+Alt 握著，快速雙擊 ↑ 或 ↓\n直奔上／下一個空行（空行＝段落路標）", "para",
     [("Ctrl", 0x11, "握住"), ("Alt", 0x12, "握住"), ("↑", 0x26, "快速按兩下・連點"),
      ("↓", 0x28, "快速按兩下・連點")]),
    ("報數",
     "握著 Ctrl+Alt 按一下 →，馬上按數字 3\n一次走三格（懶得雙擊時的精準跳法）", "count",
     [("Ctrl", 0x11, "握住"), ("Alt", 0x12, "握住"), ("→", 0x27, ""),
      ("3", (0x33, 0x63), "數字")]),
    ("反白",
     "和弦加一指：Ctrl+Alt+Shift+←\n雙擊＝一口氣圈整塊\n圈完按 F1＝只修圈住的字", "sel",
     [("Ctrl", 0x11, "握住"), ("Alt", 0x12, "握住"), ("Shift", 0x10, "加一指"),
      ("←", 0x25, "快速按兩下・連點")]),
    ("刪除",
     "Ctrl+Alt+Backspace 雙擊＝刪掉整塊\n（+Shift＝改往右刪；也吃報數）", "del",
     [("Ctrl", 0x11, "握住"), ("Alt", 0x12, "握住"), ("⌫", 0x08, "快速按兩下・連點")]),
    ("快速移動學會了",
     "Ctrl+Alt 握著：\n"
     "←→ 雙擊跳到標點、↑↓ 雙擊跳到空行\n"
     "按一下接數字＝走幾格\n"
     "加 Shift＝圈選，圈完按 F1 只修圈住的\n"
     "Backspace 雙擊＝刪掉整塊", "done", []),
]
_PLAY_KINDS = ("jump", "para", "count", "sel", "del", "glide")
_TEXTS = {"edit": _SENT_L1, "iter": _SENT_L2, "garble": _SENT_L3}


def _card(L):
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    root.title("一分鐘教學" if L is _LESSONS else "快速移動教學")
    root.attributes("-topmost", True)
    root.resizable(False, False)
    scale = max(1.0, root.winfo_fpixels("1i") / 96.0)
    W, H = int(438 * scale), int(506 * scale)
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{W}x{H}+{int(sw * 0.55)}+{int(sh * 0.30)}")

    head = tk.Label(root, text="", justify="left",
                    font=("Microsoft JhengHei UI", 14, "bold"))
    head.pack(anchor="w", padx=14, pady=(12, 2))
    body = tk.Label(root, text="", justify="left",
                    wraplength=W - int(30 * scale), font=("Microsoft JhengHei UI", 11))
    body.pack(anchor="w", padx=14, pady=(0, 2))
    slot = tk.Frame(root, height=int(150 * scale))
    slot.pack(fill="x", padx=14, pady=2)
    keys_cv = tk.Canvas(root, height=int(96 * scale),
                        highlightthickness=0, bd=0)
    keys_cv.pack(fill="x", padx=14, pady=(0, 2))
    keys_cv.bind("<Button-1>",
                 lambda _e: state.update(notme_until=time.time() + 2.2))
    aux = tk.Frame(root)
    aux.pack(anchor="w", padx=14)
    bottom = tk.Frame(root)
    bottom.pack(side="bottom", fill="x", padx=14, pady=10)
    prog = tk.Label(bottom, text="", font=("Microsoft JhengHei UI", 10))
    state = {"lesson": 0, "edit": None, "caret_done": False, "hits": 0,
             "passing": False, "prev": None, "last_txt": None, "venue": None,
             "keys": [], "keycaps": [], "hint_id": 0, "finger": None,
             "guide_until": 0.0, "guide_txt": "", "ok_until": 0.0,
             "ok_txt": "✔ 已成功", "tick": 0}

    dark = {"v": True}
    try:
        from .. import settings as _s
        bv = _s.get("box_dark")
        if bv is None:
            _s.set("box_dark", True)
            bv = True
        dark["v"] = bool(bv)
    except Exception:
        pass

    def skip_all():
        if L[state["lesson"]][2] != "done":
            from tkinter import messagebox
            if not messagebox.askyesno("等等", "確定跳過嗎？一分鐘就好",
                                       parent=root):
                return
        _mark_seen()
        _praise("教學先收起來了。想回來：右下角圖示按右鍵 → 使用說明 → 重看教學")
        root.destroy()

    def back_step():
        if state["lesson"] > 0 and not state["passing"]:
            show(state["lesson"] - 1)

    btn_theme = tk.Button(root, text="", command=lambda: toggle_theme(), relief="flat",
                          font=("Microsoft JhengHei UI", 9))
    btn_theme.place(relx=1.0, y=int(8 * scale), x=-12, anchor="ne")
    prog.pack(side="left")
    btn_skip = tk.Button(bottom, text="跳過教學", command=skip_all, relief="flat",
                         font=("Microsoft JhengHei UI", 9))
    btn_skip.pack(side="right")
    btn_next = tk.Button(bottom, text="這步先跳過 ▸", command=lambda: advance(),
                         relief="flat", bd=0, font=("Microsoft JhengHei UI", 9))
    btn_next.pack(side="right", padx=6)
    btn_back = tk.Button(bottom, text="◂ 上一步", command=back_step,
                         relief="flat", bd=0, font=("Microsoft JhengHei UI", 9))
    btn_back.pack(side="right")
    root.protocol("WM_DELETE_WINDOW", skip_all)

    root.deiconify()
    root.update_idletasks()
    top_hwnd = int(_u32.GetParent(root.winfo_id()) or root.winfo_id())

    def _fg():
        return int(_u32.GetForegroundWindow() or 0)


    def apply_theme():
        p = _PALS[dark["v"]]
        root.configure(bg=p["bg"])
        for w in (slot, aux, bottom):
            w.configure(bg=p["bg"])
        head.configure(bg=p["bg"], fg=p["fg"])
        body.configure(bg=p["bg"], fg=p["fg"])
        prog.configure(bg=p["bg"], fg=p["dim"])
        btn_skip.configure(bg=p["btn"], fg=p["fg"], activebackground=p["sel"],
                           activeforeground=p["fg"])
        btn_theme.configure(bg=p["btn"], fg=p["fg"], activebackground=p["sel"],
                            activeforeground=p["fg"],
                            text=("淺色模式" if dark["v"] else "深色模式"))
        for w in (btn_next, btn_back):
            w.configure(bg=p["bg"], fg=p["dim"], activebackground=p["bg"],
                        activeforeground=p["fg"])
        for w_ in aux.winfo_children():
            try:
                if isinstance(w_, tk.Label):
                    w_.configure(bg=p["bg"], fg=p["dim"])
                elif str(w_.cget("bg")) != _ACC:
                    w_.configure(bg=p["btn"], fg=p["fg"], activebackground=p["sel"])
            except Exception:
                pass
        if state["edit"] is not None:
            state["edit"].set_colors(p["ebg"], p["efg"])
        draw_keys()
        try:
            v = ctypes.c_int(1 if dark["v"] else 0)
            for attr in (20, 19):
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        wt.HWND(top_hwnd), attr, ctypes.byref(v), ctypes.sizeof(v)) == 0:
                    break
        except Exception:
            pass

    def toggle_theme():
        dark["v"] = not dark["v"]
        try:
            from .. import settings as _s
            _s.set("box_dark", dark["v"])
        except Exception:
            pass
        apply_theme()

    def draw_keys():
        keys_cv.delete("all")
        state["keycaps"] = []
        state["finger"] = None
        p = _PALS[dark["v"]]
        keys_cv.configure(bg=p["bg"])
        x = int(4 * scale)
        top, kh = int(18 * scale), int(32 * scale)
        target = None
        for n, (label, vk, badge) in enumerate(state["keys"]):
            if n:
                keys_cv.create_text(x - int(10 * scale), top + kh // 2, text="＋",
                                    fill=p["dim"], font=("Microsoft JhengHei UI", 10))
            kw = max(int(40 * scale), int((26 + 8 * len(label)) * scale))
            rid = keys_cv.create_rectangle(x, top, x + kw, top + kh,
                                           fill=p["btn"], outline=p["dim"])
            tid = keys_cv.create_text(x + kw // 2, top + kh // 2, text=label,
                                      fill=p["fg"],
                                      font=("Microsoft JhengHei UI", 12, "bold"))
            if badge:
                dbl = "連點" in badge
                keys_cv.create_text(x + kw // 2, top - int(9 * scale), text=badge,
                                    fill=(p["fg"] if dbl else p["dim"]),
                                    font=("Microsoft JhengHei UI",
                                          9 if dbl else 8,
                                          "bold" if dbl else "normal"))
            state["keycaps"].append((rid, tid, vk, badge))
            if target is None and any(k in badge for k in
                                      ("連點", "按住", "數字", "按我", "①")):
                target = (x + kw // 2, vk)
            x += kw + int((44 if len(badge) >= 4 else 20) * scale)
        if target is None and state["keycaps"]:
            rid, tid, vk, _b = state["keycaps"][0]
            target = (int(4 * scale) + max(int(40 * scale),
                      int((26 + 8 * len(state["keys"][0][0])) * scale)) // 2, vk)
        state["hint_id"] = keys_cv.create_text(
            int(6 * scale), top + kh + int(34 * scale), anchor="w", text="", fill=_ACC,
            font=("Microsoft JhengHei UI", 10, "bold"))
        if target is not None:
            tx, tvk = target
            fy = top + kh + int(13 * scale)
            state["finger"] = (keys_cv.create_text(
                tx, fy, text="👆︎", fill=p["fg"],
                font=("Segoe UI Symbol", 13)), tx, fy)
            state["target_vk"] = tvk
        else:
            state["target_vk"] = None

    def show(i):
        state["lesson"] = i
        state.update(passing=False, caret_done=False, hits=0, pressed_once=False,
                     prev=None, last_txt=None, guide_until=0.0, guide_txt="",
                     ok_until=0.0, ok_txt="✔ 已成功", free_fixed=False, had_text=False)
        h, b, kind, keys = L[i]
        head.config(text=h)
        body.config(text=b)
        state["keys"] = keys
        prog.config(text="  ".join(
            "●" if j < i else ("◉" if j == i else "○") for j in range(len(L))))
        for w_ in aux.winfo_children():
            w_.destroy()
        if state["edit"] is None and kind not in ("intro", "done"):
            root.update_idletasks()
            state["edit"] = _Edit(slot.winfo_id(), 0, 0,
                                  slot.winfo_width(), slot.winfo_height(),
                                  "", int(15 * scale))
            state["venue"] = None
        e = state["edit"]
        if e is not None:
            if kind in _TEXTS:
                e.set_text(_TEXTS[kind])
                state["venue"] = kind
                e.show_()
            elif kind == "cycle":
                if state["venue"] != "sent":
                    e.set_text(_SENT_L1)
                    state["venue"] = "sent"
                e.show_()
            elif kind in _PLAY_KINDS:
                if state["venue"] != "play":
                    e.set_text(_PLAY_TEXT)
                    state["venue"] = "play"
                e.show_()
            elif kind == "free":
                if state["venue"] != "free":
                    e.set_text("")
                    state["venue"] = "free"
                e.show_()

                def pick(s_):
                    e.set_text(s_)
                    _u32.SetFocus(e.h)
                    e.caret_end()
                    state.update(free_fixed=False, had_text=True, passing=False)
                for k_, s_ in enumerate(_FREE_SENTS):
                    tk.Button(aux, text=s_, command=lambda s_=s_: pick(s_), relief="flat", anchor="w", padx=8,
                              font=("Microsoft JhengHei UI", 10)).grid(row=k_ // 2, column=k_ % 2, sticky="ew",
                                                                       padx=(0, 6), pady=2)
            else:
                e.hide()
        if kind == "intro":
            tk.Button(aux, text="開始教學 ▸", command=lambda: advance(), bg=_ACC,
                      fg="#0b2812", relief="flat",
                      font=("Microsoft JhengHei UI", 10, "bold"),
                      activebackground="#4cc960").pack(anchor="w", pady=4)
        if kind == "done":
            tk.Button(aux, text="完成", command=lambda: finish(), bg=_ACC,
                      fg="#0b2812", relief="flat",
                      font=("Microsoft JhengHei UI", 10, "bold"),
                      activebackground="#4cc960").pack(anchor="w", pady=4)
        if kind == "done":
            btn_next.configure(text="↻ 再玩一次", state="normal",
                               command=lambda: show(0))
            btn_skip.configure(text="完成教學")
        elif kind == "free":
            def _skip_free():
                from tkinter import messagebox
                if messagebox.askyesno("🎓 等等",
                                       "這是最重要的一步，認真建議別跳！\n真的要跳過嗎？",
                                       parent=root):
                    advance()
            btn_next.configure(text="這步先跳過 ▸", state="normal", command=_skip_free)
            btn_skip.configure(text="跳過教學")
        else:
            btn_next.configure(text="這步先跳過 ▸", state="normal",
                               command=lambda: advance())
            btn_skip.configure(text="跳過教學")
        btn_back.configure(state=("disabled" if i == 0 else "normal"))
        apply_theme()

    def finish():
        _mark_seen()
        _praise("學會了！想複習：右下角圖示按右鍵 → 使用說明 → 重看教學")
        root.destroy()

    def advance():
        i = state["lesson"] + 1
        if i >= len(L):
            finish()
            return
        show(i)

    def lesson_pass(msg, dwell=5.0):
        if state["passing"]:
            return
        state["passing"] = True
        state["ok_until"] = time.time() + 2.2
        _praise(msg)
        root.after(int(dwell * 1000), advance)

    def hit(done_msg, mid_msg="👍 已成功！再來一次", need=2, dwell=5.0):
        if state["passing"]:
            return
        state["hits"] += 1
        state["ok_until"] = time.time() + 2.6
        state["ok_txt"] = "✔ 已成功　再試一次！"
        state["guide_until"] = 0.0
        if state["hits"] >= need:
            lesson_pass(done_msg, dwell)
        elif state["hits"] == 1:
            _praise(mid_msg)

    def guide(txt):
        if not state["passing"]:
            state["guide_txt"] = txt
            state["guide_until"] = time.time() + 2.0

    _FINGER_DIP = (0, 0, -6, 0, -6, 0, 0, 0, 0, 0, 0, 0)

    def pump():
        try:
            evs = []
            while True:
                evs.append(_q.get_nowait())
        except Exception:
            pass
        now = time.time()
        p = _PALS[dark["v"]]
        guiding = now < state["guide_until"]
        ok = now < state["ok_until"]
        _memo = {}

        def saw(vk):
            if vk not in _memo:
                _memo[vk] = bool(_u32.GetAsyncKeyState(vk) & 0x8001)
            return _memo[vk]
        tvk = state.get("target_vk")
        blink = (state["tick"] // 5) % 2 == 0
        lit = state.setdefault("lit", {})
        for rid, tid, vk, badge in state["keycaps"]:
            vks = vk if isinstance(vk, tuple) else (vk,)
            if any(saw(v) for v in vks):
                lit[rid] = now + 0.25
                if vk == tvk:
                    state["pressed_once"] = True
            down = now < lit.get(rid, 0)
            fill, tfill = (_ACC, "#0b2812") if down else (p["btn"], p["fg"])
            if (vk == tvk and not down and blink
                    and not state["pressed_once"]):
                tfill = _RED
            try:
                keys_cv.itemconfigure(rid, fill=fill)
                keys_cv.itemconfigure(tid, fill=tfill)
            except Exception:
                pass
        try:
            if state["passing"]:
                dots = "." * (1 + (state["tick"] // 6) % 3)
                keys_cv.itemconfigure(state["hint_id"],
                                      text=f"✔ 已成功　正在載入下一關{dots}", fill=_ACC)
            elif now < state.get("notme_until", 0):
                keys_cv.itemconfigure(state["hint_id"],
                                      text="不是按我，按鍵盤上的！", fill=_RED)
            elif ok:
                keys_cv.itemconfigure(state["hint_id"], text=state["ok_txt"], fill=_ACC)
            elif guiding:
                keys_cv.itemconfigure(state["hint_id"], text=state["guide_txt"],
                                      fill=_ACC)
            else:
                keys_cv.itemconfigure(state["hint_id"], text="")
        except Exception:
            pass
        state["tick"] += 1
        if state["finger"] is not None:
            fid, fx, fy = state["finger"]
            try:
                keys_cv.coords(fid, fx, fy + _FINGER_DIP[state["tick"] % len(_FINGER_DIP)])
            except Exception:
                pass

        i = state["lesson"]
        kind = L[i][2]
        e = state["edit"]
        if e is None or state["passing"] or kind in ("intro", "done"):
            root.after(80, pump)
            return
        s0, s1 = e.sel()
        ln = _u32.GetWindowTextLengthW(e.h)
        cur = (s0, s1, ln)
        prev = state["prev"] or cur
        state["prev"] = cur
        moved = cur[0] - prev[0]
        flat = cur[0] == cur[1]
        was_flat = prev[0] == prev[1]
        same_len = cur[2] == prev[2]
        ca = (bool(_u32.GetAsyncKeyState(0x11) & 0x8000)
              and bool(_u32.GetAsyncKeyState(0x12) & 0x8000))
        if saw(0x25) or saw(0x27):
            state["lr_t"] = now
        if saw(0x26) or saw(0x28):
            state["ud_t"] = now
        if saw(0x10):
            state["sh_t"] = now
        if saw(0x0D):
            state["ent_t"] = now
        lr = now - state.get("lr_t", 0) < 0.6
        ud = now - state.get("ud_t", 0) < 0.6
        sh = now - state.get("sh_t", 0) < 0.6
        ent = now - state.get("ent_t", 0) < 0.6

        if not state["caret_done"] and _fg() == top_hwnd:
            _u32.SetFocus(e.h)
            e.caret_end()
            state["caret_done"] = True
        if kind == "edit":
            t = e.text()
            if _SENT_L1_OK in t or ("f1_ok" in evs and t and t != _SENT_L1):
                lesson_pass("選錯的字自己變對了")
        elif kind == "iter":
            t = e.text()
            if _SENT_L2_OK in t:
                lesson_pass("對了！F1 算，F3 再算，這就是用法")
            elif t and t != _SENT_L2 and t != state["last_txt"]:
                state["last_txt"] = t
                state["ok_until"] = now + 8.0
                state["ok_txt"] = "改對一部分了！還有字不對？按 F3 把它再丟進去算一遍"
            elif t == _SENT_L2 and state["last_txt"] not in (None, _SENT_L2):
                state["last_txt"] = t
                state["ok_until"] = now + 6.0
                state["ok_txt"] = "回到原句了，再按一次 F1"
        elif kind == "garble":
            t = e.text()
            if _SENT_L3_OK in t or (t and t != _SENT_L3 and not any("a" <= c.lower() <= "z" for c in t)):
                lesson_pass("忘了切中文也救得回來")
        elif kind == "cycle":
            t = e.text()
            if state["last_txt"] is None:
                state["last_txt"] = t
            elif t and t != state["last_txt"]:
                state["last_txt"] = t
                hit("🎲 候選在手！滿意了按 Enter 收工",
                    "👍 已成功！再換一個看看（F2＝退回）")
        elif kind == "jump":
            if ca and lr and flat and abs(moved) == 1 and same_len:
                guide("👌 有動！接著同一顆鍵快速按兩下＝跳整塊")
            elif (ca and lr and flat and abs(moved) >= 2 and same_len) or "mover_dbl" in evs:
                hit("🐇 整塊跳達成——這一下就是精華", "👍 已成功！再跳一塊")
        elif kind == "para":
            if ca and ud and flat and abs(moved) >= 2 and same_len:
                hit("🪜 跳段落入手——空行就是路標", "👍 已成功！再跳一段")
        elif kind == "count":
            if (ca and flat and abs(moved) >= 2 and same_len and not ud) or "mover_num" in evs:
                hit("🎯 報數移動達成", "👍 已成功！再報一次數")
        elif kind == "sel":
            w_prev = abs(prev[1] - prev[0])
            w_now = abs(cur[1] - cur[0])
            if ca and sh and w_now != w_prev:
                if w_now == 1 and w_prev == 0:
                    guide("👌 圈到一格！快速雙擊＝一口氣圈整塊")
                elif w_now >= 2 and w_now > w_prev:
                    hit("🖍️ 圈起來了！圈完按 F1＝只修圈住的", "👍 已成功！放開再圈一次")
        elif kind == "del":
            drop = prev[2] - cur[2]
            if ca and drop == 1:
                guide("👌 刪了一字！快速雙擊＝整塊蒸發")
            elif ca and drop >= 2:
                hit("✂️ 刪除家族入手（雙擊＝整塊蒸發）", "👍 已成功！再刪一塊")
        elif kind == "free":
            if ln > 3:
                state["had_text"] = True
            if "f1_ok" in evs and not state["free_fixed"]:
                state["free_fixed"] = True
                state["ok_until"] = now + 3.5
                state["ok_txt"] = "✔ 改好了！接著按 Enter 取消選取"
                _praise("✨ 就是這樣！接著按 Enter")
            elif state["free_fixed"] and flat and ent:
                lesson_pass("🎉 出師了！日常就這套：打字 → F1 → Enter")
            elif state["had_text"] and ln == 0:
                guide("字不見了？反白時要先按 Enter 取消——Ctrl+Z 可救回")
        root.after(80, pump)

    show(0)
    root.after(80, pump)
    root.mainloop()
