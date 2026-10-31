# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/tcsc2026/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import os
import subprocess
import sys

from .. import settings
from . import autostart

APP = "算字大師"

_PS = (
    "$w = New-Object -ComObject WScript.Shell; "
    "foreach ($d in $env:TCSC_LNK_DIRS.Split('|')) { "
    "if (-not $d) { continue }; "
    "$dir = $(if ($d -match ':') { $d } else { [Environment]::GetFolderPath($d) }); "
    "$s = $w.CreateShortcut((Join-Path $dir ($env:TCSC_LNK_NAME + '.lnk'))); "
    "$s.TargetPath = $env:TCSC_LNK_TARGET; "
    "$s.Arguments = $env:TCSC_LNK_ARGS; "
    "$s.WorkingDirectory = (Split-Path $env:TCSC_LNK_TARGET); "
    "$s.IconLocation = $env:TCSC_LNK_ICON; "
    "$s.Save() }"
)


def _target():
    if getattr(sys, "frozen", False):
        return sys.executable, ""
    exe = sys.executable
    if os.path.basename(exe).lower() == "python.exe":
        pw = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.exists(pw):
            exe = pw
    return exe, f'"{os.path.abspath(sys.argv[0])}"'


def make_shortcuts(desktop=True, startmenu=True, dirs=None):
    dirs = dirs or [d for d, on in (("Desktop", desktop), ("Programs", startmenu)) if on]
    if not dirs:
        return True
    target, args = _target()
    env = dict(os.environ, TCSC_LNK_DIRS="|".join(dirs), TCSC_LNK_NAME=APP, TCSC_LNK_TARGET=target,
               TCSC_LNK_ARGS=args, TCSC_LNK_ICON=f"{target},0")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", _PS],
                           env=env, capture_output=True, timeout=20, creationflags=0x08000000)
        return r.returncode == 0
    except Exception:
        return False


def ask(notify=None):
    import tkinter as tk

    def say(msg):
        if notify:
            try:
                notify(msg)
            except Exception:
                pass

    dark = bool(settings.get("box_dark", True))
    BG, FG, DIM = ("#1f1f1f", "#e6e6e6", "#9a9a9a") if dark else ("#f4f4f4", "#111111", "#666666")
    BTN, SEL, ACC = ("#3a3a3a", "#264f78", "#3fb950") if dark else ("#e3e3e3", "#b5d5ff", "#3fb950")
    root = tk.Tk()
    root.title(APP)
    root.configure(bg=BG)
    root.resizable(False, False)
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass
    f_head = ("Microsoft JhengHei UI", 13, "bold")
    f_body = ("Microsoft JhengHei UI", 11)
    tk.Label(root, text="要不要順手設定好？", font=f_head, bg=BG, fg=FG).pack(anchor="w", padx=18, pady=(16, 2))
    tk.Label(root, text="之後都可以在右下角圖示的選單改。", font=f_body, bg=BG, fg=DIM).pack(anchor="w", padx=18, pady=(0, 8))
    picked = [True, True, True]
    texts = ("開機自動啟動：開機後右下角就有，不用每次自己開", "桌面捷徑", "開始功能表：可以從開始搜尋「算字大師」打開")
    for k, text in enumerate(texts):
        cb = tk.Checkbutton(root, text=text, command=lambda k=k: picked.__setitem__(k, not picked[k]), font=f_body,
                            bg=BG, fg=FG, selectcolor=BTN, activebackground=BG, activeforeground=FG, anchor="w")
        cb.select()
        cb.pack(anchor="w", padx=(14, 24), pady=2)

    def ok():
        auto, desk, start = picked
        done = []
        if auto:
            if autostart.enable():
                done.append("開機自動啟動")
        elif autostart.is_enabled():
            autostart.disable()
        if (desk or start) and make_shortcuts(desk, start):
            done += [n for n, on in (("桌面捷徑", desk), ("開始功能表", start)) if on]
        settings.set("firstrun_done", True)
        say(("設定好了：" + "、".join(done)) if done else "沒有改任何設定")
        root.destroy()

    def later():
        settings.set("firstrun_done", True)
        say("之後想設定：右下角圖示按右鍵 → 開機自動啟動、建立捷徑")
        root.destroy()

    row = tk.Frame(root, bg=BG)
    row.pack(fill="x", padx=18, pady=(12, 16))
    tk.Button(row, text="好", width=8, command=ok, bg=ACC, fg="#0b2812", relief="flat", activebackground="#4cc960",
              font=("Microsoft JhengHei UI", 11, "bold")).pack(side="right")
    tk.Button(row, text="先不要", command=later, bg=BTN, fg=FG, relief="flat", activebackground=SEL,
              font=f_body).pack(side="right", padx=8)
    root.protocol("WM_DELETE_WINDOW", later)
    root.update_idletasks()
    w, h = root.winfo_reqwidth(), root.winfo_reqheight()
    root.geometry(f"+{(root.winfo_screenwidth() - w) // 2}+{(root.winfo_screenheight() - h) // 3}")
    root.mainloop()
