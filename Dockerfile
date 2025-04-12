FROM python:3.9-slim

WORKDIR /app

# 複製 requirements.txt 並安裝依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用程式代碼
COPY . .

# 設定默認環境變數
ENV FLASK_ENV=production
ENV ENABLE_SCHEDULER=true
ENV PORT=8080

# 暴露端口 (預設 8080，可以被環境變數覆蓋)
EXPOSE 8080

# 設定啟動命令
CMD gunicorn --bind 0.0.0.0:$PORT app:app
