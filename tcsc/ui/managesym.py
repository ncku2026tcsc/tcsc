# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/tcsc2026/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import ctypes
import tkinter as tk

from .. import settings
from ..keys import keymap

_FONT = "Microsoft JhengHei"
_BG, _FG, _DIM, _ACC, _BTN = "#1f1f1f", "#e6e6e6", "#8f8f8f", "#8ec7ff", "#333333"
MAX_LEN = 20


def _rows():
    live = keymap.sym_table(settings.get)
    on = {n for n, _o, _s in live}
    off = [(n, o, "已關") for n, o in keymap.SYM_SPEC if n not in on]
    return live + off


def open_manager(rebind, notify=lambda m: None):
    root = tk.Tk()
    root.title("符號鍵——Ctrl+Alt+鍵 打出什麼字")
    root.configure(bg=_BG)
    root.geometry("560x560")
    try:
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        v = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(v), 4)
    except Exception:
        pass

    tk.Label(root, text="選一列可刪除或恢復；下面輸入鍵與字可新增（同一顆鍵＝蓋過）。",
             bg=_BG, fg=_DIM, font=(_FONT, 10)).pack(anchor="w", padx=12, pady=(10, 4))
    lb = tk.Listbox(root, bg=_BG, fg=_FG, font=(_FONT, 12), selectbackground="#3a5a80",
                    activestyle="none", relief="flat", highlightthickness=0)
    lb.pack(fill="both", expand=True, padx=12)
    shown = []

    def refresh():
        shown.clear()
        lb.delete(0, "end")
        for n, o, st in _rows():
            shown.append((n, o, st))
            lb.insert("end", f"  Ctrl+Alt+{n:<3}  →  {o}　　（{st}）")
            if st == "已關":
                lb.itemconfig("end", fg=_DIM)

    form = tk.Frame(root, bg=_BG)
    form.pack(fill="x", padx=12, pady=8)
    tk.Label(form, text="Ctrl+Alt+", bg=_BG, fg=_FG, font=(_FONT, 11)).pack(side="left")
    key_e = tk.Entry(form, width=4, font=(_FONT, 12), bg=_BTN, fg=_FG, insertbackground=_FG, relief="flat")
    key_e.pack(side="left")
    tk.Label(form, text="  打出", bg=_BG, fg=_FG, font=(_FONT, 11)).pack(side="left")
    out_e = tk.Entry(form, width=18, font=(_FONT, 12), bg=_BTN, fg=_FG, insertbackground=_FG, relief="flat")
    out_e.pack(side="left", padx=(4, 0))
    msg = tk.Label(root, text="", bg=_BG, fg=_ACC, font=(_FONT, 10))
    msg.pack(anchor="w", padx=12)

    def say(t):
        msg.configure(text=t)
        notify(t)

    def apply(user, off, text):
        settings.set("sym_user", user)
        settings.set("sym_off", sorted(off))
        try:
            rebind()
        except Exception:
            pass
        refresh()
        say(text)

    def add(_e=None):
        n = key_e.get().strip().upper()
        o = out_e.get()
        if n not in keymap.SYM_NAMES:
            say("鍵要是一個字母、數字或標點鍵（例：P、7、=）；方向鍵與 Backspace 是快速移動用的，不開放")
            return
        if not o or "\n" in o or len(o) > MAX_LEN:
            say(f"要打出的字不能空白、不能換行，最多 {MAX_LEN} 個字")
            return
        user = dict(settings.get("sym_user") or {})
        off = set(settings.get("sym_off") or [])
        builtin = dict(keymap.SYM_SPEC).get(n)
        if builtin == o:
            user.pop(n, None)
            off.discard(n)
        else:
            user[n] = o
        apply(user, off, f"已設定：Ctrl+Alt+{n} → {o}")
        key_e.delete(0, "end")
        out_e.delete(0, "end")

    def selected():
        sel = lb.curselection()
        return shown[sel[0]] if sel else None

    def remove():
        r = selected()
        if not r:
            say("先在上面選一列")
            return
        n, o, st = r
        user = dict(settings.get("sym_user") or {})
        off = set(settings.get("sym_off") or [])
        if st == "自訂":
            user.pop(n, None)
            text = f"已刪除自訂：Ctrl+Alt+{n}" + ("（內建的會回來）" if n in dict(keymap.SYM_SPEC) and n not in off else "")
        elif st == "內建":
            off.add(n)
            text = f"已關掉內建：Ctrl+Alt+{n}（{o}）；選它按「恢復」可再開"
        else:
            say("這列已經關了；要開請按「恢復」")
            return
        apply(user, off, text)

    def restore():
        r = selected()
        if not r or r[2] != "已關":
            say("選一列「已關」的內建符號再按恢復")
            return
        off = set(settings.get("sym_off") or [])
        off.discard(r[0])
        apply(dict(settings.get("sym_user") or {}), off, f"已恢復：Ctrl+Alt+{r[0]} → {r[1]}")

    def reset_all():
        apply({}, set(), "已全部還原成內建符號鍵")

    def pick(_e=None):
        r = selected()
        if r:
            key_e.delete(0, "end")
            key_e.insert(0, r[0])
            out_e.delete(0, "end")
            out_e.insert(0, r[1])

    bar = tk.Frame(root, bg=_BG)
    bar.pack(fill="x", padx=12, pady=(4, 12))
    for text, cmd in (("新增／更新", add), ("刪除選取", remove), ("恢復選取", restore), ("全部還原內建", reset_all)):
        tk.Button(bar, text=text, command=cmd, bg=_BTN, fg=_FG, activebackground="#444", activeforeground=_FG,
                  relief="flat", font=(_FONT, 10), padx=10).pack(side="left", padx=(0, 8))
    lb.bind("<<ListboxSelect>>", pick)
    out_e.bind("<Return>", add)
    root.bind("<Escape>", lambda e: root.destroy())
    if not settings.get("symkeys_on"):
        say("提醒：符號鍵總開關目前是關的（系統匣「符號鍵」），這裡設好也要開了才生效")
    refresh()
    root.mainloop()
