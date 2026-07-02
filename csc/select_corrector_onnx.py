# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""ONNX 校正引擎：OnnxCorrector（基礎）+ OnnxCorrectorV2（多音字收斂＋句尾守門）。"""


# ===== csc/select_corrector_onnx =====
# -*- coding: utf-8 -*-
"""ONNX 版校正引擎（無 torch / transformers）—— 供 exe 打包用。

- 推論：onnxruntime（csc.onnx_engine.OnnxBert）。
- 候選/字典/詞頻/同音守門：重用既有純 Python（phonetics, wordphon, segmenter）。
- 評分：遮「候選詞所佔位置」一次前向，比 token log-prob + 詞頻先驗（CPU 也夠快）。
- 介面對齊 v6：correct(text) / ranked_corrections(clause)（供 F1 循環）。
功能等同 select_corrector_v6（窮舉可連詞候選 + 詞頻先驗 + 硬 ban 罕用字 + 同音守門）。
"""
import math
import os
import re
from dataclasses import dataclass, field

from csc import phonetics, wordphon
from csc.segmenter import _span_reading_words
from csc.onnx_engine import OnnxBert, log_softmax

_DELIM = "，。！？；：、,.!?;:　 \t\n"
_CLAUSE = re.compile("[^" + re.escape(_DELIM) + "]+")

# 常錯字組（F8 強制細修用）：讀音不完全相同（的得地讀音不同、那哪差聲調）→ F1 的『同音守門』碰不到，
# 打錯了也不會被改。F8 對這三組繞過守門、純 BERT 打分強制換。
CONFUSABLE_GROUPS = ["在再", "那哪", "的得地"]
_CONF_OF = {ch: g for g in CONFUSABLE_GROUPS for ch in g}
_BOOST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "data", "custom_boost.txt")


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
        self._boost = self._load_boost()

    @staticmethod
    def _load_boost():
        d = {}
        if os.path.exists(_BOOST):
            with open(_BOOST, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    p = line.split()
                    if len(p) >= 2 and p[-1].lstrip("-").isdigit():
                        d[p[0]] = d.get(p[0], 0) + int(p[-1])
        return d

    def _freq(self, w):
        return wordphon.freq(w) + self._boost.get(w, 0)

    def _homophone_ok(self, src, cand):
        return len(src) == len(cand) and all(
            phonetics.same_sound(a, b) for a, b in zip(src, cand) if a != b)

    def _candidates_by_span(self, clause):
        """{(i, L): [候選詞]}；同音、過濾罕用單字。"""
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
        """[(gain, cand_clause, (i, src, dst))]；每個 span 遮罩一次前向。"""
        ids = self.bert.encode(clause)
        results = []
        for (i, L), words in self._candidates_by_span(clause).items():
            masked = ids[:]
            for p in range(i, i + L):
                masked[p + 1] = self.bert.mask
            logits = self.bert.run([masked])[0]                 # (S, V)
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
        out = [best] if best != clause else [clause]   # 不用改時也提供候選，原句當預設
        for _, cand, _e in scored:
            if cand not in out:
                out.append(cand)
            if len(out) >= top_n:
                break
        if clause not in out:
            out.append(clause)
        return out

    # ===== F8：常錯字強制細修（freeze 後處理，只動 在再/那哪/的得地）=====
    def has_confusable(self, text) -> bool:
        return any(ch in _CONF_OF for ch in (text or ""))

    def confusable_variants(self, text, top_n=12):
        """窮舉 text 中所有常錯字(在再/那哪/的得地)組合的整句變體，**一次遮罩全部常錯字位置**打分，
        回傳『排除原句後、依模型分數由高到低』的變體清單（供 F8 循環）。
        打分＝各常錯字位置遮罩後、該位置候選字 log-prob 之和——把『你打的原字』遮掉，模型對剩下判得才準
        （關鍵：不遮的話模型會一直覺得原本那個錯字最順）。"""
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
            if v != text:                       # 去掉原輸入那句
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


# ===== csc/select_corrector_onnx_v2 =====
# -*- coding: utf-8 -*-
"""ONNX 校正引擎 v2：在 v1(OnnxCorrector) 之上加兩道候選端手術刀（可開關）。

  reading_ratio=None      → 不做多音字收斂（行為同 v1）
  reading_ratio=0.02      → 砍奇怪讀音（見 reading_filter.active_readings）
  guard_particles=False   → 不守門
  guard_particles=True    → 句尾語助詞不准被同音替換

只覆寫『候選產生』（_candidates_by_span / _homophone_ok），打分、流程完全沿用 v1，
所以兩個旗標都關 = 與 v1 逐字相同，方便用計分卡 A/B。
"""
from csc import phonetics, reading_filter
from csc.segmenter import _span_reading_words


class OnnxCorrectorV2(OnnxCorrector):
    def __init__(self, *args, reading_ratio=None, guard_particles=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.reading_ratio = reading_ratio
        self.guard_particles = guard_particles

    def _same_sound(self, a, b):
        if self.reading_ratio is None:
            return phonetics.same_sound(a, b)
        return reading_filter.same_sound(a, b, self.reading_ratio)

    def _homophone_ok(self, src, cand):
        return len(src) == len(cand) and all(
            self._same_sound(a, b) for a, b in zip(src, cand) if a != b)

    def _candidates_by_span(self, clause):
        """同 v1，但：①同音用收斂版 ②句尾語助詞位置略過單字候選。"""
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
            if self.guard_particles and reading_filter.is_guarded_particle(clause, i):
                continue
            cs = [c for c in phonetics.homophones(ch, limit=self.char_cand)
                  if self._freq(c) >= self.min_cand_freq and self._same_sound(ch, c)]
            if cs:
                by[(i, 1)] = list(dict.fromkeys(cs))
        return by
