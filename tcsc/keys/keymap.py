# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/tcsc2026/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
from collections import namedtuple

from . import hotkey
from ..symbols import SYM_SPEC

Key = namedtuple("Key", "combo vk mods action verb gate")
Row = namedtuple("Row", "id combo verb default")

CTRL, ALT, SHIFT = hotkey.MOD_CONTROL, hotkey.MOD_ALT, hotkey.MOD_SHIFT
CA, CAS = CTRL | ALT, CTRL | ALT | SHIFT
VK_LEFT, VK_RIGHT, VK_UP, VK_DOWN, VK_BACK = 0x25, 0x27, 0x26, 0x28, 0x08
VK_TAB, VK_RETURN = 0x09, 0x0D

_NAME2VK = {"TAB": 0x09, "SPACE": 0x20, "ENTER": 0x0D, "BACKSPACE": 0x08,
            "ESC": 0x1B, "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28,
            "HOME": 0x24, "END": 0x23, "PGUP": 0x21, "PGDN": 0x22,
            "INS": 0x2D, "DEL": 0x2E,
            "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD,
            "\\": 0xDC, ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF}
for _i in range(11):
    _NAME2VK[f"F{_i + 1}"] = 0x70 + _i
for _c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
    _NAME2VK[_c] = ord(_c)
_VK2NAME = {v: k for k, v in _NAME2VK.items()}
_MODS = {"CTRL": CTRL, "ALT": ALT, "SHIFT": SHIFT}
_BARE_OK = {VK_TAB} | {0x70 + i for i in range(11)}

SYM_NAMES = tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") + ("`", "-", "=", "[", "]", "\\", ";", "'", ",", ".", "/")


def sym_table(get):
    off = set(get("sym_off") or [])
    user = {}
    for k, v in (get("sym_user") or {}).items():
        n = str(k).upper()
        if n in SYM_NAMES and isinstance(v, str) and v:
            user[n] = v
    out = []
    for n, o in SYM_SPEC:
        if n in user:
            out.append((n, user.pop(n), "自訂"))
        elif n not in off:
            out.append((n, o, "內建"))
    out += [(n, o, "自訂") for n, o in sorted(user.items())]
    return out


REBINDABLE = ("f1", "tab", "f2", "f3", "sf1", "sf2", "sf3", "f4", "sf4", "f8", "sf8", "f5", "sf5", "sf6", "f7", "sf7", "f9", "sf9", "f10")

GROUPS = [
    ("改字", [
        Key("F1", hotkey.VK_F1, 0, "f1", "改字：抓游標前那句（有反白＝只修反白）；連按＝換下一個候選", None),
        Key("Tab", VK_TAB, 0, "tab", "＝F1（這句怪怪的就按 Tab）；終端機與自家視窗裡＝原生 Tab", "tab_f1"),
        Key("F2", hotkey.VK_F2, 0, "f2", "退回上一個候選；退到底＝原句；再按＝刪掉剛剛那句（先提示、再按才刪）；沒在改字＝F2 照常給程式", None),
        Key("F3", hotkey.VK_F3, 0, "f3", "重算：把目前算的結果再丟進去算一遍", None),
        Key("Shift+F1", hotkey.VK_F1, SHIFT, "sf1", "改前一句：游標和後句都不動（終端機也行）", None),
        Key("Shift+F2", hotkey.VK_F2, SHIFT, "sf2", "一鍵回原句（保本）；誤按可用 F2 退回", None),
        Key("Shift+F3", hotkey.VK_F3, SHIFT, "sf3", "改後一句：游標和前文都不動；後句要在同一行（終端機也行）", None),
        Key("F4", hotkey.VK_F4, 0, "f4", "換寫回方式：貼上 → 打字 → 退格重打（某個程式改不動或改壞時，換一種再按 F1）", "mode_keys"),
        Key("Shift+F4", hotkey.VK_F4, SHIFT, "sf4", "換抓字方式：自動 → 直接讀畫面 → 剪貼簿（讀不到字時換一種）", "mode_keys"),
        Key("F8", hotkey.VK_F8, 0, "f8", "在再：句子裡在、再的各種換法，最通順的先（有反白＝只換反白那段）；連按＝下一個、F2 退回；系統匣可加開的得地", "xuci_key"),
        Key("Shift+F8", hotkey.VK_F8, SHIFT, "sf8", "人稱鍵：你／妳、他／她／它 逐一換，最通順的先（有反白＝只換反白那段）；連按＝下一個、F2 退回；只換人稱", "pron_key"),
    ]),
    ("學詞", [
        Key("F5", hotkey.VK_F5, 0, "f5", "把反白的詞收進常識詞庫（讀音多組會跳窗讓你選）；沒反白＝F5 照常給程式（重新整理）", None),
        Key("Shift+F5", hotkey.VK_F5, SHIFT, "sf5", "詞庫查詢窗：查詞／反查注音／看同音圈／補讀音（有反白＝直接查）", None),
        Key("F7", hotkey.VK_F7, 0, "f7", "把反白的詞學進個人詞庫（再按一次加強）", None),
        Key("Shift+F7", hotkey.VK_F7, SHIFT, "sf7", "個人詞庫管理窗", None),
        Key("Shift+F6", hotkey.VK_F6, SHIFT, "sf6", "常錯字清單", None),
    ]),
    ("記難例", [
        Key("F9", hotkey.VK_F9, 0, "f9", "把目前選到的字記成正解（改字改不對時，自己改對再按）；沒在改字＝F9 照常給程式", None),
        Key("Shift+F9", hotkey.VK_F9, SHIFT, "sf9", "移除上一筆難例（記錯了反悔用；會說移了哪筆）", None),
    ]),
    ("快速移動（Ctrl+Alt 按著）", [
        Key("Ctrl+Alt+←→", VK_LEFT, CA, "mv_left", "游標左右：單按 1 格、快速雙擊跳到標點、接數字走 N 格", "movers_on"),
        Key("Ctrl+Alt+↑↓", VK_UP, CA, "mv_up", "游標上下：單按 1 行、快速雙擊跳到空行段", "movers_on"),
        Key("＋Shift", VK_LEFT, CAS, "mv_left", "以上全部變成圈選，圈完按 F1 修", "movers_on"),
        Key("Ctrl+Alt+Backspace", VK_BACK, CA, "del_left", "往左刪：單按 1 字、雙擊刪到標點、接數字刪 N 字；加 Shift＝往右刪", "movers_on"),
    ]),
    ("符號鍵（Ctrl+Alt 按著）", [
        Key(f"Ctrl+Alt+{n}", _NAME2VK[n.upper()], CA, f"sym:{out}", f"打出 {out}", "symkeys_on")
        for n, out in SYM_SPEC
    ]),
    ("統一換行", [
        Key("Ctrl+Enter", VK_RETURN, CTRL, "enter_unify",
            "在哪都是「換行不送出」：終端機送 Ctrl+Enter、其他程式送 Shift+Enter（肌肉記憶退休）", "enter_unify_on"),
        Key("Shift+Enter", VK_RETURN, SHIFT, "enter_unify", "同上", "enter_unify_on"),
    ]),
    ("其他", [
        Key("F10", hotkey.VK_F10, 0, "f10", "暫停熱鍵（把 F 鍵還給目前程式）：按一下 15 秒、兩下 30 秒、三下永久；永久時再按恢復", None),
        Key("Shift+F11", hotkey.VK_F11, SHIFT, "sf11",
            "版本／引擎速查；1.5 秒內連按兩下＝開發者模式（3 分鐘內改字不記 error_cases／history）", None),
        Key("Esc Esc", 0, 0, "", "改字進行中連按兩下＝這一輪作廢", None),
        Key("雙擊系統匣圖示", 0, 0, "", "放開卡住的按鍵", None),
    ]),
]

_MOVER_BINDS = ([((vk, CA), f"mv:{vk}") for vk in (VK_LEFT, VK_RIGHT, VK_UP, VK_DOWN)]
                + [((vk, CAS), f"mv:{vk}") for vk in (VK_LEFT, VK_RIGHT, VK_UP, VK_DOWN)]
                + [((VK_BACK, CA), "del:left"), ((VK_BACK, CAS), "del:right")])


def parse_combo(s):
    parts = [p.strip().upper() for p in (s or "").split("+") if p.strip()]
    if not parts:
        return None
    mods = 0
    for p in parts[:-1]:
        if p not in _MODS:
            return None
        mods |= _MODS[p]
    vk = _NAME2VK.get(parts[-1])
    if vk is None:
        return None
    if mods == 0 and vk not in _BARE_OK:
        return None
    return (vk, mods)


def format_combo(bind):
    vk, mods = bind
    pre = ("Ctrl+" if mods & CTRL else "") + ("Alt+" if mods & ALT else "") \
        + ("Shift+" if mods & SHIFT else "")
    return pre + _VK2NAME.get(vk, hex(vk))


def bind_label(key, get):
    bind = key if isinstance(key, tuple) else (key, 0)
    name = format_combo(bind)
    for n, out, _src in sym_table(get):
        if (_NAME2VK[n], CA) == bind:
            return f"{name}（打出 {out}）"
    eff, _ = resolve(get)
    for _g, keys in GROUPS:
        for k in keys:
            if k.vk and eff.get(k.action, (k.vk, k.mods)) == bind:
                return f"{name}（{k.verb.split('：')[0]}）"
    return name


def rows():
    out = []
    for _g, keys in GROUPS:
        for k in keys:
            if k.action in REBINDABLE:
                out.append(Row(k.action, k.combo, k.verb, (k.vk, k.mods)))
    return out


def _fixed_binds():
    fixed = {key for key, _a in _MOVER_BINDS}
    for _g, keys in GROUPS:
        for k in keys:
            if k.vk and k.action not in REBINDABLE:
                fixed.add((k.vk, k.mods))
    return fixed


def resolve(get):
    ov = get("key_overrides") or {}
    fixed = _fixed_binds()
    out, problems, taken = {}, [], {}
    for r in rows():
        bind = r.default
        s = ov.get(r.id) if isinstance(ov, dict) else None
        if s:
            b = parse_combo(s)
            if b is None:
                problems.append(f"{r.id}:「{s}」解析不了或違規＝回預設")
            elif b in fixed:
                problems.append(f"{r.id}:「{s}」撞到固定鍵位（和弦文法）＝回預設")
            else:
                bind = b
        if bind in taken and taken[bind] != r.id:
            problems.append(f"{r.id} 與 {taken[bind]} 撞鍵「{format_combo(bind)}」＝{r.id} 回預設")
            bind = r.default
        taken.setdefault(bind, r.id)
        out[r.id] = bind
    if not out.get("f1"):
        out["f1"] = (hotkey.VK_F1, 0)
        problems.append("f1 動作不可為空＝強制回 F1")
    return out, problems


def bindings(actions, get):
    eff, _ = resolve(get)
    b = {}
    for _grp, keys in GROUPS:
        for k in keys:
            if not k.vk or k.action.startswith(("mv_", "del_", "sym:")):
                continue
            if k.gate and not get(k.gate):
                continue
            cb = actions.get(k.action)
            if cb is None:
                continue
            b[eff.get(k.action, (k.vk, k.mods))] = cb
    sym = actions.get("sym")
    if sym is not None and get("symkeys_on"):
        for n, out, _src in sym_table(get):
            b[(_NAME2VK[n], CA)] = (lambda o=out: sym(o))
    if get("movers_on"):
        for key, act in _MOVER_BINDS:
            cb = actions.get(act)
            if cb is not None:
                b[key] = cb
    return b


def overridden(get):
    eff, _ = resolve(get)
    return {bind for r in rows() for bind in [eff.get(r.id, r.default)]
            if bind != r.default and bind[1]}
