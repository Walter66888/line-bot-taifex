"""
期貨相關資料爬蟲模組 - 全面改進版
"""
import logging
import requests
import json
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
        
        # 嘗試使用替代方法獲取期貨部位數據（如果上面的方法返回全部為零）
        if all(value == 0 for key, value in institutional_futures.items() if key != 'date'):
            alternative_futures = get_institutional_futures_alternative(date)
            if alternative_futures:
                institutional_futures = alternative_futures
                logger.info("使用替代方法成功獲取期貨部位數據")
        
        # 合併數據
        result = {**tx_data, **institutional_futures}
        result['date'] = date
        
        # 計算偏差 (僅當兩個數值都正常時才計算)
        if result['close'] > 0 and taiex_close > 0:
            result['bias'] = result['close'] - taiex_close
        else:
            result['bias'] = 0.0
        
        logger.info(f"期貨數據: 收盤={result['close']}, 加權指數={taiex_close}, 偏差={result['bias']}")
        
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

def get_institutional_futures_data(date):
    """
    獲取三大法人期貨部位數據 - 改進版
    
    Args:
        date: 日期字符串，格式為YYYYMMDD
        
    Returns:
        dict: 三大法人期貨部位數據
    """
    try:
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
        
        # 檢查是否返回全零數據，如果是則可能數據抓取失敗
        if all(value == 0 for key, value in result.items() if key != 'date'):
            logger.warning("三大法人期貨抓取全部為零，可能數據抓取失敗")
        
        return result
    
    except Exception as e:
        logger.error(f"獲取三大法人期貨部位數據時出錯: {str(e)}")
        return default_institutional_data()

def get_institutional_futures_alternative(date):
    """
    使用替代方法獲取三大法人期貨部位數據
    
    Args:
        date: 日期字符串，格式為YYYYMMDD
        
    Returns:
        dict: 三大法人期貨部位數據
    """
    try:
        # 使用API格式抓取數據
        url = f"https://www.taifex.com.tw/cht/3/futContractsDateAsync?queryType=1&goDay=&doQuery=1&dateaddcnt=&queryDate={date[:4]}/{date[4:6]}/{date[6:]}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': 'https://www.taifex.com.tw/cht/3/futContractsDate'
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        
        # 默認結果
        result = default_institutional_data()
        
        # 解析JSON數據
        for item in data.get('data', []):
            # 檢查商品名稱
            product_name = item.get('commodity_name', '')
            
            # 解析台指期貨數據
            if '臺股期貨' in product_name:
                for trader in item.get('traders', []):
                    trader_type = trader.get('trader_type', '')
                    
                    # 外資部位
                    if 'foreign' in trader_type.lower() or '外資' in trader_type:
                        result['foreign_tx'] = safe_int(trader.get('position_buy_sell_diff', 0))
            
            # 解析小型台指期貨數據
            elif '小型臺指期貨' in product_name:
                for trader in item.get('traders', []):
                    trader_type = trader.get('trader_type', '')
                    
                    # 外資部位
                    if 'foreign' in trader_type.lower() or '外資' in trader_type:
                        result['foreign_mtx'] = safe_int(trader.get('position_buy_sell_diff', 0))
                        result['mtx_foreign_net'] = safe_int(trader.get('position_buy_sell_diff', 0))
                    
                    # 自營商部位
                    elif 'dealer' in trader_type.lower() or '自營' in trader_type:
                        result['mtx_dealer_net'] = safe_int(trader.get('position_buy_sell_diff', 0))
                    
                    # 投信部位
                    elif 'investment' in trader_type.lower() or '投信' in trader_type:
                        result['mtx_it_net'] = safe_int(trader.get('position_buy_sell_diff', 0))
                
                # 總未平倉量
                result['mtx_oi'] = safe_int(item.get('total_open_interest', 0))
            
            # 解析微型台指期貨數據
            elif '微型臺指期貨' in product_name:
                for trader in item.get('traders', []):
                    trader_type = trader.get('trader_type', '')
                    
                    # 外資部位
                    if 'foreign' in trader_type.lower() or '外資' in trader_type:
                        result['xmtx_foreign_net'] = safe_int(trader.get('position_buy_sell_diff', 0))
                    
                    # 自營商部位
                    elif 'dealer' in trader_type.lower() or '自營' in trader_type:
                        result['xmtx_dealer_net'] = safe_int(trader.get('position_buy_sell_diff', 0))
                    
                    # 投信部位
                    elif 'investment' in trader_type.lower() or '投信' in trader_type:
                        result['xmtx_it_net'] = safe_int(trader.get('position_buy_sell_diff', 0))
                
                # 總未平倉量
                result['xmtx_oi'] = safe_int(item.get('total_open_interest', 0))
        
        logger.info(f"替代方法獲取三大法人期貨數據: 外資台指={result['foreign_tx']}, 外資小台={result['foreign_mtx']}")
        
        return result
        
    except Exception as e:
        logger.error(f"使用替代方法獲取三大法人期貨部位數據時出錯: {str(e)}")
        return default_institutional_data()

def extract_contract_data(rows, contract_name):
    """
    從表格行中提取特定合約的數據 - 改進版
    
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
        'xmtx_oi': 0
    }

# 主程序測試
if __name__ == "__main__":
    result = get_futures_data()
    print(result)
