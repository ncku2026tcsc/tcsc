# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/tcsc2026/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import ctypes
import threading
import time

import pystray
from PIL import Image, ImageDraw

from . import autostart, bubble, iconart, notify
from .. import settings, version

_user32 = ctypes.windll.user32
_DBL_S = 0.45
_ICON_KEY = r"Control Panel\NotifyIconSettings"


def _promote_once(exe, key=_ICON_KEY):
    import os
    import winreg
    try:
        root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key)
    except OSError:
        return False
    exe = os.path.normcase(exe)
    with root:
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(root, i)
            except OSError:
                return None
            i += 1
            try:
                with winreg.OpenKey(root, sub, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
                    if os.path.normcase(winreg.QueryValueEx(k, "ExecutablePath")[0]) != exe:
                        continue
                    try:
                        winreg.QueryValueEx(k, "IsPromoted")
                        return False
                    except OSError:
                        winreg.SetValueEx(k, "IsPromoted", 0, winreg.REG_DWORD, 1)
                        return True
            except OSError:
                continue
AUTHOR_EMAIL = "tcsc2026report@gmail.com"


def _dot(color):
    try:
        return iconart.with_dot(64, color)
    except Exception:
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        ImageDraw.Draw(img).ellipse((8, 8, 56, 56), fill=color)
        return img


ICON = {"load": _dot((150, 150, 150)), "ready": _dot((40, 200, 80)),
        "busy": _dot((230, 180, 40)), "pause": _dot((200, 60, 60))}


class Tray:
    def __init__(self, app):
        self.app = app
        self.icon = pystray.Icon("szds", ICON["load"], f"{version.APP_TITLE}（載入中…）",
                                 menu=self.menu())
        self._click_t = 0.0
        self._click_gen = 0
        try:
            bubble.set_menu_provider(lambda: (self.icon, self.menu()))
        except Exception:
            pass

    def set(self, state, title):
        self.icon.icon = ICON[state]
        self.icon.title = f"{version.APP_TITLE}：{title}" if title else version.APP_TITLE

    def refresh(self):
        try:
            self.icon.menu = self.menu()
            self.icon.update_menu()
        except Exception:
            pass

    def menu(self):
        app, M, Menu = self.app, pystray.MenuItem, pystray.Menu
        SEP = Menu.SEPARATOR

        def radio(key, value, label):
            def act(i, it):
                app.set_setting(key, value)

            def chk(it):
                return settings.get(key) == value
            return M(label, act, checked=chk, radio=True)

        def toggle(key, label, after=None):
            def act(i, it):
                app.set_setting(key, not settings.get(key))
                if after:
                    after()

            def chk(it):
                return bool(settings.get(key))
            return M(label, act, checked=chk)

        def pick(fn, key, val, label):
            def act(i, it):
                fn(key, val)

            def chk(it):
                return settings.get(key) == val
            return M(label, act, checked=chk)

        def head(text):
            return M(text, None, enabled=False)

        faces = []
        for gname, keys in bubble._FACE_GROUPS:
            faces.append(M(gname, Menu(*[radio("bubble_face", k, bubble._FACES[k][1]) for k in keys])))
        faces += [SEP, M("自訂顏色…", lambda i, it: app.pick_face_color(),
                         checked=lambda it: settings.get("bubble_face") == "custom", radio=True)]
        notify_menu = Menu(
            radio("notify_style", "bubble", "字旁氣泡"),
            radio("notify_style", "toast", "系統通知"),
            radio("notify_style", "off", "不顯示"),
            SEP,
            M("位置", Menu(
                radio("bubble_pos", "auto", "跟著游標"),
                radio("bubble_pos", "fixed", "釘在拖過去的地方"),
                radio("bubble_pos", "corner", "右下角"),
                radio("bubble_pos", "corner_bl", "左下角"),
                radio("bubble_pos", "corner_tr", "右上角"),
                radio("bubble_pos", "corner_tl", "左上角"),
                SEP,
                M("跟著游標時往哪偏", Menu(
                    M("偏左上", lambda i, it: app.bubble_offset(-1, -1)),
                    M("偏左下", lambda i, it: app.bubble_offset(-1, 1)),
                    M("偏右上", lambda i, it: app.bubble_offset(1, -1)),
                    M("偏右下", lambda i, it: app.bubble_offset(1, 1)),
                    M("不偏", lambda i, it: app.bubble_offset(0, 0)))))),
            M("大小", Menu(*[radio("bubble_size_level", i, n) for i, n in enumerate(("特小", "小", "中", "大", "特大"), 1)])),
            M("停留時間", Menu(*[radio("bubble_hold_level", i, n) for i, n in enumerate(("極短", "短", "中", "長", "超長"), 1)])),
            M("外觀", Menu(*faces)),
            M("算字中的燈號", Menu(*[radio("calc_pulse", k, v) for k, v in notify.PULSE_NAMES.items()])),
            SEP,
            toggle("bubble_pin", "氣泡不自動消失"),
            toggle("bubble_thru", "滑鼠點得穿氣泡"),
            toggle("bubble_arena", "改字窗列出其他候選"),
            toggle("notify_route", "通知顯示改字路線"),
        )

        from ..engine import pronoun

        def unset(key):
            def act(i, it):
                app.toggle_pronoun(key, settings.get(key) or "")

            def chk(it):
                return not settings.get(key)
            return M("不指定", act, checked=chk)
        ni_items = [pick(app.toggle_pronoun, "pron_ni", ch, ch) for ch in pronoun.NI] + [SEP, unset("pron_ni")]
        ta_items = [pick(app.toggle_pronoun, "pron_ta", ch, ch) for ch in pronoun.TA] + [SEP, unset("pron_ta")]
        glyph_items = []
        for key, title, opts in app.GLYPH_UI:
            glyph_items.append(M(title, Menu(*[pick(app.toggle_glyph, key, val, label) for val, label in opts])))
        glyph_items += [SEP, toggle("glyph_bpmf_yi", "ㄧ 改成 一"),
                        toggle("glyph_bpmf_tone", "清掉多餘的聲調記號"),
                        SEP, M("全部不統一", lambda i, it: app.clear_glyph())]

        return Menu(
            head(version.APP_TITLE),
            M("使用說明", Menu(
                M("使用說明", lambda i, it: app.show_help()),
                M("何時用 F1、何時用 F3？", lambda i, it: app.show_f1f3()),
                M("快捷鍵一覽", lambda i, it: app.open_keysheet()),
                M("重看教學", lambda i, it: app.tutorial_first()),
                M("快速移動教學", lambda i, it: app.tutorial_movers()))),
            M("暫停熱鍵（F10）", lambda i, it: app.toggle_hotkeys(),
              checked=lambda it: app.hotkeys_paused()),
            M("開機自動啟動", lambda i, it: app.toggle_autostart(),
              checked=lambda it: autostart.is_enabled()),
            M("建立桌面與開始功能表捷徑", lambda i, it: app.make_shortcuts()),
            SEP,
            M("我的用字", Menu(
                M("你／妳", Menu(*ni_items)),
                M("他／她", Menu(*ta_items)),
                M("字形", Menu(*glyph_items)),
                SEP,
                toggle("det_windows", "F1 找得更廣"),
                toggle("list_court_order", "F1 連按照裁判排"),
                toggle("xuci_key", "F8 換在再", app.rebind_hotkeys),
                toggle("xuci_de", "F8 也換的得地"),
                toggle("pron_key", "Shift+F8 換人稱", app.rebind_hotkeys),
                toggle("pron_rank", "Shift+F8 照通順度排"),
                toggle("pron_f8_rare", "Shift+F8 也換到牠／祂"))),
            M("詞庫", Menu(
                M("查詞（Shift+F5）", lambda i, it: app.open_dictquery()),
                M("我學的詞（Shift+F7）", lambda i, it: app.open_manage()),
                M("常錯字清單（Shift+F6）", lambda i, it: app.open_escort()),
                M("內建詞庫", Menu(lambda: self._pack_items())),
                SEP,
                toggle("f7_direct", "學過的詞優先考慮"),
                toggle("f7_lock", "學滿的詞不讓 F1 改掉"),
                toggle("escort_shipped", "使用內建常錯字"))),
            M("按鍵", Menu(
                M("改鍵…", lambda i, it: app.open_keybinder()),
                M("符號鍵…", lambda i, it: app.open_symbols()),
                SEP,
                toggle("movers_on", "快速移動（Ctrl+Alt+方向鍵）", app.rebind_hotkeys),
                toggle("symkeys_on", "符號鍵（Ctrl+Alt+標點）", app.rebind_hotkeys),
                toggle("enter_unify_on", "統一換行（Ctrl+Enter）", app.rebind_hotkeys),
                toggle("tab_f1", "Tab 當 F1", app.rebind_hotkeys))),
            M("通知與改字窗設定", notify_menu),
            SEP,
            M("改不動的時候", Menu(
                M("放開卡住的按鍵", lambda i, it: app.release_keys()),
                M("重新啟用熱鍵", lambda i, it: app.revive_hotkeys()),
                M("清空剪貼簿", lambda i, it: app.clear_clipboard()),
                SEP,
                M("恢復原廠設定", lambda i, it: app.factory_reset()))),
            M("紀錄與回報", Menu(
                M("匯出給作者", lambda i, it: app.export_for_author()),
                M("寄信給作者", lambda i, it: app.contact()),
                M("GitHub 專案頁", lambda i, it: app.open_github()),
                M(f"檢查更新（目前 {version.VERSION}）", lambda i, it: app.check_update()),
                SEP,
                toggle("log_on", "記錄改不對的句子"),
                toggle("log_detail", "詳細紀錄"),
                M("查看紀錄", Menu(
                    M("改不對的句子", lambda i, it: app.open_errorlog()),
                    M("每次改字", lambda i, it: app.open_history()),
                    M("亂碼轉中文", lambda i, it: app.open_garblelog()),
                    M("診斷紀錄", lambda i, it: app.open_crashlog()),
                    SEP,
                    M("打開紀錄資料夾", lambda i, it: app.open_logdir()))),
                M("清除所有紀錄…", lambda i, it: app.clear_logs()))),
            M("進階", Menu(
                M("抓字方式", Menu(
                    radio("grab_mode", "auto", "自動"),
                    radio("grab_mode", "uia", "直接讀畫面"),
                    radio("grab_mode", "clip", "剪貼簿"),
                    SEP,
                    toggle("ia2_browser", "瀏覽器直接改網頁"))),
                M("寫回方式", Menu(
                    radio("write_mode", "paste", "貼上"),
                    radio("write_mode", "type", "打字"),
                    radio("write_mode", "backspace", "退格重打"))),
                M("符號鍵寫入方式", Menu(
                    radio("sym_write", "follow", "跟寫回方式一樣"),
                    radio("sym_write", "type", "打字"),
                    radio("sym_write", "paste", "貼上"))),
                toggle("term_auto", "終端機自動選方式"),
                toggle("mode_keys", "F4 換寫回方式", app.rebind_hotkeys),
                SEP,
                toggle("auto_verify", "寫完自動檢查"),
                toggle("autokey_refill", "改字時打的字自動補上"),
                toggle("ime_commit", "自動收掉選字底線"),
                toggle("blink_first", "按 F1 先收底線"),
                toggle("blink_alt", "切焦點時先按 Alt"),
                toggle("uia_wake_blink", "讀不到游標先眨一下再讀"),
                toggle("ia2_read_fallback", "瀏覽器讀不到先試 IA2"),
                toggle("sel_fallback_bs", "選不起來改退格重打"),
                SEP,
                toggle("garble_on", "亂碼轉中文"),
                toggle("garble_ime", "亂碼照新注音規則組字"),
                toggle("garble_rerank", "亂碼再比一次整句通順"),
                toggle("garble_single", "亂碼只有一個字也轉"),
                SEP,
                M("Esc", Menu(
                    radio("esc_mode", "single", "按一下就中止改字"),
                    radio("esc_mode", "double", "連按兩下才中止"),
                    radio("esc_mode", "block", "改字時一律擋下"),
                    radio("esc_mode", "off", "不擋"))),
                toggle("f10_stack", "F10 累積暫停"),
                toggle("tray_promote", "圖示固定在工作列"),
                toggle("update_check", "開機時檢查更新"))),
            SEP,
            M("離開", lambda i, it: app.quit()),
        )

    def _pack_items(self):
        M = pystray.MenuItem
        try:
            from ..engine import lexicon
            packs = lexicon.packs()
        except Exception:
            return [M("（詞庫包尚未啟用）", None, enabled=False)]
        if not packs:
            return [M("（沒有詞庫包）", None, enabled=False)]

        def mk(p):
            pid = p["id"]

            def act(i, it):
                self.app.toggle_pack(pid)

            def chk(it):
                return self._pack_on(pid)
            return M(f"{p['date']}　{p['name']}（{p['count']:,}）", act, checked=chk)
        return [mk(p) for p in packs]

    @staticmethod
    def _pack_on(pid):
        try:
            from ..engine import lexicon
            return any(p["id"] == pid and p["enabled"] for p in lexicon.packs())
        except Exception:
            return False

    def hook_clicks(self):
        try:
            from pystray._util import win32 as _pw
            orig = self.icon._message_handlers.get(_pw.WM_NOTIFY)

            def hook(wparam, lparam):
                if lparam == _pw.WM_LBUTTONUP:
                    self._on_click()
                    return
                return orig(wparam, lparam)
            self.icon._message_handlers[_pw.WM_NOTIFY] = hook
        except Exception:
            pass

    def _on_click(self):
        now = time.monotonic()
        last, self._click_t = self._click_t, now
        self._click_gen += 1
        gen = self._click_gen
        if now - last <= _DBL_S:
            self.app.release_keys(from_tray=True)
            return

        def single():
            time.sleep(_DBL_S + 0.05)
            if self._click_gen != gen:
                return
            try:
                from pystray._util import win32 as _pw
                _user32.PostMessageW(self.icon._hwnd, _pw.WM_NOTIFY, 0, _pw.WM_RBUTTONUP)
            except Exception:
                pass
        threading.Thread(target=single, daemon=True).start()

    def promote(self):
        import sys
        if not getattr(sys, "frozen", False) or not settings.get("tray_promote", True):
            return
        for _ in range(20):
            got = _promote_once(sys.executable)
            if got is not None:
                break
            time.sleep(0.5)
        if got:
            try:
                self.icon.visible = False
                time.sleep(0.3)
                self.icon.visible = True
            except Exception:
                pass

    def run(self, setup):
        try:
            _user32.SetThreadDpiAwarenessContext(ctypes.c_ssize_t(-4))
        except Exception:
            pass
        self.hook_clicks()
        self.icon.run(setup=setup)

    def stop(self):
        self.icon.stop()
