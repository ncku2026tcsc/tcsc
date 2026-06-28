# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""輕量 BERT MLM 推論：onnxruntime + 極簡 vocab tokenizer。

runtime 完全不需 torch / transformers——只用 onnxruntime + numpy。
tokenizer 直接讀 vocab.txt（bert-base-chinese 是字級 WordPiece，中文一字一 token）。
"""
import os

import numpy as np
import onnxruntime as ort


def log_softmax(x):
    m = np.max(x)
    return x - m - np.log(np.sum(np.exp(x - m)))


class OnnxBert:
    def __init__(self, onnx_path: str, vocab_path: str):
        so = ort.SessionOptions()
        so.intra_op_num_threads = max(1, min(8, os.cpu_count() or 4))
        self.sess = ort.InferenceSession(onnx_path, sess_options=so,
                                         providers=["CPUExecutionProvider"])
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
        return self.sess.run(["logits"], feeds)[0]   # (B, S, V)
