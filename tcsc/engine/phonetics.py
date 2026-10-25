# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import os

from .. import datafs, paths

_DATA = "BPMFBase.txt"
_EXTRA = "BPMFBase_extra.txt"
_USER = paths.user("reading_user.tsv")

_ZHUYIN = set(range(0x3105, 0x312E))
_TONE_MARKS = set("ˊˇˋ˙")
_BPMF_OK = lambda s: bool(s) and all(ord(c) in _ZHUYIN or c in _TONE_MARKS for c in s)

_READING_DISBAND: set = set()

_READING_FLAGGED: set = set()

_READING_ESCAPE: set = set()

_CAND_LIMIT: dict = {}

_ASYM_PRUNE = False

_READING_BLACKLIST: set = set()

_char2readings: dict[str, set[str]] = {}
_char2readings_raw: dict[str, set[str]] = {}
_reading2chars: dict[str, list[str]] = {}
_extra_pairs: set = set()
_loaded = False


def _load_purge() -> None:
    for _p in datafs.glob("reading_purge*.tsv"):
        _load_purge_file(_p)


def _load_purge_file(name: str) -> None:
    if not datafs.exists(name):
        return
    try:
        with datafs.open_text(name) as f:
            for line in f:
                if line.startswith("#"):
                    continue
                p = line.rstrip("\n").split("\t")
                if len(p) < 3 or not p[1] or not p[2]:
                    continue
                op, ch, bpmf = p[0].strip(), p[1].strip(), p[2].strip()
                if op == "解散":
                    _READING_DISBAND.add((ch, bpmf))
                    _READING_BLACKLIST.add((ch, bpmf))
                elif op in ("刪", "刪但標註", "刪但留逃生", "黑名單"):
                    _READING_BLACKLIST.add((ch, bpmf))
                    if op == "刪但標註":
                        _READING_FLAGGED.add((ch, bpmf))
                    elif op == "刪但留逃生":
                        _READING_ESCAPE.add((ch, bpmf))
    except Exception:
        pass


_USER_ADDS: list = []


def _load_user() -> None:
    _USER_ADDS.clear()
    if not os.path.exists(_USER):
        return
    try:
        with open(_USER, encoding="utf-8") as f:
            for line in f:
                if line.startswith("#"):
                    continue
                p = line.rstrip("\n").split("\t")
                if len(p) < 3 or not p[1].strip() or not p[2].strip():
                    continue
                op, key = p[0].strip(), (p[1].strip(), p[2].strip())
                if op == "加":
                    for st in (_READING_BLACKLIST, _READING_ESCAPE, _READING_DISBAND):
                        st.discard(key)
                    _USER_ADDS.append(key)
                elif op == "加只逃生":
                    _READING_BLACKLIST.add(key)
                    _READING_ESCAPE.add(key)
                    _READING_DISBAND.discard(key)
                    _USER_ADDS.append(key)
                elif op == "刪":
                    _READING_BLACKLIST.add(key)
                    _READING_ESCAPE.discard(key)
                elif op == "刪但留逃生":
                    _READING_BLACKLIST.add(key)
                    _READING_ESCAPE.add(key)
    except Exception:
        pass


def user_entries() -> dict:
    out = {}
    if os.path.exists(_USER):
        with open(_USER, encoding="utf-8") as f:
            for line in f:
                p = line.rstrip("\n").split("\t")
                if not line.startswith("#") and len(p) >= 3 and p[1].strip() and p[2].strip():
                    out[(p[1].strip(), p[2].strip())] = p[0].strip()
    return out


def set_user_entry(ch: str, bpmf: str, op: str = "", note: str = "") -> None:
    lines, found = [], False
    if os.path.exists(_USER):
        with open(_USER, encoding="utf-8") as f:
            lines = f.read().splitlines()
    out = []
    for line in lines:
        p = line.split("\t")
        if not line.startswith("#") and len(p) >= 3 and (p[1].strip(), p[2].strip()) == (ch, bpmf):
            found = True
            if op:
                out.append("\t".join([op, ch, bpmf, note]))
            continue
        out.append(line)
    if op and not found:
        out.append("\t".join([op, ch, bpmf, note]))
    if not any(l.startswith("#") for l in out[:1]):
        out.insert(0, "# 使用者讀音表（Shift+F5 查詢窗寫的）：操作<TAB>字<TAB>讀音<TAB>備註；操作＝加／加只逃生／刪／刪但留逃生")
    os.makedirs(os.path.dirname(_USER), exist_ok=True)
    tmp = _USER + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    os.replace(tmp, _USER)


def reload() -> None:
    global _loaded
    for st in (_READING_DISBAND, _READING_FLAGGED, _READING_ESCAPE, _READING_BLACKLIST, _extra_pairs):
        st.clear()
    for d in (_char2readings, _char2readings_raw, _reading2chars):
        d.clear()
    _loaded = False
    _load()


def _ingest(ch: str, bpmf: str, extra: bool) -> None:
    _char2readings_raw.setdefault(ch, set()).add(bpmf)
    black = (ch, bpmf) in _READING_BLACKLIST
    escape = _ASYM_PRUNE or (ch, bpmf) in _READING_ESCAPE
    if black and (not escape or (ch, bpmf) in _READING_DISBAND):
        return
    _char2readings.setdefault(ch, set()).add(bpmf)
    if black:
        return
    lst = _reading2chars.setdefault(bpmf, [])
    if ch not in lst:
        lst.append(ch)
    if extra:
        _extra_pairs.add((ch, bpmf))


def _load(path: str = _DATA) -> None:
    global _loaded
    if _loaded:
        return
    _load_purge()
    _load_user()
    if not datafs.exists(path):
        raise FileNotFoundError(
            f"找不到注音字表 {path}；請先下載 McBopomofo 的 BPMFBase.txt 到 data/。"
        )
    names = [path] + ([_EXTRA] if datafs.exists(_EXTRA) else [])
    for pth in names:
        with datafs.open_text(pth) as f:
            for line in f:
                if line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) < 2:
                    continue
                ch, bpmf = parts[0], parts[1]
                if len(ch) != 1 or ord(ch) in _ZHUYIN or ch == bpmf:
                    continue
                if not _BPMF_OK(bpmf):
                    continue
                _ingest(ch, bpmf, extra=(pth != path))
    for ch, bpmf in _USER_ADDS:
        _ingest(ch, bpmf, extra=True)
    _loaded = True


def extra_readings(ch: str) -> set:
    _load()
    return {r for c, r in _extra_pairs if c == ch}


def readings(ch: str) -> set:
    _load()
    return _char2readings.get(ch, set())


def raw_readings(ch: str) -> set:
    _load()
    out = set(_char2readings.get(ch, set()))
    extra = _char2readings_raw.get(ch, set()) - out
    extra -= {r for c, r in _READING_DISBAND if c == ch}
    if not extra:
        return out
    from . import reading_filter
    w = reading_filter._compute_weights().get(ch) or {}
    return out | {r for r in extra if w.get(r, 0) > 0}


def same_sound(a: str, b: str) -> bool:
    _load()
    ra, rb = readings(a), readings(b)
    return bool(ra and rb and (ra & rb))


def circle(ch: str) -> list:
    _load()
    out, seen = [], set()
    for r in readings(ch):
        for x in _reading2chars.get(r, []):
            if x not in seen:
                seen.add(x)
                out.append(x)
    if ch not in seen:
        out.append(ch)
    return out


def homophones(ch: str, limit: int = 12) -> list:
    _load()
    limit = max(limit, _CAND_LIMIT.get(ch, 0))
    from . import wordphon
    wordphon._load()
    freq = wordphon._freq
    scored = []
    for r in readings(ch):
        chars = _reading2chars.get(r, [])
        by_freq = sorted(chars, key=lambda c: -freq.get(c, 0))
        f_rank = {c: i for i, c in enumerate(by_freq)}
        for i, c in enumerate(chars):
            if c != ch:
                scored.append((min(i, f_rank[c]), c))
    scored.sort(key=lambda x: x[0])
    seen, out = {ch}, []
    for _i, c in scored:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out[:limit]
