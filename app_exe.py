# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""繁中自動選字 — 獨立 exe 進入點（ONNX 引擎，無 torch）。
由開發版本鏈攤平而成。F1 修正/循環·F2 重算·F3 學詞·F4 反白·F5 標記·F6 框·F7 前30字·F9 暫停·F10 記難例；F6 自動切注音、系統匣可記憶勾選、崩潰捕捉、開機自動啟動。"""


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

APP_TITLE = "繁中自動選字 v2.1"
APP_AUMID = "ZhuyinAutoFix.v2_1"
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
    def _build_menu(self):
        learned = userdict.entries_by_word()
        items = []
        if learned:
            sub = [pystray.MenuItem(
                f"✕ {w}（{'強制' if t == 'hard' else '建議'}）",
                lambda icon, it, w=w: self._remove_word(w)) for w, t in learned.items()]
            sub.append(pystray.Menu.SEPARATOR)
            sub.append(pystray.MenuItem("全部清除", lambda icon, it: self._clear_words()))
            items.append(pystray.MenuItem(f"管理我學的詞（{len(learned)}）", pystray.Menu(*sub)))
        else:
            items.append(pystray.MenuItem("我學的詞：0（反白詞→按 F2 學習）",
                                          None, enabled=False))
        items += [
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

    def _remove_word(self, w):
        userdict.remove(w)
        wordphon.reload_userforce()
        self._refresh_menu()
        self._notify(f"已移除自學詞「{w}」")

    def _clear_words(self):
        n = userdict.clear()
        wordphon.reload_userforce()
        self._refresh_menu()
        self._notify(f"已清除 {n} 個自學詞")


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
            self._notify("沒有反白到字（請先選取『正確的詞』再按 F3 學習）")
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
            self._notify(f"已學會「{word}」：建議等級（再按 F3 升級為強制）{extra}")
        elif status == "upgraded":
            self._notify(f"「{word}」升級為強制：同音打錯一定改成它")
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
        learned = userdict.entries_by_word()
        items = []
        if learned:
            sub = [pystray.MenuItem(f"✕ {w}（{'強制' if t == 'hard' else '建議'}）",
                                    self._mk_remove(w)) for w, t in learned.items()]
            sub.append(pystray.Menu.SEPARATOR)
            sub.append(pystray.MenuItem("全部清除", lambda icon, item: self._clear_words()))
            items.append(pystray.MenuItem(f"管理我學的詞（{len(learned)}）", pystray.Menu(*sub)))
        else:
            items.append(pystray.MenuItem("我學的詞：0（反白詞→按 F3 學習）",
                                          None, enabled=False))
        items += [
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

from csc import logbook, winkeys as wk, userdict, wordphon


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
            self._notify("沒有反白到字（請先選取『正確的詞』再按 F3 學習）")
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
            self._notify(f"已學會「{word}」：建議等級（再按 F3 升級為強制）{extra}")
        elif status == "upgraded":
            self._notify(f"「{word}」升級為強制：同音打錯一定改成它")
        else:
            self._notify(f"「{word}」：{msg}")

    def _do_correct_selection(self):
        is_console = _foreground_process() in _CONSOLES
        saved = self._get_clip()
        sel = self._grab_selection(is_console)
        if not sel or sel == SENTINEL or not sel.strip():
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

from csc import logbook, winkeys as wk, hotkey, textutil

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
            edits = "、".join(f"{a}→{b}" for _, a, b in changes)
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
            self._notify("沒有反白到文字（請先選取要修的字，再按 F4）"); return None
        return sel, lambda new: self._paste_selection(new, reselect=True)

    # ---- 四個入口 ----
    def _do_correct(self):                    # F1
        if _foreground_process() in _CONSOLES:
            self._notify(_CON_F4); return
        self._cycle_correct(self._read_unit, "unit", "F1")

    def _do_recorrect(self):                  # F2：重算上一次那個鍵的目標（通用）
        cyc = self._cycle
        if cyc and cyc.get("orig"):
            self._auto_log_problem(cyc["orig"])      # 重算前記原題（此刻 orig 還是最初的字）
        if cyc and cyc.get("read_fn"):
            key = cyc.get("cyclekey", "F1")
            if _foreground_process() in _CONSOLES:
                self._notify(_CON_F4); return
            self._cycle_correct(cyc["read_fn"], cyc["kind"], key, force=True)
        else:
            if _foreground_process() in _CONSOLES:
                self._notify(_CON_F4); return
            self._cycle_correct(self._read_unit, "unit", "F1", force=True)

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
            if kind == "sel":
                try:
                    s = txt.get("sel.first", "sel.last")
                    c = txt.count("1.0", "sel.first", "chars")
                    start = c[0] if isinstance(c, (tuple, list)) else int(c)
                except Exception:
                    s, start = "", 0
                if not s.strip():
                    status.config(text="（先用滑鼠/Shift 反白要修的字，再按 F4）", fg="#888")
                    return None
                return start, s
            if kind == "win":
                chunk = win[-30:]
                if not chunk.strip():
                    status.config(text="（先打字…）", fg="#888")
                    return None
                return len(win) - len(chunk), chunk
            unit, tl = textutil.split_tail_unit(win)              # tail
            if not unit.strip():
                status.config(text="（先打字…）", fg="#888")
                return None
            return len(win) - len(unit) - len(tl), unit

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
        """切回原視窗鍵入 text。哨兵 \\x00＝Ctrl+Enter 軟換行（重播框裡按的鍵）；其餘字直接打。"""
        time.sleep(0.08)
        self._bring_to_front(hwnd)
        time.sleep(0.12)
        for i, seg in enumerate(text.split("\x00")):
            if i:
                wk.combo(wk.VK_CONTROL, VK_RETURN)
                time.sleep(0.03)
            if seg:
                wk.type_text(seg)
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
        if ok:
            self._notify(f"已把正確答案補進難例清單（gold）：{correct}")
        else:
            self._notify("難例清單沒有可補的紀錄")

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

from csc import settings, winkeys as wk


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
        ]
        return pystray.Menu(*(items[:-1] + ime_items + items[-1:]))

    def _toggle_auto_ime(self, icon=None, item=None):
        settings.set("auto_switch_ime", not settings.get("auto_switch_ime"))
        self._refresh_menu()

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
        gold = cands[cyc.get("idx", 0)] if cands else None   # 目前最後選到的候選＝我選定的正解
        gold = (gold or "").strip()
        if not gold:
            _say("框內沒有可記錄的內容", ok=False)
            return
        try:
            logbook.log_error_case(problem, output if output and output != problem else None)
            logbook.append_correct_answer(gold)
        except Exception as e:
            _say(f"記錄失敗：{e}", ok=False)
            return
        _say(f"已記錄正確答案(gold)：{gold}")


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
        if cyc is before and before is not None and cyc.get("idx") != before_idx:
            self._autofill_gold()

    def _autofill_gold(self):
        """把『目前最後選到的選項』自動補進難例清單最後一筆的 gold（需先有本階段自動記的失敗案例）。"""
        if not getattr(self, "_last_elogged", None):
            return
        cyc = self._cycle
        if not (cyc and cyc.get("list")):
            return
        try:
            logbook.append_correct_answer(cyc["list"][cyc.get("idx", 0)])
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


class TrayApp(_App19):
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
            hotkey.VK_F9: self._on_logerror,      # 更新 error cases / 補 gold（原 F10）
            hotkey.VK_F10: self._on_f9_pause,     # 關閉/恢復熱鍵（原 F9）
        }, keep_vks=(hotkey.VK_F10,))
        self.icon.run(setup=self._setup)

    def _load_model(self):
        # 暫時靜音 super 的舊鍵位通知（避免啟動跳兩次），只留下面這條 v2.1 的
        _notify = self._notify
        self._notify = lambda *a, **k: None
        try:
            super()._load_model()
        finally:
            self._notify = _notify
        self.corrector.char_cand = 12
        self.corrector.word_cand = 10
        self._set(ICON_READY, f"{APP_TITLE}：就緒（右鍵 → 使用說明）")
        self._notify("就緒 v2.1： F1 改字 · F2 重算 · F3 還原 · F4 前30字 · F5 反白 · "
                     "F6 框 · F7 學詞 · F9 記正解 · F10 關熱鍵\n"
                     "（已縮到右下角系統匣，背景執行中；右鍵有使用說明）")

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

    # ---- tray 右鍵「使用說明」 ----
    def _build_menu(self):
        items = list(super()._build_menu())
        help_item = pystray.MenuItem("使用說明", self._show_help)
        return pystray.Menu(*([help_item, pystray.Menu.SEPARATOR] + items))

    def _show_help(self, icon=None, item=None):
        threading.Thread(
            target=lambda: ctypes.windll.user32.MessageBoxW(
                0, USAGE_TEXT, f"{APP_TITLE} — 使用說明", 0x40),
            daemon=True).start()


def main():
    gc.disable()
    crashlog.install()
    TrayApp().start()


if __name__ == "__main__":
    main()
