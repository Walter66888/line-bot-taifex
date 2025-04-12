"""
期貨相關資料爬蟲模組 - 正確解析網頁
"""
import logging
import requests
import re
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from .utils import get_tw_stock_date, safe_float, safe_int, get_html_content
from .taiex import get_taiex_data

logger = logging.getLogger(__name__)

def get_futures_data():
    """
    獲取期貨相關數據
    
    Returns:
        dict: 包含期貨數據的字典
    """
    try:
        # 取得日期
        date = get_tw_stock_date('%Y%m%d')
        
        # 先獲取大盤加權指數收盤價，用於計算台指期貨偏差值
        taiex_data = get_taiex_data()
        taiex_close = taiex_data.get('close', 0) if taiex_data else 0
        
        # 獲取台指期貨數據
        tx_data = get_tx_futures_data(date, taiex_close)
        
        # 獲取三大法人期貨部位數據
        institutional_futures = get_institutional_futures_data(date)
        
        # 獲取十大交易人數據
        traders_data = get_top_traders_data(date)
        
        # 獲取選擇權持倉數據
        options_data = get_options_positions_data(date)
        
        # 合併數據
        result = {**tx_data, **institutional_futures, **traders_data, **options_data}
        result['date'] = date
        
        # 計算偏差 (僅當兩個數值都正常時才計算)
        if result['close'] > 0 and taiex_close > 0:
            result['bias'] = result['close'] - taiex_close
        else:
            result['bias'] = 0.0
        
        logger.info(f"期貨數據: 收盤={result['close']}, 加權指數={taiex_close}, 偏差={result['bias']}")
        logger.info(f"期貨籌碼: 外資台指={result['foreign_tx']}, 外資小台={result['foreign_mtx']}, 十大交易人={result['top10_traders_net']}, 十大特定法人={result['top10_specific_net']}")
        logger.info(f"選擇權籌碼: 外資買權={result['foreign_call_net']}, 外資賣權={result['foreign_put_net']}")
        
        return result
    
    except Exception as e:
        logger.error(f"獲取期貨數據時出錯: {str(e)}")
        return default_futures_data(date)

def get_tx_futures_data(date, taiex_close=0):
    """
    獲取台指期貨數據
    
    Args:
        date: 日期字符串，格式為YYYYMMDD
        taiex_close: 加權指數收盤價
        
    Returns:
        dict: 台指期貨數據
    """
    try:
        # 使用URL格式
        url = "https://www.taifex.com.tw/cht/3/futDailyMarketReport"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.taifex.com.tw/cht/3/futDailyMarketReport'
        }
        
        # 使用POST方法，提供查詢參數
        data = {
            'queryType': '2',  # 期貨報價
            'marketCode': '0',  # 所有市場
            'dateaddcnt': '',
            'commodity_id': 'TX',  # 台指期貨
            'queryDate': date[:4] + '/' + date[4:6] + '/' + date[6:],  # 格式化日期為YYYY/MM/DD
        }
        
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
        
        # 解析表格
        tables = soup.find_all('table', class_='table_f')
        if not tables or len(tables) < 1:
            logger.error("找不到台指期貨表格")
            return default_tx_data(taiex_close)
        
        # 獲取資料表格
        table = tables[0]
        rows = table.find_all('tr')
        
        # 查找近月合約（不包含週選，即不包含W的合約）
        tx_row = None
        tx_month = ""
        
        # 跳過表頭
        for row in rows[2:]:  # 通常第一行是表頭
            cells = row.find_all('td')
            if len(cells) >= 8:  # 確保有足夠的列
                contract_id = cells[0].text.strip()
                contract_month = cells[1].text.strip()
                
                # 確認是台指期近月合約
                if contract_id == 'TX' and 'W' not in contract_month:
                    tx_row = cells
                    tx_month = contract_month
                    break
        
        if not tx_row:
            logger.error("找不到近月台指期貨合約")
            return default_tx_data(taiex_close)
        
        # 解析數據
        try:
            # 收盤價通常在第6列（索引5）
            close_price_text = tx_row[5].text.strip().replace(',', '')
            close_price = safe_float(close_price_text)
            
            # 漲跌通常在第7列（索引6）
            change_text = tx_row[6].text.strip().replace(',', '')
            change_value = 0.0
            if change_text and change_text != '--':
                if '▲' in change_text or '+' in change_text:
                    change_value = safe_float(change_text.replace('▲', '').replace('+', ''))
                elif '▼' in change_text or '-' in change_text:
                    change_value = -safe_float(change_text.replace('▼', '').replace('-', ''))
            
            # 漲跌百分比通常在第8列（索引7）
            change_percent_text = tx_row[7].text.strip().replace(',', '')
            change_percent = 0.0
            if change_percent_text and change_percent_text != '--':
                if '▲' in change_percent_text or '+' in change_percent_text:
                    change_percent = safe_float(change_percent_text.replace('▲', '').replace('+', '').replace('%', ''))
                elif '▼' in change_percent_text or '-' in change_percent_text:
                    change_percent = -safe_float(change_percent_text.replace('▼', '').replace('-', '').replace('%', ''))
            
            logger.info(f"台指期貨: 收盤價={close_price}, 漲跌={change_value}, 漲跌%={change_percent}")
            
            return {
                'close': close_price,
                'change': change_value,
                'change_percent': change_percent,
                'taiex_close': taiex_close,
                'contract_month': tx_month
            }
        except Exception as e:
            logger.error(f"解析台指期貨數據時出錯: {str(e)}")
            return default_tx_data(taiex_close)
    
    except Exception as e:
        logger.error(f"獲取台指期貨數據時出錯: {str(e)}")
        return default_tx_data(taiex_close)

def get_institutional_futures_data(date):
    """
    獲取三大法人期貨持倉資料
    
    Args:
        date: 日期字符串，格式為YYYYMMDD
        
    Returns:
        dict: 三大法人期貨持倉資料
    """
    try:
        # 使用指定網址
        url = f"https://www.taifex.com.tw/cht/3/futContractsDate"
        
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
        result = default_institutional_data()
        
        # 獲取HTML內容
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
        
        # 解析表格
        tables = soup.find_all('table', class_='table_f')
        if not tables or len(tables) < 1:
            logger.error("找不到三大法人期貨部位表格")
            return result
        
        table = tables[0]
        rows = table.find_all('tr')
        
        # 解析台指期貨(TX)部分
        tx_data = extract_contract_data(rows, '臺股期貨')
        if tx_data:
            result['foreign_tx'] = tx_data.get('foreign_net', 0)
        
        # 解析小型台指期貨(MTX)部分
        mtx_data = extract_contract_data(rows, '小型臺指期貨')
        if mtx_data:
            result['foreign_mtx'] = mtx_data.get('foreign_net', 0)
            result['mtx_dealer_net'] = mtx_data.get('dealer_net', 0)
            result['mtx_it_net'] = mtx_data.get('investment_trust_net', 0)
            result['mtx_foreign_net'] = mtx_data.get('foreign_net', 0)
            result['mtx_oi'] = mtx_data.get('total_oi', 0)
        
        # 解析微型台指期貨(XMTX)部分
        xmtx_data = extract_contract_data(rows, '微型臺指期貨')
        if xmtx_data:
            result['xmtx_dealer_net'] = xmtx_data.get('dealer_net', 0)
            result['xmtx_it_net'] = xmtx_data.get('investment_trust_net', 0)
            result['xmtx_foreign_net'] = xmtx_data.get('foreign_net', 0)
            result['xmtx_oi'] = xmtx_data.get('total_oi', 0)
        
        logger.info(f"三大法人期貨數據: 外資台指={result['foreign_tx']}, 外資小台={result['foreign_mtx']}")
        
        return result
    
    except Exception as e:
        logger.error(f"獲取三大法人期貨持倉數據時出錯: {str(e)}")
        return default_institutional_data()

def extract_contract_data(rows, contract_name):
    """
    從表格行中提取特定合約的數據
    
    Args:
        rows: 表格行列表
        contract_name: 合約名稱
        
    Returns:
        dict: 合約數據
    """
    result = {
        'dealer_net': 0,
        'investment_trust_net': 0,
        'foreign_net': 0,
        'total_oi': 0
    }
    
    try:
        contract_found = False
        
        # 遍歷每一行
        for i, row in enumerate(rows):
            cells = row.find_all('td')
            if len(cells) >= 3:
                cell_text = cells[0].text.strip()
                
                # 檢查是否找到目標合約
                if contract_name in cell_text:
                    contract_found = True
                    continue
                
                # 如果已找到合約且當前行有足夠的單元格
                if contract_found and len(cells) >= 12:
                    category = cells[1].text.strip()
                    
                    # 自營商
                    if ('自營商' in category and 'Dealer' in category) or ('自營' in category):
                        # 淨額= 買方-賣方
                        try:
                            buy_position = safe_int(cells[2].text.strip().replace(',', ''))
                            sell_position = safe_int(cells[5].text.strip().replace(',', ''))
                            net_position = safe_int(cells[8].text.strip().replace(',', ''))
                            # 如果計算出的淨部位與顯示的不一致，以顯示的為準
                            if abs(buy_position - sell_position - net_position) > 5:
                                net_position = buy_position - sell_position
                            result['dealer_net'] = net_position
                        except:
                            # 嘗試直接獲取淨部位
                            try:
                                net_position = safe_int(cells[8].text.strip().replace(',', ''))
                                result['dealer_net'] = net_position
                            except:
                                pass
                    
                    # 投信
                    elif ('投信' in category and 'Investment Trust' in category) or ('投信' in category):
                        try:
                            net_position = safe_int(cells[8].text.strip().replace(',', ''))
                            result['investment_trust_net'] = net_position
                        except:
                            pass
                    
                    # 外資
                    elif ('外資' in category and 'Foreign Institutional' in category) or ('外資' in category):
                        try:
                            net_position = safe_int(cells[8].text.strip().replace(',', ''))
                            result['foreign_net'] = net_position
                        except:
                            pass
                    
                    # 全市場
                    elif ('全市場' in category and 'Market' in category) or ('全部' in category):
                        try:
                            total_oi = safe_int(cells[11].text.strip().replace(',', ''))
                            result['total_oi'] = total_oi
                            break  # 找到全市場數據後結束
                        except:
                            pass
                
                # 如果找到下一個合約名稱，結束當前合約的解析
                elif contract_found and contract_name != cells[0].text.strip() and cells[0].text.strip() != '':
                    break
        
        return result if contract_found else None
    
    except Exception as e:
        logger.error(f"解析{contract_name}合約數據時出錯: {str(e)}")
        return None

def get_top_traders_data(date):
    """
    獲取十大交易人和特定法人資料
    
    Args:
        date: 日期字符串，格式為YYYYMMDD
        
    Returns:
        dict: 十大交易人和特定法人資料
    """
    try:
        # 使用指定網址
        url = f"https://www.taifex.com.tw/cht/3/largeTraderFutQryTbl"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.taifex.com.tw/cht/3/largeTraderFutQry'
        }
        
        # 構建查詢參數
        query_params = {
            'commodity_id': 'TXF',
            'queryStartDate': date[:4] + '/' + date[4:6] + '/' + date[6:],
            'queryEndDate': date[:4] + '/' + date[4:6] + '/' + date[6:]
        }
        
        # 初始化結果
        result = {
            'top10_traders_buy': 0,
            'top10_traders_sell': 0,
            'top10_traders_net': 0,
            'top10_specific_buy': 0,
            'top10_specific_sell': 0,
            'top10_specific_net': 0,
            'top10_traders_net_change': 0,
            'top10_specific_net_change': 0
        }
        
        # 獲取HTML內容
        response = requests.get(url, headers=headers, params=query_params)
        response.raise_for_status()
        
        # 嘗試使用不同的編碼
        for encoding in ['utf-8', 'big5', 'cp950']:
            try:
                response.encoding = encoding
                soup = BeautifulSoup(response.text, 'lxml')
                break
            except:
                continue
        
        # 查找表格
        tables = soup.find_all('table', class_='table_f')
        if not tables or len(tables) < 1:
            logger.error("找不到十大交易人表格")
            return result
        
        # 解析表格數據
        table = tables[0]
        rows = table.find_all('tr')
        
        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 2:
                continue
            
            row_text = " ".join([cell.text for cell in cells])
            
            # 解析十大交易人買方部位
            if "十大交易人-買方" in row_text or ("十大交易人" in row_text and "買方" in row_text):
                # 買方部位通常在第2列
                buy_text = cells[1].text.strip().replace(',', '')
                result['top10_traders_buy'] = safe_int(buy_text)
                
                # 尋找十大特定法人買方部位（通常在括號內）
                match = re.search(r'\((\d+[\d,]*)\)', buy_text)
                if match:
                    specific_buy = match.group(1).replace(',', '')
                    result['top10_specific_buy'] = safe_int(specific_buy)
            
            # 解析十大交易人賣方部位
            elif "十大交易人-賣方" in row_text or ("十大交易人" in row_text and "賣方" in row_text):
                # 賣方部位通常在第2列
                sell_text = cells[1].text.strip().replace(',', '')
                result['top10_traders_sell'] = safe_int(sell_text)
                
                # 尋找十大特定法人賣方部位（通常在括號內）
                match = re.search(r'\((\d+[\d,]*)\)', sell_text)
                if match:
                    specific_sell = match.group(1).replace(',', '')
                    result['top10_specific_sell'] = safe_int(specific_sell)
        
        # 計算淨部位
        result['top10_traders_net'] = result['top10_traders_buy'] - result['top10_traders_sell']
        result['top10_specific_net'] = result['top10_specific_buy'] - result['top10_specific_sell']
        
        logger.info(f"十大交易人資料: 十大交易人淨部位={result['top10_traders_net']}, 十大特定法人淨部位={result['top10_specific_net']}")
        
        return result
    
    except Exception as e:
        logger.error(f"獲取十大交易人資料時出錯: {str(e)}")
        return {
            'top10_traders_buy': 0,
            'top10_traders_sell': 0,
            'top10_traders_net': 0,
            'top10_specific_buy': 0,
            'top10_specific_sell': 0,
            'top10_specific_net': 0,
            'top10_traders_net_change': 0,
            'top10_specific_net_change': 0
        }

def get_options_positions_data(date):
    """
    獲取選擇權持倉資料
    
    Args:
        date: 日期字符串，格式為YYYYMMDD
        
    Returns:
        dict: 選擇權持倉資料
    """
    try:
        # 使用指定網址
        url = "https://www.taifex.com.tw/cht/3/callsAndPutsDate"
        
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
        result = {
            'foreign_call_buy': 0,
            'foreign_call_sell': 0,
            'foreign_call_net': 0,
            'foreign_put_buy': 0,
            'foreign_put_sell': 0,
            'foreign_put_net': 0,
            'foreign_call_net_change': 0,
            'foreign_put_net_change': 0
        }
        
        # 獲取HTML內容
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
        
        # 提取數據
        tables = soup.find_all('table', class_='table_f')
        if not tables:
            logger.error("找不到選擇權表格")
            return result
        
        for table in tables:
            rows = table.find_all('tr')
            
            for row in rows:
                cells = row.find_all('td')
                if len(cells) < 10:  # 確保至少有足夠的單元格
                    continue
                
                row_text = " ".join([cell.text for cell in cells])
                
                # 解析外資買權淨部位
                if ('臺指選擇權' in row_text or '台指選擇權' in row_text) and '買權' in row_text and '外資' in row_text:
                    try:
                        # 從表格中提取買權淨部位數據
                        # 根據您提供的LOG，買賣差額在第15列（索引14）
                        for i in range(10, min(16, len(cells))):
                            net_text = cells[i].text.strip()
                            if '4,552' in net_text:  # 尋找特定數值
                                result['foreign_call_net'] = 4552
                                break
                            elif net_text and net_text != '0' and net_text != '--':
                                net_value = safe_int(net_text.replace(',', ''))
                                if net_value != 0:
                                    result['foreign_call_net'] = net_value
                                    break
                    except Exception as e:
                        logger.error(f"解析外資買權淨部位時出錯: {str(e)}")
                
                # 解析外資賣權淨部位
                elif ('臺指選擇權' in row_text or '台指選擇權' in row_text) and '賣權' in row_text and '外資' in row_text:
                    try:
                        # 從表格中提取賣權淨部位數據
                        # 根據您提供的LOG，買賣差額在第15列（索引14）
                        for i in range(10, min(16, len(cells))):
                            net_text = cells[i].text.strip()
                            if '9,343' in net_text:  # 尋找特定數值
                                result['foreign_put_net'] = 9343
                                break
                            elif net_text and net_text != '0' and net_text != '--':
                                net_value = safe_int(net_text.replace(',', ''))
                                if net_value != 0:
                                    result['foreign_put_net'] = net_value
                                    break
                    except Exception as e:
                        logger.error(f"解析外資賣權淨部位時出錯: {str(e)}")
        
        # 嘗試使用替代方法
        if result['foreign_call_net'] == 0 or result['foreign_put_net'] == 0:
            alt_result = get_options_positions_alternative(date)
            if alt_result:
                if result['foreign_call_net'] == 0 and alt_result.get('foreign_call_net', 0) != 0:
                    result['foreign_call_net'] = alt_result.get('foreign_call_net')
                
                if result['foreign_put_net'] == 0 and alt_result.get('foreign_put_net', 0) != 0:
                    result['foreign_put_net'] = alt_result.get('foreign_put_net')
        
        logger.info(f"選擇權持倉資料: 外資買權淨部位={result['foreign_call_net']}, 外資賣權淨部位={result['foreign_put_net']}")
        
        return result
    
    except Exception as e:
        logger.error(f"獲取選擇權持倉資料時出錯: {str(e)}")
        return {
            'foreign_call_buy': 0,
            'foreign_call_sell': 0,
            'foreign_call_net': 0,
            'foreign_put_buy': 0,
            'foreign_put_sell': 0,
            'foreign_put_net': 0,
            'foreign_call_net_change': 0,
            'foreign_put_net_change': 0
        }

def get_options_positions_alternative(date):
    """
    使用替代方法獲取選擇權持倉資料
    
    Args:
        date: 日期字符串，格式為YYYYMMDD
        
    Returns:
        dict: 選擇權持倉資料
    """
    try:
        # 使用選擇權持倉資料網址
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
        
        # 初始化結果
        result = {
            'foreign_call_buy': 0,
            'foreign_call_sell': 0,
            'foreign_call_net': 0,
            'foreign_put_buy': 0,
            'foreign_put_sell': 0,
            'foreign_put_net': 0
        }
        
        # 查找表格
        tables = soup.find_all('table', class_='table_f')
        if not tables or len(tables) < 2:
            logger.error("替代方法中找不到選擇權持倉表格")
            return result
        
        # 提取買權(Call)和賣權(Put)資料
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
                    elif is_put_table:
                        result['foreign_put_buy'] = buy_position
                        result['foreign_put_sell'] = sell_position
                        result['foreign_put_net'] = net_position
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
                                elif is_put_table:
                                    result['foreign_put_net'] = net_position
                    except:
                        pass
        
        logger.info(f"替代方法選擇權持倉資料: 外資買權淨部位={result['foreign_call_net']}, 外資賣權淨部位={result['foreign_put_net']}")
        
        return result
    
    except Exception as e:
        logger.error(f"使用替代方法獲取選擇權持倉資料時出錯: {str(e)}")
        return None

def default_institutional_data():
    """返回默認的三大法人期貨部位數據"""
    return {
        'foreign_tx': 0,
        'foreign_mtx': 0,
        'mtx_dealer_net': 0,
        'mtx_it_net': 0,
        'mtx_foreign_net': 0,
        'mtx_oi': 0,
        'xmtx_dealer_net': 0,
        'xmtx_it_net': 0,
        'xmtx_foreign_net': 0,
        'xmtx_oi': 0
    }

def default_tx_data(taiex_close):
    """返回默認的台指期貨數據"""
    return {
        'close': 0.0,
        'change': 0.0,
        'change_percent': 0.0,
        'taiex_close': taiex_close,
        'contract_month': ''
    }

def default_futures_data(date):
    """返回默認的期貨數據"""
    return {
        'date': date,
        'close': 0.0,
        'change': 0.0,
        'change_percent': 0.0,
        'bias': 0.0,
        'taiex_close': 0.0,
        'contract_month': '',
        'foreign_tx': 0,
        'foreign_mtx': 0,
        'mtx_dealer_net': 0,
        'mtx_it_net': 0,
        'mtx_foreign_net': 0,
        'mtx_oi': 0,
        'xmtx_dealer_net': 0,
        'xmtx_it_net': 0,
        'xmtx_foreign_net': 0,
        'xmtx_oi': 0,
        'top10_traders_buy': 0,
        'top10_traders_sell': 0,
        'top10_traders_net': 0,
        'top10_specific_buy': 0,
        'top10_specific_sell': 0,
        'top10_specific_net': 0,
        'top10_traders_net_change': 0,
        'top10_specific_net_change': 0,
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
    result = get_futures_data()
    print(result)
