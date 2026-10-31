# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/tcsc2026/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import queue
import tkinter as tk
from tkinter import font as tkfont

from .. import settings
from ..engine import escort

_FONT_FAMILY = "Microsoft JhengHei"

ACTIVE = None


def open_manage_window(notify=None, correct_fn=None):
    def _say(msg):
        if notify:
            try:
                notify(msg)
            except Exception:
                pass

    root = tk.Tk()
    root.title("常錯字清單")
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
    show_builtin = tk.BooleanVar(master=root, value=bool(settings.get("escort_show_builtin")))

    def toggle_builtin():
        settings.set("escort_show_builtin", bool(show_builtin.get()))
        refresh()
    tk.Checkbutton(top, text=f"顯示出廠票（{len(escort.shipped_chars())}）", variable=show_builtin,
                   command=toggle_builtin, font=fnt, bg=BG, fg=FG, selectcolor=EBG,
                   activebackground=BG, activeforeground=FG, takefocus=0).pack(side="right", padx=(6, 0))
    search_var = tk.StringVar(master=root)
    search_entry = tk.Entry(top, textvariable=search_var, font=fnt,
                            bg=EBG, fg=FG, insertbackground=FG)
    search_entry.pack(side="left", fill="x", expand=True)

    mid = tk.Frame(root, bg=BG)
    from tkinter import ttk as _ttk
    _style = _ttk.Style(root)
    _style.theme_use("clam")
    _style.configure("ME.Vertical.TScrollbar",
                     background=("#4a4a4a" if dark else "#c8c8c8"),
                     troughcolor=BG, bordercolor=BG, arrowcolor=SUB, relief="flat")
    _style.map("ME.Vertical.TScrollbar", background=[("active", SEL)])
    _style.configure("ME.Treeview", background=EBG, fieldbackground=EBG,
                     foreground=FG, rowheight=26, borderwidth=0,
                     font=(_FONT_FAMILY, 11))
    _style.configure("ME.Treeview.Heading", background=BTN, foreground=FG,
                     font=(_FONT_FAMILY, 10, "bold"), relief="flat")
    _style.map("ME.Treeview", background=[("selected", SEL)])
    tree = _ttk.Treeview(mid, columns=("kind", "disp", "src"), show="headings",
                         style="ME.Treeview", selectmode="extended")
    tree.heading("kind", text="類")
    tree.heading("disp", text="內容")
    tree.heading("src", text="來源")
    tree.column("kind", width=44, anchor="c", stretch=False)
    tree.column("disp", width=150, anchor="w")
    tree.column("src", width=240, anchor="w")
    tree.tag_configure("詞", foreground="#7fb4e8")
    tree.tag_configure("對", foreground="#d9b64a")
    tree.tag_configure("字", foreground="#8fc47e")
    tree.tag_configure("廠", foreground=SUB)
    sb = _ttk.Scrollbar(mid, orient="vertical", command=tree.yview,
                        style="ME.Vertical.TScrollbar")
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    tree_rows = {}

    io = tk.Frame(root, padx=10, pady=4, bg=BG)

    def do_export():
        from tkinter import filedialog, messagebox
        if not escort.entries():
            _say("沒有可匯出的保送項")
            return
        path = filedialog.asksaveasfilename(
            parent=root, title="匯出常錯字清單", defaultextension=".txt",
            initialfile="tcsc_常錯字清單.txt",
            filetypes=[("文字檔", "*.txt"), ("所有檔案", "*.*")])
        if not path:
            return
        try:
            cnt = escort.export_all(path)
            _say(f"已匯出 {cnt} 個保送項")
        except Exception as e:
            messagebox.showerror("匯出失敗", str(e), parent=root)

    def do_import():
        from tkinter import filedialog, messagebox
        path = filedialog.askopenfilename(
            parent=root, title="匯入常錯字清單（每行一項；A→B=字對、1字=字票、2~4字=詞票）",
            filetypes=[("文字檔", "*.txt"), ("所有檔案", "*.*")])
        if not path:
            return
        try:
            added, skipped, bad = escort.import_all(path)
            _say(f"匯入完成：新增 {added}、重複略過 {skipped}、格式不符 {bad}")
            refresh()
        except Exception as e:
            messagebox.showerror("匯入失敗", str(e), parent=root)

    tk.Label(io, text="清單檔案：", font=fnt, bg=BG, fg=FG).pack(side="left")
    _btn(io, text="匯出…", font=fnt, command=do_export).pack(side="left", padx=4)
    _btn(io, text="匯入…（自動分類）", font=fnt,
         command=do_import).pack(side="left", padx=4)
    _btn(io, text="刪除選取（Del）", font=fnt, fg=DANGER,
         command=lambda: remove_selected()).pack(side="left", padx=12)

    def prune_covered():
        from tkinter import messagebox
        victims = [(k, key, disp) for k, disp, key, _s in escort.entries()
                   if k in ("字", "對") and escort.covered(k, key)]
        if not victims:
            _say("沒有被出廠票涵蓋的個人票")
            return
        if not messagebox.askyesno(
                "刪掉出廠已含的個人票",
                f"共 {len(victims)} 張個人票的字已在出廠保送裡。\n\n"
                "刪掉之後那些字仍會被保送（出廠票永遠在），只是少了個人票的優先權。\n"
                "詞票與 的／地／得 的字對不會動。要刪嗎？", parent=root):
            return
        n = 0
        for k, key, _d in victims:
            n += (escort.remove_char(key) if k == "字" else escort.remove_pair(*key)) or 0
        _say(f"已刪 {n} 張出廠已含的個人票")
        refresh()
    _btn(io, text="刪掉出廠已含的個人票…", font=fnt,
         command=prune_covered).pack(side="left", padx=4)

    bottom = tk.Frame(root, padx=10, pady=8, bg=BG)
    tk.Label(bottom, text="新增（詞／字／案→按）：", font=fnt, bg=BG, fg=FG).pack(side="left")
    add_var = tk.StringVar(master=root)
    add_entry = tk.Entry(bottom, textvariable=add_var, font=fnt, width=12,
                         bg=EBG, fg=FG, insertbackground=FG)
    add_entry.pack(side="left")

    def do_add(event=None):
        s = add_var.get().strip()
        if not s:
            return
        if "→" in s or ">" in s:
            ab = s.replace(">", "→").split("→")
            ok, msg = escort.add_pair(ab[0], ab[-1]) if len(ab) >= 2 else (False, "字對格式：案→按")
        elif len(s) == 1:
            ok, msg = escort.add_char(s)
        else:
            ok, msg = escort.add_word(s)
        add_var.set("")
        _say(msg)
        refresh()

    def do_clear():
        from tkinter import messagebox
        n = sum(escort.counts())
        if n and messagebox.askyesno("全部清除",
                                     f"確定清除全部 {n} 個保送項？此動作無法復原。", parent=root):
            escort.clear_all()
            _say("已清除全部保送項")
            refresh()

    _btn(bottom, text="新增", font=fnt, command=do_add).pack(side="left", padx=4)
    _btn(bottom, text="關閉", font=fnt, command=root.destroy).pack(side="right")
    _btn(bottom, text="全部清除", font=fnt, fg=DANGER,
         command=do_clear).pack(side="right", padx=4)
    add_entry.bind("<Return>", do_add)

    bottom.pack(side="bottom", fill="x")
    io.pack(side="bottom", fill="x")
    mid.pack(fill="both", expand=True, padx=10)

    def remove_selected(event=None):
        sels = tree.selection()
        if not sels:
            _say("先點選清單裡要刪的項（可 Ctrl/Shift 多選），再按 Del 或刪除鈕")
            return
        n = 0
        for iid in sels:
            kind, key, _disp = tree_rows.get(iid, (None, None, None))
            if kind == "廠":
                _say("出廠票不能在這裡刪——要整包關請走「詞庫→管理詞庫」")
                continue
            if kind == "詞":
                escort.remove_word(key)
            elif kind == "字":
                escort.remove_char(key)
            elif kind == "對":
                escort.remove_pair(*key)
            else:
                continue
            n += 1
        _say(f"已移除 {n} 項")
        refresh()
    tree.bind("<Delete>", remove_selected)

    small = tkfont.Font(root=root, family=_FONT_FAMILY, size=9)

    def _case_map():
        m = {}
        try:
            from .. import logbook
            for r in logbook.records(logbook.ERROR_FILE):
                if r.get("ts"):
                    m[r["ts"]] = r
        except Exception:
            pass
        return m

    def _src_label(src, cases):
        if not src:
            return ""
        if src.startswith("F9收割@"):
            ts = src.split("@", 1)[1]
            rec = cases.get(ts) or {}
            who = {"auto": "自收", "manual": "手收"}.get(rec.get("gold_src"), "收割")
            a, b = rec.get("input") or "", rec.get("gold") or ""
            if a and b and len(a) == len(b):
                i = next((k for k in range(len(a)) if a[k] != b[k]), 0)
                lo = max(0, i - 2)
                return f"{who}「{a[lo:i + 3]}→{b[lo:i + 3]}」"
            return f"收割 {ts[5:10].replace('-', '/')}"
        if src.startswith("統計×"):
            return f"常錯{src}"
        if "手動" in src or src == "F7":
            return "手動 F7"
        return src[:14]

    def refresh():
        tree.delete(*tree.get_children())
        tree_rows.clear()
        items = escort.entries()
        cases = _case_map()
        nw, np_, nc = escort.counts()
        ship = escort.shipped_chars()
        root.title(f"常錯字清單（詞 {nw}・字對 {np_}・字 {nc}・出廠 {len(ship)}）")
        flt = search_var.get().strip()
        if sort_state["desc"]:
            items = items[::-1]
        if show_builtin.get():
            try:
                from ..engine import wordphon
                origin = wordphon._origin
            except Exception:
                origin = {}
            for ch in ship:
                pk = "／".join(sorted(o for o in origin.get(ch, ()) if "sys_words" in o)) or "出廠"
                items.append(("廠", ch, None, "出廠 " + pk))
        shown = 0
        for kind, disp, key, src in items:
            lbl = _src_label(src, cases)
            if kind in ("字", "對") and escort.covered(kind, key):
                lbl += "・出廠已含"
            if flt and flt not in disp and flt not in lbl:
                continue
            shown += 1
            iid = tree.insert("", "end", values=(kind, disp, lbl), tags=(kind,))
            tree_rows[iid] = (kind, key, disp)
        if shown == 0:
            tree.insert("", "end", values=("", "（沒有符合的項）" if flt else
                                           "（清單是空的：反白字詞→F7 保送）", ""))

    search_var.trace_add("write", lambda *a: refresh())
    _foc = {"t": 0.0}

    def _on_focus(_e=None):
        import time as _t
        now = _t.monotonic()
        if now - _foc["t"] > 1.0:
            _foc["t"] = now
            refresh()
    root.bind("<FocusIn>", _on_focus)

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

    refresh()
    add_entry.focus_set()
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
