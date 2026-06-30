# 繁體中文自動選字 v2.63

> ## ⬇️ [**點此下載執行檔（Windows，免安裝免設定）**](https://github.com/ncku2026tcsc/tcsc/releases/latest)
> 解壓_v2.63.zip後直接執行 `tcsc.exe`，常駐系統匣。一般使用者看下面「怎麼用」就夠了。
>

## 怎麼用

**🟢 打開後它在哪？**
雙擊 `tcsc.exe` **不會跳出視窗**——它縮到螢幕**右下角的系統匣**（時鐘旁邊，可能要點「∧」往上的箭頭才看得到）。圖示**變綠色**就代表好了，之後一直在背景待命，你正常打字就好。

**✍️ 開始用**
在任何能打字的地方，打完一段話後：
1. 先按 **Enter**，把輸入法自己的選字框關掉。
2. 按 **F1**——它會抓你前面那段，看有沒有同音打錯，幫你改好。
3. 改的不是你要的字？**再按 F1** 換下一個（一直按可以看 **10 個**選項）。

**🤔 還是不滿意？**
- 一次沒改好：先按 F1 挑到比較順的，按 **F2 重算（迭代）**當新起點，再按 F1 慢慢挑。
- 想反悔：按 **F3**，變回你原本打的字。

**⌨️ 每個鍵**
F1 改字/換選項・F2 重算（迭代）・F3 還原・F4 改前 30 字・F5 只改反白的字・F6 開輸入框・F7 學會這個詞・F9 記成正解・F10 關熱鍵
（**F2 重算是通用的**：F1／F4／F5 做完哪個，按 F2 就重算哪個。系統匣右鍵有完整「使用說明」。）

**🖥️ 在終端機 / CLI**（claude code、cmd、PowerShell、MobaXterm…）
這些地方沒辦法就地改字，請按 **F6** 開一個小輸入框，在框裡打字＋改字，改好按 Enter 送回原視窗。

## 資料與隱私

- **只在你的電腦本機執行，不收集、不上傳任何資料。** 沒有雲端、沒有追蹤。
- 改錯歷史、難例都存在你自己電腦的 `logs\` 裡，給你參考。
- 若想協助改進本程式，歡迎把 `logs\error_cases.jsonl` 寄給我（系統匣右鍵「聯繫作者」就有信箱）

## ⭐ 執行

**獨立 exe 版（推薦，免裝環境）**：下載 Release 的 `繁中自動選字.zip` → 解壓 → 執行 `tcsc.exe`，常駐系統匣。

**每日版（原始碼，需 torch + transformers + GPU）**：
```powershell
雙擊 啟動注音校正.bat          # 背景常駐系統匣；或 python tray_app.py
```
首次執行自動下載模型 `ckiplab/bert-base-chinese`。

**用法**：在任意輸入欄打注音、選到同音錯字 → 按 **F1** 自動選最順的字（再按 F1 換候選）；**F6** 開輸入框、**F10** 記錄改錯。系統匣右鍵可開關「F6 自動切注音 / 自動按 Shift / 開機自動啟動」。


## 程式結構

```
app_exe.py            獨立 exe 進入點（ONNX 引擎，無 torch）
tray_app.py           每日版進入點（torch + transformers）
csc/
  select_corrector.py        torch 句子級選字引擎（PLL + 詞頻先驗 + 同音守門 + 多音字收斂）
  select_corrector_onnx.py   ONNX 版引擎（功能等同，供 exe）
  segmenter.py               自建讀音斷詞器（DAG，不靠 jieba）
  phonetics.py / wordphon.py 字級/詞級同音候選（McBopomofo 詞庫，含聲調純繁體）
  reading_filter.py          多音字收斂 + 句尾語助詞守門
  winkeys / hotkey / logbook / settings / autostart / crashlog / onnx_engine / textutil / userdict
data/                 BPMFBase / BPMFMappings / phrase.occ（McBopomofo 詞庫）
scripts/              重建模型：download_model → export_onnx → quantize_onnx（GPL 對應源碼）
build_exe.ps1 / ZhuyinFix.spec   打包成 exe
```

資料來源：**McBopomofo 小麥注音輸入法** <https://github.com/openvanilla/McBopomofo>（詞庫，MIT）。模型：**ckiplab/bert-base-chinese**（GPL-3.0）。


### 環境重建見檔末
- BERT/GUI：base 環境（py3.13 + transformers 5.9 + torch 2.11 cu128 + tkinter），模型 `ckiplab/bert-base-chinese` 首次自動下載。
- LLM 對照：`csc` 環境（py3.12 + llama-cpp-python cu124；cu124 wheel 需從 base 的 torch\lib 複製 cudart64_12/cublas64_12/cublasLt64_12.dll 進 llama_cpp\lib）。
- 含中文腳本一律存 UTF-8 檔執行，勿用行內 `python -c "中文"`（cp950 會搞爛）。

## 授權 License

本專案以 **GNU General Public License v3.0（GPL-3.0）** 釋出。

```
Copyright (C) 2026 tcsc-dev (https://github.com/ncku2026tcsc/tcsc)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
```

- 完整授權條文見 [`LICENSE`](LICENSE)（GPL-3.0 官方全文）。
- 第三方元件與授權見 [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md)。
- 貢獻條款（含未來轉授權的輕量 CLA）見 [`CONTRIBUTING.md`](CONTRIBUTING.md)。

**為什麼是 GPL-3.0**：本專案部分相依元件（中文 BERT 相關模型/函式庫）採 GPL-3.0，故整個發布物採 GPL-3.0。詞庫來自 **McBopomofo**（MIT）。未來若將其替換為寬鬆授權版本，方有機會轉為 MIT。

## 使用與散布

本專案以 GPL-3.0 釋出，歡迎自由使用、修改、散布。**散布或製作衍生作品時，請依授權保留著作權聲明與 `LICENSE`，並標註原始來源連結（本專案 GitHub：<https://github.com/ncku2026tcsc/tcsc>）。** 若於研究、作品或產品中使用，亦歡迎註明出處。
