# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/tcsc2026/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import re
import time

from . import clip, converge, ia2text, route, selprobe, textutil, win
from ..engine import garble
from .. import settings, symbols
from ..engine import crashlog, escstop

GRAB_CHARS = clip.GRAB_CHARS
_BREAKS = "\ufffc\ufffd"
_ZW = "\u200b\u200c\u200d\u2060\ufeff\u00ad"
_ZW_TABLE = {ord(c): None for c in _ZW}
_WS = " \t\u3000\u00a0\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u202f\u205f"
MSG_NO_GRAB = "剪貼簿沒抓到字：游標前要有字，且不能有輸入法的底線（先按 Enter 完成選字）"
MSG_NO_UNIT = "沒抓到要修的句子：游標前要有字；選字底線還在的話，先按 Enter 再按 F1"
MSG_ENTER = "（選字底線還在的話，先按 Enter 再按 F1）"
MSG_UIA_BLIND = "UIA 讀不到這個視窗的字——「改字方式」抓字改成剪貼簿或自動再試"
MSG_IA2_BLIND = "IA2 讀不到這個網頁的字——把「瀏覽器走 IA2」取消勾選再試"


def last_channel() -> str:
    return route.grab_channel()


def _cut_ghosts(text):
    if not text:
        return text
    k = max(text.rfind(c) for c in _BREAKS)
    return text[k + 1:] if k != -1 else text


def _strip_zw(text):
    return text.translate(_ZW_TABLE)


def _raw_suffix(raw, n):
    i, seen = len(raw), 0
    while i > 0 and (seen < n or raw[i - 1] in _ZW):
        i -= 1
        if raw[i] not in _ZW:
            seen += 1
    return raw[i:]


def _raw_prefix(raw, n):
    i, seen = 0, 0
    while i < len(raw) and (seen < n or raw[i] in _ZW):
        if raw[i] not in _ZW:
            seen += 1
        i += 1
    return raw[:i]


def _last_line(window, p=None):
    window = _cut_ghosts(window or "").rstrip("\r\n")
    k = max(window.rfind("\r"), window.rfind("\n"))
    line = window[k + 1:] if k != -1 else window
    if p is not None and p.layer == "終端機":
        for pc in symbols.PROMPTS:
            k = line.rfind(pc)
            if k != -1:
                line = line[k + 1:]
    return line


_uia_fail = {}


def _window_uia(n=None):
    proc = win.foreground_process() or "?"
    if _uia_fail.get(proc, 0) >= 3:
        return None
    blinked, why = False, ""
    for attempt in (1, 2):
        ctx = selprobe.caret_paragraph(timeout=1.2)
        if ctx is not None:
            _uia_fail.pop(proc, None)
            return ctx[0][-(n or GRAB_CHARS):]
        ctx = selprobe.caret_context(back=n or GRAB_CHARS, fwd=0, timeout=1.2)
        if ctx is not None:
            _uia_fail.pop(proc, None)
            return ctx[0]
        why = selprobe.last_fail() or ""
        crashlog.log(f"UIA讀不到 [{proc}] {why}")
        if why.startswith("選取空") and not blinked and settings.get("uia_wake_blink", True):
            win.focus_blink(win.foreground_hwnd())
            _nudge()
            time.sleep(0.05)
            blinked = True
            continue
        if attempt == 1 and not _uia_fail.get(proc):
            time.sleep(0.2)
            continue
        break
    if not why.startswith("選取空"):
        _uia_fail[proc] = _uia_fail.get(proc, 0) + 1
    return None


def _window_clip():
    time.sleep(0.08)
    return clip.grab_window()


FULL_LADDER = ("nudge", "blink", "nudge", ("poll", 2.0))
SEL_LADDER = ("blink", ("poll", 1.0))
SHORT_LADDER = ("nudge", ("poll", 0.5))
_state = {"ia2_dead": None,
          "sel_kb": False}


def _nudge():
    win.ntap(win.VK_LEFT, 1)
    win.ntap(win.VK_RIGHT, 1)
    time.sleep(0.10)


def _ia2_ladder(app, read_fn, why, stages):
    if app is not None:
        app.notify("IA2 還沒醒——正在自動修復，請稍候…")
    crashlog.log(f"IA2 修復梯進場（{why}）階={stages}")
    fg0 = win.foreground_hwnd()
    text = None
    for st in stages:
        escstop.check()
        if st == "nudge":
            _nudge()
        elif st == "blink":
            win.focus_blink(fg0)
        else:
            t0 = time.monotonic()
            while time.monotonic() - t0 < st[1]:
                escstop.check()
                time.sleep(0.25)
                text, why = read_fn()
                if text is not None:
                    break
            crashlog.log(f"輪詢 {st[1]}s 後讀={'成' if text is not None else '敗'}")
            continue
        text, why = read_fn()
        crashlog.log(f"{st} 後讀={'成' if text is not None else '敗'}")
        if text is not None:
            break
    return text, why


def _recently_dead():
    d = _state["ia2_dead"]
    return bool(d and d[0] == win.foreground_hwnd() and time.monotonic() - d[1] < 3.0)


def _window_ia2(app, quiet=False):
    rd = lambda: ia2text.read_before_caret(back=200, timeout=0.8)
    text, why = rd()
    if text is None:
        text, why = _ia2_ladder(app, rd, why, SHORT_LADDER if _recently_dead() else FULL_LADDER)
    if text is None:
        crashlog.log(f"IA2 讀失敗：{why}" + ("（自動：換路）" if quiet else ""))
        if not quiet:
            app.notify(MSG_IA2_BLIND + f"〔{why}〕")
    return text


def _kb(p):
    return p._replace(grab="auto", write=p.base)


def _window(app, p):
    if p.grab == "ia2":
        w = _window_ia2(app, quiet=p.auto)
        if w is not None:
            return w, "ia2", p
        if not p.auto:
            return None, None, p
        w = _window_uia()
        if w is not None:
            return w, "ia2→uia", _kb(p)
        w = _window_clip()
        if w is not None:
            return w, "ia2→uia→clip", _kb(p)
        app.notify("IA2、UIA 都讀不到，換剪貼簿也沒抓到字——" + MSG_NO_GRAB)
        return None, None, p
    if p.grab == "clip":
        w = _window_clip()
        if w is None:
            app.notify(MSG_NO_GRAB)
            return None, None, p
        return w, "clip", p
    w = _window_uia()
    if w is not None:
        return w, "uia", p
    if p.grab != "auto" or p.layer == "終端機":
        app.notify(MSG_UIA_BLIND if not p.layer else f"{p.layer}：UIA 讀不到這個視窗的字{MSG_ENTER}")
        return None, None, p
    if win.foreground_process() in win.BROWSERS and settings.get("ia2_read_fallback", True):
        try:
            w = ia2text.read_before_caret(back=200, timeout=0.8)[0]
        except Exception:
            w = None
        if w is not None:
            return w, "uia→ia2", p
    w = _window_clip()
    if w is None:
        app.notify("UIA 讀不到，換剪貼簿也沒抓到字——" + MSG_NO_GRAB)
        return None, None, p
    return w, "uia→clip", p


def _writer(app, p, old, new_of, anchor="", conv=None):
    from . import write
    if p.write == "ia2":
        base = p.base if p.auto else None
        return lambda new: write.write_unit_ia2(app, old, new_of(new), base=base, anchor=anchor, conv=conv)
    if conv is not None:
        return lambda new: write.write_unit_verified(app, old, new_of(new), p.write, conv)
    return lambda new: write.write_unit(app, old, new_of(new), p.write)


def _conv(p, ch, line_raw, old_raw):
    if not p.auto or p.layer == "終端機" or not settings.get("auto_verify", True):
        return None
    kind = "ia2" if ch in ("ia2", "uia→ia2") else ("uia" if ch in ("uia", "ia2→uia") else None)
    if kind is None or not line_raw.endswith(old_raw):
        return None
    return {"reader": kind, "head": line_raw[:len(line_raw) - len(old_raw)], "after0": converge.read_after(kind)}


def _anchor(line_raw, old_raw):
    head = line_raw[:len(line_raw) - len(old_raw)] if old_raw and line_raw.endswith(old_raw) else ""
    return head[-6:]


def take_garble():
    syl, _state["garble"] = _state.get("garble"), None
    return syl


GARBLE_LONG = 300
SINGLE_HINT_S = 8.0


def _read_long(ch):
    try:
        if ch.endswith("clip"):
            return clip.grab_window(GARBLE_LONG)
        if ch.startswith("ia2") and not ch.endswith(("uia", "clip")):
            text, _why = ia2text.read_before_caret(back=GARBLE_LONG, timeout=0.8)
            return text
        return _window_uia(GARBLE_LONG)
    except Exception as e:
        crashlog.log(f"長亂碼重讀失敗 {e!r}")
        return None


_KEYISH = re.compile(r"[0-9A-Za-z,./;\- ]{6,}$")


def _log_garble_miss(line):
    m = _KEYISH.search(line or "")
    if m and sum(c.isdigit() or c in ",./;-" for c in m.group(0)) >= 2:
        crashlog.log(f"亂碼沒觸發：{crashlog.q(m.group(0)[-80:])}（{len(m.group(0))} 鍵）")


def _hidden(p):
    if not settings.get("ime_commit", True):
        return False
    return (settings.get("blink_first", True) or p.layer == "終端機" or win.foreground_process() in win.COMPOSE_HIDDEN)


def _commit_now():
    win.focus_blink(win.foreground_hwnd())
    return True


def read_unit(app, blinked=False, garble_ok=True):
    p = route.plan()
    commit = settings.get("ime_commit", True)
    hidden = _hidden(p)
    if hidden and not blinked:
        blinked = _commit_now()
    window, ch, p = _window(app, p)
    if window is None and hidden and not blinked:
        win.focus_blink(win.foreground_hwnd())
        return read_unit(app, blinked=True, garble_ok=garble_ok)
    if window is None:
        return None
    line_raw = _last_line(window, p)
    _state["garble"] = None
    if garble_ok and settings.get("garble_on", True):
        ime = bool(settings.get("garble_ime", True))
        g = garble.analyze(line_raw, ime=ime)
        if (g and line_raw == (window or "").rstrip("\r\n") and len(window or "") >= GRAB_CHARS - 2
                and all(c in garble.KEYS for c in line_raw[:g.start].lower())):
            longer = _read_long(ch)
            if longer:
                lr = _last_line(longer, p)
                g2 = garble.analyze(lr, ime=ime)
                if g2 and len(lr) - g2.start > len(line_raw) - g.start:
                    line_raw, g = lr, g2
        cyc = getattr(app, "_cycle", None)
        head = getattr(app, "_cyc_head", None)
        cycling = bool(cyc and cyc.get("garble") and head and head(cyc, line_raw) is not None)
        if not g and settings.get("garble_single", True) and not cycling:
            g1 = garble.analyze_single(line_raw, ime=ime)
            if g1:
                ok = getattr(app, "_single_garble_ok", None)
                hint, _state["single_hint"] = _state.get("single_hint"), None
                forced = bool(hint and hint[0] == line_raw and time.monotonic() - hint[1] < SINGLE_HINT_S)
                if getattr(g1, "strict", False) or forced or (ok and ok(line_raw, g1)):
                    g = g1
                else:
                    _state["single_hint"] = (line_raw, time.monotonic())
                    app.notify(f"結尾的「{line_raw[g1.start:g1.end].strip()}」像是忘了切中文打的注音？再按一次 F1 轉成中文，要算字按 F3")
                    return None
        if not g:
            _log_garble_miss(line_raw)
        if g:
            old_raw = line_raw[g.start:]
            g.before = line_raw[:g.start][-20:]
            _state["garble"] = g
            route.note_grab(ch, p.layer)
            return line_raw[g.start:g.end], _writer(app, p, old_raw, lambda new: new + g.tail,
                                                    anchor=_anchor(line_raw, old_raw),
                                                    conv=_conv(p, ch, line_raw, old_raw))
    unit, tail = textutil.split_tail_unit(_strip_zw(line_raw))
    unit = unit.lstrip(_WS)
    if not unit.strip():
        crashlog.log(f"抓到字但切不出句子（{ch}）尾段={crashlog.q(line_raw[-40:])}")
        if commit and not blinked and (hidden or win.ime_chinese(win.foreground_hwnd())):
            win.focus_blink(win.foreground_hwnd())
            return read_unit(app, blinked=True, garble_ok=garble_ok)
        app.notify(MSG_NO_UNIT)
        return None
    route.note_grab(ch, p.layer)
    old_raw = _raw_suffix(line_raw, len(unit + tail))
    return unit, _writer(app, p, old_raw, lambda new: new + tail, anchor=_anchor(line_raw, old_raw),
                         conv=_conv(p, ch, line_raw, old_raw))


def _kb_has_selection():
    try:
        if selprobe.probe() != selprobe.SEL:
            return False
    except Exception:
        return False
    return bool(clip.selection_text(False, timeout=0.9))


def has_selection(app=None):
    p = route.plan()
    if p.layer == "終端機":
        return False
    if p.layer == "IA2":
        rd = lambda: ia2text.read_selection(timeout=0.6)
        t, why = rd()
        if t is None:
            t, why = _ia2_ladder(app, rd, why, SEL_LADDER)
            if t is None:
                _state["ia2_dead"] = (win.foreground_hwnd(), time.monotonic())
                if p.auto:
                    _state["sel_kb"] = True
                    return _kb_has_selection()
                return False
        _state["sel_kb"] = False
        return bool(t and t.strip())
    return _kb_has_selection()


def _sel_result(sel, write_fn, forced=True):
    _state["garble"] = None
    if settings.get("garble_on", True):
        core = sel.rstrip("\r\n")
        ime = bool(settings.get("garble_ime", True))
        g = garble.analyze_selection(core, ime=ime) if forced else garble.analyze(core, ime=ime)
        if g:
            _state["garble"] = g
            head, tail = sel[:g.start], g.tail + sel[len(core):]
            return sel[g.start:g.end], lambda new: write_fn(head + new + tail)
    return sel, write_fn


def read_sel(app):
    from . import write
    p = route.plan()
    if p.layer == "IA2" and not (p.auto and _state.get("sel_kb")):
        sel, why = ia2text.read_selection(timeout=0.6)
        if sel is None and p.auto:
            p = _kb(p)
        else:
            if not sel or not sel.strip():
                app.notify("IA2 讀不到反白的字" + (f"〔{why}〕" if why else ""))
                return None
            route.note_grab("sel", p.layer)
            base = p.base if p.auto else None
            return _sel_result(sel, lambda new: write.write_selection_ia2(app, sel, new, base=base))
    elif p.layer == "IA2":
        p = _kb(p)
    _state["sel_kb"] = False
    sel = clip.selection_text(False)
    if not sel:
        app.notify("沒有反白到文字（請先選取要修的字）")
        return None
    route.note_grab("ia2→sel" if p.layer == "IA2" else "sel", p.layer)
    return _sel_result(sel, lambda new: write.write_selection(app, sel, new, p.write))


def read_prev_unit(app, blinked=False):
    p = route.plan()
    if _hidden(p) and not blinked:
        blinked = _commit_now()
    window, ch, p = _window(app, p)
    if window is None:
        return None
    line_raw = _last_line(window, p)
    prev, mid, cur = textutil.split_prev_unit(_strip_zw(line_raw))
    prev = prev.lstrip(_WS)
    if not prev.strip():
        if not blinked and settings.get("ime_commit", True):
            win.focus_blink(win.foreground_hwnd())
            return read_prev_unit(app, blinked=True)
        app.notify("游標前只有這一句，沒有上一句——直接按 F1 就好")
        return None
    route.note_grab(ch, p.layer)
    old_raw = _raw_suffix(line_raw, len(prev + mid + cur))
    return _sel_result(prev, _writer(app, p, old_raw, lambda new: new + mid + cur, anchor=_anchor(line_raw, old_raw),
                                     conv=_conv(p, ch, line_raw, old_raw)), forced=False)


def _next_unit(app, after):
    k = min((after.find(c) for c in _BREAKS if c in after), default=-1)
    if k != -1:
        after = after[:k]
    after = after.split("\r")[0].split("\n")[0]
    clean = _strip_zw(after)
    if not clean.strip():
        app.notify("游標後面沒有字——右邊那段要在同一行才搆得到")
        return None
    mid, nxt = textutil.split_next_unit(clean)
    nxt = nxt.rstrip(_WS)
    if not nxt.strip():
        app.notify("游標後面這行只剩標點，沒有可修的句子")
        return None
    return mid, nxt, _raw_prefix(after, len(mid + nxt))


def read_next_unit(app):
    from . import write
    p = route.plan()
    if _hidden(p):
        _commit_now()
    if p.grab == "clip":
        app.notify("改後一句要讀游標後面的字，只有 UIA 做得到——抓字改成 UIA 或自動")
        return None
    ch = "uia"
    if p.grab == "ia2":
        rd = lambda: ia2text.read_after_caret(fwd=GRAB_CHARS, timeout=0.8)
        after, why = rd()
        if after is None:
            after, why = _ia2_ladder(app, rd, why, FULL_LADDER)
        if after is not None:
            got = _next_unit(app, after)
            if got is None:
                return None
            mid, nxt, old_raw = got
            route.note_grab("ia2", p.layer)
            base = p.base if p.auto else None
            return nxt, lambda new: write.write_next_ia2(app, old_raw, mid + new, base=base)
        if not p.auto:
            app.notify(MSG_IA2_BLIND + f"〔{why}〕")
            return None
        crashlog.log(f"IA2 讀不到游標後（{why}）→ 自動：換 UIA")
        p, ch = _kb(p), "ia2→uia"
    ctx = selprobe.caret_context(back=0, fwd=GRAB_CHARS, timeout=1.2)
    if ctx is None:
        app.notify("讀不到游標後的文字（這個視窗 UIA 盲）")
        return None
    got = _next_unit(app, ctx[1] or "")
    if got is None:
        return None
    mid, nxt, old_raw = got
    route.note_grab(ch, p.layer)
    return _sel_result(nxt, lambda new: write.write_next(app, old_raw, mid + new, p.write), forced=False)


def grab_word(app, maxlen=8, hint="", copy_browser=False):
    from . import winkeys as wk
    try:
        browser = copy_browser and win.foreground_process() in win.BROWSERS
        if not browser and selprobe.probe(timeout=0.25) == selprobe.NOSEL:
            return ""
    except Exception:
        pass
    saved = clip.get_clip()
    clip.set_clip(clip.SENTINEL)
    time.sleep(0.06)
    wk.combo(wk.VK_CONTROL, wk.VK_C)
    time.sleep(0.22)
    sel = clip.get_clip()
    clip.set_clip(saved)
    word = (sel or "").strip()
    if word == clip.SENTINEL or not word:
        return ""
    if len(word) > maxlen:
        app.notify(f"選取太長（上限 {maxlen} 字）")
        return None
    return word
