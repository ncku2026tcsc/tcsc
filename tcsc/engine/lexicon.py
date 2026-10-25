# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import io
import itertools
import os

from .. import datafs, paths, settings
from . import phonetics, wordphon

FLOOR = 800
ENTRY_FREQ = 3000
PACK_DIR = "vocab"
COMMON_ID = "words_common"

LAYERS = (
    ("字表", "data/BPMFBase.txt ＋ BPMFBase_extra.txt",
     "字→讀音。讀音處刑的『字級那一刀』在讀字表當下就套用（phonetics 自己做）"),
    ("原生詞庫", "data/BPMFMappings.txt",
     "詞→讀音序列。它不是詞庫包，詞頻另外來自 phrase.occ／modern_freq"),
    ("詞庫包", "data/vocab/*.tsv ＋ %APPDATA%/tcsc/words_common.tsv",
     "常識詞庫：多字詞＝入籍＋底價 800；單字＝出場權（見 _grant_entry）。"
     "一包一檔、依檔名排序、可個別開關"),
    ("個人詞", "%APPDATA%/tcsc/userforce.txt",
     "F7 段數制：入籍＋幾何加分，同音席次排最前"),
    ("保送", "%APPDATA%/tcsc/escort_words.tsv ／ escort_pairs.tsv ／ escort_chars.tsv",
     "escort 模組自己讀自己寫，這裡不碰。列在表上是為了一眼看得到資料層全貌"),
    ("讀音修正", "data/word_reading_fix.tsv",
     "拿掉詞表裡機械展開出來的假讀音序列（詞本身留著）"),
    ("讀音處刑", "data/reading_purge*.tsv 的『解散』列",
     "解散＝字級詞級一起拿掉；字級在字表層已經切過，這裡切詞級那一刀"),
    ("詞處刑", "data/word_purge.tsv",
     "詞整個拿掉（祇有／幹麼 那種：讀音黑名單是字級的刀，治不了詞本身）"),
    ("詞頻", "data/phrase.occ、modern_freq.tsv、freq_patch.tsv ＋ %APPDATA%/tcsc/freq_patch_user.tsv",
     "max 併只抬不降；滴灌表裡沒戶口的詞順手補籍（攻段欄不讀＝事後加分不抄）"),
    ("底價", "data/word_floor.tsv ＋ 詞庫包的 800",
     "max 併只抬不降；最後依詞頻重排同音席次（F7 自學詞排最前）"),
)

_MAP = "BPMFMappings.txt"
_OCC = "phrase.occ"
_MODERN = "modern_freq.tsv"
_FLOOR_FILE = "word_floor.tsv"
_WPURGE = "word_purge.tsv"
_WFIX = "word_reading_fix.tsv"
_FREQPATCH = ("freq_patch.tsv", paths.user("freq_patch_user.tsv"))
_FREQPATCH_TAG = {_FREQPATCH[0]: "官方滴灌", _FREQPATCH[1]: "手動注入（你自己加的）"}


def _exists(src):
    return os.path.exists(src) if os.path.isabs(src) else datafs.exists(src)


def _open(src):
    return io.open(src, encoding="utf-8") if os.path.isabs(src) else datafs.open_text(src)

_pack_floor: dict = {}
_pack_entry: dict = {}
_meta_cache: dict = {}


def _enroll(word: str, seq: tuple, origin: str) -> None:
    wordphon._origin.setdefault(word, set()).add(origin)
    wordphon._word2seqs.setdefault(word, set()).add(seq)
    lst = wordphon._seq2words.setdefault(seq, [])
    if word not in lst:
        lst.append(word)


def _drop_seqs(drop: dict) -> None:
    for w, bad in drop.items():
        seqs = wordphon._word2seqs.get(w)
        if not seqs:
            continue
        keep = seqs - bad
        if not keep:
            continue
        for s in seqs - keep:
            lst = wordphon._seq2words.get(s)
            if lst and w in lst:
                lst.remove(w)
        wordphon._word2seqs[w] = keep


def _bump(word: str, value: int) -> None:
    if value > wordphon._freq.get(word, 0):
        wordphon._freq[word] = value


def _resort(seqs=None) -> None:
    def key(w):
        return (w not in wordphon._userforce_level, -wordphon._freq.get(w, 0))
    if seqs is None:
        for lst in wordphon._seq2words.values():
            lst.sort(key=key)
        return
    for s in seqs:
        lst = wordphon._seq2words.get(s)
        if lst:
            lst.sort(key=key)


def _pack_meta(path: str) -> dict:
    mtime = datafs.mtime(path)
    if mtime is None:
        return {}
    hit = _meta_cache.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    meta = {"id": os.path.basename(path)[:-4], "name": "", "date": "",
            "note": "", "default_on": True, "count": 0}
    try:
        with datafs.open_text(path) as f:
            for line in f:
                if line.startswith("#"):
                    body = line[1:].strip()
                    for key in ("name", "date", "note", "default"):
                        if body.lower().startswith(key + ":"):
                            val = body.split(":", 1)[1].strip()
                            if key == "default":
                                meta["default_on"] = val.lower() != "off"
                            else:
                                meta[key] = val
                    continue
                if line.strip():
                    meta["count"] += 1
    except OSError:
        return {}
    meta["name"] = meta["name"] or meta["id"]
    _meta_cache[path] = (mtime, meta)
    return meta


def _pack_rows(path: str):
    try:
        f = datafs.open_text(path)
    except OSError:
        return
    with f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            p = line.rstrip("\n").split("\t")
            word = p[0].strip()
            if not word:
                continue
            seqs = []
            if len(p) >= 2 and p[1].strip():
                for one in p[1].split("｜"):
                    seq = tuple(one.split())
                    if len(word) == len(seq):
                        seqs.append(seq)
            floor = FLOOR
            if len(p) >= 3 and p[2].strip().isdigit():
                floor = int(p[2])
            yield word, seqs, floor


def _metas() -> list:
    out = []
    for path in datafs.glob(PACK_DIR + "/*.tsv"):
        meta = _pack_meta(path)
        if meta:
            out.append(meta)
    return out


def _off_set() -> set:
    try:
        stored = settings._load()
    except Exception:
        stored = {}
    if "vocab_packs_off" in stored:
        return set(stored["vocab_packs_off"] or ())
    return {m["id"] for m in _metas() if not m["default_on"]}


def packs() -> list:
    off = _off_set()
    out = []
    for meta in _metas():
        meta = dict(meta)
        meta["enabled"] = meta["id"] not in off
        out.append(meta)
    common = wordphon.commonwords()
    from .userpaths import commonwords_path
    p = commonwords_path()
    try:
        import time
        date = time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(p)))
    except OSError:
        date = "—"
    out.append({"id": COMMON_ID, "name": "我的常識詞（F5 學的）", "date": date,
                "note": "F5 隨手學進來的詞，永遠載入", "count": len(common),
                "default_on": True, "enabled": True})
    return out


def set_pack_enabled(pack_id: str, on: bool) -> bool:
    if pack_id == COMMON_ID:
        return True
    off = _off_set()
    if on:
        off.discard(pack_id)
    else:
        off.add(pack_id)
    settings.set("vocab_packs_off", sorted(off))
    reload_all()
    return on


def _h_chars(_path) -> None:
    phonetics._load()


def _h_native(_path) -> None:
    if not datafs.exists(_MAP):
        return
    with datafs.open_text(_MAP) as f:
        for line in f:
            p = line.split()
            if len(p) < 2:
                continue
            word, seq = p[0], tuple(p[1:])
            if len(word) == len(seq):
                _enroll(word, seq, "小麥原生")


def _load_common() -> set:
    touched = set()
    for word, seqs in wordphon.commonwords().items():
        for seq in seqs:
            _enroll(word, tuple(seq), COMMON_ID)
            touched.add(tuple(seq))
        _pack_floor[word] = max(_pack_floor.get(word, 0), FLOOR)
    return touched


def _h_packs(_glob) -> None:
    for meta in packs():
        if not meta["enabled"]:
            continue
        if meta["id"] == COMMON_ID:
            _load_common()
            continue
        path = PACK_DIR + "/" + meta["id"] + ".tsv"
        for word, seqs, floor in _pack_rows(path):
            if len(word) == 1:
                _grant_entry(word, meta["id"])
                continue
            for seq in seqs:
                _enroll(word, seq, meta["id"])
            if not seqs:
                wordphon._origin.setdefault(word, set()).add(meta["id"])
            _pack_floor[word] = max(_pack_floor.get(word, 0), floor)


def _grant_entry(ch: str, origin: str) -> None:
    wordphon._origin.setdefault(ch, set()).add(origin)
    _pack_entry[ch] = max(_pack_entry.get(ch, 0), ENTRY_FREQ)
    wordphon._userforce_freq[ch] = max(wordphon._userforce_freq.get(ch, 0), ENTRY_FREQ)
    from . import escort
    escort.set_shipped_chars(_pack_entry.keys())


def _h_userforce(_path) -> None:
    path = wordphon._USERFORCE
    if not os.path.exists(path):
        return
    with io.open(path, encoding="utf-8") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 3 or not p[0]:
                continue
            word, seq, tier = p[0], tuple(p[1].split()), p[2]
            if len(word) != len(seq):
                continue
            _enroll(word, seq, "F7 自學詞")
            wordphon._uf_pool.append((word, seq))
            lv = wordphon._uf_level(tier)
            add = int(wordphon._UF_BASE * (wordphon._UF_MULT ** (lv - 1)))
            wordphon._userforce_freq[word] = max(wordphon._userforce_freq.get(word, 0), add)
            wordphon._userforce_level[word] = max(wordphon._userforce_level.get(word, 0), lv)


def _h_escort(_path) -> None:
    return


def _h_reading_fix(_path) -> None:
    if not datafs.exists(_WFIX):
        return
    drop = {}
    with datafs.open_text(_WFIX) as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            p = line.rstrip("\n").split("\t")
            if len(p) < 2:
                continue
            w, seq = p[0].strip(), tuple(p[1].split())
            if w and seq:
                drop.setdefault(w, set()).add(seq)
    _drop_seqs(drop)


def _h_reading_purge(_path) -> None:
    band = getattr(phonetics, "_READING_DISBAND", set())
    if not band:
        return
    bad = {}
    for ch, r in band:
        bad.setdefault(ch, set()).add(r)
    drop = {}
    for w, seqs in wordphon._word2seqs.items():
        hit = {s for s in seqs
               if any(c in bad and s[i] in bad[c]
                      for i, c in enumerate(w) if i < len(s))}
        if hit:
            drop[w] = hit
    _drop_seqs(drop)


def _h_word_purge(_path) -> None:
    if not datafs.exists(_WPURGE):
        return
    with datafs.open_text(_WPURGE) as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            w = line.split("\t")[0].strip()
            if not w:
                continue
            for seq in wordphon._word2seqs.pop(w, ()):
                lst = wordphon._seq2words.get(seq)
                if lst and w in lst:
                    lst.remove(w)
            wordphon._origin.pop(w, None)


def _h_freq(_paths) -> None:
    if datafs.exists(_OCC):
        with datafs.open_text(_OCC) as f:
            for line in f:
                p = line.split()
                if len(p) >= 2 and p[-1].lstrip("-").isdigit():
                    wordphon._freq[p[0]] = int(p[-1])
    if datafs.exists(_MODERN):
        with datafs.open_text(_MODERN) as f:
            for line in f:
                if line.startswith("#"):
                    continue
                p = line.split()
                if len(p) >= 2 and p[-1].isdigit():
                    _bump(p[0], int(p[-1]))
    for path in _FREQPATCH:
        if not _exists(path):
            continue
        tag = _FREQPATCH_TAG[path]
        with _open(path) as f:
            for line in f:
                if line.startswith("#"):
                    continue
                p = line.rstrip("\n").split("\t")
                if len(p) < 2 or not p[0]:
                    continue
                word = p[0].strip()
                try:
                    fq = int(p[1])
                except (ValueError, TypeError):
                    continue
                if fq > wordphon._freq.get(word, 0):
                    wordphon._origin.setdefault(word, set()).add(tag)
                    wordphon._freq[word] = fq
                if word not in wordphon._word2seqs and len(word) >= 2:
                    per = [sorted(phonetics.readings(ch)) for ch in word]
                    if all(per):
                        for seq in list(itertools.product(*per))[:16]:
                            _enroll(word, seq, tag)
                            wordphon._patch_enrolled.add(word)


def _h_floor(_path) -> None:
    if datafs.exists(_FLOOR_FILE):
        with datafs.open_text(_FLOOR_FILE) as f:
            for line in f:
                if line.startswith("#"):
                    continue
                p = line.rstrip("\n").split("\t")
                if len(p) >= 2 and p[0] and p[1].strip().isdigit():
                    _bump(p[0], int(p[1]))
    for word, floor in _pack_floor.items():
        _bump(word, floor)
    _resort()


_HANDLERS = {
    "字表": _h_chars,
    "原生詞庫": _h_native,
    "詞庫包": _h_packs,
    "個人詞": _h_userforce,
    "保送": _h_escort,
    "讀音修正": _h_reading_fix,
    "讀音處刑": _h_reading_purge,
    "詞處刑": _h_word_purge,
    "詞頻": _h_freq,
    "底價": _h_floor,
}


def _reset() -> None:
    wordphon._word2seqs.clear()
    wordphon._seq2words.clear()
    wordphon._freq.clear()
    wordphon._origin.clear()
    wordphon._userforce_freq.clear()
    wordphon._userforce_level.clear()
    wordphon._uf_pool.clear()
    wordphon._patch_enrolled.clear()
    _pack_floor.clear()
    _pack_entry.clear()
    from . import escort
    escort.set_shipped_chars(())


def load() -> None:
    _reset()
    for kind, path, _note in LAYERS:
        _HANDLERS[kind](path)


def reload_all() -> None:
    load()


def _undo_userforce() -> set:
    touched = set()
    for word, seq in wordphon._uf_pool:
        lst = wordphon._seq2words.get(seq)
        if lst and word in lst:
            lst.remove(word)
        s = wordphon._word2seqs.get(word)
        if s:
            s.discard(seq)
            if not s:
                wordphon._word2seqs.pop(word, None)
        touched.add(seq)
    wordphon._uf_pool.clear()
    wordphon._userforce_freq.clear()
    wordphon._userforce_level.clear()
    return touched


def _undo_common() -> set:
    live = wordphon.commonwords()
    touched = set()
    for w in [w for w, src in wordphon._origin.items() if COMMON_ID in src]:
        if w in live:
            continue
        for seq in list(wordphon._word2seqs.get(w) or ()):
            lst = wordphon._seq2words.get(seq)
            if lst and w in lst:
                lst.remove(w)
            touched.add(seq)
        wordphon._word2seqs.pop(w, None)
        wordphon._origin[w].discard(COMMON_ID)
        if not wordphon._origin[w]:
            wordphon._origin.pop(w, None)
    return touched


def reload_user() -> None:
    touched = _undo_common()
    touched |= _undo_userforce()
    touched |= _load_common()
    _h_userforce("")
    for ch, add in _pack_entry.items():
        wordphon._userforce_freq[ch] = max(
            wordphon._userforce_freq.get(ch, 0), add)
    for word, floor in _pack_floor.items():
        _bump(word, floor)
    touched |= {seq for _w, seq in wordphon._uf_pool}
    _resort(touched)
