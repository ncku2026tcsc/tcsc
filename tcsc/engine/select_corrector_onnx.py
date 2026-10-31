# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/tcsc2026/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import math
import os
import re
from dataclasses import dataclass, field

from . import phonetics, wordphon
from .segmenter import _span_reading_words
from .onnx_engine import OnnxBert, log_softmax
from .. import symbols

_CLAUSE = re.compile("[^" + re.escape(symbols.CLAUSE) + "]+")

CONFUSABLE_GROUPS = ["在再", "那哪", "的得地", "長常", "是式事", "已以"]
_CONF_OF = {ch: g for g in CONFUSABLE_GROUPS for ch in g}
@dataclass
class Result:
    text: str
    corrected: str
    changes: list = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.corrected != self.text


class OnnxCorrector:
    def __init__(self, onnx_path, vocab_path, margin=1.0, lambda_prior=1.0,
                 min_cand_freq=50, max_word_len=4, word_cand=8, char_cand=8, max_iter=3):
        self.bert = OnnxBert(onnx_path, vocab_path)
        self.margin = margin
        self.lambda_prior = lambda_prior
        self.min_cand_freq = min_cand_freq
        self.max_word_len = max_word_len
        self.word_cand = word_cand
        self.char_cand = char_cand
        self.max_iter = max_iter

    def _freq(self, w):
        return wordphon.freq(w)

    def _homophone_ok(self, src, cand):
        return len(src) == len(cand) and all(
            phonetics.same_sound(a, b) for a, b in zip(src, cand) if a != b)

    def _candidates_by_span(self, clause):
        by = {}
        n = len(clause)
        for L in range(2, self.max_word_len + 1):
            for i in range(0, n - L + 1):
                span = clause[i:i + L]
                ws = [w for w in _span_reading_words(span)[:self.word_cand]
                      if w != span and self._homophone_ok(span, w)]
                if ws:
                    by[(i, L)] = list(dict.fromkeys(ws))
        for i, ch in enumerate(clause):
            cs = [c for c in phonetics.homophones(ch, limit=self.char_cand)
                  if self._freq(c) >= self.min_cand_freq and phonetics.same_sound(ch, c)]
            if cs:
                by[(i, 1)] = list(dict.fromkeys(cs))
        return by

    def _score(self, clause):
        ids = self.bert.encode(clause)
        results = []
        for (i, L), words in self._candidates_by_span(clause).items():
            masked = ids[:]
            for p in range(i, i + L):
                masked[p + 1] = self.bert.mask
            logits = self.bert.run([masked])[0]
            lps = [log_softmax(logits[p + 1]) for p in range(i, i + L)]
            src = clause[i:i + L]

            def span_score(word):
                s = 0.0
                for k, ch in enumerate(word):
                    tid = self.bert.token_id(ch)
                    if tid is None:
                        return None
                    s += float(lps[k][tid])
                return s

            orig = span_score(src)
            if orig is None:
                continue
            for w in words:
                sc = span_score(w)
                if sc is None:
                    continue
                pr = math.log(1 + self._freq(w)) - math.log(1 + self._freq(src))
                results.append(((sc - orig) + self.lambda_prior * pr,
                                clause[:i] + w + clause[i + L:], (i, src, w)))
        return results

    def _correct_clause(self, clause):
        cur = clause
        for _ in range(self.max_iter):
            scored = [s for s in self._score(cur) if s[1] != cur]
            if not scored:
                break
            gain, best, _ = max(scored, key=lambda x: x[0])
            if gain <= self.margin:
                break
            cur = best
        return cur

    def correct(self, text):
        text = text.strip()
        if not text:
            return Result(text, text)
        out, idx = [], 0
        for m in _CLAUSE.finditer(text):
            out.append(text[idx:m.start()])
            out.append(self._correct_clause(m.group()))
            idx = m.end()
        out.append(text[idx:])
        corrected = "".join(out)
        changes = [(k, a, b) for k, (a, b) in enumerate(zip(text, corrected)) if a != b]
        return Result(text, corrected, changes)

    def ranked_corrections(self, clause, top_n=10):
        clause = clause.strip()
        if not clause:
            return [clause]
        best = self._correct_clause(clause)
        scored = sorted((s for s in self._score(clause) if s[1] != clause),
                        key=lambda x: x[0], reverse=True)
        out = [best] if best != clause else [clause]
        from .. import settings as _st
        lcs = getattr(self, "last_court_sc", None)
        if _st.get("list_court_order", True) and lcs and lcs[0] == clause:
            sc = lcs[1]
            for p in sorted((p for p in sc if p != clause), key=lambda p: -sc[p]):
                if p not in out:
                    out.append(p)
                if len(out) >= top_n:
                    break
        for _, cand, _e in scored:
            if cand not in out:
                out.append(cand)
            if len(out) >= top_n:
                break
        if clause not in out:
            out.append(clause)
        vipfn = getattr(self, "_celebrity_props", None)
        if vipfn is not None:
            try:
                for p in reversed(vipfn(clause)):
                    if p == out[0]:
                        continue
                    if p in out:
                        out.remove(p)
                    out.insert(1, p)
            except Exception:
                pass
        out, locked_hit = self._f7_locked_last(clause, out)
        if out and out[0] == clause and len(out) > 1 and out[1] not in locked_hit:
            from . import pronoun
            from .. import settings
            ni, ta = settings.get("pron_ni", ""), settings.get("pron_ta", "")
            done = getattr(self, "_pre_normalized", False)
            if (settings.get("force_change") and not done
                    and pronoun.apply_pref(clause, ni, ta) == clause):
                out = out[1:] + [clause]
        return out

    @staticmethod
    def _f7_locked_last(clause, out):
        from .. import settings
        from . import userdict, wordphon
        if not settings.get("f7_lock", True):
            return out, set()
        locked = set()
        for w, lv in wordphon.defense_levels().items():
            if len(w) < 2 or lv < userdict.cap_for(w):
                continue
            st = clause.find(w)
            while st != -1:
                locked.update(range(st, st + len(w)))
                st = clause.find(w, st + 1)
        if not locked:
            return out, set()
        hit = {c for c in out if len(c) == len(clause) and any(c[k] != clause[k] for k in locked)}
        return [c for c in out if c not in hit] + [c for c in out if c in hit], hit

    def has_confusable(self, text) -> bool:
        return any(ch in _CONF_OF for ch in (text or ""))

    def confusable_variants(self, text, top_n=12):
        positions = [i for i, ch in enumerate(text or "") if ch in _CONF_OF]
        if not positions:
            return []
        ids = self.bert.encode(text)
        masked = ids[:]
        for i in positions:
            if i + 1 < len(masked):
                masked[i + 1] = self.bert.mask
        logits = self.bert.run([masked])[0]
        lp_at = {}
        for i in positions:
            if i + 1 >= len(logits):
                return []
            row = log_softmax(logits[i + 1])
            d = {c: float(row[tid]) for c in _CONF_OF[text[i]]
                 if (tid := self.bert.token_id(c)) is not None}
            if not d:
                return []
            lp_at[i] = d
        _MAXP = 8
        if len(positions) > _MAXP:
            positions = sorted(positions, key=lambda i: lp_at[i].get(text[i], 0.0))[:_MAXP]
            positions.sort()
        from itertools import product
        choices = [[(i, c, s) for c, s in lp_at[i].items()] for i in positions]
        scored = []
        for combo in product(*choices):
            chars = list(text)
            score = 0.0
            for (i, c, s) in combo:
                chars[i] = c
                score += s
            v = "".join(chars)
            if v != text:
                scored.append((score, v))
        scored.sort(key=lambda x: x[0], reverse=True)
        seen, out = set(), []
        for _s, v in scored:
            if v not in seen:
                seen.add(v)
                out.append(v)
            if len(out) >= top_n:
                break
        return out
