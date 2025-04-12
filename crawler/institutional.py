"""
三大法人買賣超爬蟲模組 - 改進版
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
        
        # 使用改進的 URL (新版證交所網站)
        url = f"https://www.twse.com.tw/rwd/zh/fund/BFI82U?date={date}&response=html"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.twse.com.tw/zh/'
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        response.encoding = 'utf-8'
        
        soup = BeautifulSoup(response.text, 'lxml')
        
        # 解析表格
        tables = soup.find_all('table')
        if not tables:
            logger.error("找不到三大法人買賣超表格")
            return default_institutional_data(date)
        
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
                buy_sell_diff = safe_float(cells[3].text.strip().replace(',', ''))
                
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
        
        # 檢查是否有異常值，如果外資為0但合計不為0，嘗試使用替代方法
        if abs(result['foreign']) < 0.01 and abs(result['total']) > 1.0:
            logger.warning("外資買賣超資料異常，嘗試使用替代方法")
            alternate_result = get_institutional_alternate(date)
            if alternate_result and abs(alternate_result.get('foreign', 0)) > 0.01:
                result['foreign'] = alternate_result.get('foreign', result['foreign'])
                logger.info(f"使用替代方法獲取外資買賣超: {result['foreign']}")
        
        # 檢查並調整數據
        if abs(result['total'] - (result['foreign'] + result['investment_trust'] + result['dealer'])) > 1.0:
            logger.warning("三大法人合計與個別加總不符，嘗試調整")
            if abs(result['total']) > 1.0 and abs(result['foreign']) < 0.01:
                # 如果合計有值但外資接近0，嘗試計算外資
                result['foreign'] = result['total'] - result['investment_trust'] - result['dealer']
                logger.info(f"計算得出外資買賣超: {result['foreign']}")
        
        logger.info(f"三大法人買賣超: 外資={result['foreign']}億, 投信={result['investment_trust']}億, 自營商={result['dealer']}億, 合計={result['total']}億")
        
        return result
    
    except Exception as e:
        logger.error(f"獲取三大法人買賣超資料時出錯: {str(e)}")
        return default_institutional_data(date)

def get_institutional_alternate(date):
    """
    使用替代方法獲取三大法人買賣超資料
    
    Args:
        date: 日期字符串，格式為YYYYMMDD
        
    Returns:
        dict: 包含三大法人買賣超資料的字典
    """
    try:
        # 使用替代URL (較舊的格式，有時較穩定)
        url = f"https://www.twse.com.tw/fund/BFI82U?response=json&date={date}&type=day"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Referer': 'https://www.twse.com.tw/zh/'
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        if data.get('stat') != 'OK':
            logger.error(f"替代方法獲取三大法人資料失敗: {data.get('stat')}")
            return None
            
        result = {
            'date': date,
            'foreign': 0.0,
            'investment_trust': 0.0,
            'dealer_self': 0.0,
            'dealer_hedge': 0.0,
            'dealer': 0.0,
            'total': 0.0
        }
        
        # 解析JSON數據
        for item in data.get('data', []):
            if len(item) >= 4:
                category = item[0]
                buy_sell_diff = safe_float(item[3].replace(',', ''))
                
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
        
        logger.info(f"替代方法獲取三大法人買賣超: 外資={result['foreign']}億, 投信={result['investment_trust']}億, 自營商={result['dealer']}億")
        
        return result
    
    except Exception as e:
        logger.error(f"使用替代方法獲取三大法人資料時出錯: {str(e)}")
        return None

def default_institutional_data(date):
    """返回默認的三大法人買賣超資料"""
    return {
        'date': date,
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
