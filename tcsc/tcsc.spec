import glob
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(SPEC)), ".."))
sys.path.insert(0, ROOT)

_pkg_bin = os.path.join(os.path.expanduser("~"), "anaconda3", "envs", "pkg", "Library", "bin")
if os.path.isdir(_pkg_bin):
    os.environ["PATH"] = _pkg_bin + os.pathsep + os.environ.get("PATH", "")

from tcsc import config as _cfg
from tcsc.ui import iconart as _icon

_PACK = os.path.join(ROOT, "build", "data.pack")
if not os.path.exists(_PACK) or not os.path.exists(os.path.join(ROOT, "tcsc", "_datakey.py")):
    raise SystemExit("找不到加密包（build/data.pack）或它的鑰匙（_datakey.py）：要先做加密包才能打包")
_datas = [(_PACK, "."), (os.path.join(ROOT, "LICENSE"), "."), (os.path.join(ROOT, "THIRD-PARTY-NOTICES.md"), ".")]
for key in ("proposer", "judge", "disc_judge", "detector", "vocab"):
    f = os.path.join(ROOT, "models", _cfg.ENGINE[key])
    if os.path.exists(f):
        _datas.append((f, "models"))

a = Analysis(
    [os.path.join(ROOT, "tcsc", "main.py")],
    pathex=[ROOT],
    binaries=collect_dynamic_libs("onnxruntime"),
    datas=_datas + collect_data_files("onnxruntime"),
    hiddenimports=["onnxruntime", "onnxruntime.capi", "onnxruntime.capi._pybind_state",
                   "pystray._win32", "numpy", "tkinter", "tkinter.font",
                   "tcsc.ui.dictquery", "tcsc.ui.managewords", "tcsc._datakey"],
    hookspath=[], runtime_hooks=[], excludes=["torch", "transformers", "matplotlib", "scipy", "pandas",
                                              "yaml", "win32pdh"],
    noarchive=False,
)
_DROP_BIN = ("PIL/_avif", "PIL/_webp")
a.binaries = [b for b in a.binaries if not b[0].replace("\\", "/").startswith(_DROP_BIN)]
_DROP_ORT = ("onnxruntime/datasets", "onnxruntime/tools", "onnxruntime/Privacy.md")
a.datas = [d for d in a.datas if not d[0].replace("\\", "/").startswith(_DROP_ORT)]
_DROP = ("_tcl_data/tzdata", "_tcl_data/msgs", "_tk_data/msgs", "_tk_data/images", "_tk_data/demos")
a.datas = [d for d in a.datas if not d[0].replace("\\", "/").startswith(_DROP)]

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="tcsc", debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          icon=_icon.write_ico(os.path.join(ROOT, "build", "tcsc.ico")))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="tcsc")
