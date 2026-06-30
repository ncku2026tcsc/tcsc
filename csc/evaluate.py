# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""CSC 評估指標：字級 (char-level) 的 Detection / Correction P/R/F1，
以及句級 (sentence-level) 的偵測 / 修正正確率。

定義（皆假設 pred 已與 src 等長）：
  gold_err  = {i : src[i] != gold[i]}          真正的錯字位置
  pred_chg  = {i : src[i] != pred[i]}           模型實際改動的位置
  Detection : 有沒有「找對位置」
  Correction: 在找到的位置有沒有「改成正解」
"""


def _prf(tp: int, fp: int, fn: int):
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return p, r, f


def evaluate(samples, preds):
    """samples: list[{src, gold}]；preds: list[str]（與對應 src 等長）。"""
    d_tp = d_fp = d_fn = 0
    c_tp = c_fp = c_fn = 0
    n = len(samples)
    sent_det_ok = sent_corr_ok = 0

    for s, pred in zip(samples, preds):
        src, gold = s["src"], s["gold"]
        L = min(len(src), len(gold), len(pred))
        gold_err = {i for i in range(L) if src[i] != gold[i]}
        pred_chg = {i for i in range(L) if src[i] != pred[i]}

        # 字級 detection
        d_tp += len(gold_err & pred_chg)
        d_fp += len(pred_chg - gold_err)
        d_fn += len(gold_err - pred_chg)

        # 字級 correction：在有改動的位置，改成正解才算對
        for i in pred_chg:
            if pred[i] == gold[i]:
                c_tp += 1
            else:
                c_fp += 1
        for i in gold_err:
            if pred[i] != gold[i]:
                c_fn += 1

        # 句級
        if gold_err == pred_chg:
            sent_det_ok += 1
        if pred == gold:
            sent_corr_ok += 1

    dp, dr, df = _prf(d_tp, d_fp, d_fn)
    cp, cr, cf = _prf(c_tp, c_fp, c_fn)
    return {
        "char_detection": {"P": dp, "R": dr, "F1": df, "tp": d_tp, "fp": d_fp, "fn": d_fn},
        "char_correction": {"P": cp, "R": cr, "F1": cf, "tp": c_tp, "fp": c_fp, "fn": c_fn},
        "sent_detection_acc": sent_det_ok / n if n else 0.0,
        "sent_correction_acc": sent_corr_ok / n if n else 0.0,
        "n": n,
    }
