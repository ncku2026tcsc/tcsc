# -*- coding: utf-8 -*-
# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""校正歷史記錄（JSONL）。重點：把『模型選錯』的案例分類記下來，供報告錯誤分析。

檔案：logs/history.jsonl，每行一筆。
  type=correction ：每次校正自動記（input/output/changes/margin）
  type=annotation ：使用者標註（label=correct/wrong；wrong 時附 gold 與逐字分析）
錯誤分類（need 等長）：
  false_positive  誤改：把本來對的字改掉（過度修正）
  missed          漏改：該改的沒改
  wrong_correction改錯方向：有改但改成錯字
"""
import datetime
import json
import os

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
LOG_FILE = os.path.join(LOG_DIR, "history.jsonl")
ERROR_FILE = os.path.join(LOG_DIR, "error_cases.jsonl")


def _append(record: dict) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    record = {"ts": datetime.datetime.now().isoformat(timespec="seconds"), **record}
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def log_correction(input_text: str, output_text: str, changes, margin: float) -> None:
    _append({
        "type": "correction",
        "input": input_text,
        "output": output_text,
        "changes": [[p, a, b] for (p, a, b) in changes],
        "margin": margin,
        "label": "unrated",
    })


def analyze(input_text: str, output_text: str, gold: str) -> dict:
    """逐位比對 input/output/gold，分類錯誤。"""
    res = {"correct": output_text == gold, "false_positive": [],
           "missed": [], "wrong_correction": []}
    if not (len(input_text) == len(output_text) == len(gold)):
        res["length_mismatch"] = True
        return res
    for i, (inp, out, g) in enumerate(zip(input_text, output_text, gold)):
        if out == g:
            continue
        if inp == g and out != inp:
            res["false_positive"].append([i, inp, out])
        elif inp != g and out == inp:
            res["missed"].append([i, inp, g])
        else:
            res["wrong_correction"].append([i, inp, out, g])
    return res


def log_annotation(input_text: str, output_text: str, label: str, gold: str = None) -> dict:
    rec = {"type": "annotation", "input": input_text, "output": output_text, "label": label}
    if gold:
        rec["gold"] = gold
        rec["analysis"] = analyze(input_text, output_text, gold)
    _append(rec)
    return rec.get("analysis", {})


def log_error_case(problem: str, wrong: str = None) -> None:
    """把『模型改錯的題目（＝原輸入）』記成乾淨、單一用途的失敗清單（JSONL），與 history.jsonl 分開。
    每行一筆：{"ts", "input"(原輸入), "output"(模型錯誤輸出，可省), "gold"(正確答案，事後由 F10 補)}。
    用途：(input→gold) 是 CSC/BERT 微調最直接的訓練對；output 是 hard negative，供錯誤分析/對比學習。
    用 JSONL（同 history.jsonl）：欄位具名、免分隔符跳脫、可直接 datasets.load_dataset('json', ...) 載入。"""
    os.makedirs(LOG_DIR, exist_ok=True)
    rec = {"ts": datetime.datetime.now().isoformat(timespec="seconds"), "input": problem}
    if wrong:
        rec["output"] = wrong
    with open(ERROR_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def append_correct_answer(correct: str) -> bool:
    """把『正確答案』補進 error_cases.jsonl **最後一筆**的 `gold` 欄。
    流程：自動記下失敗案例(input + 模型錯誤 output)後，使用者手動改對，再用這個補上 gold，
    湊成 (input, output, gold) 的完整難例——(input→gold) 即微調訓練對。
    重複呼叫＝覆寫更新 gold（讓使用者可再修正答案）。
    回傳 True=已補上；False=沒有可補的紀錄（檔案不存在或全空）。"""
    if not os.path.exists(ERROR_FILE):
        return False
    with open(ERROR_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    idx = next((i for i in range(len(lines) - 1, -1, -1) if lines[i].strip()), None)
    if idx is None:
        return False
    rec = json.loads(lines[idx])
    rec["gold"] = correct                       # 重複按就覆寫更新 gold
    lines[idx] = json.dumps(rec, ensure_ascii=False) + "\n"
    with open(ERROR_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return True
