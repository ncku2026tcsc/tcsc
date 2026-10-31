# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/tcsc2026/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
NI = ["你", "妳"]
TA = ["他", "她", "它", "牠", "祂"]

_NI_MAP = {"你": {"妳": "你"}, "妳": {"你": "妳"}}
_TA_MAP = {t: {x: t for x in TA if x != t} for t in TA}

_BLOCK = [
    "其他", "其它", "吉他", "維他命", "他人", "他鄉", "他日", "利他", "排他",
    "他者", "他律", "他山之石", "他國", "他方", "他處", "他殺", "他遷", "他用",
    "迷你",
]


def _protected(text: str) -> list:
    protected = [False] * len(text)
    for w in _BLOCK:
        start = 0
        while True:
            idx = text.find(w, start)
            if idx < 0:
                break
            for k in range(idx, idx + len(w)):
                protected[k] = True
            start = idx + 1
    return protected


def variants(text: str, cap: int = 64, rare: bool = False) -> list:
    import itertools
    fam = TA if rare else TA[:3]
    prot = _protected(text)
    slots = []
    for i, ch in enumerate(text):
        pool = NI if ch in NI else fam if ch in TA else None
        if pool and not prot[i]:
            slots.append((i, [c for c in pool if c != ch]))
    out, seen = [], {text}
    for t in range(max((len(a) for _i, a in slots), default=0)):
        for d in range(1, len(slots) + 1):
            for pick in itertools.combinations(slots, d):
                for chosen in itertools.product(*[alts[:t + 1] for _i, alts in pick]):
                    s = list(text)
                    for (i, _a), c in zip(pick, chosen):
                        s[i] = c
                    s = "".join(s)
                    if s in seen:
                        continue
                    seen.add(s)
                    out.append(s)
                    if len(out) >= cap:
                        return out
    return out


def apply_pref(text: str, ni: str = "", ta: str = "") -> str:
    mapping = {}
    if ni in _NI_MAP:
        mapping.update(_NI_MAP[ni])
    if ta in _TA_MAP:
        mapping.update(_TA_MAP[ta])
    if not text or not mapping:
        return text
    protected = _protected(text)
    out = list(text)
    for i, ch in enumerate(text):
        if not protected[i] and ch in mapping:
            out[i] = mapping[ch]
    return "".join(out)
