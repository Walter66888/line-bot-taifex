"""
十大交易人持倉爬蟲模組 - 新版
專門處理十大交易人和特定法人持倉資料
"""
import logging
import requests
import re
from bs4 import BeautifulSoup
from datetime import datetime
from .utils import get_tw_stock_date, safe_int, get_html_content

# 設定日誌
logger = logging.getLogger(__name__)

def get_top_traders_data():
    """
    獲取十大交易人和特定法人持倉資料
    
    Returns:
        dict: 包含十大交易人和特定法人持倉資料的字典
    """
    try:
        # 取得日期
        date = get_tw_stock_date('%Y%m%d')
        
        # 使用主要方法獲取資料
        result = get_top_traders_by_date(date)
        
        # 記錄結果
        logger.info(f"十大交易人持倉資料: 十大交易人={result['top10_traders_net']}, 十大特定法人={result['top10_specific_net']}")
        
        return result
    
    except Exception as e:
        logger.error(f"獲取十大交易人持倉資料時出錯: {str(e)}")
        return default_top_traders_data()

def get_top_traders_by_date(date):
    """
    獲取特定日期的十大交易人和特定法人持倉資料
    
    Args:
        date: 日期字符串，格式為YYYYMMDD
        
    Returns:
        dict: 包含十大交易人和特定法人持倉資料的字典
    """
    try:
        # 使用URL
        url = "https://www.taifex.com.tw/cht/3/largeTraderFutQryTbl"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.taifex.com.tw/cht/3/largeTraderFutQryTbl'
        }
        
        # 使用POST方法，提供查詢參數
        data = {
            'queryType': '1',
            'goDay': '',
            'doQuery': '1',
            'dateaddcnt': '',
            'queryDate': date[:4] + '/' + date[4:6] + '/' + date[6:],  # 格式化日期為YYYY/MM/DD
            'commodityId': 'TXF'  # 台指期貨
        }
        
        # 初始化結果
        result = default_top_traders_data()
        
        # 請求數據
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        
        # 嘗試使用不同的編碼
        for encoding in ['utf-8', 'big5', 'cp950']:
            try:
                response.encoding = encoding
                soup = BeautifulSoup(response.text, 'lxml')
                break
            except:
                continue
        
        # 查找表格
        tables = soup.find_all('table')
        if not tables:
            logger.error("找不到十大交易人持倉表格")
            return result
        
        # 尋找包含十大交易人資料的表格
        target_table = None
        for table in tables:
            if '十大交易人' in table.text or '大額交易人' in table.text:
                target_table = table
                break
        
        if not target_table:
            logger.error("找不到包含十大交易人資料的表格")
            return result
        
        # 解析表格資料
        # 針對表格結構尋找買方和賣方欄位
        rows = target_table.find_all('tr')
        
        if len(rows) < 3:  # 需要至少有標題行和資料行
            logger.error("表格行數不足")
            return result
        
        # 先找到標題行，建立欄位位置對應
        header_mapping = {}
        for i, row in enumerate(rows[:2]):  # 檢查前兩行，可能是多行標題
            cols = row.find_all(['th', 'td'])
            for j, col in enumerate(cols):
                text = col.text.strip().lower()
                
                # 找買方欄位
                if '買方' in text or '多方' in text:
                    if '十大交易人' in text and '特定法人' not in text:
                        header_mapping['top10_traders_buy'] = j
                    elif '特定法人' in text:
                        header_mapping['top10_specific_buy'] = j
                
                # 找賣方欄位
                elif '賣方' in text or '空方' in text:
                    if '十大交易人' in text and '特定法人' not in text:
                        header_mapping['top10_traders_sell'] = j
                    elif '特定法人' in text:
                        header_mapping['top10_specific_sell'] = j
        
        logger.info(f"表頭映射: {header_mapping}")
        
        # 如果找不到特定法人欄位，可能是因為特定法人數據在括號中
        if 'top10_specific_buy' not in header_mapping and 'top10_traders_buy' in header_mapping:
            header_mapping['top10_specific_buy'] = header_mapping['top10_traders_buy']
        
        if 'top10_specific_sell' not in header_mapping and 'top10_traders_sell' in header_mapping:
            header_mapping['top10_specific_sell'] = header_mapping['top10_traders_sell']
        
        # 尋找包含台指期貨資料的行
        data_row = None
        for row in rows[2:]:  # 跳過標題行
            cols = row.find_all(['th', 'td'])
            row_text = ' '.join([col.text.strip() for col in cols])
            
            # 檢查是否為台指期貨行
            if '臺股期貨' in row_text or 'TX' in row_text:
                data_row = cols
                break
        
        if not data_row:
            logger.error("找不到台指期貨資料行")
            return result
        
        # 從資料行提取十大交易人和特定法人的買賣方部位
        top10_traders_buy = 0
        top10_traders_sell = 0
        top10_specific_buy = 0
        top10_specific_sell = 0
        
        try:
            # 提取十大交易人買方部位
            if 'top10_traders_buy' in header_mapping:
                buy_col = data_row[header_mapping['top10_traders_buy']]
                buy_text = buy_col.text.strip()
                
                # 提取數字，可能包含在括號外
                match = re.search(r'(\d+[\d,]*)\s*\(', buy_text)
                if match:
                    top10_traders_buy = safe_int(match.group(1).replace(',', ''))
                else:
                    # 如果沒有括號，直接取數字
                    numbers = re.findall(r'\d+[\d,]*', buy_text)
                    if numbers:
                        top10_traders_buy = safe_int(numbers[0].replace(',', ''))
                
                # 提取特定法人買方部位（可能在括號內）
                match = re.search(r'\((\d+[\d,]*)\)', buy_text)
                if match:
                    top10_specific_buy = safe_int(match.group(1).replace(',', ''))
            
            # 提取十大交易人賣方部位
            if 'top10_traders_sell' in header_mapping:
                sell_col = data_row[header_mapping['top10_traders_sell']]
                sell_text = sell_col.text.strip()
                
                # 提取數字，可能包含在括號外
                match = re.search(r'(\d+[\d,]*)\s*\(', sell_text)
                if match:
                    top10_traders_sell = safe_int(match.group(1).replace(',', ''))
                else:
                    # 如果沒有括號，直接取數字
                    numbers = re.findall(r'\d+[\d,]*', sell_text)
                    if numbers:
                        top10_traders_sell = safe_int(numbers[0].replace(',', ''))
                
                # 提取特定法人賣方部位（可能在括號內）
                match = re.search(r'\((\d+[\d,]*)\)', sell_text)
                if match:
                    top10_specific_sell = safe_int(match.group(1).replace(',', ''))
            
            # 如果以上方法沒有找到特定法人數據，嘗試從專門的特定法人欄位獲取
            if top10_specific_buy == 0 and 'top10_specific_buy' in header_mapping and header_mapping['top10_specific_buy'] != header_mapping.get('top10_traders_buy', -1):
                specific_buy_col = data_row[header_mapping['top10_specific_buy']]
                specific_buy_text = specific_buy_col.text.strip()
                numbers = re.findall(r'\d+[\d,]*', specific_buy_text)
                if numbers:
                    top10_specific_buy = safe_int(numbers[0].replace(',', ''))
            
            if top10_specific_sell == 0 and 'top10_specific_sell' in header_mapping and header_mapping['top10_specific_sell'] != header_mapping.get('top10_traders_sell', -1):
                specific_sell_col = data_row[header_mapping['top10_specific_sell']]
                specific_sell_text = specific_sell_col.text.strip()
                numbers = re.findall(r'\d+[\d,]*', specific_sell_text)
                if numbers:
                    top10_specific_sell = safe_int(numbers[0].replace(',', ''))
            
            # 計算淨部位
            top10_traders_net = top10_traders_buy - top10_traders_sell
            top10_specific_net = top10_specific_buy - top10_specific_sell
            
            # 儲存結果
            result['top10_traders_buy'] = top10_traders_buy
            result['top10_traders_sell'] = top10_traders_sell
            result['top10_traders_net'] = top10_traders_net
            result['top10_specific_buy'] = top10_specific_buy
            result['top10_specific_sell'] = top10_specific_sell
            result['top10_specific_net'] = top10_specific_net
            
            logger.info(f"十大交易人: 買方={top10_traders_buy}, 賣方={top10_traders_sell}, 淨部位={top10_traders_net}")
            logger.info(f"十大特定法人: 買方={top10_specific_buy}, 賣方={top10_specific_sell}, 淨部位={top10_specific_net}")
            
        except Exception as e:
            logger.error(f"解析十大交易人資料時出錯: {str(e)}")
        
        return result
    
    except Exception as e:
        logger.error(f"獲取十大交易人持倉資料時出錯: {str(e)}")
        return default_top_traders_data()

def default_top_traders_data():
    """返回默認的十大交易人和特定法人持倉資料"""
    return {
        'top10_traders_buy': 0,
        'top10_traders_sell': 0,
        'top10_traders_net': 0,
        'top10_specific_buy': 0,
        'top10_specific_sell': 0,
        'top10_specific_net': 0
    }

# 主程序測試
if __name__ == "__main__":
    result = get_top_traders_data()
    print(result)
