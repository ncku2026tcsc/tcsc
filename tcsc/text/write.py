# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/tcsc2026/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import time

from . import clip, converge, ia2text, route, selprobe, textutil, win, winkeys as wk
from .. import settings
from ..engine import crashlog, escstop

MSG_ABORT_IME = ("發現異常，已停止寫入。不能有輸入法的底線\n"
                 "請按 Enter 取消原輸入法的選取，不然程式讀不到字")
MSG_ABORT_IA2 = "發現異常，已停止寫入。畫面內容跟剛抓的對不上\n再按一次 F1 重抓重改"
BACKSPACE_PROBE_WAIT = 0.30


def _sel_confirmed() -> bool:
    try:
        return selprobe.probe(timeout=0.25) != selprobe.NOSEL
    except Exception:
        return True


def _steps(old: str) -> int:
    return textutil.utf16_len(old) - old.count("\r\n")


def _emit(text: str, mode: str, reselect: bool = False):
    if mode == "type":
        wk.type_text(text)
        if reselect:
            wk.select_left(textutil.utf16_len(text))
    else:
        clip.paste_selection(text, reselect=reselect)
    route.note_write(mode)


def _sel_fix(n):
    got = _settled(selprobe.sel_length(), n)
    for _ in range(2):
        if not got:
            return None
        if got == n:
            return True
        if got < n:
            wk.select_left(n - got)
        else:
            wk.select_right(got - n)
        time.sleep(0.05)
        got = _settled(selprobe.sel_length(), n)
    if got == n:
        return True
    if got:
        wk.select_right(got)
    return False if got else None


def _settled(got, n, limit=0.6):
    if not got or got == n:
        return got
    t0 = time.monotonic()
    while time.monotonic() - t0 < limit:
        time.sleep(0.04)
        cur = selprobe.sel_length()
        if cur == got or cur == n:
            return cur
        got = cur
        if not got:
            return got
    return got


def _sel_copied(old, quick=False) -> bool:
    if route.plan().layer == "終端機":
        return False
    sel = clip.selection_text(False, timeout=0.25 if quick else 0.6)
    if not sel and not quick:
        sel = clip.selection_text(False, timeout=1.0)
    ok = bool(sel) and sel.replace("\r\n", "\n") == old.replace("\r\n", "\n")
    if not ok:
        crashlog.log(f"選取核對：複製到 {'（空）' if not sel else crashlog.q(sel[-30:])}，要蓋的是 {crashlog.q(old[-30:])}"
                     f"［{win.foreground_process() or '?'}］")
    return ok


_state = {}


def _wait_caret_back(limit=1.0):
    t0 = time.monotonic()
    time.sleep(0.15)
    while time.monotonic() - t0 < limit:
        try:
            if selprobe.caret_context(back=4, fwd=0, timeout=0.15) is not None:
                return
        except Exception:
            return
        time.sleep(0.08)


def _sel_fail(app, why, soft):
    if soft:
        crashlog.log(f"選取失敗（{why}）→ 改退格重打")
        return None
    app.abort_write(why)
    return False


def _select_old(app, old, soft=False):
    _state.pop("blinked", None)
    n = _steps(old)
    wk.select_left(n)
    time.sleep(settings.sp(0.04))
    if "\n" not in old and "\r" not in old and textutil.utf16_len(old) == len(old):
        fixed = _sel_fix(n)
        if fixed is True:
            return True
        if fixed is False:
            return _sel_fail(app, "選取對不準（補了兩次還是不對，已收回）", soft)
    if _sel_confirmed() or _sel_copied(old, quick=settings.get("ime_commit", True)):
        return True
    wk.select_right(n)
    time.sleep(0.12)
    if settings.get("ime_commit", True):
        win.focus_blink(win.foreground_hwnd())
        _wait_caret_back()
        _state["blinked"] = _state["blink_round"] = True
    wk.select_left(n)
    time.sleep(settings.sp(0.04) + 0.06)
    if _sel_confirmed() or _sel_copied(old):
        return True
    return _sel_fail(app, "選取沒有成立（試了兩次）", soft)


def _kept_tail(old, new):
    from .. import symbols
    marks, k = symbols.breaks(), 0
    while k < min(len(old), len(new)) and old[-1 - k] == new[-1 - k] and old[-1 - k] in marks:
        k += 1
    return k if k < len(old) else 0


def _swap(app, old, new, mode, soft=False):
    k = _kept_tail(old, new)
    if k:
        wk.move(-k)
        try:
            return _swap(app, old[:-k], new[:-k], mode, soft)
        finally:
            wk.move(k)
    if old:
        ok = _select_old(app, old, soft) if soft else _select_old(app, old)
        if ok is not True:
            return ok
    escstop.check()
    _emit(new, "paste" if _state.pop("blinked", False) else mode)
    return True


def write_unit(app, old, new, mode):
    escstop.check()
    if old == new:
        return True
    if mode == "backspace":
        k = _kept_tail(old, new)
        if k:
            wk.move(-k)
            try:
                return _write_backspace(app, old[:-k], new[:-k]) is not False
            finally:
                wk.move(k)
        return _write_backspace(app, old, new) is not False
    p = route.plan()
    soft = p.auto and p.layer != "終端機" and settings.get("sel_fallback_bs", True)
    r = _swap(app, old, new, mode, soft)
    if r is None:
        return _fallback_backspace(app, old, new)
    return r


def _fallback_backspace(app, old, new):
    k = selprobe.sel_length()
    if k:
        wk.select_right(k)
        time.sleep(0.05)
    before = _caret_text()
    if before is None and win.foreground_process() in win.BROWSERS:
        try:
            before = ia2text.read_before_caret(back=len(old) + 40, timeout=0.6)[0]
        except Exception:
            before = None
    if before is None or not before.replace("\r\n", "\n").endswith(old.replace("\r\n", "\n")):
        app.abort_write("選取不成立，改退格重打前確認不到游標前是原字（已停手）")
        return False
    crashlog.log("選取不成立 → 退格重打（游標前確認是原字）")
    return _write_backspace(app, old, new) is not False


def _modes(base):
    return ("type", "paste") if base == "type" else ("paste", "type")


def _fix_tail(app, r, want, mode):
    return _swap(app, r, want, mode)


def _conv_back(conv, old, new):
    return len(conv["head"]) + len(old) + 2 * len(new) + 16


def _conv_giveup(app, res, why, new):
    clip.set_clip(new)
    app.abort_write(f"自動收斂{'停手' if res == converge.LOST else '沒收斂'}（{why}）",
                    "自動重寫了還是對不上，新字已放進剪貼簿，Ctrl+V 可貼回（詳情記在 crash.log）")


def write_unit_verified(app, old, new, mode, conv):
    if old == new:
        write_unit(app, old, new, mode)
        return
    _state.pop("blink_round", None)
    rd = converge.reader(conv["reader"], back=_conv_back(conv, old, new))
    base = rd()
    trust = base is not None and converge.judge(base, conv["head"], old, old, conv["after0"])[0] == "ok"
    if write_unit(app, old, new, mode) is False or not trust:
        if not trust:
            crashlog.log(f"寫完回讀檢查：寫前基準讀不準（{'讀不到' if base is None else crashlog.q(base[0][-20:])}）→ 這次不驗")
        return
    modes = ("paste", "type") if _state.pop("blink_round", False) else _modes(mode)
    res, acted = converge.run(app, rd, conv["head"], old, new, conv["after0"], modes, _fix_tail,
                              prev=base, stale_guard=True)
    if res in (converge.OK, converge.ABORTED) or (res == converge.LOST and not acted):
        return
    _conv_giveup(app, res, "鍵盤寫回", new)


def _converge_ia2(app, why, old, new, base, conv):
    touched = why.startswith("寫後驗不過") or why.startswith("逾時")
    rd = converge.reader("ia2", back=_conv_back(conv, old, new))
    modes = _modes(base)
    res, acted = converge.run(app, rd, conv["head"], old, new, conv["after0"], modes, _fix_tail,
                              prev=(conv["head"] + old, conv["after0"]) if touched else None)
    crashlog.log(f"IA2 直改沒成功（{why}）→ 自動收斂：{res}，動手 {acted} 次")
    if res == converge.OK:
        route.note_write(f"ia2→{modes[(acted - 1) % len(modes)]}" if acted else "ia2")
        return True
    if res == converge.ABORTED:
        return True
    if res == converge.LOST and not acted:
        return False
    _conv_giveup(app, res, f"IA2 {why}", new)
    return True


def write_selection(app, old, new, mode):
    escstop.check()
    if mode == "backspace":
        wk.tap(win.VK_BACK)
        time.sleep(settings.sp(0.04))
        _emit(new, "paste", reselect=True)
        route.note_write("backspace")
        return
    _emit(new, mode, reselect=True)


def _write_backspace(app, old, new, retry=True):
    t0 = _caret_text()
    wk.tap(win.VK_BACK)
    if t0 is not None:
        deadline = time.monotonic() + BACKSPACE_PROBE_WAIT
        changed = False
        while True:
            time.sleep(0.02)
            t1 = _caret_text()
            if t1 is None or t1 != t0:
                changed = True
                break
            if time.monotonic() >= deadline:
                break
        if not changed:
            if retry and settings.get("ime_commit", True):
                crashlog.log("退格進不去，先收底線再試一次")
                win.focus_blink(win.foreground_hwnd())
                _wait_caret_back()
                t2 = _caret_text()
                if t2 is not None and t2.endswith(old):
                    return _write_backspace(app, old, new, retry=False)
            app.abort_write("退格進不去")
            return False
    for _ in range(len(old) - 1):
        escstop.check()
        wk.tap(win.VK_BACK)
        time.sleep(0.01)
    time.sleep(settings.sp(0.04))
    saved = clip.get_clip()
    if clip.set_clip_confirm(new):
        wk.combo(wk.VK_CONTROL, wk.VK_V)
        time.sleep(0.15)
        clip.set_clip(saved)
    else:
        clip.set_clip(saved)
        wk.type_text(new)
    route.note_write("backspace")


def _caret_text():
    try:
        ctx = selprobe.caret_context(back=120, fwd=0, timeout=0.3)
        return ctx[0] if ctx else None
    except Exception:
        return None


def _ime_composing_probe(ia2: bool = False) -> bool:
    for attempt in (1, 2):
        wk.select_left(1)
        time.sleep(0.04 if attempt == 1 else 0.10)
        if ia2:
            sel, _why = ia2text.read_selection(timeout=0.4)
            suspect = (sel == "")
        else:
            try:
                suspect = selprobe.probe(timeout=0.25) == selprobe.NOSEL
            except Exception:
                suspect = False
        wk.select_right(1)
        time.sleep(0.03)
        if not suspect:
            return False
        if attempt == 1:
            crashlog.log("組字探針第一次沒選到，再探一次")
            time.sleep(0.12)
    return True


def _clear_underline(ia2=False) -> bool:
    if not _ime_composing_probe(ia2=ia2):
        return True
    if not settings.get("ime_commit", True):
        return False
    crashlog.log("偵測到選字底線，先收掉再寫")
    win.focus_blink(win.foreground_hwnd())
    _wait_caret_back()
    return not _ime_composing_probe(ia2=ia2)


def _ia2_after(app, why, old, new, check_missing):
    if not why:
        route.note_write("ia2")
        return
    if not (why.startswith("寫後驗不過") or why.startswith("逾時")):
        app.abort_write(f"IA2 {why}", MSG_ABORT_IA2)
        return
    if check_missing:
        text, _w = ia2text.read_before_caret(back=max(len(old), len(new)) + 8, timeout=0.8)
        if text is not None and text.endswith(new):
            route.note_write("ia2")
            return
        if text is not None and text.endswith(old):
            app.abort_write(f"IA2 {why}", MSG_ABORT_IA2)
            return
        crashlog.log(f"IA2 寫回失蹤（{why}）→ 新字放進剪貼簿")
        clip.set_clip(new)
        app.abort_write(f"IA2 {why}", "IA2 直改沒成功，字可能被網頁吃掉。新字已放進剪貼簿，Ctrl+V 可貼回；"
                                      "這個網頁建議取消「瀏覽器走 IA2」")
        return
    app.abort_write(f"IA2 {why}", MSG_ABORT_IA2)


def _ia2_try(fn):
    why = fn()
    if why and not (why.startswith("寫後驗不過") or why.startswith("逾時")):
        crashlog.log(f"IA2 寫前驗沒過（{why}），再試一次")
        time.sleep(0.12)
        why = fn()
    return why


def _before_caret(n):
    text, _w = ia2text.read_before_caret(back=n, timeout=0.8)
    if text is not None:
        return text
    return _caret_text()


def _state_before(old, new, anchor):
    text = _before_caret(len(anchor) + max(len(old), len(new)) + 8)
    if text is None:
        return None
    if text.endswith(new):
        return "new"
    if text.endswith(old):
        return "old"
    if len(anchor) >= 2 and text.endswith(anchor):
        return "gone"
    return None


def _find_once(text, pat):
    i = text.find(pat)
    return i if i >= 0 and text.find(pat, i + 1) < 0 else -1


def _char_index(text, off):
    n = 0
    for i, ch in enumerate(text):
        if n >= off:
            return i if n == off else None
        n += 2 if ord(ch) > 0xFFFF else 1
    return len(text) if n == off else None


def _line_prefix_is_anchor(text, caret, anchor):
    k = _char_index(text, caret) if caret is not None and caret >= 0 else None
    if k is None:
        return False
    prefix = text[:k].replace("\r", "\n").rsplit("\n", 1)[-1]
    return prefix == anchor if len(anchor) < 6 else prefix.endswith(anchor)


def _node_state(old, new, anchor):
    text, caret, why = ia2text.read_node(timeout=0.8)
    if text is None:
        crashlog.log(f"IA2 整段讀不到（{why}）")
        return None, -1, None, caret
    a = anchor if len(anchor) >= 2 else ""
    has_new, has_old = (a + new) in text, (a + old) in text
    if a or len(new) >= 4:
        i = _find_once(text, a + new)
        if i >= 0 and not has_old:
            return "new", i + len(a + new), text, caret
    if a or len(old) >= 4:
        i = _find_once(text, a + old)
        if i >= 0 and not has_new:
            return "old", i + len(a + old), text, caret
    if old and old not in text and new not in text and _line_prefix_is_anchor(text, caret, anchor):
        return "gone", _char_index(text, caret), text, caret
    return None, -1, text, caret


def _recover_by_node(app, old, new, base, anchor):
    st, end, text, caret = _node_state(old, new, anchor)
    if st in ("old", "gone"):
        time.sleep(0.25)
        st2, end2, text, caret = _node_state(old, new, anchor)
        if st2 != st or end2 != end:
            st = st2 if st2 == "new" else None
            end = end2
    if st == "gone":
        mode = "type" if base == "type" else "paste"
        escstop.check()
        crashlog.log(f"IA2 整段：原字被整個吃掉（整段沒有原字也沒有新字，游標停在原字起點）→ 游標處補上新字（{mode}）")
        _emit(new, mode)
        route.note_write(f"ia2+{mode}")
        return True
    if st == "new":
        ia2text.set_caret(ia2text.u16_offset(text, end))
        crashlog.log("IA2 整段：新字已在（游標跑掉）→ 游標放回")
        route.note_write("ia2")
        return True
    if st == "old":
        if ia2text.set_caret(ia2text.u16_offset(text, end)):
            time.sleep(0.05)
            tail, _w = ia2text.read_before_caret(back=len(old) + 4, timeout=0.6)
            if tail is not None and tail.endswith(old):
                crashlog.log(f"IA2 整段：原字還在（游標跑掉）→ 游標放回、改用鍵盤（{base}）重寫")
                write_unit(app, old, new, base)
                if base != "backspace":
                    route.note_write(f"ia2→{base}")
                return True
        crashlog.log("IA2 整段：原字還在，但游標放不回原位 → 不動手")
        return False
    if text is not None:
        k = ia2text._u16len(text) if caret is None or caret < 0 else caret
        crashlog.log(f"IA2 整段也認不出（游標={caret}）：舊={crashlog.q(old)} 新={crashlog.q(new)} 錨點={crashlog.q(anchor)} "
                     f"整段尾 60 字={crashlog.q(text[-60:])} 游標附近={crashlog.q(text[max(0, k - 30):k + 30])}")
    return False


def _ia2_fallback_unit(app, why, old, new, base, anchor):
    touched = why.startswith("寫後驗不過") or why.startswith("逾時")
    if touched:
        time.sleep(0.4)
    state = _state_before(old, new, anchor)
    if touched and state in ("old", "gone"):
        time.sleep(0.25)
        again = _state_before(old, new, anchor)
        if again != state:
            crashlog.log(f"IA2 寫後狀態不穩（{state}→{again}）→ 不換路")
            state = again if again == "new" else None
    crashlog.log(f"IA2 直改沒成功（{why}）→ 自動：現場＝{state or '認不出來'}")
    if state == "new":
        route.note_write("ia2")
        return
    if state == "old":
        write_unit(app, old, new, base)
        if base != "backspace":
            route.note_write(f"ia2→{base}")
        return
    if state == "gone":
        escstop.check()
        _emit(new, "type" if base == "type" else "paste")
        route.note_write(f"ia2+{'type' if base == 'type' else 'paste'}")
        return
    escstop.check()
    if _recover_by_node(app, old, new, base, anchor):
        return
    _ia2_after(app, why, old, new, check_missing=True)


def write_unit_ia2(app, old, new, base=None, anchor="", conv=None):
    if old == new:
        return
    if not _clear_underline(ia2=True):
        app.abort_write("組字中（IA2，探了兩次）")
        return
    why = _ia2_try(lambda: ia2text.replace_before_caret(old, new, timeout=1.2))
    if why and base:
        if conv is not None and _converge_ia2(app, why, old, new, base, conv):
            return
        _ia2_fallback_unit(app, why, old, new, base, anchor)
        return
    _ia2_after(app, why, old, new, check_missing=True)


def write_selection_ia2(app, old, new, base=None):
    if old == new:
        return
    why = _ia2_try(lambda: ia2text.replace_selection(old, new, timeout=1.2))
    if why and base:
        if why.startswith("寫後驗不過") or why.startswith("逾時"):
            time.sleep(0.4)
        sel, _w = ia2text.read_selection(timeout=0.6)
        crashlog.log(f"IA2 反白直改沒成功（{why}）→ 自動：反白{'還是原字' if sel == old else '已變'}")
        if sel == old:
            write_selection(app, old, new, base)
            route.note_write(f"ia2→{base}")
            return
    _ia2_after(app, why, old, new, check_missing=False)


def write_next_ia2(app, old, new, base=None):
    if old == new:
        return
    if not _clear_underline(ia2=True):
        app.abort_write("組字中（IA2，探了兩次）")
        return
    why = _ia2_try(lambda: ia2text.replace_after_caret(old, new, timeout=1.2))
    if why and base:
        if why.startswith("寫後驗不過") or why.startswith("逾時"):
            time.sleep(0.4)
        after, _w = ia2text.read_after_caret(fwd=len(old) + 4, timeout=0.8)
        crashlog.log(f"IA2 後句直改沒成功（{why}）→ 自動：游標後{'還是原字' if after and after.startswith(old) else '已變或讀不到'}")
        if after is not None and after.startswith(old):
            write_next(app, old, new, base)
            route.note_write(f"ia2→{base}")
            return
    _ia2_after(app, why, old, new, check_missing=False)


def write_next(app, old, new, mode):
    n = len if mode == "backspace" else textutil.utf16_len
    win.ntap(win.VK_RIGHT, n(old), iv=0.005)
    time.sleep(settings.sp(0.04))
    write_unit(app, old, new, mode)
    win.ntap(win.VK_LEFT, n(new), iv=0.005)


def delete_unit(app, orig, mode):
    if mode == "backspace":
        for _ in range(len(orig)):
            wk.tap(win.VK_BACK)
            time.sleep(0.01)
        crashlog.log(f"F2 階梯刪字（退格）{len(orig)} 字")
        return True
    if not _select_old(app, orig):
        return False
    wk.tap(win.VK_BACK)
    crashlog.log(f"F2 階梯刪字 {len(orig)} 字")
    return True
