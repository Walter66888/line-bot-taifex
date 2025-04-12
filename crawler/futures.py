"""
期貨相關資料爬蟲模組 - 使用Excel數據來源
"""
import logging
import requests
import re
import pandas as pd
import io
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
        
        # 獲取三大法人期貨部位數據（使用Excel數據來源）
        institutional_futures = get_institutional_futures_excel(date)
        
        # 獲取十大交易人數據（使用表格數據來源）
        traders_data = get_top_traders_table(date)
        
        # 獲取選擇權持倉數據（使用Excel數據來源）
        options_data = get_options_positions_excel(date)
        
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
    獲取台指期貨數據 - 改進版
    
    Args:
        date: 日期字符串，格式為YYYYMMDD
        taiex_close: 加權指數收盤價
        
    Returns:
        dict: 台指期貨數據
    """
    try:
        # 使用改進的URL格式
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
            # 嘗試使用替代方法
            alternative_data = get_tx_futures_data_alternative(date, taiex_close)
            if alternative_data and alternative_data.get('close', 0) > 0:
                return alternative_data
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
            # 嘗試使用替代方法
            alternative_data = get_tx_futures_data_alternative(date, taiex_close)
            if alternative_data and alternative_data.get('close', 0) > 0:
                return alternative_data
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
            # 嘗試使用替代方法
            alternative_data = get_tx_futures_data_alternative(date, taiex_close)
            if alternative_data and alternative_data.get('close', 0) > 0:
                return alternative_data
            return default_tx_data(taiex_close)
    
    except Exception as e:
        logger.error(f"獲取台指期貨數據時出錯: {str(e)}")
        # 嘗試使用替代方法
        alternative_data = get_tx_futures_data_alternative(date, taiex_close)
        if alternative_data and alternative_data.get('close', 0) > 0:
            return alternative_data
        return default_tx_data(taiex_close)

def get_tx_futures_data_alternative(date, taiex_close=0):
    """
    使用替代方法獲取台指期貨數據
    
    Args:
        date: 日期字符串，格式為YYYYMMDD
        taiex_close: 加權指數收盤價
    
    Returns:
        dict: 台指期貨數據
    """
    try:
        # 使用 JSON API
        year = date[:4]
        month = date[4:6]
        day = date[6:8]
        
        url = f"https://www.taifex.com.tw/cht/app/chartQuote?weight=0&up_resolution=5&rowcount=1&type=1&commodity_id=TX&contract_date=&datemode=0&queryStartDate={year}/{month}/{day}&queryEndDate={year}/{month}/{day}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Referer': 'https://www.taifex.com.tw/cht/3/futDailyMarketReport'
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        if len(data) > 0:
            last_data = data[-1]
            close_price = safe_float(last_data.get('Close', 0))
            
            # 計算漲跌和漲跌百分比
            yesterday_close = safe_float(last_data.get('ClosePrevious', 0))
            change_value = close_price - yesterday_close
            change_percent = (change_value / yesterday_close * 100) if yesterday_close > 0 else 0.0
            
            # 尋找合約月
            contract_month = last_data.get('ContractName', '')
            if contract_month:
                match = re.search(r'TX(\d+)', contract_month)
                if match:
                    contract_month = match.group(1)
            
            logger.info(f"替代方法獲取台指期貨: 收盤價={close_price}, 漲跌={change_value}, 漲跌%={change_percent}")
            
            return {
                'close': close_price,
                'change': change_value,
                'change_percent': change_percent,
                'taiex_close': taiex_close,
                'contract_month': contract_month
            }
        else:
            logger.error("替代方法獲取台指期貨數據失敗：資料為空")
            return default_tx_data(taiex_close)
    
    except Exception as e:
        logger.error(f"使用替代方法獲取台指期貨數據時出錯: {str(e)}")
        return default_tx_data(taiex_close)

def get_institutional_futures_excel(date):
    """
    使用Excel資料獲取三大法人期貨持倉資料
    
    Args:
        date: 日期字符串，格式為YYYYMMDD
        
    Returns:
        dict: 三大法人期貨持倉資料
    """
    try:
        # 使用Excel網址
        url = f"https://www.taifex.com.tw/cht/3/futContractsDateExcel?queryType=1&goDay=&doQuery=1&dateaddcnt=&queryDate={date[:4]}%2F{date[4:6]}%2F{date[6:]}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.taifex.com.tw/cht/3/futContractsDate'
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        # 初始化結果
        result = default_institutional_data()
        
        # 使用pandas讀取Excel數據
        df = pd.read_excel(io.BytesIO(response.content))
        
        # 尋找台指期貨和小台期貨的外資淨部位
        for index, row in df.iterrows():
            # 查找包含"臺股期貨"的行
            if isinstance(row.iloc[0], str) and "臺股期貨" in row.iloc[0]:
                # 在接下來的行中尋找外資
                for i in range(index, len(df)):
                    if isinstance(df.iloc[i].iloc[0], str) and ("外資" in df.iloc[i].iloc[0] or "Foreign" in df.iloc[i].iloc[0]):
                        # 外資台指淨部位通常在第8列（索引7）
                        if len(df.columns) > 7 and not pd.isna(df.iloc[i].iloc[7]):
                            result['foreign_tx'] = safe_int(df.iloc[i].iloc[7])
                            logger.info(f"Excel數據: 外資台指淨部位 = {result['foreign_tx']}")
                        break
            
            # 查找包含"小型臺指期貨"的行
            if isinstance(row.iloc[0], str) and "小型臺指期貨" in row.iloc[0]:
                # 在接下來的行中尋找外資
                for i in range(index, len(df)):
                    if isinstance(df.iloc[i].iloc[0], str) and ("外資" in df.iloc[i].iloc[0] or "Foreign" in df.iloc[i].iloc[0]):
                        # 外資小台淨部位通常在第8列（索引7）
                        if len(df.columns) > 7 and not pd.isna(df.iloc[i].iloc[7]):
                            result['foreign_mtx'] = safe_int(df.iloc[i].iloc[7])
                            result['mtx_foreign_net'] = result['foreign_mtx']
                            logger.info(f"Excel數據: 外資小台淨部位 = {result['foreign_mtx']}")
                        break
                            
                    # 尋找自營商
                    if isinstance(df.iloc[i].iloc[0], str) and ("自營商" in df.iloc[i].iloc[0] or "Dealer" in df.iloc[i].iloc[0]):
                        if len(df.columns) > 7 and not pd.isna(df.iloc[i].iloc[7]):
                            result['mtx_dealer_net'] = safe_int(df.iloc[i].iloc[7])
                    
                    # 尋找投信
                    if isinstance(df.iloc[i].iloc[0], str) and ("投信" in df.iloc[i].iloc[0] or "Investment" in df.iloc[i].iloc[0]):
                        if len(df.columns) > 7 and not pd.isna(df.iloc[i].iloc[7]):
                            result['mtx_it_net'] = safe_int(df.iloc[i].iloc[7])
            
            # 查找包含"微型臺指期貨"的行
            if isinstance(row.iloc[0], str) and "微型臺指期貨" in row.iloc[0]:
                # 在接下來的行中尋找外資、自營商、投信
                for i in range(index, len(df)):
                    if isinstance(df.iloc[i].iloc[0], str) and ("外資" in df.iloc[i].iloc[0] or "Foreign" in df.iloc[i].iloc[0]):
                        if len(df.columns) > 7 and not pd.isna(df.iloc[i].iloc[7]):
                            result['xmtx_foreign_net'] = safe_int(df.iloc[i].iloc[7])
                    
                    if isinstance(df.iloc[i].iloc[0], str) and ("自營商" in df.iloc[i].iloc[0] or "Dealer" in df.iloc[i].iloc[0]):
                        if len(df.columns) > 7 and not pd.isna(df.iloc[i].iloc[7]):
                            result['xmtx_dealer_net'] = safe_int(df.iloc[i].iloc[7])
                    
                    if isinstance(df.iloc[i].iloc[0], str) and ("投信" in df.iloc[i].iloc[0] or "Investment" in df.iloc[i].iloc[0]):
                        if len(df.columns) > 7 and not pd.isna(df.iloc[i].iloc[7]):
                            result['xmtx_it_net'] = safe_int(df.iloc[i].iloc[7])
        
        # 如果無法從Excel獲取數據，嘗試使用替代方法
        if result['foreign_tx'] == 0 and result['foreign_mtx'] == 0:
            logger.warning("無法從Excel獲取期貨持倉數據，嘗試使用替代方法")
            alternative_data = get_institutional_futures_alternative(date)
            if alternative_data and (alternative_data.get('foreign_tx', 0) != 0 or alternative_data.get('foreign_mtx', 0) != 0):
                result = alternative_data
        
        return result
    
    except Exception as e:
        logger.error(f"使用Excel獲取三大法人期貨持倉數據時出錯: {str(e)}")
        # 嘗試使用替代方法
        return get_institutional_futures_alternative(date)

def get_top_traders_table(date):
    """
    從表格獲取十大交易人和特定法人持倉資料
    
    Args:
        date: 日期字符串，格式為YYYYMMDD
        
    Returns:
        dict: 十大交易人和特定法人持倉資料
    """
    try:
        # 使用改進的URL
        url = f"https://www.taifex.com.tw/cht/3/largeTraderFutQryTbl?commodity_id=TXF&queryStartDate={date[:4]}/{date[4:6]}/{date[6:]}&queryEndDate={date[:4]}/{date[4:6]}/{date[6:]}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.taifex.com.tw/cht/3/largeTraderFutQry'
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
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        # 嘗試使用不同的編碼
        for encoding in ['utf-8', 'big5', 'cp950']:
            try:
                response.encoding = encoding
                soup = BeautifulSoup(response.text, 'lxml')
                break
            except:
                continue
        
        # 找到表格
        tables = soup.find_all('table', class_='table_f')
        if not tables or len(tables) < 1:
            logger.error("找不到十大交易人表格")
            return result
        
        table = tables[0]
        rows = table.find_all('tr')
        
        # 解析數據
        # 處理外資期貨部位數據
        for row in rows:
            cells = row.find_all('td')
            
            # 需要至少4列數據
            if len(cells) < 4:
                continue
            
            row_text = " ".join([cell.text for cell in cells])
            
            # 解析十大交易人買賣部位
            if "十大交易人-買方" in row_text:
                # 買方部位，通常在第2列
                buy_text = cells[1].text.strip().replace(',', '')
                result['top10_traders_buy'] = safe_int(buy_text)
                
                # 同時檢查是否有特定法人數據（通常在括號內）
                match = re.search(r'\((\d+[\d,]*)\)', buy_text)
                if match:
                    specific_buy = match.group(1).replace(',', '')
                    result['top10_specific_buy'] = safe_int(specific_buy)
            
            if "十大交易人-賣方" in row_text:
                # 賣方部位，通常在第2列
                sell_text = cells[1].text.strip().replace(',', '')
                result['top10_traders_sell'] = safe_int(sell_text)
                
                # 同時檢查是否有特定法人數據（通常在括號內）
                match = re.search(r'\((\d+[\d,]*)\)', sell_text)
                if match:
                    specific_sell = match.group(1).replace(',', '')
                    result['top10_specific_sell'] = safe_int(specific_sell)
        
        # 計算淨部位
        result['top10_traders_net'] = result['top10_traders_buy'] - result['top10_traders_sell']
        result['top10_specific_net'] = result['top10_specific_buy'] - result['top10_specific_sell']
        
        logger.info(f"十大交易人表格數據: 十大交易人={result['top10_traders_net']}, 十大特定法人={result['top10_specific_net']}")
        
        # 檢查數據是否有效
        if result['top10_traders_buy'] == 0 and result['top10_traders_sell'] == 0:
            logger.warning("無法從表格獲取十大交易人數據，嘗試使用替代方法")
            alternative_data = get_top_traders_alternative(date)
            if alternative_data and (alternative_data.get('top10_traders_buy', 0) != 0 or alternative_data.get('top10_traders_sell', 0) != 0):
                result = alternative_data
        
        return result
    
    except Exception as e:
        logger.error(f"獲取十大交易人表格數據時出錯: {str(e)}")
        # 嘗試使用替代方法
        return get_top_traders_alternative(date)

def get_options_positions_excel(date):
    """
    從Excel獲取選擇權持倉資料
    
    Args:
        date: 日期字符串，格式為YYYYMMDD
        
    Returns:
        dict: 選擇權持倉資料
    """
    try:
        # 使用Excel網址
        url = f"https://www.taifex.com.tw/cht/3/callsAndPutsDateExcel?queryType=1&goDay=&doQuery=1&dateaddcnt=&queryDate={date[:4]}%2F{date[4:6]}%2F{date[6:]}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.taifex.com.tw/cht/3/callsAndPutsDate'
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
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
        
        # 使用pandas讀取Excel數據
        df = pd.read_excel(io.BytesIO(response.content))
        
        # 初始化標記變量
        found_call = False
        found_put = False
        
        # 遍歷數據尋找買權和賣權數據
        for index, row in df.iterrows():
            # 尋找買權(Call)數據
            if not found_call and isinstance(row.iloc[0], str) and '買權' in row.iloc[0]:
                # 在接下來的行中尋找外資數據
                for i in range(index, len(df)):
                    if i >= len(df) or (isinstance(df.iloc[i].iloc[0], str) and '賣權' in df.iloc[i].iloc[0]):
                        break
                    
                    if isinstance(df.iloc[i].iloc[0], str) and ('外資' in df.iloc[i].iloc[0] or 'Foreign' in df.iloc[i].iloc[0]):
                        # 買方部位通常在第2列
                        if len(df.columns) > 1 and not pd.isna(df.iloc[i].iloc[1]):
                            result['foreign_call_buy'] = safe_int(df.iloc[i].iloc[1])
                        
                        # 賣方部位通常在第4列
                        if len(df.columns) > 3 and not pd.isna(df.iloc[i].iloc[3]):
                            result['foreign_call_sell'] = safe_int(df.iloc[i].iloc[3])
                        
                        # 淨部位通常在第6列
                        if len(df.columns) > 5 and not pd.isna(df.iloc[i].iloc[5]):
                            result['foreign_call_net'] = safe_int(df.iloc[i].iloc[5])
                        
                        found_call = True
                        break
            
            # 尋找賣權(Put)數據
            if not found_put and isinstance(row.iloc[0], str) and '賣權' in row.iloc[0]:
                # 在接下來的行中尋找外資數據
                for i in range(index, len(df)):
                    if i >= len(df):
                        break
                    
                    if isinstance(df.iloc[i].iloc[0], str) and ('外資' in df.iloc[i].iloc[0] or 'Foreign' in df.iloc[i].iloc[0]):
                        # 買方部位通常在第2列
                        if len(df.columns) > 1 and not pd.isna(df.iloc[i].iloc[1]):
                            result['foreign_put_buy'] = safe_int(df.iloc[i].iloc[1])
                        
                        # 賣方部位通常在第4列
                        if len(df.columns) > 3 and not pd.isna(df.iloc[i].iloc[3]):
                            result['foreign_put_sell'] = safe_int(df.iloc[i].iloc[3])
                        
                        # 淨部位通常在第6列
                        if len(df.columns) > 5 and not pd.isna(df.iloc[i].iloc[5]):
                            result['foreign_put_net'] = safe_int(df.iloc[i].iloc[5])
                        
                        found_put = True
                        break
            
            # 如果都找到了，可以提前退出
            if found_call and found_put:
                break
        
        # 如果沒有找到淨部位，嘗試通過買賣方計算
        if result['foreign_call_net'] == 0 and result['foreign_call_buy'] != 0 and result['foreign_call_sell'] != 0:
            result['foreign_call_net'] = result['foreign_call_buy'] - result['foreign_call_sell']
        
        if result['foreign_put_net'] == 0 and result['foreign_put_buy'] != 0 and result['foreign_put_sell'] != 0:
            result['foreign_put_net'] = result['foreign_put_buy'] - result['foreign_put_sell']
        
        logger.info(f"選擇權Excel數據: 外資買權淨部位={result['foreign_call_net']}, 外資賣權淨部位={result['foreign_put_net']}")
        
        # 獲取昨日數據，用於計算變化
        yesterday = (datetime.strptime(date, '%Y%m%d') - timedelta(days=1)).strftime('%Y%m%d')
        yesterday_data = get_options_positions_excel(yesterday) if date != yesterday else None
        
        # 計算變化
        today_foreign_call_net = result.get('foreign_call_net', 0)
        yesterday_foreign_call_net = yesterday_data.get('foreign_call_net', 0) if yesterday_data else 0
        foreign_call_net_change = today_foreign_call_net - yesterday_foreign_call_net
        
        today_foreign_put_net = result.get('foreign_put_net', 0)
        yesterday_foreign_put_net = yesterday_data.get('foreign_put_net', 0) if yesterday_data else 0
        foreign_put_net_change = today_foreign_put_net - yesterday_foreign_put_net
        
        # 更新變化值
        result['foreign_call_net_change'] = foreign_call_net_change
        result['foreign_put_net_change'] = foreign_put_net_change
        
        return result
    
    except Exception as e:
        logger.error(f"獲取選擇權Excel數據時出錯: {str(e)}")
        # 嘗試使用替代方法
        return get_options_positions_alternative(date)

def get_institutional_futures_alternative(date):
    """
    使用替代方法獲取三大法人期貨持倉資料
    
    Args:
        date: 日期字符串，格式為YYYYMMDD
        
    Returns:
        dict: 三大法人期貨持倉資料
    """
    try:
        # 使用原有的獲取方法作為替代
        # 使用更可靠的URL
        url = "https://www.taifex.com.tw/cht/3/futContractsDate"
        
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
        
        # 默認結果
        result = default_institutional_data()
        
        # 解析表格
        tables = soup.find_all('table', class_='table_f')
        if not tables or len(tables) < 1:
            logger.error("找不到三大法人期貨部位表格")
            return result
        
        table = tables[0]
        rows = table.find_all('tr')
        
        # 解析台指期貨(TX)部分
        for index, row in enumerate(rows):
            cells = row.find_all('td')
            if len(cells) < 3:
                continue
            
            row_text = " ".join([cell.text for cell in cells])
            
            # 查找臺股期貨區域
            if "臺股期貨" in row_text:
                # 尋找外資
                for i in range(index, len(rows)):
                    sub_cells = rows[i].find_all('td')
                    if len(sub_cells) < 8:
                        continue
                    
                    sub_text = " ".join([cell.text for cell in sub_cells])
                    if "外資" in sub_text:
                        # 淨部位通常在第8列
                        try:
                            net_text = sub_cells[7].text.strip().replace(',', '')
                            result['foreign_tx'] = safe_int(net_text)
                        except:
                            pass
                        break
            
            # 查找小型臺指期貨區域
            elif "小型臺指期貨" in row_text:
                # 尋找外資、自營商、投信
                for i in range(index, len(rows)):
                    sub_cells = rows[i].find_all('td')
                    if len(sub_cells) < 8:
                        continue
                    
                    sub_text = " ".join([cell.text for cell in sub_cells])
                    
                    if "外資" in sub_text:
                        try:
                            net_text = sub_cells[7].text.strip().replace(',', '')
                            result['foreign_mtx'] = safe_int(net_text)
                            result['mtx_foreign_net'] = result['foreign_mtx']
                        except:
                            pass
                    
                    elif "自營" in sub_text:
                        try:
                            net_text = sub_cells[7].text.strip().replace(',', '')
                            result['mtx_dealer_net'] = safe_int(net_text)
                        except:
                            pass
                    
                    elif "投信" in sub_text:
                        try:
                            net_text = sub_cells[7].text.strip().replace(',', '')
                            result['mtx_it_net'] = safe_int(net_text)
                        except:
                            pass
        
        return result
    
    except Exception as e:
        logger.error(f"使用替代方法獲取三大法人期貨部位數據時出錯: {str(e)}")
        return default_institutional_data()

def get_top_traders_alternative(date):
    """
    使用替代方法獲取十大交易人和特定法人持倉資料
    
    Args:
        date: 日期字符串，格式為YYYYMMDD
        
    Returns:
        dict: 十大交易人和特定法人持倉資料
    """
    try:
        # 使用原URL
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
            return default_top_traders_data()
        
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
        
        return result
    
    except Exception as e:
        logger.error(f"使用替代方法獲取十大交易人資料時出錯: {str(e)}")
        return default_top_traders_data()

def get_options_positions_alternative(date):
    """
    使用替代方法獲取選擇權持倉資料
    
    Args:
        date: 日期字符串，格式為YYYYMMDD
        
    Returns:
        dict: 選擇權持倉資料
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
            return default_option_positions_data()
        
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
        
        return result
    
    except Exception as e:
        logger.error(f"使用替代方法獲取選擇權持倉資料時出錯: {str(e)}")
        return default_option_positions_data()

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

def default_top_traders_data():
    """返回默認的十大交易人和特定法人持倉資料"""
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

def default_option_positions_data():
    """返回默認的選擇權持倉資料"""
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
