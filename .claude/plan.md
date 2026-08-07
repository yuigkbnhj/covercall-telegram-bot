# Covered Call 機會掃描 + 倉位追蹤 系統

## 目標
針對長期持有的股票清單，每天掃描 option chain，找出符合條件的 covered call 機會，並透過 Telegram 通知。同時追蹤已開倉的 covered call，到期或獲利已達門檻時提醒 roll。全程在 GitHub Actions 免費額度內運行，不需自架伺服器。

## 整體架構

```
GitHub repo (private)
├── config/
│   ├── settings.yaml       # 篩選門檻、風險利率、roll規則
│   └── holdings.yaml       # 長期持有的股票代號清單
├── data/
│   ├── positions.yaml      # 目前開倉的covered call (ticker/strike/expiry/premium/opened_date)
│   └── telegram_offset.txt # 已處理過的Telegram update_id，避免重複處理指令
├── src/
│   ├── data_provider.py    # 包裝yfinance：現價、option chain、ex-div日期、下次財報日
│   ├── greeks.py           # Black-Scholes反推delta (yfinance沒有現成delta欄位)
│   ├── screener.py         # 核心篩選+排序邏輯
│   ├── positions.py        # 讀寫positions.yaml、roll判斷邏輯
│   ├── telegram_bot.py     # send_message / get_updates / 指令解析
│   ├── scan.py             # entrypoint: 每日機會掃描 + roll提醒 → 發Telegram
│   └── poll.py             # entrypoint: 讀取Telegram新指令 → 更新positions.yaml → commit
├── .github/workflows/
│   ├── daily_scan.yml      # 每日美股收盤後跑一次 scan.py
│   └── poll_commands.yml   # 每15分鐘跑一次 poll.py
├── requirements.txt
└── README.md                # 建置步驟(建立Telegram bot、設定GitHub secrets等)
```

資料來源：`yfinance`（免費、無需API key）。已知限制：15分鐘延遲報價、無現成delta（用Black-Scholes從IV反推）、財報/除息日期偶爾缺漏（缺漏時該檔略過時間窗排除，並在報告中標註「資料不足」，不是硬性擋掉）。

## 篩選邏輯 (`screener.py`)

對 `holdings.yaml` 裡每檔股票：
1. 抓現價、option chain（僅看 calls）、ex-dividend日期、下次財報日
2. 對每個到期日，若 `dte` 落在 `[dte_min, dte_max]`，抓該到期日的calls
3. 只看價外(strike > 現價)的call，用IV算出每個strike的delta
4. 保留 `delta` 落在 `[delta_min, delta_max]` 的合約
5. 用 `bid`（沒有bid就用lastPrice）算年化報酬率：`(premium/現價) * (365/dte)`
6. 篩掉低於 `min_annualized_return` 的
7. 排除到期日落在「除息日前X天」或「財報公布前X天」視窗內的合約（天數在settings.yaml設定，預設3天）
8. 依年化報酬率排序，每檔股票取前1-3名進報告

## 倉位追蹤與Roll提醒 (`positions.py`)

`positions.yaml` 每筆記錄：`ticker, strike, expiry, premium_sold, opened_date`

每日掃描時對每筆open position：
- 抓目前該合約市價
- 若 `dte <= roll_dte_threshold`（預設5天）→ 標記「即將到期，考慮roll」
- 若 目前市價 `<= premium_sold * (1 - roll_profit_capture)`（預設50%，即已賺到一半利潤）→ 標記「獲利已達門檻，考慮roll/回補」
- 兩者都會在Telegram訊息中列出，附上建議動作文字

## Telegram Bot (`telegram_bot.py`)

指令（在 `/poll_commands.yml` 每15分鐘的執行週期內被處理，非即時）：
- `/add TICKER STRIKE EXPIRY PREMIUM` — 記錄新開的covered call倉位
- `/close TICKER STRIKE EXPIRY` — 關閉倉位（到期/被assign/買回）
- `/list` — 列出目前所有open positions
- `/holdings_add TICKER` / `/holdings_remove TICKER` — 維護長期持股清單
- `/help` — 顯示指令說明

`poll.py` 讀取新指令、更新對應yaml、`git commit & push` 回repo（用GitHub Actions內建的 `GITHUB_TOKEN`，workflow需開 `contents: write` 權限）。

## GitHub Actions

- `daily_scan.yml`：cron `0 21 * * 1-5`（UTC 21:00，約美股收盤後，對應台灣時間05:00），跑 `python src/scan.py`，透過secrets傳入 `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`
- `poll_commands.yml`：cron `*/15 * * * *`，跑 `python src/poll.py`，若有更新則commit回repo
- 兩個workflow都需要 `permissions: contents: write`

## Settings 預設值 (`settings.yaml`)

```yaml
delta_min: 0.15
delta_max: 0.30
dte_min: 21
dte_max: 45
min_annualized_return: 0.08
risk_free_rate: 0.04
exclude_window_days: 3        # 除息日/財報日前幾天內的到期不建議
roll_dte_threshold: 5
roll_profit_capture: 0.50
```

## 實作順序

1. 專案骨架 + `requirements.txt` + `config/settings.yaml`、`config/holdings.yaml`（先放1-2檔測試股票）
2. `data_provider.py`：現價、option chain、ex-div、財報日的yfinance包裝，含基本錯誤處理
3. `greeks.py`：Black-Scholes delta計算
4. `screener.py`：核心篩選邏輯 + 單元測試（用固定假資料驗證年化報酬率/delta篩選正確）
5. `positions.py`：positions.yaml讀寫 + roll判斷邏輯 + 測試
6. `telegram_bot.py`：send_message/get_updates/指令解析
7. `scan.py`、`poll.py` 兩個entrypoint串接以上模組
8. 本機用你的Telegram bot token手動測試整條流程（scan一次、送指令、poll一次）
9. 寫 `.github/workflows/*.yml`
10. README：如何建立Telegram bot取得token、如何在GitHub repo設定secrets、如何初次push repo並啟用Actions
11. 你在GitHub建好私有repo並設定好secrets後，push上去實際跑一次驗證整條流程

## 需要你事後提供才能實際跑起來的東西

- 一個Telegram bot token（跟 @BotFather 申請，我會在README寫步驟）
- 你的Telegram chat id
- 一個GitHub私有repo（建議private，因為裡面會存你的持股/倉位資料）

這些都會在README列步驟，不需要現在決定。
