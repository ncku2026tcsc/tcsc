# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/tcsc2026/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import os

import numpy as np

from .. import paths

DET_TH = 0.09
CAP = 3

_dir = paths.MODELS
_state = {"sess": None, "dead": False, "vocab": None}


def _load():
    if _state["dead"] or _state["sess"] is not None:
        return _state["sess"]
    try:
        import onnxruntime as ort
        path = os.path.join(_dir, "detector.onnx")
        vpath = os.path.join(_dir, "vocab.txt")
        if not (os.path.exists(path) and os.path.exists(vpath)):
            _state["dead"] = True
            return None
        vocab = {}
        with open(vpath, encoding="utf-8") as f:
            for i, line in enumerate(f):
                vocab[line.rstrip("\n")] = i
        _state["vocab"] = vocab
        so = ort.SessionOptions()
        so.log_severity_level = 3
        _state["sess"] = ort.InferenceSession(path, so,
                                              providers=["CPUExecutionProvider"])
    except Exception:
        _state["dead"] = True
    return _state["sess"]


def suspects(clause, th=DET_TH, cap=CAP):
    sess = _load()
    if sess is None or not clause:
        return []
    try:
        v = _state["vocab"]
        unk = v.get("[UNK]", 100)
        ids = [v.get("[CLS]", 101)] + [v.get(c, unk) for c in clause] + \
              [v.get("[SEP]", 102)]
        arr = np.array([ids], dtype=np.int64)
        ones = np.ones_like(arr)
        logits = sess.run(None, {"input_ids": arr, "attention_mask": ones,
                                 "token_type_ids": np.zeros_like(arr)})[0][0]
        ex = np.exp(logits - logits.max(-1, keepdims=True))
        p1 = (ex[:, 1] / ex.sum(-1))[1:1 + len(clause)]
        out = [(i, float(p)) for i, p in enumerate(p1)
               if p >= th and "一" <= clause[i] <= "鿿"]
        out.sort(key=lambda x: -x[1])
        return out[:cap]
    except Exception:
        _state["dead"] = True
        return []
