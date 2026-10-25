# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import os

import numpy as np
import onnxruntime as ort

try:
    ort.disable_telemetry_events()
except Exception:
    pass


def log_softmax(x):
    m = np.max(x)
    return x - m - np.log(np.sum(np.exp(x - m)))


class OnnxBert:
    def __init__(self, onnx_path: str, vocab_path: str, basic_opt: bool = False):
        so = ort.SessionOptions()
        so.intra_op_num_threads = max(1, min(8, os.cpu_count() or 4))
        if basic_opt:
            so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
        self.sess = ort.InferenceSession(onnx_path, sess_options=so,
                                         providers=["CPUExecutionProvider"])
        self._path, self._basic_opt = onnx_path, basic_opt
        self.tok2id = {}
        with open(vocab_path, encoding="utf-8") as f:
            for i, line in enumerate(f):
                self.tok2id[line.rstrip("\n")] = i
        self.cls = self.tok2id["[CLS]"]
        self.sep = self.tok2id["[SEP]"]
        self.mask = self.tok2id["[MASK]"]
        self.unk = self.tok2id["[UNK]"]

    def token_id(self, ch: str):
        return self.tok2id.get(ch)

    def encode(self, text: str):
        return [self.cls] + [self.tok2id.get(c, self.unk) for c in text] + [self.sep]

    def run(self, batch_ids):
        arr = np.asarray(batch_ids, dtype=np.int64)
        feeds = {"input_ids": arr,
                 "attention_mask": np.ones_like(arr),
                 "token_type_ids": np.zeros_like(arr)}
        return self.sess.run(["logits"], feeds)[0]

    def run_singles(self, many_ids):
        if len(many_ids) <= 1:
            return [self.run([m])[0] for m in many_ids]
        if getattr(self, "_pool", None) is None:
            import concurrent.futures as cf
            so = ort.SessionOptions()
            so.intra_op_num_threads = 1
            so.inter_op_num_threads = 1
            if self._basic_opt:
                so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
            self._sess1 = ort.InferenceSession(self._path, sess_options=so, providers=["CPUExecutionProvider"])
            self._pool = cf.ThreadPoolExecutor(max(2, min(8, os.cpu_count() or 4)), thread_name_prefix="mlm")

        def one(ids):
            arr = np.asarray([ids], dtype=np.int64)
            feeds = {"input_ids": arr, "attention_mask": np.ones_like(arr), "token_type_ids": np.zeros_like(arr)}
            return self._sess1.run(["logits"], feeds)[0][0]
        return list(self._pool.map(one, many_ids))
