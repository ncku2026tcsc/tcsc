# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/tcsc2026/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import tkinter as tk

from . import keymap
from .. import settings

_KEYSYM = {"Return": "ENTER", "BackSpace": "BACKSPACE", "Escape": "ESC",
           "space": "SPACE", "Tab": "TAB", "ISO_Left_Tab": "TAB",
           "Left": "LEFT", "Right": "RIGHT", "Up": "UP", "Down": "DOWN",
           "Home": "HOME", "End": "END", "Prior": "PGUP", "Next": "PGDN",
           "Insert": "INS", "Delete": "DEL",
           "grave": "`", "minus": "-", "equal": "=", "bracketleft": "[",
           "bracketright": "]", "backslash": "\\", "semicolon": ";",
           "apostrophe": "'", "comma": ",", "period": ".", "slash": "/"}
_MOD_SYMS = {"Control_L", "Control_R", "Alt_L", "Alt_R", "Shift_L", "Shift_R"}


def _event_combo(ev):
    if ev.keysym in _MOD_SYMS:
        return None
    name = _KEYSYM.get(ev.keysym)
    if name is None:
        s = ev.keysym.upper()
        name = s if s in keymap._NAME2VK else None
    if name is None:
        return "?" + ev.keysym
    mods = ("Ctrl+" if ev.state & 0x0004 else "") \
        + ("Alt+" if ev.state & 0x20000 else "") \
        + ("Shift+" if ev.state & 0x0001 else "")
    return mods + name


def open_binder(apply_fn, notify=None):
    BG, FG, SUB, ACC, SEL = "#1b1b1f", "#e8e8e8", "#9a9a9a", "#ffd479", "#2d4f67"
    fnt, small = ("Microsoft JhengHei", 12), ("Microsoft JhengHei", 10)
    root = tk.Tk()
    root.title("改鍵——點一列，按下新的組合鍵")
    root.configure(bg=BG)
    root.geometry("620x440")
    rows = keymap.rows()
    state = {"arm": None}
    tk.Label(root, text="點選動作 → 直接按下想用的鍵（可含 Ctrl／Alt／Shift）\n"
                        "字母／數字必須帶修飾鍵；F12 不能用；Delete＝清除該鍵覆寫回預設",
             bg=BG, fg=SUB, font=small, justify="left").pack(anchor="w", padx=12, pady=(10, 4))
    lb = tk.Listbox(root, width=64, height=11, font=fnt, bg="#242429", fg=FG,
                    selectbackground=SEL, selectforeground=FG, relief="solid", bd=1,
                    activestyle="none")
    lb.pack(fill="both", expand=True, padx=12, pady=4)
    status = tk.Label(root, text="", bg=BG, fg=ACC, font=small, wraplength=580, justify="left")
    status.pack(anchor="w", padx=12, pady=(2, 8))

    def refresh():
        eff, problems = keymap.resolve(settings.get)
        lb.delete(0, "end")
        for r in rows:
            bind = eff.get(r.id, r.default)
            mark = "＊" if bind != r.default else "　"
            lb.insert("end", f"{mark}{keymap.format_combo(bind).ljust(16)}｜{r.verb[:26]}")
        if problems:
            status.config(text="⚠ " + "；".join(problems))

    def arm(_=None):
        sel = lb.curselection()
        if not sel:
            return
        state["arm"] = sel[0]
        status.config(text=f"請按下「{rows[sel[0]].verb[:20]}」的新組合鍵……（Esc 取消、Delete 回預設）")

    def on_key(ev):
        i = state["arm"]
        if i is None:
            return
        r = rows[i]
        ov = dict(settings.get("key_overrides") or {})
        if ev.keysym == "Escape":
            state["arm"] = None
            status.config(text="已取消")
            return "break"
        if ev.keysym == "Delete":
            ov.pop(r.id, None)
            settings.set("key_overrides", ov)
            state["arm"] = None
            apply_fn()
            refresh()
            status.config(text=f"「{r.verb[:16]}」已還原預設 {r.combo}")
            return "break"
        combo = _event_combo(ev)
        if combo is None:
            return "break"
        if combo.startswith("?") or keymap.parse_combo(combo) is None:
            status.config(text=f"「{combo.lstrip('?')}」不能當熱鍵（白名單外或 F12）——換一顆")
            return "break"
        ov[r.id] = combo
        settings.set("key_overrides", ov)
        state["arm"] = None
        apply_fn()
        refresh()
        _eff, problems = keymap.resolve(settings.get)
        if problems:
            status.config(text="⚠ " + "；".join(problems))
        else:
            status.config(text=f"「{r.verb[:16]}」→ {combo} ✓ 已生效")
            if notify:
                try:
                    notify(f"改鍵：{combo} ＝ {r.verb[:14]}")
                except Exception:
                    pass
        return "break"

    def reset_all():
        settings.set("key_overrides", {})
        state["arm"] = None
        apply_fn()
        refresh()
        status.config(text="全部覆寫已清空＝回出廠鍵位")

    lb.bind("<<ListboxSelect>>", arm)
    root.bind("<KeyPress>", on_key)
    bar = tk.Frame(root, bg=BG)
    bar.pack(fill="x", padx=12, pady=(0, 10))
    tk.Button(bar, text="全部還原預設", command=reset_all, font=small,
              bg="#3a2a2a", fg=FG, relief="flat", padx=10).pack(side="right")
    refresh()
    root.mainloop()
