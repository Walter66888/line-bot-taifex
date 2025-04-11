"""
三大法人買賣超爬蟲模組
"""
import logging
import requests
from bs4 import BeautifulSoup
from .utils import get_tw_stock_date, safe_float

logger = logging.getLogger(__name__)

def get_institutional_investors_data():
    """
    獲取三大法人買賣超資料
    
    Returns:
        dict: 包含三大法人買賣超資料的字典
    """
    try:
        # 取得日期
        date = get_tw_stock_date('%Y%m%d')
        url = f"https://www.twse.com.tw/rwd/zh/fund/BFI82U?response=html&date={date}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        response.encoding = 'utf-8'
        
        soup = BeautifulSoup(response.text, 'lxml')
        
        # 解析表格
        tables = soup.find_all('table')
        if not tables:
            logger.error("找不到三大法人買賣超表格")
            return None
        
        table = tables[0]
        rows = table.find_all('tr')
        
        # 初始化結果
        result = {
            'date': date,
            'foreign': 0.0,
            'investment_trust': 0.0,
            'dealer_self': 0.0,
            'dealer_hedge': 0.0,
            'dealer': 0.0,
            'total': 0.0
        }
        
        # 解析各行數據
        for row in rows:
            cells = row.find_all('td')
            if len(cells) >= 4:
                category = cells[0].text.strip()
                buy_sell_diff = safe_float(cells[3].text.strip())
                
                # 判斷類別並存儲數據
                if '自營商(自行買賣)' in category:
                    result['dealer_self'] = buy_sell_diff / 100000000  # 轉換為億
                elif '自營商(避險)' in category:
                    result['dealer_hedge'] = buy_sell_diff / 100000000  # 轉換為億
                elif '投信' in category:
                    result['investment_trust'] = buy_sell_diff / 100000000  # 轉換為億
                elif '外資及陸資' in category and '外資自營' not in category:
                    result['foreign'] = buy_sell_diff / 100000000  # 轉換為億
                elif '合計' in category:
                    result['total'] = buy_sell_diff / 100000000  # 轉換為億
        
        # 計算自營商總計
        result['dealer'] = result['dealer_self'] + result['dealer_hedge']
        
        return result
    
    except Exception as e:
        logger.error(f"獲取三大法人買賣超資料時出錯: {str(e)}")
        return {
            'date': get_tw_stock_date('%Y%m%d'),
            'foreign': 0.0,
            'investment_trust': 0.0,
            'dealer_self': 0.0,
            'dealer_hedge': 0.0,
            'dealer': 0.0,
            'total': 0.0
        }

# 主程序測試
if __name__ == "__main__":
    result = get_institutional_investors_data()
    print(result)
