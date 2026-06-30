# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""BERT 同音重評分校正引擎（masked-LM rescoring，限制在繁體同音候選）。

核心：把位置遮起來，讓 BERT 算該位置各字機率，
      只在「原字 + 其同音候選」中比較，選機率明顯更高者才替換。
- 自動模式：逐輪挑「信心最高」的一個同音改正，套用後重算（處理部分相鄰錯字）。
- 提示模式：look_back 指定最後 N 字範圍；n_errors 指定錯字數。
            範圍內「一起遮罩」聯合重評分，可解相鄰雙錯字（城市→程式）。
"""
from dataclasses import dataclass, field

import torch
from transformers import AutoTokenizer, AutoModelForMaskedLM

from . import phonetics

DEFAULT_MODEL = "ckiplab/bert-base-chinese"


@dataclass
class Change:
    pos: int
    src: str
    dst: str
    score: float   # logP(dst) - logP(src)，越大越有信心


@dataclass
class Result:
    text: str
    corrected: str
    changes: list = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.corrected != self.text


class BertCorrector:
    def __init__(self, model_name: str = DEFAULT_MODEL, device=None,
                 margin: float = 3.0, cand_limit: int = 30):
        self.tok = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForMaskedLM.from_pretrained(model_name).eval()
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)
        self.margin = margin
        self.cand_limit = cand_limit

    def _cand_ids(self, ch: str) -> dict:
        """原字 + 同音候選 -> {字: token_id}（只留 BERT 詞表內的單字）。"""
        cid = {}
        for c in [ch] + phonetics.homophones(ch, limit=self.cand_limit):
            t = self.tok.convert_tokens_to_ids(c)
            if t is not None and t != self.tok.unk_token_id:
                cid[c] = t
        return cid

    @torch.no_grad()
    def _logprobs(self, ids: torch.Tensor):
        return torch.log_softmax(self.model(ids.unsqueeze(0)).logits[0], dim=-1)

    def correct(self, text: str, look_back=None, n_errors=None,
                margin=None, max_iter: int = 4) -> Result:
        text = text.strip()
        if not text:
            return Result(text, text)
        margin = self.margin if margin is None else margin
        chars = list(text)
        n = len(chars)
        enc = self.tok(text, return_tensors="pt").to(self.device)
        ids = enc["input_ids"][0]
        if len(ids) != n + 2:           # 對齊失敗（含非單 token 字元）→ 不動
            return Result(text, text)

        lo = (n - look_back) if look_back else 0
        positions = list(range(max(lo, 0), n))

        if look_back is not None:
            # 提示模式：使用者按了 F 鍵 = 斷定這裡一定有錯 -> 強制替換，不受 margin 限制
            budget = n_errors if n_errors is not None else 1
            changes = self._joint(ids, chars, positions, budget)
        else:
            changes = self._iterative(ids, chars, positions, margin,
                                      budget=n_errors if n_errors is not None else n,
                                      max_iter=max_iter)
        return Result(text, "".join(chars), changes)

    @torch.no_grad()
    def _iterative(self, ids, chars, positions, margin, budget, max_iter):
        """每輪挑全域信心最高的一個同音改正，套用後重算。"""
        changes = []
        for _ in range(max_iter):
            if len(changes) >= budget:
                break
            best = None  # (gain, i, src, dst, tid)
            for i in positions:
                ch = chars[i]
                cid = self._cand_ids(ch)
                if ch not in cid or len(cid) <= 1:
                    continue
                masked = ids.clone()
                masked[i + 1] = self.tok.mask_token_id
                lp = self._logprobs(masked)[i + 1]
                scored = {c: lp[t].item() for c, t in cid.items()}
                cand = max(scored, key=scored.get)
                gain = scored[cand] - scored[ch]
                if cand != ch and gain >= margin and (best is None or gain > best[0]):
                    best = (gain, i, ch, cand, cid[cand])
            if best is None:
                break
            gain, i, src, dst, tid = best
            chars[i] = dst
            ids[i + 1] = tid
            changes.append(Change(i, src, dst, round(gain, 2)))
        return changes

    @torch.no_grad()
    def _joint(self, ids, chars, positions, budget):
        """提示模式：範圍內一起遮罩、聯合重評分，**強制**替換 budget 個位置。
        使用者按 F 鍵即斷定有錯，故不套用 margin，只挑「最該換」的幾個位置，
        各換成該位置機率最高的『非原字同音候選』。"""
        masked = ids.clone()
        for i in positions:
            masked[i + 1] = self.tok.mask_token_id
        lp = self._logprobs(masked)
        ranked = []
        for i in positions:
            ch = chars[i]
            cid = self._cand_ids(ch)
            if ch not in cid or len(cid) <= 1:
                continue
            scored = {c: lp[i + 1][t].item() for c, t in cid.items()}
            alts = {c: s for c, s in scored.items() if c != ch}
            if not alts:
                continue
            best = max(alts, key=alts.get)
            gain = alts[best] - scored[ch]   # 可能為負，仍強制換最可能的同音字
            ranked.append((gain, i, ch, best))
        ranked.sort(reverse=True)
        changes = []
        for gain, i, ch, best in ranked[:budget]:
            chars[i] = best
            changes.append(Change(i, ch, best, round(gain, 2)))
        return changes
