# 繁中自動選字（TCSC）— 新注音同音錯字校正
# Copyright (C) 2026 tcsc-dev  <https://github.com/ncku2026tcsc/tcsc>
# Licensed under the GNU General Public License v3.0 or later; see LICENSE.
"""內建的小型繁中錯字測試資料（smoke test 用）。

每筆 (src, gold) 皆為「等長、只有單字替換」，符合 CSC 標準設定。
涵蓋音近字、形近字，以及一筆無錯字句（測過度修正 / false positive）。
正式實驗請換成 SIGHAN13(繁) 或自行收集 + 合成的資料集。
"""

SAMPLES = [
    {"src": "我昨天去學效上課，老師教我們寫做文。", "gold": "我昨天去學校上課，老師教我們寫作文。"},  # 效→校, 做→作
    {"src": "這件事情我己經知道了。",               "gold": "這件事情我已經知道了。"},                # 己→已
    {"src": "請你不要在開玩笑了。",                 "gold": "請你不要再開玩笑了。"},                  # 在→再
    {"src": "他把球丟進藍框裡。",                   "gold": "他把球丟進籃框裡。"},                    # 藍→籃
    {"src": "天空中漂著朵朵白雲。",                 "gold": "天空中飄著朵朵白雲。"},                  # 漂→飄
    {"src": "我正在複習工課，準備考試。",           "gold": "我正在複習功課，準備考試。"},            # 工→功
    {"src": "這部電影非常精採。",                   "gold": "這部電影非常精彩。"},                    # 採→彩
    {"src": "今天天氣很好，適合出去散步。",         "gold": "今天天氣很好，適合出去散步。"},          # 無錯字
    {"src": "他們搭船度過河流。",                   "gold": "他們搭船渡過河流。"},                    # 度→渡
    {"src": "你必需努力才能成功。",                 "gold": "你必須努力才能成功。"},                  # 需→須
]


def error_positions(src: str, gold: str):
    """回傳 src 相對 gold 的錯字位置（假設等長）。"""
    return [i for i, (a, b) in enumerate(zip(src, gold)) if a != b]


def n_errors(src: str, gold: str) -> int:
    return len(error_positions(src, gold))
