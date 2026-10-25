# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import tkinter as tk
import tkinter.font as tkfont

from .. import settings
from ..engine import addword

SHOW = 8
MAX_LEVEL = 20
_FONT_FAMILY = "Microsoft JhengHei"


def pick(word, combos, verb, master=None, level=None):
    dark = bool(settings.get("box_dark"))
    BG = "#1f1f1f" if dark else "#f4f4f4"
    FG = "#e6e6e6" if dark else "#111111"
    SUB = "#9a9a9a" if dark else "#777777"
    EBG = "#2b2b2b" if dark else "#ffffff"
    BTN = "#3a3a3a" if dark else "SystemButtonFace"
    SEL = "#264f78" if dark else "#b5d5ff"
    ACC = "#3ecfa0" if dark else "#0a7a55"

    own = master is None
    win = tk.Tk() if own else tk.Toplevel(master)
    win.title("選讀音")
    win.configure(bg=BG)
    if not own:
        win.transient(master)
    try:
        win.attributes("-topmost", True)
    except Exception:
        pass
    fnt = tkfont.Font(root=win, family=_FONT_FAMILY, size=11)
    bold = tkfont.Font(root=win, family=_FONT_FAMILY, size=13, weight="bold")

    tk.Label(win, text=word, font=bold, bg=BG, fg=FG).pack(anchor="w", padx=14, pady=(12, 0))
    tk.Label(win, text=f"這個詞有 {len(combos)} 種讀法，要{verb}哪個？（數字鍵勾選・Enter 收下・Esc 取消）",
             font=fnt, bg=BG, fg=SUB).pack(anchor="w", padx=14, pady=(0, 4))
    known = {tuple(s) for s in _known(word)}
    vars_ = []
    for k, seq in enumerate(combos[:SHOW], 1):
        v = tk.BooleanVar(master=win, value=(k == 1 and seq in known))
        tag = "　（詞庫登記）" if seq in known else ""
        tk.Checkbutton(win, text=f"{k}.  {' '.join(seq)}{tag}", variable=v, font=fnt, bg=BG, fg=FG,
                       selectcolor=EBG, activebackground=BG, activeforeground=FG, anchor="w").pack(fill="x", padx=14)
        vars_.append((v, seq))
    row9 = tk.Frame(win, bg=BG)
    row9.pack(fill="x", padx=14, pady=(4, 0))
    tk.Label(row9, text=f"{SHOW + 1}.  自己打：", font=fnt, bg=BG, fg=FG).pack(side="left")
    ent = tk.Entry(row9, width=24, bg=EBG, fg=FG, insertbackground=FG, font=fnt, relief="flat",
                   highlightthickness=1, highlightbackground=SUB, highlightcolor=ACC)
    ent.pack(side="left", ipady=2)
    msg = tk.Label(win, text="一個字一節、空白分隔，一聲不加符號（例：ㄐㄩˋ ㄨㄟˇ）",
                   font=fnt, bg=BG, fg=SUB, anchor="w", justify="left")
    msg.pack(fill="x", padx=14)
    spin = None
    if level is not None:
        lrow = tk.Frame(win, bg=BG)
        lrow.pack(fill="x", padx=14, pady=(6, 0))
        tk.Label(lrow, text="段數：", font=fnt, bg=BG, fg=FG).pack(side="left")
        lv_var = tk.StringVar(master=win, value=str(level))
        spin = tk.Spinbox(lrow, from_=1, to=MAX_LEVEL, width=4, textvariable=lv_var, font=fnt,
                          bg=EBG, fg=FG, insertbackground=FG, buttonbackground=BTN, relief="flat")
        spin.pack(side="left")
        tk.Label(lrow, text=f"（1～{MAX_LEVEL}，越高越容易被選上；之後在 Shift+F7 也能調）",
                 font=fnt, bg=BG, fg=SUB).pack(side="left", padx=6)

    out = {"seqs": [], "level": None}

    def ok(_e=None):
        if spin is not None:
            try:
                lv = int(spin.get())
            except ValueError:
                lv = 0
            if not 1 <= lv <= MAX_LEVEL:
                msg.configure(text=f"段數要是 1～{MAX_LEVEL} 的整數")
                return
            out["level"] = lv
        chosen = [seq for v, seq in vars_ if v.get()]
        typed = ent.get().strip()
        if typed:
            seq = addword.parse_reading(typed, word)
            if seq is None:
                msg.configure(text=f"讀音要 {len(word)} 節（一個字一節、空白分隔），只能用注音符號和聲調")
                return
            if seq not in chosen:
                chosen.append(seq)
        if not chosen:
            msg.configure(text="還沒勾任何一組（或在第 9 格自己打）")
            return
        out["seqs"] = chosen
        win.destroy()

    def key(e):
        if win.focus_get() in (ent, spin):
            return None
        if e.char.isdigit() and 1 <= int(e.char) <= len(vars_):
            v = vars_[int(e.char) - 1][0]
            v.set(not v.get())
            return "break"
        if e.char == str(SHOW + 1):
            ent.focus_set()
            return "break"
        return None

    btns = tk.Frame(win, bg=BG)
    btns.pack(fill="x", padx=14, pady=10)
    tk.Button(btns, text="收下", command=ok, bg=BTN, fg=FG, font=fnt, activebackground=SEL,
              relief="flat", padx=12).pack(side="left")
    tk.Button(btns, text="取消", command=win.destroy, bg=BTN, fg=FG, font=fnt, activebackground=SEL,
              relief="flat", padx=12).pack(side="right")
    win.bind("<Key>", key)
    win.bind("<Return>", ok)
    win.bind("<Escape>", lambda e: win.destroy())
    win.update_idletasks()
    if not own:
        win.geometry("+%d+%d" % (master.winfo_rootx() + 60, master.winfo_rooty() + 90))
    win.lift()
    win.focus_force()
    if own:
        win.after(60, lambda: _to_front(win))
        win.mainloop()
    else:
        win.grab_set()
        master.wait_window(win)
    return out["seqs"], (out["level"] if out["seqs"] else None)


def _known(word):
    from ..engine import wordphon
    try:
        return wordphon.seqs_of(word)
    except Exception:
        return []


def _to_front(win):
    try:
        import ctypes
        u = ctypes.windll.user32
        hw = u.GetParent(win.winfo_id()) or win.winfo_id()
        fg = u.GetForegroundWindow()
        me = ctypes.windll.kernel32.GetCurrentThreadId()
        other = u.GetWindowThreadProcessId(fg, None)
        att = bool(u.AttachThreadInput(me, other, True)) if other != me else False
        try:
            u.SetForegroundWindow(hw)
            u.BringWindowToTop(hw)
        finally:
            if att:
                u.AttachThreadInput(me, other, False)
    except Exception:
        pass
