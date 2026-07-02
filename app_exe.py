# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""繁中自動選字 — 獨立 exe 進入點（ONNX 引擎，無 torch）。由開發版本鏈 app_exe→v32 攤平而成（行為逐字相同）。"""


# ===== app_exe =====
# -*- coding: utf-8 -*-
"""繁中自動選字 — 獨立 exe 進入點（onnxruntime 引擎，無 torch/transformers）。

整合 tray v11+v12 的全部行為：換行視窗抓取、終端機略過、F1 修正/再按換候選、
F2 標記錯誤、自訂通知標題、聯繫作者選單。引擎用 csc.select_corrector_onnx.OnnxCorrector。
模型/字表路徑支援 PyInstaller 打包（sys._MEIPASS）。
"""
import ctypes
import os
import sys
import threading
import time
import webbrowser
from ctypes import wintypes

import pystray
from PIL import Image, ImageDraw

from csc import logbook, winkeys as wk, hotkey
from csc.select_corrector_onnx import OnnxCorrector
from csc.version import VERSION

APP_TITLE = f"繁中自動選字 {VERSION}"   # 版本號取自 csc/version.py 單一來源；通知標題/tray tooltip/說明標題共用
APP_AUMID = "ZhuyinAutoFix.v2_3"       # 內部通知識別碼（不顯示給使用者），維持不變以免通知重新註冊
AUTHOR_EMAIL = "ncku2026tcsc@gmail.com"
SENTINEL = "\x00__zfix__\x00"
VK_LEFT, VK_RIGHT = 0x25, 0x27
GRAB_CHARS = 50
_DELIM = "，。！？；：、,.!?;:　 \t\n"
_CONSOLES = {"powershell.exe", "pwsh.exe", "cmd.exe", "windowsterminal.exe",
             "conhost.exe", "openconsole.exe", "wt.exe", "mobaxterm.exe",
             "wezterm-gui.exe", "alacritty.exe", "putty.exe", "kitty.exe",
             "windowsterminalpreview.exe"}

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32


def _res(*parts):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def _icon(color):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((8, 8, 56, 56), fill=color)
    return img


ICON_LOAD = _icon((150, 150, 150))
ICON_READY = _icon((40, 200, 80))
ICON_BUSY = _icon((230, 180, 40))


def _split_unit(line):
    idx = -1
    for ch in _DELIM:
        p = line.rfind(ch)
        if p > idx:
            idx = p
    return line[:idx + 1], line[idx + 1:]


def _foreground_process():
    try:
        hwnd = _user32.GetForegroundWindow()
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        h = _kernel32.OpenProcess(0x1000, False, pid.value)
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(512)
            size = wintypes.DWORD(512)
            if _kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return buf.value.rsplit("\\", 1)[-1].lower()
        finally:
            _kernel32.CloseHandle(h)
    except Exception:
        pass
    return ""


class _App0:
    def __init__(self):
        try:
            _user32  # noqa
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                ctypes.c_wchar_p(APP_TITLE))
        except Exception:
            pass
        self.corrector = None
        self._busy = False
        self._last = None
        self._cycle = None
        self.icon = pystray.Icon(
            "zhuyin_fix", ICON_LOAD, f"{APP_TITLE}（載入中…）",
            menu=pystray.Menu(
                pystray.MenuItem("重新載入詞庫加權 (custom_boost.txt)", self._reload_boost),
                pystray.MenuItem(f"聯繫作者：{AUTHOR_EMAIL}", self._contact),
                pystray.MenuItem("離開", self._quit),
            ),
        )

    # ---- 狀態 ----
    def _set(self, img, title):
        self.icon.icon = img
        self.icon.title = title

    def _notify(self, msg):
        try:
            self.icon.notify(msg, APP_TITLE)
        except Exception:
            pass

    def start(self):
        threading.Thread(target=self._load_model, daemon=True).start()
        hotkey.start_hotkeys_thread({hotkey.VK_F1: self._on_f1, hotkey.VK_F2: self._on_f2})
        self.icon.run()

    def _load_model(self):
        self.corrector = OnnxCorrector(_res("models", "bert.int8.onnx"),
                                       _res("models", "vocab.txt"))
        self._set(ICON_READY, f"{APP_TITLE}：就緒（F1 修正/再按換下一個 · F2 標記）")
        self._notify("就緒：F1 修正、再按 F1 換候選")

    def _reload_boost(self, *_):
        if self.corrector:
            self.corrector._boost = self.corrector._load_boost()
        self._notify("已重新載入詞庫加權")

    def _contact(self, *_):
        self._set_clip(AUTHOR_EMAIL)
        try:
            webbrowser.open(f"mailto:{AUTHOR_EMAIL}")
        except Exception:
            pass
        self._notify(f"作者信箱已複製：{AUTHOR_EMAIL}")

    def _quit(self, *_):
        self.icon.stop()

    # ---- 抓取/取代 ----
    def _grab_window(self):
        original = self._get_clip()
        self._set_clip(SENTINEL)
        time.sleep(0.06)
        wk.key(wk.VK_SHIFT)
        for _ in range(GRAB_CHARS):
            wk.tap(VK_LEFT)
        wk.key(wk.VK_SHIFT, up=True)
        time.sleep(0.05)
        wk.combo(wk.VK_CONTROL, wk.VK_C)
        time.sleep(0.22)
        window = self._get_clip()
        self._set_clip(original)
        wk.tap(VK_RIGHT)
        if window == SENTINEL or not window or not window.strip():
            return None
        return window

    def _replace_tail(self, cur_unit, new_unit):
        wk.key(wk.VK_SHIFT)
        for _ in range(len(cur_unit)):
            wk.tap(VK_LEFT)
        wk.key(wk.VK_SHIFT, up=True)
        time.sleep(0.03)
        wk.type_text(new_unit)

    # ---- 熱鍵 ----
    def _on_f1(self):
        if self.corrector is None or self._busy:
            return
        threading.Thread(target=self._run, args=(self._do_correct,), daemon=True).start()

    def _on_f2(self):
        if self._busy:
            return
        threading.Thread(target=self._run, args=(self._do_mark_wrong,), daemon=True).start()

    def _run(self, fn):
        self._busy = True
        self._set(ICON_BUSY, f"{APP_TITLE}：處理中…")
        try:
            fn()
        except Exception as e:
            self._notify(f"發生錯誤：{e}")
        finally:
            self._set(ICON_READY, f"{APP_TITLE}：就緒（F1 修正 / F2 標記）")
            self._busy = False

    def _do_correct(self):
        if _foreground_process() in _CONSOLES:
            self._notify("終端機不支援，請在一般輸入欄使用")
            return
        time.sleep(0.08)
        window = self._grab_window()
        if window is None:
            self._notify("沒抓到文字（換個輸入欄試試）")
            return
        _, sent = _split_unit(window)
        if not sent.strip():
            self._notify("沒抓到要修的句子")
            return
        cyc = self._cycle
        if cyc and sent == cyc["list"][cyc["idx"]]:
            cyc["idx"] = (cyc["idx"] + 1) % len(cyc["list"])
            nxt = cyc["list"][cyc["idx"]]
            self._replace_tail(sent, nxt)
            self._last = (cyc["list"][-1], nxt)
            n, total = cyc["idx"] + 1, len(cyc["list"])
            tag = "原句(還原)" if cyc["idx"] == total - 1 else f"第 {n}/{total} 個"
            self._notify(f"換成 {tag}：{nxt}")
            return
        ranked = self.corrector.ranked_corrections(sent)
        self._cycle = {"list": ranked, "idx": 0}
        self._last = (sent, ranked[0])
        if ranked[0] != sent:
            self._replace_tail(sent, ranked[0])
            changes = [(i, a, b) for i, (a, b) in enumerate(zip(sent, ranked[0])) if a != b]
            logbook.log_correction(sent, ranked[0], changes, self.corrector.margin)
            edits = "、".join(f"{a}→{b}" for _, a, b in changes)
            self._notify(f"已修正：{edits}（不滿意再按 F1 換，共 {len(ranked)} 個）")
        elif len(ranked) > 1:
            self._notify(f"未發現錯字（再按 F1 看其他候選，共 {len(ranked)} 個）")
        else:
            self._cycle = None
            self._notify(f"未發現需修正的同音字：{sent}")

    def _do_mark_wrong(self):
        if not self._last:
            self._notify("沒有可標記的上一筆")
            return
        sent, model_out = self._last
        gold = None
        if _foreground_process() not in _CONSOLES:
            window = self._grab_window()
            if window:
                _, gold_seg = _split_unit(window)
                if gold_seg and gold_seg != model_out:
                    gold = gold_seg
        analysis = logbook.log_annotation(sent, model_out, "wrong", gold)
        self._last = None
        self._cycle = None
        if gold and analysis:
            fp = len(analysis.get("false_positive", []))
            ms = len(analysis.get("missed", []))
            wc = len(analysis.get("wrong_correction", []))
            self._notify(f"已記錄錯誤+正解（誤改{fp}/漏改{ms}/改錯{wc}）")
        else:
            self._notify("已記錄上一筆為錯誤")

    @staticmethod
    def _get_clip():
        import pyperclip
        try:
            return pyperclip.paste()
        except Exception:
            return ""

    @staticmethod
    def _set_clip(text):
        import pyperclip
        try:
            pyperclip.copy(text if text is not None else "")
        except Exception:
            pass


# ===== app_exe_v2 =====
# -*- coding: utf-8 -*-
"""繁中自動選字 — 獨立 exe 進入點 v2（onnxruntime 引擎，無 torch/transformers）。

相對 app_exe（v1）：
  - start() 改用 pystray 的 setup 回呼啟動模型載入：就緒通知保證在系統匣圖示
    可用之後才跳（ONNX 模型載入很快，v1 的就緒通知早於 icon.run 被系統吞掉）。
  - _do_correct 的循環分支：中間候選**安靜**（只換欄位文字 + 圖示已閃黃→綠），
    只有「轉一圈回原句」時跳一次「已還原為原句」。
其餘行為（換行視窗抓取、終端機略過、F2 標記、自訂標題、聯繫作者）全沿用 v1。
PyInstaller 進入點（ZhuyinFix.spec）改指向本檔。
"""
import threading
import time

from csc import logbook, hotkey


class _App1(_App0):
    def start(self):
        hotkey.start_hotkeys_thread({hotkey.VK_F1: self._on_f1, hotkey.VK_F2: self._on_f2})
        self.icon.run(setup=self._setup)

    def _setup(self, icon):
        icon.visible = True
        threading.Thread(target=self._load_model, daemon=True).start()

    def _do_correct(self):
        if _foreground_process() in _CONSOLES:
            self._notify("終端機不支援，請在一般輸入欄使用")
            return
        time.sleep(0.08)
        window = self._grab_window()
        if window is None:
            self._notify("沒抓到文字（換個輸入欄試試）")
            return
        _, sent = _split_unit(window)
        if not sent.strip():
            self._notify("沒抓到要修的句子")
            return

        cyc = self._cycle
        if cyc and sent == cyc["list"][cyc["idx"]]:        # 再按 F1 → 下一個候選
            cyc["idx"] = (cyc["idx"] + 1) % len(cyc["list"])
            nxt = cyc["list"][cyc["idx"]]
            self._replace_tail(sent, nxt)
            self._last = (cyc["orig"], nxt)
            if nxt == cyc["orig"]:                         # 轉一圈回原句 → 提醒一次
                self._notify("已還原為原句")
            return                                          # 中間候選：安靜（只換文字）

        ranked = self.corrector.ranked_corrections(sent)
        self._cycle = {"list": ranked, "idx": 0, "orig": sent}
        self._last = (sent, ranked[0])
        if ranked[0] != sent:
            self._replace_tail(sent, ranked[0])
            changes = [(i, a, b) for i, (a, b) in enumerate(zip(sent, ranked[0])) if a != b]
            logbook.log_correction(sent, ranked[0], changes, self.corrector.margin)
            edits = "、".join(f"{a}→{b}" for _, a, b in changes)
            self._notify(f"已修正：{edits}（不滿意再按 F1 換，共 {len(ranked)} 個）")
        elif len(ranked) > 1:
            self._notify(f"未發現錯字（再按 F1 看其他候選，共 {len(ranked)} 個）")
        else:
            self._cycle = None
            self._notify(f"未發現需修正的同音字：{sent}")


# ===== app_exe_v3 =====
# -*- coding: utf-8 -*-
"""繁中自動選字 — 獨立 exe 進入點 v3 = v2 + F3「反白手動修正」模式。

F1（自動）：往回抓視窗、切最後一個單位、就地修正/循環——適合一般輸入欄。
F3（手動）：你**自己反白**要修的字（任何 app，含終端機）→ 修正整段：
  - 一般 app：把修正結果**貼上取代反白**（Ctrl+V，保留全形標點、不怕 IME 吃字）。
  - 終端機：Ctrl+C 在終端機是中斷、且反白的是螢幕字非命令緩衝，無法安全打回，
    故改用 Ctrl+Shift+C 讀取 → 修正 → 放回剪貼簿，通知你自己 Ctrl+Shift+V 貼上。
F3 會把整段（含多個標點分句）逐句修正、保留所有標點/空白。
PyInstaller 進入點（ZhuyinFix.spec）改指向本檔。
"""
import re
import threading
import time

from csc import logbook, winkeys as wk, hotkey

_SPLIT = re.compile(r"([，。！？；：、,.!?;:　 \t\n]+)")


class _App2(_App1):
    def start(self):
        hotkey.start_hotkeys_thread({
            hotkey.VK_F1: self._on_f1,
            hotkey.VK_F2: self._on_f2,
            hotkey.VK_F3: self._on_f3,
        })
        self.icon.run(setup=self._setup)

    def _on_f3(self):
        if self.corrector is None or self._busy:
            return
        threading.Thread(target=self._run, args=(self._do_correct_selection,), daemon=True).start()

    def _correct_selection_text(self, sel: str) -> str:
        """逐句修正：標點/空白原樣保留，只修中間的子句（每句取最佳候選）。"""
        out = []
        for i, part in enumerate(_SPLIT.split(sel)):
            if i % 2 == 0 and part.strip():
                out.append(self.corrector.ranked_corrections(part)[0])
            else:
                out.append(part)
        return "".join(out)

    def _do_correct_selection(self):
        is_console = _foreground_process() in _CONSOLES
        saved = self._get_clip()
        self._set_clip(SENTINEL)
        time.sleep(0.06)
        if is_console:
            wk.chord(wk.VK_CONTROL, wk.VK_SHIFT, wk.VK_C)
        else:
            wk.combo(wk.VK_CONTROL, wk.VK_C)
        time.sleep(0.22)
        sel = self._get_clip()
        if sel == SENTINEL or not sel or not sel.strip():
            self._set_clip(saved)
            self._notify("沒有反白到文字（請先選取要修的字，再按 F3）")
            return

        corrected = self._correct_selection_text(sel)
        if corrected == sel:
            self._set_clip(saved)
            self._notify(f"未發現需修正的同音字（已選 {len(sel)} 字）")
            return

        changes = [(i, a, b) for i, (a, b) in enumerate(zip(sel, corrected)) if a != b]
        logbook.log_correction(sel, corrected, changes, self.corrector.margin)
        self._last = (sel, corrected)
        self._cycle = None
        edits = "、".join(f"{a}→{b}" for _, a, b in changes)
        if is_console:
            self._set_clip(corrected)
            self._notify(f"已修正：{edits}（已複製，按 Ctrl+Shift+V 貼上取代）")
        else:
            self._set_clip(corrected)
            time.sleep(0.05)
            wk.combo(wk.VK_CONTROL, wk.VK_V)        # 貼上=取代反白
            time.sleep(0.15)
            self._set_clip(saved)
            self._notify(f"已修正：{edits}（已取代反白）")


# ===== app_exe_v4 =====
# -*- coding: utf-8 -*-
"""繁中自動選字 — 獨立 exe 進入點 v4 = v3 + 修兩個 F1 bug：游標停在標點上、emoji 消失。

Bug1（游標在標點上）：改用 textutil.split_tail_unit，先剝尾端標點往前抓真正的字、
  修完把標點原樣保留（回填時跳過、不重打）。
Bug2（emoji 消失）：winkeys.type_text 已改成送代理對；取代選取改用 textutil.utf16_len
  計數（emoji=2 個 UTF-16 單元），選取才對得齊、不吃字。
F1 只用於一般輸入欄；終端機請用 F3（沿用 v3）。
PyInstaller 進入點（ZhuyinFix.spec）改指向本檔。
"""
import time

from csc import logbook, winkeys as wk, hotkey, textutil

VK_LEFT, VK_RIGHT = 0x25, 0x27


class _App3(_App2):
    def _replace_unit(self, unit, tail, new_unit):
        """游標在尾端：跳過 tail(標點，不選) → 選取 unit → 打字覆蓋 → 游標移回尾端。
        選取長度用 UTF-16 單元數（emoji=2）；標點不重打、不會被 IME 吃。"""
        for _ in range(textutil.utf16_len(tail)):
            wk.tap(VK_LEFT)
        wk.key(wk.VK_SHIFT)
        for _ in range(textutil.utf16_len(unit)):
            wk.tap(VK_LEFT)
        wk.key(wk.VK_SHIFT, up=True)
        time.sleep(0.03)
        wk.type_text(new_unit)
        for _ in range(textutil.utf16_len(tail)):
            wk.tap(VK_RIGHT)

    def _do_correct(self):
        if _foreground_process() in _CONSOLES:
            self._notify("終端機請用 F3（反白後按）")
            return
        time.sleep(0.08)
        window = self._grab_window()
        if window is None:
            self._notify("沒抓到文字（換個輸入欄試試）")
            return
        unit, tail = textutil.split_tail_unit(window)
        if not unit.strip():
            self._notify("沒抓到要修的句子")
            return

        cyc = self._cycle
        if cyc and unit == cyc["list"][cyc["idx"]]:        # 再按 F1 → 下一個候選
            cyc["idx"] = (cyc["idx"] + 1) % len(cyc["list"])
            nxt = cyc["list"][cyc["idx"]]
            self._replace_unit(unit, tail, nxt)
            self._last = (cyc["orig"], nxt)
            if nxt == cyc["orig"]:                         # 轉一圈回原句 → 提醒一次
                self._notify("已還原為原句")
            return                                          # 中間候選：安靜

        ranked = self.corrector.ranked_corrections(unit)
        self._cycle = {"list": ranked, "idx": 0, "orig": unit}
        self._last = (unit, ranked[0])
        if ranked[0] != unit:
            self._replace_unit(unit, tail, ranked[0])
            changes = [(i, a, b) for i, (a, b) in enumerate(zip(unit, ranked[0])) if a != b]
            logbook.log_correction(unit, ranked[0], changes, self.corrector.margin)
            edits = "、".join(f"{a}→{b}" for _, a, b in changes)
            self._notify(f"已修正：{edits}（不滿意再按 F1 換，共 {len(ranked)} 個）")
        elif len(ranked) > 1:
            self._notify(f"未發現錯字（再按 F1 看其他候選，共 {len(ranked)} 個）")
        else:
            self._cycle = None
            self._notify(f"未發現需修正的同音字：{unit}")


# ===== app_exe_v5 =====
# -*- coding: utf-8 -*-
"""繁中自動選字 — 獨立 exe 進入點 v5 = v4 + 修「emoji 害選取算錯格、吃掉前面空格/標點」。

v4 用 UTF-16 單元數選取，但有些 app 游標按「字素」走（emoji=1 格），於是 emoji
會讓 Shift+← 多選一格，把前面的空格/標點吃掉（你好 早安🥹 → 你好棗安🥹）。
改法：寫回時用與抓取**相同的格數**（GRAB_CHARS 次 Shift+←）重選同一塊視窗，再把
「整個視窗（前綴 + 修好的單位 + 尾端標點）」**貼上**取代——按鍵次數一致 → 區域一致，
與 emoji 幾格無關；貼上保留空格/全形標點/emoji。
F1 只用於一般輸入欄；終端機請用 F3。PyInstaller 進入點（ZhuyinFix.spec）改指向本檔。
"""
import time

from csc import logbook, winkeys as wk, textutil

VK_LEFT = 0x25


class _App4(_App3):
    def _replace_window(self, new_window):
        """重選與抓取相同的格數後，整段貼上 new_window（避開 emoji 的游標計數差異）。"""
        saved = self._get_clip()
        wk.key(wk.VK_SHIFT)
        for _ in range(GRAB_CHARS):
            wk.tap(VK_LEFT)
        wk.key(wk.VK_SHIFT, up=True)
        time.sleep(0.03)
        self._set_clip(new_window)
        time.sleep(0.05)
        wk.combo(wk.VK_CONTROL, wk.VK_V)
        time.sleep(0.15)
        self._set_clip(saved)

    def _do_correct(self):
        if _foreground_process() in _CONSOLES:
            self._notify("終端機請用 F3（反白後按）")
            return
        time.sleep(0.08)
        window = self._grab_window()
        if window is None:
            self._notify("沒抓到文字（換個輸入欄試試）")
            return
        unit, tail = textutil.split_tail_unit(window)
        if not unit.strip():
            self._notify("沒抓到要修的句子")
            return
        prefix = window[: len(window) - len(unit) - len(tail)]

        cyc = self._cycle
        if cyc and unit == cyc["list"][cyc["idx"]]:        # 再按 F1 → 下一個候選
            cyc["idx"] = (cyc["idx"] + 1) % len(cyc["list"])
            nxt = cyc["list"][cyc["idx"]]
            self._replace_window(prefix + nxt + tail)
            self._last = (cyc["orig"], nxt)
            if nxt == cyc["orig"]:                         # 轉一圈回原句 → 提醒一次
                self._notify("已還原為原句")
            return                                          # 中間候選：安靜

        ranked = self.corrector.ranked_corrections(unit)
        self._cycle = {"list": ranked, "idx": 0, "orig": unit}
        self._last = (unit, ranked[0])
        if ranked[0] != unit:
            self._replace_window(prefix + ranked[0] + tail)
            changes = [(i, a, b) for i, (a, b) in enumerate(zip(unit, ranked[0])) if a != b]
            logbook.log_correction(unit, ranked[0], changes, self.corrector.margin)
            edits = "、".join(f"{a}→{b}" for _, a, b in changes)
            self._notify(f"已修正：{edits}（不滿意再按 F1 換，共 {len(ranked)} 個）")
        elif len(ranked) > 1:
            self._notify(f"未發現錯字（再按 F1 看其他候選，共 {len(ranked)} 個）")
        else:
            self._cycle = None
            self._notify(f"未發現需修正的同音字：{unit}")


# ===== app_exe_v6 =====
# -*- coding: utf-8 -*-
"""繁中自動選字 — 獨立 exe 進入點 v6 = v5 + F2「反白學這個詞」+ 鍵位重排。

鍵位：F1 自動修正 · F2 學這個詞 · F3 反白手動修 · F4 標記上一筆錯誤(log)。
F2 學詞：反白「正確的詞」→ 自動推導注音 → 寫入 data/userforce.txt → 熱重載即時生效。
  第一次=建議(soft)；同詞再按 F2=升級強制(hard)；單字不開放強制；系統匣可管理/移除。
解決 BERT 不認得的新詞/俗稱（Threads 叫「脆」→ 教「脆友/發脆」即可穩定修正）。
PyInstaller 進入點（ZhuyinFix.spec）改指向本檔。
"""
import threading
import time

import pystray

from csc import logbook, winkeys as wk, hotkey, userdict, wordphon


class _App5(_App4):
    def start(self):
        self.icon.menu = self._build_menu()
        hotkey.start_hotkeys_thread({
            hotkey.VK_F1: self._on_f1,
            hotkey.VK_F2: self._on_f2_learn,
            hotkey.VK_F3: self._on_f3,
            hotkey.VK_F4: self._on_f4_mark,
        })
        self.icon.run(setup=self._setup)

    def _load_model(self):
        self.corrector = OnnxCorrector(_res("models", "bert.int8.onnx"),
                                       _res("models", "vocab.txt"))
        self._set(ICON_READY, f"{APP_TITLE}：就緒（F1改/F2學詞/F3反白/F4標記）")
        self._notify("就緒：F1 修正 · F2 學這個詞 · F3 反白修 · F4 標記")

    # ---- 熱鍵：F2=學詞、F4=標記 ----
    def _on_f2_learn(self):
        if self.corrector is None or self._busy:
            return
        threading.Thread(target=self._run, args=(self._do_learn_word,), daemon=True).start()

    def _on_f4_mark(self):
        if self._busy:
            return
        threading.Thread(target=self._run, args=(self._do_mark_wrong,), daemon=True).start()

    def _do_learn_word(self):
        is_console = _foreground_process() in _CONSOLES
        saved = self._get_clip()
        self._set_clip(SENTINEL)
        time.sleep(0.06)
        if is_console:
            wk.chord(wk.VK_CONTROL, wk.VK_SHIFT, wk.VK_C)
        else:
            wk.combo(wk.VK_CONTROL, wk.VK_C)
        time.sleep(0.22)
        sel = self._get_clip()
        self._set_clip(saved)
        word = (sel or "").strip()
        if word == SENTINEL or not word:
            self._notify("沒有反白到字（請先選取『正確的詞』再按 F2 學習）")
            return
        if len(word) > 8:
            self._notify("選取太長，請只選一個詞（≤8 字）")
            return
        status, tier, msg = userdict.learn(word)
        if status == "nochar":
            self._notify(f"無法學「{word}」：{msg}")
            return
        wordphon.reload_userforce()
        self._refresh_menu()
        if status == "ok":
            extra = "；單字較易誤套，建議連詞一起教" if len(word) == 1 else ""
            self._notify(f"已學會「{word}」：建議等級（再按 F2 升級為強制）{extra}")
        elif status == "upgraded":
            self._notify(f"「{word}」升級為強制：同音打錯一定改成它")
        else:
            self._notify(f"「{word}」：{msg}")

    # ---- 系統匣：管理我學的詞 ----
    # ---- 舊「管理我學的詞」階層式子選單（已被視窗版取代；此層為死碼保留）----
    def _build_menu(self):
        items = [
            pystray.MenuItem("重新載入詞庫加權 (custom_boost.txt)", self._reload_boost),
            pystray.MenuItem(f"聯繫作者：{AUTHOR_EMAIL}", self._contact),
            pystray.MenuItem("離開", self._quit),
        ]
        return pystray.Menu(*items)

    def _refresh_menu(self):
        try:
            self.icon.menu = self._build_menu()
            self.icon.update_menu()
        except Exception:
            pass

    @staticmethod
    def _ask_yesno(msg):
        """Win32 是非框（YESNO＋警告＋搶到前景/置頂）。回傳 True=按了「是」。
        關鍵：必須在『獨立執行緒』呼叫——同步在 pystray 選單回呼裡彈，會卡在選單的 modal loop、按鈕沒反應。"""
        import ctypes
        flags = 0x4 | 0x30 | 0x10000 | 0x40000   # YESNO | ICONWARNING | SETFOREGROUND | TOPMOST
        return ctypes.windll.user32.MessageBoxW(0, msg, "刪除確認", flags) == 6

    def _remove_word(self, w):
        threading.Thread(target=self._confirm_remove, args=(w,), daemon=True).start()

    def _confirm_remove(self, w):
        if not self._ask_yesno(f"確定要刪除自學詞「{w}」?"):
            return
        userdict.remove(w)
        wordphon.reload_userforce()
        self._refresh_menu()
        self._notify(f"已移除自學詞「{w}」")

    def _clear_words(self):
        threading.Thread(target=self._confirm_clear, daemon=True).start()

    def _confirm_clear(self):
        n = len(userdict.entries_by_word())
        if not n:
            self._notify("沒有自學詞可清除")
            return
        if not self._ask_yesno(f"確定要清除全部 {n} 個自學詞?（無法復原）"):
            return
        m = userdict.clear()
        wordphon.reload_userforce()
        self._refresh_menu()
        self._notify(f"已清除 {m} 個自學詞")


# ===== app_exe_v7 =====
# -*- coding: utf-8 -*-
"""繁中自動選字 — 獨立 exe 進入點 v7 = v6 + F2「重新計算（擷取當前字）」+ 鍵位右移。

F1 循環候選從「原始字」算，整段替換會打亂已改好的部分；F2 改成「抓目前的字重算」，
已對的當基準保留、只重算剩下的。F1/F2 共用 _correct_core，差別只在 force_recompute。
鍵位：F1 修正/循環 · F2 重新計算 · F3 學詞 · F4 反白手動修 · F5 標記/log。
PyInstaller 進入點（ZhuyinFix.spec）改指向本檔。
"""
import threading
import time

import pystray

from csc import logbook, winkeys as wk, hotkey, userdict, wordphon, textutil


class _App6(_App5):
    def start(self):
        self.icon.menu = self._build_menu()
        hotkey.start_hotkeys_thread({
            hotkey.VK_F1: self._on_f1,            # 修正 / 循環整段候選
            hotkey.VK_F2: self._on_f2_recorrect,  # 重新計算（擷取當前字）
            hotkey.VK_F3: self._on_f2_learn,      # 學這個詞
            hotkey.VK_F4: self._on_f3,            # 反白手動修正
            hotkey.VK_F5: self._on_f4_mark,       # 標記 / log
        })
        self.icon.run(setup=self._setup)

    def _load_model(self):
        self.corrector = OnnxCorrector(_res("models", "bert.int8.onnx"),
                                       _res("models", "vocab.txt"))
        self._set(ICON_READY, f"{APP_TITLE}：就緒（F1改/F2重算/F3學詞/F4反白/F5標記）")
        self._notify("就緒：F1 修正 · F2 從現在的字再修 · F3 學詞 · F4 反白 · F5 標記")

    # ---- F1 + F2 共用核心 ----
    def _correct_core(self, force_recompute):
        if _foreground_process() in _CONSOLES:
            self._notify("終端機請用 F4（反白後按）")
            return
        time.sleep(0.08)
        window = self._grab_window()
        if window is None:
            self._notify("沒抓到文字（換個輸入欄試試）")
            return
        unit, tail = textutil.split_tail_unit(window)
        if not unit.strip():
            self._notify("沒抓到要修的句子")
            return
        prefix = window[: len(window) - len(unit) - len(tail)]

        cyc = self._cycle
        if not force_recompute and cyc and unit == cyc["list"][cyc["idx"]]:   # F1 再按 → 循環
            cyc["idx"] = (cyc["idx"] + 1) % len(cyc["list"])
            nxt = cyc["list"][cyc["idx"]]
            self._replace_window(prefix + nxt + tail)
            self._last = (cyc["orig"], nxt)
            if nxt == cyc["orig"]:
                self._notify("已還原為原句")
            return

        ranked = self.corrector.ranked_corrections(unit)        # 從「目前的字」重算
        self._cycle = {"list": ranked, "idx": 0, "orig": unit}
        self._last = (unit, ranked[0])
        if ranked[0] != unit:
            self._replace_window(prefix + ranked[0] + tail)
            changes = [(i, a, b) for i, (a, b) in enumerate(zip(unit, ranked[0])) if a != b]
            logbook.log_correction(unit, ranked[0], changes, self.corrector.margin)
            edits = "、".join(f"{a}→{b}" for _, a, b in changes)
            tag = "重算" if force_recompute else "已修正"
            self._notify(f"{tag}：{edits}（F2 從現在再修 / F1 換整段候選）")
        elif force_recompute:
            self._notify(f"目前沒有可再修的同音字：{unit}")
        elif len(ranked) > 1:
            self._notify(f"未發現錯字（再按 F1 看其他候選，共 {len(ranked)} 個）")
        else:
            self._cycle = None
            self._notify(f"未發現需修正的同音字：{unit}")

    def _do_correct(self):
        self._correct_core(False)

    def _do_recorrect(self):
        self._correct_core(True)

    def _on_f2_recorrect(self):
        if self.corrector is None or self._busy:
            return
        threading.Thread(target=self._run, args=(self._do_recorrect,), daemon=True).start()

    # ---- 改鍵後修正提示字串（學詞→F3、手動修→F4）----
    def _do_learn_word(self):
        is_console = _foreground_process() in _CONSOLES
        saved = self._get_clip()
        self._set_clip(SENTINEL)
        time.sleep(0.06)
        if is_console:
            wk.chord(wk.VK_CONTROL, wk.VK_SHIFT, wk.VK_C)
        else:
            wk.combo(wk.VK_CONTROL, wk.VK_C)
        time.sleep(0.22)
        sel = self._get_clip()
        self._set_clip(saved)
        word = (sel or "").strip()
        if word == SENTINEL or not word:
            self._notify("沒有反白到字（請先選取『正確的詞』再按 F7 學習）")
            return
        if len(word) > 8:
            self._notify("選取太長，請只選一個詞（≤8 字）")
            return
        status, level, msg = userdict.learn(word)
        if status == "nochar":
            self._notify(f"無法學「{word}」：{msg}")
            return
        wordphon.reload_userforce()
        self._refresh_menu()
        if status == "ok":
            cap = userdict.cap_for(word)
            self._notify(f"已學「{word}」：強度 {level}/{cap}（再按 F7 加強，越高越容易贏）")
        elif status == "maxed":
            self._notify(f"「{word}」已是最高強度 {level}（再按也不會更強）")
        else:
            self._notify(f"「{word}」：{msg}")

    def _do_correct_selection(self):
        is_console = _foreground_process() in _CONSOLES
        saved = self._get_clip()
        self._set_clip(SENTINEL)
        time.sleep(0.06)
        if is_console:
            wk.chord(wk.VK_CONTROL, wk.VK_SHIFT, wk.VK_C)
        else:
            wk.combo(wk.VK_CONTROL, wk.VK_C)
        time.sleep(0.22)
        sel = self._get_clip()
        if sel == SENTINEL or not sel or not sel.strip():
            self._set_clip(saved)
            self._notify("沒有反白到文字（請先選取要修的字，再按 F4）")
            return
        corrected = self._correct_selection_text(sel)
        if corrected == sel:
            self._set_clip(saved)
            self._notify(f"未發現需修正的同音字（已選 {len(sel)} 字）")
            return
        changes = [(i, a, b) for i, (a, b) in enumerate(zip(sel, corrected)) if a != b]
        logbook.log_correction(sel, corrected, changes, self.corrector.margin)
        self._last = (sel, corrected)
        self._cycle = None
        edits = "、".join(f"{a}→{b}" for _, a, b in changes)
        if is_console:
            self._set_clip(corrected)
            self._notify(f"已修正：{edits}（已複製，按 Ctrl+Shift+V 貼上取代）")
        else:
            self._set_clip(corrected)
            time.sleep(0.05)
            wk.combo(wk.VK_CONTROL, wk.VK_V)
            time.sleep(0.15)
            self._set_clip(saved)
            self._notify(f"已修正：{edits}（已取代反白）")

    def _mk_remove(self, w):
        # 回傳 2 參數 (icon, item) 的 action；pystray 只收 co_argcount≤2 的可呼叫物
        return lambda icon, item: self._remove_word(w)

    def _build_menu(self):
        # 舊「管理我學的詞」階層式子選單已移除（改用系統匣的「管理我學的詞…」視窗，見最終層 _on_manage）。
        items = [
            pystray.MenuItem("重新載入詞庫加權 (custom_boost.txt)", self._reload_boost),
            pystray.MenuItem(f"聯繫作者：{AUTHOR_EMAIL}", self._contact),
            pystray.MenuItem("離開", self._quit),
        ]
        return pystray.Menu(*items)


# ===== app_exe_v8 =====
# -*- coding: utf-8 -*-
"""繁中自動選字 — 獨立 exe 進入點 v8 = v7 + 修「PowerPoint/Office 抓不到文字」。

根因：Office 剪貼簿延遲渲染——Ctrl+C 後文字不會馬上上剪貼簿，固定 sleep 0.22s
就讀常讀到哨兵 → 「沒抓到文字」。解法：改輪詢，拿到非哨兵內容就立刻往下
（一般 app ~50ms 即回，Office 最多等 ~0.9s）。套用在 F1/F2 抓取與 F3/F4 選取讀取。
PyInstaller 進入點（ZhuyinFix.spec）改指向本檔。
"""
import time

from csc import logbook, winkeys as wk, userdict, wordphon, editfmt


class _App7(_App6):
    def _poll_clip(self, timeout=0.9):
        """Ctrl+C 後輪詢剪貼簿，回傳非哨兵內容或逾時值（Office 剪貼簿較慢）。"""
        deadline = time.time() + timeout
        last = ""
        while time.time() < deadline:
            time.sleep(0.03)
            c = self._get_clip()
            if c and c != SENTINEL:
                return c
            last = c
        return last

    def _grab_window(self):
        original = self._get_clip()
        self._set_clip(SENTINEL)
        time.sleep(0.06)
        wk.key(wk.VK_SHIFT)
        for _ in range(GRAB_CHARS):
            wk.tap(VK_LEFT)
        wk.key(wk.VK_SHIFT, up=True)
        time.sleep(0.05)
        wk.combo(wk.VK_CONTROL, wk.VK_C)
        window = self._poll_clip()                       # 輪詢取代固定 sleep
        self._set_clip(original)
        wk.tap(VK_RIGHT)
        if not window or window == SENTINEL or not window.strip():
            return None
        return window

    def _grab_selection(self, is_console):
        """讀『現有選取』（F3/F4 用）：放哨兵 → 複製 → 輪詢讀回。不還原剪貼簿（交給呼叫端）。"""
        self._set_clip(SENTINEL)
        time.sleep(0.06)
        if is_console:
            wk.chord(wk.VK_CONTROL, wk.VK_SHIFT, wk.VK_C)
        else:
            wk.combo(wk.VK_CONTROL, wk.VK_C)
        return self._poll_clip()

    def _do_learn_word(self):
        is_console = _foreground_process() in _CONSOLES
        saved = self._get_clip()
        sel = self._grab_selection(is_console)
        self._set_clip(saved)
        word = (sel or "").strip()
        if not word or word == SENTINEL:
            self._notify("沒有反白到字（請先選取『正確的詞』再按 F7 學習）")
            return
        if len(word) > 8:
            self._notify("選取太長，請只選一個詞（≤8 字）")
            return
        status, level, msg = userdict.learn(word)            # 與 F9 同源：多段式，回傳目前等級
        if status == "nochar":
            self._notify(f"無法學「{word}」：{msg}")
            return
        wordphon.reload_userforce()
        self._refresh_menu()
        if status == "ok":                                   # 報等級（對齊 tray v20、與 F9 自動學一致）
            cap = userdict.cap_for(word)
            self._notify(f"已學「{word}」：強度 {level}/{cap}（再按 F7 加強，越高越容易贏）")
        elif status == "maxed":
            self._notify(f"「{word}」已是最高強度 {level}（再按也不會更強）")
        else:
            self._notify(f"「{word}」：{msg}")

    def _do_correct_selection(self):
        is_console = _foreground_process() in _CONSOLES
        saved = self._get_clip()
        sel = self._grab_selection(is_console)
        if not sel or sel == SENTINEL or not sel.strip():
            self._set_clip(saved)
            self._notify("沒有反白到文字（請先選取要修的字，再按 F5）")
            return
        corrected = self._correct_selection_text(sel)
        if corrected == sel:
            self._set_clip(saved)
            self._notify(f"未發現需修正的同音字（已選 {len(sel)} 字）")
            return
        changes = [(i, a, b) for i, (a, b) in enumerate(zip(sel, corrected)) if a != b]
        logbook.log_correction(sel, corrected, changes, self.corrector.margin)
        self._last = (sel, corrected)
        self._cycle = None
        edits = editfmt.fmt_edits(changes)                # v2.3b：notify_group 開→相鄰黏一起；關→逐字（同舊）
        if is_console:
            self._set_clip(corrected)
            self._notify(f"已修正：{edits}（已複製，按 Ctrl+Shift+V 貼上取代）")
        else:
            self._set_clip(corrected)
            time.sleep(0.05)
            wk.combo(wk.VK_CONTROL, wk.VK_V)
            time.sleep(0.15)
            self._set_clip(saved)
            self._notify(f"已修正：{edits}（已取代反白）")


# ===== app_exe_v9 =====
# -*- coding: utf-8 -*-
"""繁中自動選字 — 獨立 exe 進入點 v9 = v8 + 追上日常版 v33（統一引擎/F7/F10/剪貼簿修正/暫停鈕…）。

把日常版 v21~v33 的改進鏡像進 ONNX exe（**不含 F6 輸入框**——它需 tkinter 打包，留作下一輪）：
  - 剪貼簿寫回：確認寫入(殺 pyperclip 靜默失敗) + 嚴格序列化(殺連按重疊) + 批次反白(殺 Shift 長按漏鍵)。
  - F1/F2/F4/F7 統一循環引擎 `_cycle_correct`；通知比照 F1（第一次提示、中間安靜、轉回原句）。
  - F2 重算通用（做完哪個鍵按 F2 就重算那個目標）。
  - F7 前30字整段重修。
  - 難例自動記錄 logs/error_cases.log（F2/按第二次，含原題 + 改錯成的內容）；手動 F10。
  - 系統匣：暫停熱鍵偵測（暫停＝真的 UnregisterHotKey、圖示變紅）+ 開啟 error_cases.log。
鍵位：F1 修正/循環 · F2 重算(通用) · F3 學詞 · F4 反白修 · F5 標記 · F7 前30字 · F10 記難例。
PyInstaller 進入點（ZhuyinFix.spec）改指向本檔。
"""
import os
import threading
import time

import pystray

from csc import logbook, winkeys as wk, hotkey, textutil, editfmt

ICON_PAUSE = _icon((200, 60, 60))            # 暫停＝紅（與 載入灰/就緒綠/忙黃 區別）
_CON_F4 = "終端機/CLI 不能就地改字，請按 F6 開輸入框打字（框裡一樣 F1~F5 改字、Enter 送回）"


class _App8(_App7):
    def __init__(self):
        super().__init__()
        self._op_lock = threading.Lock()     # 序列化所有碰剪貼簿的校正
        self._last_elogged = None

    # ---- 啟動：F1~F7 + F10，抓 HotkeyController ----
    def start(self):
        self.icon.menu = self._build_menu()
        self._hk = hotkey.start_hotkeys_thread({
            hotkey.VK_F1: self._on_f1,            # 修正 / 循環
            hotkey.VK_F2: self._on_f2_recorrect,  # 重算（通用）
            hotkey.VK_F3: self._on_f2_learn,      # 學詞
            hotkey.VK_F4: self._on_f3,            # 反白手動修
            hotkey.VK_F5: self._on_f4_mark,       # 標記 / log
            hotkey.VK_F7: self._on_f7,            # 前30字整段重修
            hotkey.VK_F10: self._on_logerror,     # 記難例
        })
        self.icon.run(setup=self._setup)

    def _load_model(self):
        self.corrector = OnnxCorrector(_res("models", "bert.int8.onnx"),
                                       _res("models", "vocab.txt"))
        self._set(ICON_READY,
                  f"{APP_TITLE}：就緒（F1改/F2重算/F3學/F4反白/F5標記/F7前30字/F10記難例）")
        self._notify("就緒：F1 修 · F2 重算 · F3 學 · F4 反白 · F5 標記 · F7 前30字 · F10 記難例")

    # ---- 序列化（連按不重疊剪貼簿操作）----
    def _run(self, fn):
        if not self._op_lock.acquire(blocking=False):
            return
        try:
            super()._run(fn)
        finally:
            self._op_lock.release()

    # ---- 剪貼簿：確認寫入 + 批次反白 ----
    def _set_clip_confirm(self, text, timeout=0.5):
        deadline = time.time() + timeout
        while True:
            self._set_clip(text)
            time.sleep(0.03)
            if self._get_clip() == text:
                return True
            if time.time() >= deadline:
                return False

    def _grab_window(self):
        original = self._get_clip()
        self._set_clip(SENTINEL)
        time.sleep(0.06)
        wk.select_left(GRAB_CHARS)               # 批次反白：壓短 Shift 按住、杜絕漏鍵
        time.sleep(0.05)
        wk.combo(wk.VK_CONTROL, wk.VK_C)
        window = self._poll_clip()
        self._set_clip(original)
        wk.tap(VK_RIGHT)
        if not window or window == SENTINEL or not window.strip():
            return None
        return window

    def _replace_window(self, new_window):
        # Windows 剪貼簿換行：放裸 \n 時很多 app 會把連續換行收合 → 統一成 \r\n 再貼，多行才完整保留
        new_window = new_window.replace("\r\n", "\n").replace("\n", "\r\n")
        saved = self._get_clip()
        if not self._set_clip_confirm(new_window):
            self._set_clip(saved)
            raise RuntimeError("剪貼簿被佔用，沒貼成功，請再按一次")
        wk.select_left(GRAB_CHARS)
        time.sleep(0.05)
        wk.combo(wk.VK_CONTROL, wk.VK_V)
        time.sleep(0.30)
        self._set_clip(saved)

    def _paste_selection(self, text, reselect=True):
        text = text.replace("\r\n", "\n").replace("\n", "\r\n")   # 多行選取貼回保留換行（同 _replace_window）
        saved = self._get_clip()
        if not self._set_clip_confirm(text):
            self._set_clip(saved)
            raise RuntimeError("剪貼簿被佔用，沒貼成功，請再按一次 F4")
        wk.combo(wk.VK_CONTROL, wk.VK_V)
        time.sleep(0.20)
        if reselect:
            wk.select_left(textutil.utf16_len(text))
        self._set_clip(saved)

    # ---- 失敗案例：原題 + 改錯成的內容（＝該輪最佳猜測 list[0]）----
    def _auto_log_problem(self, prob=None, wrong=None):
        cyc = self._cycle
        if prob is None:
            prob = (cyc["orig"] if cyc else None) or (self._last[0] if self._last else None)
        if wrong is None:
            if cyc and cyc.get("list"):
                wrong = cyc["list"][0]
            elif self._last:
                wrong = self._last[1]
        if not prob or prob == self._last_elogged:
            return
        try:
            logbook.log_error_case(prob, wrong)
            self._last_elogged = prob
        except Exception:
            pass

    # ---- 統一循環引擎（F1/F2/F4/F7 共用）----
    def _cycle_correct(self, read_fn, kind, cyclekey, force=False):
        got = read_fn()
        if got is None:
            return
        target, writer = got
        cyc = self._cycle
        if not force and cyc and cyc.get("kind") == kind and target == cyc["list"][cyc["idx"]]:
            cyc["idx"] = (cyc["idx"] + 1) % len(cyc["list"])
            nxt = cyc["list"][cyc["idx"]]
            writer(nxt)
            self._last = (cyc["orig"], nxt)
            self._auto_log_problem(cyc["orig"])          # 按第二次＝第一次沒改對 → 記難例
            if nxt == cyc["orig"]:
                self._notify("已還原為原句")
            return
        ranked = self.corrector.ranked_corrections(target)
        best = ranked[0]
        self._cycle = {"list": ranked, "idx": 0, "orig": target, "kind": kind,
                       "read_fn": read_fn, "cyclekey": cyclekey}
        self._last = (target, best)
        if best != target:
            writer(best)
            changes = [(i, a, b) for i, (a, b) in enumerate(zip(target, best)) if a != b]
            logbook.log_correction(target, best, changes, self.corrector.margin)
            edits = editfmt.fmt_edits(changes)            # v2.3b：notify_group 開→相鄰黏一起；關→逐字（同舊）
            tag = "重算" if force else "已修正"
            self._notify(f"{tag}：{edits}（不滿意再按 {cyclekey} 換候選，共 {len(ranked)} 個）")
        elif force:
            self._notify(f"目前沒有可再修的同音字：{target}")
        elif len(ranked) > 1:
            self._notify(f"未發現需修正（再按 {cyclekey} 看其他候選，共 {len(ranked)} 個）")
        else:
            self._cycle = None
            self._notify(f"未發現需修正的同音字：{target}")

    # ---- 各鍵：怎麼取文字、怎麼寫回 ----
    def _read_unit(self):
        time.sleep(0.08)
        window = self._grab_window()
        if window is None:
            self._notify("沒抓到文字（換個輸入欄試試）"); return None
        unit, tail = textutil.split_tail_unit(window)
        if not unit.strip():
            self._notify("沒抓到要修的句子"); return None
        prefix = window[: len(window) - len(unit) - len(tail)]
        return unit, lambda new: self._replace_window(prefix + new + tail)

    def _read_win(self, n):
        time.sleep(0.08)
        window = self._grab_window()
        if window is None:
            self._notify("沒抓到文字（換個輸入欄試試）"); return None
        chunk = window[-n:]
        if not chunk.strip():
            self._notify("沒抓到要修的字"); return None
        prefix = window[: len(window) - len(chunk)]
        return chunk, lambda new: self._replace_window(prefix + new)

    def _read_sel(self):
        saved = self._get_clip()
        sel = self._grab_selection(False)
        self._set_clip(saved)
        if not sel or sel == SENTINEL or not sel.strip():
            self._notify("沒有反白到文字（請先選取要修的字，再按 F5）"); return None
        return sel, lambda new: self._paste_selection(new, reselect=True)

    # ---- 四個入口 ----
    def _do_correct(self):                    # F1
        if _foreground_process() in _CONSOLES:
            self._notify(_CON_F4); return
        self._cycle_correct(self._read_unit, "unit", "F1")

    def _do_recorrect(self):                  # F2：重算上一次那個鍵的目標（通用）
        cyc = self._cycle
        orig0 = cyc.get("orig") if cyc else None
        if orig0:
            self._auto_log_problem(orig0)            # 重算前記原題（此刻 orig 還是最初的字）
        if cyc and cyc.get("read_fn"):
            key = cyc.get("cyclekey", "F1")
            if _foreground_process() in _CONSOLES:
                self._notify(_CON_F4); return
            self._cycle_correct(cyc["read_fn"], cyc["kind"], key, force=True)
        else:
            if _foreground_process() in _CONSOLES:
                self._notify(_CON_F4); return
            self._cycle_correct(self._read_unit, "unit", "F1", force=True)
        if self._cycle and orig0:
            # F2 重算後新 cycle 的 orig 會變成「上次結果」→ 保留真原題：dedup 只記一筆、input 正確、F3 還原回真原題
            self._cycle["orig"] = orig0

    def _do_correct_window(self, n):          # F7
        if _foreground_process() in _CONSOLES:
            self._notify(_CON_F4); return
        self._cycle_correct(lambda: self._read_win(n), "win", "F4")   # v2.1：前30字＝F4

    def _do_correct_selection(self):          # F4：一般欄走統一引擎；終端機沿用 v8（無循環）
        if _foreground_process() in _CONSOLES:
            super()._do_correct_selection()
            return
        self._cycle_correct(self._read_sel, "sel", "F5")   # v2.1：只改反白＝F5

    # ---- F7 / F10 熱鍵 ----
    def _on_f7(self):
        if self.corrector is None or self._busy:
            return
        threading.Thread(target=self._run,
                         args=(lambda: self._do_correct_window(30),), daemon=True).start()

    def _on_logerror(self):
        threading.Thread(target=self._do_log_error, daemon=True).start()

    def _do_log_error(self):
        if not self._cycle and not self._last:
            self._notify("沒有可記錄的上一筆（先按 F1/F7 修正，發現改錯了再按 F10）")
            return
        self._auto_log_problem()
        self._notify("已記錄改錯題目（含改錯成的內容）到 error_cases.log")

    # ---- 系統匣：暫停熱鍵 / 開啟難例清單 ----
    def _build_menu(self):
        extra = [
            pystray.MenuItem("暫停熱鍵偵測（要用原程式的 F 鍵時）", self._toggle_pause,
                             checked=lambda item: bool(getattr(self, "_hk", None) and self._hk.paused)),
            pystray.MenuItem("開啟 error_cases.log（難例清單）", self._open_errorlog),
            pystray.Menu.SEPARATOR,
        ]
        return pystray.Menu(*(extra + list(super()._build_menu())))

    def _toggle_pause(self, icon=None, item=None):
        hk = getattr(self, "_hk", None)
        if not hk:
            return
        hk.toggle()
        if hk.paused:
            self._set(ICON_PAUSE, f"{APP_TITLE}：熱鍵已暫停（點選單恢復）")
            self._notify("熱鍵已暫停：F 鍵交還給目前的程式；要恢復請點系統匣選單")
        else:
            self._set(ICON_READY, f"{APP_TITLE}：就緒（熱鍵已恢復）")
            self._notify("熱鍵已恢復")
        try:
            self.icon.update_menu()
        except Exception:
            pass

    def _open_errorlog(self, icon=None, item=None):
        try:
            path = logbook.ERROR_FILE
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if not os.path.exists(path):
                open(path, "a", encoding="utf-8").close()
            os.startfile(path)
        except Exception as e:
            self._notify(f"開啟失敗：{e}")


# ===== app_exe_v10 =====
# -*- coding: utf-8 -*-
"""繁中自動選字 — 獨立 exe 進入點 v10 = v9 + F6 輸入框（終端機輸入），追平日常版 v33。

把日常版 v21/v27 的 F6 框（tkinter）移植進 ONNX exe：打字 → 框裡一樣按 F1 改字 / 再按換候選 /
F2 重算 / 前30字 → Enter 送回原視窗（Ctrl+Enter 軟換行重播、Shift+Enter 純換行）。框內按 F10
記框內題目。框開著時 F1/F2/F10 轉進框（OS 攔截熱鍵 → 經 queue 給 Tk 緒）。
打包：`ZhuyinFix.spec` 需**移除 tkinter 排除**（框要用）。產品檔名改 tcsc。
鍵位：F1 修/循環 · F2 重算(通用) · F3 學詞 · F4 反白修 · F5 標記 · F6 輸入框 · F7 前30字 · F10 記難例。
"""
import queue
import threading
import time

from csc import winkeys as wk, hotkey, textutil, logbook

VK_RETURN = 0x0D


class _App9(_App8):
    def __init__(self):
        super().__init__()
        self._box_q = None
        self._box_problem = None

    def start(self):
        self._box_q = None
        self._box_problem = None
        self.icon.menu = self._build_menu()
        self._hk = hotkey.start_hotkeys_thread({
            hotkey.VK_F1: self._on_f1,
            hotkey.VK_F2: self._on_f2_recorrect,
            hotkey.VK_F3: self._on_f2_learn,
            hotkey.VK_F4: self._on_f3,
            hotkey.VK_F5: self._on_f4_mark,
            hotkey.VK_F6: self._on_f6,             # 輸入框（終端機輸入）
            hotkey.VK_F7: self._on_f7,
            hotkey.VK_F10: self._on_logerror,
        })
        self.icon.run(setup=self._setup)

    def _load_model(self):
        self.corrector = OnnxCorrector(_res("models", "bert.int8.onnx"),
                                       _res("models", "vocab.txt"))
        self._install_box_problem_tracker()
        self._set(ICON_READY,
                  f"{APP_TITLE}：就緒（F1改/F2重算/F3學/F4反白/F5標記/F6框/F7前30字/F10記難例）")
        self._notify("就緒：F1 修 · F2 重算 · F3 學 · F4 反白 · F5 標記 · "
                     "F6 輸入框 · F7 前30字 · F10 記難例")

    def _install_box_problem_tracker(self):
        """包裝 ranked_corrections：記住最近一次被要求修正的題目（給 F6 框內 F10 記錄用）。"""
        _orig = self.corrector.ranked_corrections

        def _wrapped(text, *a, **k):
            self._box_problem = text
            return _orig(text, *a, **k)

        self.corrector.ranked_corrections = _wrapped

    # ---- 框開著時 F1/F2/F10 轉進框 ----
    def _on_f1(self):
        q = getattr(self, "_box_q", None)
        if q is not None:
            try:
                q.put("f1")
            except Exception:
                pass
            return
        super()._on_f1()

    def _on_f2_recorrect(self):
        q = getattr(self, "_box_q", None)
        if q is not None:
            try:
                q.put("f2")
            except Exception:
                pass
            return
        super()._on_f2_recorrect()

    def _on_logerror(self):
        if getattr(self, "_box_q", None) is not None:
            threading.Thread(target=self._do_log_error_box, daemon=True).start()
        else:
            super()._on_logerror()

    def _do_log_error_box(self):
        try:
            prob = getattr(self, "_box_problem", None)
            if not prob:
                self._notify("框內還沒有可記錄的修正（先在框裡按 F1/F7 修正，再按 F10）")
                return
            logbook.log_error_case(prob)
            self._notify(f"已記錄框內改錯題目到 error_cases.log：{prob}")
        except Exception as e:
            self._notify(f"記錄失敗：{e}")

    # ---- 前景搶奪／還原（背景程式彈窗必備）----
    def _bring_to_front(self, hwnd):
        try:
            if not hwnd:
                return
            fg = _user32.GetForegroundWindow()
            if fg == hwnd:
                return
            cur = _kernel32.GetCurrentThreadId()
            other = _user32.GetWindowThreadProcessId(fg, 0) if fg else 0
            attached = bool(other) and other != cur
            if attached:
                _user32.AttachThreadInput(cur, other, True)
            _user32.BringWindowToTop(hwnd)
            _user32.SetForegroundWindow(hwnd)
            if attached:
                _user32.AttachThreadInput(cur, other, False)
        except Exception:
            pass

    # ---- F6：輸入框 ----
    def _on_f6(self):
        if self.corrector is None or self._busy:
            return
        self._box_problem = None                   # 進框前清掉框外的舊題目
        target = _user32.GetForegroundWindow()
        threading.Thread(target=self._run_input_box, args=(target,), daemon=True).start()

    def _run_input_box(self, target_hwnd):
        self._busy = True
        self._box_q = queue.Queue()
        self._set(ICON_BUSY, f"{APP_TITLE}：輸入框開啟中…（框裡按 F1 改字）")
        text = None
        try:
            text = self._input_box_dialog(self._box_q)
        except Exception as e:
            self._notify(f"輸入框錯誤：{e}")
        finally:
            self._box_q = None
            self._set(ICON_READY, f"{APP_TITLE}：就緒（F1~F7 / F10）")
            self._busy = False
        if text:
            self._send_to_window(target_hwnd, text)

    def _input_box_dialog(self, cmd_q):
        """Tk 視窗（建立/迴圈/銷毀全在本執行緒）。打字不跑模型。F1/F2 經 cmd_q 進來，行為與全域
        一致——切最後一個單位：F1 修正、再按循環換候選；F2 以當前字重算。重算丟背景緒、結果回主緒。
        回傳要送出的文字（Enter＝框內當前內容；None＝取消/空白）。"""
        import tkinter as tk

        result = {"text": None}
        done_q = queue.Queue()
        state = {"computing": False, "cycle": None}

        root = tk.Tk()
        root.title(f"{APP_TITLE} — 輸入框（F1 改字 · Enter 送出）")
        root.attributes("-topmost", True)
        root.configure(bg="#f4f4f4")

        FONT = ("Microsoft JhengHei", 14)
        SMALL = ("Microsoft JhengHei", 9)

        tk.Label(root, text="在這裡打字（可含同音錯字）：", font=SMALL, bg="#f4f4f4",
                 anchor="w").grid(row=0, column=0, sticky="we", padx=10, pady=(10, 2))
        txtwrap = tk.Frame(root, bg="#f4f4f4")
        txtwrap.grid(row=1, column=0, sticky="we", padx=10)
        txt = tk.Text(txtwrap, height=3, width=42, font=FONT, wrap="word",
                      relief="solid", borderwidth=1)
        txt.pack(side="left", fill="both", expand=True)
        sb = tk.Scrollbar(txtwrap, command=txt.yview)
        sb.pack(side="right", fill="y")
        txt.config(yscrollcommand=sb.set)

        status = tk.Label(root, text="F1 改字(再按換選項) · F2 重算 · F3 還原 · F4 前30字 · F5 修反白 · Enter 送出",
                          font=SMALL, fg="#888", bg="#f4f4f4", anchor="w",
                          wraplength=440, justify="left")
        status.grid(row=2, column=0, sticky="we", padx=10, pady=(8, 2))

        tk.Label(root, text="F1=改字 F2=重算 F3=還原 F4=前30字 F5=反白　Enter=送出　"
                            "Ctrl+Enter=軟換行(終端機不送出)　Shift+Enter=純換行　Esc 按兩下=取消",
                 font=SMALL, fg="#aaa", bg="#f4f4f4").grid(
                     row=3, column=0, sticky="we", padx=10, pady=(0, 2))

        btns = tk.Frame(root, bg="#f4f4f4")
        btns.grid(row=4, column=0, sticky="e", padx=10, pady=(2, 10))

        def box_text():
            return txt.get("1.0", "end-1c")

        def ce_offsets():
            offs, r = [], txt.tag_ranges("ce")
            for i in range(0, len(r), 2):
                c = txt.count("1.0", r[i], "chars")
                offs.append(c[0] if isinstance(c, (tuple, list)) else int(c))
            return offs

        def set_box(t, ce=None):
            txt.delete("1.0", "end")
            txt.insert("1.0", t)
            for o in (ce or []):
                if 0 <= o < len(t) and t[o] == "\n":
                    txt.tag_add("ce", f"1.0+{o}c", f"1.0+{o + 1}c")
            txt.mark_set("insert", "end-1c")
            txt.see("insert")

        def build_payload():
            s = box_text()
            ce = set(ce_offsets())
            if not ce:
                return s
            chars = list(s)
            for o in ce:
                if 0 <= o < len(chars) and chars[o] == "\n":
                    chars[o] = "\x00"
            return "".join(chars)

        def edits(a, b):
            return "、".join(f"{x}→{y}" for x, y in zip(a, b) if x != y)

        def finish(text):
            result["text"] = text
            try:
                root.destroy()
            except Exception:
                pass

        # ── 框內校正統一引擎（錨點）：F1/F4/F7 同一套＝改字＋再按換候選；F2 重算當前目標；
        #    F10 補 gold 也讀同一份 state["cycle"]。行為對照一般欄的 _cycle_correct，差別只在
        #    I/O 是 Tk 文字框、模型丟背景緒、套用回主緒(done_q)。改這裡請連同 _cycle_correct 一起想。
        KEYNAME = {"tail": "F1", "sel": "F5", "win": "F4"}   # v2.1 鍵位：改字F1/反白F5/前30字F4

        def box_region(kind):
            """取『目前該 kind 的目標』→ (start_字元位移, target_文字)；取不到回 None 並提示。"""
            win = box_text()

            def _off(index):                                     # 字元位移；count 距離為 0 時 tkinter 回 None
                c = txt.count("1.0", index, "chars")
                return (c[0] if isinstance(c, (tuple, list)) else c) or 0

            if kind == "sel":
                try:
                    s = txt.get("sel.first", "sel.last")
                except Exception:
                    s = ""
                if not s.strip():
                    status.config(text="（先用滑鼠/Shift 反白要修的字，再按 F5）", fg="#888")
                    return None
                return _off("sel.first"), s                      # 反白含第 0 字時 count 回 None → _off 補 0（修首字反白改不了）
            if kind == "win":
                chunk = win[-30:]
                if not chunk.strip():
                    status.config(text="（先打字…）", fg="#888")
                    return None
                return len(win) - len(chunk), chunk
            cur = _off("insert")                                 # tail(F1)：依游標前的文字決定範圍（與一般模式一致，不再只改最尾）
            base = win[:cur] if cur else win                     # 游標在最前 → 退回全文（等同沒移游標）
            unit, tl = textutil.split_tail_unit(base)
            if not unit.strip():
                status.config(text="（先打字…）", fg="#888")
                return None
            return len(base) - len(unit) - len(tl), unit

        def box_apply(start, length, text):
            """以 text 取代 [start, start+length) 字元（候選同長→offset 穩定、保留其餘標記）。"""
            txt.delete(f"1.0+{start}c", f"1.0+{start + length}c")
            txt.insert(f"1.0+{start}c", text)

        def box_run(kind, force=False):
            """F1/F4/F7/F2 共用引擎。kind: tail/sel/win；force(F2)＝重算上一次那個鍵的目標。"""
            if state["computing"]:
                return
            cyc = state["cycle"]
            if force and cyc and cyc.get("kind"):
                kind = cyc["kind"]                                # F2：重算上一次那個鍵的目標
            reg = box_region(kind)
            if reg is None:
                return
            start, target = reg
            if not force and cyc and cyc.get("kind") == kind and target == cyc["list"][cyc["idx"]]:
                cyc["idx"] = (cyc["idx"] + 1) % len(cyc["list"])
                nxt = cyc["list"][cyc["idx"]]
                box_apply(start, len(target), nxt)
                if kind == "sel":
                    txt.tag_remove("sel", "1.0", "end")
                    txt.tag_add("sel", f"1.0+{start}c", f"1.0+{start + len(nxt)}c")
                k = KEYNAME[kind]
                if nxt == cyc["orig"]:
                    status.config(text=f"已回到原字（共 {len(cyc['list'])} 個，再按 {k} 重來）",
                                  fg="#888")
                else:
                    status.config(text=f"第 {cyc['idx'] + 1}/{len(cyc['list'])} 個候選"
                                       f"（再按 {k} 換 · F2 從現在重算）", fg="#1a7f37")
                return
            state["computing"] = True
            status.config(text="重算中…" if force else "修正中…", fg="#c77f00")

            def work(snap, kd, st, tgt, forced):
                try:
                    ranked = self.corrector.ranked_corrections(tgt)
                except Exception:
                    ranked = [tgt]
                done_q.put((snap, tgt, st, kd, ranked, forced, "cyc"))

            threading.Thread(target=work, args=(box_text(), kind, start, target, force),
                             daemon=True).start()

        def box_restore():
            """F3 還原回原字：把目前 cycle 的區域改回 orig（讀同一份 state["cycle"]）。"""
            cyc = state["cycle"]
            if not cyc or "orig" not in cyc:
                status.config(text="（沒有可還原的，先按 F1/F4/F5 改字）", fg="#888")
                return
            orig = cyc["orig"]
            box_apply(cyc["start"], cyc["len"], orig)
            if cyc.get("kind") == "sel":
                txt.tag_remove("sel", "1.0", "end")
                txt.tag_add("sel", f"1.0+{cyc['start']}c", f"1.0+{cyc['start'] + len(orig)}c")
            try:
                cyc["idx"] = cyc["list"].index(orig)
            except ValueError:
                pass
            status.config(text=f"已還原回原字：{orig}", fg="#1a7f37")

        def poll():
            try:
                while True:
                    cmd = cmd_q.get_nowait()
                    if cmd == "f1":
                        box_run("tail", False)
                    elif cmd == "f2":
                        box_run("tail", True)          # F2：重算上一次那個鍵的目標
                    elif cmd == "f4":
                        box_run("sel", False)
                    elif cmd == "f7":
                        box_run("win", False)
                    elif cmd == "restore":             # F3：還原回原字
                        box_restore()
                    elif cmd == "f10":                 # 框內 F10：記正確答案(gold)（鉤子，子類提供）
                        hook = getattr(self, "_box_log_gold", None)
                        if hook:
                            try:
                                hook(box_text(), state, status)
                            except Exception:
                                pass
            except queue.Empty:
                pass
            try:
                while True:
                    snap, target, start, cyckind, ranked, forced, tag = done_q.get_nowait()
                    state["computing"] = False
                    if snap != box_text():
                        continue
                    best = ranked[0]
                    box_apply(start, len(target), best)
                    state["cycle"] = {"list": ranked, "idx": 0, "orig": target,
                                      "kind": cyckind, "start": start, "len": len(target)}
                    if cyckind == "sel":
                        txt.tag_remove("sel", "1.0", "end")
                        txt.tag_add("sel", f"1.0+{start}c", f"1.0+{start + len(best)}c")
                    k = KEYNAME[cyckind]
                    n = len(ranked)
                    if best != target:
                        status.config(text=f"{'重算' if forced else '已修正'}："
                                           f"{edits(target, best)}（{k} 換候選/共 {n} 個 · "
                                           f"F2 從現在重算）", fg="#1a7f37")
                    elif forced:
                        status.config(text=f"目前沒有可再修的同音字（{k} 換候選共 {n} 個）", fg="#888")
                    elif n > 1:
                        status.config(text=f"未發現需修正（再按 {k} 看其他候選，共 {n} 個）· Enter 送出",
                                      fg="#888")
                    else:
                        state["cycle"] = None
                        status.config(text=f"未發現需修正的同音字：{target}", fg="#888")
            except queue.Empty:
                pass
            root.after(60, poll)

        def do_send(event=None):
            payload = build_payload()
            finish(payload if payload.replace("\x00", "").strip() else None)
            return "break"

        def do_cancel(event=None):
            # Esc 鍵要按兩下才放棄（避免誤觸把辛苦打的字弄丟）；「取消」按鈕 event=None → 直接關。
            if event is not None and not state.get("esc_armed"):
                state["esc_armed"] = True
                status.config(text="⚠ 再按一次 Esc 才會放棄並關閉（你打的字還在）", fg="#c0392b")
                root.after(2000, lambda: state.update(esc_armed=False))
                return "break"
            finish(None)
            return "break"

        def do_plain_nl(event=None):
            txt.insert("insert", "\n")
            txt.see("insert")
            return "break"

        def do_soft_nl(event=None):
            txt.insert("insert", "\n", "ce")
            txt.see("insert")
            return "break"

        txt.bind("<Return>", do_send)
        txt.bind("<Shift-Return>", do_plain_nl)
        txt.bind("<Control-Return>", do_soft_nl)
        root.bind("<Escape>", do_cancel)
        root.protocol("WM_DELETE_WINDOW", do_cancel)

        # 顯示順序（左→右）：改字 · 重算 · 還原 · 前30字 · 修反白 · 送出 · 取消（side=right 故倒序 pack）
        tk.Button(btns, text="取消 (Esc)", font=SMALL,
                  command=do_cancel).pack(side="right", padx=4)
        tk.Button(btns, text="送出 (Enter)", font=SMALL,
                  command=do_send).pack(side="right", padx=4)
        tk.Button(btns, text="修反白 (F5)", font=SMALL,
                  command=lambda: box_run("sel", False)).pack(side="right", padx=4)
        tk.Button(btns, text="前30字 (F4)", font=SMALL,
                  command=lambda: box_run("win", False)).pack(side="right", padx=4)
        tk.Button(btns, text="還原 (F3)", font=SMALL,
                  command=box_restore).pack(side="right", padx=4)
        tk.Button(btns, text="重算 (F2)", font=SMALL,
                  command=lambda: box_run("tail", True)).pack(side="right", padx=4)
        tk.Button(btns, text="改字 (F1)", font=SMALL,
                  command=lambda: box_run("tail", False)).pack(side="right", padx=4)

        root.update_idletasks()
        w, h = root.winfo_width(), root.winfo_height()
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"+{(sw - w) // 2}+{(sh - h) // 3}")

        def grab():
            GA_ROOT = 2
            try:
                hwnd = _user32.GetAncestor(txt.winfo_id(), GA_ROOT)
            except Exception:
                hwnd = 0
            root.lift()
            root.focus_force()
            self._bring_to_front(hwnd)
            txt.focus_set()

        root.after(30, grab)
        root.after(80, poll)
        root.mainloop()
        return result["text"]

    def _send_to_window(self, hwnd, text):
        """切回原視窗鍵入 text。哨兵 \\x00＝Ctrl+Enter 軟換行（重播框裡按的鍵）。
        寫回方式與 F1 _write_unit 完全一致：貼上（剪貼簿）模式永遠貼上；打字模式預設打字，
        但該段含全形標點（注音會吃字）時自動改走剪貼簿貼上。用 _App23._paste_selection 強制貼上，
        避開 _paste_selection 的『依模式改打字』覆寫（同 F1 的做法）。"""
        from csc import settings
        time.sleep(0.08)
        self._bring_to_front(hwnd)
        time.sleep(0.12)
        for i, seg in enumerate(text.split("\x00")):
            if i:
                wk.combo(wk.VK_CONTROL, VK_RETURN)
                time.sleep(0.03)
            if not seg:
                continue
            if settings.get("direct_type") and not wk.has_ime_punct(seg):
                wk.type_text(seg)                                    # 打字模式且無全形標點 → 直接打
            else:
                _App23._paste_selection(self, seg, reselect=False)   # 貼上模式 or 含標點 → 剪貼簿貼上（同 F1）
                time.sleep(0.05)
        self._notify("已輸入到原視窗（請檢查後自行按 Enter 送出）")


# ===== app_exe_v11 =====
# -*- coding: utf-8 -*-
"""繁中自動選字 — 獨立 exe 進入點 v11 = v10 + F10 改用途（補正確答案 gold），追平日常版 v34。

日常版 v34：F10 原本「手動記失敗題目」已無作用（F2／按第二次已自動記）→ 改成「**改完後把正確
答案補進該筆難例的 gold**」；難例清單改存 **JSONL**（改在共用的 `csc/logbook`，exe 重建即一併生效，
每筆 `{"ts","input","output","gold"}`，(input→gold) 即微調訓練對）。本檔把同一套搬進 exe：
  - 一般欄 F10 → `_do_record_correct`：用上一輪循環的 `read_fn`（沒有就 `_read_unit`）重讀目前欄位＝
    改好的正確答案，append 到 `error_cases.jsonl` 最後一筆的 `gold`（需先有本次自動記的失敗案例）。
  - F6 框內 F10 → 維持 v10 的「記框內題目」（框沒走自動記流程）。
  - 開啟難例清單 → 改用記事本開（`.jsonl` 在 Windows 多半沒預設關聯，os.startfile 會跳「選程式」）。
鍵位不變：F1 修/循環 · F2 重算 · F3 學 · F4 反白 · F5 標記 · F6 框 · F7 前30字 · F10 補正確答案。
PyInstaller 進入點（ZhuyinFix.spec）改指向本檔。
"""
import os
import subprocess
import threading

from csc import logbook


class _App10(_App9):
    # ---- F10 改用途：改完後補正確答案 gold（框內維持舊的「記題目」）----
    def _on_logerror(self):
        if getattr(self, "_box_q", None) is not None:
            threading.Thread(target=self._do_log_error_box, daemon=True).start()
        else:
            threading.Thread(target=self._do_record_correct, daemon=True).start()

    def _do_record_correct(self):
        if not getattr(self, "_last_elogged", None):
            self._notify("還沒有自動記下的失敗案例可補（先用 F1/F2 修，按到第二次會自動記題目，"
                         "改對後再按 F10 補正確答案）")
            return
        cyc = self._cycle
        read_fn = cyc.get("read_fn") if cyc else None
        got = (read_fn or self._read_unit)()    # 重讀目前欄位＝我改好的正確答案
        if got is None:
            return                              # read_fn 已通知（沒抓到文字）
        correct = got[0]
        try:
            ok = logbook.append_correct_answer(correct)
        except Exception as e:
            self._notify(f"補正確答案失敗：{e}")
            return
        if ok == "notfound":
            self._notify(f"找不到對應原題（讀到的「{correct}」長度/讀音對不上任何難例），沒記。"
                         "請把游標移回那句、只改同音錯字再按 F9")
            return
        if ok:
            self._notify(f"已把正確答案補進難例清單（gold）：{correct}" + self._maybe_auto_learn(correct))
        else:
            self._notify("難例清單沒有可補的紀錄")

    def _maybe_auto_learn(self, correct, wrong=None):
        """實驗：自動學詞開啟時，diff 模型改錯的(wrong) ↔ gold(correct)。回傳通知尾段。
        wrong 省略 → 自 error_cases 取最後一筆 output/input（一般欄用）；F6 框直接傳入。"""
        from csc import settings
        if not settings.get("auto_learn"):
            return ""
        from csc import userdict, wordphon
        if wrong is None:
            rec = logbook.case_matching(correct) or {}
            wrong = rec.get("output") or rec.get("input") or ""
        res = userdict.auto_learn_from_diff(wrong, correct)
        up, down, pending = res["up"], res["down"], res["pending"]
        if up or down:
            wordphon.reload_userforce()
        if up:                                          # 自動學常斷錯字 → 留最近的供「剛剛學的字」重挑
            getattr(self, "_note_recent_learned", lambda x: None)([(w, c) for w, _lv, c in up])
        parts = [f"{w}↑{lv}" for w, lv, _c in up] + [f"{w}↓{lv or '忘'}" for w, lv in down]
        if pending:
            self._queue_pending(pending)
            parts.append(f"{len(pending)} 個新詞待確認（右鍵系統匣 → 待確認新詞）")
        if not parts:
            return ""
        self._refresh_menu()
        return "；自動學：" + "、".join(parts)

    # ---- 開啟難例清單：用記事本開（.jsonl 多半沒預設關聯）----
    def _open_errorlog(self, icon=None, item=None):
        try:
            path = logbook.ERROR_FILE
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if not os.path.exists(path):
                open(path, "a", encoding="utf-8").close()
            subprocess.Popen(["notepad.exe", path])
        except Exception as e:
            self._notify(f"開啟失敗：{e}")


# ===== app_exe_v12 =====
# -*- coding: utf-8 -*-
"""繁中自動選字 — 獨立 exe 進入點 v12 = v11 + F9 全域熱鍵切換暫停/恢復熱鍵偵測（追平日常版 v35）。

F9 直接觸發既有的 `_toggle_pause`（同系統匣那顆）。暫停會 UnregisterHotKey 全部熱鍵，所以
F9 必須在暫停時保留，否則無法用 F9 解除 → `keep_vks=(VK_F9,)`（csc/hotkey.py 已支援）。
PyInstaller 進入點（ZhuyinFix.spec）改指向本檔。
"""
import threading

from csc import hotkey


class _App11(_App10):
    def start(self):
        self._box_q = None
        self._box_problem = None
        self.icon.menu = self._build_menu()
        self._hk = hotkey.start_hotkeys_thread({
            hotkey.VK_F1: self._on_f1,
            hotkey.VK_F2: self._on_f2_recorrect,
            hotkey.VK_F3: self._on_f2_learn,
            hotkey.VK_F4: self._on_f3,
            hotkey.VK_F5: self._on_f4_mark,
            hotkey.VK_F6: self._on_f6,
            hotkey.VK_F7: self._on_f7,
            hotkey.VK_F9: self._on_f9_pause,      # 暫停/恢復熱鍵偵測（新）
            hotkey.VK_F10: self._on_logerror,
        }, keep_vks=(hotkey.VK_F9,))
        self.icon.run(setup=self._setup)

    def _on_f9_pause(self):
        threading.Thread(target=self._toggle_pause, daemon=True).start()


# ===== app_exe_v13 =====
# -*- coding: utf-8 -*-
"""繁中自動選字 — 獨立 exe 進入點 v13 = v12 + 引擎換成 OnnxCorrectorV2（追平日常版 v36）。

v1.8 的兩道候選端手術刀（見 csc/reading_filter.py）：
  reading_ratio=0.02   多音字收斂（砍奇怪讀音，斷開假同音：解→界、嗎→馬）
  guard_particles=True 句尾語助詞守門（走吧→走八 這類誤改擋掉）
只換 _load_model 裡的引擎類別，其餘（F1~F10、F9 暫停、F6 框）全沿用 v12。
PyInstaller 進入點（ZhuyinFix.spec）改指向本檔。
"""
from csc.select_corrector_onnx import OnnxCorrectorV2


class _App12(_App11):
    def _load_model(self):
        self.corrector = OnnxCorrectorV2(
            _res("models", "bert.int8.onnx"), _res("models", "vocab.txt"),
            reading_ratio=0.02, guard_particles=True)
        self._install_box_problem_tracker()
        self._set(ICON_READY,
                  f"{APP_TITLE}：就緒（F1改/F2重算/F3學/F4反白/F5標記/F6框/F7前30字/F10記難例）")
        self._notify("就緒：F1 修 · F2 重算 · F3 學 · "
                     "F4 反白 · F5 標記 · F6 輸入框 · F7 前30字 · F10 記難例")


# ===== app_exe_v14 =====
# -*- coding: utf-8 -*-
"""繁中自動選字 — exe 進入點 v14 = v13 + F6 開框自動切繁中注音 + 兩個可記憶勾選（追平日常版 v37/v38）。

- 開 F6 框後另起看守緒，等框視窗(標題含「輸入框」)出現即切輸入法（見 csc/winkeys.switch_to_bopomofo）。
- 系統匣兩個勾選控制行為、存 logs/settings.json（csc/settings），關閉後仍記得：
    「F6 自動切注音輸入法」預設打勾；「F6 自動按 Shift（切中文）」預設不勾（Shift 是切換、不適用所有情境）。
不碰那支 250 行的輸入框程式：用視窗標題搜尋切輸入法、覆寫 _build_menu 加勾選。
PyInstaller 進入點（ZhuyinFix.spec）改指向本檔。
"""
import threading
import time

import pystray

from csc import settings, winkeys as wk, pronoun


class _App13(_App12):
    # ---- F6 開框後自動切繁中注音（依勾選）----
    def _on_f6(self):
        super()._on_f6()
        threading.Thread(target=self._box_to_bopomofo, daemon=True).start()

    def _box_to_bopomofo(self):
        if not settings.get("auto_switch_ime"):
            return
        press_shift = bool(settings.get("auto_press_shift"))
        for _ in range(50):                       # 最多等 ~2.5s 讓框出現並取得焦點
            hwnd = wk.find_window_by_title_substr("輸入框")
            if hwnd:
                time.sleep(0.2)
                wk.switch_to_bopomofo(hwnd, press_shift=press_shift)
                return
            time.sleep(0.05)

    # ---- 系統匣：在「離開」之前插入兩個可記憶勾選 ----
    def _build_menu(self):
        items = list(super()._build_menu())
        ime_items = [
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("F6 自動切注音輸入法", self._toggle_auto_ime,
                             checked=lambda item: bool(settings.get("auto_switch_ime"))),
            pystray.MenuItem("F6 自動按 Shift（切中文模式）", self._toggle_auto_shift,
                             checked=lambda item: bool(settings.get("auto_press_shift"))),
            pystray.MenuItem("自動學詞（實驗）：F9 補正解時學差異詞", self._toggle_auto_learn,
                             checked=lambda item: bool(settings.get("auto_learn"))),
            pystray.MenuItem("人稱用字（目標對象）", pystray.Menu(*self._pronoun_items())),
        ]
        return pystray.Menu(*(items[:-1] + ime_items + items[-1:]))

    def _toggle_auto_ime(self, icon=None, item=None):
        settings.set("auto_switch_ime", not settings.get("auto_switch_ime"))
        self._refresh_menu()

    def _toggle_auto_learn(self, icon=None, item=None):
        settings.set("auto_learn", not settings.get("auto_learn"))
        self._refresh_menu()

    # ---- 人稱用字：7 字分兩組，各勾一個（你/妳；他她它牠祂）----
    def _pronoun_items(self):
        items = [pystray.MenuItem("〔你／妳 擇一〕", None, enabled=False)]
        for ch in pronoun.NI:
            items.append(pystray.MenuItem(ch, self._mk_pronoun("pron_ni", ch),
                         checked=lambda item, ch=ch: settings.get("pron_ni") == ch))
        items.append(pystray.MenuItem("〔他她它牠祂 擇一〕", None, enabled=False))
        for ch in pronoun.TA:
            items.append(pystray.MenuItem(ch, self._mk_pronoun("pron_ta", ch),
                         checked=lambda item, ch=ch: settings.get("pron_ta") == ch))
        items.append(pystray.Menu.SEPARATOR)
        items.append(pystray.MenuItem("✕ 都不指定", self._clear_pronoun))
        return items

    def _mk_pronoun(self, key, ch):
        def toggle(icon=None, item=None):
            settings.set(key, "" if settings.get(key) == ch else ch)   # 再點同字＝取消
            self._refresh_menu()
            self._notify(f"人稱用字：你→{settings.get('pron_ni') or '不指定'}、"
                         f"他→{settings.get('pron_ta') or '不指定'}")
        return toggle

    def _clear_pronoun(self, icon=None, item=None):
        settings.set("pron_ni", "")
        settings.set("pron_ta", "")
        self._refresh_menu()
        self._notify("人稱用字：都不指定")

    def _toggle_auto_shift(self, icon=None, item=None):
        settings.set("auto_press_shift", not settings.get("auto_press_shift"))
        self._refresh_menu()

    def _refresh_menu(self):
        try:
            self.icon.update_menu()
        except Exception:
            pass


# ===== app_exe_v15 =====
# -*- coding: utf-8 -*-
"""exe 進入點 v15 = v14 + 崩潰捕捉(csc/crashlog) + F1/F2/F6 麵包屑。

為抓『隨機閃退』(尤其 F6 框內按 F1)：main() 先 install() 開 faulthandler + 例外鉤子寫
logs/crash.log；F1/F2/F6 留麵包屑(含框開了沒)，對到崩潰前最後動作。純診斷、不改行為。
PyInstaller 進入點(ZhuyinFix.spec) 指向本檔。
"""
from csc import crashlog


class _App14(_App13):
    def _on_f1(self):
        crashlog.log(f"F1 (box={getattr(self, '_box_q', None) is not None})")
        super()._on_f1()

    def _on_f2_recorrect(self):
        crashlog.log(f"F2 (box={getattr(self, '_box_q', None) is not None})")
        super()._on_f2_recorrect()

    def _on_f6(self):
        crashlog.log(f"F6 (box={getattr(self, '_box_q', None) is not None})")
        super()._on_f6()


# ===== app_exe_v16 =====
# -*- coding: utf-8 -*-
"""exe 進入點 v16 = v15 + 系統匣「開機自動啟動」可勾選/可取消（csc/autostart，HKCU Run 機碼）。

勾＝寫 Run 機碼、取消＝刪除，完全可逆、免系統管理員。其餘(校正/F6切注音/勾選/崩潰捕捉)全沿用。
PyInstaller 進入點(ZhuyinFix.spec) 指向本檔。
"""
import pystray

from csc import autostart, crashlog


class _App15(_App14):
    def _build_menu(self):
        items = list(super()._build_menu())
        auto_item = pystray.MenuItem("開機自動啟動", self._toggle_autostart,
                                     checked=lambda item: autostart.is_enabled())
        return pystray.Menu(*(items[:-1] + [auto_item] + items[-1:]))   # 插在「離開」之前

    def _toggle_autostart(self, icon=None, item=None):
        try:
            on = autostart.toggle()
            self._notify("已設為開機自動啟動" if on else "已取消開機自動啟動")
        except Exception as e:
            self._notify(f"設定開機啟動失敗：{e}")
        try:
            self.icon.update_menu()
        except Exception:
            pass


# ===== app_exe_v17 =====
# -*- coding: utf-8 -*-
"""exe v17 = v16 + 修『隨機閃退』根因（v2.0）。

crash.log 分析：F6 框把 Tkinter(Tcl) 跑在非主執行緒；Python 自動循環 GC 在『別的執行緒』
回收到殘留的 Tcl 物件 → Tcl 偵測「被錯誤的執行緒刪除」→ abort 整個行程
（Windows fatal exception 0x80000003，堆疊頂端永遠是 Garbage-collecting）。
修法：
  1. gc.disable()        關掉自動循環 GC —— 那類崩潰只發生在自動 GC，關掉即根除。
  2. 框關閉後 gc.collect() 在『框自己的執行緒』回收其 Tcl 物件 —— 不漏記憶體、不跨緒。
"""
import gc

from csc import crashlog


class _App16(_App15):
    def _run_input_box(self, target_hwnd):
        try:
            super()._run_input_box(target_hwnd)
        finally:
            gc.collect()              # 框關閉後在『框的這條緒』回收其 Tcl 物件


# ===== app_exe_v18 =====
# -*- coding: utf-8 -*-
"""exe v18 = v17 + 系統匣「前往 GitHub」選單項（加在「聯繫作者」下方）。v2.01。"""
import gc
import webbrowser

import pystray

from csc import crashlog

GITHUB_URL = "https://github.com/ncku2026tcsc/tcsc"


class _App17(_App16):
    def _build_menu(self):
        gh = pystray.MenuItem("前往 GitHub（專案頁）", self._open_github)
        out = []
        for it in super()._build_menu():
            out.append(it)
            if (getattr(it, "text", "") or "").startswith("聯繫作者"):
                out.append(gh)                 # 插在「聯繫作者」下方
        return pystray.Menu(*out)

    def _open_github(self, *_):
        try:
            webbrowser.open(GITHUB_URL)
        except Exception:
            pass
        self._notify("已開啟 GitHub 專案頁")


# ===== app_exe_v19 =====
# -*- coding: utf-8 -*-
"""繁中自動選字 — 獨立 exe 進入點 v19 = v18 + 修 bug：F6 輸入框內按 F10 改成「記正確答案(gold)」。

追平日常版 v43。回報：F6 框狀態下 F10 記下的是『題目』而非『正確答案』。
查證：非通知字串寫錯——舊框內路 `_do_log_error_box` 把 `_box_problem`(＝丟進 ranked_corrections
的尾單位＝題目)寫進 input 欄、通知顯示同一變數，兩者必然一致，且根本沒寫 gold 欄。是真行為 bug：
v11 起一般欄 F10 已改「補正確答案」，框內這條路沒跟上。
修法：框開著時 F10 丟 "f10" 進框命令通道，由框 poll()(Tk 緒)呼叫 `_box_log_gold`，把這次難例補齊成
(input=題目, output=模型修正, gold=改好的正確答案)。底層 box(app_exe_v10) 已加向後相容鉤子。
PyInstaller 進入點（ZhuyinFix.spec）改指向本檔。
"""
import gc
import threading

from csc import crashlog, logbook, textutil


class _App18(_App17):
    # ---- F10：框開著 → 記正確答案(gold)；一般欄 → 維持 v11 的補 gold ----
    def _on_logerror(self):
        q = getattr(self, "_box_q", None)
        if q is not None:                         # 框開著：交給框(Tk緒讀框內文字)記正確答案
            try:
                q.put("f10")
            except Exception:
                pass
            return
        threading.Thread(target=self._do_record_correct, daemon=True).start()

    def _box_log_gold(self, text, state, status=None):
        """在框的 Tk 緒內執行（由 poll 經 cmd_q 'f10' 呼叫）。把這次難例補齊：
        input＝題目(被模型改的尾單位)、output＝模型(可能錯)的修正、gold＝我改好的正確答案。"""
        def _say(msg, ok=True):
            if status is not None:
                try:
                    status.config(text=msg, fg="#1a7f37" if ok else "#c0392b")
                    return
                except Exception:
                    pass
            self._notify(msg)

        cyc = state.get("cycle") if state else None
        if not cyc:
            _say("框內還沒做過修正（先按 F1/F2 修、把字改對，再按 F10 記正確答案）", ok=False)
            return
        # 全部讀同一份 state["cycle"]（統一引擎的唯一事實來源）：
        problem = cyc.get("orig")                     # 題目＝這次被模型改的目標
        cands = cyc.get("list") or []
        output = cands[0] if cands else None          # 模型(可能錯)的修正＝best＝list[0]
        # gold＝框內該段「目前實際顯示」的字（循環選的、或你手動打字改的，都抓得到；
        # 比 list[idx] 穩——手動改或 best=原字時 list[idx] 會誤記成原字/題目）
        st, ln = cyc.get("start"), cyc.get("len")
        if isinstance(st, int) and isinstance(ln, int) and 0 <= st <= len(text):
            gold = text[st:st + ln]
        else:
            gold = cands[cyc.get("idx", 0)] if cands else ""
        gold = (gold or "").strip()
        if not gold:
            _say("框內沒有可記錄的內容", ok=False)
            return
        try:
            logbook.log_error_case(problem, output if output and output != problem else None)
            ok = logbook.append_correct_answer(gold)
        except Exception as e:
            _say(f"記錄失敗：{e}", ok=False)
            return
        if ok == "notfound":
            _say("框內這段和原題對不上（長度/讀音），沒記", ok=False)
            return
        _say(f"已記錄正確答案(gold)：{gold}" + self._maybe_auto_learn(gold, wrong=output or problem))


# ===== app_exe_v20 =====
# -*- coding: utf-8 -*-
"""繁中自動選字 — 獨立 exe 進入點 v20 = v19 + 三件事（v2.03），追平日常版 v44：

(1) F6 框內對齊 F4/F7：框開著時 F4＝修反白選取、F7＝前30字整段重修（先前只對齊 F1/F2）。
    框內實作在底層 box 方法 app_exe_v10；本檔把 F4/F7 熱鍵像 F1/F2 一樣轉進框。
(2) gold 自動記錄：循環換候選時，把『目前最後選到的選項』自動補進難例最後一筆的 gold；F10 仍可更新。
(3) F6 框雙擊 Esc 才關閉（實作在 app_exe_v10 的 do_cancel）。
PyInstaller 進入點（ZhuyinFix.spec）改指向本檔。
"""
import gc
import threading

from csc import crashlog, logbook


class _App19(_App18):
    # ---- (1) F4/F7：框開著時轉進框（與 F1/F2 一致）----
    def _on_f3(self):            # F4 ＝ 反白手動修
        q = getattr(self, "_box_q", None)
        if q is not None:
            try:
                q.put("f4")
            except Exception:
                pass
            return
        super()._on_f3()

    def _on_f7(self):            # F7 ＝ 前30字整段重修
        q = getattr(self, "_box_q", None)
        if q is not None:
            try:
                q.put("f7")
            except Exception:
                pass
            return
        super()._on_f7()

    # ---- (2) gold 自動記錄：循環換候選 → gold 跟著『目前最後選到的選項』----
    def _cycle_correct(self, read_fn, kind, cyclekey, force=False):
        before = self._cycle
        before_idx = before["idx"] if before else None
        super()._cycle_correct(read_fn, kind, cyclekey, force)
        cyc = self._cycle
        cycled = cyc is before and before is not None and cyc.get("idx") != before_idx
        if cycled or (force and cyc and cyc.get("list")):        # 換候選、或 F2 重算 → 更新 gold(auto)
            self._autofill_gold()

    def _autofill_gold(self):
        """把『目前最後選到的選項』自動補進難例清單最後一筆的 gold（需先有本階段自動記的失敗案例）。"""
        if not getattr(self, "_last_elogged", None):
            return
        cyc = self._cycle
        if not (cyc and cyc.get("list")):
            return
        try:
            logbook.append_correct_answer(cyc["list"][cyc.get("idx", 0)], src="auto")  # 循環自動補 → auto
        except Exception:
            pass


# ===== app_exe_v21 =====
# -*- coding: utf-8 -*-
"""繁中自動選字 — 獨立 exe 進入點 v21 = v20 + v2.1 大改（追平日常版 v45）：

鍵位重排：F1改字+換選項·F2重算·F3還原回原字(新)·F4改前30字·F5只改反白·F6開框·
          F7學習反白詞·F9更新error cases(補gold)·F10關閉熱鍵(暫停)；移除舊 F5「標記」。
候選 10 個：ranked_corrections top_n 6→10 + char_cand 8→12。
tray 右鍵「使用說明」→ Win32 訊息框（純文字、無 Tk）。
PyInstaller 進入點（ZhuyinFix.spec）改指向本檔。
"""
import ctypes
import gc
import threading

import pystray

from csc import crashlog, hotkey
from csc.usage import USAGE_TEXT


class _App20(_App19):
    def start(self):
        self._box_q = None
        self._box_problem = None
        self.icon.menu = self._build_menu()
        self._hk = hotkey.start_hotkeys_thread({
            hotkey.VK_F1: self._on_f1,            # 改字＋換選項
            hotkey.VK_F2: self._on_f2_recorrect,  # 重算
            hotkey.VK_F3: self._on_restore,       # 還原回原字（新）
            hotkey.VK_F4: self._on_f7,            # 改前30字（原 F7）
            hotkey.VK_F5: self._on_f3,            # 只改反白（原 F4，handler 名 _on_f3）
            hotkey.VK_F6: self._on_f6,            # 開輸入框
            hotkey.VK_F7: self._on_f2_learn,      # 學習反白詞（原 F3）
            hotkey.VK_F8: self._on_confusable,    # 常錯字強制細修（在再/那哪/的得地；還原剪貼簿改到選單）
            hotkey.VK_F9: self._on_logerror,      # 更新 error cases / 補 gold（原 F10）
            hotkey.VK_F10: self._on_f9_pause,     # 關閉/恢復熱鍵（原 F9）
        }, keep_vks=(hotkey.VK_F10,))
        self.icon.run(setup=self._setup)

    def _load_model(self):
        # 暫時靜音 super 的舊鍵位通知（避免啟動跳兩次），只留下面這條 v2.3 的
        _notify = self._notify
        self._notify = lambda *a, **k: None
        try:
            super()._load_model()
        finally:
            self._notify = _notify
        self.corrector.char_cand = 12
        self.corrector.word_cand = 10
        self._wrap_pronoun_pref()                 # 人稱用字偏好：對每個候選強制換 你他→妳她/牠/祂
        self._set(ICON_READY, f"{APP_TITLE}：就緒（右鍵 → 使用說明）")
        self._notify("就緒 v2.3（已縮到右下角系統匣，背景執行中；右鍵有使用說明）\n"
                     " F1 改字 · F2 重算（迭代）· F3 還原 · F4 前30字 · F5 反白 · "
                     "F6 框 · F7 學詞 · F9 記正解 · F10 關熱鍵")

    # ---- F3 還原回原字 ----
    def _on_restore(self):
        q = getattr(self, "_box_q", None)
        if q is not None:
            try:
                q.put("restore")
            except Exception:
                pass
            return
        threading.Thread(target=self._do_restore, daemon=True).start()

    def _do_restore(self):
        cyc = self._cycle
        if not cyc or "orig" not in cyc:
            self._notify("沒有可還原的（先按 F1/F4/F5 改字，再按 F3 還原回原字）")
            return
        read_fn = cyc.get("read_fn")
        got = (read_fn or self._read_unit)()
        if got is None:
            return
        _t, writer = got
        try:
            writer(cyc["orig"])
        except Exception as e:
            self._notify(f"還原失敗：{e}")
            return
        self._last = (cyc["orig"], cyc["orig"])
        try:
            cyc["idx"] = cyc["list"].index(cyc["orig"])
        except (ValueError, KeyError, TypeError):
            pass
        self._notify(f"已還原回原字：{cyc['orig']}")

    # ---- tray 右鍵「使用說明」+「待確認新詞」 ----
    def _build_menu(self):
        items = list(super()._build_menu())
        head = [pystray.MenuItem("使用說明", self._show_help)]   # 待確認新詞移到上層（排在剛剛學之前）
        return pystray.Menu(*(head + [pystray.Menu.SEPARATOR] + items))

    def _refresh_menu(self):
        # 覆寫 v38（只 update_menu 不重建）：結構會變的項目（待確認新詞、學詞計數）需重建選單才會即時反映。
        try:
            self.icon.menu = self._build_menu()
            self.icon.update_menu()
        except Exception:
            pass

    def _show_help(self, icon=None, item=None):
        threading.Thread(
            target=lambda: ctypes.windll.user32.MessageBoxW(
                0, USAGE_TEXT, f"{APP_TITLE} — 使用說明", 0x40),
            daemon=True).start()

    # ---- 自動學詞：詞庫沒有的新詞 → 列候選讓使用者右鍵挑（挑中才存進 %APPDATA% userforce）----
    def _queue_pending(self, pending):
        cur = getattr(self, "_pending_words", None)
        if cur is None:
            cur = self._pending_words = []
        for cands in pending:
            if cands and list(cands) not in cur:
                cur.append(list(cands))
        del cur[:-8]   # 只留最近 8 組：不選＝不學，也不會堆積成一堆

    def _pending_menu_items(self):
        pend = getattr(self, "_pending_words", None)
        if not pend:
            return []
        subs = []
        for cands in pend:
            for c in cands:
                subs.append(pystray.MenuItem(c, self._mk_pick(cands, c)))
            subs.append(pystray.MenuItem("✕ 都不學", self._mk_pick(cands, None)))
            subs.append(pystray.Menu.SEPARATOR)
        return [pystray.MenuItem(f"待確認新詞（{len(pend)}）", pystray.Menu(*subs))]

    def _mk_pick(self, cands, word):
        key = tuple(cands)
        return lambda icon, item: self._pick_pending(key, word)

    def _pick_pending(self, key, word):
        pend = getattr(self, "_pending_words", [])
        for i, c in enumerate(pend):
            if tuple(c) == key:
                del pend[i]
                break
        if word:
            from csc import userdict, wordphon
            _st, lv, _msg = userdict.learn(word)
            wordphon.reload_userforce()
            self._notify(f"已學「{word}」：強度 {lv}（待確認清單移除此項）")
        else:
            self._notify("已略過此新詞（不學）")
        self._refresh_menu()

    # ---- 人稱用字偏好：包一層 ranked_corrections，對每個候選強制換部首 ----
    def _wrap_pronoun_pref(self):
        from csc import settings, pronoun
        orig = self.corrector.ranked_corrections

        def wrapped(text, *a, **k):
            ranked = orig(text, *a, **k)
            ni, ta = settings.get("pron_ni"), settings.get("pron_ta")
            if not ni and not ta:
                return ranked
            out, seen = [], set()
            for c in ranked:                       # 偏好版優先（預設套用）
                m = pronoun.apply_pref(c, ni, ta)
                if m not in seen:
                    seen.add(m)
                    out.append(m)
            for c in ranked:                       # 再附原版，F1 可循環回去（多人句可救回）
                if c not in seen:
                    seen.add(c)
                    out.append(c)
            return out
        self.corrector.ranked_corrections = wrapped


# ===== app_exe_v22 =====
# -*- coding: utf-8 -*-
"""繁中自動選字 — 獨立 exe 進入點 v22 = v21 + v2.3b（追平日常版 v46）：

改字通知「合併顯示」開關（實驗）：把『位置相鄰』的改動黏成一段、不相鄰的仍分開。
  關（預設，＝v2.3a）：勿→物、鞭→鞕
  開：              勿鞭→物鞕；勿鞭→物鞕、客→刻

字串格式化抽到 csc/editfmt.fmt_edits()，由設定 notify_group 決定（旗標關＝逐位元同舊）；
統一引擎 app_exe_v9._cycle_correct + 終端機 F4（app_exe_v8）那兩處改呼叫 editfmt。
本檔只負責：右鍵加開關 + 版本字串改 v2.3b。設定存 %APPDATA%\\tcsc\\settings.json，
預設關（release 不含此檔 → 公眾吃預設關）。PyInstaller 進入點（ZhuyinFix.spec）改指向本檔。
"""
import gc

import pystray

from csc import crashlog, settings


class _App21(_App20):
    def _load_model(self):
        # 靜音 v21 的「就緒 v2.3」那條（v21 內部已先靜音它的 super），改報 v2.3b
        _notify = self._notify
        self._notify = lambda *a, **k: None
        try:
            super()._load_model()
        finally:
            self._notify = _notify
        self._notify("就緒 v2.3b（新增：通知合併顯示，右鍵可切換）\n"
                     " F1 改字 · F2 重算 · F3 還原 · F4 前30字 · F5 反白 · "
                     "F6 框 · F7 學詞 · F9 記正解 · F10 關熱鍵")

    def _build_menu(self):
        base_items = list(super()._build_menu())
        toggle = pystray.MenuItem(
            "通知合併顯示：相鄰改動黏成一段（預設開）", self._toggle_notify_group,
            checked=lambda item: bool(settings.get("notify_group")))
        return pystray.Menu(toggle, pystray.Menu.SEPARATOR, *base_items)

    def _toggle_notify_group(self, icon=None, item=None):
        settings.set("notify_group", not settings.get("notify_group"))
        on = settings.get("notify_group")
        self._notify("通知合併顯示：開（相鄰改動黏成一段，如 勿鞭→物鞕）" if on
                     else "通知合併顯示：關（恢復逐字：勿→物、鞭→鞕）")
        self._refresh_menu()


# ===== app_exe_v23 =====
# -*- coding: utf-8 -*-
"""繁中自動選字 — 獨立 exe 進入點 v23 = v22 + v2.31（追平日常版 v47）：

抓欄位文字失敗時自動重抓一次（第二次也失敗才報「沒抓到文字」）。`_grab_window()` 第一次回
None 就稍等再抓一次，仍 None 才交給上層通知（_read_unit/_read_win 的訊息不變、只在重抓也失敗才跳）。
單點覆寫即涵蓋 F1/F2（_read_unit）與 F4 前30字（_read_win）。

v2.31 另含（不在本檔）：通知合併顯示改預設開（csc/settings.py）、F7 學詞通知對齊 F9 報等級
（app_exe_v8._do_learn_word：F3→F7、印『強度 level/cap』）。本檔只負責重抓 + 版本字串。
PyInstaller 進入點（ZhuyinFix.spec）改指向本檔。
"""
import gc
import time

from csc import crashlog


class _App22(_App21):
    def _grab_window(self):
        w = super()._grab_window()
        if w is None:                 # 第一次沒抓到 → 給前景/剪貼簿一點時間，再抓一次
            time.sleep(0.12)
            w = super()._grab_window()
        return w

    def _load_model(self):
        _notify = self._notify
        self._notify = lambda *a, **k: None      # 靜音 v22 的「就緒 v2.3b」，改報 v2.31
        try:
            super()._load_model()
        finally:
            self._notify = _notify
        self._notify("就緒 v2.31（抓不到字會自動重試一次；通知合併顯示預設開，右鍵可關）\n"
                     " F1 改字 · F2 重算 · F3 還原 · F4 前30字 · F5 反白 · "
                     "F6 框 · F7 學詞 · F9 記正解 · F10 關熱鍵")


# ===== app_exe_v24 =====
# -*- coding: utf-8 -*-
"""繁中自動選字 — 獨立 exe 進入點 v24 = v23 + v2.32（追平日常版 v48）：

根治『校正後貼上偶爾貼到舊剪貼簿內容』的讀取端競態（v22 只修了寫入端）。Ctrl+V 後不立刻還原，
讓校正後的新內容在剪貼簿多留 ~0.8s（慢的程式也讀得到正確內容），再背景還原使用者剪貼簿；配
世代守衛，連續校正不互相蓋、還原的是使用者真正的原內容。貼上前再 reconfirm 一次。實作在
csc/clipsafe；F1/F2/F4/F5 都走 _replace_window/_paste_selection，一次修好；F6 框不碰系統剪貼簿。
PyInstaller 進入點（ZhuyinFix.spec）改指向本檔。
"""
import gc
import time

from csc import crashlog, winkeys as wk, textutil, clipsafe


class _App23(_App22):
    def _replace_window(self, new_window):
        new_window = new_window.replace("\r\n", "\n").replace("\n", "\r\n")
        if not clipsafe.begin_paste(self, new_window):
            raise RuntimeError("剪貼簿被佔用，沒貼成功，請再按一次 F1")
        wk.select_left(GRAB_CHARS)
        time.sleep(0.05)
        clipsafe.reconfirm(self, new_window)     # 貼上前再確認剪貼簿沒被蓋掉
        wk.combo(wk.VK_CONTROL, wk.VK_V)
        time.sleep(0.12)                         # 短 settle；新內容留在剪貼簿，由延遲還原顧讀取端
        clipsafe.end_paste(self)

    def _paste_selection(self, text, reselect=True):
        text = text.replace("\r\n", "\n").replace("\n", "\r\n")
        if not clipsafe.begin_paste(self, text):
            raise RuntimeError("剪貼簿被佔用，沒貼成功，請再按一次 F5")
        clipsafe.reconfirm(self, text)
        wk.combo(wk.VK_CONTROL, wk.VK_V)
        time.sleep(0.12)
        if reselect:
            wk.select_left(textutil.utf16_len(text))
        clipsafe.end_paste(self)

    def _load_model(self):
        _notify = self._notify
        self._notify = lambda *a, **k: None      # 靜音 v23 的「就緒 v2.31」，改報 v2.32
        try:
            super()._load_model()
        finally:
            self._notify = _notify
        self._notify("就緒 v2.32（修好『貼上偶爾貼到舊內容』；抓不到字會重試；通知合併顯示）\n"
                     " F1 改字 · F2 重算 · F3 還原 · F4 前30字 · F5 反白 · "
                     "F6 框 · F7 學詞 · F9 記正解 · F10 關熱鍵")


# ===== app_exe_v25 =====
# -*- coding: utf-8 -*-
"""繁中自動選字 — 獨立 exe 進入點 v25 = v24 + v2.33（實驗，追平日常版 v49）：

改字「直接打字」——不經剪貼簿、根除貼上競態。選好取代區域後用 SendInput Unicode（wk.type_text，
繞過注音 IME、F6 框已在用）把校正後的字直接打進去（送什麼就是什麼、零剪貼簿足跡）。
動到核心、屬實驗：開關 `direct_type`（系統匣切換），**預設關**（公眾走證實穩的 v2.32 剪貼簿路徑），
即時可退回。**有換行**（聊天室 Enter 會誤送）→ 自動退回剪貼簿路徑。只改『寫回』，抓字仍用剪貼簿讀取。
PyInstaller 進入點（ZhuyinFix.spec）改指向本檔。
"""
import gc
import time

import pystray

from csc import crashlog, winkeys as wk, textutil, settings


class _App24(_App23):
    @staticmethod
    def _can_type(t):
        return bool(settings.get("direct_type")) and t and "\n" not in t and "\r" not in t

    def _replace_window(self, new_window):
        if self._can_type(new_window):
            wk.select_left(GRAB_CHARS)        # 反白與抓取相同格數（打字會取代選取）
            time.sleep(0.04)                  # 等選取落地再打字
            wk.type_text(new_window)          # 直接打字、完全不碰剪貼簿
            return
        super()._replace_window(new_window)   # 有換行/開關關 → v2.32 安全剪貼簿路徑

    def _paste_selection(self, text, reselect=True):
        if self._can_type(text):
            wk.type_text(text)
            if reselect:
                wk.select_left(textutil.utf16_len(text))   # 重新反白供循環（同剪貼簿路徑）
            return
        super()._paste_selection(text, reselect)

    def _build_menu(self):
        base_items = list(super()._build_menu())
        toggle = pystray.MenuItem(
            "直接打字（實驗）：不經剪貼簿、根除貼上競態", self._toggle_direct_type,
            checked=lambda item: bool(settings.get("direct_type")))
        return pystray.Menu(toggle, pystray.Menu.SEPARATOR, *base_items)

    def _toggle_direct_type(self, icon=None, item=None):
        settings.set("direct_type", not settings.get("direct_type"))
        on = settings.get("direct_type")
        self._notify("直接打字：開（改字直接打進去、不碰剪貼簿；有換行仍走剪貼簿）" if on
                     else "直接打字：關（改回 v2.32 剪貼簿貼上）")
        self._refresh_menu()

    def _load_model(self):
        _notify = self._notify
        self._notify = lambda *a, **k: None      # 靜音 v24 的「就緒 v2.32」，改報 v2.33
        try:
            super()._load_model()
        finally:
            self._notify = _notify
        self._notify("就緒 v2.33（實驗：改字可直接打字、不經剪貼簿，右鍵切換）\n"
                     " F1 改字 · F2 重算 · F3 還原 · F4 前30字 · F5 反白 · "
                     "F6 框 · F7 學詞 · F9 記正解 · F10 關熱鍵")


# ===== app_exe_v26 =====
# -*- coding: utf-8 -*-
"""繁中自動選字 — 獨立 exe 進入點 v26 = v25 + v2.4 大改版（追平日常版 v50）：

改字「貼上方式」二選一，預設模式1：
  模式1（預設）＝一律直接打字（SendInput Unicode、繞注音 IME、完全不碰剪貼簿）——含多行：
    換行正規化成 \\n 直接打入（Unicode 換行不會像 Enter 鍵那樣誤送訊息）。
  模式2          ＝一律剪貼簿貼上（v2.32 延遲還原+世代守衛安全路徑，相容性最高）。
承 v2.33 但改成乾淨二選一（v2.33 是單行打字/多行剪貼簿的混合，模式不純粹）。設定 `direct_type`
（True=模式1）存 %APPDATA%；某 app 多行壓成一行/打不進去 → 系統匣切模式2。只改寫回，抓字仍用剪貼簿。
PyInstaller 進入點（ZhuyinFix.spec）改指向本檔。
"""
import gc
import time

import pystray

from csc import crashlog, winkeys as wk, textutil, settings


class _App25(_App24):
    def _replace_window(self, new_window):
        if settings.get("direct_type"):
            text = new_window.replace("\r\n", "\n").replace("\r", "\n")   # 打字用乾淨 \n
            wk.select_left(GRAB_CHARS)
            time.sleep(0.04)
            wk.type_text(text)                # 直接打字、完全不碰剪貼簿（含多行）
            return
        super()._replace_window(new_window)   # 模式2：剪貼簿（v25→v24 clipsafe）

    def _paste_selection(self, text, reselect=True):
        if settings.get("direct_type"):
            t = text.replace("\r\n", "\n").replace("\r", "\n")
            wk.type_text(t)
            if reselect:
                wk.select_left(textutil.utf16_len(t))
            return
        super()._paste_selection(text, reselect)

    def _build_menu(self):
        # super(app_exe_v25,...)：跳過 v25 的單一開關層，接 v22 的選單（含通知合併開關等）
        base_items = list(super(_App24, self)._build_menu())
        mode = pystray.MenuItem("改字方式（貼上模式）", pystray.Menu(
            pystray.MenuItem("模式①　直接打字（不經剪貼簿，預設）",
                             lambda i, it: self._set_direct(True),
                             checked=lambda item: bool(settings.get("direct_type")), radio=True),
            pystray.MenuItem("模式②　剪貼簿貼上（相容性高）",
                             lambda i, it: self._set_direct(False),
                             checked=lambda item: not bool(settings.get("direct_type")), radio=True),
        ))
        return pystray.Menu(mode, pystray.Menu.SEPARATOR, *base_items)

    def _set_direct(self, on):
        settings.set("direct_type", bool(on))
        self._notify("改字方式 → 模式①直接打字（不經剪貼簿、含多行）" if on
                     else "改字方式 → 模式②剪貼簿貼上（相容性高）")
        self._refresh_menu()

    def _load_model(self):
        _notify = self._notify
        self._notify = lambda *a, **k: None      # 靜音 v25 的「就緒 v2.33」，改報 v2.4
        try:
            super()._load_model()
        finally:
            self._notify = _notify
        self._notify("就緒 v2.4（改字方式可選：模式①直接打字／模式②剪貼簿，右鍵切換）\n"
                     " F1 改字 · F2 重算 · F3 還原 · F4 前30字 · F5 反白 · "
                     "F6 框 · F7 學詞 · F9 記正解 · F10 關熱鍵")


# ===== app_exe_v27 =====
# -*- coding: utf-8 -*-
"""繁中自動選字 — 獨立 exe 進入點 v27 = v26 + v2.41（追平日常版 v51）：

模式順序對調＋預設改剪貼簿＋新增「清空剪貼簿」。實測「直接打字」用 Unicode 注入吞換行（多行壓成
一行）→ 不適合當預設。所以：預設改回剪貼簿（相容、支援換行）且排第一（①）；直接打字排第二（②）並
標註「不支援換行」（單行情境想完全不碰剪貼簿的進階選項）；新增「清空剪貼簿（卡住時用）」手動救援。
設定 `direct_type`（False=剪貼簿，預設）。只改選單與預設；兩條寫回路徑沿用 v26。
PyInstaller 進入點（ZhuyinFix.spec）改指向本檔。
"""
import gc

import pystray

from csc import crashlog, settings


class _App26(_App25):
    def _build_menu(self):
        # super(base25,...)：跳過 v26 的舊順序模式選單與 v25 的單一開關，接 v22 選單（含通知合併）
        base_items = list(super(_App24, self)._build_menu())
        mode = pystray.MenuItem("改字方式（貼上模式）", pystray.Menu(
            pystray.MenuItem("模式①　剪貼簿貼上（相容、支援換行，預設）",
                             lambda i, it: self._set_direct(False),
                             checked=lambda item: not bool(settings.get("direct_type")), radio=True),
            pystray.MenuItem("模式②　直接打字（不經剪貼簿，不支援換行）",
                             lambda i, it: self._set_direct(True),
                             checked=lambda item: bool(settings.get("direct_type")), radio=True),
        ))
        clearclip = pystray.MenuItem("清空剪貼簿（卡住時用）", self._clear_clipboard)
        return pystray.Menu(mode, clearclip, pystray.Menu.SEPARATOR, *base_items)

    def _set_direct(self, on):
        settings.set("direct_type", bool(on))
        self._notify("改字方式 → 直接打字（不經剪貼簿；注意：不支援換行）" if on
                     else "改字方式 → 剪貼簿貼上（相容、支援換行，預設）")
        self._refresh_menu()

    def _clear_clipboard(self, icon=None, item=None):
        try:
            self._set_clip("")
            self._notify("已清空剪貼簿（若剛剛貼上卡到怪內容，這樣可即時救援）")
        except Exception as e:
            self._notify(f"清空剪貼簿失敗：{e}")

    def _load_model(self):
        _notify = self._notify
        self._notify = lambda *a, **k: None      # 靜音 v26 的「就緒 v2.4」，改報 v2.41
        try:
            super()._load_model()
        finally:
            self._notify = _notify
        self._notify("就緒 v2.41（改字預設剪貼簿；可切「直接打字」不經剪貼簿但不支援換行；可清空剪貼簿）\n"
                     " F1 改字 · F2 重算 · F3 還原 · F4 前30字 · F5 反白 · "
                     "F6 框 · F7 學詞 · F9 記正解 · F10 關熱鍵")


# ===== app_exe_v28 =====
# -*- coding: utf-8 -*-
"""繁中自動選字 — 獨立 exe 進入點 v28 = v27 + v2.5（追平日常版 v52）：

直接打字模式的換行改用 **Shift+Enter（軟換行）** → 兩個模式都完整支援多行。寫回時把文字依 \\n 切段、
逐段 type_text，段與段之間送一次 Shift+Enter（多數編輯器/聊天室當軟換行、不會送出訊息）。
選單拿掉「不支援換行」標註；「清空剪貼簿」改名「改字怪怪的？點我清空剪貼簿」；使用說明加「卡住了？」段
（csc/usage.py，共用）。兩模式都保留、預設仍剪貼簿（相容性最高）。
PyInstaller 進入點（ZhuyinFix.spec）改指向本檔。
"""
import gc
import time

import pystray

from csc import crashlog, winkeys as wk, textutil, settings


VK_RETURN = 0x0D


class _App27(_App26):
    def _type_keep_newlines(self, text):
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        for k, seg in enumerate(text.split("\n")):
            if k:
                wk.combo(wk.VK_SHIFT, VK_RETURN)     # 軟換行：Shift+Enter（多數 app 不會送出）
                time.sleep(0.01)
            if seg:
                wk.type_text(seg)

    def _replace_window(self, new_window):
        if settings.get("direct_type"):
            wk.select_left(GRAB_CHARS)
            time.sleep(0.04)
            self._type_keep_newlines(new_window)
            return
        super()._replace_window(new_window)          # 模式①→ v26→v24 剪貼簿

    def _paste_selection(self, text, reselect=True):
        if settings.get("direct_type"):
            self._type_keep_newlines(text)
            if reselect:
                wk.select_left(textutil.utf16_len(text.replace("\r\n", "\n").replace("\r", "\n")))
            return
        super()._paste_selection(text, reselect)

    def _build_menu(self):
        base_items = list(super(_App24, self)._build_menu())   # 跳過 v27/v26 的舊模式選單層
        mode = pystray.MenuItem("改字方式（貼上模式）", pystray.Menu(
            pystray.MenuItem("模式①　剪貼簿貼上（相容，預設）",
                             lambda i, it: self._set_direct(False),
                             checked=lambda item: not bool(settings.get("direct_type")), radio=True),
            pystray.MenuItem("模式②　直接打字（不經剪貼簿、換行用 Shift+Enter）",
                             lambda i, it: self._set_direct(True),
                             checked=lambda item: bool(settings.get("direct_type")), radio=True),
        ))
        clearclip = pystray.MenuItem("改字怪怪的？點我清空剪貼簿", self._clear_clipboard)
        return pystray.Menu(mode, clearclip, pystray.Menu.SEPARATOR, *base_items)

    def _set_direct(self, on):
        settings.set("direct_type", bool(on))
        self._notify("改字方式 → 直接打字（不經剪貼簿、換行用 Shift+Enter）" if on
                     else "改字方式 → 剪貼簿貼上（相容、支援換行，預設）")
        self._refresh_menu()

    def _load_model(self):
        _notify = self._notify
        self._notify = lambda *a, **k: None          # 靜音 v27 的「就緒 v2.41」，改報 v2.5
        try:
            super()._load_model()
        finally:
            self._notify = _notify
        self._notify("就緒 v2.5（兩種改字方式：剪貼簿／直接打字，皆支援換行；右鍵可切換、可清空剪貼簿）\n"
                     " F1 改字 · F2 重算 · F3 還原 · F4 前30字 · F5 反白 · "
                     "F6 框 · F7 學詞 · F9 記正解 · F10 關熱鍵")


# ===== app_exe_v29 =====
# -*- coding: utf-8 -*-
"""繁中自動選字 — 獨立 exe 進入點 v29 = v28 + v2.51 小修（追平日常版 v53）：

就緒通知簡潔化（不提兩種改字模式，使用者不必知道）。配合 APP_TITLE 拿掉版本號（app_exe.py，
通知標題/tooltip/說明標題共用）→ 通知標題不再卡在舊版本。其餘（Shift+Enter 換行、模式選單、
清空剪貼簿、卡住了？說明）皆沿用 v28。PyInstaller 進入點（ZhuyinFix.spec）改指向本檔。
"""
import gc

from csc import crashlog


class _App28(_App27):
    def _load_model(self):
        _notify = self._notify
        self._notify = lambda *a, **k: None      # 靜音 v28 的就緒通知，改報簡潔版
        try:
            super()._load_model()
        finally:
            self._notify = _notify
        self._notify("就緒（已在背景執行，右鍵有使用說明）\n"
                     " F1 改字 · F2 重算 · F3 還原 · F4 前30字 · F5 反白 · "
                     "F6 框 · F7 學詞 · F9 記正解 · F10 關熱鍵")


# ===== app_exe_v30 =====
# -*- coding: utf-8 -*-
"""繁中自動選字 — 獨立 exe 進入點 v30 = v29 + v2.52（追平日常版 v54）：

修「模式②直接打字遇多行越換越多行」：直接打字是「選游標前 50 格→重打整段」，多行時選取格數
（換行算 1 格）和抓回字串長度（換行＝\\r\\n 兩字元）對不齊 → 行數累加。修法：**模式②只在單行打字**
（快、不碰剪貼簿）；**多行自動走剪貼簿**（v2.32 clipsafe 原子取代、可靠）。模式①本就走剪貼簿、支援多行。
版本號改由 csc/version.py 單一來源帶進 APP_TITLE（app_exe.py），標題不再卡舊版本。
PyInstaller 進入點（ZhuyinFix.spec）改指向本檔。
"""
import gc
import time

import pystray

from csc import crashlog, winkeys as wk, textutil, settings


class _App29(_App28):
    @staticmethod
    def _has_nl(t):
        return ("\n" in t) or ("\r" in t)

    def _replace_window(self, new_window):
        if settings.get("direct_type") and new_window and not self._has_nl(new_window):
            wk.select_left(GRAB_CHARS)            # 單行直接打字、完全不碰剪貼簿
            time.sleep(0.04)
            wk.type_text(new_window)
            return
        _App23._replace_window(self, new_window)   # 多行/模式①→ clipsafe 剪貼簿（原子取代、可靠）

    def _paste_selection(self, text, reselect=True):
        if settings.get("direct_type") and text and not self._has_nl(text):
            wk.type_text(text)
            if reselect:
                wk.select_left(textutil.utf16_len(text))
            return
        _App23._paste_selection(self, text, reselect)

    def _build_menu(self):
        base_items = list(super(_App24, self)._build_menu())   # 跳過各舊版模式選單層，接 v22（含通知合併）
        mode = pystray.MenuItem("改字方式（貼上模式）", pystray.Menu(
            pystray.MenuItem("模式①　剪貼簿貼上（相容，預設）",
                             lambda i, it: self._set_direct(False),
                             checked=lambda item: not bool(settings.get("direct_type")), radio=True),
            pystray.MenuItem("模式②　直接打字（不經剪貼簿）",
                             lambda i, it: self._set_direct(True),
                             checked=lambda item: bool(settings.get("direct_type")), radio=True),
        ))
        clearclip = pystray.MenuItem("改字怪怪的？點我清空剪貼簿", self._clear_clipboard)
        return pystray.Menu(mode, clearclip, pystray.Menu.SEPARATOR, *base_items)

    def _set_direct(self, on):
        settings.set("direct_type", bool(on))
        self._notify("改字方式 → 直接打字（不經剪貼簿；多行會自動改用剪貼簿）" if on
                     else "改字方式 → 剪貼簿貼上（相容、支援換行，預設）")
        self._refresh_menu()


# ===== app_exe_v31 =====
# -*- coding: utf-8 -*-
"""繁中自動選字 — 獨立 exe 進入點 v31 = v30 + v2.53（追平日常版 v55）：

(A) F1/F2 直接打字支援多行：_read_unit 改成只重打『被改的那段 unit+tail』（在最後一個分隔符／換行
    之後、不含換行、等長 → 選取精準、不碰前面行與換行）。F4/F5 抓的範圍可能跨行，維持 v30。
(B) 「剛剛學的字」選單（照抄「待確認新詞」批准選單）：自動學常斷錯字，保留最近 2 個自動學到的詞＋
    候選，可在系統匣重挑正確斷詞或移除。候選由 userdict.auto_learn_from_diff 的 up 帶出。
PyInstaller 進入點（ZhuyinFix.spec）改指向本檔。
"""
import gc
import time

import pystray

from csc import crashlog, winkeys as wk, textutil, settings


class _App30(_App29):
    # ===== (A) F1/F2 直接打字：只重打 break-free 的 unit+tail =====
    def _read_unit(self):
        if not settings.get("direct_type"):
            return super()._read_unit()
        time.sleep(0.08)
        window = self._grab_window()
        if window is None:
            self._notify("沒抓到文字（換個輸入欄試試）"); return None
        unit, tail = textutil.split_tail_unit(window)
        if not unit.strip():
            self._notify("沒抓到要修的句子"); return None
        return unit, lambda new: self._type_replace(unit + tail, new + tail)

    def _type_replace(self, old, new):
        wk.select_left(textutil.utf16_len(old))   # 選「被改的那段」（break-free、等長 → 精準）
        time.sleep(0.04)
        wk.type_text(new)

    # ===== (B) 剛剛學的字（照抄「待確認新詞」批准選單）=====
    def _note_recent_learned(self, pairs):
        cur = getattr(self, "_recent_learned", None)
        if cur is None:
            cur = self._recent_learned = []
        for w, cands in pairs:
            cur[:] = [(x, c) for (x, c) in cur if x != w]
            cur.append((w, list(cands)))
        del cur[:-8]                                     # 留最近 8 個（對齊待確認新詞）

    def _recent_menu_items(self):
        rec = getattr(self, "_recent_learned", None)
        if not rec:
            return []
        subs = []
        for word, cands in rec:
            opts = [word] + [c for c in cands if c != word]
            for c in opts:
                subs.append(pystray.MenuItem(("✓ " if c == word else "　") + c,
                                             self._mk_repick(word, c)))
            subs.append(pystray.MenuItem("✕ 移除（剛剛學錯了）", self._mk_repick(word, None)))
            subs.append(pystray.Menu.SEPARATOR)
        return [pystray.MenuItem(f"剛剛學的字（{len(rec)}）", pystray.Menu(*subs))]

    def _mk_repick(self, learned, choice):
        return lambda icon, item: self._repick_learned(learned, choice)

    def _repick_learned(self, learned, choice):
        from csc import userdict, wordphon
        rec = getattr(self, "_recent_learned", [])
        if choice == learned:
            self._notify(f"「{learned}」維持不變"); return
        userdict.remove(learned)
        if choice:
            _st, lv, _msg = userdict.learn(choice)
            msg = f"已改學「{choice}」（強度 {lv}）、移除「{learned}」"
        else:
            msg = f"已移除剛剛學的「{learned}」"
        wordphon.reload_userforce()
        self._recent_learned[:] = [(w, c) for (w, c) in rec if w != learned]
        self._notify(msg)
        self._refresh_menu()

    # ===== 選單 =====
    def _build_menu(self):
        base_items = list(super(_App24, self)._build_menu())   # 跳過各舊版模式選單層，接 v22
        mode = pystray.MenuItem("改字方式（貼上模式）", pystray.Menu(
            pystray.MenuItem("模式①　剪貼簿貼上（相容，預設）",
                             lambda i, it: self._set_direct(False),
                             checked=lambda item: not bool(settings.get("direct_type")), radio=True),
            pystray.MenuItem("模式②　直接打字（不支援全形標點，遇標點自動切換為貼上）",
                             lambda i, it: self._set_direct(True),
                             checked=lambda item: bool(settings.get("direct_type")), radio=True),
        ))
        clearclip = pystray.MenuItem("改字怪怪的？點我清空剪貼簿", self._clear_clipboard)
        restoreclip = pystray.MenuItem("還原我剛剛複製的內容到剪貼簿", self._on_f8)
        autoclear = pystray.MenuItem("改字後自動清空剪貼簿", self._toggle_auto_clear,
                                     checked=lambda item: bool(settings.get("auto_clear_clip")))
        autorestore = pystray.MenuItem("用過後 30 秒自動還原你的剪貼簿", self._toggle_auto_restore,
                                       checked=lambda item: bool(settings.get("auto_restore_clip")))
        wrapfix = pystray.MenuItem("自動折行補選字（慢的話可關）", self._toggle_wrap_fix,
                                   checked=lambda item: bool(settings.get("wrap_fix")))
        try:
            _nw = len(userdict.entries_by_word())
        except Exception:
            _nw = 0
        manage = pystray.MenuItem(f"管理我學的詞…（共 {_nw}）", self._on_manage)
        pending = self._pending_menu_items()      # 待確認新詞（排在剛剛學之上）
        recent = self._recent_menu_items()        # 剛剛學的字
        return pystray.Menu(mode, clearclip, restoreclip, autoclear, autorestore, wrapfix, manage,
                            *pending, *recent, pystray.Menu.SEPARATOR, *base_items)

    def _toggle_auto_clear(self, icon=None, item=None):
        on = not settings.get("auto_clear_clip")
        settings.set("auto_clear_clip", on)
        self._notify("改字後自動清空剪貼簿：開（改完不還原你的剪貼簿、直接清空）" if on
                     else "改字後自動清空剪貼簿：關（改回還原你原本的剪貼簿，預設）")
        self._refresh_menu()

    def _toggle_auto_restore(self, icon=None, item=None):
        on = not settings.get("auto_restore_clip")
        settings.set("auto_restore_clip", on)
        self._notify("用過後 30 秒自動還原剪貼簿：開（改完 30 秒沒再動作，就把你原本複製的內容還原回來；期間又動作會重新倒數）" if on
                     else "用過後 30 秒自動還原剪貼簿：關（要還原請按 F8）")
        self._refresh_menu()

    def _toggle_wrap_fix(self, icon=None, item=None):
        on = not settings.get("wrap_fix")
        settings.set("wrap_fix", on)
        self._notify("自動折行補選字：開（claude.ai／gemini 自動折行時不再疊字；每次 F1 多一次剪貼簿來回、稍慢）" if on
                     else "自動折行補選字：關（F1 較快，但 claude.ai／gemini 自動折行的那句可能少改一格）")
        self._refresh_menu()

    def _set_direct(self, on):
        settings.set("direct_type", bool(on))
        self._notify("改字方式 → 直接打字（不支援全形標點，遇標點會自動切換為貼上）" if on
                     else "改字方式 → 剪貼簿貼上（相容、支援換行，預設）")
        self._refresh_menu()


# ===== app_exe_v32 =====
# -*- coding: utf-8 -*-
"""繁中自動選字 — 獨立 exe 進入點 v32 = v31 + v2.54（追平日常版 v56）：

F1/F2 多行修好（兩種模式）——只取代「被改的那段」unit+tail（最後一個分隔符之後、break-free、與校正
等長），`select_left(utf16_len(unit+tail))` 精準選那段，再用目前模式打字或剪貼簿貼上 new+tail，
完全不碰前面的行與換行。病根：抓取拿不到換行時 prefix 變空，但寫回 select_left(50) 往回多選了前面
幾行、貼上單行內容 → 壓成一行；只取代被改那段即可避開（兩模式皆安全）。F4/F5 抓的範圍跨行，維持原樣。
PyInstaller 進入點（ZhuyinFix.spec）改指向本檔。
"""
import gc
import time

from csc import crashlog, winkeys as wk, textutil, settings


class TrayApp(_App30):
    def _read_unit(self):
        time.sleep(0.08)
        window = self._grab_window()
        if window is None:
            self._notify("沒抓到文字（換個輸入欄試試）"); return None
        unit, tail = textutil.split_tail_unit(window)
        if not unit.strip():
            self._notify("沒抓到要修的句子"); return None
        return unit, lambda new: self._write_unit(unit + tail, new + tail)

    def _write_unit(self, old, new):
        wk.select_left(textutil.utf16_len(old))
        time.sleep(0.04)
        self._extend_if_wrap_short(old)   # 自動折行(soft-wrap)少選一格→補選，杜絕疊字
        if settings.get("direct_type") and not wk.has_ime_punct(new):
            wk.type_text(new)                                            # 模式②直接打字（無全形標點才用）
        else:
            _App23._paste_selection(self, new, reselect=False)   # 模式①剪貼簿（含標點→貼上，繞過注音吃字）

    def _extend_if_wrap_short(self, old):
        """claude.ai / gemini 等『自動折行(soft-wrap)』時，Shift+← 跨折行處會多吃一格(caret 換行 affinity)，
        使選取比 old 少最左幾格 → 貼回後最左字沒被蓋到＝疊字（症狀：沒手動換行、字溢到下一行就少一格）。
        非破壞性修正：複製目前選取比對——只有『確定選到的正好是 old 去掉最左 n 格(old.endswith(sel))』才補按
        n 次 Shift+←；確認不了(空/逾時/對不上)就完全不動，維持原行為、不惡化。序列化(_op_lock)下不會與別的操作重疊。
        只做幾何補正、不碰校正決策（純觀察者原則）。可在系統匣關閉（嫌每次 F1 多一次剪貼簿來回太慢）。"""
        if not settings.get("wrap_fix"):
            return                              # 使用者關掉了折行補選（嫌慢）
        want = old.replace("\r\n", "").replace("\r", "").replace("\n", "")
        if len(want) < 2:
            return                              # 太短：補選的誤判風險大於效益
        try:
            pre = self._get_clip()
            self._set_clip(SENTINEL)
            time.sleep(0.02)
            wk.combo(wk.VK_CONTROL, wk.VK_C)
            got = self._poll_clip(timeout=0.5)  # 短逾時：折行的瀏覽器複製很快，慢的 app 對不上就跳過
            self._set_clip(pre)                 # 還原，避免污染 clipsafe 的『使用者剪貼簿』判斷
        except Exception:
            return
        if not got or got == SENTINEL:
            return
        sel = got.replace("\r\n", "").replace("\r", "").replace("\n", "")
        if not sel or sel == want:
            return                              # 選取精準：不動
        missing = len(want) - len(sel)
        if 1 <= missing <= 3 and want.endswith(sel):   # 只補『少選了最左 missing 格』這種明確情形
            wk.select_left(textutil.utf16_len(want[:missing]))
            time.sleep(0.02)

    # tries 觀察者：純 super() + 數次數，**完全不影響引擎行為**（v2.55 引擎原樣跑）。錯了沒關係、只當參考。
    def _cycle_correct(self, read_fn, kind, cyclekey, force=False):
        before = self._cycle
        super()._cycle_correct(read_fn, kind, cyclekey, force)
        cyc = self._cycle
        if cyc is not None:
            cyc["tries"] = (cyc.get("tries", 0) + 1) if cyc is before else 1   # 同輪+1 / 新輪=1

    # F8：把「你剛剛複製的內容」還原回剪貼簿（改字不再自動還原，故用一鍵手動取回）→ 之後你自己 Ctrl+V。
    def _on_f8(self):
        clip = getattr(self, "_clip_user", "")
        if not clip:
            self._notify("目前沒有記到你先前複製的內容"); return
        self._set_clip(clip)
        self._notify("已把你剛剛複製的內容還原到剪貼簿（可 Ctrl+V 貼上）")

    # F8：常錯字強制細修（freeze 後的強制版 F1/F4/F5，只動 在再/那哪/的得地）。
    # 對『剛剛改的那段』窮舉常錯字變體→去掉原句→模型打分→套最高分；連按往下一個變體換（自己一套 cycle，
    # 不碰 v2.55 引擎）。沒有這三組字→跳「沒有常錯字」。
    def _on_confusable(self):
        cyc = self._cycle
        read_fn = (cyc.get("read_fn") if cyc else None) or self._read_unit
        got = read_fn()
        if got is None:
            return
        cur, writer = got
        cc = getattr(self, "_conf_cycle", None)
        if cc and cc.get("last") == cur and cc.get("list"):          # 連按：往下一個變體換
            cc["idx"] = (cc["idx"] + 1) % len(cc["list"])
            nxt = cc["list"][cc["idx"]]
            writer(nxt)
            cc["last"] = nxt
            self._notify_conf(cc["src"], nxt, cc["idx"], len(cc["list"]))
            return
        if not self.corrector.has_confusable(cur):
            self._conf_cycle = None
            self._notify("這段沒有常錯字（在再／那哪／的得地），免按 F8")
            return
        variants = self.corrector.confusable_variants(cur, top_n=12)
        if not variants:
            self._conf_cycle = None
            self._notify("這段沒有可換的常錯字")
            return
        lst = variants + [cur]                                       # 原句擺最後，連按可循環回來
        self._conf_cycle = {"list": lst, "idx": 0, "last": variants[0], "src": cur}
        writer(variants[0])
        self._notify_conf(cur, variants[0], 0, len(lst))

    def _notify_conf(self, src, dst, idx, total):
        changes = [(i, a, b) for i, (a, b) in enumerate(zip(src, dst)) if a != b]
        if changes:
            self._notify(f"常錯字強制換：{editfmt.fmt_edits(changes)}（{idx + 1}/{total}，再按 F8 換下一個）")
        else:
            self._notify(f"已回到你原本打的字（{idx + 1}/{total}，再按 F8 換下一個）")

    # F9：記正解 + 學詞。純旁觀（不碰循環）、**永遠可按**（無 tries/_last_elogged 門檻）。
    # log 只在「真的改過」(orig != 現值) 才寫，避免記 no-op；學詞交給 _maybe_auto_learn（依 auto_learn 設定）。
    def _do_record_correct(self):
        cyc = self._cycle
        if not cyc:
            self._notify("先按 F1 改字，再按 F9 記正解")
            return
        got = (cyc.get("read_fn") or self._read_unit)()      # 重讀目前欄位＝我確認的正解
        if got is None:
            return
        correct = got[0]
        problem = cyc.get("orig")
        learned = self._maybe_auto_learn(correct, wrong=problem) if problem else ""
        if problem and problem != correct:
            try:
                logbook.upsert_error_case(problem, problem, correct, "manual", cyc.get("tries"))
            except Exception:
                pass
        self._notify(f"已記正解：{correct}" + (learned or ""))

    # ---- 自學詞管理視窗（共享 csc.managewords；沿用 F6 框的『獨立緒 Tk + 關閉後 gc』防跨緒閃退）----
    def _on_manage(self, icon=None, item=None):
        threading.Thread(target=self._run_manage, daemon=True).start()

    def _run_manage(self):
        import gc
        from csc import managewords
        try:
            managewords.open_manage_window(self._notify)
        except Exception as e:
            self._notify(f"管理視窗錯誤：{e}")
        finally:
            gc.collect()
            self._refresh_menu()


def main():
    gc.disable()
    crashlog.install()
    TrayApp().start()


if __name__ == "__main__":
    main()
