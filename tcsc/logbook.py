# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import datetime
import json
import os
import sys
import threading

from . import paths
from . import vault
from . import version


ENGINE_DESC = None


def _engine_tag() -> str:
    try:
        from . import settings
        app = "exe" if getattr(sys, "frozen", False) else "src"
        return f"{version.LABEL.replace(' ', '-')}/{ENGINE_DESC or settings.get('engine_model', 'base')}/{app}"
    except Exception:
        return version.LABEL.replace(' ', '-')
LOG_DIR = paths.LOGS
LOG_FILE = os.path.join(LOG_DIR, "history.jsonl")
ERROR_FILE = os.path.join(LOG_DIR, "error_cases.jsonl")
GARBLE_FILE = os.path.join(LOG_DIR, "garble_cases.jsonl")


_lock = threading.RLock()
_mem: dict = {}


def _read(path) -> list:
    with _lock:
        try:
            with open(path, encoding="utf-8") as f:
                raw = [ln.rstrip("\n") for ln in f if ln.strip()]
        except OSError:
            return []
        prev = _mem.get(path)
        memo = dict(zip(prev[0], prev[1])) if prev else {}
        plain = [memo[r] if r in memo else vault.unseal(r) for r in raw]
        _mem[path] = (raw, plain)
        return [p for p in plain if p is not None]


def _write(path, plains) -> None:
    with _lock:
        prev = _mem.get(path)
        memo = {p: r for r, p in zip(prev[0], prev[1]) if p is not None and vault.is_sealed(r)} if prev else {}
        raw = []
        for p in plains:
            r = memo.get(p)
            if r is None:
                r = vault.seal(p)
                if vault.unseal(r) != p:
                    raise OSError("紀錄加密後解不回原文，沒有寫入")
            raw.append(r)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("".join(r + "\n" for r in raw))
        os.replace(tmp, path)
        _mem[path] = (raw, list(plains))


def _add(path, plain) -> None:
    with _lock:
        r = vault.seal(plain)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(r + "\n")
        prev = _mem.get(path)
        if prev is not None:
            prev[0].append(r)
            prev[1].append(plain)


def _recording() -> bool:
    if _dev_mode():
        return False
    try:
        from . import settings
        return bool(settings.get("log_on", True))
    except Exception:
        return True


def detail() -> bool:
    try:
        from . import settings
        return bool(settings.get("log_detail", False))
    except Exception:
        return False


def records(path) -> list:
    out = []
    for p in _read(path):
        try:
            out.append(json.loads(p))
        except Exception:
            continue
    return out


def _when(rec) -> str:
    return str(rec.get("ts") or rec.get("id") or "")


def migrate(keep_days=None) -> dict:
    from . import settings
    days = settings.get("log_keep_days", 30) if keep_days is None else keep_days
    cut = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat(timespec="seconds") if days else ""
    out = {}
    for path in (LOG_FILE, ERROR_FILE, GARBLE_FILE):
        if not os.path.exists(path):
            continue
        with _lock:
            plains = _read(path)
            raw = _mem.get(path, ([], []))[0]
            keep = plains
            if cut:
                keep = []
                for p in plains:
                    try:
                        w = _when(json.loads(p))
                    except Exception:
                        w = ""
                    if not w or w >= cut:
                        keep.append(p)
            redo = len(keep) != len(plains) or any(not vault.is_sealed(r) for r in raw)
            if redo:
                _write(path, keep)
            out[os.path.basename(path)] = (len(plains), len(keep), redo)
    return out


def clear_all() -> int:
    n = 0
    with _lock:
        for path in (LOG_FILE, ERROR_FILE, GARBLE_FILE):
            try:
                os.remove(path)
                n += 1
            except OSError:
                pass
            _mem.pop(path, None)
    return n


def export_for_author(out_path) -> int:
    lines = ["算字大師：回報給作者的難例",
             "這份檔案是從你電腦裡的加密紀錄解出來的，只有你看得到。",
             "請先看過一遍，不想給的整段刪掉，再寄到 ncku2026tcsc@gmail.com。",
             "寄來的資料只用來改進程式，不會公開；要刪除隨時來信。", ""]
    n = 0
    for r in records(ERROR_FILE):
        lines += [f"【難例 {n + 1}】", f"原句：{r.get('input', '')}", f"第一次 F1：{r.get('output', '')}",
                  f"正解：{r.get('gold', '（沒記）')}（{'自己按 F9 記的' if r.get('gold_src') == 'manual' else '停在哪個候選'}）", ""]
        n += 1
    for r in records(GARBLE_FILE):
        lines += [f"【亂碼 {n + 1}】", f"按鍵：{r.get('input', '')}", f"轉出：{r.get('output', '')}",
                  f"最後選：{r.get('final') or r.get('output', '')}", f"正解：{r.get('gold', '（沒記）')}", ""]
        n += 1
    hist = [r for r in records(LOG_FILE) if r.get("type") == "correction"] if detail() else []
    if hist:
        lines += ["", "──── 詳細紀錄：每次改字（原句 → 改成）────", ""]
        for r in hist:
            lines.append(f"{r.get('input', '')} → {r.get('output', '')}")
            n += 1
    with open(out_path, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(lines))
    return n


TUTORIAL = False


def _dev_mode() -> bool:
    if TUTORIAL:
        return True
    try:
        import time as _t
        from . import settings
        return (bool(settings.get("dev_mode"))
                and _t.time() < float(settings.get("dev_mode_until") or 0))
    except Exception:
        return False


def _append(record: dict) -> None:
    if not (_recording() and detail()):
        return
    record = {"ts": datetime.datetime.now().isoformat(timespec="seconds"), **record}
    _add(LOG_FILE, json.dumps(record, ensure_ascii=False))


_log_ctx: dict = {}


def set_log_ctx(**kw) -> None:
    _log_ctx.clear()
    _log_ctx.update({k: v for k, v in kw.items() if v is not None})


def log_correction(input_text: str, output_text: str, changes, margin: float, **extra) -> None:
    try:
        from .ui import tutorial
        tutorial.notify("f1_ok")
    except Exception:
        pass
    rec = {
        "type": "correction",
        "input": input_text,
        "output": output_text,
        "changes": [[p, a, b] for (p, a, b) in changes],
        "margin": margin,
        "label": "unrated",
        "engine": _engine_tag(),
    }
    rec.update(_log_ctx)
    _log_ctx.clear()
    rec.update({k: v for k, v in extra.items() if v is not None})
    _append(rec)


def analyze(input_text: str, output_text: str, gold: str) -> dict:
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


def log_error_case(problem: str, wrong: str = None, engine: str = None,
                   route: str = None, grab: str = None, t_first=None) -> None:
    if not _recording():
        return
    rec = {"ts": datetime.datetime.now().isoformat(timespec="seconds"), "input": problem,
           "engine": engine or _engine_tag()}
    if wrong:
        rec["output"] = wrong
    if route:
        rec["route"] = route
    if grab:
        rec["grab"] = grab
    if t_first:
        rec["t_first"] = t_first
    _add(ERROR_FILE, json.dumps(rec, ensure_ascii=False))


def upsert_error_case(inp, output, gold, gold_src, tries, engine=None,
                      route=None, grab=None, t_first=None):
    if not _recording():
        return
    lines = _read(ERROR_FILE)
    tag = engine or _engine_tag()
    rec = {"ts": datetime.datetime.now().isoformat(timespec="seconds"),
           "input": inp, "output": output, "gold": gold, "gold_src": gold_src, "tries": tries,
           "engine": tag}
    if route:
        rec["route"] = route
    if grab:
        rec["grab"] = grab
    if t_first:
        rec["t_first"] = t_first
    idx = None
    for i in range(len(lines) - 1, -1, -1):
        try:
            old = json.loads(lines[i])
            if old.get("input") == inp and old.get("engine", tag) == tag:
                idx = i
                if old.get("t_first"):
                    rec["t_first"] = old["t_first"]
                if old.get("output") and old.get("output") != old.get("input"):
                    rec["output"] = old["output"]
                break
        except Exception:
            continue
    line = json.dumps(rec, ensure_ascii=False)
    if idx is not None:
        lines[idx] = line
    else:
        lines.append(line)
    _write(ERROR_FILE, lines)


def last_error_case():
    try:
        lines = _read(ERROR_FILE)
        return json.loads(lines[-1]) if lines else None
    except Exception:
        return None


def case_matching(gold: str):
    for ln in reversed(_read(ERROR_FILE)):
        try:
            rec = json.loads(ln)
        except Exception:
            continue
        if gold_matches(gold, rec.get("input", "")):
            return rec
    return None


def case_for_input(inp: str):
    if not inp:
        return None
    for ln in reversed(_read(ERROR_FILE)):
        try:
            rec = json.loads(ln)
        except Exception:
            continue
        if rec.get("input") == inp:
            return rec
    return None


def gold_matches(gold: str, src: str) -> bool:
    gold = (gold or "").strip()
    src = (src or "").strip()
    return bool(gold) and bool(src) and len(gold) == len(src)


def append_correct_answer(correct: str, src: str = "manual", tries=None, engine=None,
                          route=None, grab=None, problem=None):
    if not _recording():
        return False
    lines = _read(ERROR_FILE)
    if not lines:
        return False
    tag = engine or _engine_tag()
    target = None
    for i in range(len(lines) - 1, -1, -1):
        if not lines[i].strip():
            continue
        try:
            rec = json.loads(lines[i])
        except Exception:
            continue
        if problem is not None:
            if rec.get("input") == problem and rec.get("engine", tag) == tag:
                target = i
                break
            continue
        if gold_matches(correct, rec.get("input", "")) and rec.get("engine", tag) == tag:
            target = i
            break
    if target is None:
        return "notfound"
    rec = json.loads(lines[target])
    rec["gold"] = correct
    rec["gold_src"] = src
    if tries is not None:
        rec["tries"] = tries
    if route:
        rec["route"] = route
    if grab:
        rec["grab"] = grab
    lines[target] = json.dumps(rec, ensure_ascii=False)
    _write(ERROR_FILE, lines)
    return True


def log_garble(rec: dict) -> None:
    if not _recording():
        return
    rec.setdefault("id", datetime.datetime.now().isoformat(timespec="seconds"))
    lines = _read(GARBLE_FILE)
    line = json.dumps(rec, ensure_ascii=False)
    for i in range(len(lines) - 1, max(-1, len(lines) - 51), -1):
        try:
            if json.loads(lines[i]).get("id") == rec["id"]:
                lines[i] = line
                break
        except Exception:
            continue
    else:
        lines.append(line)
    _write(GARBLE_FILE, lines)


def remove_last_error():
    lines = _read(ERROR_FILE)
    if not lines:
        return None
    last = lines.pop()
    _write(ERROR_FILE, lines)
    try:
        import json as _json
        return _json.loads(last)
    except Exception:
        return {"raw": last[:80]}
