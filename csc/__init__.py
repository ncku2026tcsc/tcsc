# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""繁體中文錯字校正 (Chinese Spelling Correction, CSC) 實驗框架。

以 Llama-3-Taiwan-8B (GGUF, llama-cpp-python, GPU) 為基礎，
比較 f1~f4 四種 prompt 條件在繁中錯字修正上的表現。
"""

__all__ = ["model", "prompts", "confusion", "postprocess", "evaluate", "data", "pipeline"]
