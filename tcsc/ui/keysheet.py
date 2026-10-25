# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import ctypes
import tkinter as tk

from .. import settings
from ..keys import keymap

_FONT = "Microsoft JhengHei"
_BG, _FG, _DIM, _OK, _HDR = "#1f1f1f", "#e6e6e6", "#8f8f8f", "#7dd87d", "#8ec7ff"


def _lines():
    eff, problems = keymap.resolve(settings.get)
    out = []
    for grp, keys in keymap.GROUPS:
        out.append(("hdr", f"［{grp}］"))
        if keys and all(k.action.startswith("sym:") for k in keys):
            alive = bool(settings.get("symkeys_on"))
            for n, o, src in keymap.sym_table(settings.get):
                out.append(("ok" if alive else "dim", f"  {'●' if alive else '○'} {'Ctrl+Alt+' + n:<28}打出 {o}"
                                                      + ("（自訂）" if src == "自訂" else "")))
            out.append(("plain", ""))
            continue
        for k in keys:
            alive = (not k.gate) or bool(settings.get(k.gate))
            combo = k.combo
            if k.action in keymap.REBINDABLE:
                bind = eff.get(k.action, (k.vk, k.mods))
                if bind != (k.vk, k.mods):
                    combo = f"{keymap.format_combo(bind)}（改鍵，原 {k.combo}）"
            out.append(("ok" if alive else "dim", f"  {'●' if alive else '○'} {combo:<28}{k.verb}"))
        out.append(("plain", ""))
    if problems:
        out.append(("hdr", "［改鍵設定有問題，已回預設］"))
        out += [("dim", "  " + p) for p in problems]
    out.append(("dim", "○＝管它的開關關著（系統匣可開）；改鍵：系統匣「改鍵…」"))
    return out


def open_keysheet():
    root = tk.Tk()
    root.title("快捷鍵表——現在生效的鍵位")
    root.configure(bg=_BG)
    root.geometry("760x640")
    try:
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        v = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(v), 4)
    except Exception:
        pass
    txt = tk.Text(root, bg=_BG, fg=_FG, font=(_FONT, 11), relief="flat", wrap="none",
                  padx=14, pady=10, insertbackground=_BG)
    sb = tk.Scrollbar(root, command=txt.yview)
    txt.configure(yscrollcommand=sb.set)
    txt.tag_configure("hdr", foreground=_HDR, font=(_FONT, 11, "bold"))
    txt.tag_configure("ok", foreground=_OK)
    txt.tag_configure("dim", foreground=_DIM)
    txt.tag_configure("plain", foreground=_FG)
    for tag, line in _lines():
        txt.insert("end", line + "\n", tag)
    txt.configure(state="disabled")
    sb.pack(side="right", fill="y")
    txt.pack(fill="both", expand=True)
    root.bind("<Escape>", lambda e: root.destroy())
    root.mainloop()
