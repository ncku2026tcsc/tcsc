# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import os

from .userpaths import userforce_path

_USERFORCE = userforce_path()
_UF_BASE = 3000
_UF_MULT = 8
_UF_MAX_LEVEL = 20


def _uf_level(field: str) -> int:
    if field == "soft":
        return 1
    if field == "hard":
        return _UF_MAX_LEVEL
    try:
        return max(1, min(_UF_MAX_LEVEL, int(field)))
    except (ValueError, TypeError):
        return 1


_word2seqs: dict = {}
_seq2words: dict = {}
_freq: dict = {}
_userforce_freq: dict = {}
_userforce_level: dict = {}
_uf_pool: list = []
_patch_enrolled: set = set()
_origin: dict = {}
_loaded = False


def _load() -> None:
    global _loaded
    if _loaded:
        return
    from . import lexicon
    lexicon.load()
    _loaded = True


def origins(word: str) -> set:
    _load()
    return _origin.get(word, set())


def patch_status(word: str) -> str:
    _load()
    if word in _patch_enrolled:
        return "外加"
    if word in _word2seqs:
        return "內建"
    return "無籍"


def commonwords() -> dict:
    from .userpaths import commonwords_path
    out = {}
    p = commonwords_path()
    if not os.path.exists(p):
        return out
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                if line.startswith("#") or "\t" not in line:
                    continue
                w, reads = line.rstrip("\n").split("\t", 1)
                for one in reads.split("｜"):
                    seq = tuple(one.split())
                    if w and len(w) == len(seq):
                        out.setdefault(w, []).append(seq)
    except Exception:
        pass
    return out


def add_commonword(word: str, seqs) -> bool:
    from .userpaths import commonwords_path
    from . import lexicon
    p = commonwords_path()
    line = word + "\t" + "｜".join(" ".join(s) for s in seqs)
    try:
        old = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    except Exception:
        old = ""
    if line in old.split("\n"):
        return False
    with open(p, "a", encoding="utf-8") as f:
        if not old:
            f.write("# 常識詞庫（F5 學詞寫入）——詞<TAB>注音（多組用 ｜）\n")
        f.write(line + "\n")
    _load()
    lexicon.reload_user()
    return True


def remove_commonword(word: str) -> bool:
    from .userpaths import commonwords_path
    from . import lexicon
    p = commonwords_path()
    if not os.path.exists(p):
        return False
    try:
        rows = open(p, encoding="utf-8").read().split("\n")
    except Exception:
        return False
    keep = [r for r in rows
            if r.startswith("#") or not r.strip() or r.split("\t")[0] != word]
    if len(keep) == len(rows):
        return False
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(keep).rstrip("\n") + "\n")
    _load()
    lexicon.reload_user()
    return True


def reload_userforce() -> None:
    _load()
    from . import lexicon
    lexicon.reload_user()


def defense_levels() -> dict:
    _load()
    return _userforce_level


def attack_levels() -> dict:
    _load()
    return _userforce_level


def reading_seqs(word: str) -> set:
    _load()
    return _word2seqs.get(word, set())


def homophone_words(word: str, limit: int = 15) -> list:
    _load()
    out, seen = [], {word}
    for seq in reading_seqs(word):
        for w in _seq2words.get(seq, []):
            if w not in seen:
                seen.add(w)
                out.append(w)
    return out[:limit]


def words_by_reading(seq) -> list:
    _load()
    return _seq2words.get(tuple(seq), [])


def seqs_of(word: str) -> list:
    _load()
    return [tuple(s) for s in _word2seqs.get(word, [])]


def freq(word: str) -> int:
    _load()
    return _freq.get(word, 0) + _userforce_freq.get(word, 0)


def corpus_freq(word: str) -> int:
    _load()
    return _freq.get(word, 0)


def learned_bonus(word: str) -> int:
    _load()
    return _userforce_freq.get(word, 0)


def learned_level(word: str) -> int:
    _load()
    return _userforce_level.get(word, 0)
