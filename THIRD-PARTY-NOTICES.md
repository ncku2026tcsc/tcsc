# 第三方元件與授權（Third-Party Notices）

算字大師（TCSC）以 **GPL-3.0** 釋出。發布物內含或依賴下列第三方元件。散布時請保留本檔。

## 模型（`models\`）

| 檔案 | 來源 | 授權 |
|---|---|---|
| `proposer.onnx` | 衍生自 [ckiplab/bert-base-chinese](https://huggingface.co/ckiplab/bert-base-chinese) | **GPL-3.0** |
| `judge.onnx` | 衍生自 ckiplab/bert-base-chinese | **GPL-3.0** |
| `judge_disc.onnx` | 衍生自 ckiplab/bert-base-chinese | **GPL-3.0** |
| `detector.onnx` | 衍生自 [hfl/chinese-electra-180g-small-discriminator](https://huggingface.co/hfl/chinese-electra-180g-small-discriminator) | Apache-2.0 |
| `vocab.txt` | ckiplab/bert-base-chinese | GPL-3.0 |

## 字典與詞頻（`data\`）

- 小麥注音 McBopomofo（MIT）：`BPMFBase.txt`、`BPMFMappings.txt`、`phrase.occ`。<https://github.com/openvanilla/McBopomofo>
  讀音資料另衍生自「注音 IVS 字型規格／國字讀音整理檔」（Apache-2.0，見 McBopomofo `ACKNOWLEDGEMENTS.md`）。
- 其餘資料檔為本專案整理，著作權保留，不在 GPL-3.0 授權範圍內（見 [data/README.md](data/README.md)）；統計類資料只含數字，不含原始文章。

## 打包進 exe 的程式元件

| 元件 | 授權 |
|---|---|
| Python 3.11 與標準函式庫 | PSF-2.0 |
| onnxruntime | MIT |
| NumPy（含 OpenBLAS 等） | BSD-3-Clause 等 |
| Pillow | MIT-CMU（HPND） |
| pystray | LGPL-3.0 |
| pyperclip | BSD-3-Clause |
| six | MIT |
| typing_extensions | PSF-2.0 |
| Tcl/Tk（tkinter） | TCL（BSD 式） |
| OpenSSL | Apache-2.0 |
| libffi、expat | MIT |
| zlib | Zlib |
| bzip2 | bzip2 授權（BSD 式） |
| liblzma（xz） | 0BSD |
| Microsoft Visual C++ 執行階段、UCRT | Microsoft 可再散布授權 |
| PyInstaller bootloader | GPL-2.0＋bootloader 例外 |

每個元件的授權全文都在 zip 裡 `tcsc\licenses\`（打包時依實際收進去的元件自動收集），清單見該資料夾的 `README.md`。
