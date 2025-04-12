"""
十大交易人和特定法人持倉資料爬蟲模組
"""
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
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
        
        # 使用改進的URL格式
        url = "https://www.taifex.com.tw/cht/3/largeTraderFutQry"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
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
        
        # 獲取HTML內容
        soup = get_html_content(url, headers=headers, method='POST', data=data)
        
        if not soup:
            # 嘗試獲取前一個交易日的數據
            yesterday = (datetime.strptime(date, '%Y%m%d') - timedelta(days=1)).strftime('%Y%m%d')
            logger.warning(f"無法獲取 {date} 的十大交易人資料，嘗試獲取 {yesterday} 的數據")
            return get_top_traders_data_by_date(yesterday)
        
        # 獲取今日數據
        today_data = extract_top_traders_data(soup, date)
        
        # 獲取昨日數據，用於計算變化
        yesterday = (datetime.strptime(date, '%Y%m%d') - timedelta(days=1)).strftime('%Y%m%d')
        yesterday_data = get_top_traders_data_by_date(yesterday)
        
        # 計算變化
        today_top10_traders_net = today_data.get('top10_traders_net', 0)
        yesterday_top10_traders_net = yesterday_data.get('top10_traders_net', 0) if yesterday_data else 0
        top10_traders_net_change = today_top10_traders_net - yesterday_top10_traders_net
        
        today_top10_specific_net = today_data.get('top10_specific_net', 0)
        yesterday_top10_specific_net = yesterday_data.get('top10_specific_net', 0) if yesterday_data else 0
        top10_specific_net_change = today_top10_specific_net - yesterday_top10_specific_net
        
        # 更新變化值
        today_data['top10_traders_net_change'] = top10_traders_net_change
        today_data['top10_specific_net_change'] = top10_specific_net_change
        
        return today_data
    
    except Exception as e:
        logger.error(f"獲取十大交易人資料時出錯: {str(e)}")
        return default_top_traders_data()

def get_top_traders_data_by_date(date):
    """
    獲取特定日期的十大交易人和特定法人持倉資料
    
    Args:
        date: 日期字符串，格式為YYYYMMDD
        
    Returns:
        dict: 包含十大交易人和特定法人持倉資料的字典
    """
    try:
        # 使用URL
        url = "https://www.taifex.com.tw/cht/3/largeTraderFutQry"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
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
        
        # 獲取HTML內容
        soup = get_html_content(url, headers=headers, method='POST', data=data)
        
        if not soup:
            logger.error(f"無法獲取 {date} 的十大交易人資料")
            return default_top_traders_data()
        
        return extract_top_traders_data(soup, date)
    
    except Exception as e:
        logger.error(f"獲取 {date} 的十大交易人資料時出錯: {str(e)}")
        return default_top_traders_data()

def extract_top_traders_data(soup, date):
    """
    從HTML內容中提取十大交易人和特定法人持倉資料
    
    Args:
        soup: BeautifulSoup對象
        date: 日期字符串，格式為YYYYMMDD
        
    Returns:
        dict: 包含十大交易人和特定法人持倉資料的字典
    """
    try:
        # 初始化結果
        result = {
            'date': date,
            'top10_traders_buy': 0,
            'top10_traders_sell': 0,
            'top10_traders_net': 0,
            'top10_specific_buy': 0,
            'top10_specific_sell': 0,
            'top10_specific_net': 0,
            'top10_traders_net_change': 0,
            'top10_specific_net_change': 0
        }
        
        # 查找表格
        tables = soup.find_all('table', class_='table_f')
        if not tables or len(tables) < 1:
            logger.error("找不到十大交易人表格")
            return result
        
        # 第一個表格通常是十大交易人資料
        table = tables[0]
        rows = table.find_all('tr')
        
        # 遍歷每一行，尋找所需資料
        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 6:
                continue
            
            # 十大交易人多方(buy)部位
            if '十大交易人-多方' in cells[0].text:
                buy_position = safe_int(cells[2].text.strip().replace(',', ''))
                result['top10_traders_buy'] = buy_position
            
            # 十大交易人空方(sell)部位
            elif '十大交易人-空方' in cells[0].text:
                sell_position = safe_int(cells[2].text.strip().replace(',', ''))
                result['top10_traders_sell'] = sell_position
            
            # 十大特定法人多方(buy)部位
            elif '十大特定法人-多方' in cells[0].text:
                buy_position = safe_int(cells[2].text.strip().replace(',', ''))
                result['top10_specific_buy'] = buy_position
            
            # 十大特定法人空方(sell)部位
            elif '十大特定法人-空方' in cells[0].text:
                sell_position = safe_int(cells[2].text.strip().replace(',', ''))
                result['top10_specific_sell'] = sell_position
        
        # 計算淨部位
        result['top10_traders_net'] = result['top10_traders_buy'] - result['top10_traders_sell']
        result['top10_specific_net'] = result['top10_specific_buy'] - result['top10_specific_sell']
        
        logger.info(f"十大交易人淨部位: {result['top10_traders_net']}, 十大特定法人淨部位: {result['top10_specific_net']}")
        
        return result
    
    except Exception as e:
        logger.error(f"解析十大交易人資料時出錯: {str(e)}")
        return default_top_traders_data()

def default_top_traders_data():
    """返回默認的十大交易人和特定法人持倉資料"""
    return {
        'date': get_tw_stock_date('%Y%m%d'),
        'top10_traders_buy': 0,
        'top10_traders_sell': 0,
        'top10_traders_net': 0,
        'top10_specific_buy': 0,
        'top10_specific_sell': 0,
        'top10_specific_net': 0,
        'top10_traders_net_change': 0,
        'top10_specific_net_change': 0
    }

# 主程序測試
if __name__ == "__main__":
    result = get_top_traders_data()
    print(result)
