# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/tcsc2026/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import unicodedata

SYM_SPEC = (
    ("[", "「"), ("]", "」"),
    ("K", "！"), ("1", "！"),
    ("/", "？"),
    ("'", "、"),
    (";", "；"), ("L", "："),
    ("B", "←"), ("N", "→"), ("H", "↑"), ("J", "↓"),
    ("9", "（"), ("0", "）"),
    ("`", "～"),
)

NEWLINES = "\r\n\v\f\x85\u2028\u2029"
SPACES = "　 \t"
PUNCT = "，。！？；：、,.!?;:"
TAGS = "[]［］【】〔〕"
CODE = "\\/()[]{}"
PROMPTS = "❯❮›»❱⟩"

CLAUSE = PUNCT + SPACES + "\n"


def _uniq(*parts):
    seen = []
    for p in parts:
        for c in p:
            if c not in seen:
                seen.append(c)
    return "".join(seen)


def _wide_symbols(texts):
    return "".join(c for t in texts for c in t if ord(c) > 0x7F and unicodedata.category(c)[0] in "PS")


def sym_outputs():
    from . import settings
    user = settings.get("sym_user") or {}
    return [o for _n, o in SYM_SPEC] + [v for v in user.values() if isinstance(v, str)]


def breaks():
    return _uniq(PUNCT, SPACES, NEWLINES, TAGS, _wide_symbols(sym_outputs()))


def move_stops():
    return _uniq(breaks(), CODE, PROMPTS)
