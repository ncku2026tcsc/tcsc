# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""把 BERT MLM 匯出成 ONNX + 抽出 vocab.txt（供 onnxruntime 引擎用，runtime 不需 torch/transformers）。"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import torch
from transformers import AutoModelForMaskedLM, AutoTokenizer

LOCAL = r"D:\NLP_Final\models\bert"
ONNX = r"D:\NLP_Final\models\bert.onnx"
VOCAB = r"D:\NLP_Final\models\vocab.txt"

tok = AutoTokenizer.from_pretrained(LOCAL)
model = AutoModelForMaskedLM.from_pretrained(LOCAL).eval()

enc = tok("測試句子", return_tensors="pt")
inputs = (enc["input_ids"], enc["attention_mask"], enc["token_type_ids"])
dyn = {k: {0: "batch", 1: "seq"} for k in ["input_ids", "attention_mask", "token_type_ids", "logits"]}

torch.onnx.export(
    model, inputs, ONNX,
    input_names=["input_ids", "attention_mask", "token_type_ids"],
    output_names=["logits"], dynamic_axes=dyn,
    opset_version=14, do_constant_folding=True, dynamo=False,
)
print("exported", ONNX)

vocab = tok.get_vocab()                       # {token: id}
with open(VOCAB, "w", encoding="utf-8") as f:
    for t, _ in sorted(vocab.items(), key=lambda x: x[1]):
        f.write(t + "\n")
print("vocab", len(vocab), "->", VOCAB)
print("mask id", tok.mask_token_id, "cls", tok.cls_token_id, "sep", tok.sep_token_id, "pad", tok.pad_token_id, "unk", tok.unk_token_id)
