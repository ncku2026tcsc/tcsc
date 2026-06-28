# 第三方元件與授權（Third-Party Notices）

本專案（繁中自動選字 / TCSC）的原始碼以 **GPL-3.0** 釋出。發布物（原始碼、打包的 `tcsc.exe`、zip）內含或依賴下列第三方元件，各自授權如下。散布本專案時請保留本檔。

> ⚠️ **copyleft 關鍵**：本專案部分元件（包含中文 BERT 相關模型/函式庫）採用 GPL-3.0，因此整個發布物採 GPL-3.0。未來若將其替換為寬鬆授權版本（例如 Apache-2.0 的中文 BERT），方有機會把整個專案轉為較寬鬆授權（如 MIT）。詳見 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 模型（隨 exe 打包散布）

### ckiplab/bert-base-chinese — **GPL-3.0**
- 用途：句子級「選最順的字」的 BERT MLM 評審。
- 來源：<https://huggingface.co/ckiplab/bert-base-chinese>
- 對應源碼：重建腳本 `scripts/download_model.py`、`scripts/export_onnx.py`、`scripts/quantize_onnx.py`（下載原模型 → 匯出 ONNX → int8 量化）。

## 字典 / 詞頻資料（隨程式散布）

### McBopomofo 小麥注音輸入法 — **MIT**
- 用途：`data/BPMFBase.txt`（字→注音）、`data/BPMFMappings.txt`（詞→注音序列）、`data/phrase.occ`（詞頻）。
- 來源：<https://github.com/openvanilla/McBopomofo>
- 讀音資料另衍生自「注音 IVS 字型規格／國字讀音整理檔」，以 **Apache-2.0** 釋出（見 McBopomofo `ACKNOWLEDGEMENTS.md`）。

## Python 套件（打包進 exe 或執行時相依）

| 套件 | 授權 | 用途 |
|---|---|---|
| pystray | **LGPL-3.0** | 系統匣圖示／選單 |
| onnxruntime | MIT | ONNX 推論（exe 引擎） |
| NumPy | BSD-3-Clause | 數值運算 |
| Pillow (PIL) | HPND（MIT 式寬鬆） | 產生圖示點陣圖 |
| pyperclip | BSD-3-Clause | 剪貼簿存取 |
| Tcl/Tk | BSD 式 | F6 輸入框（tkinter） |
| PyTorch（每日版） | BSD-3-Clause | BERT 推論 |
| Transformers（每日版） | Apache-2.0 | 載入模型／分詞器 |

> LGPL-3.0 的 **pystray**：與 GPL-3.0 相容。散布時請一併保留其授權條文、並讓使用者能以自備版本替換（提供原始碼即滿足）。

---

## 各授權全文取得
- GPL-3.0：<https://www.gnu.org/licenses/gpl-3.0.txt>（本 repo 的 `LICENSE`）
- LGPL-3.0：<https://www.gnu.org/licenses/lgpl-3.0.txt>
- Apache-2.0：<https://www.apache.org/licenses/LICENSE-2.0.txt>
- 各套件授權亦隨打包輸出於 `dist/tcsc/_internal/*.dist-info/`。
