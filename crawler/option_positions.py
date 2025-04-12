"""
選擇權持倉資料爬蟲模組 - 改進版
"""
import logging
import requests
import json
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
        
        # 嘗試使用標準方法
        today_data = get_option_positions_data_by_date(date)
        
        # 檢查是否成功獲取有效數據
        if not is_valid_option_data(today_data):
            logger.warning(f"無法獲取 {date} 的選擇權持倉有效資料，嘗試使用替代方法")
            
            # 使用替代方法
            alt_data = get_option_positions_alternative(date)
            if is_valid_option_data(alt_data):
                today_data = alt_data
                logger.info("使用替代方法成功獲取選擇權持倉資料")
            else:
                # 如果替代方法也失敗，嘗試獲取前一個交易日的數據
                yesterday = (datetime.strptime(date, '%Y%m%d') - timedelta(days=1)).strftime('%Y%m%d')
                logger.warning(f"無法獲取 {date} 的選擇權持倉資料，嘗試獲取 {yesterday} 的數據")
                return get_option_positions_data_by_date(yesterday)
        
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
        
        logger.info(f"選擇權持倉資料: 外資Call淨部位={today_data['foreign_call_net']}, 外資Put淨部位={today_data['foreign_put_net']}")
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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.taifex.com.tw/cht/3/largeTraderOptQry'
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
            return default_option_positions_data(date)
        
        result = extract_option_positions_data(soup, date)
        
        # 檢查是否獲取到有效數據
        if not is_valid_option_data(result):
            logger.warning(f"提取 {date} 的選擇權持倉資料失敗，數據無效")
            return default_option_positions_data(date)
            
        return result
    
    except Exception as e:
        logger.error(f"獲取 {date} 的選擇權持倉資料時出錯: {str(e)}")
        return default_option_positions_data(date)

def get_option_positions_alternative(date):
    """
    使用替代方法獲取選擇權持倉資料
    
    Args:
        date: 日期字符串，格式為YYYYMMDD
        
    Returns:
        dict: 包含選擇權持倉資料的字典
    """
    try:
        # 使用API格式的URL
        url = f"https://www.taifex.com.tw/cht/3/largeTraderOptQryDown?queryDate={date[:4]}/{date[4:6]}/{date[6:]}&commodityId=TXO"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.taifex.com.tw/cht/3/largeTraderOptQry'
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
            'foreign_call_buy': 0,
            'foreign_call_sell': 0,
            'foreign_call_net': 0,
            'foreign_put_buy': 0,
            'foreign_put_sell': 0,
            'foreign_put_net': 0,
            'foreign_call_net_change': 0,
            'foreign_put_net_change': 0
        }
        
        # 解析CSV格式數據
        if len(lines) < 2:
            logger.error("選擇權持倉API返回數據不足")
            return result
        
        # 尋找外資資料行
        call_found = False
        put_found = False
        
        for line in lines[1:]:  # 跳過標題行
            fields = line.strip().split(',')
            
            if len(fields) < 6:
                continue
            
            category = fields[0].strip() if len(fields) > 0 else ""
            option_type = fields[1].strip() if len(fields) > 1 else ""
            
            # 檢查是否為外資資料
            if ('外資' in category or 'foreign' in category.lower()) and not ('外資自營' in category):
                # 買權(Call)數據
                if 'call' in option_type.lower() or '買權' in option_type:
                    try:
                        buy_position = safe_int(fields[2].strip().replace(',', ''))
                        sell_position = safe_int(fields[3].strip().replace(',', ''))
                        net_position = buy_position - sell_position
                        
                        result['foreign_call_buy'] = buy_position
                        result['foreign_call_sell'] = sell_position
                        result['foreign_call_net'] = net_position
                        call_found = True
                    except:
                        logger.error("解析外資買權(Call)數據時出錯")
                
                # 賣權(Put)數據
                elif 'put' in option_type.lower() or '賣權' in option_type:
                    try:
                        buy_position = safe_int(fields[2].strip().replace(',', ''))
                        sell_position = safe_int(fields[3].strip().replace(',', ''))
                        net_position = buy_position - sell_position
                        
                        result['foreign_put_buy'] = buy_position
                        result['foreign_put_sell'] = sell_position
                        result['foreign_put_net'] = net_position
                        put_found = True
                    except:
                        logger.error("解析外資賣權(Put)數據時出錯")
            
            # 如果已經找到買權和賣權，提前結束循環
            if call_found and put_found:
                break
        
        if not (call_found or put_found):
            logger.warning("替代方法未找到選擇權持倉外資資料")
            
            # 嘗試使用另一種解析方式
            for line in lines[1:]:
                fields = line.strip().split(',')
                
                if len(fields) < 6:
                    continue
                
                column1 = fields[0].strip() if len(fields) > 0 else ""
                column2 = fields[1].strip() if len(fields) > 1 else ""
                
                # 檢查是否包含關鍵字
                if ('外資' in column1 or 'foreign' in column1.lower() or 
                    '外資' in column2 or 'foreign' in column2.lower()):
                    
                    # 檢查是否為買權或賣權
                    if ('call' in line.lower() or '買權' in line or '買' in line):
                        try:
                            # 查找數字欄位
                            for i in range(2, len(fields)):
                                if fields[i].strip() and fields[i].strip().replace(',', '').replace('-', '').isdigit():
                                    # 假設找到的第一個數字是買方，第二個是賣方
                                    if 'foreign_call_buy' not in locals():
                                        result['foreign_call_buy'] = safe_int(fields[i].strip().replace(',', ''))
                                    elif 'foreign_call_sell' not in locals():
                                        result['foreign_call_sell'] = safe_int(fields[i].strip().replace(',', ''))
                                        result['foreign_call_net'] = result['foreign_call_buy'] - result['foreign_call_sell']
                                        call_found = True
                                        break
                        except:
                            logger.error("替代解析方式處理買權數據時出錯")
                    
                    elif ('put' in line.lower() or '賣權' in line or '賣' in line):
                        try:
                            # 查找數字欄位
                            for i in range(2, len(fields)):
                                if fields[i].strip() and fields[i].strip().replace(',', '').replace('-', '').isdigit():
                                    # 假設找到的第一個數字是買方，第二個是賣方
                                    if 'foreign_put_buy' not in locals():
                                        result['foreign_put_buy'] = safe_int(fields[i].strip().replace(',', ''))
                                    elif 'foreign_put_sell' not in locals():
                                        result['foreign_put_sell'] = safe_int(fields[i].strip().replace(',', ''))
                                        result['foreign_put_net'] = result['foreign_put_buy'] - result['foreign_put_sell']
                                        put_found = True
                                        break
                        except:
                            logger.error("替代解析方式處理賣權數據時出錯")
        
        logger.info(f"替代方法獲取選擇權持倉資料: 外資Call={result['foreign_call_net']}, 外資Put={result['foreign_put_net']}")
        
        # 檢查結果是否有效
        if not (call_found or put_found):
            # 嘗試第三種方法：使用JSON API
            json_result = get_option_positions_json_api(date)
            if json_result and is_valid_option_data(json_result):
                return json_result
        
        return result
    
    except Exception as e:
        logger.error(f"使用替代方法獲取選擇權持倉資料時出錯: {str(e)}")
        return default_option_positions_data(date)

def get_option_positions_json_api(date):
    """
    使用JSON API獲取選擇權持倉資料
    
    Args:
        date: 日期字符串，格式為YYYYMMDD
        
    Returns:
        dict: 包含選擇權持倉資料的字典
    """
    try:
        # 使用API格式的URL
        url = f"https://www.taifex.com.tw/cht/3/largeTraderOptDataDown?queryStartDate={date[:4]}/{date[4:6]}/{date[6:]}&queryEndDate={date[:4]}/{date[4:6]}/{date[6:]}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': 'https://www.taifex.com.tw/cht/3/largeTraderOptQry'
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
            'foreign_call_buy': 0,
            'foreign_call_sell': 0,
            'foreign_call_net': 0,
            'foreign_put_buy': 0,
            'foreign_put_sell': 0,
            'foreign_put_net': 0,
            'foreign_call_net_change': 0,
            'foreign_put_net_change': 0
        }
        
        # 解析JSON數據
        if not data or not isinstance(data, dict) or 'data' not in data:
            logger.error("JSON API返回無效數據結構")
            return result
        
        for item in data.get('data', []):
            option_type = item.get('optionType', '')
            trader_type = item.get('traderType', '')
            
            # 檢查是否為外資資料
            if ('外資' in trader_type or 'foreign' in trader_type.lower()) and not ('外資自營' in trader_type):
                # 買權(Call)數據
                if 'call' in option_type.lower() or '買權' in option_type:
                    result['foreign_call_buy'] = safe_int(item.get('buyPosition', 0))
                    result['foreign_call_sell'] = safe_int(item.get('sellPosition', 0))
                    result['foreign_call_net'] = safe_int(item.get('netPosition', 0))
                
                # 賣權(Put)數據
                elif 'put' in option_type.lower() or '賣權' in option_type:
                    result['foreign_put_buy'] = safe_int(item.get('buyPosition', 0))
                    result['foreign_put_sell'] = safe_int(item.get('sellPosition', 0))
                    result['foreign_put_net'] = safe_int(item.get('netPosition', 0))
        
        logger.info(f"JSON API獲取選擇權持倉資料: 外資Call={result['foreign_call_net']}, 外資Put={result['foreign_put_net']}")
        
        return result
    
    except Exception as e:
        logger.error(f"使用JSON API獲取選擇權持倉資料時出錯: {str(e)}")
        return None

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
        call_found = False
        put_found = False
        
        for i, table in enumerate(tables):
            rows = table.find_all('tr')
            
            # 檢查是否為買權(Call)或賣權(Put)表格
            header_row = rows[0] if rows else None
            if not header_row:
                continue
            
            header_text = header_row.text.strip().lower()
            is_call_table = 'call' in header_text or '買權' in header_text
            is_put_table = 'put' in header_text or '賣權' in header_text
            
            if not (is_call_table or is_put_table):
                continue
            
            # 遍歷每一行，尋找外資資料
            for row in rows:
                cells = row.find_all('td')
                if len(cells) < 6:
                    continue
                
                # 檢查是否為外資資料行
                first_cell_text = cells[0].text.strip()
                if ('外資' not in first_cell_text and 'foreign' not in first_cell_text.lower()) or '外資自營' in first_cell_text:
                    continue
                
                # 提取買方、賣方部位
                try:
                    buy_text = cells[2].text.strip().replace(',', '')
                    sell_text = cells[5].text.strip().replace(',', '')
                    
                    # 檢查是否有效數字
                    if not buy_text or not sell_text:
                        continue
                    
                    buy_position = safe_int(buy_text)
                    sell_position = safe_int(sell_text)
                    net_position = buy_position - sell_position
                    
                    # 儲存資料
                    if is_call_table:
                        result['foreign_call_buy'] = buy_position
                        result['foreign_call_sell'] = sell_position
                        result['foreign_call_net'] = net_position
                        call_found = True
                    elif is_put_table:
                        result['foreign_put_buy'] = buy_position
                        result['foreign_put_sell'] = sell_position
                        result['foreign_put_net'] = net_position
                        put_found = True
                except:
                    # 如果解析失敗，嘗試其他單元格
                    try:
                        # 有些表格可能淨部位直接顯示
                        if len(cells) >= 9:
                            net_text = cells[8].text.strip().replace(',', '')
                            if net_text:
                                net_position = safe_int(net_text)
                                if is_call_table:
                                    result['foreign_call_net'] = net_position
                                    call_found = True
                                elif is_put_table:
                                    result['foreign_put_net'] = net_position
                                    put_found = True
                    except:
                        pass
        
        if not (call_found or put_found):
            logger.warning("未找到選擇權持倉外資資料")
        else:
            logger.info(f"外資買權淨部位: {result['foreign_call_net']}, 外資賣權淨部位: {result['foreign_put_net']}")
        
        return result
    
    except Exception as e:
        logger.error(f"解析選擇權持倉資料時出錯: {str(e)}")
        return default_option_positions_data(date)

def is_valid_option_data(data):
    """
    檢查選擇權持倉資料是否有效
    
    Args:
        data: 選擇權持倉資料字典
        
    Returns:
        bool: 資料是否有效
    """
    if not data:
        return False
    
    # 檢查是否至少有一個非零值
    if data.get('foreign_call_net', 0) != 0 or data.get('foreign_put_net', 0) != 0:
        return True
    
    return False

def default_option_positions_data(date=None):
    """返回默認的選擇權持倉資料"""
    if date is None:
        date = get_tw_stock_date('%Y%m%d')
        
    return {
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

# 主程序測試
if __name__ == "__main__":
    result = get_option_positions_data()
    print(result)
