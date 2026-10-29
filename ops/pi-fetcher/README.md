# 樹莓派 www 取源器（#393 WP3）

住宅出口代取 `www.cpbl.com.tw` 原始回應。VPS 給清單（manifest），樹莓派照清單取回原文，
打包成 bundle（`index.json`＋`responses/*.body`，每檔附 sha256），由 VPS 收件匣驗證後回放給既有解析器。

- 樹莓派⛔ 不持有 DB 憑證、⛔ 不解析、⛔ 不寫 DB（不可能成為第二個 writer）。
- 只依賴標準庫＋Playwright；⛔ 不 import 本 repo。
- 前兆 S1–S6（#382 PLAN §3）第一格就停、⛔ 不重試；之後冷卻 15–20 分鐘以上，由 PM 決定下一段。
- 只在 manifest 的 `window` 內送請求；`min_gap_s` 下限 1.0 s；單段上限 600 個請求。

manifest／bundle 格式見 `cpbl_pi_fetch.py` 模組 docstring。

## 安裝（樹莓派，64 位元 Raspberry Pi OS）

需求方許可後才做；需要 PyPI 與 Playwright 瀏覽器下載網路。

```bash
python3 -m venv ~/cpbl-fetcher/venv
~/cpbl-fetcher/venv/bin/pip install -r requirements.txt
~/cpbl-fetcher/venv/bin/playwright install --with-deps chromium
```

## 使用

```bash
# 只驗 manifest，零網路
~/cpbl-fetcher/venv/bin/python -I cpbl_pi_fetch.py manifest.json --out ~/cpbl-fetcher/out --check
# 實取（須在 PM 轉達的時段窗內）
~/cpbl-fetcher/venv/bin/python -I cpbl_pi_fetch.py manifest.json --out ~/cpbl-fetcher/out
```

離開碼：0 完整取完；3 中途停止（看 `index.json` 的 `stopped`）；65 manifest 不合法（零請求）；
75 同一 `manifest_id` 已有 bundle（不覆寫、不重跑）。

送往 VPS 收件匣的通道（受限 ssh 帳號）屬 WP4／WP5，不在本目錄。
