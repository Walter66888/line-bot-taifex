"""
共用工具函數模組 - 改進版
"""
import logging
import requests
import pytz
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# 設定台灣時區
TW_TIMEZONE = pytz.timezone('Asia/Taipei')

def get_today_date_string(format='%Y%m%d'):
    """獲取今日日期字符串（台灣時間）"""
    return datetime.now(TW_TIMEZONE).strftime(format)

def get_yesterday_date_string(format='%Y%m%d'):
    """獲取昨日日期字符串（台灣時間）"""
    yesterday = datetime.now(TW_TIMEZONE) - timedelta(days=1)
    return yesterday.strftime(format)

def is_taiwan_market_closed():
    """
    檢查台灣股市是否已收盤
    台灣股市交易時間: 9:00-13:30
    """
    now = datetime.now(TW_TIMEZONE)
    current_hour = now.hour
    current_minute = now.minute
    
    # 檢查是否為週末
    if now.weekday() >= 5:  # 5 = 週六, 6 = 週日
        return True
    
    # 檢查是否在交易時間內
    if (current_hour > 13) or (current_hour == 13 and current_minute >= 30) or (current_hour < 9):
        return True
    
    return False

def get_tw_stock_date(format='%Y%m%d'):
    """
    獲取台灣股市最近交易日
    改進版: 判斷是否收盤，並考慮週末和假日
    """
    now = datetime.now(TW_TIMEZONE)
    
    # 如果是週末，返回上週五的日期
    if now.weekday() >= 5:  # 5 = 週六, 6 = 週日
        days_to_subtract = now.weekday() - 4  # 計算到上週五的天數
        last_trading_day = now - timedelta(days=days_to_subtract)
        return last_trading_day.strftime(format)
    
    # 如果當日市場已收盤，返回當日日期
    if is_taiwan_market_closed():
        return now.strftime(format)
    else:
        # 如果市場尚未收盤，返回上一個交易日
        if now.weekday() == 0:  # 週一
            last_trading_day = now - timedelta(days=3)  # 返回上週五
        else:
            last_trading_day = now - timedelta(days=1)  # 返回昨天
        return last_trading_day.strftime(format)

def get_html_content(url, headers=None, params=None, encoding='utf-8', method='GET', data=None, timeout=30):
    """
    獲取網頁HTML內容 - 改進版
    
    Args:
        url: 網址
        headers: 請求頭
        params: URL參數
        encoding: 編碼
        method: 請求方法，GET或POST
        data: POST數據
        timeout: 超時時間（秒）
        
    Returns:
        BeautifulSoup對象
    """
    try:
        if not headers:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
                'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            }
        
        if method.upper() == 'GET':
            response = requests.get(url, headers=headers, params=params, timeout=timeout)
        else:  # POST
            response = requests.post(url, headers=headers, params=params, data=data, timeout=timeout)
        
        response.raise_for_status()
        
        # 嘗試不同的編碼
        encodings = [encoding, 'utf-8', 'big5', 'cp950', 'latin-1']
        soup = None
        
        for enc in encodings:
            try:
                response.encoding = enc
                soup = BeautifulSoup(response.text, 'lxml')
                break
            except:
                continue
        
        if not soup:
            logger.error(f"無法解析頁面內容: {url}")
            return None
        
        return soup
    
    except requests.RequestException as e:
        logger.error(f"獲取網頁內容時出錯: {url}, {str(e)}")
        return None
    except Exception as e:
        logger.error(f"處理網頁內容時出錯: {url}, {str(e)}")
        return None

def safe_float(value, default=0.0):
    """安全地將值轉換為浮點數 - 改進版"""
    try:
        if value is None:
            return default
        
        if isinstance(value, str):
            # 移除千分位逗號和其他非數字字符（保留負號和小數點）
            value = ''.join(c for c in value if c.isdigit() or c in '.-')
            
            # 處理空字符串
            if not value or value in ['.', '-', '-.']:
                return default
        
        return float(value)
    except (ValueError, TypeError):
        return default

def safe_int(value, default=0):
    """安全地將值轉換為整數 - 改進版"""
    try:
        if value is None:
            return default
        
        if isinstance(value, str):
            # 移除千分位逗號和其他非數字字符（保留負號）
            value = ''.join(c for c in value if c.isdigit() or c == '-')
            
            # 處理空字符串
            if not value or value == '-':
                return default
        
        return int(float(value))  # 使用float作為中間轉換，處理小數
    except (ValueError, TypeError):
        return default

def format_number(value, decimal_places=2, add_plus=False):
    """
    格式化數字為字符串，可選添加正號
    
    Args:
        value: 數字值
        decimal_places: 小數位數
        add_plus: 是否為正數添加+號
        
    Returns:
        格式化後的字符串
    """
    try:
        num = safe_float(value)
        if num > 0 and add_plus:
            return f"+{num:.{decimal_places}f}"
        else:
            return f"{num:.{decimal_places}f}"
    except:
        return f"0.{'0' * decimal_places}"

def get_market_trend_symbol(value):
    """
    獲取市場趨勢符號
    
    Args:
        value: 數值變化
        
    Returns:
        趨勢符號: ▲, ▼ 或 --
    """
    value = safe_float(value)
    if value > 0:
        return "▲"
    elif value < 0:
        return "▼"
    else:
        return "--"

def normalize_pc_ratio(value):
    """
    處理PC Ratio可能的異常值
    
    Args:
        value: PC Ratio值
        
    Returns:
        normalized value: 處理後的值
    """
    try:
        if not value:
            return 0.0
            
        # 如果數值過大 (通常大於 10 就不合理)
        if value > 1000:
            return value / 10000  # 可能是百分比顯示為整數 (例如 7500 應為 0.75)
        elif value > 100:
            return value / 100  # 可能是百分比顯示為整數 (例如 75 應為 0.75)
        elif value > 10:
            # 判斷是否合理，通常PC比率在0.5-2.0之間
            if value > 50:
                return value / 100
            elif value > 20:
                return value / 10
            
        return value
    except:
        return 0.0

# 測試函數
if __name__ == "__main__":
    print(f"當前台灣時間: {datetime.now(TW_TIMEZONE)}")
    print(f"今日日期: {get_today_date_string()}")
    print(f"昨日日期: {get_yesterday_date_string()}")
    print(f"台灣市場是否已收盤: {is_taiwan_market_closed()}")
    print(f"台灣股市資料日期: {get_tw_stock_date()}")
    
    # 測試格式化函數
    print(f"格式化正數: {format_number(123.456)}")
    print(f"格式化負數: {format_number(-123.456)}")
    print(f"格式化正數並添加+號: {format_number(123.456, add_plus=True)}")
    print(f"趨勢符號測試: 正數={get_market_trend_symbol(5)}, 負數={get_market_trend_symbol(-5)}, 零={get_market_trend_symbol(0)}")
    
    # 測試PC Ratio處理
    print(f"PC Ratio處理測試: 0.75={normalize_pc_ratio(0.75)}, 75={normalize_pc_ratio(75)}, 7500={normalize_pc_ratio(7500)}")
