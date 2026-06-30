# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""把 model + prompt + 後處理串起來，提供 f1~f4 的修正函式。

每個 correct_fX(model, src, gold) 回傳 (pred, raw_length_mismatch)，
pred 保證與 src 等長。gold 只有 f2 會用到（oracle 錯字數）。
"""
from . import prompts
from .postprocess import clean_output, enforce_same_length
from .data import n_errors

# 視為分段邊界的標點 / 空白
_PUNCT = set("，。！？；：、,.!?;:　 \n\t")


def _gen(model, user: str, src_len: int) -> str:
    raw = model.chat(user, max_tokens=src_len + 32)
    return clean_output(raw)


def correct_f1(model, src: str, gold: str | None = None):
    pred = _gen(model, prompts.build_f1(src), len(src))
    return enforce_same_length(src, pred)


def correct_f2(model, src: str, gold: str):
    pred = _gen(model, prompts.build_f2(src, n_errors(src, gold)), len(src))
    return enforce_same_length(src, pred)


def correct_f4(model, src: str, gold: str | None = None):
    pred = _gen(model, prompts.build_f4(src), len(src))
    return enforce_same_length(src, pred)


def _split_segments(text: str):
    """切成 [(片段, 是否為標點)]；標點原樣保留。"""
    segs, buf = [], ""
    for ch in text:
        if ch in _PUNCT:
            if buf:
                segs.append((buf, False)); buf = ""
            segs.append((ch, True))
        else:
            buf += ch
    if buf:
        segs.append((buf, False))
    return segs


def correct_f3(model, src: str, gold: str | None = None, ctx_k: int = 6):
    """軟體切割：依標點切片段，逐片段帶『前文視窗』修正後重組（往前看 ctx_k 字）。"""
    out_parts, corrected_so_far = [], ""
    for seg, is_punct in _split_segments(src):
        if is_punct:
            out_parts.append(seg)
            corrected_so_far += seg
            continue
        left = corrected_so_far[-ctx_k:]
        raw = model.chat(prompts.build_f3_segment(seg, left), max_tokens=len(seg) + 16)
        fixed, _ = enforce_same_length(seg, clean_output(raw))
        out_parts.append(fixed)
        corrected_so_far += fixed
    return enforce_same_length(src, "".join(out_parts))


CONDITIONS = {
    "f1": correct_f1,
    "f2": correct_f2,
    "f3": correct_f3,
    "f4": correct_f4,
}
