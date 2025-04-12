"""
市場數據爬取和推送排程模組
"""
import os
import logging
import random
import time
from datetime import datetime, timedelta
import schedule
import threading
import pytz
from linebot.models import TextSendMessage

from crawler.taiex import get_taiex_data
from crawler.futures import get_futures_data
from crawler.institutional import get_institutional_investors_data
from crawler.pc_ratio import get_pc_ratio
from crawler.vix import get_vix_data
# 暫時註解掉缺少的模組，等添加文件後再恢復
# from crawler.top_traders import get_top_traders_data
# from crawler.option_positions import get_option_positions_data
from database.mongodb import (
    save_market_report, 
    update_consecutive_days, 
    get_groups_for_push, 
    mark_report_as_pushed, 
    save_push_log
)
from utils import generate_market_report

# 設定日誌
logger = logging.getLogger(__name__)

# 設定台灣時區
TW_TIMEZONE = pytz.timezone('Asia/Taipei')

def fetch_market_data():
    """
    爬取所有市場數據並存入資料庫
    """
    try:
        logger.info("開始獲取市場數據...")
        
        # 獲取加權指數數據
        taiex_data = get_taiex_data()
        logger.info(f"獲取加權指數數據: {taiex_data}")
        
        # 獲取期貨數據
        futures_data = get_futures_data()
        logger.info(f"獲取期貨數據: {futures_data}")
        
        # 獲取三大法人數據
        institutional_data = get_institutional_investors_data()
        logger.info(f"獲取三大法人數據: {institutional_data}")
        
        # 獲取PC Ratio數據
        pc_ratio_data = get_pc_ratio()
        logger.info(f"獲取PC Ratio數據: {pc_ratio_data}")
        
        # 獲取VIX指標數據
        vix_data = get_vix_data()
        logger.info(f"獲取VIX指標數據: {vix_data}")
        
        # 暫時使用默認值替代缺少的模組
        top_traders_data = {
            'top10_traders_net': 0,
            'top10_traders_net_change': 0,
            'top10_specific_net': 0,
            'top10_specific_net_change': 0
        }
        logger.info(f"使用默認值替代十大交易人數據: {top_traders_data}")
        
        option_positions_data = {
            'foreign_call_net': 0,
            'foreign_call_net_change': 0,
            'foreign_put_net': 0,
            'foreign_put_net_change': 0
        }
        logger.info(f"使用默認值替代選擇權持倉數據: {option_positions_data}")
        
        # 計算散戶指標
        mtx_institutional_net = futures_data.get('mtx_dealer_net', 0) + futures_data.get('mtx_it_net', 0) + futures_data.get('mtx_foreign_net', 0)
        mtx_oi = futures_data.get('mtx_oi', 1)  # 避免除以零
        mtx_retail_indicator = -mtx_institutional_net / mtx_oi * 100 if mtx_oi > 0 else 0.0
        
        xmtx_institutional_net = futures_data.get('xmtx_dealer_net', 0) + futures_data.get('xmtx_it_net', 0) + futures_data.get('xmtx_foreign_net', 0)
        xmtx_oi = futures_data.get('xmtx_oi', 1)  # 避免除以零
        xmtx_retail_indicator = -xmtx_institutional_net / xmtx_oi * 100 if xmtx_oi > 0 else 0.0
        
        # 獲取前一天的散戶指標
        yesterday_mtx_retail_indicator = 0.0  # 需要從資料庫獲取
        yesterday_xmtx_retail_indicator = 0.0  # 需要從資料庫獲取
        yesterday_pc_ratio = 0.0  # 需要從資料庫獲取
        yesterday_vix = 0.0  # 需要從資料庫獲取
        
        # 整合所有數據
        market_data = {
            'date': futures_data.get('date', datetime.now(TW_TIMEZONE).strftime('%Y%m%d')),
            'taiex': {
                'close': taiex_data.get('close', 0),
                'change': taiex_data.get('change', 0),
                'change_percent': taiex_data.get('change_percent', 0),
                'volume': taiex_data.get('volume', 0)
            },
            'futures': {
                'close': futures_data.get('close', 0),
                'change': futures_data.get('change', 0),
                'change_percent': futures_data.get('change_percent', 0),
                'bias': futures_data.get('bias', 0)
            },
            'institutional': {
                'total': institutional_data.get('total', 0),
                'foreign': institutional_data.get('foreign', 0),
                'investment_trust': institutional_data.get('investment_trust', 0),
                'dealer': institutional_data.get('dealer', 0),
                'dealer_self': institutional_data.get('dealer_self', 0),
                'dealer_hedge': institutional_data.get('dealer_hedge', 0)
            },
            'futures_positions': {
                'foreign_tx_net': futures_data.get('foreign_tx', 0),
                'foreign_tx_net_change': 0,  # 需要從資料庫計算變化
                'foreign_mtx_net': futures_data.get('foreign_mtx', 0),
                'foreign_mtx_net_change': 0,  # 需要從資料庫計算變化
                'foreign_call_net': option_positions_data.get('foreign_call_net', 0),
                'foreign_call_net_change': option_positions_data.get('foreign_call_net_change', 0),
                'foreign_put_net': option_positions_data.get('foreign_put_net', 0),
                'foreign_put_net_change': option_positions_data.get('foreign_put_net_change', 0),
                'top10_traders_net': top_traders_data.get('top10_traders_net', 0),
                'top10_traders_net_change': top_traders_data.get('top10_traders_net_change', 0),
                'top10_specific_net': top_traders_data.get('top10_specific_net', 0),
                'top10_specific_net_change': top_traders_data.get('top10_specific_net_change', 0)
            },
            'retail_positions': {
                'mtx_net': -mtx_institutional_net,
                'mtx_net_change': 0,  # 需要從資料庫計算變化
                'xmtx_net': -xmtx_institutional_net,
                'xmtx_net_change': 0  # 需要從資料庫計算變化
            },
            'market_indicators': {
                'mtx_retail_ratio': mtx_retail_indicator,
                'mtx_retail_ratio_prev': yesterday_mtx_retail_indicator,
                'xmtx_retail_ratio': xmtx_retail_indicator,
                'xmtx_retail_ratio_prev': yesterday_xmtx_retail_indicator,
                'put_call_ratio': pc_ratio_data.get('oi_ratio', 0),
                'put_call_ratio_prev': yesterday_pc_ratio,
                'vix': vix_data,
                'vix_prev': yesterday_vix
            }
        }
        
        # 儲存到資料庫
        report_id = save_market_report(market_data)
        if report_id:
            # 更新連續買賣超天數
            update_consecutive_days()
            logger.info(f"市場數據已儲存到資料庫，報告ID: {report_id}")
            return report_id
        else:
            logger.error("儲存市場數據失敗")
            return None
        
    except Exception as e:
        logger.error(f"獲取市場數據時發生錯誤: {str(e)}")
        return None
