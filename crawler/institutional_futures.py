"""
三大法人期貨持倉爬蟲模組 - 新版
專門處理三大法人期貨持倉資料，包含外資台指和小台指淨未平倉
"""
import logging
import requests
import re
from bs4 import BeautifulSoup
from datetime import datetime
from .utils import get_tw_stock_date, safe_int, get_html_content

# 設定日誌
logger = logging.getLogger(__name__)

def get_institutional_futures_data():
    """
    獲取三大法人期貨持倉資料，專注於外資台指和小台指淨未平倉
    
    Returns:
        dict: 包含三大法人期貨持倉資料的字典
    """
    try:
        # 取得日期
        date = get_tw_stock_date('%Y%m%d')
        
        # 使用主要方法獲取資料
        result = get_institutional_futures_by_date(date)
        
        # 記錄結果
        logger.info(f"三大法人期貨持倉資料: 外資台指={result['foreign_tx_net']}, 外資小台={result['foreign_mtx_net']}")
        
        return result
    
    except Exception as e:
        logger.error(f"獲取三大法人期貨持倉資料時出錯: {str(e)}")
        return default_institutional_futures_data()

def get_institutional_futures_by_date(date):
    """
    獲取特定日期的三大法人期貨持倉資料
    
    Args:
        date: 日期字符串，格式為YYYYMMDD
        
    Returns:
        dict: 包含三大法人期貨持倉資料的字典
    """
    try:
        # 使用Excel格式URL以獲取更穩定的資料
        url = "https://www.taifex.com.tw/cht/3/futContractsDateExcel"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.taifex.com.tw/cht/3/futContractsDate'
        }
        
        # 使用POST方法，提供查詢參數
        data = {
            'queryType': '1',
            'goDay': '',
            'doQuery': '1',
            'dateaddcnt': '',
            'queryDate': date[:4] + '/' + date[4:6] + '/' + date[6:],  # 格式化日期為YYYY/MM/DD
        }
        
        # 初始化結果
        result = default_institutional_futures_data()
        
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
        
        # 查找包含期貨部位資訊的表格
        tables = soup.find_all('table')
        if not tables:
            logger.error("找不到三大法人期貨部位表格")
            return result
        
        # 尋找包含「臺股期貨」和「小型臺指期貨」的表格
        target_table = None
        for table in tables:
            if '臺股期貨' in table.text or '小型臺指期貨' in table.text:
                target_table = table
                break
        
        if not target_table:
            logger.error("找不到包含臺股期貨或小型臺指期貨的表格")
            return result
        
        # 建立表頭映射 - 找出關鍵欄位索引
        net_position_idx = -1
        header_rows = target_table.find_all('tr')[:2]  # 通常表頭在前幾行
        
        for header_row in header_rows:
            th_elements = header_row.find_all(['th', 'td'])
            for idx, th in enumerate(th_elements):
                text = th.text.strip().lower()
                if ('買賣' in text and '差額' in text) or ('多空' in text and '淨額' in text) or ('net' in text):
                    net_position_idx = idx
                    break
        
        # 如果找不到明確的淨部位欄位，嘗試常見的索引位置
        if net_position_idx == -1:
            logger.warning("找不到淨部位欄位，嘗試使用預設索引")
            # 通常是第8欄，但有時是第9欄或第10欄，取決於表格結構
            net_position_candidates = [8, 9, 10]
            max_cols = 0
            
            # 檢查表格有多少列
            for row in target_table.find_all('tr'):
                max_cols = max(max_cols, len(row.find_all(['td', 'th'])))
            
            # 選擇一個有效的索引位置
            for idx in net_position_candidates:
                if idx < max_cols:
                    net_position_idx = idx
                    break
            
            if net_position_idx == -1:
                logger.error("無法確定淨部位欄位位置")
                return result
        
        # 遍歷表格尋找臺股期貨和小型臺指期貨的外資部位
        contract_type = None
        for row in target_table.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) < net_position_idx + 1:
                continue
            
            # 檢查是否為契約標題行
            first_cell_text = cells[0].text.strip() if cells else ""
            if '臺股期貨' in first_cell_text or 'TX' in first_cell_text:
                contract_type = '臺股期貨'
                continue
            elif '小型臺指期貨' in first_cell_text or 'MTX' in first_cell_text:
                contract_type = '小型臺指期貨'
                continue
            
            # 檢查是否為外資的資料行
            if len(cells) > 1 and contract_type:
                identity_cell = cells[1].text.strip() if len(cells) > 1 else ""
                # 擴大匹配條件，包括可能的不同表示方式
                if ('外資' in identity_cell or 'Foreign' in identity_cell) and '外資自營' not in identity_cell:
                    # 取得淨部位數值
                    if net_position_idx < len(cells):
                        # 嘗試從淨部位欄位取得數值
                        net_cell = cells[net_position_idx]
                        
                        # 檢查是否有font標籤
                        font_tag = net_cell.find('font')
                        if font_tag:
                            net_text = font_tag.text.strip()
                        else:
                            net_text = net_cell.text.strip()
                        
                        # 移除千分位逗號並處理可能的空值
                        net_text = net_text.replace(',', '')
                        if net_text and net_text != '-' and net_text != '--':
                            net_position = safe_int(net_text)
                            
                            # 根據契約類型存入結果
                            if contract_type == '臺股期貨' and net_position != 0:
                                result['foreign_tx_net'] = net_position
                                logger.info(f"找到外資臺股期貨淨部位: {net_position}")
                            elif contract_type == '小型臺指期貨' and net_position != 0:
                                result['foreign_mtx_net'] = net_position
                                logger.info(f"找到外資小型臺指期貨淨部位: {net_position}")
        
        return result
    
    except Exception as e:
        logger.error(f"獲取三大法人期貨持倉數據時出錯: {str(e)}")
        return default_institutional_futures_data()

def default_institutional_futures_data():
    """返回默認的三大法人期貨部位數據"""
    return {
        'foreign_tx_net': 0,
        'foreign_mtx_net': 0
    }

# 主程序測試
if __name__ == "__main__":
    result = get_institutional_futures_data()
    print(result)
