# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import itertools
import math

from . import phonetics, wordphon

KEYMAP = {
    "1": "ㄅ", "q": "ㄆ", "a": "ㄇ", "z": "ㄈ", "2": "ㄉ", "w": "ㄊ", "s": "ㄋ", "x": "ㄌ",
    "e": "ㄍ", "d": "ㄎ", "c": "ㄏ", "r": "ㄐ", "f": "ㄑ", "v": "ㄒ", "5": "ㄓ", "t": "ㄔ",
    "g": "ㄕ", "b": "ㄖ", "y": "ㄗ", "h": "ㄘ", "n": "ㄙ",
    "u": "ㄧ", "j": "ㄨ", "m": "ㄩ",
    "8": "ㄚ", "i": "ㄛ", "k": "ㄜ", ",": "ㄝ", "9": "ㄞ", "o": "ㄟ", "l": "ㄠ", ".": "ㄡ",
    "0": "ㄢ", "p": "ㄣ", ";": "ㄤ", "/": "ㄥ", "-": "ㄦ",
}
TONES = {" ": "", "6": "ˊ", "3": "ˇ", "4": "ˋ", "7": "˙"}
_INIT = set("ㄅㄆㄇㄈㄉㄊㄋㄌㄍㄎㄏㄐㄑㄒㄓㄔㄕㄖㄗㄘㄙ")
_MED = set("ㄧㄨㄩ")
_SLOT = lambda z: 0 if z in _INIT else (1 if z in _MED else 2)
_KEYS = set(KEYMAP) | set(TONES)
KEYS = frozenset(_KEYS)
SEG_COST = 16.0


def _valid(r):
    phonetics._load()
    return bool(phonetics._reading2chars.get(r))


def parse(s):
    syl, cur, slot = [], "", -1
    for ch in s:
        if ch == " " and not cur:
            continue
        if ch in TONES:
            if not cur:
                return None
            r = cur + TONES[ch]
            if not _valid(r):
                return None
            syl.append(r)
            cur, slot = "", -1
            continue
        z = KEYMAP.get(ch)
        if z is None:
            return None
        k = _SLOT(z)
        if k <= slot:
            return None
        cur, slot = cur + z, k
    return syl if syl and not cur else None


def _partial(s):
    if not 1 <= len(s) <= 3:
        return False
    slot = -1
    for ch in s:
        z = KEYMAP.get(ch)
        if z is None or _SLOT(z) <= slot:
            return False
        slot = _SLOT(z)
    return True


def _syl(raw):
    if not raw or raw[-1] not in TONES:
        return None
    cur, slot = "", -1
    for ch in raw[:-1]:
        z = KEYMAP.get(ch)
        if z is None or _SLOT(z) <= slot:
            return None
        cur, slot = cur + z, _SLOT(z)
    if not cur:
        return None
    r = cur + TONES[raw[-1]]
    return r if _valid(r) else None


def _split_glued(raw):
    for k in range(1, len(raw) - 1):
        r = _syl(raw[k:])
        if r:
            return None if _partial(raw[:k].strip()) else (k, r)
    return None


class Garble:

    def __init__(self, start, end, tail, segs):
        self.start, self.end, self.tail, self.segs = start, end, tail, segs
        self.before = ""

    @property
    def syllables(self):
        return [r for _raw, r in self.segs if r]

    def runs(self):
        out, pos, cur, cur_at = [], 0, [], 0
        for raw, r in self.segs:
            if r:
                if not cur:
                    cur_at = pos
                cur.append(r)
                pos += 1
            else:
                if cur:
                    out.append((cur_at, cur))
                    cur = []
                pos += len(raw)
        if cur:
            out.append((cur_at, cur))
        return out

    def template(self):
        t = []
        for raw, r in self.segs:
            t.extend([r] if r else [("lit", c) for c in raw])
        return t


def _syl_ime(raw):
    if not raw or raw[-1] not in TONES:
        return None, 0
    slots, swaps = [None, None, None], [0, 0, 0]
    for ch in raw[:-1]:
        z = KEYMAP.get(ch)
        if z is None:
            return None, 0
        k = _SLOT(z)
        if slots[k] is not None:
            swaps[k] += 1
        slots[k] = z
    cur = "".join(z for z in slots if z)
    if not cur:
        return None, 0
    r = cur + TONES[raw[-1]]
    return (r if _valid(r) else None), max(swaps)


def _read(raw, ime):
    r = _syl(raw)
    if r or not ime or raw[-1] not in "3467":
        return r
    r, swaps = _syl_ime(raw)
    return r if swaps <= 2 else None


def _sandwiched(raw):
    r, swaps = _syl_ime(raw)
    return r if swaps <= 2 else None


def _tail_ok(tail, ime):
    if _partial(tail):
        return True
    return ime and 1 <= len(tail) <= 3 and all(ch in KEYMAP for ch in tail)


def _english_tail(tail):
    return len(tail) >= 4 and tail.isascii() and tail.isalpha()


def _chunks(body):
    chunks, at, q = [], None, 0
    while q < len(body):
        c = body[q]
        if at is None:
            if c == " ":
                q += 1
                continue
            at = q
            if c in TONES:
                chunks.append((at, body[at:q + 1]))
                at = None
        elif c in TONES:
            chunks.append((at, body[at:q + 1]))
            at = None
        q += 1
    return chunks


def _collect(chunks, reads, base, ime=True):
    segs, idx = [], len(chunks) - 1
    while idx >= 0:
        a, raw = chunks[idx]
        if reads[idx]:
            segs.append((base + a, raw, reads[idx]))
        elif idx > 0 and reads[idx - 1] and (segs or raw[-1] in "3467"):
            mid = _sandwiched(raw) if segs and ime else None
            sp = None if mid else (_split_glued(raw) if raw[-1] in "3467" else None)
            if mid:
                segs.append((base + a, raw, mid))
            elif sp:
                segs.append((base + a + sp[0], raw[sp[0]:], sp[1]))
                segs.append((base + a, raw[:sp[0]], None))
            else:
                segs.append((base + a, raw, None))
        else:
            sp = _split_glued(raw)
            if sp:
                segs.append((base + a + sp[0], raw[sp[0]:], sp[1]))
            break
        idx -= 1
    if not segs:
        return None
    segs.reverse()
    return segs if segs[0][2] else None


def _region(run, base, ime=True, need=2):
    k = len(run)
    while k > 0 and run[k - 1] not in TONES:
        k -= 1
    tail = run[k:]
    if tail and not _tail_ok(tail, ime) and not _english_tail(tail):
        return None
    chunks = _chunks(run[:k])
    if not chunks:
        return None
    best = _collect(chunks, [_read(raw, ime) for _a, raw in chunks], base, ime)
    if not best or sum(1 for x in best if x[2]) < need:
        return None
    if not any(r and _syl(raw) == r and any(c.isalpha() for c in raw) for _p, raw, r in best):
        return None
    return best


def _runs(line):
    key = lambda c: c in _KEYS or "A" <= c <= "Z"
    e = len(line)
    while e > 0:
        while e > 0 and not key(line[e - 1]):
            e -= 1
        s = e
        while s > 0 and key(line[s - 1]):
            s -= 1
        if s == e:
            return
        run = line[s:e]
        if any("A" <= c <= "Z" for c in run) and any("a" <= c <= "z" for c in run):
            q = e
            while q > s:
                p = q
                while p > s and line[p - 1] in _KEYS:
                    p -= 1
                if p < q:
                    yield p, q
                q = p
                while q > s and line[q - 1] not in _KEYS:
                    q -= 1
        else:
            yield s, e
        e = s


def analyze(line, ime=True):
    tries = 0
    for s, e in _runs(line):
        run = line[s:e]
        if not run.strip():
            continue
        segs = _region(run.lower(), s, ime, 3 if run != run.lower() else 2)
        if segs:
            start, end = segs[0][0], segs[-1][0] + len(segs[-1][1])
            return Garble(start, end, line[end:], [(line[p:p + len(raw)], r) for p, raw, r in segs])
        tries += 1
        if tries >= 4:
            break
    return None


def analyze_single(line, ime=True):
    first = next(iter(_runs(line)), None)
    if not first:
        return None
    s, e = first
    left = line[s - 1] if s > 0 else ""
    if not left or left.isascii() or left.isspace():
        return None
    run = line[s:e]
    if run.isascii() and run.isalpha() and run.isupper():
        return None
    raw = run.lower()
    if not any("a" <= c <= "z" for c in raw):
        return None
    if line[e:].strip() and not any(c in "3467" for c in raw):
        return None
    k = len(raw)
    while k > 0 and raw[k - 1] not in TONES:
        k -= 1
    chunks, tail = _chunks(raw[:k]), raw[k:]
    segs = None
    if tail.strip() and not chunks:
        r = _read(tail.rstrip() + " ", ime) if " " not in tail.rstrip() else None
        if r:
            segs = [(0, tail.rstrip(), r)]
    elif len(chunks) == 1 and not tail.strip():
        a, chunk = chunks[0]
        r = _read(chunk, ime)
        if r:
            segs = [(a, chunk, r)]
        elif chunk[-1] in "3467":
            sp = _split_glued(chunk)
            if sp:
                segs = [(a, chunk[:sp[0]], None), (a + sp[0], chunk[sp[0]:], sp[1])]
    if not segs:
        return None
    start, end = s + segs[0][0], s + segs[-1][0] + len(segs[-1][1])
    g = Garble(start, end, line[end:], [(line[s + p:s + p + len(seg)], r) for p, seg, r in segs])
    g.single = True
    return g


def analyze_selection(text, ime=True):
    from .. import symbols
    low = text.lower()
    marks = set(symbols.breaks())
    if not low.strip() or any(c not in _KEYS and c not in marks for c in low):
        return None
    segs, q = [], 0
    while q < len(low):
        p = q
        if low[q] not in _KEYS:
            while p < len(low) and low[p] not in _KEYS:
                p += 1
            segs.append((q, low[q:p], None))
            q = p
            continue
        while p < len(low) and low[p] in _KEYS:
            p += 1
        run, k = low[q:p], p - q
        while k > 0 and run[k - 1] not in TONES:
            k -= 1
        for a, raw in _chunks(run[:k]):
            r = _read(raw, ime)
            sp = None if r or raw[-1] not in "3467" else _split_glued(raw)
            if sp:
                segs += [(q + a, raw[:sp[0]], None), (q + a + sp[0], raw[sp[0]:], sp[1])]
                continue
            if not r and ime:
                r = _syl_ime(raw)[0]
            segs.append((q + a, raw, r))
        if run[k:]:
            segs.append((q + k, run[k:], None))
        q = p
    while segs and segs[-1][2] is None:
        segs.pop()
    while segs and segs[0][2] is None and not segs[0][1].strip():
        segs.pop(0)
    if not any(r for _a, _raw, r in segs):
        return None
    start, end = segs[0][0], segs[-1][0] + len(segs[-1][1])
    return Garble(start, end, text[end:], [(text[p:p + len(raw)], r) for p, raw, r in segs])


def find_suffix(line):
    g = analyze(line)
    if not g or g.tail or any(r is None for _raw, r in g.segs):
        return None
    return g.start, g.syllables


def _opts(syl, i, L):
    seq = tuple(syl[i:i + L])
    if L == 1:
        chars = phonetics._reading2chars.get(seq[0], [])
        top = sorted(chars, key=lambda c: -wordphon.freq(c))[:10]
        return [(c, math.log1p(wordphon.freq(c)) - SEG_COST) for c in top]
    return [(w, math.log1p(wordphon.freq(w)) - SEG_COST) for w in wordphon.words_by_reading(seq)[:6]]


def decode(syl, k=20, beam=40):
    phonetics._load()
    wordphon._load()
    n = len(syl)
    at = {0: [(0.0, "")]}
    for i in range(n):
        cur = at.get(i)
        if not cur:
            continue
        seen, keep = set(), []
        for sc, s in sorted(cur, key=lambda x: -x[0]):
            if s not in seen:
                seen.add(s)
                keep.append((sc, s))
            if len(keep) >= beam:
                break
        for sc, s in keep:
            for L in range(1, min(4, n - i) + 1):
                for w, ws in _opts(syl, i, L):
                    at.setdefault(i + L, []).append((sc + ws, s + w))
    out, seen = [], set()
    for _sc, s in sorted(at.get(n, []), key=lambda x: -x[0]):
        if s not in seen:
            seen.add(s)
            out.append(s)
        if len(out) >= k:
            break
    return out


def respell(text, keep=4.0, k=20, beam=40, per_span=8):
    phonetics._load()
    wordphon._load()
    rs = [sorted(phonetics.readings(ch)) for ch in text]
    n = len(text)
    opts = {}
    for i in range(n):
        for L in range(1, min(4, n - i) + 1):
            if not all(rs[i:i + L]):
                continue
            cands = {}
            for seq in itertools.islice(itertools.product(*rs[i:i + L]), per_span):
                ws = ([(c, wordphon.freq(c)) for c in sorted(phonetics._reading2chars.get(seq[0], []),
                                                              key=lambda x: -wordphon.freq(x))[:10]]
                      if L == 1 else [(w, wordphon.freq(w)) for w in wordphon.words_by_reading(seq)[:6]])
                for w, f in ws:
                    sc = math.log1p(f) - SEG_COST + keep * sum(a == b for a, b in zip(w, text[i:i + L]))
                    cands[w] = max(cands.get(w, -1e9), sc)
            if L == 1:
                cands[text[i]] = max(cands.get(text[i], -1e9), math.log1p(wordphon.freq(text[i])) - SEG_COST + keep)
            opts[(i, L)] = list(cands.items())
        if (i, 1) not in opts:
            opts[(i, 1)] = [(text[i], keep - SEG_COST)]
    at = {0: [(0.0, "")]}
    for i in range(n):
        seen, kept = set(), []
        for sc, s in sorted(at.get(i, []), key=lambda x: -x[0]):
            if s not in seen:
                seen.add(s)
                kept.append((sc, s))
            if len(kept) >= beam:
                break
        for sc, s in kept:
            for L in range(1, min(4, n - i) + 1):
                for w, ws in opts.get((i, L), []):
                    at.setdefault(i + L, []).append((sc + ws, s + w))
    out, seen = [], {text}
    for _sc, s in sorted(at.get(n, []), key=lambda x: -x[0]):
        if s not in seen:
            seen.add(s)
            out.append(s)
        if len(out) >= k:
            break
    return out


def consistent(cand, tmpl):
    if len(cand) != len(tmpl):
        return False
    for c, t in zip(cand, tmpl):
        if isinstance(t, tuple):
            if c != t[1]:
                return False
        elif t not in phonetics.raw_readings(c):
            return False
    return True


def compose(g, k=20):
    per = [decode(syls, k=k) for _at, syls in g.runs()]
    if not per or any(not p for p in per):
        return []

    def fill(picks):
        it = iter("".join(picks))
        return "".join(next(it) if r else raw for raw, r in g.segs)
    base = [p[0] for p in per]
    out = [fill(base)]
    for ri, alts in enumerate(per):
        for alt in alts[1:]:
            picks = list(base)
            picks[ri] = alt
            c = fill(picks)
            if c not in out:
                out.append(c)
    return out


def demo(s):
    g = analyze(s)
    if not g:
        return None
    return [s[:g.start] + c + g.tail for c in compose(g)[:5]]
