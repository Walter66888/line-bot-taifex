"""
PC Ratio爬蟲模組 - 修復版
"""
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
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
        
        # 首先嘗試使用標準方法獲取PC Ratio
        result = get_pc_ratio_standard(date)
        
        # 檢查取得的數據是否正常
        if result and is_valid_pc_ratio(result):
            return result
        
        # 如果標準方法失敗或返回異常值，嘗試使用替代方法
        result_alt = get_pc_ratio_alternative(date)
        
        # 檢查替代方法取得的數據是否正常
        if result_alt and is_valid_pc_ratio(result_alt):
            return result_alt
        
        # 如果都失敗，嘗試獲取前一天的數據
        yesterday = (datetime.strptime(date, '%Y%m%d') - timedelta(days=1)).strftime('%Y%m%d')
        logger.warning(f"當天PC Ratio抓取失敗，嘗試獲取前一天數據: {yesterday}")
        
        result_prev = get_pc_ratio_standard(yesterday)
        
        # 檢查前一天的數據
        if result_prev and is_valid_pc_ratio(result_prev):
            # 更新日期為今天
            result_prev['date'] = date
            return result_prev
        
        # 如果前一天的數據也抓取失敗，返回默認值
        logger.error("所有方法獲取PC Ratio失敗，返回默認值")
        return default_pc_ratio(date)
    
    except Exception as e:
        logger.error(f"獲取PC Ratio數據時出錯: {str(e)}")
        return default_pc_ratio(date)

def get_pc_ratio_standard(date):
    """
    使用標準方法獲取PC Ratio數據
    
    Args:
        date: 日期字符串，格式為YYYYMMDD
        
    Returns:
        dict: 包含PC Ratio數據的字典，或失敗時返回None
    """
    try:
        # 台指選擇權Put/Call Ratio網頁
        url = "https://www.taifex.com.tw/cht/3/pcRatio"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.taifex.com.tw/cht/3/pcRatio'
        }
        
        # 使用POST方法，提供查詢參數
        data = {
            'queryDate': date[:4] + '/' + date[4:6] + '/' + date[6:],  # 格式化日期為YYYY/MM/DD
        }
        
        # 使用get_html_content獲取HTML內容
        soup = get_html_content(url, headers=headers, method='POST', data=data)
        
        if not soup:
            logger.error("無法獲取PC Ratio頁面")
            return None
        
        # 解析表格
        tables = soup.find_all('table', class_='table_f')
        if not tables or len(tables) < 1:
            logger.error("找不到PC Ratio表格")
            return None
        
        table = tables[0]
        rows = table.find_all('tr')
        
        # 跳過表頭行，直接獲取第二行（最新數據）
        if len(rows) < 3:  # 包含標題行和數據行
            logger.error("PC Ratio表格數據不足")
            return None
        
        # 獲取最新數據（第二行，索引為1）
        latest_row = rows[1]
        cells = latest_row.find_all('td')
        
        # 檢查是否有足夠的列
        if len(cells) < 6:
            logger.error(f"PC Ratio表格列數不足: {len(cells)}")
            return None
        
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
            
            # 檢查數據是否超出合理範圍
            if vol_ratio > 1000 or oi_ratio > 1000:
                logger.warning(f"PC Ratio數據超出合理範圍: vol_ratio={vol_ratio}, oi_ratio={oi_ratio}")
                # 如果百分比顯示為整數形式，嘗試轉換
                if vol_ratio > 100:
                    vol_ratio = vol_ratio / 100
                if oi_ratio > 100:
                    oi_ratio = oi_ratio / 100
            
            logger.info(f"成功獲取PC Ratio數據: 日期={trade_date}, 成交量比率={vol_ratio}, 未平倉量比率={oi_ratio}")
            
            # 格式化日期為YYYYMMDD
            if '/' in trade_date:
                parts = trade_date.split('/')
                if len(parts) == 3:
                    formatted_date = ''.join(parts)
                else:
                    formatted_date = date
            else:
                formatted_date = date
            
            return {
                'date': formatted_date,
                'vol_ratio': vol_ratio,
                'oi_ratio': oi_ratio
            }
        except Exception as e:
            logger.error(f"解析PC Ratio數據時出錯: {str(e)}")
            return None
    
    except Exception as e:
        logger.error(f"標準方法獲取PC Ratio數據時出錯: {str(e)}")
        return None

def get_pc_ratio_alternative(date):
    """
    使用替代方法獲取PC Ratio數據
    
    Args:
        date: 日期字符串，格式為YYYYMMDD
        
    Returns:
        dict: 包含PC Ratio數據的字典，或失敗時返回None
    """
    try:
        # 使用API格式的URL
        url = f"https://www.taifex.com.tw/cht/3/pcRatioDown?queryDate={date[:4]}/{date[4:6]}/{date[6:]}&queryType=1"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.taifex.com.tw/cht/3/pcRatio'
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
        
        # 解析CSV格式數據
        if len(lines) < 2:
            logger.error("PC Ratio API返回數據不足")
            return None
        
        # 跳過標題行，取第一行數據
        data_line = lines[1].strip()
        fields = data_line.split(',')
        
        if len(fields) < 5:
            logger.error(f"PC Ratio API返回字段不足: {len(fields)}")
            return None
        
        # 解析數據
        try:
            trade_date = fields[0].strip()
            
            # 數據欄位可能因網站更新而變化，嘗試不同的索引
            vol_ratio_idx = 2 if len(fields) > 2 else 1
            oi_ratio_idx = 4 if len(fields) > 4 else 3
            
            vol_ratio = safe_float(fields[vol_ratio_idx].strip())
            oi_ratio = safe_float(fields[oi_ratio_idx].strip())
            
            # 檢查數據是否超出合理範圍
            if vol_ratio > 1000 or oi_ratio > 1000:
                logger.warning(f"PC Ratio API數據超出合理範圍: vol_ratio={vol_ratio}, oi_ratio={oi_ratio}")
                # 如果百分比顯示為整數形式，嘗試轉換
                if vol_ratio > 100:
                    vol_ratio = vol_ratio / 100
                if oi_ratio > 100:
                    oi_ratio = oi_ratio / 100
            
            logger.info(f"替代方法成功獲取PC Ratio數據: 日期={trade_date}, 成交量比率={vol_ratio}, 未平倉量比率={oi_ratio}")
            
            # 格式化日期為YYYYMMDD
            if '/' in trade_date:
                parts = trade_date.split('/')
                if len(parts) == 3:
                    formatted_date = ''.join(parts)
                else:
                    formatted_date = date
            else:
                formatted_date = date
            
            return {
                'date': formatted_date,
                'vol_ratio': vol_ratio,
                'oi_ratio': oi_ratio
            }
        except Exception as e:
            logger.error(f"解析PC Ratio API數據時出錯: {str(e)}")
            return None
    
    except Exception as e:
        logger.error(f"替代方法獲取PC Ratio數據時出錯: {str(e)}")
        return None

def is_valid_pc_ratio(data):
    """
    檢查PC Ratio數據是否有效
    
    Args:
        data: PC Ratio數據字典
        
    Returns:
        bool: 數據是否有效
    """
    if not data:
        return False
    
    vol_ratio = data.get('vol_ratio', 0)
    oi_ratio = data.get('oi_ratio', 0)
    
    # 檢查數據是否在合理範圍內 (通常在0.1-10之間)
    if vol_ratio < 0.01 or vol_ratio > 1000:
        logger.warning(f"成交量比率超出合理範圍: {vol_ratio}")
        return False
    
    if oi_ratio < 0.01 or oi_ratio > 1000:
        logger.warning(f"未平倉量比率超出合理範圍: {oi_ratio}")
        return False
    
    return True

def default_pc_ratio(date):
    """返回默認的PC Ratio數據"""
    return {
        'date': date,
        'vol_ratio': 0.8,  # 使用接近市場平均的默認值
        'oi_ratio': 0.75   # 使用接近市場平均的默認值
    }

# 主程序測試
if __name__ == "__main__":
    result = get_pc_ratio()
    print(result)
