# Covered Call 機會掃描

針對長期持有的股票，每天掃描 option chain 找covered call機會，並追蹤已開倉的倉位提醒roll。透過Telegram通知與下指令，全部跑在GitHub Actions免費額度內，不需要自己開伺服器。

## 運作方式

- **每天美股開盤後**（UTC 14:45，香港時間22:45）自動掃描 `config/holdings.yaml` 裡的股票，找出符合 `config/settings.yaml` 篩選條件的covered call機會，並檢查 `data/positions.yaml` 裡現有倉位要不要roll，結果發到你的Telegram。
- **每5分鐘**檢查Telegram有沒有新指令（`/add`、`/close`、`/list`、`/holdings_add`、`/holdings_remove`），處理後把結果寫回repo並自動commit。指令不是即時處理，最多延遲約5分鐘。
- 兩個工作都由 [cloudflare/](cloudflare/) 裡的Cloudflare Worker定時觸發（詳見下方「排程觸發層」），而不是GitHub Actions自己的`schedule:`——GitHub的排程實測會無預警地整天不自動執行。

## 篩選邏輯

- 只看價外(OTM)的call，delta落在 `delta_min`~`delta_max`（預設0.20~0.30，delta越低被assign機率越低）
- 到期天數(DTE)落在 `dte_min`~`dte_max`（預設21~45天，theta衰減效率較高的區間）
- 年化報酬率 `(premium/現價) * (365/DTE)` 要 ≥ `min_annualized_return`（預設8%）
- 排除「除息日或財報公布日發生在合約到期之前」的合約（業界慣例是無條件排除，不是可調的天數視窗），避免提早被assign去支付股息，或財報後股價跳空的風險
- delta是用Black-Scholes從yfinance的implied volatility反推的，yfinance本身沒有現成delta欄位

現有倉位每天檢查三件事：
1. 剩餘天數 ≤ `roll_dte_threshold`（預設5天）
2. 合約市價已跌到賣出價的 `1-roll_profit_capture`（預設50%）以下（代表已經賺到一半利潤，可以考慮roll或直接買回鎖定獲利）
3. delta已達 `roll_defensive_delta_threshold`（預設0.45，接近ATM）——這是時間價值的高點，也是roll up-and-out能拿到最好net credit的時間點；等到DTE用完或股價已經穿過strike才防守，時間價值已經被榨乾、buy-back成本也更貴

## 建置步驟

### 1. 建立Telegram Bot

1. 在Telegram搜尋 `@BotFather`，傳送 `/newbot`，依指示取得一個 **bot token**（格式類似 `123456:ABC-DEF...`）
2. 跟你剛建的bot隨便說一句話（例如 `/start`）
3. 瀏覽器打開 `https://api.telegram.org/bot<你的token>/getUpdates`，找到 `"chat":{"id": ...}` 裡的數字，那就是你的 **chat id**

### 2. 建立GitHub Repo

1. 在GitHub建一個新的 **private** repo（裡面會存你的持股/倉位資料，不建議公開）
2. 把這個資料夾push上去：

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin <你的repo URL>
git push -u origin main
```

### 3. 設定GitHub Secrets

Repo頁面 → Settings → Secrets and variables → Actions → New repository secret，新增兩個：

- `TELEGRAM_BOT_TOKEN`：步驟1拿到的bot token
- `TELEGRAM_CHAT_ID`：步驟1拿到的chat id

### 4. 確認Actions權限

Repo頁面 → Settings → Actions → General → Workflow permissions，選 **Read and write permissions**（`poll_commands.yml` 需要能commit回repo）。

### 5. 手動觸發測試一次

Repo頁面 → Actions → 選 "Daily covered call scan" 或 "Poll Telegram commands" → Run workflow，確認能收到Telegram訊息。

### 6. 設定排程觸發層（Cloudflare Worker）

GitHub Actions的`schedule:`觸發器不可靠（實測整天不會自動跑），所以改用Cloudflare Worker的Cron Trigger去呼叫GitHub API的`workflow_dispatch`，兩個workflow檔案本身只保留`workflow_dispatch`。

1. 註冊[Cloudflare](https://dash.cloudflare.com/sign-up)免費帳號（Workers免費額度每天10萬次請求，遠超這裡的用量）
2. 在GitHub建立一個有`workflow`權限的[Personal Access Token (fine-grained)](https://github.com/settings/personal-access-tokens/new)，Repository permissions → Actions → Read and write，範圍限定在這個repo
3. 本機安裝並登入wrangler：
   ```bash
   cd cloudflare
   npm install
   npx wrangler login
   ```
4. 把GitHub token存成Worker secret（不要寫進`wrangler.toml`）：
   ```bash
   npx wrangler secret put GITHUB_TOKEN
   ```
5. 部署：
   ```bash
   npm run deploy
   ```

部署後Cloudflare會依`cloudflare/wrangler.toml`裡的兩條cron定時呼叫GitHub，觸發`daily_scan.yml`和`poll_commands.yml`的`workflow_dispatch`。之後要改排程時間，改`wrangler.toml`的`crons`再重新`npm run deploy`即可。

## 修改設定

- 篩選門檻：改 [config/settings.yaml](config/settings.yaml)
- 持股清單：改 [config/holdings.yaml](config/holdings.yaml)，或用Telegram指令 `/holdings_add TICKER`

## Telegram指令

```
/add TICKER STRIKE EXPIRY PREMIUM   記錄新開的covered call (EXPIRY用YYYY-MM-DD)
/close TICKER STRIKE EXPIRY         關閉倉位
/list                               列出目前所有open positions
/scan                                立即重新掃描covered call機會（跟每日排程同一份邏輯）
/holdings_add TICKER                加入長期持股清單
/holdings_remove TICKER             從長期持股清單移除
/help                                顯示這份說明
```

## 本機執行（選用）

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...
python -m src.scan     # 跑一次機會掃描
python -m src.poll     # 跑一次指令檢查
```

## 已知限制

- yfinance是免費、非官方的Yahoo Finance資料，報價有約15分鐘延遲，且沒有現成的delta欄位（本專案自行用Black-Scholes反推）。除息日/財報日資料偶爾會缺漏，缺漏時該檔股票的排除規則不會生效，等於没被過濾掉，請自行留意。
- Telegram指令不是即時的，最多延遲約5分鐘（受Cloudflare Worker cron頻率限制）。
