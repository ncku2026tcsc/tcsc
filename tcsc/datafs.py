# -*- coding: utf-8 -*-
# 算字大師（TCSC）
# Copyright (C) 2026 tcsc-dev  <https://github.com/tcsc2026/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
import fnmatch
import hashlib
import io
import os
import secrets
import zipfile

from . import paths

PACK_NAME = "data.pack"
MAGIC = b"TCSCPK1\0"
_EXTS = (".txt", ".tsv", ".occ")
_SKIP = ("words_common.tsv", "userforce.txt", "userwords.txt", "settings.json")
_zip = None
_loaded = False


def _xor(data, key, nonce):
    ks = hashlib.shake_256(key + nonce).digest(len(data))
    return (int.from_bytes(data, "little") ^ int.from_bytes(ks, "little")).to_bytes(len(data), "little")


def shipped_names(src):
    out = []
    for root, _dirs, files in os.walk(src):
        rel = os.path.relpath(root, src).replace("\\", "/")
        if rel not in (".", "vocab", "escort"):
            continue
        for f in files:
            if not f.endswith(_EXTS) or f in _SKIP or ".v" in f or f.endswith(("_shipped.txt", ".pre_fix")):
                continue
            out.append(f if rel == "." else f"{rel}/{f}")
    return sorted(out)


def build(src, out_path, key):
    names = shipped_names(src)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            z.write(os.path.join(src, n), n)
    nonce = secrets.token_bytes(16)
    with open(out_path, "wb") as f:
        f.write(MAGIC + nonce + _xor(buf.getvalue(), key, nonce))
    return names


def read_pack(pack_path, key):
    raw = open(pack_path, "rb").read()
    if raw[:len(MAGIC)] != MAGIC:
        raise ValueError("data.pack 格式不對")
    nonce = raw[len(MAGIC):len(MAGIC) + 16]
    return zipfile.ZipFile(io.BytesIO(_xor(raw[len(MAGIC) + 16:], key, nonce)))


def _load():
    global _zip, _loaded
    if _loaded:
        return
    _loaded = True
    pack = os.environ.get("TCSC_PACK") or os.path.join(paths.ROOT, PACK_NAME)
    if not os.path.exists(pack):
        return
    from . import _datakey
    _zip = read_pack(pack, _datakey.KEY)


def packed():
    _load()
    return _zip is not None


def exists(name):
    _load()
    if _zip is not None:
        try:
            _zip.getinfo(name)
            return True
        except KeyError:
            return False
    return os.path.exists(paths.data(name))


def open_text(name, encoding="utf-8"):
    _load()
    if _zip is not None:
        try:
            data = _zip.read(name)
        except KeyError:
            raise FileNotFoundError(name)
        return io.TextIOWrapper(io.BytesIO(data), encoding=encoding, errors="replace")
    return io.open(paths.data(name), encoding=encoding)


def glob(pattern):
    _load()
    if _zip is not None:
        return sorted(n for n in _zip.namelist() if fnmatch.fnmatchcase(n, pattern))
    import glob as _g
    base = paths.DATA
    return sorted(os.path.relpath(p, base).replace("\\", "/") for p in _g.glob(os.path.join(base, pattern)))


def mtime(name):
    _load()
    if _zip is not None:
        return 0.0
    try:
        return os.path.getmtime(paths.data(name))
    except OSError:
        return None


def new_key():
    return secrets.token_bytes(32)
