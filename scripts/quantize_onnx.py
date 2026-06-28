# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import os
import sys
sys.stdout.reconfigure(encoding="utf-8")
from onnxruntime.quantization import quantize_dynamic, QuantType

SRC = r"D:\NLP_Final\models\bert.onnx"
DST = r"D:\NLP_Final\models\bert.int8.onnx"
quantize_dynamic(SRC, DST, weight_type=QuantType.QInt8)
print("int8 size MB:", round(os.path.getsize(DST) / 1e6, 1))

from csc.select_corrector_onnx import OnnxCorrector
c = OnnxCorrector(DST, r"D:\NLP_Final\models\vocab.txt")
for t in ["現在來嘗試一下剛剛時做的程式", "天氣很好我們去公圓",
          "向我平常根本就沒用這個做法", "我的興趣是看書"]:
    print(t, "->", c.correct(t).corrected)
