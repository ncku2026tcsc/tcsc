# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/tcsc2026/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import os
import time

from . import crashlog, engines, select_corrector_onnx_v2
from .onnx_engine import OnnxBert
from .. import config, paths, settings

_engine = None


def load():
    global _engine
    if _engine is not None:
        return _engine
    st = engines.current()
    _lbl, pm, jf = engines.CONFIGS[st]
    vocab_path = paths.model(config.ENGINE["vocab"])
    proposer_path = paths.model(engines.PROPOSER_FILES.get(pm, "proposer.onnx"))
    if not os.path.exists(proposer_path):
        proposer_path = paths.model("proposer.onnx")
    corrector = select_corrector_onnx_v2.OnnxCorrectorV2(
        proposer_path, vocab_path, reading_ratio=None, guard_particles=True)
    corrector.char_cand = 12
    corrector.word_cand = 10
    judge_path = paths.model(jf)
    if os.path.exists(judge_path):
        corrector.judge = OnnxBert(judge_path, vocab_path, basic_opt=True)
    _engine = corrector
    return _engine


def ranked(text, top_n=10):
    return load().ranked_corrections(text, top_n=top_n)


def correct(text):
    return load().correct(text).corrected


def warm():
    try:
        t0 = time.monotonic()
        if settings.get("disc_judge"):
            from . import discjudge
            if discjudge.available():
                discjudge.score("預熱", ["預熱", "預喝"])
        load().ranked_corrections("這是預熱用的一句話")
        crashlog.log(f"模型預熱完成 {(time.monotonic() - t0) * 1000:.0f}ms")
    except Exception as e:
        crashlog.log(f"模型預熱略過：{e}")
