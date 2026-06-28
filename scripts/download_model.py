# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""把 BERT 從 HF 快取存成本地檔（供 PyInstaller 打包）。"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from transformers import AutoTokenizer, AutoModelForMaskedLM

NAME = "ckiplab/bert-base-chinese"
OUT = r"D:\NLP_Final\models\bert"
print("載入", NAME, "…")
tok = AutoTokenizer.from_pretrained(NAME)
model = AutoModelForMaskedLM.from_pretrained(NAME)
tok.save_pretrained(OUT)
model.save_pretrained(OUT, safe_serialization=True)
print("已存到", OUT)
