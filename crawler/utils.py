"""
共用工具函數模組
"""
import logging
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def get_today_date_string(format='%Y%m%d'):
    """獲取今日日期字符串"""
    return datetime.today().strftime(format)

def get_yesterday_date_string(format='%Y%m%d'):
    """獲取昨日日期字符串"""
    yesterday = datetime.today() - timedelta(days=1)
    return yesterday.strftime(format)

def get_tw_stock_date(format='%Y%m%d'):
    """
    獲取台灣股市最近交易日
    簡單版：如果當前時間在15:00之後，返回今天，否則返回昨天
    """
    now = datetime.now()
    current_time = now.time()
    if current_time.hour >= 15:
        return get_today_date_string(format)
    else:
        return get_yesterday_date_string(format)

def get_html_content(url, headers=None, params=None, encoding='utf-8'):
    """
    獲取網頁HTML內容
    
    Args:
        url: 網址
        headers: 請求頭
        params: URL參數
        encoding: 編碼
        
    Returns:
        BeautifulSoup對象
    """
    try:
        if not headers:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
        
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        response.encoding = encoding
        
        return BeautifulSoup(response.text, 'lxml')
    except Exception as e:
        logging.error(f"獲取網頁內容時出錯: {url}, {str(e)}")
        return None

def safe_float(value, default=0.0):
    """安全地將值轉換為浮點數"""
    try:
        if isinstance(value, str):
            # 移除千分位逗號和其他非數字字符（保留負號和小數點）
            value = ''.join(c for c in value if c.isdigit() or c in '.-')
        return float(value)
    except (ValueError, TypeError):
        return default

def safe_int(value, default=0):
    """安全地將值轉換為整數"""
    try:
        if isinstance(value, str):
            # 移除千分位逗號和其他非數字字符（保留負號）
            value = ''.join(c for c in value if c.isdigit() or c == '-')
        return int(value)
    except (ValueError, TypeError):
        return default
