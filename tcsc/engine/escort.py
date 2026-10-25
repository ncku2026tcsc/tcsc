# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import os

from .. import paths, settings

_cache = {"mtime": None, "words": ()}
_pcache = {"mtime": None, "pairs": {}}

FILE = paths.user("escort_words.tsv")
PAIR_FILE = paths.user("escort_pairs.tsv")


def words():
    try:
        mt = os.path.getmtime(FILE)
    except OSError:
        return ()
    if _cache["mtime"] == mt:
        return _cache["words"]
    out = []
    wts = {}
    try:
        with open(FILE, encoding="utf-8-sig") as f:
            for line in f:
                p = line.split("\t")
                w = p[0].strip()
                if w and w != "詞組" and 2 <= len(w) <= 4 and w not in out:
                    out.append(w)
                    c = p[2].strip() if len(p) > 2 else ""
                    wts[w] = int(c) if c.isdigit() else 25
                if len(out) >= 1000:
                    break
    except Exception:
        return ()
    _cache["mtime"] = mt
    _cache["words"] = tuple(out)
    _cache["wts"] = wts
    return _cache["words"]


_ccache = {"mtime": None, "chars": ()}
CHAR_FILE = paths.user("escort_chars.tsv")

DIRECTIONAL_ONLY = frozenset("的地得")
_shipped = frozenset()


def set_shipped_chars(chs) -> None:
    global _shipped
    _shipped = frozenset(c for c in chs if len(c) == 1 and c not in DIRECTIONAL_ONLY)


def is_shipped(ch) -> bool:
    return ch in _shipped


def personal_chars():
    try:
        mt = os.path.getmtime(CHAR_FILE)
    except OSError:
        return ()
    if _ccache["mtime"] == mt:
        return _ccache["chars"]
    out = []
    try:
        with open(CHAR_FILE, encoding="utf-8-sig") as f:
            for line in f:
                c = line.split("\t")[0].strip()
                if len(c) == 1 and c not in out and c not in DIRECTIONAL_ONLY:
                    out.append(c)
                if len(out) >= 2000:
                    break
    except Exception:
        return ()
    _ccache["mtime"] = mt
    _ccache["chars"] = tuple(out)
    return _ccache["chars"]


def chars():
    mine = ticket_chars()
    return mine + tuple(c for c in sorted(_shipped) if c not in mine)


def shipped_chars():
    return tuple(sorted(_shipped))


def covered(kind, key) -> bool:
    if kind == "字":
        return key in _shipped
    if kind == "對":
        return len(key) == 2 and key[1] in _shipped
    return False


_ship_cache = {}


def _ship_rows(kind):
    from .. import datafs
    try:
        with datafs.open_text(f"escort/{kind}.tsv", encoding="utf-8-sig") as f:
            return [l.rstrip("\n").split("\t") for l in f if l.strip() and not l.startswith("#")]
    except OSError:
        return []


def _ship(kind):
    empty = {} if kind == "pairs" else ()
    if not settings.get("escort_shipped", True):
        return empty
    if kind not in _ship_cache:
        rows = _ship_rows(kind)
        if kind == "pairs":
            mp = {}
            for p in rows:
                if len(p) >= 2 and len(p[0]) == 1 and len(p[1]) == 1 and p[1] not in mp.setdefault(p[0], []):
                    mp[p[0]].append(p[1])
            _ship_cache[kind] = {k: tuple(v) for k, v in mp.items()}
        elif kind == "chars":
            _ship_cache[kind] = tuple(dict.fromkeys(p[0] for p in rows
                                                    if len(p[0]) == 1 and p[0] not in DIRECTIONAL_ONLY))
        else:
            _ship_cache[kind] = tuple(dict.fromkeys(p[0] for p in rows if 2 <= len(p[0]) <= 4))
    return _ship_cache[kind]


def ticket_words():
    mine = words()
    return mine + tuple(w for w in _ship("words") if w not in mine)


def ticket_pairs():
    mp = {k: list(v) for k, v in pairs().items()}
    for a, bs in _ship("pairs").items():
        for b in bs:
            if b not in mp.setdefault(a, []):
                mp[a].append(b)
    return {k: tuple(v) for k, v in mp.items()}


def ticket_chars():
    mine = personal_chars()
    return mine + tuple(c for c in _ship("chars") if c not in mine)


def pairs():
    try:
        mt = os.path.getmtime(PAIR_FILE)
    except OSError:
        return {}
    if _pcache["mtime"] == mt:
        return _pcache["pairs"]
    mp = {}
    wts = {}
    n = 0
    try:
        with open(PAIR_FILE, encoding="utf-8-sig") as f:
            for line in f:
                p = line.rstrip("\n").split("\t")
                if len(p) < 2 or len(p[0]) != 1 or len(p[1]) != 1:
                    continue
                if p[1] not in mp.setdefault(p[0], []):
                    mp[p[0]].append(p[1])
                    c = p[2].strip() if len(p) > 2 else ""
                    wts[(p[0], p[1])] = int(c) if c.isdigit() else 25
                    n += 1
                if n >= 1000:
                    break
    except Exception:
        return {}
    _pcache["mtime"] = mt
    _pcache["pairs"] = {k: tuple(v) for k, v in mp.items()}
    _pcache["wts"] = wts
    return _pcache["pairs"]


def _ensure_dir(path):
    import os as _os
    _os.makedirs(_os.path.dirname(path), exist_ok=True)


def add_word(w, note="手動保送"):
    w = (w or "").strip()
    if not (2 <= len(w) <= 4):
        return False, "詞票限 2~4 字"
    if w in words():
        return False, f"「{w}」已在常錯字清單"
    _ensure_dir(FILE)
    with open(FILE, "a", encoding="utf-8") as f:
        f.write(f"{w}\tF7\t\t{note}\n")
    _cache["mtime"] = None
    return True, f"已保送詞「{w}」"


def add_char(c, note="F7手動保送"):
    c = (c or "").strip()
    if len(c) != 1:
        return False, "字票限 1 字"
    if c in personal_chars():
        return False, f"「{c}」已在常錯字清單"
    _ensure_dir(CHAR_FILE)
    with open(CHAR_FILE, "a", encoding="utf-8") as f:
        f.write(f"{c}\t{note}\n")
    _ccache["mtime"] = None
    return True, f"已保送字「{c}」"


def add_pair(a, b, note="手動"):
    a, b = (a or "").strip(), (b or "").strip()
    if len(a) != 1 or len(b) != 1 or a == b:
        return False, "字對格式：打出的字→想要的字（各 1 字）"
    if b in pairs().get(a, ()):
        return False, f"「{a}→{b}」已在常錯字清單"
    _ensure_dir(PAIR_FILE)
    with open(PAIR_FILE, "a", encoding="utf-8") as f:
        f.write(f"{a}\t{b}\t{note}\n")
    _pcache["mtime"] = None
    return True, f"已保送字對「{a}→{b}」"


def _rewrite(path, keep_fn, cache):
    import os as _os
    if not _os.path.exists(path):
        return 0
    lines = open(path, encoding="utf-8-sig").read().splitlines()
    kept = [l for l in lines if keep_fn(l.split("\t"))]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(kept) + ("\n" if kept else ""))
    cache["mtime"] = None
    return len(lines) - len(kept)


def remove_word(w):
    return _rewrite(FILE, lambda p: p[0].strip() != w, _cache)


def remove_char(c):
    return _rewrite(CHAR_FILE, lambda p: p[0].strip() != c, _ccache)


def remove_pair(a, b):
    return _rewrite(PAIR_FILE,
                    lambda p: not (len(p) >= 2 and p[0].strip() == a
                                   and p[1].strip() == b), _pcache)


def _src_of(cols):
    tail = [c.strip() for c in cols if c.strip()]
    if not tail:
        return ""
    c = tail[-1]
    return f"統計×{c}" if c.isdigit() else c


def entries():
    wsrc, psrc, csrc = {}, {}, {}
    for path, store, keyn in ((FILE, wsrc, 1), (PAIR_FILE, psrc, 2), (CHAR_FILE, csrc, 1)):
        try:
            with open(path, encoding="utf-8-sig") as f:
                for line in f:
                    p = line.rstrip("\n").split("\t")
                    if len(p) >= keyn and all(p[i].strip() for i in range(keyn)):
                        k = p[0].strip() if keyn == 1 else (p[0].strip(), p[1].strip())
                        store.setdefault(k, _src_of(p[keyn:]))
        except OSError:
            pass
    out = []
    for w in words():
        out.append(("詞", w, w, wsrc.get(w, "")))
    for a, bs in pairs().items():
        for b in bs:
            out.append(("對", f"{a}→{b}", (a, b), psrc.get((a, b), "")))
    for c in personal_chars():
        out.append(("字", c, c, csrc.get(c, "")))
    return out


def counts():
    return len(words()), sum(len(v) for v in pairs().values()), len(personal_chars())


def clear_all():
    import os as _os
    n = sum(counts())
    for p, cache in ((FILE, _cache), (PAIR_FILE, _pcache), (CHAR_FILE, _ccache)):
        try:
            _os.path.exists(p) and _os.remove(p)
        except Exception:
            pass
        cache["mtime"] = None
    return n


def export_all(path):
    with open(path, "w", encoding="utf-8") as f:
        for kind, disp, _k, _s in entries():
            f.write(disp + "\n")
    return sum(counts())


def import_all(path):
    added = skipped = bad = 0
    for line in open(path, encoding="utf-8-sig"):
        s = line.strip().split("\t")[0]
        if not s:
            continue
        if "→" in s or ">" in s:
            ab = s.replace(">", "→").split("→")
            ok, _m = add_pair(ab[0], ab[-1]) if len(ab) >= 2 else (False, "")
        elif len(s) == 1:
            ok, _m = add_char(s)
        elif 2 <= len(s) <= 4:
            ok, _m = add_word(s)
        else:
            bad += 1
            continue
        added += 1 if ok else 0
        skipped += 0 if ok else 1
    return added, skipped, bad


def remove_by_tag(tag):
    if not tag:
        return []
    mark = f"F9收割@{tag}"
    removed = []

    def keep_word(p):
        hit = any(c.strip() == mark for c in p)
        if hit:
            removed.append(p[0].strip())
        return not hit

    def keep_pair(p):
        hit = any(c.strip() == mark for c in p)
        if hit and len(p) >= 2:
            removed.append(f"{p[0].strip()}→{p[1].strip()}")
        return not hit

    def keep_char(p):
        hit = any(c.strip() == mark for c in p)
        if hit:
            removed.append(p[0].strip())
        return not hit

    _rewrite(FILE, keep_word, _cache)
    _rewrite(PAIR_FILE, keep_pair, _pcache)
    _rewrite(CHAR_FILE, keep_char, _ccache)
    return removed


def weight(kind, key):
    if kind == "word":
        if key not in words():
            return 15
        return _cache.get("wts", {}).get(key, 25)
    if kind == "pair":
        if key[1] not in pairs().get(key[0], ()):
            return 15
        return _pcache.get("wts", {}).get(key, 25)
    return 20 if key in personal_chars() else 15


def harvest(inp, gold, mode="pair", court=None, tag=None):
    added = []
    if not inp or not gold or len(inp) != len(gold) or inp == gold:
        return added
    _BI = ({"在", "再"}, {"哪", "那"})
    _PRON = set("他她它牠祂你妳您")
    diffs = [i for i, (a, b) in enumerate(zip(inp, gold)) if a != b]
    if not diffs or len(diffs) > 6:
        return added
    from . import phonetics
    same = sum(1 for i in diffs if phonetics.same_sound(inp[i], gold[i]))
    if same * 2 < len(diffs):
        return added
    runs = []
    for i in diffs:
        if runs and i == runs[-1][-1] + 1:
            runs[-1].append(i)
        else:
            runs.append([i])
    def _fair(c, ok_at):
        return (len(c) == len(inp) and ok_at(c)
                and all(c[k] == inp[k] or c[k] == gold[k] for k in range(len(inp))))

    def _one(i):
        a, b = inp[i], gold[i]
        if {a, b} in _BI or (a in _PRON and b in _PRON):
            return
        if court and any(_fair(c, lambda c, i=i, b=b: c[i] == b) for c in court):
            return
        note = f"F9收割@{tag}" if tag else None
        if mode == "char" and b not in DIRECTIONAL_ONLY:
            ok, _m = add_char(b, note or "F7手動保送")
            if ok:
                added.append(b)
        else:
            ok, _m = add_pair(a, b, note or "手動")
            if ok:
                added.append(f"{a}→{b}")

    for run in runs:
        if len(run) == 1:
            _one(run[0])
        elif len(run) <= 4:
            lo, hi = run[0], run[-1] + 1
            sg = gold[lo:hi]
            from . import wordphon
            if wordphon.corpus_freq(sg) <= 0:
                k = lo
                while k < hi:
                    hit = None
                    for L in (4, 3, 2):
                        if k + L <= hi and wordphon.corpus_freq(gold[k:k + L]) > 0:
                            hit = gold[k:k + L]
                            break
                    if hit is None:
                        _one(k)
                        k += 1
                        continue
                    if court and any(_fair(c, lambda c, k=k, w=hit: c[k:k + len(w)] == w)
                                     for c in court):
                        k += len(hit)
                        continue
                    ok, _m = add_word(hit, (f"F9收割@{tag}" if tag else "手動保送"))
                    if ok:
                        added.append(hit)
                    k += len(hit)
                continue
            if court and any(_fair(c, lambda c: c[lo:hi] == sg) for c in court):
                continue
            ok, _m = add_word(sg, (f"F9收割@{tag}" if tag else "手動保送"))
            if ok:
                added.append(sg)
    return added
