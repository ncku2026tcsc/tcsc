# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/tcsc2026/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
DEFAULT = "default"

CONFIGS = {
    "default": ("標準", "base", "judge.onnx"),
}
ORDER = ("default",)

PROPOSER_FILES = {
    "base": "proposer.onnx",
}


def current():
    from .. import settings
    c = settings.get("engine_config") or DEFAULT
    return c if c in CONFIGS else DEFAULT


def label(key):
    return CONFIGS[key][0] if key in CONFIGS else (key or "")


def bundle_files():
    files = set()
    for _lbl, pm, jf in CONFIGS.values():
        files.add(PROPOSER_FILES[pm])
        files.add(jf)
    return sorted(files)
