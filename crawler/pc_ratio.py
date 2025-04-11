"""
PC Ratio爬蟲模組
"""
import logging
import requests
from bs4 import BeautifulSoup
from .utils import get_tw_stock_date, safe_float, get_html_content

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
        
        # 改用更可靠的方式獲取PC Ratio數據
        # 台指選擇權Put/Call Ratio網頁
        url = "https://www.taifex.com.tw/cht/3/pcRatio"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # 使用get_html_content獲取HTML內容
        soup = get_html_content(url, headers=headers)
        
        if not soup:
            logger.error("無法獲取PC Ratio頁面")
            return default_pc_ratio(date)
        
        # 解析表格
        tables = soup.find_all('table', class_='table_f')
        if not tables or len(tables) < 1:
            logger.error("找不到PC Ratio表格")
            return default_pc_ratio(date)
        
        table = tables[0]
        rows = table.find_all('tr')
        
        # 跳過表頭行，直接獲取第二行（最新數據）
        if len(rows) < 3:  # 包含標題行和數據行
            logger.error("PC Ratio表格數據不足")
            return default_pc_ratio(date)
        
        # 獲取最新數據（第二行，索引為1）
        latest_row = rows[1]
        cells = latest_row.find_all('td')
        
        # 檢查是否有足夠的列
        if len(cells) < 6:
            logger.error(f"PC Ratio表格列數不足: {len(cells)}")
            return default_pc_ratio(date)
        
        # 解析數據
        # 日期通常在第一列
        try:
            trade_date = cells[0].text.strip()
            
            # 成交量比率(P/C)通常在第三列
            vol_ratio_text = cells[2].text.strip().replace(',', '')
            vol_ratio = safe_float(vol_ratio_text)
            
            # 未平倉量比率(P/C)通常在第五列
            oi_ratio_text = cells[4].text.strip().replace(',', '')
            oi_ratio = safe_float(oi_ratio_text)
            
            logger.info(f"成功獲取PC Ratio數據: 日期={trade_date}, 成交量比率={vol_ratio}, 未平倉量比率={oi_ratio}")
            
            # 格式化日期為YYYYMMDD
            formatted_date = ''.join(trade_date.split('/'))
            
            return {
                'date': formatted_date,
                'vol_ratio': vol_ratio,
                'oi_ratio': oi_ratio
            }
        except Exception as e:
            logger.error(f"解析PC Ratio數據時出錯: {str(e)}")
            return default_pc_ratio(date)
    
    except Exception as e:
        logger.error(f"獲取PC Ratio數據時出錯: {str(e)}")
        return default_pc_ratio(date)

def default_pc_ratio(date):
    """返回默認的PC Ratio數據"""
    return {
        'date': date,
        'vol_ratio': 0.0,
        'oi_ratio': 0.0
    }

# 主程序測試
if __name__ == "__main__":
    result = get_pc_ratio()
    print(result)
