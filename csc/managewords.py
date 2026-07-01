# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""自學詞管理視窗（Tk）：列出所有學過的詞 + 總數，可調等級（1~6，−/＋）、刪除、新增、搜尋。

在『獨立執行緒』跑（呼叫端負責開 thread、視窗關閉後 gc.collect）——沿用 F6 框那套
『Tk 跑在非主緒、關閉後在該緒回收 Tcl 物件』避免跨緒 GC 隨機閃退（見 history 階段 47）。
資料層全走 csc.userdict（entries_by_word / set_level / learn / remove），改完都 reload_userforce。
"""
import tkinter as tk
from tkinter import font as tkfont

from . import userdict, wordphon

_FONT_FAMILY = "Microsoft JhengHei"   # 繁中字型（Win 內建）


def open_manage_window(notify=None):
    """開啟管理視窗並 mainloop（阻塞至關閉）。notify：可選的系統匣通知函式。"""
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
    fnt = tkfont.Font(family=_FONT_FAMILY, size=11)
    bold = tkfont.Font(family=_FONT_FAMILY, size=11, weight="bold")

    # ---- 搜尋列 ----
    top = tk.Frame(root, padx=10, pady=6)
    top.pack(fill="x")
    tk.Label(top, text="搜尋：", font=fnt).pack(side="left")
    search_var = tk.StringVar()
    tk.Entry(top, textvariable=search_var, font=fnt).pack(side="left", fill="x", expand=True)

    # ---- 可捲動清單（Canvas + 內層 Frame）----
    mid = tk.Frame(root)
    mid.pack(fill="both", expand=True, padx=10)
    canvas = tk.Canvas(mid, highlightthickness=0)
    sb = tk.Scrollbar(mid, orient="vertical", command=canvas.yview)
    inner = tk.Frame(canvas)
    win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=sb.set)
    canvas.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win_id, width=e.width))
    canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))

    # ---- 匯入 / 匯出（同詞取較高等級）----
    io = tk.Frame(root, padx=10, pady=4)
    io.pack(fill="x")

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
            added, raised, same = userdict.import_words(path)
            wordphon.reload_userforce()
            _say(f"匯入完成：新增 {added}、提升 {raised}、不變 {same}")
            refresh()
        except Exception as e:
            messagebox.showerror("匯入失敗", str(e), parent=root)

    tk.Label(io, text="詞庫檔案：", font=fnt).pack(side="left")
    tk.Button(io, text="匯出…", font=fnt, command=do_export).pack(side="left", padx=4)
    tk.Button(io, text="匯入…（同詞取較高等級）", font=fnt,
              command=do_import).pack(side="left", padx=4)

    # ---- 底部：新增 + 關閉 ----
    bottom = tk.Frame(root, padx=10, pady=8)
    bottom.pack(fill="x")
    tk.Label(bottom, text="新增詞彙：", font=fnt).pack(side="left")
    add_var = tk.StringVar()
    add_entry = tk.Entry(bottom, textvariable=add_var, font=fnt, width=14)
    add_entry.pack(side="left")

    def do_add(event=None):
        w = add_var.get().strip()
        if not w:
            return
        st, lv, msg = userdict.learn(w)
        wordphon.reload_userforce()
        add_var.set("")
        _say(f"「{w}」{msg}" if st == "nochar" else f"已新增/加強「{w}」：等級 {lv}")
        refresh()

    def do_clear():
        from tkinter import messagebox
        n = len(userdict.entries_by_word())
        if n and messagebox.askyesno("全部清除", f"確定清除全部 {n} 個自學詞？此動作無法復原。", parent=root):
            userdict.clear()
            wordphon.reload_userforce()
            _say("已清除全部自學詞")
            refresh()

    tk.Button(bottom, text="新增", font=fnt, command=do_add).pack(side="left", padx=4)
    tk.Button(bottom, text="關閉", font=fnt, command=root.destroy).pack(side="right")
    tk.Button(bottom, text="全部清除", font=fnt, fg="#c0392b",
              command=do_clear).pack(side="right", padx=4)
    add_entry.bind("<Return>", do_add)

    # ---- 資料操作 ----
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
        shown = 0
        for word, lv in learned.items():
            if flt and flt not in word:
                continue
            shown += 1
            row = tk.Frame(inner, pady=1)
            row.pack(fill="x")
            tk.Label(row, text=word, font=fnt, width=18, anchor="w").pack(side="left")
            tk.Button(row, text="－", font=fnt, width=2, takefocus=0,
                      command=lambda w=word: change(w, -1)).pack(side="left")
            tk.Label(row, text=str(lv), font=bold, width=2).pack(side="left")
            tk.Button(row, text="＋", font=fnt, width=2, takefocus=0,
                      command=lambda w=word: change(w, +1)).pack(side="left")
            tk.Button(row, text="刪除", font=fnt, takefocus=0,
                      command=lambda w=word: remove(w)).pack(side="left", padx=6)
        if shown == 0:
            tk.Label(inner, font=fnt, fg="#888",
                     text="（沒有符合的詞）" if flt else "（還沒學任何詞：反白詞→F7 學）").pack(pady=20)
        inner.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

    search_var.trace_add("write", lambda *a: refresh())

    # 置中、給個合理大小
    w, h = 470, 480
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 3
    root.geometry(f"{w}x{h}+{x}+{y}")

    refresh()
    add_entry.focus_set()
    root.mainloop()
