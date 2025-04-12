# 台股籌碼快報 LINE Bot

這是一個用於爬取台灣股市籌碼資料並透過 LINE Bot 提供給用戶的應用程式。它每天會自動爬取台灣期貨交易所和證券交易所的籌碼資料，並存儲在資料庫中，用戶可以透過私訊或在群組中使用指令獲取這些資料。

## 功能特點

- 每日自動爬取股市籌碼資料（約 14:45-14:50）
- 支援 MongoDB 資料庫存儲和查詢歷史資料
- 自動推送每日籌碼報告到指定群組
- 用戶可以透過指令獲取特定籌碼資料
- 支援私訊和群組使用
- 完整的日誌記錄和錯誤處理

## 主要籌碼資料

- 加權指數：收盤價、漲跌、成交金額
- 台指期：收盤價、漲跌、與現貨差
- 三大法人買賣超：外資、投信、自營商
- 期貨籌碼：外資期貨、選擇權部位，十大交易人部位
- 散戶籌碼：小台散戶、微台散戶指標
- 市場氛圍指標：PC ratio、VIX指標

## 技術架構

- **後端**：Python Flask
- **資料庫**：MongoDB
- **訊息推送**：LINE Messaging API
- **排程**：Schedule 套件
- **爬蟲**：Requests、BeautifulSoup4
- **部署**：支援 Docker 容器化部署

## 系統需求

- Python 3.9+
- MongoDB 資料庫
- LINE Messaging API 帳號和管道

## 安裝說明

1. 克隆項目
   ```bash
   git clone https://github.com/yourusername/line-bot-taifex.git
   cd line-bot-taifex
   ```

2. 安裝依賴
   ```bash
   pip install -r requirements.txt
   ```

3. 設定環境變數
   ```bash
   cp .env.example .env
   # 編輯 .env 檔案，填入你的 LINE Channel 和 MongoDB 憑證
   ```

4. 本地測試
   ```bash
   python run_local.py --test  # 執行測試
   python run_local.py --app   # 啟動 Flask 應用程式
   ```

## 部署指南

### 使用 Docker 部署

1. 建立 Docker 映像
   ```bash
   docker build -t line-bot-taifex .
   ```

2. 執行容器
   ```bash
   docker run -p 8080:8080 --env-file .env line-bot-taifex
   ```

### 部署到 Render 或其他雲端平台

1. 在平台上設定環境變數
2. 連接 GitHub 倉庫或上傳程式碼
3. 使用 `gunicorn app:app` 作為啟動命令

## 使用指南

1. 將 LINE Bot 加為好友
2. 可以使用以下指令：
   - `籌碼快報`：獲取今日完整籌碼報告
   - `加權指數`：獲取今日加權指數資訊
   - `三大法人`：獲取今日三大法人買賣超資訊
   - `期貨籌碼`：獲取今日期貨籌碼資訊
   - `散戶籌碼`：獲取今日散戶籌碼資訊
   - `籌碼說明`：查看使用說明

## 專案結構

```
line-bot-taifex/
│
├── app.py                   # 主應用程式
├── utils.py                 # 工具函數
├── run_local.py             # 本地測試腳本
├── Dockerfile               # Docker 配置
├── requirements.txt         # 依賴庫
│
├── crawler/                 # 爬蟲模組
│   ├── __init__.py
│   ├── taiex.py             # 加權指數爬蟲
│   ├── futures.py           # 期貨爬蟲
│   ├── institutional.py     # 三大法人爬蟲
│   ├── pc_ratio.py          # PC Ratio爬蟲
│   ├── vix.py               # VIX指標爬蟲
│   ├── top_traders.py       # 十大交易人爬蟲
│   ├── option_positions.py  # 選擇權持倉爬蟲
│   └── utils.py             # 爬蟲共用工具
│
├── database/                # 資料庫模組
│   ├── __init__.py
│   └── mongodb.py           # MongoDB 資料庫操作
│
└── scheduler/               # 排程模組
    ├── __init__.py
    └── market_data.py       # 市場數據排程任務
```

## 關於資料來源

本專案爬取的資料來源包括：
- [臺灣證券交易所](https://www.twse.com.tw/)
- [臺灣期貨交易所](https://www.taifex.com.tw/)

## 授權協議

MIT License
