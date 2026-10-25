# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import os

import numpy as np

from .. import paths

_DIR = paths.MODELS
_state = {"sess": None, "vocab": None, "dead": False}
MAXLEN = 128


MODELS = {
    "default": ("判別裁判", "judge_disc.onnx"),
}
DEFAULT_MODEL = "default"


def model_key():
    try:
        from .. import settings
        k = settings.get("disc_model") or DEFAULT_MODEL
    except Exception:
        k = DEFAULT_MODEL
    return k if k in MODELS else DEFAULT_MODEL


def reload_model():
    _state.update(sess=None, dead=False)


def _load():
    if _state["dead"] or _state["sess"] is not None:
        return _state["sess"]
    try:
        import onnxruntime as ort
        path = os.path.join(_DIR, MODELS[model_key()][1])
        vpath = os.path.join(_DIR, "vocab.txt")
        if not (os.path.exists(path) and os.path.exists(vpath)):
            _state["dead"] = True
            return None
        v = {}
        with open(vpath, encoding="utf-8") as f:
            for i, line in enumerate(f):
                v[line.rstrip("\n")] = i
        _state["vocab"] = v
        so = ort.SessionOptions()
        so.log_severity_level = 3
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
        _state["sess"] = ort.InferenceSession(path, so, providers=["CPUExecutionProvider"])
    except Exception:
        _state["dead"] = True
    return _state["sess"]


def available():
    return _load() is not None


def encode_pair(vocab, a, b, maxlen=MAXLEN):
    cls, sep, unk = vocab.get("[CLS]", 101), vocab.get("[SEP]", 102), vocab.get("[UNK]", 100)
    room = maxlen - 3
    if len(a) + len(b) > room:
        keep = room // 2
        a, b = a[-keep:], b[-(room - keep):]
    ia = [vocab.get(c, unk) for c in a]
    ib = [vocab.get(c, unk) for c in b]
    ids = [cls] + ia + [sep] + ib + [sep]
    tt = [0] * (len(ia) + 2) + [1] * (len(ib) + 1)
    return ids, tt


def score(clause, cands):
    sess = _load()
    if sess is None or not cands:
        return None
    try:
        v = _state["vocab"]
        enc = [encode_pair(v, clause, c) for c in cands]
        n = max(len(x[0]) for x in enc)
        ids = np.zeros((len(enc), n), dtype=np.int64)
        att = np.zeros((len(enc), n), dtype=np.int64)
        tt = np.zeros((len(enc), n), dtype=np.int64)
        for i, (a, t) in enumerate(enc):
            ids[i, :len(a)] = a
            att[i, :len(a)] = 1
            tt[i, :len(t)] = t
        out = sess.run(["logits"], {"input_ids": ids, "attention_mask": att,
                                    "token_type_ids": tt})[0]
        return [float(x) for x in np.asarray(out).reshape(-1)]
    except Exception:
        _state["dead"] = True
        return None
