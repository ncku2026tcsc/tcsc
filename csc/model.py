# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""Llama-3-Taiwan-8B GGUF 載入與生成封裝（llama-cpp-python，GPU 全層 offload）。"""
from __future__ import annotations

import os

DEFAULT_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "models", "llama-3-taiwan-8B-instruct-q4_k_m.gguf",
)

# CSC 的核心 system prompt：強調「等長、只替換」是壓制 LLM 過度改寫的關鍵。
SYSTEM_PROMPT = (
    "你是一個專門做繁體中文錯字校正（Chinese Spelling Correction）的助手。"
    "句子中可能含有「同音或形近」的錯字。請找出並改正錯字，"
    "務必保持句子長度與原句完全相同：只能替換錯字，"
    "不可增加、刪除或改寫其他任何字與標點。"
    "只輸出改正後的句子本身，不要加任何解釋、引號或前後綴。"
)


def _import_llama():
    try:
        from llama_cpp import Llama
        return Llama
    except OSError as e:  # 多半是缺 CUDA 12 runtime DLL
        raise RuntimeError(
            "載入 llama_cpp 失敗（通常是缺 CUDA 12 runtime DLL）。\n"
            "請把 cudart64_12.dll / cublas64_12.dll / cublasLt64_12.dll 複製到\n"
            "  <csc env>\\Lib\\site-packages\\llama_cpp\\lib\\\n"
            "（可從 base 環境的 torch\\lib 取得）。\n"
            f"原始錯誤：{e}"
        ) from e


class LlamaCorrector:
    """封裝一顆 GGUF chat 模型，提供繁中錯字校正用的 chat 介面。"""

    def __init__(self, model_path: str = DEFAULT_MODEL_PATH, n_gpu_layers: int = -1,
                 n_ctx: int = 2048, seed: int = 0, verbose: bool = False):
        Llama = _import_llama()
        self.llm = Llama(
            model_path=model_path,
            n_gpu_layers=n_gpu_layers,   # -1 = 全部 offload 到 GPU
            n_ctx=n_ctx,
            seed=seed,
            verbose=verbose,
        )

    def chat(self, user: str, system: str = SYSTEM_PROMPT,
             max_tokens: int = 256, temperature: float = 0.0) -> str:
        out = self.llm.create_chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return out["choices"][0]["message"]["content"]
