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

from .userpaths import logs_dir
LOG_DIR = logs_dir()   # exe → %APPDATA%\tcsc\logs；原始碼 → 專案 logs/（重建不洗掉）
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


def upsert_error_case(inp, output, gold, gold_src, tries):
    """寫入/更新一筆難例（新版 schema）。以 input **完全相符**往回找最近一筆：找到→更新、無→新增。
    欄位：input(原 raw 輸入)、output(**第一次 F1 的結果**，永不變)、gold(正解)、
          gold_src("auto"=模型最後答案／"manual"=F9 手動)、tries(F1/F2/F4/F5 按了幾次)。
    規則：tries>=2 才寫（第一次 F1 就改對的不記）；只有 manual 觸發學習（在呼叫端）。"""
    os.makedirs(LOG_DIR, exist_ok=True)
    lines = open(ERROR_FILE, encoding="utf-8").readlines() if os.path.exists(ERROR_FILE) else []
    rec = {"ts": datetime.datetime.now().isoformat(timespec="seconds"),
           "input": inp, "output": output, "gold": gold, "gold_src": gold_src, "tries": tries}
    idx = None
    for i in range(len(lines) - 1, -1, -1):
        try:
            if json.loads(lines[i]).get("input") == inp:
                idx = i
                break
        except Exception:
            continue
    line = json.dumps(rec, ensure_ascii=False) + "\n"
    if idx is not None:
        lines[idx] = line
    else:
        lines.append(line)
    with open(ERROR_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)


def last_error_case():
    """回傳 error_cases.jsonl 最後一筆 dict（含 input/output/gold），無則 None。供自動學詞 diff 用。"""
    if not os.path.exists(ERROR_FILE):
        return None
    try:
        with open(ERROR_FILE, "r", encoding="utf-8") as f:
            lines = [ln for ln in f if ln.strip()]
        return json.loads(lines[-1]) if lines else None
    except Exception:
        return None


def case_matching(gold: str):
    """回傳『input 與此 gold 同長度+同音』的最近一筆 dict（即 append_correct_answer 會寫進去的那筆），
    無則 None。供自動學詞對齊同一筆的 output（而非盲讀最後一筆）。"""
    if not os.path.exists(ERROR_FILE):
        return None
    try:
        with open(ERROR_FILE, "r", encoding="utf-8") as f:
            lines = [ln for ln in f if ln.strip()]
    except Exception:
        return None
    for ln in reversed(lines):
        try:
            rec = json.loads(ln)
        except Exception:
            continue
        if gold_matches(gold, rec.get("input", "")):
            return rec
    return None


def gold_matches(gold: str, src: str) -> bool:
    """gold 是否對得上 src：**只看同長度**。
    為何不過濾讀音：一個字本就有多種讀音、讀音資料也未必齊全，逐字比同音會誤殺真正的修正
    （例：乏 ㄈㄚˊ vs 發 ㄈㄚ 被當不同音，但使用者就是要改成「發」）。
    長度才是關鍵防呆：長度不同＝不是同一句的逐字修正（多半是改寫/移到別句）→ 拒，避免寫進不相干紀錄。"""
    gold = (gold or "").strip()
    src = (src or "").strip()
    return bool(gold) and bool(src) and len(gold) == len(src)


def append_correct_answer(correct: str, src: str = "manual"):
    """把『正確答案』補進對應的難例：**往回找 input 與此 gold 同長度+同音的那一筆**，補上 `gold`。
    為何用搜尋而非「最後一筆」：F9 補 gold 是重讀游標處的字，若你已改寫/移到別句，最後一筆未必對得上；
    用 (input↔gold 同音) 找正確對象，長度不符者一律跳過 → **絕不會把別句的 gold 寫進不相干的紀錄**。
    重複按＝覆寫更新該筆 gold。
    src：gold 來源標註，寫進 `gold_src` 欄——"manual"=使用者按 F9 自己補；"auto"=自動補（之後做）。
        用途：之後拿 error_cases 當訓練資料時，可區分人工驗證(高可信)與自動產生(低可信)的 gold。
    回傳 True=已補上；False=檔案空/不存在；"notfound"=找不到長度相符的同音原題（防呆，不寫、不亂建）。"""
    if not os.path.exists(ERROR_FILE):
        return False
    with open(ERROR_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    target = None
    for i in range(len(lines) - 1, -1, -1):          # 往回找最近一筆「同長度+同音」的原題
        if not lines[i].strip():
            continue
        try:
            rec = json.loads(lines[i])
        except Exception:
            continue
        if gold_matches(correct, rec.get("input", "")):
            target = i
            break
    if target is None:
        return "notfound"                            # 長度不符/對不上 → 一律不寫
    rec = json.loads(lines[target])
    rec["gold"] = correct                            # 重複按就覆寫更新 gold
    rec["gold_src"] = src                            # 標 gold 來源：manual / auto
    lines[target] = json.dumps(rec, ensure_ascii=False) + "\n"
    with open(ERROR_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return True
