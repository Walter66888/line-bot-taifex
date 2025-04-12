"""
選擇權持倉資料爬蟲模組
"""
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from .utils import get_tw_stock_date, safe_int, get_html_content

# 設定日誌
logger = logging.getLogger(__name__)

def get_option_positions_data():
    """
    獲取選擇權持倉資料
    
    Returns:
        dict: 包含選擇權持倉資料的字典
    """
    try:
        # 取得日期
        date = get_tw_stock_date('%Y%m%d')
        
        # 使用改進的URL格式
        url = "https://www.taifex.com.tw/cht/3/largeTraderOptQry"
        
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
            'commodityId': 'TXO'  # 台指選擇權
        }
        
        # 獲取HTML內容
        soup = get_html_content(url, headers=headers, method='POST', data=data)
        
        if not soup:
            # 嘗試獲取前一個交易日的數據
            yesterday = (datetime.strptime(date, '%Y%m%d') - timedelta(days=1)).strftime('%Y%m%d')
            logger.warning(f"無法獲取 {date} 的選擇權持倉資料，嘗試獲取 {yesterday} 的數據")
            return get_option_positions_data_by_date(yesterday)
        
        # 獲取今日數據
        today_data = extract_option_positions_data(soup, date)
        
        # 獲取昨日數據，用於計算變化
        yesterday = (datetime.strptime(date, '%Y%m%d') - timedelta(days=1)).strftime('%Y%m%d')
        yesterday_data = get_option_positions_data_by_date(yesterday)
        
        # 計算變化
        today_foreign_call_net = today_data.get('foreign_call_net', 0)
        yesterday_foreign_call_net = yesterday_data.get('foreign_call_net', 0) if yesterday_data else 0
        foreign_call_net_change = today_foreign_call_net - yesterday_foreign_call_net
        
        today_foreign_put_net = today_data.get('foreign_put_net', 0)
        yesterday_foreign_put_net = yesterday_data.get('foreign_put_net', 0) if yesterday_data else 0
        foreign_put_net_change = today_foreign_put_net - yesterday_foreign_put_net
        
        # 更新變化值
        today_data['foreign_call_net_change'] = foreign_call_net_change
        today_data['foreign_put_net_change'] = foreign_put_net_change
        
        return today_data
    
    except Exception as e:
        logger.error(f"獲取選擇權持倉資料時出錯: {str(e)}")
        return default_option_positions_data()

def get_option_positions_data_by_date(date):
    """
    獲取特定日期的選擇權持倉資料
    
    Args:
        date: 日期字符串，格式為YYYYMMDD
        
    Returns:
        dict: 包含選擇權持倉資料的字典
    """
    try:
        # 使用URL
        url = "https://www.taifex.com.tw/cht/3/largeTraderOptQry"
        
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
            'commodityId': 'TXO'  # 台指選擇權
        }
        
        # 獲取HTML內容
        soup = get_html_content(url, headers=headers, method='POST', data=data)
        
        if not soup:
            logger.error(f"無法獲取 {date} 的選擇權持倉資料")
            return default_option_positions_data()
        
        return extract_option_positions_data(soup, date)
    
    except Exception as e:
        logger.error(f"獲取 {date} 的選擇權持倉資料時出錯: {str(e)}")
        return default_option_positions_data()

def extract_option_positions_data(soup, date):
    """
    從HTML內容中提取選擇權持倉資料
    
    Args:
        soup: BeautifulSoup對象
        date: 日期字符串，格式為YYYYMMDD
        
    Returns:
        dict: 包含選擇權持倉資料的字典
    """
    try:
        # 初始化結果
        result = {
            'date': date,
            'foreign_call_buy': 0,
            'foreign_call_sell': 0,
            'foreign_call_net': 0,
            'foreign_put_buy': 0,
            'foreign_put_sell': 0,
            'foreign_put_net': 0,
            'foreign_call_net_change': 0,
            'foreign_put_net_change': 0
        }
        
        # 查找表格
        tables = soup.find_all('table', class_='table_f')
        if not tables or len(tables) < 2:
            logger.error("找不到選擇權持倉表格")
            return result
        
        # 提取買權(Call)和賣權(Put)資料
        for i, table in enumerate(tables):
            rows = table.find_all('tr')
            
            # 檢查是否為買權(Call)或賣權(Put)表格
            header_row = rows[0] if rows else None
            if not header_row:
                continue
            
            header_text = header_row.text.strip().lower()
            is_call_table = 'call' in header_text
            is_put_table = 'put' in header_text
            
            if not (is_call_table or is_put_table):
                continue
            
            # 遍歷每一行，尋找外資資料
            for row in rows:
                cells = row.find_all('td')
                if len(cells) < 6:
                    continue
                
                # 檢查是否為外資資料行
                first_cell_text = cells[0].text.strip()
                if '外資' not in first_cell_text and 'foreign' not in first_cell_text.lower():
                    continue
                
                # 提取買方、賣方部位
                buy_position = safe_int(cells[2].text.strip().replace(',', ''))
                sell_position = safe_int(cells[5].text.strip().replace(',', ''))
                net_position = buy_position - sell_position
                
                # 儲存資料
                if is_call_table:
                    result['foreign_call_buy'] = buy_position
                    result['foreign_call_sell'] = sell_position
                    result['foreign_call_net'] = net_position
                elif is_put_table:
                    result['foreign_put_buy'] = buy_position
                    result['foreign_put_sell'] = sell_position
                    result['foreign_put_net'] = net_position
        
        logger.info(f"外資買權淨部位: {result['foreign_call_net']}, 外資賣權淨部位: {result['foreign_put_net']}")
        
        return result
    
    except Exception as e:
        logger.error(f"解析選擇權持倉資料時出錯: {str(e)}")
        return default_option_positions_data()

def default_option_positions_data():
    """返回默認的選擇權持倉資料"""
    return {
        'date': get_tw_stock_date('%Y%m%d'),
        'foreign_call_buy': 0,
        'foreign_call_sell': 0,
        'foreign_call_net': 0,
        'foreign_put_buy': 0,
        'foreign_put_sell': 0,
        'foreign_put_net': 0,
        'foreign_call_net_change': 0,
        'foreign_put_net_change': 0
    }

# 主程序測試
if __name__ == "__main__":
    result = get_option_positions_data()
    print(result)
