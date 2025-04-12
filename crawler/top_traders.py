"""
十大交易人和特定法人持倉資料爬蟲模組 - 改進版
"""
import logging
import requests
import json
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
        
        # 嘗試使用標準方法
        today_data = get_top_traders_data_by_date(date)
        
        # 檢查是否成功獲取有效數據
        if not is_valid_top_traders_data(today_data):
            logger.warning(f"無法獲取 {date} 的十大交易人有效資料，嘗試使用替代方法")
            
            # 使用替代方法
            alt_data = get_top_traders_alternative(date)
            if is_valid_top_traders_data(alt_data):
                today_data = alt_data
                logger.info("使用替代方法成功獲取十大交易人資料")
            else:
                # 如果替代方法也失敗，嘗試獲取前一個交易日的數據
                yesterday = (datetime.strptime(date, '%Y%m%d') - timedelta(days=1)).strftime('%Y%m%d')
                logger.warning(f"無法獲取 {date} 的十大交易人資料，嘗試獲取 {yesterday} 的數據")
                return get_top_traders_data_by_date(yesterday)
        
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
        
        logger.info(f"十大交易人資料: 交易人淨部位={today_data['top10_traders_net']}, 特定法人淨部位={today_data['top10_specific_net']}")
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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.taifex.com.tw/cht/3/largeTraderFutQry'
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
            return default_top_traders_data(date)
        
        result = extract_top_traders_data(soup, date)
        
        # 檢查是否獲取到有效數據
        if not is_valid_top_traders_data(result):
            logger.warning(f"提取 {date} 的十大交易人資料失敗，數據無效")
            return default_top_traders_data(date)
            
        return result
    
    except Exception as e:
        logger.error(f"獲取 {date} 的十大交易人資料時出錯: {str(e)}")
        return default_top_traders_data(date)

def get_top_traders_alternative(date):
    """
    使用替代方法獲取十大交易人和特定法人持倉資料
    
    Args:
        date: 日期字符串，格式為YYYYMMDD
        
    Returns:
        dict: 包含十大交易人和特定法人持倉資料的字典
    """
    try:
        # 使用API格式的URL
        url = f"https://www.taifex.com.tw/cht/3/largeTraderFutQryDown?queryDate={date[:4]}/{date[4:6]}/{date[6:]}&commodityId=TXF"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.taifex.com.tw/cht/3/largeTraderFutQry'
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        # 嘗試使用不同的編碼
        for encoding in ['utf-8', 'big5', 'cp950']:
            try:
                response.encoding = encoding
                lines = response.text.strip().split('\n')
                break
            except:
                continue
        
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
        
        # 解析CSV格式數據
        if len(lines) < 2:
            logger.error("十大交易人API返回數據不足")
            return result
        
        traders_found = False
        specific_found = False
        
        for line in lines[1:]:  # 跳過標題行
            fields = line.strip().split(',')
            
            if len(fields) < 6:
                continue
            
            category = fields[0].strip() if len(fields) > 0 else ""
            
            # 檢查是否為十大交易人資料
            if '十大交易人' in category and '多方' in category:
                try:
                    buy_position = safe_int(fields[2].strip().replace(',', ''))
                    result['top10_traders_buy'] = buy_position
                except:
                    logger.error("解析十大交易人多方數據時出錯")
            
            elif '十大交易人' in category and '空方' in category:
                try:
                    sell_position = safe_int(fields[2].strip().replace(',', ''))
                    result['top10_traders_sell'] = sell_position
                    # 計算淨部位
                    result['top10_traders_net'] = result['top10_traders_buy'] - result['top10_traders_sell']
                    traders_found = True
                except:
                    logger.error("解析十大交易人空方數據時出錯")
            
            # 檢查是否為十大特定法人資料
            elif '十大特定法人' in category and '多方' in category:
                try:
                    buy_position = safe_int(fields[2].strip().replace(',', ''))
                    result['top10_specific_buy'] = buy_position
                except:
                    logger.error("解析十大特定法人多方數據時出錯")
            
            elif '十大特定法人' in category and '空方' in category:
                try:
                    sell_position = safe_int(fields[2].strip().replace(',', ''))
                    result['top10_specific_sell'] = sell_position
                    # 計算淨部位
                    result['top10_specific_net'] = result['top10_specific_buy'] - result['top10_specific_sell']
                    specific_found = True
                except:
                    logger.error("解析十大特定法人空方數據時出錯")
        
        if not (traders_found or specific_found):
            logger.warning("替代方法未找到十大交易人或特定法人資料")
            
            # 嘗試使用JSON API
            json_result = get_top_traders_json_api(date)
            if json_result and is_valid_top_traders_data(json_result):
                return json_result
        
        logger.info(f"替代方法獲取十大交易人資料: 十大交易人={result['top10_traders_net']}, 十大特定法人={result['top10_specific_net']}")
        
        return result
    
    except Exception as e:
        logger.error(f"使用替代方法獲取十大交易人資料時出錯: {str(e)}")
        return default_top_traders_data(date)

def get_top_traders_json_api(date):
    """
    使用JSON API獲取十大交易人和特定法人持倉資料
    
    Args:
        date: 日期字符串，格式為YYYYMMDD
        
    Returns:
        dict: 包含十大交易人和特定法人持倉資料的字典
    """
    try:
        # 使用API格式的URL
        url = f"https://www.taifex.com.tw/cht/3/largeTraderFutDataDown?queryStartDate={date[:4]}/{date[4:6]}/{date[6:]}&queryEndDate={date[:4]}/{date[4:6]}/{date[6:]}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': 'https://www.taifex.com.tw/cht/3/largeTraderFutQry'
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        try:
            data = response.json()
        except:
            logger.error("JSON API返回的數據不是有效的JSON格式")
            return None
        
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
        
        # 解析JSON數據
        if not data or not isinstance(data, dict) or 'data' not in data:
            logger.error("JSON API返回無效數據結構")
            return result
        
        for item in data.get('data', []):
            category = item.get('category', '')
            
            # 檢查是否為十大交易人資料
            if '十大交易人-多方' in category:
                result['top10_traders_buy'] = safe_int(item.get('buyPosition', 0))
            elif '十大交易人-空方' in category:
                result['top10_traders_sell'] = safe_int(item.get('sellPosition', 0))
            
            # 檢查是否為十大特定法人資料
            elif '十大特定法人-多方' in category:
                result['top10_specific_buy'] = safe_int(item.get('buyPosition', 0))
            elif '十大特定法人-空方' in category:
                result['top10_specific_sell'] = safe_int(item.get('sellPosition', 0))
        
        # 計算淨部位
        result['top10_traders_net'] = result['top10_traders_buy'] - result['top10_traders_sell']
        result['top10_specific_net'] = result['top10_specific_buy'] - result['top10_specific_sell']
        
        logger.info(f"JSON API獲取十大交易人資料: 十大交易人={result['top10_traders_net']}, 十大特定法人={result['top10_specific_net']}")
        
        return result
    
    except Exception as e:
        logger.error(f"使用JSON API獲取十大交易人資料時出錯: {str(e)}")
        return None

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
                continue  # 這行內容不足，跳過
            
            # 獲取第一個單元格文字
            first_cell_text = cells[0].text.strip()
            
            # 十大交易人多方(buy)部位
            if '十大交易人-多方' in first_cell_text or ('十大交易人' in first_cell_text and '多方' in first_cell_text):
                try:
                    # 嘗試不同可能的列索引
                    for i in range(2, min(6, len(cells))):
                        text = cells[i].text.strip().replace(',', '')
                        if text and text.isdigit():
                            buy_position = safe_int(text)
                            result['top10_traders_buy'] = buy_position
                            break
                except:
                    logger.error("解析十大交易人多方部位時出錯")
            
            # 十大交易人空方(sell)部位
            elif '十大交易人-空方' in first_cell_text or ('十大交易人' in first_cell_text and '空方' in first_cell_text):
                try:
                    # 嘗試不同可能的列索引
                    for i in range(2, min(6, len(cells))):
                        text = cells[i].text.strip().replace(',', '')
                        if text and text.isdigit():
                            sell_position = safe_int(text)
                            result['top10_traders_sell'] = sell_position
                            break
                except:
                    logger.error("解析十大交易人空方部位時出錯")
            
            # 十大特定法人多方(buy)部位
            elif '十大特定法人-多方' in first_cell_text or ('十大特定法人' in first_cell_text and '多方' in first_cell_text):
                try:
                    # 嘗試不同可能的列索引
                    for i in range(2, min(6, len(cells))):
                        text = cells[i].text.strip().replace(',', '')
                        if text and text.isdigit():
                            buy_position = safe_int(text)
                            result['top10_specific_buy'] = buy_position
                            break
                except:
                    logger.error("解析十大特定法人多方部位時出錯")
            
            # 十大特定法人空方(sell)部位
            elif '十大特定法人-空方' in first_cell_text or ('十大特定法人' in first_cell_text and '空方' in first_cell_text):
                try:
                    # 嘗試不同可能的列索引
                    for i in range(2, min(6, len(cells))):
                        text = cells[i].text.strip().replace(',', '')
                        if text and text.isdigit():
                            sell_position = safe_int(text)
                            result['top10_specific_sell'] = sell_position
                            break
                except:
                    logger.error("解析十大特定法人空方部位時出錯")
        
        # 計算淨部位
        result['top10_traders_net'] = result['top10_traders_buy'] - result['top10_traders_sell']
        result['top10_specific_net'] = result['top10_specific_buy'] - result['top10_specific_sell']
        
        # 檢查是否找到數據
        if result['top10_traders_buy'] == 0 and result['top10_traders_sell'] == 0 and result['top10_specific_buy'] == 0 and result['top10_specific_sell'] == 0:
            logger.warning("無法從表格解析出十大交易人和特定法人資料")
            
            # 嘗試使用另一種解析方式
            for row in rows:
                cells = row.find_all('td')
                if len(cells) < 3:
                    continue
                
                # 查找包含特定關鍵字的行
                row_text = ' '.join([cell.text.strip() for cell in cells])
                
                if '十大交易人' in row_text and ('多方' in row_text or '買方' in row_text):
                    # 嘗試找出數字
                    for cell in cells:
                        cell_text = cell.text.strip().replace(',', '')
                        if cell_text.isdigit():
                            result['top10_traders_buy'] = safe_int(cell_text)
                            break
                
                elif '十大交易人' in row_text and ('空方' in row_text or '賣方' in row_text):
                    # 嘗試找出數字
                    for cell in cells:
                        cell_text = cell.text.strip().replace(',', '')
                        if cell_text.isdigit():
                            result['top10_traders_sell'] = safe_int(cell_text)
                            break
                
                elif '十大特定法人' in row_text and ('多方' in row_text or '買方' in row_text):
                    # 嘗試找出數字
                    for cell in cells:
                        cell_text = cell.text.strip().replace(',', '')
                        if cell_text.isdigit():
                            result['top10_specific_buy'] = safe_int(cell_text)
                            break
                
                elif '十大特定法人' in row_text and ('空方' in row_text or '賣方' in row_text):
                    # 嘗試找出數字
                    for cell in cells:
                        cell_text = cell.text.strip().replace(',', '')
                        if cell_text.isdigit():
                            result['top10_specific_sell'] = safe_int(cell_text)
                            break
            
            # 重新計算淨部位
            result['top10_traders_net'] = result['top10_traders_buy'] - result['top10_traders_sell']
            result['top10_specific_net'] = result['top10_specific_buy'] - result['top10_specific_sell']
        
        logger.info(f"十大交易人淨部位: {result['top10_traders_net']}, 十大特定法人淨部位: {result['top10_specific_net']}")
        
        return result
    
    except Exception as e:
        logger.error(f"解析十大交易人資料時出錯: {str(e)}")
        return default_top_traders_data(date)

def is_valid_top_traders_data(data):
    """
    檢查十大交易人和特定法人持倉資料是否有效
    
    Args:
        data: 十大交易人和特定法人持倉資料字典
        
    Returns:
        bool: 資料是否有效
    """
    if not data:
        return False
    
    # 檢查是否至少有一個非零值
    return (data.get('top10_traders_net', 0) != 0 or data.get('top10_specific_net', 0) != 0)

def default_top_traders_data(date=None):
    """返回默認的十大交易人和特定法人持倉資料"""
    if date is None:
        date = get_tw_stock_date('%Y%m%d')
        
    return {
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

# 主程序測試
if __name__ == "__main__":
    result = get_top_traders_data()
    print(result)
