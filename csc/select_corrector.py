# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""torch 校正引擎：SelectCorrector→…→V8（句子級選字 + 詞頻先驗 + 同音守門 + 多音字收斂）。"""


# ===== csc/select_corrector =====
# -*- coding: utf-8 -*-
"""句子級『選擇題』校正（關注點分離的最終整合）。

流程：
  1. 自家讀音斷詞 segmenter.segment() 切單位、給每單位同音候選（字典，有界）
  2. 每次把「一個單位」換成它的某個同音候選 → 組成候選句
  3. BERT pseudo-log-likelihood 算各候選句流暢度，選最順者（模型只負責選）
  4. 反覆數輪以處理多個錯字
"""
from dataclasses import dataclass, field

import torch
from transformers import AutoTokenizer, AutoModelForMaskedLM

from . import phonetics, segmenter

DEFAULT_MODEL = "ckiplab/bert-base-chinese"


@dataclass
class Result:
    text: str
    corrected: str
    changes: list = field(default_factory=list)   # [(pos, src, dst)]

    @property
    def changed(self) -> bool:
        return self.corrected != self.text


class SelectCorrector:
    def __init__(self, model_name: str = DEFAULT_MODEL, device=None,
                 cand_per_unit: int = 8, margin: float = 1.0, max_iter: int = 3):
        self.tok = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForMaskedLM.from_pretrained(model_name).eval()
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)
        self.cand_per_unit = cand_per_unit
        self.margin = margin
        self.max_iter = max_iter

    @torch.no_grad()
    def _pll(self, text: str) -> float:
        """pseudo-log-likelihood：句子流暢度（越大越順）。"""
        ids = self.tok(text, return_tensors="pt").to(self.device)["input_ids"][0]
        L = ids.size(0)
        if L <= 2:
            return 0.0
        batch = ids.unsqueeze(0).repeat(L - 2, 1).clone()
        rows = torch.arange(L - 2)
        cols = torch.arange(1, L - 1)
        batch[rows, cols] = self.tok.mask_token_id
        lp = torch.log_softmax(self.model(batch.to(self.device)).logits, dim=-1)
        return sum(lp[k - 1, k, ids[k]].item() for k in range(1, L - 1))

    def _unit_candidates(self, span: str, words):
        """單位的候選字串（含原 span、去重、等長）。多字用詞庫同音詞；單字用同音字。"""
        raw = ([span] + [w for w in (words or []) if w != span]) if words \
            else [span] + phonetics.homophones(span, limit=self.cand_per_unit)
        seen, out = set(), []
        for c in raw:
            if c not in seen and len(c) == len(span):
                seen.add(c)
                out.append(c)
        return out[: self.cand_per_unit + 1]

    def correct(self, text: str) -> Result:
        text = text.strip()
        if not text:
            return Result(text, text)
        cur = text
        for _ in range(self.max_iter):
            base = self._pll(cur)
            best_text, best_score = cur, base
            for (i, j, span, words) in segmenter.segment(cur):
                for w in self._unit_candidates(span, words):
                    if w == span:
                        continue
                    cand = cur[:i] + w + cur[j:]
                    s = self._pll(cand)
                    if s > best_score + self.margin:
                        best_score, best_text = s, cand
            if best_text == cur:
                break
            cur = best_text
        changes = [(k, a, b) for k, (a, b) in enumerate(zip(text, cur)) if a != b]
        return Result(text, cur, changes)


# ===== csc/select_corrector_v2 =====
# -*- coding: utf-8 -*-
"""SelectCorrector v2 —— 不先斷詞，改用「窮舉可連詞」當選擇題。

設計（依使用者定案）：
  - 小麥詞庫已定義「哪些相鄰字是詞」，不需自己斷詞。
  - 只要相鄰 2~4 字（依讀音）能連成真詞，就「必須」把該詞的同音詞加入選項，
    不先 commit 一種切法（避免斷錯傳播）。
  - 模型只負責「選擇題」：在所有候選句中選最順（BERT pseudo-log-likelihood）。
  - 學習訊號：若正解在選項中、模型卻沒選中 → 才是更新模型的時機；
    若正解不在選項 → 是詞庫覆蓋問題，非模型問題。reachable() 用來區分這兩者。

不修改 v1（select_corrector.py）。
"""
import re
from dataclasses import dataclass, field

import torch
from transformers import AutoTokenizer, AutoModelForMaskedLM

from . import phonetics
from .segmenter import _span_reading_words   # 讀音 → 同音真詞（重用，不改原檔）

DEFAULT_MODEL = "ckiplab/bert-base-chinese"
_DELIM = "，。！？；：、,.!?;:　 \t\n"
_CLAUSE = re.compile("[^" + re.escape(_DELIM) + "]+")


@dataclass
class Result:
    text: str
    corrected: str
    changes: list = field(default_factory=list)   # [(pos, src, dst)]

    @property
    def changed(self) -> bool:
        return self.corrected != self.text


class SelectCorrectorV2:
    def __init__(self, model_name: str = DEFAULT_MODEL, device=None,
                 max_word_len: int = 4, word_cand: int = 8, char_cand: int = 8,
                 margin: float = 1.0, max_iter: int = 3):
        self.tok = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForMaskedLM.from_pretrained(model_name).eval()
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)
        self.max_word_len = max_word_len
        self.word_cand = word_cand
        self.char_cand = char_cand
        self.margin = margin
        self.max_iter = max_iter

    @torch.no_grad()
    def _pll(self, text: str) -> float:
        ids = self.tok(text, return_tensors="pt").to(self.device)["input_ids"][0]
        L = ids.size(0)
        if L <= 2:
            return 0.0
        batch = ids.unsqueeze(0).repeat(L - 2, 1).clone()
        rows = torch.arange(L - 2)
        cols = torch.arange(1, L - 1)
        batch[rows, cols] = self.tok.mask_token_id
        lp = torch.log_softmax(self.model(batch.to(self.device)).logits, dim=-1)
        return sum(lp[k - 1, k, ids[k]].item() for k in range(1, L - 1))

    def options(self, clause: str) -> dict:
        """所有候選句 {字串: (pos, src, dst)}：
        窮舉所有能連成詞的 2~4 字 span 之同音詞替換 + 單字同音替換（單一編輯）。"""
        cands = {}
        n = len(clause)
        for L in range(2, self.max_word_len + 1):           # 詞級：所有可連 span（重疊全列）
            for i in range(0, n - L + 1):
                span = clause[i:i + L]
                for w in _span_reading_words(span)[: self.word_cand]:
                    if w != span:
                        cands.setdefault(clause[:i] + w + clause[i + L:], (i, span, w))
        for i, ch in enumerate(clause):                     # 字級：單字同音
            for c in phonetics.homophones(ch, limit=self.char_cand):
                cands.setdefault(clause[:i] + c + clause[i + 1:], (i, ch, c))
        return cands

    def _correct_clause(self, clause: str) -> str:
        cur = clause
        for _ in range(self.max_iter):
            best, best_s = cur, self._pll(cur)
            for cand in self.options(cur):
                s = self._pll(cand)
                if s > best_s + self.margin:
                    best_s, best = s, cand
            if best == cur:
                break
            cur = best
        return cur

    def correct(self, text: str) -> Result:
        text = text.strip()
        if not text:
            return Result(text, text)
        out, idx = [], 0
        for m in _CLAUSE.finditer(text):
            out.append(text[idx:m.start()])               # 原樣保留標點/空白
            out.append(self._correct_clause(m.group()))
            idx = m.end()
        out.append(text[idx:])
        corrected = "".join(out)
        changes = [(k, a, b) for k, (a, b) in enumerate(zip(text, corrected)) if a != b]
        return Result(text, corrected, changes)

    # ---- 學習訊號：正解是否在選項可達範圍（單步）----
    def reachable(self, text: str, gold: str) -> dict:
        """逐子句檢查 gold 是否 ∈ {原子句} ∪ options(原子句)。
        回傳 {reachable, clauses:[(orig, gold, in_options)]}；
        子句結構不一致則 reachable=None。"""
        oc = _CLAUSE.findall(text)
        gc = _CLAUSE.findall(gold)
        if len(oc) != len(gc):
            return {"reachable": None, "reason": "子句結構不一致", "clauses": []}
        detail, ok = [], True
        for o, g in zip(oc, gc):
            hit = (g == o) or (g in self.options(o))
            detail.append((o, g, hit))
            ok = ok and hit
        return {"reachable": ok, "clauses": detail}


# ===== csc/select_corrector_v3 =====
# -*- coding: utf-8 -*-
"""SelectCorrector v3 —— 在 v2（窮舉可連詞選項）之上，加「詞頻先驗 + 可編輯加權」。

評分（每個候選相對目前句的增益）：
    gain = [PLL(cand) - PLL(cur)]            ← BERT 流暢度（語境）
         + λ · [log(1+freq(dst)) - log(1+freq(src))]   ← 詞庫機率先驗

- freq 來自 phrase.occ，並可被 data/custom_boost.txt 的加權「加強」。
  → 這就是「更新詞庫 / 加強某候選機率」的開關：模型選錯時，在加權檔幫正解加分即可，
    不必重訓模型（符合關注點分離）。
- λ (lambda_prior) 控制「多信任詞頻 vs 多信任 BERT 語境」。
- 修掉 v2 的「向→曏」問題（像 freq 18673 >> 曏 freq 1）。

繼承 v2，不修改 v1/v2。
"""
import math
import os

from . import wordphon

_BOOST_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "custom_boost.txt")


class SelectCorrectorV3(SelectCorrectorV2):
    def __init__(self, *args, lambda_prior: float = 0.5, **kwargs):
        super().__init__(*args, **kwargs)
        self.lambda_prior = lambda_prior
        self._boost = self._load_boost()

    @staticmethod
    def _load_boost() -> dict:
        d = {}
        if os.path.exists(_BOOST_FILE):
            with open(_BOOST_FILE, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    p = line.split()
                    if len(p) >= 2 and p[-1].lstrip("-").isdigit():
                        d[p[0]] = d.get(p[0], 0) + int(p[-1])
        return d

    def _freq(self, w: str) -> int:
        return wordphon.freq(w) + self._boost.get(w, 0)

    def _correct_clause(self, clause: str) -> str:
        cur = clause
        for _ in range(self.max_iter):
            base = self._pll(cur)
            best, best_gain = cur, self.margin
            for cand, (i, src, dst) in self.options(cur).items():
                fluency = self._pll(cand) - base
                prior = math.log(1 + self._freq(dst)) - math.log(1 + self._freq(src))
                gain = fluency + self.lambda_prior * prior
                if gain > best_gain:
                    best_gain, best = gain, cand
            if best == cur:
                break
            cur = best
        return cur


# ===== csc/select_corrector_v4 =====
# -*- coding: utf-8 -*-
"""SelectCorrector v4 = v3 + 硬 ban 罕用單字候選。

問題：v3 在多音字上會挑到罕用同音字（例：姊→訾，訾 詞頻僅 9），只靠詞頻先驗軟壓不夠。
修法：對「單字候選」加**硬性詞頻門檻** min_cand_freq——詞頻低於門檻者直接從候選移除，
      不留給模型選；並把 lambda_prior 預設提高到 1.0，讓常用字更勝出。
注意：詞候選（≥2 字、來自小麥詞庫的真詞）不套此單字門檻。
繼承 v3，不修改 v1/v2/v3。
"""


class SelectCorrectorV4(SelectCorrectorV3):
    def __init__(self, *args, min_cand_freq: int = 50, lambda_prior: float = 1.0, **kwargs):
        super().__init__(*args, lambda_prior=lambda_prior, **kwargs)
        self.min_cand_freq = min_cand_freq

    def options(self, clause: str) -> dict:
        opts = super().options(clause)
        out = {}
        for cand, (i, src, dst) in opts.items():
            if len(dst) == 1 and self._freq(dst) < self.min_cand_freq:
                continue   # 硬 ban 罕用單字候選（如 訾=9、曏=1）
            out[cand] = (i, src, dst)
        return out


# ===== csc/select_corrector_v5 =====
# -*- coding: utf-8 -*-
"""SelectCorrector v5 = v4 + 最終同音守門（保證只做同音替換）。

發現（實測 log）：v2~v4 偶爾產生「非同音 / 不同聲調」的字變動，違反核心保證：
  - 這惠紅的 → 這塊公地（惠→塊，惠=ㄏㄨㄟˋ / 塊=ㄎㄨㄞˋ，非同音）
  - 一時性起使用… → …是用（使=ㄕˇ / 是=ㄕˋ，不同調）
疑為候選生成在某些讀音組合（多音字、罕用讀音）下誤匹配。
修法：最終輸出再過一道守門——逐字檢查，若「原字↔新字」非同音(含聲調) → 一律還原。
不論候選怎麼產生，輸出保證只含同音替換。
"""
from csc import phonetics


class SelectCorrectorV5(SelectCorrectorV4):
    def correct(self, text: str) -> Result:
        res = super().correct(text)
        src, out = res.text, list(res.corrected)
        changed = False
        for i in range(min(len(src), len(out))):
            if out[i] != src[i] and not phonetics.same_sound(src[i], out[i]):
                out[i] = src[i]          # 非同音變動 → 還原
                changed = True
        if not changed:
            return res
        corrected = "".join(out)
        changes = [(k, a, b) for k, (a, b) in enumerate(zip(src, corrected)) if a != b]
        return Result(src, corrected, changes)


# ===== csc/select_corrector_v6 =====
# -*- coding: utf-8 -*-
"""SelectCorrector v6 = v5 + 排名候選清單（給 IME 式「再按一次換下一個」）。

ranked_corrections(clause) 回傳 [最佳, 次佳, 第三, …, 原句] —— 全部同音、依分數排序、去重。
- [0] = 正常最佳結果（含多錯字迭代 + 同音守門），與 v5 的 correct() 一致。
- 之後是其他同音候選（單一編輯）依分數排名。
- 末端放回原句，循環時可回到「不改」。
若引擎判斷不需改（best == 原句）→ 回傳 [原句]（不進入循環）。
"""
import math

from csc import phonetics


class SelectCorrectorV6(SelectCorrectorV5):
    def _homophone_ok(self, src: str, cand: str) -> bool:
        if len(src) != len(cand):
            return False
        return all(phonetics.same_sound(a, b) for a, b in zip(src, cand) if a != b)

    def ranked_corrections(self, clause: str, top_n: int = 10) -> list:
        clause = clause.strip()
        if not clause:
            return [clause]
        best = self.correct(clause).corrected
        if best == clause:
            return [clause]                      # 不需改 → 不循環
        base = self._pll(clause)
        scored = []
        for cand, (i, src, dst) in self.options(clause).items():
            if cand == clause or not self._homophone_ok(clause, cand):
                continue
            fl = self._pll(cand) - base
            pr = math.log(1 + self._freq(dst)) - math.log(1 + self._freq(src))
            scored.append((fl + self.lambda_prior * pr, cand))
        scored.sort(reverse=True)
        out = [best]
        for _, cand in scored:
            if cand not in out:
                out.append(cand)
            if len(out) >= top_n:
                break
        out.append(clause)                       # 循環末端 = 原句（還原）
        return out


# ===== csc/select_corrector_v7 =====
# -*- coding: utf-8 -*-
"""SelectCorrector v7 = v6 + ranked_corrections 永遠提供候選（即使「不用改」）。

讓 F1 預設不改、但仍能再按 F1 循環下一個機率的字：
ranked_corrections 回傳 [預設(最佳或原句), 候選2, 候選3, …, 原句]。
若無信心修正，預設=原句（不改），後面仍接同音候選供循環。
"""
import math



class SelectCorrectorV7(SelectCorrectorV6):
    def ranked_corrections(self, clause: str, top_n: int = 6) -> list:
        clause = clause.strip()
        if not clause:
            return [clause]
        best = self.correct(clause).corrected
        base = self._pll(clause)
        scored = []
        for cand, (i, src, dst) in self.options(clause).items():
            if cand == clause or not self._homophone_ok(clause, cand):
                continue
            fl = self._pll(cand) - base
            pr = math.log(1 + self._freq(dst)) - math.log(1 + self._freq(src))
            scored.append((fl + self.lambda_prior * pr, cand))
        scored.sort(reverse=True)
        out = [best] if best != clause else [clause]   # 不用改時也提供候選，原句當預設
        for _, cand in scored:
            if cand not in out:
                out.append(cand)
            if len(out) >= top_n:
                break
        if clause not in out:
            out.append(clause)
        return out


# ===== csc/select_corrector_v8 =====
# -*- coding: utf-8 -*-
"""SelectCorrector v8 = v6 + 兩道候選端手術刀（torch 版，對應 ONNX 的 OnnxCorrectorV2）。

  reading_ratio=0.02     → 多音字收斂：砍掉『沒人用的奇怪讀音』，斷開假同音（解→界、姊→子）
  guard_particles=True   → 句尾語助詞守門：句尾 嗎/呢/吧/啊… 不准被同音替換（走吧→走八）

只覆寫候選產生 options()——correct()(v3 的 _correct_clause) 與 ranked_corrections()(v6)
都經過 options()，故兩條路徑一次到位。打分/守門/迭代全沿用 v6，旗標關掉＝與 v6 逐字相同。
詳見 csc/reading_filter.py。
"""
from csc import reading_filter


class SelectCorrectorV8(SelectCorrectorV6):
    def __init__(self, *args, reading_ratio=0.02, guard_particles=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.reading_ratio = reading_ratio
        self.guard_particles = guard_particles

    def _read_ok(self, src: str, dst: str) -> bool:
        """收斂版同音檢查：src→dst 每個變動字都要『實際讀音』有交集。"""
        if self.reading_ratio is None or len(src) != len(dst):
            return True
        return all(reading_filter.same_sound(a, b, self.reading_ratio)
                   for a, b in zip(src, dst) if a != b)

    def options(self, clause: str) -> dict:
        opts = super().options(clause)
        if self.reading_ratio is None and not self.guard_particles:
            return opts
        out = {}
        for cand, (i, src, dst) in opts.items():
            if self.guard_particles and len(dst) == 1 \
                    and reading_filter.is_guarded_particle(clause, i):
                continue                      # 句尾助詞：擋掉對它的同音替換
            if not self._read_ok(src, dst):
                continue                      # 多音字收斂：奇怪讀音不算同音
            out[cand] = (i, src, dst)
        return out
