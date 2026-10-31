# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/tcsc2026/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
from .. import paths


def user_data_dir() -> str:
    paths.user("")
    return paths.USER


def logs_dir() -> str:
    paths.log("")
    return paths.LOGS


def userforce_path() -> str:
    return paths.user("userforce.txt")


def userwords_path() -> str:
    return paths.user("userwords.txt")


def commonwords_path() -> str:
    return paths.user("words_common.tsv")
