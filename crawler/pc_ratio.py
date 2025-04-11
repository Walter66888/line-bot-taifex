"""
PC Ratio爬蟲模組
"""
import logging
import requests
from bs4 import BeautifulSoup
from .utils import get_tw_stock_date, safe_float

logger = logging.getLogger(__name__)

def get_pc_ratio():
    """
    獲取PC Ratio數據
    
    Returns:
        dict: 包含PC Ratio數據的字典
    """
    try:
        # 取得日期
        date = get_tw_stock_date('%Y%m%d')
        url = f"https://www.taifex.com.tw/cht/3/pcRatioExcel"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        # 根據實際情況，可能需要嘗試不同的編碼
        encodings = ['utf-8', 'big5', 'cp950', 'latin-1']
        soup = None
        
        for encoding in encodings:
            try:
                response.encoding = encoding
                soup = BeautifulSoup(response.text, 'lxml')
                break
            except:
                continue
        
        if not soup:
            logger.error("無法解析PC Ratio頁面")
            return None
        
        # 解析表格
        tables = soup.find_all('table')
        if not tables:
            logger.error("找不到PC Ratio表格")
            return {
                'date': date,
                'vol_ratio': 0.0,
                'oi_ratio': 0.0
            }
        
        table = tables[0]
        rows = table.find_all('tr')
        
        # 通常第一行是標題，第二行是最新數據
        if len(rows) < 2:
            logger.error("PC Ratio表格數據不足")
            return {
                'date': date,
                'vol_ratio': 0.0,
                'oi_ratio': 0.0
            }
        
        # 獲取最新數據
        latest_row = rows[1]  # 第二行，索引為1
        cells = latest_row.find_all('td')
        
        # 檢查是否有足夠的列
        if len(cells) < 7:
            logger.error("PC Ratio表格列數不足")
            return {
                'date': date,
                'vol_ratio': 0.0,
                'oi_ratio': 0.0
            }
        
        # 解析數據
        trade_date = cells[0].text.strip()
        vol_ratio = safe_float(cells[3].text.strip())
        oi_ratio = safe_float(cells[6].text.strip())
        
        return {
            'date': trade_date.replace('/', ''),
            'vol_ratio': vol_ratio,
            'oi_ratio': oi_ratio
        }
    
    except Exception as e:
        logger.error(f"獲取PC Ratio數據時出錯: {str(e)}")
        return {
            'date': date,
            'vol_ratio': 0.0,
            'oi_ratio': 0.0
        }

# 主程序測試
if __name__ == "__main__":
    result = get_pc_ratio()
    print(result)
