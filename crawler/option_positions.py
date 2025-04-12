"""
選擇權持倉爬蟲模組 - 新版
專門處理選擇權持倉資料，包含外資買權和賣權淨未平倉
"""
import logging
import requests
import re
from bs4 import BeautifulSoup
from datetime import datetime
from .utils import get_tw_stock_date, safe_int, get_html_content

# 設定日誌
logger = logging.getLogger(__name__)

def get_option_positions_data():
    """
    獲取選擇權持倉資料，專注於外資買權和賣權淨未平倉
    
    Returns:
        dict: 包含選擇權持倉資料的字典
    """
    try:
        # 取得日期
        date = get_tw_stock_date('%Y%m%d')
        
        # 使用主要方法獲取資料
        result = get_option_positions_by_date(date)
        
        # 記錄結果
        logger.info(f"選擇權持倉資料: 外資買權={result['foreign_call_net']}, 外資賣權={result['foreign_put_net']}")
        
        return result
    
    except Exception as e:
        logger.error(f"獲取選擇權持倉資料時出錯: {str(e)}")
        return default_option_positions_data()

def get_option_positions_by_date(date):
    """
    獲取特定日期的選擇權持倉資料
    
    Args:
        date: 日期字符串，格式為YYYYMMDD
        
    Returns:
        dict: 包含選擇權持倉資料的字典
    """
    try:
        # 使用Excel格式URL以獲取更穩定的資料
        url = "https://www.taifex.com.tw/cht/3/callsAndPutsDateExcel"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.taifex.com.tw/cht/3/callsAndPutsDate'
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
        result = default_option_positions_data()
        
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
        
        # 查找所有表格 (Excel格式頁面可能沒有class='table_f')
        tables = soup.find_all('table')
        if not tables:
            logger.error("找不到任何表格")
            return result
        
        # 尋找包含選擇權持倉資訊的表格
        target_table = None
        
        for table in tables:
            table_text = table.text.lower()
            if ('臺指選擇權' in table_text or '台指選擇權' in table_text) and ('買權' in table_text or '賣權' in table_text):
                target_table = table
                break
        
        if not target_table:
            logger.error("找不到包含選擇權持倉資訊的表格")
            
            # 嘗試更寬鬆的匹配
            for table in tables:
                if '選擇權' in table.text and ('買權' in table.text or '賣權' in table.text or 'call' in table.text.lower() or 'put' in table.text.lower()):
                    target_table = table
                    logger.info("找到可能包含選擇權資料的表格")
                    break
                    
            if not target_table:
                return result
        
        # 建立表頭映射
        header_mapping = {}
        header_rows = target_table.find_all('tr')[:2]  # 可能有多行表頭
        
        for header_row in header_rows:
            headers = header_row.find_all(['th', 'td'])
            for idx, header in enumerate(headers):
                header_text = header.text.strip().lower()
                if '買賣差額' in header_text or '買賣淨額' in header_text or 'net' in header_text:
                    # 可能有多個包含相關文字的欄位，尋找包含「口數」的欄位
                    if '口數' in header_text or '部位' in header_text or 'position' in header_text:
                        header_mapping['net_position'] = idx
                        break
        
        # 如果沒有找到明確的淨部位欄位，嘗試另一種方法
        if 'net_position' not in header_mapping:
            logger.warning("找不到明確的淨部位欄位，嘗試尋找可能的位置")
            
            # 計算表格列數
            max_cols = 0
            for row in target_table.find_all('tr'):
                max_cols = max(max_cols, len(row.find_all(['td', 'th'])))
            
            # 通常淨部位在後半部，嘗試幾個可能的位置
            # 一般的選擇權表格可能有：序號(0)、商品(1)、權別(2)、身份(3)、買方口數(4)、買方金額(5)、賣方口數(6)、賣方金額(7)、買賣差額口數(8)、買賣差額金額(9)
            # 或者後面還有未平倉相關欄位
            possible_positions = [8, 10, 14]  # 可能的淨部位欄位索引
            
            for pos in possible_positions:
                if pos < max_cols:
                    header_mapping['net_position'] = pos
                    logger.info(f"使用預設欄位索引 {pos} 作為淨部位欄位")
                    break
        
        if 'net_position' not in header_mapping:
            # 使用預設索引
            logger.warning("無法確定淨部位欄位位置，使用預設索引")
            header_mapping['net_position'] = 8
        
        # 尋找買權和賣權區段中的外資行
        call_found = False
        put_found = False
        
        for row in target_table.find_all('tr')[1:]:  # 跳過表頭行
            cells = row.find_all('td')
            
            # 檢查是否有足夠的單元格
            if len(cells) <= header_mapping.get('net_position', 8):
                continue
            
            # 讀取整行文字，以便更寬鬆地分析
            row_text = ' '.join([cell.text.strip() for cell in cells])
            
            # 識別所在區段和是否為外資行
            is_call = False
            is_put = False
            is_foreign = False
            
            if '買權' in row_text.lower() or 'call' in row_text.lower():
                is_call = True
            elif '賣權' in row_text.lower() or 'put' in row_text.lower():
                is_put = True
            
            if '外資' in row_text and '外資自營' not in row_text:
                is_foreign = True
            
            # 如果是外資且在買權或賣權區段
            if is_foreign and (is_call or is_put):
                net_idx = header_mapping.get('net_position', 8)
                if net_idx < len(cells):
                    net_cell = cells[net_idx]
                    
                    # 嘗試取得數值
                    font_tag = net_cell.find('font')
                    if font_tag:
                        net_text = font_tag.text.strip()
                    else:
                        net_text = net_cell.text.strip()
                    
                    # 移除千分位逗號與其他非數字字符
                    net_text = net_text.replace(',', '')
                    
                    # 確保有數值並轉換
                    if net_text and net_text != '-' and net_text != '--':
                        try:
                            net_position = safe_int(net_text)
                            
                            # 存入對應類型
                            if is_call:
                                result['foreign_call_net'] = net_position
                                call_found = True
                                logger.info(f"找到外資買權淨部位: {net_position}")
                            elif is_put:
                                result['foreign_put_net'] = net_position
                                put_found = True
                                logger.info(f"找到外資賣權淨部位: {net_position}")
                        except Exception as e:
                            logger.error(f"轉換淨部位值時出錯: {str(e)}")
        
        return result
    
    except Exception as e:
        logger.error(f"獲取選擇權持倉數據時出錯: {str(e)}")
        return default_option_positions_data()

def default_option_positions_data():
    """返回默認的選擇權持倉資料"""
    return {
        'foreign_call_net': 0,
        'foreign_put_net': 0
    }

# 主程序測試
if __name__ == "__main__":
    result = get_option_positions_data()
    print(result)
