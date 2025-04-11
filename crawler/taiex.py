"""
台灣加權指數爬蟲模組
"""
import re
import logging
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from .utils import get_tw_stock_date, safe_float

logger = logging.getLogger(__name__)

def get_taiex_data():
    """
    獲取台灣加權指數相關數據
    
    Returns:
        dict: 包含指數數據的字典
    """
    try:
        # 取得日期
        date = get_tw_stock_date('%Y%m%d')
        url = f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={date}&type=IND&response=html"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        response.encoding = 'utf-8'
        
        soup = BeautifulSoup(response.text, 'lxml')
        
        # 取得加權指數
        tables = soup.find_all('table')
        if not tables:
            logger.error("找不到台灣加權指數表格")
            return None
        
        # 第一個表格包含指數數據
        taiex_table = tables[0]
        rows = taiex_table.find_all('tr')
        
        # 尋找發行量加權股價指數行
        taiex_row = None
        for row in rows:
            cells = row.find_all('td')
            if cells and cells[0].text.strip() == '發行量加權股價指數':
                taiex_row = cells
                break
        
        if not taiex_row:
            logger.error("找不到發行量加權股價指數行")
            return None
        
        # 解析數據
        index_value = safe_float(taiex_row[1].text.strip())
        change_sign = 1 if taiex_row[2].text.strip() == '+' else -1
        change_value = safe_float(taiex_row[3].text.strip()) * change_sign
        change_percent = safe_float(taiex_row[4].text.strip()) * change_sign
        
        # 獲取成交金額
        url_vol = f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={date}&type=MS&response=html"
        response_vol = requests.get(url_vol, headers=headers)
        response_vol.encoding = 'utf-8'
        soup_vol = BeautifulSoup(response_vol.text, 'lxml')
        
        volume = 0.0
        # 找到總計行
        tables_vol = soup_vol.find_all('table')
        if tables_vol and len(tables_vol) > 0:
            rows_vol = tables_vol[0].find_all('tr')
            for row in rows_vol:
                cells = row.find_all('td')
                if cells and '總計' in cells[0].text:
                    volume_text = cells[1].text.strip()
                    # 轉換為億
                    volume = safe_float(volume_text) / 100000000
                    break
        
        return {
            'date': date,
            'close': index_value,
            'change': change_value,
            'change_percent': change_percent,
            'volume': volume
        }
    
    except Exception as e:
        logger.error(f"獲取台灣加權指數數據時出錯: {str(e)}")
        return {
            'date': get_tw_stock_date('%Y%m%d'),
            'close': 0.0,
            'change': 0.0,
            'change_percent': 0.0,
            'volume': 0.0
        }

# 主程序測試
if __name__ == "__main__":
    result = get_taiex_data()
    print(result)
