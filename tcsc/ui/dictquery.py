# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/tcsc2026/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import itertools
import queue
import tkinter as tk
from tkinter import font as tkfont

from . import pickreading
from .. import settings
from ..engine import addword, phonetics, wordphon

ACTIVE = None

_FONT_FAMILY = "Microsoft JhengHei"
_BPMF = set(chr(c) for c in range(0x3105, 0x3130)) | set("ˊˇˋ˙")


def _is_bpmf(s: str) -> bool:
    return bool(s) and all(ch in _BPMF or ch.isspace() for ch in s)


def _lookup(q: str) -> list:
    wordphon._load()
    phonetics._load()
    q = q.strip()
    if not q:
        return []
    out = []

    if _is_bpmf(q):
        seq = tuple(q.split())
        ws = wordphon.words_by_reading(seq)
        out.append((f"注音反查　{' '.join(seq)}",
                    "\n".join(f"　{w}　詞頻 {wordphon.freq(w)}　"
                              f"來源 {'／'.join(sorted(wordphon.origins(w))) or '—'}"
                              for w in ws[:60]) or "　（沒有任何詞是這個讀音）"))
        if len(seq) == 1:
            cir = phonetics._reading2chars.get(seq[0], [])
            out.append((f"同音圈　{seq[0]}（{len(cir)} 字）",
                        "　" + "／".join(f"{c}({wordphon.freq(c)})" for c in cir[:40])))
        return out

    seqs = sorted(wordphon.reading_seqs(q))
    org = sorted(wordphon.origins(q))
    head = []
    head.append(f"　戶口：{'有' if seqs else '**查無**'}")
    head.append(f"　來源：{'／'.join(org) if org else '—'}")
    head.append(f"　讀音：{'｜'.join(' '.join(s) for s in seqs) if seqs else '—'}")
    head.append(f"　詞頻：{wordphon.freq(q)}"
                f"（語料 {wordphon.corpus_freq(q)}"
                f"／自學加成 {wordphon.learned_bonus(q)}）")
    lv = wordphon.learned_level(q)
    if lv:
        head.append(f"　自學段數：{lv}")
    if q in wordphon.commonwords():
        head.append("　📗 這個詞在你的常識詞庫裡（下面可以移除）")
    out.append((f"「{q}」", "\n".join(head)))

    if seqs:
        rivals = []
        for s in seqs:
            rivals += [w for w in wordphon.words_by_reading(s)
                       if w != q and w not in rivals]
        out.append((f"同音詞（{len(rivals)}）",
                    "　" + ("／".join(f"{w}({wordphon.freq(w)})" for w in rivals[:40])
                            or "（沒有同音對手＝這個讀音只有它）")))

    per = []
    for ch in q:
        rs = sorted(phonetics.readings(ch))
        raw = sorted(phonetics.raw_readings(ch))
        extra = [r for r in raw if r not in rs]
        per.append((ch, rs, extra))
    out.append(("逐字讀音",
                "\n".join(f"　{ch}　{'／'.join(rs) or '（字表查無）'}"
                          + (f"　〔被讀音黑名單拿掉：{'／'.join(ex)}〕" if ex else "")
                          for ch, rs, ex in per)))

    if not seqs and all((rs or _e) for _c, rs, _e in per):
        combos = list(itertools.product(*[(rs + _e) for _c, rs, _e in per]))
        out.append((f"建議讀音（{len(combos)} 種組合）",
                    "\n".join("　" + " ".join(c) for c in combos[:12])
                    + ("\n　…" if len(combos) > 12 else "")))
    if len(q) == 1:
        lines = []
        for r in sorted(phonetics.readings(q)):
            cir = phonetics._reading2chars.get(r, [])
            pos = cir.index(q) + 1 if q in cir else "—"
            lines.append(f"　{r}　第 {pos} 席／共 {len(cir)}　"
                         + "／".join(f"{c}({wordphon.freq(c)})" for c in cir[:12]))
        out.append(("這個字在各同音圈的席次", "\n".join(lines) or "　—"))
    return out


def open_query_window(notify=None, correct_fn=None, initial=None, reload_fn=None):
    def _say(m):
        if notify:
            try:
                notify(m)
            except Exception:
                pass

    root = tk.Tk()
    root.title("詞庫查詢／收詞")
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass
    dark = bool(settings.get("box_dark"))
    BG = "#1f1f1f" if dark else "#f4f4f4"
    FG = "#e6e6e6" if dark else "#111111"
    SUB = "#9a9a9a" if dark else "#777777"
    EBG = "#2b2b2b" if dark else "#ffffff"
    BTN = "#3a3a3a" if dark else "SystemButtonFace"
    SEL = "#264f78" if dark else "#b5d5ff"
    ACC = "#3ecfa0" if dark else "#0a7a55"
    root.configure(bg=BG)
    fnt = tkfont.Font(root=root, family=_FONT_FAMILY, size=11)
    bold = tkfont.Font(root=root, family=_FONT_FAMILY, size=12, weight="bold")
    mono = tkfont.Font(root=root, family=_FONT_FAMILY, size=11)

    try:
        import ctypes as _ct
        root.update_idletasks()
        _hw = _ct.windll.user32.GetParent(root.winfo_id())
        _v = _ct.c_int(1 if dark else 0)
        for _attr in (20, 19):
            _ct.windll.dwmapi.DwmSetWindowAttribute(
                _hw, _attr, _ct.byref(_v), _ct.sizeof(_v))
    except Exception:
        pass

    top = tk.Frame(root, bg=BG)
    top.pack(fill="x", padx=12, pady=(12, 6))
    tk.Label(top, text="查詢", bg=BG, fg=FG, font=bold).pack(side="left")
    ent = tk.Entry(top, bg=EBG, fg=FG, insertbackground=FG, font=fnt,
                   relief="flat", highlightthickness=1,
                   highlightbackground=SUB, highlightcolor=ACC)
    ent.pack(side="left", fill="x", expand=True, padx=8, ipady=4)
    ent.focus_set()

    def _grab_foreground():
        try:
            root.lift()
            root.focus_force()
            import ctypes as _c
            u = _c.windll.user32
            hw = u.GetParent(root.winfo_id()) or root.winfo_id()
            fg = u.GetForegroundWindow()
            me = _c.windll.kernel32.GetCurrentThreadId()
            other = u.GetWindowThreadProcessId(fg, None)
            att = bool(u.AttachThreadInput(me, other, True)) if other != me else False
            try:
                u.SetForegroundWindow(hw)
                u.BringWindowToTop(hw)
            finally:
                if att:
                    u.AttachThreadInput(me, other, False)
            ent.focus_set()
        except Exception:
            pass

    root.after(60, _grab_foreground)

    hint = tk.Label(root, bg=BG, fg=SUB, font=fnt, justify="left", anchor="w",
                    text="打詞查戶口與來源｜打注音（空白分隔，如 ㄅㄚ ㄨㄟˊ）反查同音詞"
                         "｜打單字看它在同音圈第幾席\n"
                         "Enter 查詢・同一個詞再按一次 Enter＝收進常識詞庫"
                         "｜F1＝改字（輸入法選錯就按它）")
    hint.pack(fill="x", padx=12)

    body = tk.Frame(root, bg=BG)
    body.pack(fill="both", expand=True, padx=12, pady=(8, 6))
    sb = tk.Scrollbar(body)
    sb.pack(side="right", fill="y")
    txt = tk.Text(body, bg=EBG, fg=FG, font=mono, relief="flat", wrap="word",
                  yscrollcommand=sb.set, insertbackground=FG,
                  highlightthickness=1, highlightbackground=SUB, width=74, height=26)
    txt.pack(side="left", fill="both", expand=True)
    sb.config(command=txt.yview)
    txt.tag_config("h", foreground=ACC, font=bold, spacing1=8, spacing3=3)
    txt.tag_config("b", foreground=FG)
    txt.tag_config("word", foreground=ACC, underline=True)

    bar = tk.Frame(root, bg=BG)
    bar.pack(fill="x", padx=12, pady=(0, 12))
    cur = {"q": "", "combos": [], "can_add": False}

    def _mkbtn(text, cmd):
        return tk.Button(bar, text=text, command=cmd, bg=BTN, fg=FG, font=fnt,
                         activebackground=SEL, activeforeground=FG,
                         relief="flat", padx=12, state="disabled")

    def do_add(_e=None):
        w, combos = cur["q"], cur["combos"]
        if not (w and combos):
            return
        seqs = combos if len(combos) == 1 else pickreading.pick(w, combos, "收", master=root)[0]
        if not seqs:
            return
        if wordphon.add_commonword(w, seqs):
            _say("📗 收進常識詞庫：" + w)
        go()

    def do_del(_e=None):
        w = cur["q"]
        if w and wordphon.remove_commonword(w):
            _say("已從常識詞庫移除：" + w)
        go()

    def show_mine(_e=None):
        d = wordphon.commonwords()
        txt.config(state="normal")
        txt.delete("1.0", "end")
        txt.insert("end", "我學過的常識詞（%d）\n" % len(d), "h")
        if not d:
            txt.insert("end", "　還沒收過任何詞——查一個詞，不在庫裡就能收。\n", "b")
        for w in sorted(d):
            rivals = [x for x in wordphon.words_by_reading(tuple(d[w][0])) if x != w]
            txt.insert("end", "　", "b")
            txt.insert("end", w, ("word", "w_" + w))
            txt.insert("end", "　%s　%s\n" % (
                "｜".join(" ".join(s) for s in d[w]),
                ("同音：" + "／".join(rivals[:5])) if rivals else "（唯一同音詞）"), "b")
            txt.tag_bind("w_" + w, "<Button-1>",
                         lambda e, x=w: (ent.delete(0, "end"), ent.insert(0, x), go()))
        txt.insert("end", "\n　（點任何一個詞＝填回查詢框並重查，接著就能移除）\n", "b")
        txt.config(state="disabled")

    btn_add = _mkbtn("＋ 收進常識詞庫（Enter）", do_add)
    btn_del = _mkbtn("🗑 從常識詞庫移除", do_del)
    btn_add.pack(side="left")
    btn_del.pack(side="left", padx=6)
    btn_mine = tk.Button(bar, text="📗 我學過的", command=show_mine, bg=BTN, fg=FG,
                         font=fnt, activebackground=SEL, activeforeground=FG,
                         relief="flat", padx=12)
    btn_mine.pack(side="right")

    rbar = tk.Frame(root, bg=BG)
    tk.Label(rbar, text="這個字的讀音", bg=BG, fg=FG, font=fnt).pack(side="left")
    r_ent = tk.Entry(rbar, width=8, bg=EBG, fg=FG, insertbackground=FG, font=fnt, relief="flat",
                     highlightthickness=1, highlightbackground=SUB, highlightcolor=ACC)
    r_ent.pack(side="left", padx=6, ipady=2)
    r_msg = tk.Label(root, text="", bg=BG, fg=SUB, font=fnt, anchor="w", justify="left")
    _OPS = (("加", "加：打這個音會出現它、它也能改成同音字"),
            ("加只逃生", "加（只逃生）：它能改成同音字，但別的字不會被改成它"),
            ("刪", "刪：這個音跟它完全無關"),
            ("刪但留逃生", "刪（留逃生）：別的字不會被改成它，它自己還能改成同音字"))

    def _set_reading(op):
        ch, bpmf = cur["q"], r_ent.get().strip().replace(" ", "")
        if not bpmf or any(ord(c) not in range(0x3105, 0x312A) and c not in "ˊˇˋ˙" for c in bpmf):
            r_msg.configure(text="讀音請用注音符號打，例如 ㄩˋ、ㄓㄨㄢˋ（一聲不加符號）")
            return
        import datetime
        phonetics.set_user_entry(ch, bpmf, op, f"{datetime.date.today()} 查詢窗")
        r_msg.configure(text=f"已記下：{ch} {bpmf} → {op or '回到內建'}；套用中…（幾秒）")
        _say(f"讀音：{ch} {bpmf} → {op or '回到內建'}")
        ev = reload_fn() if reload_fn else None

        def wait():
            if ev is not None and not ev.is_set():
                root.after(200, wait)
                return
            r_msg.configure(text=f"已套用：{ch} {bpmf} → {op or '回到內建'}")
            go()
        wait()

    for op, tip in _OPS:
        tk.Button(rbar, text=tip.split("：")[0], command=lambda o=op: _set_reading(o), bg=BTN, fg=FG, font=fnt,
                  activebackground=SEL, activeforeground=FG, relief="flat", padx=8).pack(side="left", padx=(0, 4))
    tk.Button(rbar, text="回到內建", command=lambda: _set_reading(""), bg=BTN, fg=FG, font=fnt,
              activebackground=SEL, activeforeground=FG, relief="flat", padx=8).pack(side="left")

    def _sync_reading_row(q):
        is_char = len(q) == 1 and not _is_bpmf(q) and "㐀" <= q <= "鿿"
        if is_char:
            mine = {r: op for (c, r), op in phonetics.user_entries().items() if c == q}
            tips = "　".join(t for _o, t in _OPS[:2])
            r_msg.configure(text=("你設定過：" + "、".join(f"{r}（{op}）" for r, op in mine.items()) + "\n" if mine else "")
                            + tips + "\n" + "　".join(t for _o, t in _OPS[2:]))
            rbar.pack(fill="x", padx=12, pady=(0, 2), before=bar)
            r_msg.pack(fill="x", padx=12, pady=(0, 6), before=bar)
        else:
            rbar.pack_forget()
            r_msg.pack_forget()

    def _sync_buttons(q):
        _sync_reading_row(q)
        cur["q"] = q
        cur["combos"] = []
        can_add = can_del = False
        if q and not _is_bpmf(q):
            if q in wordphon.commonwords():
                can_del = True
            elif not wordphon.reading_seqs(q):
                cur["combos"] = addword.reading_combos(q)
                can_add = bool(cur["combos"])
        cur["can_add"] = can_add
        btn_add.config(state="normal" if can_add else "disabled")
        btn_del.config(state="normal" if can_del else "disabled")
        btn_mine.config(text="📗 我學過的 %d 個" % len(wordphon.commonwords()))

    def go(_e=None):
        q = ent.get()
        txt.config(state="normal")
        txt.delete("1.0", "end")
        try:
            blocks = _lookup(q)
        except Exception as e:
            blocks = [("查詢出錯", "　%s" % e)]
        if not blocks:
            txt.insert("end", "　輸入要查的詞或注音。\n", "b")
        for title, content in blocks:
            txt.insert("end", title + "\n", "h")
            txt.insert("end", content + "\n", "b")
        txt.config(state="disabled")
        _sync_buttons(q.strip())

    def on_enter(_e=None):
        q = ent.get().strip()
        if q and q == cur["q"] and cur["can_add"]:
            do_add()
            return
        go()

    ent.bind("<Return>", on_enter)
    tk.Button(top, text="查", command=go, bg=BTN, fg=FG, font=fnt,
              activebackground=SEL, activeforeground=FG,
              relief="flat", padx=14).pack(side="left")

    cmdq = queue.Queue()
    f1cyc = {}

    def entry_correct(step=1):
        if correct_fn is None:
            return
        s0 = ent.get().strip()
        if not s0:
            return
        c = f1cyc.get("e")
        if c and s0 == c["list"][c["idx"]]:
            c["idx"] = (c["idx"] + step) % len(c["list"])
        else:
            try:
                ranked = list(correct_fn(s0))
            except Exception:
                ranked = [s0]
            if not ranked:
                ranked = [s0]
            if s0 not in ranked:
                ranked.append(s0)
            f1cyc["e"] = c = {"list": ranked, "idx": 0}
        ent.delete(0, "end")
        ent.insert(0, c["list"][c["idx"]])
        ent.icursor("end")
        go()

    def poll_cmd():
        try:
            while True:
                cmd = cmdq.get_nowait()
                if cmd in ("f1", "f2"):
                    entry_correct(1 if cmd == "f1" else -1)
        except queue.Empty:
            pass
        root.after(80, poll_cmd)

    if initial:
        ent.insert(0, initial)
    go()
    root.geometry("+120+90")
    global ACTIVE
    try:
        import ctypes
        _hwnd = ctypes.windll.user32.GetAncestor(root.winfo_id(), 2)
    except Exception:
        _hwnd = 0
    ACTIVE = {"q": cmdq, "hwnd": int(_hwnd or 0)}
    poll_cmd()
    try:
        from . import movernative
        movernative.push(root)
    except Exception:
        movernative = None
    try:
        root.mainloop()
    finally:
        ACTIVE = None
        if movernative is not None:
            try:
                movernative.pop(root)
            except Exception:
                pass
