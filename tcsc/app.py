# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/tcsc2026/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import ctypes
import gc
import os
import sys
import threading
import time
import webbrowser

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "tcsc"

from . import logbook, settings, version
from .engine import crashlog, escstop
from .keys import enterguard, hotkey, keymap
from .keys.movers import Movers
from .text import clip, grab, route, win, winkeys as wk, write
from .ui import arena, autostart, editfmt, iconart, notify, tray

AUTHOR_EMAIL = "tcsc2026report@gmail.com"
GITHUB_URL = "https://github.com/tcsc2026/tcsc"
TOP_N = 10
DEL_ARM_S = 4.0
PRON_RANK_MAX = 20
OP_KEEPOUT = 0.25


class App:
    def __init__(self):
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                ctypes.c_wchar_p(version.APP_TITLE))
        except Exception:
            pass
        self.corrector = None
        self._busy = False
        self._op_keepout = 0.0
        self._f7_lock = threading.Lock()
        self._f7_run = None
        self._cycle = None
        self._last = None
        self._del_armed = None
        self._last_elogged = None
        self._pending_harvest = None
        self._sf11_last = 0.0
        self._hk = None
        self._sym_lock = threading.Lock()
        self.tray = tray.Tray(self)
        self.notifier = notify.Notifier(self.tray.icon)
        self.movers = Movers(lambda: self._op_gate(stamp=False), tut=self._tut)
        self.actions = {
            "f1": self._on_f1, "f2": self._on_f2, "f3": self._on_f3,
            "f5": self._on_f5, "sf5": self._on_sf5, "f7": self._on_f7, "sf7": self._on_sf7,
            "f10": self._on_f10,
            "f4": self._on_f4, "sf4": self._on_sf4,
            "f8": self._on_f8, "sf8": self._on_sf8, "f9": self._on_f9, "sf9": self._on_sf9,
            "sf1": self._on_sf1, "sf2": self._on_sf2, "sf3": self._on_sf3,
            "sf6": self.open_escort, "sf11": self._on_sf11,
            "tab": self._on_tab,
            "enter_unify": self._on_enter_unify,
            "del:left": lambda: self.movers.on_delete(False),
            "del:right": lambda: self.movers.on_delete(True),
        }
        for vk in (win.VK_LEFT, win.VK_RIGHT, win.VK_UP, win.VK_DOWN):
            self.actions[f"mv:{vk}"] = (lambda v=vk: self.movers.on_move(v))
        self.actions["sym"] = self._on_sym

    def notify(self, msg):
        self.notifier.notify(msg)

    def abort_write(self, why, msg=None):
        crashlog.log(f"寫回中止（{why}）[{win.foreground_process() or '?'}] 票={tuple(route.plan())}")
        self.tray.set("ready", f"就緒（上一次沒寫進去：{why}）")
        self.notify(msg or write.MSG_ABORT_IME)
        self.notifier.mute(1.5)

    def start(self):
        escstop.wire(self.notify,
                     lambda: (win.release_all_mods(),
                              self.notify("已緊急停止——這一輪讀寫作廢（Esc）"
                                          if escstop._mode() == "single" else
                                          "已緊急停止——這一輪讀寫作廢（Esc×2）")),
                     lambda: True)
        self._hk = hotkey.start_hotkeys_thread(self._bindings(), keep_vks=(hotkey.VK_F10,))
        self._hk.rebuild_fn = self._bindings
        self._hk.on_error = crashlog.log
        _eff, problems = keymap.resolve(settings.get)
        if problems:
            threading.Timer(6.0, lambda: self.notify("改鍵設定有問題已回預設：" + "；".join(problems[:3]))).start()
        self.tray.run(setup=self._setup)

    def _bindings(self):
        b = keymap.bindings(self.actions, settings.get)
        for bind in keymap.overridden(settings.get):
            if bind in b:
                b[bind] = self._after_mods_up(b[bind], bind[1])
        return b

    @staticmethod
    def _after_mods_up(cb, mods):
        watch = [vk for bit, vk in ((keymap.CTRL, 0x11), (keymap.ALT, 0x12), (keymap.SHIFT, 0x10)) if mods & bit]

        def go():
            deadline = time.monotonic() + 1.0
            while any(wk.is_down(v) for v in watch) and time.monotonic() < deadline:
                time.sleep(0.01)
            cb()
        return lambda: threading.Thread(target=go, daemon=True).start()

    def _setup(self, icon):
        icon.visible = True
        threading.Thread(target=self.tray.promote, daemon=True).start()
        threading.Thread(target=self._tidy_logs, daemon=True).start()
        upd = threading.Timer(20.0, self._auto_update_check)
        upd.daemon = True
        upd.start()
        threading.Thread(target=self._load_engine, daemon=True).start()
        threading.Thread(target=self._check_hotkeys, daemon=True).start()
        if not settings.get("tutorial_seen"):
            threading.Timer(2.5, self.tutorial_first).start()
        elif not settings.get("firstrun_done"):
            threading.Timer(6.0, self.first_run_setup).start()
        try:
            from .ui import bubble
            threading.Thread(target=bubble.warmup, daemon=True).start()
        except Exception:
            pass

    def _load_engine(self):
        self.tray.set("load", "載入模型中…")
        try:
            from . import engine
            self.corrector = engine.load()
            logbook.ENGINE_DESC = "default"
            engine.warm()
        except Exception as e:
            crashlog.log(f"引擎載入失敗：{e!r}")
            self.tray.set("pause", "引擎載入失敗")
            self.notify(f"引擎載入失敗：{e}")
            return
        self.tray.set("ready", "就緒")
        self.notify("就緒：打完一句按 F1 改字；有進步按 F3 用這句重算，沒進步再按 F1 換下一個，F2 退回。")

    def _check_hotkeys(self):
        def poll():
            for _ in range(40):
                f = getattr(self._hk, "failed_vks", None) if self._hk else None
                if f is not None:
                    return f
                time.sleep(0.1)
            return None
        failed = poll()
        if not failed:
            return
        eff, _ = keymap.resolve(settings.get)
        core = {eff.get(a) for a in ("f1", "f2", "f3")}

        def is_core(k):
            return (k if isinstance(k, tuple) else (k, 0)) in core
        loud = any(is_core(k) for k in failed)
        if loud:
            self.notify("載入熱鍵中，請稍待…")
        for _ in range(6):
            time.sleep(1.0)
            if not self._hk:
                return
            self._hk.failed_vks = None
            self._hk.rebind()
            failed = poll()
            if not failed:
                if loud:
                    self.notify("熱鍵就緒")
                return
        quiet = [k for k in failed if not is_core(k)]
        if quiet:
            crashlog.log("被別的程式佔走（不提醒）：" + "、".join(keymap.bind_label(k, settings.get) for k in quiet))
        core_failed = [k for k in failed if is_core(k)]
        if core_failed:
            names = "、".join(keymap.bind_label(k, settings.get) for k in core_failed)
            self.notify(f"{names} 被別的程式佔走了：關掉那個程式後，按系統匣「改不動的時候」裡的「重新啟用熱鍵」或重開；"
                        "也可以在系統匣「按鍵 → 改鍵…」換一顆。")

    def _op_gate(self, stamp=True):
        now = time.monotonic()
        if self._busy or now < self._op_keepout:
            return True
        if stamp:
            self._op_keepout = now + OP_KEEPOUT
        return False

    def _spawn(self, fn):
        def run():
            self._busy = True
            escstop.begin()
            try:
                with enterguard.guard(refill_keys=bool(settings.get("autokey_refill")),
                                      allow_back=True, log=crashlog.log) as g:
                    fn()
                if g.is_owner and g.blocked:
                    crashlog.log(f"護欄：擋下 {g.blocked} 顆、補回 {g.refilled} 顆、丟 {g.refill_dropped} 顆"
                                 f"{'（' + g.refill_reason + '）' if g.refill_reason else ''}")
            except escstop.EStop:
                pass
            except Exception as e:
                crashlog.log(f"操作炸裂 {type(e).__name__}: {e}")
                self.notify(f"這一下失敗了：{e}")
            finally:
                escstop.end()
                self.notifier.calc_end()
                self._busy = False
        threading.Thread(target=run, daemon=True).start()

    def _route_to_window(self, key):
        try:
            from .ui import dictquery, manageescort, managewords
            fg = win.foreground_hwnd()
            for mod in (managewords, manageescort, dictquery):
                mw = mod.ACTIVE
                if mw and mw.get("q") is not None and fg and fg == mw.get("hwnd"):
                    mw["q"].put(key)
                    return True
        except Exception:
            pass
        return False

    def _on_f1(self):
        if self._route_to_window("f1") or self._op_gate():
            return
        if self.corrector is None:
            self.notify("模型還在載入，請稍候")
            return
        self._spawn(self._do_correct)

    def _do_correct(self):
        if win.ime_candidates_open():
            self.notify("注音選字窗開著——先按 Enter 完成選字，再按 F1")
            return
        if grab.has_selection(self):
            crashlog.log("F1 反白路")
            self._cycle_correct(lambda: grab.read_sel(self), "sel")
            return
        self._cycle_correct(lambda: grab.read_unit(self), "unit")

    def _cycle_correct(self, read_fn, kind, force=False):
        self.notifier.calc_begin()
        try:
            t0 = time.monotonic()
            got = read_fn()
            t_read = time.monotonic() - t0
            if got is None:
                return
            target, writer = got
            syl = grab.take_garble() if kind in ("unit", "sel", "prev", "next") else None
            cyc = self._cycle
            hs = self._cyc_head(cyc, target) if (not force and cyc and cyc["kind"] == kind) else None
            if hs is not None:
                cyc["hist"].append(cyc["list"][cyc["idx"]])
                cyc["idx"] = (cyc["idx"] + 1) % len(cyc["list"])
                nxt = cyc["list"][cyc["idx"]]
                writer(hs[0] + nxt + hs[1])
                self._last = (cyc["orig"], nxt)
                cyc["tries"] += 1
                self._auto_log_problem(cyc)
                self._autofill_gold()
                self._garble_log(cyc, "F1")
                if nxt == cyc["orig"]:
                    self.notify("已回到原句（F1 往前 · F3 用這句重算 · F2 往回）")
                elif cyc.get("garble"):
                    self.notify(f"亂碼轉中文：{nxt}（{cyc['idx'] + 1}/{len(cyc['list']) - 1}）")
                else:
                    self._step_feedback()
                return
            self.notifier.calc_tick("算字中…")
            t1 = time.monotonic()
            ranked = self._ranked_garble(syl) if syl else self._ranked(target)
            t_calc = time.monotonic() - t1
            crashlog.log(f"算字計時 讀={t_read:.2f}s 算={t_calc:.2f}s（{len(target)}字）")
        finally:
            self.notifier.calc_end()
        if syl:
            if not ranked:
                self.notify("這段像是英文模式打的注音，但組不出中文")
                return
            self._flush_harvest(keep_for=target)
            glog = {"engine": logbook._engine_tag(), "ime": bool(settings.get("garble_ime", True)),
                    "before": syl.before, "input": target, "tail": syl.tail, "syllables": syl.syllables,
                    "output": ranked[0], "top": ranked[:5], "t": [round(t_read, 2), round(t_calc, 2)],
                    "route": grab.last_channel(), "tries": 1, "steps": []}
            self._cycle = {"list": ranked + [target], "idx": 0, "orig": target, "kind": kind,
                           "read_fn": read_fn, "hist": [target], "tries": 1, "garble": True, "suffix": syl.tail,
                           "glog": glog, "hwnd": win.foreground_hwnd()}
            self._last = (target, ranked[0])
            writer(ranked[0])
            self._garble_log(self._cycle)
            self.notify(f"亂碼轉中文：{ranked[0]}（F1 換下一個 · F3 用這句重算 · F2 退回，共 {len(ranked)} 個）{route.tail()}")
            return
        best = ranked[0]
        route_ch = grab.last_channel()
        self._flush_harvest(keep_for=target)
        self._cycle = {"list": ranked, "idx": 0, "orig": target, "kind": kind,
                       "read_fn": read_fn, "hist": [target], "tries": 1,
                       "etag": logbook._engine_tag(), "route": route_ch, "grab": kind,
                       "t1st": [round(t_read, 2), round(t_calc, 2)], "hwnd": win.foreground_hwnd()}
        logbook.set_log_ctx(key="F1", tries=self._cycle["tries"], route=route_ch, grab=kind)
        self._last = (target, best)
        bar = ""
        if len(ranked) > 1 and settings.get("bubble_arena", True):
            ar = arena.beat3(target, ranked)[1]
            if ar:
                bar = "｜" + ar
        if best != target:
            writer(best)
            changes = editfmt.diff(target, best)
            try:
                logbook.log_correction(target, best, changes, getattr(self.corrector, "margin", 0.0))
            except Exception:
                pass
            tag = "重算" if force else "已修正"
            self.notify(f"{tag}：{editfmt.fmt_edits(changes)}（F1 換下一個 · F3 用這句重算 · F2 退回，共 {len(ranked)} 個）{bar}{route.tail()}")
        elif force:
            self.notify(f"目前沒有可再修的同音字：{target}{bar}")
        elif len(ranked) > 1:
            self.notify(f"未發現需修正（再按 F1 看其他候選，共 {len(ranked)} 個；選字底線還在的話先按 Enter）{bar}{route.tail()}")
        else:
            self._cycle = None
            self.notify(f"未發現需修正的同音字：{target}{grab.MSG_ENTER}{route.tail()}")

    def _step_feedback(self):
        cyc = self._cycle
        if not cyc:
            return
        cur = cyc["list"][cyc["idx"]]
        others = [c for c in cyc["list"] if c != cyc["orig"]]
        no = (others.index(cur) + 1) if cur in others else (cyc["idx"] + 1)
        diff = editfmt.diff(cyc["orig"], cur)
        self.notifier.bubble_only(f"{editfmt.fmt_edits(diff)}（{no}/{len(others)}）", "ok")

    def _on_f2(self):
        if self._route_to_window("f2") or self._op_gate():
            return
        if not self._cycle_here():
            self._pass_key("f2")
            return
        self._spawn(self._do_back)

    def _cycle_here(self):
        cyc = self._cycle
        return bool(cyc and cyc.get("list") and cyc.get("hwnd") == win.foreground_hwnd())

    @staticmethod
    def _cyc_head(cyc, target):
        if not cyc or not cyc.get("list"):
            return None
        cur = cyc["list"][cyc["idx"]]
        if target == cur:
            return "", ""
        if cyc.get("garble") and cur:
            tail = cyc.get("suffix", "")
            if tail and target.endswith(cur + tail):
                return target[:len(target) - len(cur + tail)], tail
            if target.endswith(cur):
                return target[:len(target) - len(cur)], ""
        return None

    def _do_back(self):
        cyc = self._cycle
        if not cyc or not cyc.get("list"):
            self.notify("沒有上一步可退——先用 F1 改字，才有得退")
            return
        got = cyc["read_fn"]()
        if got is None:
            return
        target, writer = got
        hs = self._cyc_head(cyc, target)
        if hs is None:
            return
        hist = cyc["hist"]
        if not hist:
            self._del_ladder(cyc, target)
            return
        prv = hist.pop()
        writer(hs[0] + prv + hs[1])
        self._last = (cyc["orig"], prv)
        try:
            cyc["idx"] = cyc["list"].index(prv)
        except ValueError:
            pass
        cyc["tries"] += 1
        self._auto_log_problem(cyc)
        self._autofill_gold()
        self._garble_log(cyc, "F2")
        if prv == cyc["orig"]:
            self.notify("已回到原句（F1 往前換候選）")
        else:
            self._step_feedback()

    def _del_ladder(self, cyc, target):
        orig = cyc["orig"]
        now = time.time()
        armed = self._del_armed
        if not (armed and armed[0] == orig and now - armed[1] <= DEL_ARM_S):
            self._del_armed = (orig, now)
            self.notify(f"已回到原句。再按一次 F2 會刪掉這 {len(orig)} 個字")
            return
        self._del_armed = None
        if target != orig:
            self.notify("這裡已經不是剛剛那句了，沒有刪")
            return
        if write.delete_unit(self, orig, route.plan().write):
            self._cycle = None
            self.notify(f"已刪掉「{orig[:12]}{'…' if len(orig) > 12 else ''}」")

    def _on_f3(self):
        if self._route_to_window("f3") or self._op_gate():
            return
        if self.corrector is None:
            return
        self._spawn(self._do_recorrect)

    def _do_recorrect(self):
        cyc = self._cycle
        orig0 = cyc["orig"] if cyc else None
        hist0 = list(cyc["hist"]) if cyc else []
        tries0 = cyc["tries"] if cyc else 0
        garbled = bool(cyc and cyc.get("garble"))
        if garbled:
            self._garble_log(cyc, "F3")
            orig0, hist0, tries0 = None, [], 0
        if cyc:
            self._auto_log_problem(cyc)
        if cyc and cyc.get("read_fn") and not garbled:
            self._cycle_correct(cyc["read_fn"], cyc["kind"], force=True)
        else:
            self._cycle_correct(lambda: grab.read_unit(self, garble_ok=False), "unit", force=True)
        if self._cycle and orig0:
            self._cycle["orig"] = orig0
            if orig0 not in self._cycle["list"]:
                self._cycle["list"].append(orig0)
            self._cycle["hist"] = hist0 + self._cycle["hist"]
            self._cycle["tries"] = tries0 + 1
            self._autofill_gold()

    def _garble_log(self, cyc, key=None, gold=None):
        rec = cyc.get("glog") if cyc else None
        if rec is None:
            return
        try:
            if key:
                rec["steps"].append(key)
                rec["tries"] = cyc.get("tries")
                rec["final"] = cyc["list"][cyc["idx"]]
            if gold:
                rec["gold"], rec["gold_src"] = gold, "manual"
            logbook.log_garble(rec)
        except Exception as e:
            crashlog.log(f"亂碼紀錄寫入失敗 {e!r}")

    def _auto_log_problem(self, cyc):
        prob = cyc.get("orig")
        if not prob or prob == self._last_elogged or cyc.get("kind") in ("pron", "xuci") or cyc.get("garble"):
            return
        try:
            logbook.log_error_case(prob, cyc["list"][0], engine=cyc.get("etag"),
                                   route=cyc.get("route"), grab=cyc.get("grab"),
                                   t_first=cyc.get("t1st"))
            self._last_elogged = prob
        except Exception:
            pass

    def _autofill_gold(self):
        if not self._last_elogged:
            return
        cyc = self._cycle
        if not (cyc and cyc.get("list")) or cyc.get("kind") in ("pron", "xuci") or cyc.get("garble"):
            return
        try:
            gold = cyc["list"][cyc["idx"]]
            logbook.append_correct_answer(gold, src="auto", tries=cyc.get("tries"),
                                          engine=cyc.get("etag"), route=cyc.get("route"),
                                          grab=cyc.get("grab"), problem=cyc.get("orig"))
            if settings.get("escort_harvest_auto"):
                self._pending_harvest = {"gold": gold, "orig": cyc.get("orig"),
                                         "court": getattr(self.corrector, "last_court", None)}
        except Exception:
            pass

    def _maybe_escort_harvest(self, correct, court_snap=None, problem=None):
        mode = settings.get("escort_harvest") or "off"
        crashlog.log(f"收割敲門 gold={crashlog.q(correct)} mode={mode}")
        if mode == "off" or logbook._dev_mode():
            return ""
        from .engine import escort
        if problem is not None:
            rec = logbook.case_for_input(problem)
            if rec is None:
                crashlog.log(f"收割：找不到原句相同的難例（{crashlog.q(problem[:20])}），不收不退")
                return ""
        else:
            rec = logbook.case_matching(correct) or {}
        inp = (rec.get("input") or "").strip()
        correct = (correct or "").strip()
        court = None
        lc = court_snap or getattr(self.corrector, "last_court", None)
        if lc and lc[0] == inp:
            court = lc[1]
        try:
            if rec.get("ts"):
                escort.remove_by_tag(rec["ts"])
        except Exception:
            pass
        try:
            added = escort.harvest(inp, correct, mode, court, tag=rec.get("ts"))
        except Exception as e:
            crashlog.log(f"收割炸裂 案={rec.get('ts')} {type(e).__name__}: {e}")
            return ""
        crashlog.log(f"收割 案={rec.get('ts')} inp={crashlog.q(inp)} gold={crashlog.q(correct)} mode={mode} "
                     f"名冊={'同案%d人' % len(court) if court else '無'} 收={crashlog.q('、'.join(added)) if added else '空'}")
        if not added:
            return ""
        return "；🎫 自動保送：" + "、".join(added) + "（正解不在候選圈；Shift+F6 可管理）"

    def _flush_harvest(self, keep_for=None):
        pend = self._pending_harvest
        if not pend:
            return
        if keep_for and keep_for in (pend.get("orig"), pend.get("gold")):
            return
        self._pending_harvest = None
        if not pend.get("gold") or (pend.get("orig") and pend["gold"] == pend["orig"]):
            return
        try:
            tail = self._maybe_escort_harvest(pend["gold"], court_snap=pend.get("court"), problem=pend.get("orig"))
            if tail:
                crashlog.log("auto-gold 定稿" + tail.lstrip("；"))
        except Exception:
            pass

    def open_escort(self):
        def go():
            from .ui import manageescort
            try:
                manageescort.open_manage_window(self.notify, correct_fn=self._correct_fn)
            except Exception as e:
                self.notify(f"常錯字清單視窗錯誤：{e}")
            finally:
                gc.collect()
        threading.Thread(target=go, daemon=True).start()

    def _on_sf11(self):
        now = time.monotonic()
        last, self._sf11_last = self._sf11_last, now
        if now - last <= 1.5:
            on = not (settings.get("dev_mode") and time.time() < float(settings.get("dev_mode_until") or 0))
            settings.set("dev_mode", on)
            if on:
                until = time.time() + 180.0
                settings.set("dev_mode_until", until)

                def expire(u=until):
                    if settings.get("dev_mode") and abs(float(settings.get("dev_mode_until") or 0) - u) < 1.0:
                        settings.set("dev_mode", False)
                        self.notify("開發者模式到時（3 分鐘）自動關閉——恢復記錄")
                t = threading.Timer(180.5, expire)
                t.daemon = True
                t.start()
            self.notify("已進入開發者模式（3 分鐘後自動關閉）——改字不記 error_cases／history；"
                        "再雙擊 Shift+F11 提前退出" if on else "已退出開發者模式——恢復記錄")
            return
        dev = ("｜開發者模式（不記錄）" if settings.get("dev_mode")
               and time.time() < float(settings.get("dev_mode_until") or 0) else "")
        self.notify(f"版本 {version.LABEL}{dev}")

    _WRITE_CYCLE = (("paste", "貼上"), ("type", "打字"), ("backspace", "退格重打"))
    _GRAB_CYCLE = (("auto", "自動"), ("uia", "直接讀畫面"), ("clip", "剪貼簿"))

    def _on_f4(self):
        self._next_mode("write_mode", self._WRITE_CYCLE, "寫回方式", "F4")

    def _on_sf4(self):
        self._next_mode("grab_mode", self._GRAB_CYCLE, "抓字方式", "Shift+F4")

    def _next_mode(self, key, cycle, name, hk):
        vals = [v for v, _ in cycle]
        cur = settings.get(key)
        i = (vals.index(cur) + 1) % len(vals) if cur in vals else 0
        settings.set(key, vals[i])
        self.notify(f"{name}：{cycle[i][1]}（再按 {hk} 換下一種）")

    def _on_f8(self):
        if self._route_to_window("f8") or self._op_gate():
            return
        self._spawn(self._do_xuci)

    def _on_sf8(self):
        if self._route_to_window("sf8") or self._op_gate():
            return
        self._spawn(self._do_pron)

    def _do_pron(self):
        from .engine import pronoun

        def ranked(t):
            alts = pronoun.variants(t, rare=bool(settings.get("pron_f8_rare")))
            if not settings.get("pron_rank", True):
                return alts
            return self._by_fluency(alts[:PRON_RANK_MAX], "人稱") + alts[PRON_RANK_MAX:]
        self._rule_cycle("pron", "人稱", "Shift+F8", "這句沒有可以換的人稱（你／妳、他／她／它）", ranked)

    def _by_fluency(self, alts, what):
        c = self.corrector
        if c is None or len(alts) < 2:
            return alts
        try:
            return sorted(alts, key=lambda s: -c._cond_pll(s))
        except Exception as e:
            crashlog.log(f"{what}：排序失敗，照原順序 {e!r}")
            return alts

    def _do_xuci(self):
        from .engine import xuci
        de = bool(settings.get("xuci_de"))
        groups = xuci.GROUPS if de else xuci.ZAI
        name = "的得地／在再" if de else "在再"

        def ranked(t):
            return self._by_fluency(xuci.variants(t, groups), name)
        self._rule_cycle("xuci", name, "F8", "這句沒有可以換的" + ("的得地、在再" if de else "在、再"), ranked)

    def _rule_cycle(self, kind, name, hk, empty_msg, make_alts):
        if win.ime_candidates_open():
            self.notify(f"注音選字窗開著——先按 Enter 完成選字，再按 {hk}")
            return
        sel = grab.has_selection(self)
        read_fn = (lambda: grab.read_sel(self)) if sel else (lambda: grab.read_unit(self))
        got = read_fn()
        if got is None:
            return
        target, writer = got
        cyc = self._cycle
        if cyc and cyc["kind"] == kind and target == cyc["list"][cyc["idx"]]:
            cyc["hist"].append(target)
            cyc["idx"] = (cyc["idx"] + 1) % len(cyc["list"])
        else:
            alts = make_alts(target)
            if not alts:
                self.notify(empty_msg)
                return
            self._flush_harvest(keep_for=target)
            self._cycle = cyc = {"list": alts + [target], "idx": 0, "orig": target, "kind": kind,
                                 "read_fn": read_fn, "hist": [target], "tries": 1, "hwnd": win.foreground_hwnd()}
        nxt = cyc["list"][cyc["idx"]]
        writer(nxt)
        self._last = (cyc["orig"], nxt)
        n = len(cyc["list"]) - 1
        if nxt == cyc["orig"]:
            self.notify(f"{name}：已回到原句（{hk} 往前 · F2 往回）")
            return
        diff = editfmt.diff(cyc["orig"], nxt)
        self.notify(f"{name}：{editfmt.fmt_edits(diff)}（{cyc['idx'] + 1}/{n}，{hk} 換下一個 · F2 退回）")

    def _on_f9(self):
        if self._op_gate(stamp=False):
            return
        if not self._cycle_here():
            self._pass_key("f9")
            return
        threading.Thread(target=self._do_record_correct, daemon=True).start()

    def _do_record_correct(self):
        cyc = self._cycle
        if not cyc:
            self.notify("先按 F1 改字，再按 F9 記正解")
            return
        got = cyc["read_fn"]()
        if got is None:
            return
        correct, problem = got[0], cyc.get("orig")
        if cyc.get("garble"):
            self._garble_log(cyc, "F9", gold=correct)
            self.notify(f"已記正解（亂碼轉中文）：{correct}")
            return
        if problem and problem != correct:
            try:
                first = cyc["list"][0] if cyc.get("list") else problem
                logbook.upsert_error_case(problem, first, correct, "manual", cyc.get("tries"),
                                          engine=cyc.get("etag"), route=cyc.get("route"),
                                          grab=cyc.get("grab"), t_first=cyc.get("t1st"))
            except Exception:
                pass
        self._pending_harvest = None
        self.notify(f"已記正解：{correct}" + self._maybe_escort_harvest(correct, problem=problem))

    def _on_sf9(self):
        if self._op_gate(stamp=False):
            return
        rec = logbook.remove_last_error()
        if not rec:
            self.notify("難例清單是空的——沒有可移除的紀錄")
            return
        self._last_elogged = None
        inp = (rec.get("input") or rec.get("raw") or "")[:24]
        gold = (rec.get("gold") or "")[:24]
        out = (rec.get("output") or "")[:24]
        from .engine import escort
        pulled = escort.remove_by_tag(rec.get("ts"))
        self.notify("🗑 已移除上一筆難例：" + inp
                    + (f" ⇒ gold「{gold}」" if gold else (f"（引擎改成「{out}」、未補 gold）" if out else ""))
                    + (f"；連動退票：{'、'.join(pulled)}" if pulled else ""))

    def open_errorlog(self):
        self._open_log_file(logbook.ERROR_FILE)

    def open_history(self):
        self._open_log_file(logbook.LOG_FILE)

    def open_garblelog(self):
        self._open_log_file(logbook.GARBLE_FILE)

    def open_crashlog(self):
        self._open_log_file(crashlog._FILE)

    def open_logdir(self):
        try:
            os.makedirs(logbook.LOG_DIR, exist_ok=True)
            os.startfile(logbook.LOG_DIR)
        except Exception as e:
            self.notify(f"開啟失敗：{e}")

    _VIEW_DIR = os.path.join(os.environ.get("TEMP") or os.path.expanduser("~"), "tcsc_view")

    def _open_log_file(self, path):
        import subprocess
        try:
            os.makedirs(self._VIEW_DIR, exist_ok=True)
            out = os.path.join(self._VIEW_DIR, os.path.basename(path) + ".txt")
            if path == crashlog._FILE:
                try:
                    with open(path, encoding="utf-8", errors="replace") as f:
                        text = "\n".join(crashlog.unseal_line(ln) for ln in f)
                except OSError:
                    text = ""
            else:
                text = "\n".join(logbook._read(path))
            with open(out, "w", encoding="utf-8-sig") as f:
                f.write(text or "（目前沒有紀錄）")
            subprocess.Popen(["notepad.exe", out])
        except Exception as e:
            self.notify(f"開啟失敗：{e}")

    def _clean_view(self):
        try:
            for n in os.listdir(self._VIEW_DIR):
                try:
                    os.remove(os.path.join(self._VIEW_DIR, n))
                except OSError:
                    pass
        except OSError:
            pass

    def _tidy_logs(self):
        self._clean_view()
        try:
            res = logbook.migrate()
            crashlog.log(f"紀錄整理：{res}")
        except Exception as e:
            crashlog.log(f"紀錄整理失敗 {e!r}")

    def export_for_author(self):
        import datetime as _dt
        import subprocess
        desk = os.path.join(os.path.expanduser("~"), "Desktop")
        out = os.path.join(desk if os.path.isdir(desk) else os.path.expanduser("~"),
                           f"算字大師_回報給作者_{_dt.date.today():%Y%m%d}.txt")
        try:
            n = logbook.export_for_author(out)
            subprocess.Popen(["notepad.exe", out])
            self.notify(f"已匯出 {n} 筆到桌面：先看過、刪掉不想給的，再寄到 {AUTHOR_EMAIL}")
        except Exception as e:
            self.notify(f"匯出失敗：{e}")

    def clear_logs(self):
        def go():
            if ctypes.windll.user32.MessageBoxW(
                    None, "要刪掉所有改字紀錄嗎？\n（改字史、難例、亂碼紀錄、診斷紀錄；學的詞與設定不受影響，刪了不能復原）",
                    version.APP_TITLE, 0x4 | 0x30 | 0x40000) != 6:
                return
            n = logbook.clear_all()
            crashlog.clear()
            self.notify(f"已清除所有紀錄（{n} 個紀錄檔＋診斷紀錄）")
        threading.Thread(target=go, daemon=True).start()

    def _on_sf1(self):
        if self._route_to_window("sf1") or self._op_gate() or self.corrector is None:
            return
        self._spawn(self._do_correct_prev)

    def _do_correct_prev(self):
        wk.wait_mods_up()
        self._cycle_correct(lambda: grab.read_prev_unit(self), "prev")

    def _on_sf3(self):
        if self._route_to_window("sf3") or self._op_gate() or self.corrector is None:
            return
        self._spawn(self._do_correct_next)

    def _do_correct_next(self):
        wk.wait_mods_up()
        self._cycle_correct(lambda: grab.read_next_unit(self), "next")

    def _on_sf2(self):
        if self._route_to_window("sf2") or self._op_gate():
            return
        self._spawn(self._do_restore)

    def _do_restore(self):
        cyc = self._cycle
        if not cyc or not cyc.get("list"):
            self.notify("沒有可還原的——先用 F1 改字，Shift+F2 才有原句可回")
            return
        wk.wait_mods_up()
        got = cyc["read_fn"]()
        if got is None:
            return
        target, writer = got
        if target != cyc["list"][cyc["idx"]]:
            return
        orig = cyc["orig"]
        if target == orig:
            self.notify("這句已是原句（F1 往前換候選）")
            return
        cyc["hist"].append(target)
        writer(orig)
        self._last = (orig, orig)
        try:
            cyc["idx"] = cyc["list"].index(orig)
        except ValueError:
            cyc["list"].append(orig)
            cyc["idx"] = len(cyc["list"]) - 1
        self.notify("已回到原句（F2 可退回剛剛的改法）")

    def _on_f5(self):
        if self._op_gate(stamp=False):
            return
        threading.Thread(target=self._do_f5, daemon=True).start()

    def _pass_key(self, action):
        bind = keymap.resolve(settings.get)[0].get(action)
        if self._hk and bind:
            self._hk.key_pass(*bind)

    def _do_f5(self):
        from .engine import wordphon
        word = grab.grab_word(self, maxlen=8)
        if word == "":
            self._pass_key("f5")
            return
        if not word:
            return
        if word in wordphon.commonwords():
            self.notify(f"「{word}」已經在常識詞庫裡了（Shift+F5 可查）")
            return
        seqs, _lv = self._choose_reading(word, "收")
        if not seqs:
            return
        if wordphon.add_commonword(word, seqs):
            self._cycle = None
            rivals = [w for w in wordphon.words_by_reading(tuple(seqs[0])) if w != word][:4]
            tail = ("　同音詞：" + "／".join(rivals)) if rivals else "　（唯一同音詞）"
            self.notify(f"📗 收進常識詞庫：{word}　{' ／ '.join(' '.join(s) for s in seqs)}{tail}")
        else:
            self.notify(f"「{word}」本來就收過了")

    def _choose_reading(self, word, verb, level=None):
        from .engine import addword
        combos = addword.reading_combos(word)
        if not combos:
            self.notify(f"「{word}」含沒有注音的字（英數／emoji），{verb}不了")
            return [], None
        if len(combos) == 1:
            return combos, level
        from .ui import pickreading
        try:
            seqs, lv = pickreading.pick(word, combos, verb, level=level)
        finally:
            gc.collect()
        if not seqs:
            self.notify(f"沒有{verb}「{word}」（取消了）")
        return seqs, lv

    def _on_sf5(self):
        def go():
            self.open_dictquery(self._selected_text())
        threading.Thread(target=go, daemon=True).start()

    def _selected_text(self):
        try:
            fgp = win.foreground_process()
            if fgp not in win.CONSOLES and wk.wait_mods_up():
                if fgp in win.UIA_DEAF or grab.selprobe.probe() == grab.selprobe.SEL:
                    sel = clip.selection_text(False, timeout=0.35 if fgp in win.UIA_DEAF else 0.9)
                    if sel:
                        return sel.rstrip("\r\n").strip() or None
        except Exception:
            pass
        return None

    def open_dictquery(self, initial=None):
        def go():
            from .ui import dictquery
            try:
                dictquery.open_query_window(self.notify, correct_fn=self._correct_fn, initial=initial,
                                            reload_fn=self.reload_readings)
            except Exception as e:
                self.notify(f"詞庫查詢視窗錯誤：{e}")
            finally:
                gc.collect()
        threading.Thread(target=go, daemon=True).start()

    def _on_f7(self):
        if self._op_gate(stamp=False):
            return
        with self._f7_lock:
            if self._f7_run is not None:
                self._f7_run["more"] += 1
                return
            self._f7_run = run = {"more": 0}
        threading.Thread(target=self._do_f7, args=(run,), daemon=True).start()

    def _do_f7(self, run):
        try:
            self._learn_selected(run)
        finally:
            with self._f7_lock:
                self._f7_run = None

    def _learn_selected(self, run):
        from .engine import userdict, wordphon
        word = grab.grab_word(self, maxlen=8, copy_browser=True)
        if word == "":
            self.notify("先反白要學的詞，再按 F7")
            return
        if not word:
            return
        seqs = lv = None
        if not userdict.seqs_of(word):
            seqs, lv = self._choose_reading(word, "學", level=1)
            if not seqs:
                return
            run["more"] = 0
        status, level, msg = userdict.learn(word, seqs, lv)
        while status == "ok":
            with self._f7_lock:
                if not run["more"]:
                    break
                run["more"] -= 1
            st2, lv2, _msg2 = userdict.learn(word)
            if st2 != "ok":
                break
            level = lv2
        if status == "ok":
            wordphon.reload_userforce()
            self._cycle = None
            self.notify(f"📘 學起來了：{word}（強度 {level}／{userdict.cap_for(word)}）　再按一次加強・Shift+F7 管理")
        else:
            self.notify(msg or f"「{word}」學不了")

    def _on_sf7(self):
        def go():
            self.open_manage(self._selected_text())
        threading.Thread(target=go, daemon=True).start()

    def open_manage(self, initial=None):
        def go():
            from .ui import managewords
            try:
                managewords.open_manage_window(self.notify, correct_fn=self._correct_fn, initial=initial)
            except Exception as e:
                self.notify(f"管理視窗錯誤：{e}")
            finally:
                gc.collect()
        threading.Thread(target=go, daemon=True).start()

    def _correct_fn(self, text):
        return self._ranked(text) if self.corrector is not None else [text]

    _GLYPH_KEYS = ("glyph_tai", "glyph_li", "glyph_shen", "glyph_bu", "glyph_chi", "glyph_kaoyao")

    def _ranked_garble(self, g, top_n=TOP_N):
        from .engine import garble
        cands = garble.compose(g)
        if not cands:
            return []
        pool = list(cands)
        tmpl = g.template()
        try:
            pool += [c for c in self.corrector.ranked_corrections(cands[0], top_n=top_n)
                     if c not in pool and garble.consistent(c, tmpl)]
        except Exception as e:
            crashlog.log(f"亂碼轉中文：引擎補候選失敗 {e!r}")
        try:
            sc = self.corrector._court_scores(cands[0], pool)
            pool.sort(key=lambda c: -sc.get(c, -1e9))
        except Exception as e:
            crashlog.log(f"亂碼轉中文：裁判排序失敗，照詞庫順序 {e!r}")
        if settings.get("garble_rerank", True):
            try:
                head = pool[:5]
                pll = {c: self.corrector._cond_pll(c) for c in head}
                pool = sorted(head, key=lambda c: -pll[c]) + pool[5:]
            except Exception as e:
                crashlog.log(f"亂碼轉中文：通順度複審失敗，照裁判順序 {e!r}")
        pool = [c for c in pool if self._in_vocab(c)] + [c for c in pool if not self._in_vocab(c)]
        return [g.respace(c) for c in self._prefer(pool)[:top_n]]

    def _in_vocab(self, text):
        bert = getattr(self.corrector, "judge", None) or getattr(self.corrector, "bert", None)
        if bert is None:
            return True
        return all(ch.isascii() or bert.token_id(ch) is not None for ch in text)

    SINGLE_GAIN = 1.0

    def _single_garble_ok(self, line, g):
        from .engine import garble, wordphon
        c = self.corrector
        if c is None:
            return False
        try:
            freq = lambda x: wordphon._freq.get("".join(ch for ch in x if not ch.isascii()), 0)
            cands = sorted((x for x in garble.compose(g, k=60) if self._in_vocab(x)), key=freq, reverse=True)[:8]
            if not cands:
                return False
            head, tail = line[max(0, g.start - 30):g.start], g.tail[:15]

            def mean(s):
                return c._cond_pll(s) / max(1, len(s))
            base = mean(head + line[g.start:g.end] + tail)
            return max(mean(head + x + tail) for x in cands) - base >= self.SINGLE_GAIN
        except Exception as e:
            crashlog.log(f"亂碼轉中文：單一音節判斷失敗，不轉 {e!r}")
            return False

    def _ranked(self, text, top_n=TOP_N):
        from .engine import glyphpref, pronoun
        fixed = text
        if settings.get("glyph_bpmf_yi", True):
            fixed = glyphpref.fix_bpmf_yi(fixed)
        if settings.get("glyph_bpmf_tone", True):
            fixed = glyphpref.fix_bpmf_tone(fixed)
        self.corrector._pre_normalized = (fixed != text)
        ranked = self.corrector.ranked_corrections(fixed, top_n=top_n)
        return self._prefer(ranked)

    def _prefer(self, ranked):
        from .engine import glyphpref, pronoun
        p = {k: settings.get(k) or "" for k in self._GLYPH_KEYS}
        ni, ta = settings.get("pron_ni") or "", settings.get("pron_ta") or ""

        def prefer(cands, fn):
            out, seen = [], set()
            for c in cands:
                m = fn(c)
                if m not in seen:
                    seen.add(m)
                    out.append(m)
            for c in cands:
                if c not in seen:
                    seen.add(c)
                    out.append(c)
            return out
        if ni or ta:
            ranked = prefer(ranked, lambda c: pronoun.apply_pref(c, ni, ta))
        if any(p.values()):
            ranked = prefer(ranked, lambda c: glyphpref.apply_pref(
                c, tai=p["glyph_tai"], li=p["glyph_li"], shen=p["glyph_shen"],
                bu=p["glyph_bu"], chi=p["glyph_chi"], words=p))
        return ranked

    def _on_sym(self, out):
        if self._op_gate(stamp=False):
            return
        threading.Thread(target=self._sym_paste, args=(out,), daemon=True).start()

    @staticmethod
    def _sym_mode():
        m = settings.get("sym_write") or "paste"
        if m in ("type", "paste"):
            return m
        return "type" if settings.get("write_mode") == "type" else "paste"

    def _sym_paste(self, out):
        if self._sym_mode() == "type":
            try:
                st = win.mods_hold()
                try:
                    wk.type_text(out)
                finally:
                    win.mods_release(st)
            except Exception:
                pass
            return
        with self._sym_lock:
            try:
                pre = clip.get_clip()
                if not clip.set_clip_confirm(out):
                    clip.set_clip(pre)
                    return
                st = win.mods_hold()
                try:
                    wk.combo(wk.VK_CONTROL, wk.VK_V)
                finally:
                    win.mods_release(st)
                time.sleep(0.20)
                clip.set_clip(pre)
            except Exception:
                pass

    def _tut(self, ev):
        try:
            from .ui import tutorial
            tutorial.notify(ev)
        except Exception:
            pass

    def tutorial_first(self):
        from .ui import tutorial
        tutorial.start(self._tutorial_warmup, on_close=self._after_tutorial)

    def _after_tutorial(self):
        if not settings.get("firstrun_done"):
            self.first_run_setup()

    def first_run_setup(self):
        if getattr(sys, "frozen", False) and os.path.exists(os.path.join(os.path.dirname(sys.executable), "unins000.exe")):
            settings.set("firstrun_done", True)
            return

        def go():
            from .ui import firstrun
            try:
                firstrun.ask(self.notify)
            except Exception as e:
                crashlog.log(f"第一次設定窗錯誤：{e!r}")
            finally:
                gc.collect()
        threading.Thread(target=go, daemon=True).start()

    def make_shortcuts(self):
        from .ui import firstrun
        ok = firstrun.make_shortcuts(True, True)
        self.notify("建立好了：桌面捷徑、開始功能表" if ok else "建立捷徑失敗")

    def tutorial_movers(self):
        from .ui import tutorial
        tutorial.start_movers()

    def _tutorial_warmup(self):
        try:
            if self.corrector is not None:
                self.corrector.ranked_corrections("先暖個身")
        except Exception:
            pass

    def _on_tab(self):
        if win.foreground_process() in win.CONSOLES or win.is_own_foreground():
            if self._hk:
                self._hk.key_pass(keymap.VK_TAB)
            return
        self._on_f1()

    def reload_readings(self):
        done = threading.Event()

        def go():
            t0 = time.monotonic()
            while self._busy and time.monotonic() - t0 < 10:
                time.sleep(0.1)
            self._busy = True
            try:
                from .engine import lexicon, phonetics, reading_filter
                phonetics.reload()
                reading_filter._weights = None
                reading_filter._active_cache.clear()
                lexicon.reload_all()
                self.notify("讀音設定已套用")
            except Exception as e:
                crashlog.log(f"讀音重載失敗：{e!r}")
                self.notify(f"讀音設定套用失敗：{e}")
            finally:
                self._busy = False
                done.set()
        threading.Thread(target=go, daemon=True).start()
        return done

    def open_symbols(self):
        def go():
            from .ui import managesym
            try:
                managesym.open_manager(self.rebind_hotkeys, self.notify)
            except Exception as e:
                crashlog.log(f"符號鍵管理窗錯誤：{e!r}")
                self.notify(f"符號鍵管理窗錯誤：{e}")
            finally:
                gc.collect()
        threading.Thread(target=go, daemon=True).start()

    def open_keybinder(self):
        def go():
            from .keys import keybinder
            try:
                keybinder.open_binder(self.rebind_hotkeys, self.notify)
            except Exception as e:
                self.notify(f"改鍵窗錯誤：{e}")
            finally:
                gc.collect()
                self.tray.refresh()
        threading.Thread(target=go, daemon=True).start()

    def _on_enter_unify(self):
        threading.Thread(target=self._enter_burst, daemon=True).start()

    def _enter_burst(self):
        want_ctrl = win.foreground_process() in win.CONSOLES
        hk = self._hk
        did = False
        if hk is not None and not hk.paused:
            hk.pause()
            did = True
        ctl, sh = wk.is_down(win.VK_CONTROL), wk.is_down(win.VK_SHIFT)
        if ctl:
            wk.key(win.VK_CONTROL, up=True)
        if sh:
            wk.key(win.VK_SHIFT, up=True)
        try:
            wk.combo(win.VK_CONTROL if want_ctrl else win.VK_SHIFT, keymap.VK_RETURN)
            time.sleep(0.01)
        finally:
            if sh:
                wk.key(win.VK_SHIFT)
            if ctl:
                wk.key(win.VK_CONTROL)
            if did:
                time.sleep(0.03)
                hk.resume()

    PAUSE_STEPS = (15, 30)

    def _on_f10(self):
        if not self._hk:
            return
        if not settings.get("f10_stack", True):
            self.toggle_hotkeys()
            return
        lvl = getattr(self, "_pause_lvl", 0)
        if self._hk.paused and (lvl == 0 or lvl > len(self.PAUSE_STEPS)):
            self._resume_hotkeys("熱鍵已恢復")
            return
        lvl += 1
        self._pause_lvl = lvl
        self._pause_gen = getattr(self, "_pause_gen", 0) + 1
        gen = self._pause_gen
        self._hk.pause()
        if lvl <= len(self.PAUSE_STEPS):
            sec = self.PAUSE_STEPS[lvl - 1]
            t = threading.Timer(sec, lambda: self._pause_expire(gen, sec))
            t.daemon = True
            t.start()
            self.tray.set("pause", f"熱鍵暫停 {sec} 秒")
            more = "再按 F10＝30 秒、按三下＝永久" if lvl == 1 else "再按 F10＝永久暫停"
            self.notify(f"熱鍵暫停 {sec} 秒：F 鍵先還給目前的程式（{more}）")
        else:
            self.tray.set("pause", "熱鍵已暫停（F10 或選單恢復）")
            self.notify("熱鍵永久暫停：再按 F10 或從選單恢復")
        self.tray.refresh()

    def _pause_expire(self, gen, sec):
        if gen == getattr(self, "_pause_gen", 0) and 0 < getattr(self, "_pause_lvl", 0) <= len(self.PAUSE_STEPS):
            self._resume_hotkeys(f"熱鍵已恢復（暫停 {sec} 秒到了）")

    def _resume_hotkeys(self, msg):
        self._pause_lvl = 0
        self._pause_gen = getattr(self, "_pause_gen", 0) + 1
        if self._hk:
            self._hk.resume()
        self.tray.set("ready", "就緒（熱鍵已恢復）")
        self.notify(msg)
        self.tray.refresh()

    def toggle_hotkeys(self):
        if not self._hk:
            return
        if self._hk.paused:
            self._resume_hotkeys("熱鍵已恢復")
            return
        self._pause_lvl = len(self.PAUSE_STEPS) + 1
        self._pause_gen = getattr(self, "_pause_gen", 0) + 1
        self._hk.pause()
        threading.Thread(target=self._pause_ui, daemon=True).start()

    def _pause_ui(self):
        if self._hk.paused:
            self.tray.set("pause", "熱鍵已暫停（F10 或選單恢復）")
            self.notify("熱鍵已暫停：F 鍵交還給目前的程式；再按 F10 恢復")
        else:
            self.tray.set("ready", "就緒（熱鍵已恢復）")
            self.notify("熱鍵已恢復")
        self.tray.refresh()

    def hotkeys_paused(self):
        return bool(self._hk and self._hk.paused)

    def rebind_hotkeys(self):
        if self._hk:
            self._hk.rebind()

    def revive_hotkeys(self):
        hk = self._hk
        t = getattr(hk, "thread", None)
        if hk is not None and t is not None and t.is_alive():
            hk.paused = False
            hk.rebind()
            self.notify("已重新啟用熱鍵")
            return
        crashlog.log("熱鍵復活：迴圈緒已死＝重生新迴圈")
        self._hk = hotkey.start_hotkeys_thread(self._bindings(), keep_vks=(hotkey.VK_F10,))
        self._hk.rebuild_fn = self._bindings
        self._hk.on_error = crashlog.log
        self.notify("熱鍵原本停掉了，已重新啟動")

    GLYPH_UI = [("glyph_tai", "台／臺", (("台", "台"), ("臺", "臺"))),
                ("glyph_li", "裡／裏", (("裡", "裡"), ("裏", "裏"))),
                ("glyph_shen", "什麼／甚麼", (("什", "什麼"), ("甚", "甚麼"))),
                ("glyph_bu", "布／佈", (("布", "布"), ("佈", "佈"))),
                ("glyph_chi", "痴／癡", (("痴", "痴"), ("癡", "癡"))),
                ("glyph_kaoyao", "靠夭／靠腰",
                 (("靠夭", "靠夭"), ("靠腰", "靠腰"), ("靠么", "靠么"), ("靠邀", "靠邀")))]

    def toggle_glyph(self, key, val):
        settings.set(key, "" if settings.get(key) == val else val)
        self.tray.refresh()
        state = "、".join(f"{t.split('／')[0]}→{settings.get(k) or '不動'}" for k, t, _ in self.GLYPH_UI[:5])
        self.notify(f"字形統一：{state}｜ㄧ→一 {'開' if settings.get('glyph_bpmf_yi') else '關'}")

    def clear_glyph(self):
        for k, _t, _o in self.GLYPH_UI:
            settings.set(k, "")
        self.tray.refresh()
        self.notify("字形統一：變體全部不動")

    def toggle_pronoun(self, key, ch):
        settings.set(key, "" if settings.get(key) == ch else ch)
        self.tray.refresh()
        self.notify(f"人稱用字：你→{settings.get('pron_ni') or '不指定'}、他→{settings.get('pron_ta') or '不指定'}")

    def clear_pronoun(self):
        settings.set("pron_ni", "")
        settings.set("pron_ta", "")
        self.tray.refresh()
        self.notify("人稱用字：都不指定")

    def bubble_offset(self, dx, dy):
        if dx == 0 and dy == 0:
            settings.set("bubble_off_x", 0)
            settings.set("bubble_off_y", 0)
            self.notify("氣泡偏移已歸零")
            return
        ox = max(-400, min(int(settings.get("bubble_off_x") or 0) + dx * 40, 400))
        oy = max(-400, min(int(settings.get("bubble_off_y") or 0) + dy * 40, 400))
        settings.set("bubble_off_x", ox)
        settings.set("bubble_off_y", oy)
        self.notify(f"氣泡偏移 → 橫 {ox:+d}、直 {oy:+d}（再點可加大）")

    def pick_face_color(self):
        def run():
            try:
                import tkinter as tk
                from tkinter import colorchooser
                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                init = settings.get("bubble_face_custom") or "#8B5CF6"
                col = colorchooser.askcolor(color=init, title="氣泡底色", parent=root)[1]
                root.destroy()
            except Exception:
                col = None
            root = None
            gc.collect()
            if not col:
                return
            settings.set("bubble_face_custom", col)
            settings.set("bubble_face", "custom")
            self.tray.refresh()
            self.notify(f"氣泡外觀：自訂 {col}")
        threading.Thread(target=run, daemon=True).start()

    def open_keysheet(self):
        def go():
            from .ui import keysheet
            try:
                keysheet.open_keysheet()
            except Exception as e:
                self.notify(f"快捷鍵表視窗錯誤：{e}")
            finally:
                gc.collect()
        threading.Thread(target=go, daemon=True).start()

    def factory_reset(self):
        def go():
            if ctypes.windll.user32.MessageBoxW(
                    None, "要把所有設定恢復成原廠嗎？\n你學的詞、常錯字清單和紀錄都不會動。",
                    version.APP_TITLE, 0x4 | 0x20 | 0x40000) != 6:
                return
            settings.reset()
            self.rebind_hotkeys()
            self.tray.refresh()
            self.notify("已恢復原廠設定。你學的詞、常錯字清單和紀錄都沒動")
        threading.Thread(target=go, daemon=True).start()

    def set_setting(self, key, value):
        settings.set(key, value)
        self.tray.refresh()
        label = {"grab_mode": {"auto": "抓字方式：自動。讀不到或寫不進去時，會自己換別的方法",
                               "uia": "抓字方式：直接讀畫面。讀不到就停下來告訴你，不換方法",
                               "clip": "抓字方式：剪貼簿。最多程式能用，稍慢一點"},
                 "ia2_browser": {True: "瀏覽器直接改網頁：開。只影響瀏覽器，其他程式照抓字方式",
                                 False: "瀏覽器直接改網頁：關"},
                 "write_mode": {"paste": "寫回方式：貼上。大部分程式都能用，也能貼換行",
                                "type": "寫回方式：打字。不經過剪貼簿，擋貼上的網站用這個",
                                "backspace": "寫回方式：退格重打。終端機這種不能選取取代的地方用"},
                 "sym_write": {"follow": "符號鍵寫入方式：跟寫回方式一樣",
                               "type": "符號鍵寫入方式：打字", "paste": "符號鍵寫入方式：貼上"},
                 "auto_verify": {True: "寫完自動檢查：開。寫完會讀回畫面，不對就自己重寫到對",
                                 False: "寫完自動檢查：關"},
                 "notify_route": {True: "通知顯示改字路線：開。通知最後會標這次怎麼抓字、怎麼寫回，回報問題時有用",
                                  False: "通知顯示改字路線：關"},
                 "uia_wake_blink": {True: "讀不到游標先眨一下再讀：開。網頁說找不到游標時，焦點離開再回來，游標掛上後再讀",
                                    False: "讀不到游標先眨一下再讀：關。找不到游標就直接換別的讀法"},
                 "ia2_read_fallback": {True: "瀏覽器讀不到先試 IA2：開。瀏覽器裡直接讀不到字時，先用 IA2 讀，最後才用剪貼簿",
                                       False: "瀏覽器讀不到先試 IA2：關。讀不到就直接用剪貼簿"},
                 "sel_fallback_bs": {True: "選不起來改退格重打：開。要換掉的字選不起來時，確認游標前是原字，改成退格刪掉再寫",
                                     False: "選不起來改退格重打：關。選不起來就停手，一個字都不動"},
                 "ime_commit": {True: "自動收掉選字底線：開。選字底線還沒收就按 F1，程式會先讓輸入法收掉再改",
                                False: "自動收掉選字底線：關。要先按 Enter 收掉底線，再按 F1"},
                 "autokey_refill": {True: "改字時打的字自動補上：開。改字那一兩秒按的鍵，改完照順序補回去",
                                    False: "改字時打的字自動補上：關。改字時按的鍵會被擋掉"},
                 "garble_ime": {True: "亂碼照新注音規則組字：開。打反、打重的注音，照新注音的方式組",
                                False: "亂碼照新注音規則組字：關。注音要照順序打才認得"},
                 "garble_rerank": {True: "亂碼再比一次整句通順：開。比較準，每次多約 0.3 秒",
                                   False: "亂碼再比一次整句通順：關。比較快"},
                 "garble_single": {True: "亂碼只有一個字也轉：開。結尾只有一個字的注音（例：請假vup4）也轉；要算字按 F3，轉錯按 F2 退回",
                                   False: "亂碼只有一個字也轉：關。至少要兩個字的亂碼才轉"},
                 "garble_on": {True: "亂碼轉中文：開。忘了切注音打出 1u3bj6 這種，按 F1 轉成中文",
                               False: "亂碼轉中文：關"},
                 "mode_keys": {True: "F4 換寫回方式：開。F4 換寫回方式，Shift+F4 換抓字方式",
                               False: "F4 換寫回方式：關。F4 還給原本的程式"},
                 "xuci_key": {True: "F8 換在再：開。句子裡的 在、再 照通順度依序換",
                              False: "F8 換在再：關。F8 還給原本的程式"},
                 "xuci_de": {True: "F8 也換的得地：開。F8 連 的、得、地 一起換", False: "F8 也換的得地：關。F8 只換 在、再"},
                 "pron_key": {True: "Shift+F8 換人稱：開。你／妳、他／她／它 依序換", False: "Shift+F8 換人稱：關。Shift+F8 還給原本的程式"},
                 "log_on": {True: "記錄改不對的句子：開。加密存在這台電腦，只有你的 Windows 帳號打得開，保留 30 天",
                            False: "記錄改不對的句子：關。之後不再記，已經記的要刪請按「清除所有紀錄」"},
                 "log_detail": {True: "詳細紀錄：開。每次改字都記，匯出給作者時一起帶。一樣加密，保留 30 天",
                                False: "詳細紀錄：關。只記改不對的句子"},
                 "update_check": {True: "開機時檢查更新：開。一天最多問一次 GitHub 最新版號，不送任何本機資料",
                                  False: "開機時檢查更新：關。要看新版，按「紀錄與回報」裡的檢查更新"},
                 "tray_promote": {True: "圖示固定在工作列：開。新版本第一次開時，圖示直接放在工作列",
                                  False: "圖示固定在工作列：關。照 Windows 預設收在 ^ 裡"},
                 "escort_shipped": {True: "使用內建常錯字：開。內建的常錯字詞跟你自己加的一起用",
                                    False: "使用內建常錯字：關。只用你自己加的"},
                 "list_court_order": {True: "F1 連按照裁判排：開。第 4 下以後也照裁判的分數排，裁判看好的候選不會被擠到後面",
                                      False: "F1 連按照裁判排：關。只有裁判前 3 名保證排在前面，之後照舊的順序"},
                 "det_windows": {True: "F1 找得更廣：開。可疑的字一個一個分開重找，兩個字連錯（件為→鍵位）也找得到，每次多約 0.1 秒",
                                 False: "F1 找得更廣：關。照舊的找法，快約 0.1 秒"},
                 "f7_lock": {True: "學滿的詞不讓 F1 改掉：開。F7 強度到 20 的詞，F1 不會去改它",
                             False: "學滿的詞不讓 F1 改掉：關。學滿的詞也只是很難被改"},
                 "f7_direct": {True: "學過的詞優先考慮：開。F7 學過的詞，讀音對得上就一定列入考慮",
                               False: "學過的詞優先考慮：關。學過的詞要先通過初步篩選"},
                 "pron_rank": {True: "Shift+F8 照通順度排：開。最像的人稱組合先換（我媽說他→她）",
                               False: "Shift+F8 照通順度排：關。照固定順序逐一換"},
                 "pron_f8_rare": {True: "Shift+F8 也換到牠／祂：開", False: "Shift+F8 也換到牠／祂：關。只在 他／她／它 之間換"},
                 "f10_stack": {True: "F10 累積暫停：開。按一下暫停 15 秒、兩下 30 秒、三下一直暫停",
                               False: "F10 累積暫停：關。按一下暫停，再按一下恢復"},
                 "term_auto": {True: "終端機自動選方式：開。在終端機裡自動用最合適的抓字和寫回方式",
                               False: "終端機自動選方式：關。終端機也照你選的方式"},
                 "esc_mode": {"single": "Esc：按一下就中止改字",
                              "double": "Esc：連按兩下才中止，第一下會提醒",
                              "block": "Esc：改字時一律擋下，避免誤按",
                              "off": "Esc：不擋，照常給程式"},
                 "bubble_pin": {True: "氣泡不自動消失：開。新訊息會在同一個氣泡更新", False: "氣泡不自動消失：關。看完自動淡出"},
                 "bubble_arena": {True: "改字窗列出其他候選：開。改字窗後面會列出這一格的其他候選字",
                                  False: "改字窗列出其他候選：關。改字窗只寫改了什麼"},
                 "bubble_thru": {True: "滑鼠點得穿氣泡：開。點擊會穿過氣泡，不能拖曳和按右鍵，下一個氣泡起生效",
                                 False: "滑鼠點得穿氣泡：關。氣泡可以拖曳、按右鍵"},
                 "calc_pulse": {k: f"算字中的燈號：{v}，下次算字生效" for k, v in notify.PULSE_NAMES.items()},
                 "bubble_pos": {"auto": "氣泡位置：跟著游標", "fixed": "氣泡位置：釘在拖過去的地方",
                                "corner": "氣泡位置：右下角", "corner_bl": "氣泡位置：左下角",
                                "corner_tr": "氣泡位置：右上角", "corner_tl": "氣泡位置：左上角"},
                 "bubble_hold_level": {i: f"氣泡停留時間：{n}" for i, n in enumerate(("極短", "短", "中", "長", "超長"), 1)},
                 "bubble_size_level": {i: f"氣泡大小：{n}" for i, n in enumerate(("特小", "小", "中", "大", "特大"), 1)},
                 "bubble_face": {k: f"氣泡外觀：{v[1]}" for k, v in self._faces().items()},
                 "glyph_bpmf_yi": {True: "ㄧ 改成 一：開", False: "ㄧ 改成 一：關"},
                 "glyph_bpmf_tone": {True: "清掉多餘的聲調記號：開。前後沒有注音符號的 ˊˇˋ˙ 會在改字時一起拿掉",
                                     False: "清掉多餘的聲調記號：關"},
                 "notify_style": {"bubble": "通知方式：字旁氣泡", "toast": "通知方式：系統通知", "off": "通知方式：不顯示"},
                 "movers_on": {True: "快速移動：開。Ctrl+Alt+方向鍵移動游標", False: "快速移動：關。Ctrl+Alt+方向鍵還給原本的程式"},
                 "symkeys_on": {True: "符號鍵：開。Ctrl+Alt+[ ] 打「」，9 0 打（），其他看快捷鍵一覽", False: "符號鍵：關"},
                 "enter_unify_on": {True: "統一換行：開。Ctrl+Enter、Shift+Enter 在哪都是換行、不送出",
                                    False: "統一換行：關。這兩個組合鍵還給原本的程式"},
                 "tab_f1": {True: "Tab 當 F1：開。這句怪怪的就按 Tab；終端機和本程式的視窗裡還是原本的 Tab",
                            False: "Tab 當 F1：關。Tab 還給原本的程式"}}
        msg = label.get(key, {}).get(value)
        if msg and not (key == "notify_style" and value == "off"):
            self.notify(msg)

    @staticmethod
    def _faces():
        try:
            from .ui import bubble
            return bubble._FACES
        except Exception:
            return {}

    def toggle_pack(self, pid):
        def go():
            try:
                from .engine import lexicon
                on = lexicon.set_pack_enabled(pid, not any(
                    p["id"] == pid and p["enabled"] for p in lexicon.packs()))
                self.notify(f"詞庫包「{pid}」{'已載入' if on else '已卸下'}")
            except Exception as e:
                self.notify(f"切換詞庫包失敗：{e}")
            self.tray.refresh()
        threading.Thread(target=go, daemon=True).start()

    def toggle_autostart(self):
        try:
            on = autostart.toggle()
            self.notify("開機自動啟動：已設定（下次開機自動常駐系統匣）" if on else "開機自動啟動：已取消")
        except Exception as e:
            self.notify(f"開機自動啟動設定失敗：{e}")
        self.tray.refresh()

    def release_keys(self, from_tray=False):
        win.release_all_mods()
        self.notify("已釋放所有按鍵（Ctrl／Alt／Shift／Win）"
                    + ("。開選單＝單擊圖示就好，不要雙擊" if from_tray else "——剛剛卡死的話現在應該恢復了"))

    def clear_clipboard(self):
        clip.set_clip("")
        self.notify("已清空剪貼簿（若剛剛貼上卡到怪內容，這樣可即時救援）")

    def show_help(self):
        from .ui.usage import USAGE_TEXT
        threading.Thread(target=lambda: ctypes.windll.user32.MessageBoxW(
            0, USAGE_TEXT, f"{version.APP_TITLE} — 使用說明", 0x40), daemon=True).start()

    def show_f1f3(self):
        from .ui.usage import F1F3_TEXT
        threading.Thread(target=lambda: ctypes.windll.user32.MessageBoxW(
            0, F1F3_TEXT, f"{version.APP_TITLE} — 何時用 F1、何時用 F3", 0x40), daemon=True).start()

    def _auto_update_check(self):
        from . import update
        if not update.due():
            return
        got = update.latest()
        if got is None:
            return
        update.mark()
        if update.newer(got[0]):
            self._update_url = got[1]
            self.notify(f"有新版 {got[0]}（目前 {version.VERSION}）：系統匣「檢查更新」開下載頁")

    def check_update(self):
        def go():
            from . import update
            self.notify("檢查更新中…")
            got = update.latest()
            if got is None:
                self.notify("連不上 GitHub，稍後再試")
                return
            update.mark()
            if update.newer(got[0]):
                self.notify(f"有新版 {got[0]}（目前 {version.VERSION}）：已開下載頁，下載安裝程式直接裝")
                try:
                    webbrowser.open(got[1])
                except Exception:
                    pass
            else:
                self.notify(f"已經是最新版（{version.VERSION}）")
        threading.Thread(target=go, daemon=True).start()

    def open_github(self):
        try:
            webbrowser.open(GITHUB_URL)
        except Exception:
            pass
        self.notify("已開啟 GitHub 專案頁")

    def contact(self):
        clip.set_clip(AUTHOR_EMAIL)
        try:
            webbrowser.open(f"mailto:{AUTHOR_EMAIL}")
        except Exception:
            pass
        self.notify(f"作者信箱已複製：{AUTHOR_EMAIL}")

    def quit(self):
        self._clean_view()
        self.tray.stop()


def main():
    gc.disable()
    crashlog.install()
    iconart.install_tk()
    App().start()


if __name__ == "__main__":
    main()
