# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import queue
import tkinter as tk
from tkinter import font as tkfont

from .. import settings
from ..engine import userdict, wordphon

_FONT_FAMILY = "Microsoft JhengHei"

ACTIVE = None


def open_manage_window(notify=None, correct_fn=None, initial=None):
    def _say(msg):
        if notify:
            try:
                notify(msg)
            except Exception:
                pass

    root = tk.Tk()
    root.title("管理我學的詞")
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass
    fnt = tkfont.Font(root=root, family=_FONT_FAMILY, size=11)
    bold = tkfont.Font(root=root, family=_FONT_FAMILY, size=11, weight="bold")

    dark = bool(settings.get("box_dark"))
    BG = "#1f1f1f" if dark else "#f4f4f4"
    FG = "#e6e6e6" if dark else "#111111"
    SUB = "#9a9a9a" if dark else "#888888"
    EBG = "#2b2b2b" if dark else "#ffffff"
    BTN = "#3a3a3a" if dark else "SystemButtonFace"
    SEL = "#264f78" if dark else "#b5d5ff"
    DANGER = "#f85149" if dark else "#c0392b"
    root.configure(bg=BG)

    def _btn(*a, **kw):
        kw.setdefault("bg", BTN)
        kw.setdefault("fg", FG)
        kw.setdefault("activebackground", SEL)
        kw.setdefault("activeforeground", FG)
        return tk.Button(*a, **kw)

    try:
        import ctypes as _ct
        root.update_idletasks()
        _hw = _ct.windll.user32.GetParent(root.winfo_id())
        _v = _ct.c_int(1 if dark else 0)
        for _attr in (20, 19):
            if _ct.windll.dwmapi.DwmSetWindowAttribute(_hw, _attr, _ct.byref(_v), _ct.sizeof(_v)) == 0:
                break
    except Exception:
        pass

    top = tk.Frame(root, padx=10, pady=6, bg=BG)
    top.pack(fill="x")
    tk.Label(top, text="搜尋：", font=fnt, bg=BG, fg=FG).pack(side="left")
    sort_state = {"desc": True}

    def toggle_sort():
        sort_state["desc"] = not sort_state["desc"]
        sort_btn.config(text="最新在上 ⬇" if sort_state["desc"] else "最舊在上 ⬆")
        refresh()
    sort_btn = _btn(top, text="最新在上 ⬇", font=fnt, takefocus=0, command=toggle_sort)
    sort_btn.pack(side="right", padx=(6, 0))
    search_var = tk.StringVar(master=root)
    search_entry = tk.Entry(top, textvariable=search_var, font=fnt,
                            bg=EBG, fg=FG, insertbackground=FG)
    search_entry.pack(side="left", fill="x", expand=True)

    mid = tk.Frame(root, bg=BG)
    canvas = tk.Canvas(mid, highlightthickness=0, bg=BG)
    from tkinter import ttk as _ttk
    _style = _ttk.Style(root)
    _style.theme_use("clam")
    _style.configure("MW.Vertical.TScrollbar",
                     background=("#4a4a4a" if dark else "#c8c8c8"),
                     troughcolor=BG, bordercolor=BG, arrowcolor=SUB, relief="flat")
    _style.map("MW.Vertical.TScrollbar", background=[("active", SEL)])
    sb = _ttk.Scrollbar(mid, orient="vertical", command=canvas.yview,
                        style="MW.Vertical.TScrollbar")
    inner = tk.Frame(canvas, bg=BG)
    win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=sb.set)
    canvas.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win_id, width=e.width))
    canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))

    io = tk.Frame(root, padx=10, pady=4, bg=BG)

    def do_export():
        from tkinter import filedialog, messagebox
        if not userdict.entries_by_word():
            _say("沒有可匯出的自學詞")
            return
        path = filedialog.asksaveasfilename(
            parent=root, title="匯出自學詞", defaultextension=".txt",
            initialfile="tcsc_自學詞.txt",
            filetypes=[("文字檔", "*.txt"), ("所有檔案", "*.*")])
        if not path:
            return
        try:
            cnt = userdict.export_words(path)
            _say(f"已匯出 {cnt} 個自學詞")
        except Exception as e:
            messagebox.showerror("匯出失敗", str(e), parent=root)

    def do_import():
        from tkinter import filedialog, messagebox
        path = filedialog.askopenfilename(
            parent=root, title="匯入自學詞（同詞取較高等級）",
            filetypes=[("文字檔", "*.txt"), ("所有檔案", "*.*")])
        if not path:
            return
        try:
            added, raised, same, missing = userdict.import_words(path)
            wordphon.reload_userforce()
            _say(f"匯入完成：新增 {added}、提升 {raised}、不變 {same}"
                 + (f"；{missing} 個沒帶讀音、又不只一種讀法，沒匯入（用 F7 學會問讀音）" if missing else ""))
            refresh()
        except Exception as e:
            messagebox.showerror("匯入失敗", str(e), parent=root)

    tk.Label(io, text="詞庫檔案：", font=fnt, bg=BG, fg=FG).pack(side="left")
    _btn(io, text="匯出…", font=fnt, command=do_export).pack(side="left", padx=4)
    _btn(io, text="匯入…（同詞取較高等級）", font=fnt,
         command=do_import).pack(side="left", padx=4)

    bottom = tk.Frame(root, padx=10, pady=8, bg=BG)
    tk.Label(bottom, text="新增詞彙：", font=fnt, bg=BG, fg=FG).pack(side="left")
    add_var = tk.StringVar(master=root)
    add_entry = tk.Entry(bottom, textvariable=add_var, font=fnt, width=14,
                         bg=EBG, fg=FG, insertbackground=FG)
    add_entry.pack(side="left")

    def do_add(event=None):
        w = add_var.get().strip()
        if not w:
            return
        seqs = level = None
        if not userdict.seqs_of(w):
            from ..engine import addword
            from . import pickreading
            combos = addword.reading_combos(w)
            if not combos:
                _say(f"「{w}」含沒有注音的字（英數／emoji），學不了")
                return
            if len(combos) == 1:
                seqs = combos
            else:
                seqs, level = pickreading.pick(w, combos, "學", master=root, level=1)
            if not seqs:
                return
        st, lv, msg = userdict.learn(w, seqs, level)
        wordphon.reload_userforce()
        add_var.set("")
        _say(f"已新增/加強「{w}」：等級 {lv}" if st == "ok" else msg)
        refresh()

    def do_clear():
        from tkinter import messagebox
        n = len(userdict.entries_by_word())
        if n and messagebox.askyesno("全部清除", f"確定清除全部 {n} 個自學詞？此動作無法復原。", parent=root):
            userdict.clear()
            wordphon.reload_userforce()
            _say("已清除全部自學詞")
            refresh()

    _btn(bottom, text="新增", font=fnt, command=do_add).pack(side="left", padx=4)
    _btn(bottom, text="關閉", font=fnt, command=root.destroy).pack(side="right")
    _btn(bottom, text="全部清除", font=fnt, fg=DANGER,
         command=do_clear).pack(side="right", padx=4)
    add_entry.bind("<Return>", do_add)

    bottom.pack(side="bottom", fill="x")
    io.pack(side="bottom", fill="x")
    mid.pack(fill="both", expand=True, padx=10)

    def change(word, d):
        cur = userdict.entries_by_word().get(word, 0)
        userdict.set_level(word, cur + d)
        wordphon.reload_userforce()
        refresh()

    def remove(word):
        userdict.remove(word)
        wordphon.reload_userforce()
        _say(f"已移除「{word}」")
        refresh()

    def refresh():
        for c in inner.winfo_children():
            c.destroy()
        learned = userdict.entries_by_word()
        root.title(f"管理我學的詞（共 {len(learned)} 個）")
        flt = search_var.get().strip()
        items = list(learned.items())
        if sort_state["desc"]:
            items = items[::-1]
        shown = 0
        for word, lv in items:
            if flt and flt not in word:
                continue
            shown += 1
            row = tk.Frame(inner, pady=1, bg=BG)
            row.pack(fill="x")
            tk.Label(row, text=word, font=fnt, width=18, anchor="w",
                     bg=BG, fg=FG).pack(side="left")
            _btn(row, text="－", font=fnt, width=2, takefocus=0,
                 command=lambda w=word: change(w, -1)).pack(side="left")
            tk.Label(row, text=str(lv), font=bold, width=2, bg=BG, fg=FG).pack(side="left")
            _btn(row, text="＋", font=fnt, width=2, takefocus=0,
                 command=lambda w=word: change(w, +1)).pack(side="left")
            _btn(row, text="刪除", font=fnt, takefocus=0,
                 command=lambda w=word: remove(w)).pack(side="left", padx=6)
        if shown == 0:
            if flt and flt == add_var.get().strip():
                msg = f"還沒學過「{flt}」\n按下面的「新增」或 Enter 學起來"
            else:
                msg = "（沒有符合的詞）" if flt else "（還沒學任何詞：反白詞→F7 學）"
            tk.Label(inner, font=fnt, fg=SUB, bg=BG, text=msg).pack(pady=20)
        inner.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

    search_var.trace_add("write", lambda *a: refresh())

    cmdq = queue.Queue()
    f1cyc = {}

    def entry_correct(entry, var, step=1):
        if correct_fn is None:
            return
        s = var.get().strip()
        if not s:
            return
        c = f1cyc.get(id(entry))
        if c and s == c["list"][c["idx"]]:
            c["idx"] = (c["idx"] + step) % len(c["list"])
            var.set(c["list"][c["idx"]])
            entry.icursor("end")
            return
        try:
            ranked = list(correct_fn(s))
        except Exception:
            ranked = [s]
        if not ranked:
            ranked = [s]
        if s not in ranked:
            ranked.append(s)
        f1cyc[id(entry)] = {"list": ranked, "idx": 0}
        var.set(ranked[0])
        entry.icursor("end")

    def poll_cmd():
        try:
            while True:
                cmd = cmdq.get_nowait()
                if cmd in ("f1", "f2"):
                    step = 1 if cmd == "f1" else -1
                    w = root.focus_get()
                    if w is add_entry:
                        entry_correct(add_entry, add_var, step)
                    else:
                        entry_correct(search_entry, search_var, step)
        except queue.Empty:
            pass
        root.after(80, poll_cmd)

    w, h = 470, 480
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 3
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.minsize(470, 300)

    if initial:
        if len(initial) <= 8:
            add_var.set(initial)
        search_var.set(initial)
    else:
        refresh()
    add_entry.focus_set()
    add_entry.icursor("end")
    global ACTIVE
    try:
        import ctypes
        _hwnd = ctypes.windll.user32.GetAncestor(root.winfo_id(), 2)
    except Exception:
        _hwnd = 0
    ACTIVE = {"q": cmdq, "hwnd": int(_hwnd or 0)}
    poll_cmd()
    try:
        root.mainloop()
    finally:
        ACTIVE = None
