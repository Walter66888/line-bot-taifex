"""
VIX指標爬蟲模組
"""
import re
import logging
from datetime import datetime, timedelta
import requests
from .utils import get_tw_stock_date

logger = logging.getLogger(__name__)

def get_vix_data():
    """
    獲取VIX指標數據，返回最後一分鐘平均值
    
    Returns:
        float: 收盤VIX值（最後一分鐘平均值）
    """
    try:
        # 取得日期
        date = get_tw_stock_date('%Y%m%d')
        
        # 構建URL
        url = f"https://www.taifex.com.tw/cht/7/getVixData?filesname={date}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # 檢查是否有HTTP錯誤
        
        # 檢查是否有數據
        if "無資料" in response.text or len(response.text.strip()) == 0:
            # 可能是非交易日，嘗試獲取前一天的數據
            logger.warning(f"無法獲取 {date} 的VIX數據，可能是非交易日")
            yesterday = (datetime.strptime(date, '%Y%m%d') - timedelta(days=1)).strftime('%Y%m%d')
            return get_vix_data_by_date(yesterday)
        
        return get_vix_data_by_date(date)
    
    except Exception as e:
        logger.error(f"獲取VIX數據時出錯: {str(e)}")
        return 0.0

def get_vix_data_by_date(date):
    """
    獲取特定日期的VIX指標數據
    
    Args:
        date: 日期字符串，格式為YYYYMMDD
        
    Returns:
        float: 收盤VIX值（最後一分鐘平均值）
    """
    try:
        url = f"https://www.taifex.com.tw/cht/7/getVixData?filesname={date}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        # 嘗試不同的編碼
        encodings = ['utf-8', 'big5', 'cp950', 'latin-1']
        
        for encoding in encodings:
            try:
                decoded_text = response.content.decode(encoding)
                
                # 直接查找最後一分鐘平均值
                last_min_avg_pattern = r"Last 1 min AVG\s+(\d+\.\d+)"
                match = re.search(last_min_avg_pattern, decoded_text)
                
                if match:
                    return float(match.group(1))
                
                # 如果找不到特定模式，則解析整個文件並取最後一個非空值
                lines = decoded_text.split('\n')
                for line in reversed(lines):
                    if "AVG" in line and re.search(r"\d+\.\d+", line):
                        value_match = re.search(r"(\d+\.\d+)$", line.strip())
                        if value_match:
                            return float(value_match.group(1))
                
                # 最後嘗試：查找任何浮點數
                for line in reversed(lines):
                    float_match = re.search(r"(\d+\.\d+)$", line.strip())
                    if float_match:
                        return float(float_match.group(1))
                
            except UnicodeDecodeError:
                continue
        
        # 如果所有嘗試都失敗，則返回0
        logger.error(f"無法解析 {date} 的VIX數據")
        return 0.0
    
    except Exception as e:
        logger.error(f"獲取 {date} 的VIX數據時出錯: {str(e)}")
        return 0.0

# 主程序測試
if __name__ == "__main__":
    result = get_vix_data()
    print(f"VIX: {result}")
