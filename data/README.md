# data／詞庫資料

詞庫資料（字表、詞表、詞頻、詞庫包、出廠保送票）**不開源**，以加密包 `data.pack` 隨 `tcsc_portable.zip` 發布。

- 程式碼依 GPL-3.0 開源（見上層 [LICENSE](../LICENSE)）；詞庫資料是另外的作品，著作權由作者保留，不在 GPL 授權範圍內。
- 字表與基礎詞表衍生自 [小麥注音 McBopomofo](https://github.com/openvanilla/McBopomofo)（MIT），其授權聲明見 [THIRD-PARTY-NOTICES.md](../THIRD-PARTY-NOTICES.md)。
- 程式讀資料的入口是 `tcsc/datafs.py`：有 `data.pack` 就讀加密包，沒有就讀這個資料夾裡的明文檔（格式見 `tcsc/engine/lexicon.py`）。
