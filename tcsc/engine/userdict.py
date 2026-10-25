# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import os

from .userpaths import userforce_path

_FILE = userforce_path()
_MAX_LEVEL = 20


def seqs_of(word: str) -> list:
    out = []
    for w, reads, _lvl in _read_rows():
        seq = tuple(reads.split())
        if w == word and len(seq) == len(word) and seq not in out:
            out.append(seq)
    return out


def auto_seqs(word: str) -> list:
    from . import addword
    seqs = seqs_of(word)
    if seqs:
        return seqs
    combos = addword.reading_combos(word)
    return combos if len(combos) == 1 else []


def _level_of(field: str) -> int:
    if field == "soft":
        return 1
    if field == "hard":
        return _MAX_LEVEL
    try:
        return max(1, min(_MAX_LEVEL, int(field)))
    except (ValueError, TypeError):
        return 1


def cap_for(word: str) -> int:
    return _MAX_LEVEL


def _read_rows():
    rows = []
    if not os.path.exists(_FILE):
        return rows
    with open(_FILE, encoding="utf-8") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) >= 3 and p[0]:
                rows.append((p[0], p[1], p[2]))
    return rows


def _write_rows(rows):
    os.makedirs(os.path.dirname(_FILE), exist_ok=True)
    with open(_FILE, "w", encoding="utf-8") as f:
        for word, reads, lvl in rows:
            f.write(f"{word}\t{reads}\t{lvl}\n")


def entries_by_word() -> dict:
    out = {}
    for word, _reads, field in _read_rows():
        if word not in out:
            out[word] = _level_of(field)
    return out


def learn(word: str, seqs=None, level=None):
    word = word.strip()
    seqs = [tuple(s) for s in seqs] if seqs else seqs_of(word)
    if not seqs:
        return ("noreading", None, f"「{word}」還沒選讀音，學不了")
    cur = entries_by_word().get(word, 0)
    cap = cap_for(word)
    if level:
        new = max(1, min(cap, int(level)))
    elif cur >= cap:
        return ("maxed", cur, f"已達最高強度 {cur}/{cap}")
    else:
        new = cur + 1
    _put(word, seqs, new)
    return ("ok", new, "")


def _put(word: str, seqs, n: int) -> None:
    rows = [r for r in _read_rows() if r[0] != word]
    if n >= 1:
        rows += [(word, " ".join(seq), str(n)) for seq in seqs]
    _write_rows(rows)


def set_level(word: str, n: int) -> int:
    word = word.strip()
    n = max(0, min(_MAX_LEVEL, int(n)))
    seqs = auto_seqs(word) if n >= 1 else []
    if n >= 1 and not seqs:
        return 0
    _put(word, seqs, n)
    return n


def demote(word: str) -> int:
    cur = entries_by_word().get(word, 0)
    if cur <= 0:
        return 0
    _put(word, seqs_of(word), cur - 1)
    return cur - 1


def _words_covering(text: str, diffs):
    from . import segmenter
    out, seen = [], set()
    for (i0, i1, span, _w) in segmenter.segment(text):
        if span not in seen and any(i0 <= d < i1 for d in diffs):
            seen.add(span)
            out.append(span)
    return out


def _candidates_for(gold: str, i: int):
    lo = max(0, i - 2)
    hi = min(len(gold), i + 3)
    cont, other, seen = [], [], set()
    for L in (2, 3, 4, 1):
        for start in range(lo, hi - L + 1):
            w = gold[start:start + L]
            if not w or w in seen:
                continue
            seen.add(w)
            (cont if start <= i < start + L else other).append(w)
    return cont + other


def auto_learn_from_diff(wrong: str, gold: str):
    empty = {"up": [], "down": [], "pending": []}
    if not wrong or not gold or len(wrong) != len(gold):
        return empty
    diffs = [i for i in range(len(gold)) if wrong[i] != gold[i]]
    if not diffs:
        return empty
    from . import segmenter
    learned_before = set(entries_by_word())
    up, pending, seen_pos = [], [], set()
    for (i0, i1, span, _w) in segmenter.segment(gold):
        covered = [d for d in diffs if i0 <= d < i1]
        if not covered:
            continue
        if len(span) > 1:
            _st, lv, _msg = learn(span, auto_seqs(span))
            if lv:
                cands = [span]
                for d in covered:
                    for c in _candidates_for(gold, d):
                        if c not in cands:
                            cands.append(c)
                up.append((span, lv, cands))
        else:
            for d in covered:
                if d not in seen_pos:
                    seen_pos.add(d)
                    pending.append(_candidates_for(gold, d))
    down = []
    for w in _words_covering(wrong, diffs):
        if w in learned_before:
            down.append((w, demote(w)))
    return {"up": up, "down": down, "pending": pending}


def remove(word: str) -> bool:
    rows = _read_rows()
    kept = [r for r in rows if r[0] != word]
    if len(kept) == len(rows):
        return False
    _write_rows(kept)
    return True


def clear() -> int:
    n = len(entries_by_word())
    _write_rows([])
    return n


def export_words(path: str) -> int:
    entries = entries_by_word()
    with open(path, "w", encoding="utf-8") as f:
        for word, lv in entries.items():
            f.write(f"{word}\t{'｜'.join(' '.join(s) for s in seqs_of(word))}\t{lv}\n")
    return len(entries)


def import_words(path: str):
    from . import addword
    parsed = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            word = (p[0] if p else "").strip()
            if not word:
                continue
            field = p[-1] if len(p) >= 2 else "1"
            ent = parsed.setdefault(word, [0, []])
            ent[0] = max(ent[0], _level_of(field))
            for one in (p[1].split("｜") if len(p) >= 3 else ()):
                seq = addword.parse_reading(one.strip(), word)
                if seq and seq not in ent[1]:
                    ent[1].append(seq)
    cur = entries_by_word()
    added = raised = same = missing = 0
    for word, (lv, seqs) in parsed.items():
        old = cur.get(word, 0)
        new = max(old, lv)
        if new == old:
            same += 1
            continue
        seqs = seqs or auto_seqs(word)
        if not seqs:
            missing += 1
            continue
        _put(word, seqs, new)
        raised += 1 if old else 0
        added += 0 if old else 1
    return (added, raised, same, missing)
