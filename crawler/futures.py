"""
期貨相關資料爬蟲模組 - 改進版
"""
import logging
import requests
from bs4 import BeautifulSoup
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
        url = f"https://www.taifex.com.tw/cht/3/futDailyMarketReport"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
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
                if '▲' in change_text:
                    change_value = safe_float(change_text.replace('▲', ''))
                elif '▼' in change_text:
                    change_value = -safe_float(change_text.replace('▼', ''))
            
            # 漲跌百分比通常在第8列（索引7）
            change_percent_text = tx_row[7].text.strip().replace(',', '')
            change_percent = 0.0
            if change_percent_text and change_percent_text != '--':
                if '▲' in change_percent_text:
                    change_percent = safe_float(change_percent_text.replace('▲', '').replace('%', ''))
                elif '▼' in change_percent_text:
                    change_percent = -safe_float(change_percent_text.replace('▼', '').replace('%', ''))
            
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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
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
        
        return result
    
    except Exception as e:
        logger.error(f"獲取三大法人期貨部位數據時出錯: {str(e)}")
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
                # 檢查是否找到目標合約
                if contract_name in cells[0].text.strip():
                    contract_found = True
                    continue
                
                # 如果已找到合約且當前行有足夠的單元格
                if contract_found and len(cells) >= 12:
                    category = cells[1].text.strip()
                    
                    # 自營商
                    if '自營商' in category and 'Dealer' in category:
                        # 淨額= 買方-賣方
                        buy_position = safe_int(cells[2].text.strip().replace(',', ''))
                        sell_position = safe_int(cells[5].text.strip().replace(',', ''))
                        net_position = safe_int(cells[8].text.strip().replace(',', ''))
                        result['dealer_net'] = net_position
                    
                    # 投信
                    elif '投信' in category and 'Investment Trust' in category:
                        net_position = safe_int(cells[8].text.strip().replace(',', ''))
                        result['investment_trust_net'] = net_position
                    
                    # 外資
                    elif '外資' in category and 'Foreign Institutional' in category:
                        net_position = safe_int(cells[8].text.strip().replace(',', ''))
                        result['foreign_net'] = net_position
                    
                    # 全市場
                    elif '全市場' in category and 'Market' in category:
                        total_oi = safe_int(cells[11].text.strip().replace(',', ''))
                        result['total_oi'] = total_oi
                        break  # 找到全市場數據後結束
                
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
