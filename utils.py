"""
工具函數模組 - 更新版
"""
import logging
from datetime import datetime, timedelta
import pytz
from database.mongodb import get_latest_market_report, get_market_report_by_date

# 設定日誌
logger = logging.getLogger(__name__)

# 設定台灣時區
TW_TIMEZONE = pytz.timezone('Asia/Taipei')

def generate_market_report(report_id=None, report_date=None, report_type='full'):
    """
    生成市場報告文字
    
    Args:
        report_id: 報告ID (如果提供)
        report_date: 報告日期 (如果提供，格式為 'YYYYMMDD')
        report_type: 報告類型 ('full', 'taiex', 'institutional', 'futures', 'retail')
        
    Returns:
        str: 格式化後的市場報告
    """
    try:
        # 獲取報告數據
        report = None
        if report_id:
            # 透過ID獲取指定報告
            # 此處需要實現 get_market_report_by_id 函數
            pass
        elif report_date:
            # 透過日期獲取指定報告
            report = get_market_report_by_date(report_date)
        else:
            # 獲取最新報告
            report = get_latest_market_report()
        
        if not report:
            logger.error("找不到市場報告")
            return None
        
        # 根據報告類型生成不同格式的報告
        if report_type == 'full':
            return generate_full_report(report)
        elif report_type == 'taiex':
            return generate_taiex_report(report)
        elif report_type == 'institutional':
            return generate_institutional_report(report)
        elif report_type == 'futures':
            return generate_futures_report(report)
        elif report_type == 'retail':
            return generate_retail_report(report)
        else:
            logger.error(f"不支援的報告類型: {report_type}")
            return None
    
    except Exception as e:
        logger.error(f"生成市場報告時發生錯誤: {str(e)}")
        return None

def generate_full_report(report):
    """
    生成完整市場報告
    
    Args:
        report: 市場報告資料
        
    Returns:
        str: 格式化後的完整市場報告
    """
    try:
        # 取得報告日期和星期
        date_string = report.get('date_string', '')
        weekday = report.get('weekday', '')
        
        # 加權指數資料
        taiex = report.get('taiex', {})
        taiex_close = taiex.get('close', 0)
        taiex_change = taiex.get('change', 0)
        taiex_change_percent = taiex.get('change_percent', 0)
        taiex_volume = taiex.get('volume', 0)
        
        # 期貨資料
        futures = report.get('futures', {})
        futures_close = futures.get('close', 0)
        futures_change = futures.get('change', 0)
        futures_change_percent = futures.get('change_percent', 0)
        futures_bias = futures.get('bias', 0)
        
        # 三大法人資料
        institutional = report.get('institutional', {})
        total = institutional.get('total', 0)
        foreign = institutional.get('foreign', 0)
        investment_trust = institutional.get('investment_trust', 0)
        dealer = institutional.get('dealer', 0)
        dealer_self = institutional.get('dealer_self', 0)
        dealer_hedge = institutional.get('dealer_hedge', 0)
        
        # 連續買賣超天數
        foreign_consecutive_days = institutional.get('foreign_consecutive_days', 0)
        investment_trust_consecutive_days = institutional.get('investment_trust_consecutive_days', 0)
        dealer_consecutive_days = institutional.get('dealer_consecutive_days', 0)
        
        # 期貨持倉資料
        futures_positions = report.get('futures_positions', {})
        foreign_tx_net = futures_positions.get('foreign_tx_net', 0)
        foreign_tx_net_change = futures_positions.get('foreign_tx_net_change', 0)
        foreign_mtx_net = futures_positions.get('foreign_mtx_net', 0)
        foreign_mtx_net_change = futures_positions.get('foreign_mtx_net_change', 0)
        foreign_call_net = futures_positions.get('foreign_call_net', 0)
        foreign_call_net_change = futures_positions.get('foreign_call_net_change', 0)
        foreign_put_net = futures_positions.get('foreign_put_net', 0)
        foreign_put_net_change = futures_positions.get('foreign_put_net_change', 0)
        top10_traders_net = futures_positions.get('top10_traders_net', 0)
        top10_traders_net_change = futures_positions.get('top10_traders_net_change', 0)
        top10_specific_net = futures_positions.get('top10_specific_net', 0)
        top10_specific_net_change = futures_positions.get('top10_specific_net_change', 0)
        
        # 散戶持倉資料
        retail_positions = report.get('retail_positions', {})
        mtx_net = retail_positions.get('mtx_net', 0)
        mtx_net_change = retail_positions.get('mtx_net_change', 0)
        xmtx_net = retail_positions.get('xmtx_net', 0)
        xmtx_net_change = retail_positions.get('xmtx_net_change', 0)
        
        # 市場指標
        market_indicators = report.get('market_indicators', {})
        mtx_retail_ratio = market_indicators.get('mtx_retail_ratio', 0)
        mtx_retail_ratio_prev = market_indicators.get('mtx_retail_ratio_prev', 0)
        xmtx_retail_ratio = market_indicators.get('xmtx_retail_ratio', 0)
        xmtx_retail_ratio_prev = market_indicators.get('xmtx_retail_ratio_prev', 0)
        put_call_ratio = market_indicators.get('put_call_ratio', 0)
        put_call_ratio_prev = market_indicators.get('put_call_ratio_prev', 0)
        vix = market_indicators.get('vix', 0)
        vix_prev = market_indicators.get('vix_prev', 0)
        
        # 處理PC Ratio異常值
        put_call_ratio = normalize_pc_ratio(put_call_ratio)
        put_call_ratio_prev = normalize_pc_ratio(put_call_ratio_prev)
        
        # 生成報告文字
        report_text = f"📊 [盤後籌碼快報] {date_string} ({weekday})\n\n"
        
        # 加權指數
        report_text += f"📈 加權指數\n"
        report_text += f"{taiex_close:,.2f} "
        if taiex_change > 0:
            report_text += f"▲{abs(taiex_change):,.2f}"
        elif taiex_change < 0:
            report_text += f"▼{abs(taiex_change):,.2f}"
        else:
            report_text += "—"
        report_text += f" ({abs(taiex_change_percent):,.2f}%) 成交金額: {taiex_volume:,.2f}億元\n\n"
        
        # 台指期(近月)
        report_text += f"📉 台指期(近月)\n"
        report_text += f"{futures_close:,.0f} "
        if futures_change > 0:
            report_text += f"▲{abs(futures_change):,.0f}"
        elif futures_change < 0:
            report_text += f"▼{abs(futures_change):,.0f}"
        else:
            report_text += "—"
        report_text += f" ({abs(futures_change_percent):,.2f}%) 現貨與期貨差: {futures_bias:,.2f}\n\n"
        
        # 三大法人買賣超
        report_text += f"👥 三大法人買賣超\n"
        report_text += f"三大法人合計: "
        if total > 0:
            report_text += f"+{total:,.2f}"
        else:
            report_text += f"{total:,.2f}"
        report_text += "億元\n"
        
        # 外資
        report_text += f"外資買賣超: "
        if foreign > 0:
            report_text += f"+{foreign:,.2f}"
        else:
            report_text += f"{foreign:,.2f}"
        report_text += "億元"
        if foreign_consecutive_days != 0:
            if foreign_consecutive_days > 0:
                report_text += f" (連{foreign_consecutive_days}天買超)"
            else:
                report_text += f" (連{abs(foreign_consecutive_days)}天賣超)"
        report_text += "\n"
        
        # 投信
        report_text += f"投信買賣超: "
        if investment_trust > 0:
            report_text += f"+{investment_trust:,.2f}"
        else:
            report_text += f"{investment_trust:,.2f}"
        report_text += "億元"
        if investment_trust_consecutive_days != 0:
            if investment_trust_consecutive_days > 0:
                report_text += f" (連{investment_trust_consecutive_days}天買超)"
            else:
                report_text += f" (連{abs(investment_trust_consecutive_days)}天賣超)"
        report_text += "\n"
        
        # 自營商
        report_text += f"自營商買賣超: "
        if dealer > 0:
            report_text += f"+{dealer:,.2f}"
        else:
            report_text += f"{dealer:,.2f}"
        report_text += "億元"
        if dealer_consecutive_days != 0:
            if dealer_consecutive_days > 0:
                report_text += f" (連{dealer_consecutive_days}天買超)"
            else:
                report_text += f" (連{abs(dealer_consecutive_days)}天賣超)"
        report_text += "\n"
        
        # 自營商細項
        report_text += f"  自營商(自行): "
        if dealer_self > 0:
            report_text += f"+{dealer_self:,.2f}"
        else:
            report_text += f"{dealer_self:,.2f}"
        report_text += "億元\n"
        
        report_text += f"  自營商(避險): "
        if dealer_hedge > 0:
            report_text += f"+{dealer_hedge:,.2f}"
        else:
            report_text += f"{dealer_hedge:,.2f}"
        report_text += "億元\n\n"
        
        # 期貨籌碼
        report_text += f"🔄 期貨籌碼\n"
        report_text += f"外資台指淨未平倉(口): "
        if foreign_tx_net > 0:
            report_text += f"+{foreign_tx_net:,}"
        else:
            report_text += f"{foreign_tx_net:,}"
        
        if foreign_tx_net_change != 0:
            report_text += " ("
            if foreign_tx_net_change > 0:
                report_text += f"+{foreign_tx_net_change:,}"
            else:
                report_text += f"{foreign_tx_net_change:,}"
            report_text += ")"
        report_text += "\n"
        
        report_text += f"外資小台指淨未平倉(口): "
        if foreign_mtx_net > 0:
            report_text += f"+{foreign_mtx_net:,}"
        else:
            report_text += f"{foreign_mtx_net:,}"
        
        if foreign_mtx_net_change != 0:
            report_text += " ("
            if foreign_mtx_net_change > 0:
                report_text += f"+{foreign_mtx_net_change:,}"
            else:
                report_text += f"{foreign_mtx_net_change:,}"
            report_text += ")"
        report_text += "\n"
        
        report_text += f"外資買權淨未平倉(口): "
        if foreign_call_net > 0:
            report_text += f"+{foreign_call_net:,}"
        else:
            report_text += f"{foreign_call_net:,}"
        
        if foreign_call_net_change != 0:
            report_text += " ("
            if foreign_call_net_change > 0:
                report_text += f"+{foreign_call_net_change:,}"
            else:
                report_text += f"{foreign_call_net_change:,}"
            report_text += ")"
        report_text += "\n"
        
        report_text += f"外資賣權淨未平倉(口): "
        if foreign_put_net > 0:
            report_text += f"+{foreign_put_net:,}"
        else:
            report_text += f"{foreign_put_net:,}"
        
        if foreign_put_net_change != 0:
            report_text += " ("
            if foreign_put_net_change > 0:
                report_text += f"+{foreign_put_net_change:,}"
            else:
                report_text += f"{foreign_put_net_change:,}"
            report_text += ")"
        report_text += "\n"
        
        report_text += f"十大交易人淨未平倉(口): "
        if top10_traders_net > 0:
            report_text += f"+{top10_traders_net:,}"
        else:
            report_text += f"{top10_traders_net:,}"
        
        if top10_traders_net_change != 0:
            report_text += " ("
            if top10_traders_net_change > 0:
                report_text += f"+{top10_traders_net_change:,}"
            else:
                report_text += f"{top10_traders_net_change:,}"
            report_text += ")"
        report_text += "\n"
        
        report_text += f"十大特定法人淨未平倉(口): "
        if top10_specific_net > 0:
            report_text += f"+{top10_specific_net:,}"
        else:
            report_text += f"{top10_specific_net:,}"
        
        if top10_specific_net_change != 0:
            report_text += " ("
            if top10_specific_net_change > 0:
                report_text += f"+{top10_specific_net_change:,}"
            else:
                report_text += f"{top10_specific_net_change:,}"
            report_text += ")"
        report_text += "\n\n"
        
        # 散戶籌碼
        report_text += f"👨‍💼 散戶籌碼\n"
        report_text += f"散戶小台淨未平倉(口): "
        if mtx_net > 0:
            report_text += f"+{mtx_net:,}"
        else:
            report_text += f"{mtx_net:,}"
        
        if mtx_net_change != 0:
            report_text += " ("
            if mtx_net_change > 0:
                report_text += f"+{mtx_net_change:,}"
            else:
                report_text += f"{mtx_net_change:,}"
            report_text += ")"
        report_text += "\n"
        
        report_text += f"散戶微台淨未平倉(口): "
        if xmtx_net > 0:
            report_text += f"+{xmtx_net:,}"
        else:
            report_text += f"{xmtx_net:,}"
        
        if xmtx_net_change != 0:
            report_text += " ("
            if xmtx_net_change > 0:
                report_text += f"+{xmtx_net_change:,}"
            else:
                report_text += f"{xmtx_net_change:,}"
            report_text += ")"
        report_text += "\n\n"
        
        # 市場氛圍指標
        report_text += f"🌡️ 市場氛圍指標\n"
        report_text += f"小台散戶多空比: 今日 {mtx_retail_ratio:,.2f}% / 昨日 {mtx_retail_ratio_prev:,.2f}%\n"
        report_text += f"微台散戶多空比: 今日 {xmtx_retail_ratio:,.2f}% / 昨日 {xmtx_retail_ratio_prev:,.2f}%\n"
        report_text += f"全市場Put/Call Ratio: 今日 {put_call_ratio:,.2f}% / 昨日 {put_call_ratio_prev:,.2f}%\n"
        report_text += f"VIX指標: 今日 {vix:,.2f} / 昨日 {vix_prev:,.2f}\n"
        
        return report_text
    
    except Exception as e:
        logger.error(f"生成完整市場報告時發生錯誤: {str(e)}")
        return None

# 以下保留原有的其他函數，如 generate_taiex_report(), generate_institutional_report() 等...
# 省略其他函數，這些函數邏輯保持不變

def normalize_pc_ratio(value):
    """處理PC Ratio可能的異常值"""
    try:
        if not value:
            return 0.0
            
        # 如果數值過大 (通常大於 10 就不合理)
        if value > 1000:
            return value / 10000  # 可能是百分比顯示為整數 (例如 7500 應為 0.75)
        elif value > 100:
            return value / 100  # 可能是百分比顯示為整數 (例如 75 應為 0.75)
        elif value > 10:
            # 判斷是否合理，通常PC比率在0.5-2.0之間
            if value > 50:
                return value / 100
            elif value > 20:
                return value / 10
            
        return value
    except:
        return 0.0

def safe_float(value, default=0.0):
    """安全地將值轉換為浮點數 - 改進版"""
    try:
        if value is None:
            return default
        
        if isinstance(value, str):
            # 移除千分位逗號和其他非數字字符（保留負號和小數點）
            value = ''.join(c for c in value if c.isdigit() or c in '.-')
            
            # 處理空字符串
            if not value or value in ['.', '-', '-.']:
                return default
        
        return float(value)
    except (ValueError, TypeError):
        return default

def safe_int(value, default=0):
    """安全地將值轉換為整數 - 改進版"""
    try:
        if value is None:
            return default
        
        if isinstance(value, str):
            # 移除千分位逗號和其他非數字字符（保留負號）
            value = ''.join(c for c in value if c.isdigit() or c == '-')
            
            # 處理空字符串
            if not value or value == '-':
                return default
        
        return int(float(value))  # 使用float作為中間轉換，處理小數
    except (ValueError, TypeError):
        return default

def format_number(value, decimal_places=2, add_plus=False):
    """
    格式化數字為字符串，可選添加正號
    
    Args:
        value: 數字值
        decimal_places: 小數位數
        add_plus: 是否為正數添加+號
        
    Returns:
        格式化後的字符串
    """
    try:
        num = safe_float(value)
        if num > 0 and add_plus:
            return f"+{num:.{decimal_places}f}"
        else:
            return f"{num:.{decimal_places}f}"
    except:
        return f"0.{'0' * decimal_places}"

def get_market_trend_symbol(value):
    """
    獲取市場趨勢符號
    
    Args:
        value: 數值變化
        
    Returns:
        趨勢符號: ▲, ▼ 或 --
    """
    value = safe_float(value)
    if value > 0:
        return "▲"
    elif value < 0:
        return "▼"
    else:
        return "--"

def get_today_date_string(format='%Y%m%d'):
    """獲取今日日期字符串（台灣時間）"""
    return datetime.now(TW_TIMEZONE).strftime(format)

def get_yesterday_date_string(format='%Y%m%d'):
    """獲取昨日日期字符串（台灣時間）"""
    yesterday = datetime.now(TW_TIMEZONE) - timedelta(days=1)
    return yesterday.strftime(format)

def is_taiwan_market_closed():
    """
    檢查台灣股市是否已收盤
    台灣股市交易時間: 9:00-13:30
    """
    now = datetime.now(TW_TIMEZONE)
    current_hour = now.hour
    current_minute = now.minute
    
    # 檢查是否為週末
    if now.weekday() >= 5:  # 5 = 週六, 6 = 週日
        return True
    
    # 檢查是否在交易時間內
    if (current_hour > 13) or (current_hour == 13 and current_minute >= 30) or (current_hour < 9):
        return True
    
    return False

def get_tw_stock_date(format='%Y%m%d'):
    """
    獲取台灣股市最近交易日
    改進版: 判斷是否收盤，並考慮週末和假日
    """
    now = datetime.now(TW_TIMEZONE)
    
    # 如果是週末，返回上週五的日期
    if now.weekday() >= 5:  # 5 = 週六, 6 = 週日
        days_to_subtract = now.weekday() - 4  # 計算到上週五的天數
        last_trading_day = now - timedelta(days=days_to_subtract)
        return last_trading_day.strftime(format)
    
    # 如果當日市場已收盤，返回當日日期
    if is_taiwan_market_closed():
        return now.strftime(format)
    else:
        # 如果市場尚未收盤，返回上一個交易日
        if now.weekday() == 0:  # 週一
            last_trading_day = now - timedelta(days=3)  # 返回上週五
        else:
            last_trading_day = now - timedelta(days=1)  # 返回昨天
        return last_trading_day.strftime(format)

def is_trading_day():
    """
    檢查今天是否為交易日
    
    Returns:
        bool: 是否為交易日
    """
    now = datetime.now(TW_TIMEZONE)
    
    # 週末不是交易日
    if now.weekday() >= 5:  # 5 = 週六, 6 = 週日
        return False
    
    # 這裡可以加入台灣股市假日的判斷邏輯
    # 例如: 國定假日、特殊休市日等
    
    return True

# 注意：這個文件中的其他功能（如 generate_taiex_report, generate_institutional_report 等）
# 應該保持原樣，不需要修改，因為它們只是讀取資料庫中已存在的數據，不直接與爬蟲模組互動。
