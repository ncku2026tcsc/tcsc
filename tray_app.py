# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""繁中自動選字 — 每日版進入點（torch + transformers，GPU）。
由開發版本鏈攤平而成。功能同 exe 版（引擎為 torch BERT）。"""


# ===== tray_app_v5 =====
# -*- coding: utf-8 -*-
"""背景注音同音校正 v5 —— 加 F2「標記上一筆為錯誤」（收集模型選錯的語料）。

相對 v4：
  - F1：校正（選取→複製→修正→打字覆蓋）；記住上一筆 (原句, 模型輸出)。
  - F2：標記上一筆為錯誤。會重抓目前該行：
        若你已手動把它改成正確的 → 把現在內容當「正解」，自動分類(誤改/漏改/改錯方向)；
        若還沒改 → 只記為 wrong。寫進 logs/history.jsonl 的 annotation。
  - 用 csc.hotkey 一次註冊 F1 + F2。

執行： pythonw tray_app_v5.py（或用 .bat）
"""
import threading
import time

import pyperclip
import pystray
from PIL import Image, ImageDraw

from csc.select_corrector import SelectCorrectorV3
from csc import logbook, winkeys as wk, hotkey

SENTINEL = "\x00__zhuyin_fix__\x00"
TITLE = "注音校正"


def _icon(color):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((8, 8, 56, 56), fill=color)
    return img


ICON_LOAD = _icon((150, 150, 150))
ICON_READY = _icon((40, 200, 80))
ICON_BUSY = _icon((230, 180, 40))


def _last_seg(line: str):
    """切出『最後一個空格之後』那段（往前看到空格/行首為止）。"""
    idx = max(line.rfind(" "), line.rfind("\t"), line.rfind("　"))
    return line[:idx + 1], line[idx + 1:]


class _App0:
    def __init__(self, margin=1.0, lambda_prior=0.5):
        self.margin = margin
        self.lambda_prior = lambda_prior
        self.corrector = None
        self._busy = False
        self._last = None          # (sent, corrected) 上一次 F1 結果，供 F2 標記
        self.icon = pystray.Icon(
            "zhuyin_fix", ICON_LOAD, f"{TITLE}（載入中…）",
            menu=pystray.Menu(
                pystray.MenuItem("重新載入詞庫加權 (custom_boost.txt)", self._reload_boost),
                pystray.MenuItem("離開", self._quit),
            ),
        )

    def _set(self, img, title):
        self.icon.icon = img
        self.icon.title = title

    def _notify(self, msg):
        try:
            self.icon.notify(msg, TITLE)
        except Exception:
            pass

    def start(self):
        threading.Thread(target=self._load_model, daemon=True).start()
        hotkey.start_hotkeys_thread({hotkey.VK_F1: self._on_f1, hotkey.VK_F2: self._on_f2})
        self.icon.run()

    def _load_model(self):
        self.corrector = SelectCorrectorV3(margin=self.margin, lambda_prior=self.lambda_prior)
        self._set(ICON_READY, f"{TITLE}：就緒（F1 修正 / F2 標記上一筆錯誤）")
        self._notify("就緒：F1 修正、改錯了按 F2 標記")

    def _reload_boost(self, *_):
        if self.corrector:
            self.corrector._boost = self.corrector._load_boost()
        self._notify("已重新載入詞庫加權")

    def _quit(self, *_):
        self.icon.stop()

    # 抓取目前行（游標→行首），保留選取；回傳 line 或 None
    def _grab_line(self):
        original = self._get_clip()
        self._set_clip(SENTINEL)
        time.sleep(0.06)
        wk.combo(wk.VK_SHIFT, wk.VK_HOME)
        time.sleep(0.05)
        wk.combo(wk.VK_CONTROL, wk.VK_C)
        time.sleep(0.22)
        line = self._get_clip()
        self._set_clip(original)
        if line == SENTINEL or not line or not line.strip():
            return None
        return line

    # ---- F1：校正 ----
    def _on_f1(self):
        if self.corrector is None or self._busy:
            return
        threading.Thread(target=self._run, args=(self._do_correct,), daemon=True).start()

    def _do_correct(self):
        time.sleep(0.08)
        line = self._grab_line()
        if line is None:
            wk.tap(wk.VK_END)
            self._notify("沒抓到文字（換個輸入欄試試）")
            return
        prefix, sent = _last_seg(line)
        res = self.corrector.correct(sent)
        new_line = prefix + res.corrected
        logbook.log_correction(sent, res.corrected, res.changes, self.corrector.margin)
        self._last = (sent, res.corrected)
        if new_line == line:
            wk.tap(wk.VK_END)
            self._notify(f"未發現需修正的同音字：{sent}")
            return
        wk.type_text(new_line)
        edits = "、".join(f"{a}→{b}" for _, a, b in res.changes)
        self._notify(f"已修正 {len(res.changes)} 字：{edits}（改錯了按 F2）")

    # ---- F2：標記上一筆為錯誤 ----
    def _on_f2(self):
        if self._busy:
            return
        threading.Thread(target=self._run, args=(self._do_mark_wrong,), daemon=True).start()

    def _do_mark_wrong(self):
        if not self._last:
            self._notify("沒有可標記的上一筆")
            return
        sent, model_out = self._last
        time.sleep(0.05)
        line = self._grab_line()
        wk.tap(wk.VK_END)
        gold = None
        if line:
            _, gold_seg = _last_seg(line)
            if gold_seg and gold_seg != model_out:
                gold = gold_seg          # 你已手動改正 → 當作正解
        analysis = logbook.log_annotation(sent, model_out, "wrong", gold)
        self._last = None
        if gold and analysis:
            fp = len(analysis.get("false_positive", []))
            ms = len(analysis.get("missed", []))
            wc = len(analysis.get("wrong_correction", []))
            self._notify(f"已記錄錯誤+正解（誤改{fp}/漏改{ms}/改錯{wc}）")
        else:
            self._notify("已記錄上一筆為錯誤（未取得正解；可先手動改正再按 F2）")

    def _run(self, fn):
        self._busy = True
        self._set(ICON_BUSY, f"{TITLE}：處理中…")
        try:
            fn()
        except Exception as e:
            self._notify(f"發生錯誤：{e}")
        finally:
            self._set(ICON_READY, f"{TITLE}：就緒（F1 修正 / F2 標記錯誤）")
            self._busy = False

    @staticmethod
    def _get_clip():
        try:
            return pyperclip.paste()
        except Exception:
            return ""

    @staticmethod
    def _set_clip(text):
        try:
            pyperclip.copy(text if text is not None else "")
        except Exception:
            pass


# ===== tray_app_v11 =====
# -*- coding: utf-8 -*-
"""tray v11 = v10（F1 循環）+ 修換行抓取 + 終端機略過。

問題1（換行）：長句換行後 Shift+Home 只到「目前視覺行」行首 → 只抓到第二行前段。
  改用 Shift+←×K 往回抓固定字數視窗（會跨越換行），讀完 collapse 回真正行尾；
  取代時也只用 Shift+← 從行尾選取，不用 End（End 也受換行影響）。
問題2（終端機）：PowerShell/cmd 等的 Ctrl+C 是中斷、編輯模型不同 → 偵測前景是終端機就略過並通知。

其餘（F2、循環、引擎 v6）沿用。
"""
import ctypes
import time
from ctypes import wintypes

from csc import logbook, winkeys as wk
from csc.select_corrector import SelectCorrectorV6

VK_LEFT, VK_RIGHT = 0x25, 0x27
GRAB_CHARS = 50          # 往回抓多少字當視窗（可跨換行）
SENTINEL = "\x00__zfix__\x00"

_CONSOLES = {"powershell.exe", "pwsh.exe", "cmd.exe", "windowsterminal.exe",
             "conhost.exe", "openconsole.exe", "wt.exe", "mobaxterm.exe",
             "wezterm-gui.exe", "alacritty.exe", "putty.exe", "kitty.exe",
             "windowsterminalpreview.exe"}
_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32


def _foreground_process() -> str:
    """前景視窗的執行檔名（小寫）；失敗回空字串。"""
    try:
        hwnd = _user32.GetForegroundWindow()
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        h = _kernel32.OpenProcess(0x1000, False, pid.value)   # QUERY_LIMITED_INFORMATION
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


class _App1(_App0):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._cycle = None

    def _load_model(self):
        self.corrector = SelectCorrectorV6(margin=self.margin, lambda_prior=1.0)
        self._set(ICON_READY, f"{TITLE}：就緒（F1 修正/再按換下一個 · F2 標記）")
        self._notify("就緒：F1 修正、再按 F1 換候選（已支援換行）")

    def _grab_window(self):
        """Shift+←×K 抓視窗(跨換行) → 複製 → collapse 回行尾。回傳視窗字串或 None。"""
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
        wk.tap(VK_RIGHT)                 # collapse 到右緣 = 真正行尾（不受換行影響）
        if window == SENTINEL or not window or not window.strip():
            return None
        return window

    def _replace_tail(self, cur_unit, new_unit):
        """游標在行尾時：選取最後 len(cur_unit) 字、打字覆蓋（不用 End）。"""
        wk.key(wk.VK_SHIFT)
        for _ in range(len(cur_unit)):
            wk.tap(VK_LEFT)
        wk.key(wk.VK_SHIFT, up=True)
        time.sleep(0.03)
        wk.type_text(new_unit)

    def _do_correct(self):
        proc = _foreground_process()
        if proc in _CONSOLES:
            self._notify(f"終端機（{proc}）不支援，請在一般輸入欄使用")
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
        if cyc and sent == cyc["list"][cyc["idx"]]:          # 再按 F1 → 換下一個
            cyc["idx"] = (cyc["idx"] + 1) % len(cyc["list"])
            nxt = cyc["list"][cyc["idx"]]
            self._replace_tail(sent, nxt)
            self._last = (cyc["list"][-1], nxt)
            n, total = cyc["idx"] + 1, len(cyc["list"])
            tag = "原句(還原)" if cyc["idx"] == total - 1 else f"第 {n}/{total} 個"
            self._notify(f"換成 {tag}：{nxt}")
            return

        ranked = self.corrector.ranked_corrections(sent)
        if len(ranked) <= 1 or ranked[0] == sent:
            self._notify(f"未發現需修正的同音字：{sent}")
            self._cycle = None
            return
        best = ranked[0]
        self._replace_tail(sent, best)
        changes = [(i, a, b) for i, (a, b) in enumerate(zip(sent, best)) if a != b]
        logbook.log_correction(sent, best, changes, self.corrector.margin)
        self._last = (sent, best)
        self._cycle = {"list": ranked, "idx": 0}
        edits = "、".join(f"{a}→{b}" for _, a, b in changes)
        self._notify(f"已修正：{edits}（不滿意再按 F1 換，共 {len(ranked)} 個）")

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


# ===== tray_app_v12 =====
# -*- coding: utf-8 -*-
"""tray v12 = v11 + 自訂通知標題 + 選單「聯繫作者」。

- 通知標題顯示「繁中自動選字 v1.1」而非「Python」：
    (a) 進程啟動時設 AppUserModelID（蓋掉 toast 的 app 名 'Python'）
    (b) notify() 改用自訂標題
- 系統匣選單加「聯繫作者」（點擊複製信箱 + 開 mailto）。
其餘（換行視窗抓取、終端機略過、F1 循環、F2 標記）全沿用 v11。
"""
import ctypes
import webbrowser

import pystray

from csc.select_corrector import SelectCorrectorV6

APP_TITLE = "繁中自動選字 v2.1"
APP_AUMID = "ZhuyinAutoFix.v2_1"
AUTHOR_EMAIL = "ncku2026tcsc@gmail.com"


class _App2(_App1):
    def __init__(self, *a, **k):
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                ctypes.c_wchar_p(APP_TITLE))
        except Exception:
            pass
        super().__init__(*a, **k)
        # 重建系統匣圖示：自訂提示文字 + 加「聯繫作者」選單
        self.icon = pystray.Icon(
            "zhuyin_fix", ICON_LOAD, f"{APP_TITLE}（載入中…）",
            menu=pystray.Menu(
                pystray.MenuItem("重新載入詞庫加權 (custom_boost.txt)", self._reload_boost),
                pystray.MenuItem(f"聯繫作者：{AUTHOR_EMAIL}", self._contact),
                pystray.MenuItem("離開", self._quit),
            ),
        )

    def _notify(self, msg):
        try:
            self.icon.notify(msg, APP_TITLE)
        except Exception:
            pass

    def _contact(self, *_):
        self._set_clip(AUTHOR_EMAIL)
        try:
            webbrowser.open(f"mailto:{AUTHOR_EMAIL}")
        except Exception:
            pass
        self._notify(f"作者信箱已複製：{AUTHOR_EMAIL}")

    def _load_model(self):
        self.corrector = SelectCorrectorV6(margin=self.margin, lambda_prior=1.0)
        self._set(ICON_READY, f"{APP_TITLE}：就緒（F1 修正/再按換下一個 · F2 標記）")
        self._notify("就緒：F1 修正、再按 F1 換候選")


# ===== tray_app_v13 =====
# -*- coding: utf-8 -*-
"""tray v13 = v12 + 「F1 預設不改、仍可再按 F1 換候選」+ 引擎 v7。

相對 v12：
  - 引擎用 SelectCorrectorV7（ranked_corrections 永遠提供候選）。
  - _do_correct 總是進入循環：即使「不用改」，再按 F1 仍能看下一個機率候選。
其餘（換行視窗抓取、終端機略過、F2、自訂標題、聯繫作者）沿用 v11/v12。
"""
import time

from csc import logbook, winkeys as wk
from csc.select_corrector import SelectCorrectorV7

VK_LEFT = 0x25


class _App3(_App2):
    def _load_model(self):
        self.corrector = SelectCorrectorV7(margin=self.margin, lambda_prior=1.0)
        self._set(ICON_READY, f"{APP_TITLE}：就緒（F1 修正/再按換下一個 · F2 標記）")
        self._notify("就緒：F1 修正；不滿意（或想換字）再按 F1")

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
        if cyc and sent == cyc["list"][cyc["idx"]]:           # 再按 F1 → 下一個候選
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


# ===== tray_app_v14 =====
# -*- coding: utf-8 -*-
"""tray v14 = v13 + 修「就緒通知」+ 循環候選安靜（只在還原時提醒一次）。

相對 v13：
  - start() 改用 pystray 的 setup 回呼啟動模型載入：就緒通知保證在系統匣圖示
    可用之後才跳（v13/exe 在模型載入很快時，就緒通知會早於 icon.run 被系統吞掉）。
  - _do_correct 的循環分支：中間候選**安靜**（只換欄位文字 + 圖示已閃黃→綠），
    只有「轉一圈回原句」時跳一次「已還原為原句」。
其餘（換行視窗抓取、終端機略過、F2、自訂標題、聯繫作者、引擎 v7）沿用 v11~v13。
"""
import threading
import time

from csc import logbook, hotkey


class _App4(_App3):
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


# ===== tray_app_v15 =====
# -*- coding: utf-8 -*-
"""tray v15 = v14 + F3「反白手動修正」模式（讓終端機等場景也能用）。

F1（自動）：往回抓視窗、切最後一個單位、就地修正/循環——適合一般輸入欄。
F3（手動）：你**自己反白**要修的字（任何 app，含終端機）→ 修正整段：
  - 一般 app：把修正結果**貼上取代反白**（Ctrl+V，保留全形標點、不怕 IME 吃字）。
  - 終端機：Ctrl+C 在終端機是中斷、且反白的是螢幕字非命令緩衝，無法安全打回，
    故改用 Ctrl+Shift+C 讀取 → 修正 → 放回剪貼簿，通知你自己 Ctrl+Shift+V 貼上。
F3 會把整段（含多個標點分句）逐句修正、保留所有標點/空白。
"""
import re
import time

from csc import logbook, winkeys as wk, hotkey

_SPLIT = re.compile(r"([，。！？；：、,.!?;:　 \t\n]+)")


class _App5(_App4):
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
        import threading
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


# ===== tray_app_v16 =====
# -*- coding: utf-8 -*-
"""tray v16 = v15 + 修兩個 F1 bug：游標停在標點上、emoji 消失。

Bug1（游標在標點上）：原本取「最後一個標點之後」那段 → 游標剛好在標點後時那段是空的，
  等於沒抓到。改用 textutil.split_tail_unit：先剝掉尾端標點(記住)、往前抓真正的字，
  修完把標點原樣保留（回填時跳過、不重打）。
Bug2（emoji 消失）：(a) winkeys.type_text 原本跳過 BMP 以外字元 → 已修成送代理對；
  (b) 取代用 Shift+←×len(碼點)，但 Windows 游標按 UTF-16 單元走(emoji=2) → 改用
  textutil.utf16_len 計數，選取才對得齊。
F1（自動）只用於一般輸入欄；終端機請用 F3（沿用 v15）。
"""
import time

from csc import logbook, winkeys as wk, hotkey, textutil

VK_LEFT, VK_RIGHT = 0x25, 0x27


class _App6(_App5):
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


# ===== tray_app_v17 =====
# -*- coding: utf-8 -*-
"""tray v17 = v16 + 修「emoji 害選取算錯格、吃掉前面空格/標點」。

v16 用 UTF-16 單元數選取，但有些 app 游標按「字素」走（emoji=1 格），於是 emoji
會讓 Shift+← 多選一格，把前面的空格/標點吃掉（你好 早安🥹 → 你好棗安🥹）。
根因是「把字元數換算成游標格數」這件事在不同 app 計法相反，怎麼數都會有一邊錯。

改法：不再數字元。寫回時用與抓取**相同的格數**（GRAB_CHARS 次 Shift+←）重選同一塊
視窗，再把「整個視窗（前綴 + 修好的單位 + 尾端標點）」**貼上**取代：
  - 50 是按鍵次數，抓/貼兩次都按 50 → 選到的區域保證一致，與 emoji 幾格無關。
  - 用貼上（非打字）→ 空格、全形標點、emoji 全部原樣保留。
F1 只用於一般輸入欄；終端機請用 F3。
"""
import time

from csc import logbook, winkeys as wk, textutil

VK_LEFT = 0x25
GRAB_CHARS = GRAB_CHARS


class _App7(_App6):
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


# ===== tray_app_v18 =====
# -*- coding: utf-8 -*-
"""tray v18 = v17 + F2「反白學這個詞」（自學詞庫，兩段式）+ 鍵位重排。

鍵位：F1 自動修正 · F2 學這個詞 · F3 反白手動修 · F4 標記上一筆錯誤(log)。
（原本 F2=標記 移到 F4；學習放 F2 因為較常用。）

F2 學詞：反白「正確的詞」→ 自動推導注音 → 寫入 data/userforce.txt → 熱重載即時生效。
  - 第一次學 = 建議(soft，強先驗、通常贏)；對同詞再按 F2 = 升級強制(hard，讀音對就贏)。
  - 單字不開放升級強制（裸字會把同音其他詞改壞）。
  - 系統匣「管理我學的詞」可逐一移除或全清。
解決 BERT 不認得的新詞/俗稱（例：Threads 台灣叫「脆」→ 教「脆友/發脆」即可穩定修正）。
"""
import threading
import time

import pystray

from csc import logbook, winkeys as wk, hotkey, userdict, wordphon
from csc.select_corrector import SelectCorrectorV7


class _App8(_App7):
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
        self.corrector = SelectCorrectorV7(margin=self.margin, lambda_prior=1.0)
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


# ===== tray_app_v19 =====
# -*- coding: utf-8 -*-
"""tray v19 = v18 + F2「重新計算（擷取當前字、累積修）」+ 鍵位右移。

問題：F1 循環候選是從「原始的字」算的，整段替換會把你已改好/已接受的部分打亂。
解法：F2 改成「抓目前欄位的字當基準重算」——已對的自然保留，只重算還沒對的。
  技術上 F1/F2 共用 _correct_core，差別只在 force_recompute：
    F1 → 同一段沒被你動過時會「循環整段候選」；
    F2 → 一律從「現在的字」重算（略過循環），累積式精修。

鍵位右移：F1 修正/循環 · F2 重新計算(新) · F3 學詞 · F4 反白手動修 · F5 標記/log。
"""
import threading
import time

import pystray

from csc import logbook, winkeys as wk, hotkey, userdict, wordphon, textutil
from csc.select_corrector import SelectCorrectorV7


class _App9(_App8):
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
        self.corrector = SelectCorrectorV7(margin=self.margin, lambda_prior=1.0)
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


# ===== tray_app_v20 =====
# -*- coding: utf-8 -*-
"""tray v20 = v19 + 修「PowerPoint/Office 抓不到文字」。

根因：Office（PowerPoint/Word/Excel）剪貼簿是延遲渲染——按 Ctrl+C 後文字不會
馬上出現在剪貼簿，我們固定 sleep 0.22s 就讀，常讀到還是哨兵 → 判定「沒抓到文字」。
解法：改成輪詢——Ctrl+C 後每 30ms 檢查一次，拿到「非哨兵」內容就立刻往下；
一般 app 約 50~90ms 就回（反而比原本快），慢的 app（Office）最多等 ~0.9s。
套用在 F1/F2 的 _grab_window 與 F3/F4 的選取讀取。
"""
import time

from csc import winkeys as wk


class _App10(_App9):
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
        from csc import userdict, wordphon
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
        from csc import logbook
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


# ===== tray_app_v21 =====
# -*- coding: utf-8 -*-
"""tray v21 = v20 + F6「輸入框」：終端機輸入的新切入點（框內一樣按 F1 改字）。

終端機沒辦法就地改字（Ctrl+C 是中斷、命令緩衝區動不得），v15 的 F4 只能修「已存在的
反白文字」。v21 換個思路：按 F6 叫出一個自己的小視窗當「打字暫存區」——

  打字 → 一樣按 F1 改字（再按 F1 換下一個候選，跟全域行為一致）→ Enter 送出
  （自動切回剛剛那個終端機，逐字鍵入框裡的內容）。

UX 一致性是重點：F1 在哪都是「改字」，框裡也不例外，不另發明流程。
  - F1 是全域熱鍵、OS 會攔截（框收不到 F1 鍵事件），故全域 `_on_f1` 偵測「框開著」時，
    把 F1 轉給框去改字（改在框裡），而非跑原本的視窗抓取。
  - 改字（ranked_corrections / 逐句修正）丟**背景執行緒**算，GUI 全程不凍結；打字本身
    不跑任何模型 → 完全不卡。單一子句支援「再按 F1 換候選」循環，多子句則整段最佳修正。
  - Enter 送出框裡「當前內容」（F1 已就地改好的）；不自動按終端機 Enter，游標留給你檢查。

鍵位：F1 修正/換候選 · F2 重算 · F3 學詞 · F4 反白修 · F5 標記 · F6 輸入框(新)。
"""
import ctypes
import queue
import threading
import time

from csc import hotkey, textutil, winkeys as wk

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
VK_RETURN = 0x0D


class _App11(_App10):
    def start(self):
        self._box_q = None                       # 框開著時 = 一個 queue.Queue（F1 命令通道）
        self.icon.menu = self._build_menu()
        hotkey.start_hotkeys_thread({
            hotkey.VK_F1: self._on_f1,            # 修正 / 換候選（框開著時改框裡的字）
            hotkey.VK_F2: self._on_f2_recorrect,  # 重新計算（擷取當前字）
            hotkey.VK_F3: self._on_f2_learn,      # 學這個詞
            hotkey.VK_F4: self._on_f3,            # 反白手動修正
            hotkey.VK_F5: self._on_f4_mark,       # 標記 / log
            hotkey.VK_F6: self._on_f6,            # 輸入框（終端機輸入）
            hotkey.VK_F7: self._on_f7,            # 前30字整段重修（多看上下文，實驗）
        })
        self.icon.run(setup=self._setup)

    def _load_model(self):
        from csc.select_corrector import SelectCorrectorV7
        self.corrector = SelectCorrectorV7(margin=self.margin, lambda_prior=1.0)
        self._set(ICON_READY,
                  f"{APP_TITLE}：就緒（F1改/F2重算/F3學/F4反白/F5標記/F6框/F7前30字）")
        self._notify("就緒：F1 修正 · F2 重算 · F3 學詞 · F4 反白 · F5 標記 · "
                     "F6 輸入框 · F7 前30字整段重修(多看上下文)")

    # ---- F1：框開著時轉給框改字，否則照原本全域行為 ----
    def _on_f1(self):
        q = getattr(self, "_box_q", None)
        if q is not None:                         # 輸入框開著 → F1 改框裡的字（交給 Tk 緒）
            try:
                q.put("f1")
            except Exception:
                pass
            return
        super()._on_f1()

    def _on_f2_recorrect(self):
        q = getattr(self, "_box_q", None)
        if q is not None:                         # 輸入框開著 → F2 在框裡以當前字重算
            try:
                q.put("f2")
            except Exception:
                pass
            return
        super()._on_f2_recorrect()

    # ---- F7：全域「前30字整段重修」（讓模型多看上下文，實驗用，對照 F1 只修最後一句）----
    def _on_f7(self):
        if self.corrector is None or self._busy:  # 框開著時 _busy=True → 用框內「前30字」按鈕
            return
        threading.Thread(target=self._run,
                         args=(lambda: self._do_correct_window(30),), daemon=True).start()

    def _do_correct_window(self, n):
        from csc import logbook
        if _foreground_process() in _CONSOLES:
            self._notify("終端機請用 F6 輸入框")
            return
        time.sleep(0.08)
        window = self._grab_window()
        if window is None:
            self._notify("沒抓到文字（換個輸入欄試試）")
            return
        chunk = window[-n:]                       # 游標前 n 字，整段餵模型（多看上下文）
        if not chunk.strip():
            self._notify("沒抓到要修的字")
            return
        prefix = window[: len(window) - len(chunk)]
        ranked = self.corrector.ranked_corrections(chunk)
        best = ranked[0]
        self._cycle = None                        # 一次性，不接 F1 循環
        self._last = (chunk, best)
        if best != chunk:
            self._replace_window(prefix + best)
            changes = [(i, a, b) for i, (a, b) in enumerate(zip(chunk, best)) if a != b]
            logbook.log_correction(chunk, best, changes, self.corrector.margin)
            edits = "、".join(f"{a}→{b}" for _, a, b in changes)
            self._notify(f"前{len(chunk)}字整段重修：{edits}（多看上下文）")
        else:
            self._notify(f"前{len(chunk)}字：未發現需修正（已多看上下文）")

    # ---- 前景搶奪／還原（背景程式彈窗必備）----
    def _bring_to_front(self, hwnd):
        """把 hwnd 拉到前景並取得鍵盤焦點（AttachThreadInput 繞過前景鎖）。"""
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
        target = _user32.GetForegroundWindow()       # 先記住現在的視窗（多半是終端機）
        threading.Thread(target=self._run_input_box, args=(target,), daemon=True).start()

    def _run_input_box(self, target_hwnd):
        self._busy = True
        self._box_q = queue.Queue()                  # 開啟 F1 命令通道
        self._set(ICON_BUSY, f"{APP_TITLE}：輸入框開啟中…（框裡按 F1 改字）")
        text = None
        try:
            text = self._input_box_dialog(self._box_q)
        except Exception as e:
            self._notify(f"輸入框錯誤：{e}")
        finally:
            self._box_q = None                       # 關閉通道 → F1 恢復全域行為
            self._set(ICON_READY, f"{APP_TITLE}：就緒（F1~F6）")
            self._busy = False
        if text:
            self._send_to_window(target_hwnd, text)

    def _input_box_dialog(self, cmd_q):
        """Tk 視窗（建立/迴圈/銷毀全在本執行緒）。打字不跑模型。F1/F2 經 cmd_q 進來，行為
        與全域一致——切最後一個單位：F1 修正、再按循環換候選；F2 以當前字重算。重算丟背景
        緒、結果回主緒套用。回傳要送出的文字（Enter＝框內當前內容；None＝取消/空白）。"""
        import tkinter as tk

        result = {"text": None}
        done_q = queue.Queue()                        # 背景算完的結果回傳
        state = {"computing": False, "cycle": None}   # cycle = {"list", "idx", "orig"}

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
        sb = tk.Scrollbar(txtwrap, command=txt.yview)   # 超出框 → 右側捲動條
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
            """目前被標記為 Ctrl+Enter（軟換行）的那些 \\n 的字元位移。"""
            offs, r = [], txt.tag_ranges("ce")
            for i in range(0, len(r), 2):
                c = txt.count("1.0", r[i], "chars")
                offs.append(c[0] if isinstance(c, (tuple, list)) else int(c))
            return offs

        def set_box(t, ce=None):
            txt.delete("1.0", "end")
            txt.insert("1.0", t)
            for o in (ce or []):                       # 還原 Ctrl+Enter 軟換行標記
                if 0 <= o < len(t) and t[o] == "\n":
                    txt.tag_add("ce", f"1.0+{o}c", f"1.0+{o + 1}c")
            txt.mark_set("insert", "end-1c")
            txt.see("insert")                          # 捲到最新行

        def build_payload():
            """框內容→送出字串：Ctrl+Enter 換行→哨兵 \\x00（送出時打 Ctrl+Enter 軟換行），
            其餘（含 Shift+Enter 的純換行 \\n）原樣保留。"""
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
        #    F10 補 gold 也讀同一份 state["cycle"]。行為刻意對照一般輸入欄的 _cycle_correct
        #    （read 目標→ranked→寫回、同 kind 再按換候選、F2=force 重算），差別只在 I/O 是
        #    Tk 文字框、模型丟背景緒、套用回主緒(done_q)。改這裡時請連同 _cycle_correct 一起想。
        #    state["cycle"] = {list, idx, orig, kind, start, len}＝唯一事實來源，未來功能掛這上面。
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
            # 再按（非 force）、同 kind、目前目標＝目前候選（沒被你改動）→ 換下一個（不跑模型）
            if not force and cyc and cyc.get("kind") == kind and target == cyc["list"][cyc["idx"]]:
                cyc["idx"] = (cyc["idx"] + 1) % len(cyc["list"])
                nxt = cyc["list"][cyc["idx"]]
                box_apply(start, len(target), nxt)
                if kind == "sel":                                 # 反白循環：保持反白該段
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
            # 新一輪 / 重算：丟背景緒算 ranked，回主緒套用（done_q kind="cyc"）
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
            # 1) F1/F2 命令（來自全域熱鍵緒）
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
            # 2) 背景算好的結果
            try:
                while True:
                    snap, target, start, cyckind, ranked, forced, tag = done_q.get_nowait()
                    state["computing"] = False
                    if snap != box_text():
                        continue                       # 使用者已改字 → 丟棄、不覆蓋
                    best = ranked[0]
                    box_apply(start, len(target), best)
                    state["cycle"] = {"list": ranked, "idx": 0, "orig": target,
                                      "kind": cyckind, "start": start, "len": len(target)}
                    if cyckind == "sel":               # 反白：保持反白該段，方便再按換候選
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

        def do_plain_nl(event=None):                 # Shift+Enter → 純換行（送出時原樣 \n）
            txt.insert("insert", "\n")
            txt.see("insert")                        # 焦點/視窗捲到最新行
            return "break"

        def do_soft_nl(event=None):                  # Ctrl+Enter → 軟換行（送出時送 Ctrl+Enter）
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
        """切回原視窗鍵入 text。哨兵 \\x00＝Ctrl+Enter 軟換行（重播你在框裡按的鍵）；
        其餘字（含 Shift+Enter 的純 \\n）用 SendInput 直接打。不按 Enter，游標留給你檢查。"""
        time.sleep(0.08)
        self._bring_to_front(hwnd)
        time.sleep(0.12)
        for i, seg in enumerate(text.split("\x00")):
            if i:                                      # 段與段之間＝一個 Ctrl+Enter 軟換行
                wk.combo(wk.VK_CONTROL, VK_RETURN)
                time.sleep(0.03)
            if seg:
                wk.type_text(seg)
        self._notify("已輸入到原視窗（請檢查後自行按 Enter 送出）")

    # ---- F4 反白手動修：移除終端機剪貼簿分支，終端機改用 F6 ----
    def _do_correct_selection(self):
        """只服務一般輸入欄：反白 → Ctrl+C 讀 → 逐句修 → 貼回取代。
        終端機不再走「Ctrl+Shift+C 讀 / 通知 Ctrl+Shift+V 貼」那套剪貼簿，改提示用 F6。"""
        from csc import logbook
        if _foreground_process() in _CONSOLES:
            self._notify("終端機請改用 F6 輸入框（F4 反白手動修僅供一般輸入欄）")
            return
        saved = self._get_clip()
        sel = self._grab_selection(False)                  # 一般 app：Ctrl+C 讀選取
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
        self._set_clip(corrected)
        time.sleep(0.05)
        wk.combo(wk.VK_CONTROL, wk.VK_V)                   # 貼上＝取代反白
        time.sleep(0.15)
        self._set_clip(saved)
        self._notify(f"已修正：{edits}（已取代反白）")


# ===== tray_app_v22 =====
# -*- coding: utf-8 -*-
"""tray v22 = v21 + 修「F1 貼上偶爾貼成『上一個剪貼簿內容』」的競態。

症狀（使用者回報）：F1 改完後，Windows 通知顯示的是正確的改字內容，但實際貼上的卻是
『上一次剪貼簿裡的東西』，而且特別容易在「剪貼簿原本就有內容」時發生。

根因（在 v17 的 _replace_window）：流程是
    saved = clip → 反白 → set_clip(new) → sleep → Ctrl+V → sleep → set_clip(saved)
  兩個競態都會讓貼出來的是舊內容 saved：
  (1) 設定端：pyperclip.copy(new) 偶爾因剪貼簿被別的程式（剪貼簿管理員等）佔住而
      『靜默失敗』（例外被吞掉）。此時剪貼簿還是舊的 saved → Ctrl+V 貼到舊內容；
      而通知字串是另外從 unit/best 算的，照樣顯示「已修正」。只有剪貼簿原本有料時
      saved 才有東西、才看得出貼錯——正好對上「有東西時才發生」。
  (2) 讀取端：少數程式延遲讀剪貼簿，0.15s 就把 saved 還原回去 → 程式讀到 saved。

修法（只覆寫『寫回』這一個方法，其餘行為完全不變）：
  - 先把新內容寫進剪貼簿並『輪詢確認真的生效』(_set_clip_confirm) 才去動目標選取與貼上；
    確認不過就還原剪貼簿並丟出例外（由 _run 顯示錯誤），絕不在沒寫進去時硬貼舊內容。
  - 貼上後給前景程式多一點讀取時間（0.22s）再還原剪貼簿。
F1 / F1循環 / F2重算 / F7 都走這個方法，故一次修好；F6 輸入框不碰系統剪貼簿、不受影響。
"""
import time

from csc import winkeys as wk

GRAB_CHARS = GRAB_CHARS
VK_LEFT = VK_LEFT


class _App12(_App11):
    def _set_clip_confirm(self, text, timeout=0.5):
        """設剪貼簿並輪詢確認內容『確實寫進去』，克服 pyperclip.copy 偶發的靜默失敗
        （剪貼簿被佔用時 copy 會無聲失敗，正是貼到舊內容的元兇）。
        生效回 True；逾時仍未生效回 False。"""
        deadline = time.time() + timeout
        while True:
            self._set_clip(text)
            time.sleep(0.03)
            if self._get_clip() == text:
                return True
            if time.time() >= deadline:
                return False

    def _replace_window(self, new_window):
        """重選與抓取相同的格數→整段貼上 new_window。相對 v17：先確認剪貼簿真的是新內容
        才動目標選取與貼上，杜絕『通知已修正、卻貼出舊剪貼簿內容』的競態。"""
        saved = self._get_clip()
        if not self._set_clip_confirm(new_window):       # 設定端：沒寫進去就別硬貼舊內容
            self._set_clip(saved)
            raise RuntimeError("剪貼簿被佔用，沒貼成功，請再按一次 F1")
        wk.key(wk.VK_SHIFT)                              # 反白與抓取相同的 GRAB_CHARS 格
        for _ in range(GRAB_CHARS):
            wk.tap(VK_LEFT)
        wk.key(wk.VK_SHIFT, up=True)
        time.sleep(0.05)
        wk.combo(wk.VK_CONTROL, wk.VK_V)                 # 貼上＝取代選取
        time.sleep(0.22)                                 # 讀取端：多給前景程式讀取時間再還原
        self._set_clip(saved)


# ===== tray_app_v23 =====
# -*- coding: utf-8 -*-
"""tray v23 = v22 + 讓 F7「前30字整段重修」也能像 F1 一樣『再按換下一個候選』。

原本 F7 是一次性（`_cycle=None`，按第二次只是重算出同一個 best）。使用者要它比照 F1
的選項循環：第一次 F7 修成最佳，**該段沒被改動時再按 F7 → 換下一個候選**，轉一圈回原句
（即使第一次「沒發現需修正」，也能再按 F7 逐一看其他候選，與 F1 階段20 行為一致）。

實作：F7 用獨立的 `self._cycle_win`，與 F1 的 `self._cycle` 互不干擾（免動 `_correct_core`）。
偵測「前 N 字 == 目前候選」就換下一個，邏輯與 v19 `_correct_core` 的 F1 循環一致；
候選＝`ranked_corrections(整段 N 字)` 回傳的整段候選字串（同長度、逐一替換）。
循環鍵＝F7（與 F1『再按 F1』對稱，各自循環各自的結果）。
"""
import time



class _App13(_App12):
    def _do_correct_window(self, n):
        from csc import logbook
        if _foreground_process() in _CONSOLES:
            self._notify("終端機請用 F6 輸入框")
            return
        time.sleep(0.08)
        window = self._grab_window()
        if window is None:
            self._notify("沒抓到文字（換個輸入欄試試）")
            return
        chunk = window[-n:]                        # 游標前 n 字，整段餵模型（多看上下文）
        if not chunk.strip():
            self._notify("沒抓到要修的字")
            return
        prefix = window[: len(window) - len(chunk)]

        cyc = getattr(self, "_cycle_win", None)
        # 再按 F7、且前 N 字＝目前候選（沒被你改動）→ 換下一個候選（比照 F1 循環）
        if cyc and chunk == cyc["list"][cyc["idx"]]:
            cyc["idx"] = (cyc["idx"] + 1) % len(cyc["list"])
            nxt = cyc["list"][cyc["idx"]]
            self._replace_window(prefix + nxt)
            self._last = (cyc["orig"], nxt)
            total = len(cyc["list"])
            if nxt == cyc["orig"]:
                self._notify(f"前{len(nxt)}字：已還原為原句（共 {total} 個，再按 F7 重來）")
            else:
                ed = "、".join(f"{a}→{b}" for a, b in zip(cyc["orig"], nxt) if a != b)
                self._notify(f"前{len(nxt)}字 第 {cyc['idx'] + 1}/{total} 個候選：{ed}")
            return

        ranked = self.corrector.ranked_corrections(chunk)
        self._cycle = None                         # 開新一輪 F7：清掉 F1 的循環狀態
        self._cycle_win = {"list": ranked, "idx": 0, "orig": chunk}
        best = ranked[0]
        self._last = (chunk, best)
        total = len(ranked)
        if best != chunk:
            self._replace_window(prefix + best)
            changes = [(i, a, b) for i, (a, b) in enumerate(zip(chunk, best)) if a != b]
            logbook.log_correction(chunk, best, changes, self.corrector.margin)
            edits = "、".join(f"{a}→{b}" for _, a, b in changes)
            self._notify(f"前{len(chunk)}字整段重修：{edits}（不滿意再按 F7 換，共 {total} 個）")
        else:
            self._notify(f"前{len(chunk)}字：未發現需修正（再按 F7 看其他候選，共 {total} 個）")


# ===== tray_app_v24 =====
# -*- coding: utf-8 -*-
"""tray v24 = v23 + F12『記錄改錯的題目』到獨立的失敗清單（與 history.jsonl 分開）。

動機：現行 `logs/history.jsonl` 把每次校正（成功約 7 成 + 失敗約 3 成）混在一起，事後要撈
失敗案例很亂。新增一個獨立、單一用途的鍵——模型這次改錯時按 F12 → 把『**題目**（模型當時
拿到的原輸入，`self._last[0]`）』而非『改過的內容』寫進 `logs/error_cases.log`，當作之後
重跑/評估、或微調難例（hard negative）的乾淨清單。

設計：
  - F12 是獨立全域熱鍵（`VK_F12=0x7B`），用**自己的熱鍵迴圈緒**註冊，完全不動原本 F1~F7。
  - 記錄很輕量，**不經 `_run`**（不翻 `self._busy`，避免與 F6 輸入框的 busy 狀態打架）。
  - `self._last[0]` 在 F1/F4/F7（含循環）後都＝模型當時拿到的原輸入＝題目。
"""
import threading

from csc import hotkey, logbook


class _App14(_App13):
    def start(self):
        # 另起一個熱鍵迴圈緒專收 F12（與 F1~F7 的迴圈各自獨立，免重寫整包綁定）
        hotkey.start_hotkeys_thread({hotkey.VK_F12: self._on_f12_logerror})
        super().start()

    def _on_f12_logerror(self):
        threading.Thread(target=self._do_log_error, daemon=True).start()

    def _do_log_error(self):
        try:
            last = getattr(self, "_last", None)
            if not last or not last[0]:
                self._notify("沒有可記錄的上一筆（先按 F1/F7 修正，發現改錯了再按 F12）")
                return
            problem = last[0]                    # 題目＝模型當時拿到的原輸入（非改過的內容）
            logbook.log_error_case(problem)
            self._notify(f"已記錄改錯題目到 error_cases.log：{problem}")
        except Exception as e:
            self._notify(f"記錄失敗：{e}")


# ===== tray_app_v25 =====
# -*- coding: utf-8 -*-
"""tray v25 = v24 + 根治「連按 F1 偶發貼到上一個剪貼簿內容」的重入競態。

回報：即使有 v22 的確認寫入，連按很多次 F1（尤其循環換候選時）仍會『突然』貼出上一個
剪貼簿內容；右下角 tray 通知卻是對的（＝抓取/模型都對，只有寫回貼錯）。

更精確的根因：擋重入的 `self._busy` 有 TOCTOU 空隙——`_on_f1` 檢查「不忙」與背景緒
真正把 `_busy=True` 之間有極短縫隙；連按剛好卡進去 → **同時跑兩個校正**，兩者的
「設哨兵/抓取/設新內容/貼上/還原剪貼簿」彼此交錯，於是貼上時剪貼簿已被另一緒還原成舊內容。
這正好對上「按很多次才偶發」。（v22 只修了單次操作的『寫進剪貼簿』那半，擋不住兩操作重疊。）

為何不用「確認欄位變了才還原」：要讀欄位就得 Ctrl+C，會把還沒被貼上讀走的 new_window
蓋掉、製造新 bug（讀取與待貼上的剪貼簿互相清掉）。故改從根本消除重疊。

修法：
  1. 嚴格序列化——所有會碰剪貼簿的校正（F1/F2/F4/F7 都經 `_run`）改用一把
     `threading.Lock`「非阻塞」取得；取不到（已有校正在跑）就直接略過這次連按。
     永遠不可能有兩個剪貼簿操作同時進行，TOCTOU 重疊絕跡。
  2. 序列化後系統輸入佇列只剩單一操作的按鍵，固定 settle 變得足夠可靠；順手把貼上後的
     還原 settle 由 0.22s 提到 0.30s 留餘裕。
F6 輸入框與 F12 不走 `_run`、也不碰系統剪貼簿，故不受影響、不需這把鎖。
"""
import threading
import time

from csc import winkeys as wk

GRAB_CHARS = GRAB_CHARS
VK_LEFT = VK_LEFT


class _App15(_App14):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._op_lock = threading.Lock()        # 序列化所有碰剪貼簿的校正操作

    def _run(self, fn):
        # 非阻塞取鎖：已有校正在跑就丟棄這次（連按去重，絕不重疊剪貼簿操作）
        if not self._op_lock.acquire(blocking=False):
            return
        try:
            super()._run(fn)
        finally:
            self._op_lock.release()

    def _replace_window(self, new_window):
        """同 v22（先確認剪貼簿真的是新內容才貼），但因為現在校正已嚴格序列化，輸入佇列
        只剩本次操作，貼上後的固定 settle 變得足夠可靠（0.22→0.30 留餘裕）再還原。"""
        saved = self._get_clip()
        if not self._set_clip_confirm(new_window):       # 設定端：沒寫進去就別硬貼舊內容
            self._set_clip(saved)
            raise RuntimeError("剪貼簿被佔用，沒貼成功，請再按一次 F1")
        wk.key(wk.VK_SHIFT)                              # 反白與抓取相同的 GRAB_CHARS 格
        for _ in range(GRAB_CHARS):
            wk.tap(VK_LEFT)
        wk.key(wk.VK_SHIFT, up=True)
        time.sleep(0.05)
        wk.combo(wk.VK_CONTROL, wk.VK_V)                 # 貼上＝取代選取
        time.sleep(0.30)                                 # 已序列化→佇列單一操作，settle 可靠
        self._set_clip(saved)


# ===== tray_app_v26 =====
# -*- coding: utf-8 -*-
"""tray v26 = v25 + 修『連按 F1 時實體鍵漏給前景程式（叫出它的 F1/說明）』。

回報：v25 嚴格序列化後，連按很多次 F1 仍會「叫到原本程式裡的 F1」。根因不在攔截邏輯，而在
**注入修飾鍵的方式**：校正時為了反白視窗，我們把 Shift『按住』再送 50 個 ← 鍵——這個 Shift
是跨一個 50 圈的 Python 迴圈按住的（數十毫秒）。在這段時間你若實體按下 F1，系統看到的是
「Shift+F1」，那不是我們註冊的純 F1 熱鍵 → 不被攔截 → 漏給前景程式 → 觸發它的 F1（說明等）。
（`combo`/`chord` 的 Ctrl+C/V 已是單次原子注入、窗口極短不漏，只有 Shift 長按會漏。）

修法：把「Shift↓ + (←↓ ←↑)×50 + Shift↑」壓成**單一次 SendInput 原子注入**
（`winkeys.select_left`），Shift 只被按住約 1ms 而非數十毫秒 → 漏鍵窗口幾乎消失，實務上等於
攔截全部；且**不需註冊 Shift+F1/Ctrl+F1 等變體去永久吃掉別程式快捷鍵**（會偷走 Ctrl+F4 關分頁
等），也**不裝低階鍵盤掛鉤**（階段14e 明確棄用、會干擾 SendInput）。不重複間隔照舊靠 v25 序列化鎖。
"""
import time

from csc import winkeys as wk

GRAB_CHARS = GRAB_CHARS


class _App16(_App15):
    def _grab_window(self):
        original = self._get_clip()
        self._set_clip(SENTINEL)
        time.sleep(0.06)
        wk.select_left(GRAB_CHARS)               # 批次反白：壓短 Shift 按住時間、杜絕漏鍵
        time.sleep(0.05)
        wk.combo(wk.VK_CONTROL, wk.VK_C)
        window = self._poll_clip()
        self._set_clip(original)
        wk.tap(VK_RIGHT)
        if not window or window == SENTINEL or not window.strip():
            return None
        return window

    def _replace_window(self, new_window):
        """同 v25（確認寫入 + 序列化下的可靠 settle），只把反白改成批次注入避免漏鍵。"""
        saved = self._get_clip()
        if not self._set_clip_confirm(new_window):
            self._set_clip(saved)
            raise RuntimeError("剪貼簿被佔用，沒貼成功，請再按一次 F1")
        wk.select_left(GRAB_CHARS)               # 批次反白：壓短 Shift 按住時間、杜絕漏鍵
        time.sleep(0.05)
        wk.combo(wk.VK_CONTROL, wk.VK_V)
        time.sleep(0.30)
        self._set_clip(saved)


# ===== tray_app_v27 =====
# -*- coding: utf-8 -*-
"""tray v27 = v26 + 修『F12 記錄鍵無效』改用 F10，並讓 F6 輸入框也能記錄改錯題目。

問題1：F12 無法當全域熱鍵——Windows 保留 F12 給除錯器，`RegisterHotKey(F12)` 一定回傳 0
（實測 F8~F11 可、F12 不可）。v24 註冊失敗只是靜默跳過，等於 F12 功能從沒生效、瀏覽器照樣
吃掉它。改用 **F10**（單鍵、可註冊；使用者選定），並把它併進 F1~F7 同一個熱鍵迴圈（單一
執行緒），不再用 v24 那個會註冊失敗的獨立緒。

問題2：F6 輸入框內也要能記錄改錯題目。框內修正在 Tk 緒、狀態藏在 `_input_box_dialog` 的閉包，
外部讀不到「題目」。解法不動那支 250 行的方法：**包裝 `corrector.ranked_corrections`**，把每次
被要求修正的「題目」記到 `self._box_problem`。框開著時只有框會呼叫它（全域 F1/F2 轉進框、F7 被
`_busy` 擋），故 `_box_problem` 即框內最近修正的題目；F10 在框開著時就記它。進框前清掉舊值。
"""
import threading

from csc import hotkey


class _App17(_App16):
    def start(self):
        self._box_q = None
        self._box_problem = None
        self.icon.menu = self._build_menu()
        hotkey.start_hotkeys_thread({
            hotkey.VK_F1: self._on_f1,            # 修正 / 換候選
            hotkey.VK_F2: self._on_f2_recorrect,  # 重算
            hotkey.VK_F3: self._on_f2_learn,      # 學詞
            hotkey.VK_F4: self._on_f3,            # 反白手動修
            hotkey.VK_F5: self._on_f4_mark,       # 標記 / log
            hotkey.VK_F6: self._on_f6,            # 輸入框
            hotkey.VK_F7: self._on_f7,            # 前30字整段重修
            hotkey.VK_F10: self._on_logerror,     # 記錄改錯題目（原 F12 無法註冊 → 改 F10）
        })
        self.icon.run(setup=self._setup)

    def _load_model(self):
        super()._load_model()
        self._install_box_problem_tracker()

    def _install_box_problem_tracker(self):
        """包裝 ranked_corrections：記住最近一次被要求修正的『題目』（給 F6 框內 F10 記錄用）。"""
        _orig = self.corrector.ranked_corrections

        def _wrapped(text, *a, **k):
            self._box_problem = text
            return _orig(text, *a, **k)

        self.corrector.ranked_corrections = _wrapped

    def _on_f6(self):
        self._box_problem = None                  # 進框前清掉框外的舊題目
        super()._on_f6()

    # ---- F10：記錄改錯題目（框開著記框內題目，否則記全域上一筆）----
    def _on_logerror(self):
        if getattr(self, "_box_q", None) is not None:
            threading.Thread(target=self._do_log_error_box, daemon=True).start()
        else:
            threading.Thread(target=self._do_log_error, daemon=True).start()

    def _do_log_error_box(self):
        from csc import logbook
        try:
            prob = getattr(self, "_box_problem", None)
            if not prob:
                self._notify("框內還沒有可記錄的修正（先在框裡按 F1/F7 修正，再按 F10）")
                return
            logbook.log_error_case(prob)
            self._notify(f"已記錄框內改錯題目到 error_cases.log：{prob}")
        except Exception as e:
            self._notify(f"記錄失敗：{e}")


# ===== tray_app_v28 =====
# -*- coding: utf-8 -*-
"""tray v28 = v27 + F4「反白手動修」加上 F1 式『再按換下一個候選』循環。

使用者：F4 很好用，但只要改字就該像 F1 一樣能換候選、行為完全同 F1。

關鍵：原本 F4 的 `_correct_selection_text` 本來就是「把反白用標點切句、每句取
`ranked_corrections(part)[0]`」——**單一子句的反白，第一次結果本來就 = `ranked_corrections(反白)[0]`**，
與 F1 同一個引擎。故 F4 直接改走 `ranked_corrections(反白)`：第一次結果不變，但多了候選清單可循環。

行為（與 F1 對稱）：
  - 第一次 F4：修成最佳、貼回取代反白，並**把貼上的字重新反白**（供再按 F4 循環）。
  - 反白＝目前候選（沒被你改動）再按 F4 → 換下一個候選，轉一圈回原句（即使「沒發現需修正」也能循環）。
  - 用獨立的 `self._sel_cycle`，與 F1 的 `_cycle`、F7 的 `_cycle_win` 互不干擾。
  - 寫回沿用 v22 確認寫入（避免貼到舊剪貼簿）；F4 經 `_run` 已被 v25 序列化。
  - 循環鍵＝F4。終端機仍導向 F6。
"""
import time

from csc import winkeys as wk, textutil


class _App18(_App17):
    def _paste_selection(self, text, reselect):
        """貼上 text 取代目前反白；reselect=True 則貼完用 Shift+← 重新反白 text（供再按 F4 循環）。
        用確認寫入避免貼到舊剪貼簿；不負責還原 saved（呼叫端負責）。"""
        if not self._set_clip_confirm(text):
            raise RuntimeError("剪貼簿被佔用，沒貼成功，請再按一次 F4")
        wk.combo(wk.VK_CONTROL, wk.VK_V)                  # 貼上＝取代反白
        time.sleep(0.20)
        if reselect:
            wk.select_left(textutil.utf16_len(text))      # 重新反白剛貼上的字（給循環）

    def _do_correct_selection(self):
        from csc import logbook
        if _foreground_process() in _CONSOLES:
            self._notify("終端機請改用 F6 輸入框（F4 反白手動修僅供一般輸入欄）")
            return
        saved = self._get_clip()
        sel = self._grab_selection(False)
        if not sel or sel == SENTINEL or not sel.strip():
            self._set_clip(saved)
            self._notify("沒有反白到文字（請先選取要修的字，再按 F4）")
            return

        cyc = getattr(self, "_sel_cycle", None)
        # 反白＝目前候選（沒被你改動）→ 換下一個候選（與 F1 循環同邏輯）
        if cyc and sel == cyc["list"][cyc["idx"]]:
            cyc["idx"] = (cyc["idx"] + 1) % len(cyc["list"])
            nxt = cyc["list"][cyc["idx"]]
            self._paste_selection(nxt, reselect=True)
            self._set_clip(saved)
            self._last = (cyc["orig"], nxt)
            total = len(cyc["list"])
            if nxt == cyc["orig"]:
                self._notify(f"已還原為原句（共 {total} 個，再按 F4 重來）")
            else:
                ed = "、".join(f"{a}→{b}" for a, b in zip(cyc["orig"], nxt) if a != b)
                self._notify(f"第 {cyc['idx'] + 1}/{total} 個候選：{ed}")
            return

        # 新一輪：用 ranked_corrections 排候選（與 F1 同一套；單子句時＝原 F4 結果）
        ranked = self.corrector.ranked_corrections(sel)
        best = ranked[0]
        self._sel_cycle = {"list": ranked, "idx": 0, "orig": sel}
        self._last = (sel, best)
        total = len(ranked)
        if best != sel:
            self._paste_selection(best, reselect=True)
            self._set_clip(saved)
            changes = [(i, a, b) for i, (a, b) in enumerate(zip(sel, best)) if a != b]
            logbook.log_correction(sel, best, changes, self.corrector.margin)
            edits = "、".join(f"{a}→{b}" for _, a, b in changes)
            self._notify(f"已修正：{edits}（不滿意再按 F4 換候選，共 {total} 個）")
        else:
            self._set_clip(saved)                          # 沒改→保留原反白，供再按 F4 循環
            self._notify(f"未發現需修正（再按 F4 看其他候選，共 {total} 個）")


# ===== tray_app_v29 =====
# -*- coding: utf-8 -*-
"""tray v29 = v28 + 把 F1/F2/F4/F7 的循環邏輯**統一成一套引擎**（並修 F7 通知太多）。

使用者：F1/F4/F7 應該統一邏輯，不然亂亂的、也沒辦法保證行為都對；且「前30字(F7)」通知太多，
應該跟 F1 一樣只有第一次提示。

之前各寫一套（`_cycle` / `_cycle_win` / `_sel_cycle`），且通知不一致（F1 中間候選安靜，F4/F7
每按必跳）。本版抽出單一引擎 `_cycle_correct(read_fn, kind, cyclekey, force)`，四個鍵都走它，
差別只在「**怎麼取文字、怎麼寫回**」由 read_fn 的回傳 (target, writer) 決定：
  - F1：抓視窗→切最後一個單位；寫回＝_replace_window(prefix+新+tail)。kind="unit"。
  - F2：同 F1 但 force=True（一律以當前字重算，不走循環）。
  - F7：抓視窗→取游標前 n 字；寫回＝_replace_window(prefix+新)。kind="win"。
  - F4：讀反白選取；寫回＝_paste_selection(新, 重新反白)。kind="sel"。
通知一律比照 F1：**第一次修正才提示；中間候選安靜；轉回原句提示一次**。`kind` 防止不同粒度
的循環互相誤判（按了別的鍵就重新開始）。狀態統一回 `self._cycle`（含 kind）。
"""
import time

from csc import winkeys as wk, textutil

_CON_F6 = "終端機/CLI 不能就地改字，請按 F6 開輸入框打字（框裡一樣 F1~F5 改字、Enter 送回）"
_CON_MSG = {  # 終端機/CLI 前景時的導引：不能就地改字，一律導去 F6 輸入框
    "F1": _CON_F6,
    "F2": _CON_F6,
    "F7": _CON_F6,
    "F4": _CON_F6,
}


class _App19(_App18):
    # ---- 統一循環引擎（F1/F2/F4/F7 共用）----
    def _cycle_correct(self, read_fn, kind, cyclekey, force=False):
        got = read_fn()
        if got is None:                       # 取不到文字（read_fn 已通知）
            return
        target, writer = got
        cyc = self._cycle
        # 再按（非 force）、同 kind、目前文字＝目前候選（沒被你改動）→ 換下一個（中間安靜）
        if not force and cyc and cyc.get("kind") == kind and target == cyc["list"][cyc["idx"]]:
            cyc["idx"] = (cyc["idx"] + 1) % len(cyc["list"])
            nxt = cyc["list"][cyc["idx"]]
            writer(nxt)
            self._last = (cyc["orig"], nxt)
            if nxt == cyc["orig"]:            # 轉一圈回原句 → 提示一次；其餘候選安靜
                self._notify("已還原為原句")
            return
        # 新一輪 / 重算
        ranked = self.corrector.ranked_corrections(target)
        best = ranked[0]
        self._cycle = {"list": ranked, "idx": 0, "orig": target, "kind": kind}
        self._last = (target, best)
        if best != target:
            writer(best)
            from csc import logbook
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

    # ---- 各鍵的「怎麼取文字、怎麼寫回」 ----
    def _read_unit(self):
        time.sleep(0.08)
        window = self._grab_window()
        if window is None:
            self._notify("沒抓到文字（換個輸入欄試試）")
            return None
        unit, tail = textutil.split_tail_unit(window)
        if not unit.strip():
            self._notify("沒抓到要修的句子")
            return None
        prefix = window[: len(window) - len(unit) - len(tail)]
        return unit, lambda new: self._replace_window(prefix + new + tail)

    def _read_win(self, n):
        time.sleep(0.08)
        window = self._grab_window()
        if window is None:
            self._notify("沒抓到文字（換個輸入欄試試）")
            return None
        chunk = window[-n:]
        if not chunk.strip():
            self._notify("沒抓到要修的字")
            return None
        prefix = window[: len(window) - len(chunk)]
        return chunk, lambda new: self._replace_window(prefix + new)

    def _read_sel(self):
        saved = self._get_clip()
        sel = self._grab_selection(False)
        self._set_clip(saved)                 # grab 不自還原 → 立刻還原（寫回時 paste 自管剪貼簿）
        if not sel or sel == SENTINEL or not sel.strip():
            self._notify("沒有反白到文字（請先選取要修的字，再按 F4）")
            return None
        return sel, lambda new: self._paste_selection(new, reselect=True)

    def _paste_selection(self, text, reselect=True):
        """貼上 text 取代目前反白（自管剪貼簿、確認寫入避免貼到舊剪貼簿）；reselect 則貼完重新反白。"""
        saved = self._get_clip()
        if not self._set_clip_confirm(text):
            self._set_clip(saved)
            raise RuntimeError("剪貼簿被佔用，沒貼成功，請再按一次 F4")
        wk.combo(wk.VK_CONTROL, wk.VK_V)
        time.sleep(0.20)
        if reselect:
            wk.select_left(textutil.utf16_len(text))
        self._set_clip(saved)

    # ---- 四個入口：只負責終端機檢查 + 餵對的 read_fn / kind / cyclekey ----
    def _do_correct(self):                    # F1
        if _foreground_process() in _CONSOLES:
            self._notify(_CON_MSG["F1"]); return
        self._cycle_correct(self._read_unit, "unit", "F1")

    def _do_recorrect(self):                  # F2（force：一律以當前字重算）
        if _foreground_process() in _CONSOLES:
            self._notify(_CON_MSG["F2"]); return
        self._cycle_correct(self._read_unit, "unit", "F1", force=True)

    def _do_correct_window(self, n):          # F7（前 n 字整段）
        if _foreground_process() in _CONSOLES:
            self._notify(_CON_MSG["F7"]); return
        self._cycle_correct(lambda: self._read_win(n), "win", "F4")   # v2.1：前30字＝F4

    def _do_correct_selection(self):          # F4（反白手動修）
        if _foreground_process() in _CONSOLES:
            self._notify(_CON_MSG["F4"]); return
        self._cycle_correct(self._read_sel, "sel", "F5")   # v2.1：只改反白＝F5


# ===== tray_app_v30 =====
# -*- coding: utf-8 -*-
"""tray v30 = v29 + 讓 F2「重算」對 F1/F4/F7 都通用（共用同一個 F2 鍵）。

使用者：F2 的「以當前字重算」應該不只服務 F1，F4(反白)、F7(前30字) 也該能用，且共用 F2 鍵——
做完哪個鍵，按 F2 就重算那個鍵的當前目標。

統一引擎(v29)讓這件事很簡單：每輪循環只差在「用哪個 read_fn 取文字」。本版讓 `self._cycle`
**記住這輪的 read_fn 與 cyclekey**；F2 就拿上一次的 read_fn 重算(force=True)：
  - 上一次 F1 → F2 重算那個單位（同 v29 行為）
  - 上一次 F4 → F2 重算目前反白（會讀 F4 改完重新反白的那段，累積精修）
  - 上一次 F7 → F2 重算游標前 n 字
沒有上一次時 → 預設重算 F1 的單位。重算後 cycle 同樣記住 read_fn，故可連續 F2、或用該鍵循環。
"""
from csc import winkeys as wk  # noqa: F401  (與 v29 同模組空間，保持一致)


class _App20(_App19):
    def _cycle_correct(self, read_fn, kind, cyclekey, force=False):
        super()._cycle_correct(read_fn, kind, cyclekey, force)
        # 新一輪建立的 cycle 補記 read_fn / cyclekey（供 F2 重算用）；循環換候選時已有、不覆蓋
        if self._cycle and "read_fn" not in self._cycle:
            self._cycle["read_fn"] = read_fn
            self._cycle["cyclekey"] = cyclekey

    def _do_recorrect(self):
        """F2：重算『上一次那個鍵(F1/F4/F7)』的當前目標（force=True，一律以當前字重算）。"""
        cyc = self._cycle
        if cyc and cyc.get("read_fn"):
            key = cyc.get("cyclekey", "F1")
            if _foreground_process() in _CONSOLES:
                self._notify(_CON_MSG.get(key, _CON_MSG["F1"]))
                return
            self._cycle_correct(cyc["read_fn"], cyc["kind"], key, force=True)
        else:                                  # 沒有上一次 → 預設重算 F1 的單位
            if _foreground_process() in _CONSOLES:
                self._notify(_CON_MSG["F2"])
                return
            self._cycle_correct(self._read_unit, "unit", "F1", force=True)


# ===== tray_app_v31 =====
# -*- coding: utf-8 -*-
"""tray v31 = v30 + 按 F2 時自動記下『原題』到 error_cases.log（不必手動 F10、不必追蹤狀態）。

使用者洞察：按 F2 ＝「模型剛剛改錯了、我要重算」＝這就是一筆失敗案例的訊號。所以按 F2 時就
自動做 F10 的事——而且要在「**重算之前**」記，因為此刻 `self._cycle["orig"]` 還是**最初的原題**
（F1 循環不會動 orig；是 F2 重算才會把 orig 重設成當前字）。如此不必額外追蹤一堆 origin0 狀態，
F10「記到 F2 後的半成品」那個問題就自然解了。

行為：
  - 按 F2 且有進行中的循環 → 重算前先把 `self._cycle["orig"]` 記進 `error_cases.log`。
    第一次 F2 記的就是最初打錯的原話（正是要的難例）。靜默（不另跳通知，F2 本來就有「重算」通知）。
  - 與上一筆相同則略過（避免重複，例如 F2 後又手動 F10）。
  - 手動 F10 仍保留（純 F1、沒按 F2 而是自己改的情況用）。
"""


class _App21(_App20):
    def _do_recorrect(self):
        cyc = self._cycle
        if cyc and cyc.get("orig"):            # 重算前先記原題（此刻 orig 還是最初的字）
            self._auto_log_problem(cyc["orig"])
        super()._do_recorrect()

    def _auto_log_problem(self, prob):
        if not prob or prob == getattr(self, "_last_elogged", None):
            return                             # 與上一筆相同 → 不重複記
        try:
            from csc import logbook
            logbook.log_error_case(prob)
            self._last_elogged = prob
        except Exception:
            pass


# ===== tray_app_v32 =====
# -*- coding: utf-8 -*-
"""tray v32 = v31 + F1/F4/F7「按第二次(換下一個候選)」時也自動記原題。

延伸 v31 的想法：按 F2 ＝ 模型改錯的訊號。同理，**F1/F4/F7 要按第二次（第一個候選沒被接受、
要換下一個）也是「第一次沒改對」的訊號** → 在循環換候選那一刻自動記下原題。

實作：包裝 `_cycle_correct`，比對前後 `self._cycle`——若「**同一個 cycle 物件、idx 變了**」即剛做了
循環換候選（第二次以後按同一鍵），此時 `cyc["orig"]` 仍是最初原題 → `_auto_log_problem`
（沿用 v31 去重，故每個原題只記一次）。新一輪/重算會換成新的 cycle 物件，不在此記；F2 由 v31 的
`_do_recorrect` 負責。故「需要再按一次（F1/F4/F7 循環 或 F2 重算）」的硬案例都會自動進清單，
而一次就改對的happy path完全不記。
"""


class _App22(_App21):
    def _cycle_correct(self, read_fn, kind, cyclekey, force=False):
        before = self._cycle
        before_idx = before["idx"] if before else None
        super()._cycle_correct(read_fn, kind, cyclekey, force)
        cyc = self._cycle
        # 同一個 cycle 物件、idx 變了 → 剛做了循環換候選（按第二次）→ 第一次沒改對 → 記原題
        if cyc is before and before is not None and cyc.get("idx") != before_idx:
            self._auto_log_problem(cyc["orig"])


# ===== tray_app_v33 =====
# -*- coding: utf-8 -*-
"""tray v33 = v32 + 系統匣兩個新項目（暫停熱鍵/開啟難例清單）+ 暫停用不同顏色 + 記下『改錯成什麼』。

1. 暫停熱鍵偵測：突然要用前景程式的 F1~F12 等鍵時，可暫停我們的全域熱鍵。暫停＝真的
   UnregisterHotKey（前景程式才拿得回那些鍵；只靠 flag 略過沒用，OS 仍會吃掉），再點一次恢復。
   透過 `hotkey.HotkeyController`。**暫停時圖示換成不同顏色（紅）**，與載入(灰)/就緒(綠)/忙(黃) 區別。
2. 開啟 error_cases.log：直接打開難例清單檔（不存在就先建空檔）。
3. 記下『改錯成什麼』：失敗案例除了原題，再記**模型改錯成的內容**＝該輪最佳猜測 `_cycle["list"][0]`。
   只覆寫 `_auto_log_problem`（F2 觸發、F1/F4/F7 第二次觸發都經它）即一次到位；手動 F10 也改走它。
   故 error_cases.log 每行＝時間 / 原題 / 改錯成的內容。
"""
import os

import pystray

from csc import hotkey, logbook

ICON_PAUSE = _icon((200, 60, 60))     # 暫停＝紅（與 載入灰/就緒綠/忙黃 區別）


class _App23(_App22):
    def start(self):
        self._box_q = None
        self._box_problem = None
        self._hk = hotkey.start_hotkeys_thread({
            hotkey.VK_F1: self._on_f1,
            hotkey.VK_F2: self._on_f2_recorrect,
            hotkey.VK_F3: self._on_f2_learn,
            hotkey.VK_F4: self._on_f3,
            hotkey.VK_F5: self._on_f4_mark,
            hotkey.VK_F6: self._on_f6,
            hotkey.VK_F7: self._on_f7,
            hotkey.VK_F10: self._on_logerror,
        })
        self.icon.menu = self._build_menu()
        self.icon.run(setup=self._setup)

    # ---- 系統匣選單：前面加兩個新項目 ----
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
            self._notify("熱鍵已暫停：F1~F10 交還給目前的程式；要恢復請點系統匣選單")
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
                open(path, "a", encoding="utf-8").close()      # 還沒有難例就先建空檔，免得開檔失敗
            os.startfile(path)
        except Exception as e:
            self._notify(f"開啟失敗：{e}")

    # ---- 失敗案例：除了原題，再記『模型改錯成的內容』（＝該輪最佳猜測 list[0]）----
    def _auto_log_problem(self, prob=None, wrong=None):
        cyc = self._cycle
        if prob is None:
            prob = (cyc["orig"] if cyc else None) or (self._last[0] if self._last else None)
        if wrong is None:
            if cyc and cyc.get("list"):
                wrong = cyc["list"][0]                          # 模型的最佳猜測＝改錯成的內容
            elif self._last:
                wrong = self._last[1]
        if not prob or prob == getattr(self, "_last_elogged", None):
            return
        try:
            logbook.log_error_case(prob, wrong)
            self._last_elogged = prob
        except Exception:
            pass

    def _do_log_error(self):                                    # 手動 F10（一般欄、非框）
        if not self._cycle and not self._last:
            self._notify("沒有可記錄的上一筆（先按 F1/F7 修正，發現改錯了再按 F10）")
            return
        self._auto_log_problem()
        self._notify("已記錄改錯題目（含改錯成的內容）到 error_cases.log")


# ===== tray_app_v34 =====
# -*- coding: utf-8 -*-
"""tray v34 = v33 + F10 改用途：不再記『失敗題目』，改成『改完後補正確答案(gold)』。難例清單改存 JSONL。

使用者回報：F10 原本的用途（手動記下改錯的題目）已**無作用**——因為 v31/v32 起，按 F2 或
F1/F4/F7 按第二次時就會**自動**把原題（含改錯成的內容）記進難例清單，不必再手動 F10。

所以把 F10 改成更有價值的事：**我自己把字改對之後，按 F10 把『正確答案』補進該筆 log**。
每筆難例就從 (input, output) 補成 (input, output, gold) 完整三元組——(input→gold) 正是
微調 BERT / CSC 訓練最直接的訓練對，output 留作 hard negative 做錯誤分析。

存法：難例清單改用 **JSONL**（`logs/error_cases.jsonl`，同 history.jsonl 的 input/output/gold 語彙）。
欄位具名、免分隔符跳脫，可直接 `datasets.load_dataset('json', ...)` 餵進微調 pipeline。
（log_error_case / append_correct_answer 的改寫在 csc/logbook.py。）

實作：
  - 一般輸入欄：F10 → `_do_record_correct`。用『上一輪循環的 read_fn』（沒有就 `_read_unit`）
    重讀**目前欄位的文字**＝我改好的正確答案，呼叫 `logbook.append_correct_answer` 補進
    最後一筆的 `gold`。read_fn 是讀取用、非破壞性（_grab_window 會還原剪貼簿、把游標移回原位）。
  - 必須先有「這個階段自動記下的失敗案例」(`self._last_elogged`) 才允許補，避免誤補到上次開機的舊紀錄。
  - F6 框內：框沒走自動記流程，維持舊用途（記框內題目），不動。
  - 開啟難例清單：改用記事本開（`.jsonl` 在 Windows 多半沒預設關聯，os.startfile 會跳「選程式」）。
"""
import subprocess
import threading

from csc import logbook


class _App24(_App23):
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
        import os
        try:
            path = logbook.ERROR_FILE
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if not os.path.exists(path):
                open(path, "a", encoding="utf-8").close()
            subprocess.Popen(["notepad.exe", path])
        except Exception as e:
            self._notify(f"開啟失敗：{e}")


# ===== tray_app_v35 =====
# -*- coding: utf-8 -*-
"""tray v35 = v34 + F9 全域熱鍵切換『暫停/恢復熱鍵偵測』（原本只能從系統匣選單按）。

需求：給暫停一個快捷鍵。難點：暫停會 UnregisterHotKey **全部**熱鍵（把 F 鍵交還前景程式），
所以 F9 本身若也被取消，暫停後就沒辦法再用 F9 解除 → 必須在暫停時保留 F9：
`hotkey.start_hotkeys_thread(..., keep_vks=(VK_F9,))`（csc/hotkey.py 已支援）。
F9 直接觸發既有的 `_toggle_pause`（與系統匣那顆同一個），圖示一樣紅(暫停)/綠(恢復)。
丟背景緒呼叫，避免卡住熱鍵迴圈緒（_toggle_pause 內的 hk.toggle() 會 PostThreadMessage 回該緒）。
"""
import threading

from csc import hotkey


class _App25(_App24):
    def start(self):
        self._box_q = None
        self._box_problem = None
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
        self.icon.menu = self._build_menu()
        self.icon.run(setup=self._setup)

    def _on_f9_pause(self):
        threading.Thread(target=self._toggle_pause, daemon=True).start()


# ===== tray_app_v36 =====
# -*- coding: utf-8 -*-
"""tray v36 = v35 + 引擎換成 SelectCorrectorV8（v1.8：多音字收斂＋句尾語助詞守門）。

只覆寫 _load_model 把引擎從 v6 換成 v8（reading_ratio=0.02, guard_particles=True），
並沿用 v27 的 _install_box_problem_tracker（F6 框內 F10 記題目）。其餘（F1~F10、F9 暫停）全沿用 v35。
兩道手術刀說明見 csc/reading_filter.py。
"""
from csc.select_corrector import SelectCorrectorV8


class _App26(_App25):
    def _load_model(self):
        self.corrector = SelectCorrectorV8(margin=self.margin, lambda_prior=1.0,
                                           reading_ratio=0.02, guard_particles=True)
        self._install_box_problem_tracker()
        self._set(ICON_READY,
                  f"{APP_TITLE}：就緒（F1改/F2重算/F3學/F4反白/F5標記/F6框/F7前30字/F10記難例）")
        self._notify("就緒：F1 修 · F2 重算 · F3 學 · "
                     "F4 反白 · F5 標記 · F6 框 · F7 前30字 · F10 記難例")


# ===== tray_app_v37 =====
# -*- coding: utf-8 -*-
"""tray v37 = v36 + F6 框開啟後自動切到繁中注音輸入法（中文模式）。

不動那支 250 行的 _input_box_dialog：覆寫 _on_f6，照常開框(super)，另起一條看守緒，
等框視窗(標題含「輸入框」)出現+取得焦點後，呼叫 winkeys.switch_to_bopomofo 切輸入法。
Windows 切 IME 看環境臉色，故盡力而為；切輸入法/中文模式的細節見 csc/winkeys.py。
"""
import threading
import time

from csc import winkeys as wk


class _App27(_App26):
    def _on_f6(self):
        super()._on_f6()                        # 照常開框（行為全沿用）
        threading.Thread(target=self._box_to_bopomofo, daemon=True).start()

    def _box_to_bopomofo(self):
        for _ in range(50):                     # 最多等 ~2.5s 讓框出現並取得焦點
            hwnd = wk.find_window_by_title_substr("輸入框")
            if hwnd:
                time.sleep(0.2)                 # 等焦點/IME 就緒再切
                wk.switch_to_bopomofo(hwnd)
                return
            time.sleep(0.05)


# ===== tray_app_v38 =====
# -*- coding: utf-8 -*-
"""tray v38 = v37 + 系統匣兩個可記憶勾選，控制 F6 自動切輸入法行為。

- 「F6 自動切注音輸入法」：開框時自動把鍵盤配置切到繁中注音。**預設打勾**。
- 「F6 自動按 Shift（切中文）」：再敲一下 Shift 把英數切成中文模式。Shift 是『切換』、
  不適用所有情境（本來就中文會被切成英數），故**預設不勾**。
偏好存 logs/settings.json（csc/settings），關閉程式後仍記得。
"""
import time

import pystray

from csc import settings, winkeys as wk


class _App28(_App27):
    def _build_menu(self):
        items = list(super()._build_menu())
        ime_items = [
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("F6 自動切注音輸入法", self._toggle_auto_ime,
                             checked=lambda item: bool(settings.get("auto_switch_ime"))),
            pystray.MenuItem("F6 自動按 Shift（切中文模式）", self._toggle_auto_shift,
                             checked=lambda item: bool(settings.get("auto_press_shift"))),
        ]
        # 插在最後一項（離開）之前，讓「離開」維持在最底
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

    # 覆寫 v37 的看守緒：依勾選決定切不切、按不按 Shift
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


# ===== tray_app_v39 =====
# -*- coding: utf-8 -*-
"""tray v39 = v38 + 崩潰捕捉(csc/crashlog) + F1/F2/F6 麵包屑。

為抓『隨機閃退』(尤其 F6 框內按 F1)：main() 先 install() 開 faulthandler + 例外鉤子寫
logs/crash.log；F1/F2/F6 留麵包屑(含框開了沒)。純診斷、不改行為。
"""
from csc import crashlog


class _App29(_App28):
    def _on_f1(self):
        crashlog.log(f"F1 (box={getattr(self, '_box_q', None) is not None})")
        super()._on_f1()

    def _on_f2_recorrect(self):
        crashlog.log(f"F2 (box={getattr(self, '_box_q', None) is not None})")
        super()._on_f2_recorrect()

    def _on_f6(self):
        crashlog.log(f"F6 (box={getattr(self, '_box_q', None) is not None})")
        super()._on_f6()


# ===== tray_app_v40 =====
# -*- coding: utf-8 -*-
"""tray v40 = v39 + 系統匣「開機自動啟動」可勾選/可取消（csc/autostart，HKCU Run 機碼）。

勾＝寫 Run 機碼、取消＝刪除，完全可逆、免系統管理員。其餘(校正/F6切注音/勾選/崩潰捕捉)全沿用。
"""
import pystray

from csc import autostart, crashlog


class _App30(_App29):
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


# ===== tray_app_v41 =====
# -*- coding: utf-8 -*-
"""tray v41 = v40 + 修『隨機閃退』根因（v2.0）。原因與修法同 app_exe_v17：
F6 框的 Tkinter 跑在非主緒，自動循環 GC 跨緒回收 Tcl 物件 → abort。
gc.disable() 關自動 GC；框關閉後在框自己的緒 gc.collect()。"""
import gc

from csc import crashlog


class _App31(_App30):
    def _run_input_box(self, target_hwnd):
        try:
            super()._run_input_box(target_hwnd)
        finally:
            gc.collect()


# ===== tray_app_v42 =====
# -*- coding: utf-8 -*-
"""tray v42 = v41 + 系統匣「前往 GitHub」選單項（加在「聯繫作者」下方）。v2.01。"""
import gc
import webbrowser

import pystray

from csc import crashlog

GITHUB_URL = "https://github.com/ncku2026tcsc/tcsc"


class _App32(_App31):
    def _build_menu(self):
        gh = pystray.MenuItem("前往 GitHub（專案頁）", self._open_github)
        out = []
        for it in super()._build_menu():
            out.append(it)
            if (getattr(it, "text", "") or "").startswith("聯繫作者"):
                out.append(gh)
        return pystray.Menu(*out)

    def _open_github(self, *_):
        try:
            webbrowser.open(GITHUB_URL)
        except Exception:
            pass
        self._notify("已開啟 GitHub 專案頁")


# ===== tray_app_v43 =====
# -*- coding: utf-8 -*-
"""tray v43 = v42 + 修 bug：F6 輸入框內按 F10 改成「記正確答案(gold)」，與一般輸入欄一致。

回報：在 F6 框狀態下按 F10 記下的是『題目』而非『正確答案』。

查證：不是通知字串寫錯——舊的框內路 `_do_log_error_box` 把 `self._box_problem`（＝丟進
`ranked_corrections` 的尾單位＝題目/輸入）寫進 `input` 欄，且通知顯示同一個變數，兩者必然一致；
`log_error_case(prob)` 也根本沒寫 gold 欄。是真行為 bug：v34 起一般欄 F10 已改成「補正確答案」，
但框內這條路沒跟上、仍停在舊的「記題目」。

修法：框開著時，F10 不再記題目，而是把這次難例一次補齊成 (input=題目, output=模型修正, gold=
我改好的正確答案)。難點：gold＝框內當前文字，只活在 `_input_box_dialog` 的 Tk 緒閉包裡、跨緒讀
會踩到 Tcl『wrong thread』那顆地雷，故沿用既有的 cmd_q 機制——F10 丟 "f10" 進框的命令通道，由框
的 poll()（在 Tk 緒）呼叫本檔的 `_box_log_gold`（底層 box 方法已加一個向後相容的鉤子）。
"""
import gc
import threading

from csc import crashlog, logbook, textutil


class _App33(_App32):
    # ---- F10：框開著 → 記正確答案(gold)；一般欄 → 維持 v34 的補 gold ----
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


# ===== tray_app_v44 =====
# -*- coding: utf-8 -*-
"""tray v44 = v43 + 三件事（v2.03）：

(1) F6 框內對齊 F4/F7：框開著時 F4＝修反白選取、F7＝前30字整段重修，與一般輸入欄完全一致
    （先前只對齊了 F1/F2；F4/F7 的 `_on_f3`/`_on_f7` 在 `_busy` 時直接 return → 框內按了沒反應）。
    框內實作（box_correct_selection / poll 處理 f4,f7）在底層 box 方法 tray_app_v21；本檔負責把
    F4/F7 熱鍵像 F1/F2 一樣轉進框。

(2) gold 自動記錄：循環換候選（按第二次以後）那一刻，把『目前最後選到的選項』＝
    `_cycle["list"][idx]` 自動補進難例清單最後一筆的 gold；之後按 F10 仍可更新（沿用 v34 的
    `_do_record_correct`，重讀目前欄位＝最終的字）。故 gold 隨你選的候選自動更新，免手動。

(3) F6 框雙擊 Esc 才關閉（避免誤觸把辛苦打的字弄丟）—— 實作在 tray_app_v21 的 do_cancel。
"""
import gc
import threading

from csc import crashlog, logbook


class _App34(_App33):
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
        super()._cycle_correct(read_fn, kind, cyclekey, force)   # 內含 v32 的『idx 變了就自動記原題』
        cyc = self._cycle
        if cyc is before and before is not None and cyc.get("idx") != before_idx:
            self._autofill_gold()                                # 換了候選 → 同步更新 gold

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


# ===== tray_app_v45 =====
# -*- coding: utf-8 -*-
"""tray v45 = v44 + v2.1 大改：鍵位重排、移除舊 F5「標記」、新增 F3「還原回原字」、候選 10 個、tray 使用說明。

新鍵位（這版起的錨點）：
  F1 改字+換選項 · F2 重算 · F3 還原回原字(新) · F4 改前30字 · F5 只改反白
  F6 開輸入框 · F7 學習反白詞 · F9 更新 error cases(補gold) · F10 關閉熱鍵(暫停)
（移除舊 F5「標記」_on_f4_mark；F3 改成還原、F7 改成學詞、F4/F5/F9/F10 重排。box 內各鍵的轉發
 cmd 仍沿用既有名稱即可——功能正確，不必改 box；只另加 F3→"restore"。）

候選 10 個：`ranked_corrections` top_n 6→10 + `char_cand` 8→12 → 改字/前30/反白都最多 10 個選項，
搭配 F3 一鍵還原，不必靠 F1 繞一圈回原字。

使用說明：tray 右鍵「使用說明」→ Win32 訊息框（純文字、無 Tk、零閃退風險）。
"""
import ctypes
import gc
import threading

import pystray

from csc import crashlog, hotkey
from csc.usage import USAGE_TEXT


class TrayApp(_App34):
    def start(self):
        self._box_q = None
        self._box_problem = None
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
        }, keep_vks=(hotkey.VK_F10,))             # 暫停時保留關熱鍵的鍵，才能再開
        self.icon.menu = self._build_menu()
        self.icon.run(setup=self._setup)

    def _load_model(self):
        # 暫時靜音 super 的舊鍵位通知（避免啟動跳兩次），只留下面這條 v2.1 的
        _notify = self._notify
        self._notify = lambda *a, **k: None
        try:
            super()._load_model()                 # 載入 V8 + box tracker
        finally:
            self._notify = _notify
        self.corrector.char_cand = 12             # 產生上限拉高，配合 top_n=10 → 真的給到 10 個選項
        self.corrector.word_cand = 10
        self._set(ICON_READY, f"{APP_TITLE}：就緒（右鍵 → 使用說明）")
        self._notify("就緒 v2.1： F1 改字 · F2 重算 · F3 還原 · F4 前30字 · F5 反白 · "
                     "F6 框 · F7 學詞 · F9 記正解 · F10 關熱鍵\n"
                     "（已縮到右下角系統匣，背景執行中；右鍵有使用說明）")

    # ---- F3 還原回原字（框開著轉進框；否則還原一般欄）----
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

    # ---- tray 右鍵「使用說明」（Win32 訊息框，無 Tk）----
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
