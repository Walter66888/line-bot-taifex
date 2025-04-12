"""
市場數據爬取和推送排程模組 - 修改版
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
# 移除原本的 futures 引入
# from crawler.futures import get_futures_data
# 新增引入三大法人期貨持倉模組
from crawler.institutional_futures import get_institutional_futures_data
from crawler.institutional import get_institutional_investors_data
from crawler.pc_ratio import get_pc_ratio
from crawler.vix import get_vix_data
from crawler.top_traders import get_top_traders_data
from crawler.option_positions import get_option_positions_data
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
        
        # 移除原本的期貨數據獲取
        # futures_data = get_futures_data()
        # logger.info(f"獲取期貨數據: {futures_data}")
        
        # 獲取三大法人數據
        institutional_data = get_institutional_investors_data()
        logger.info(f"獲取三大法人數據: {institutional_data}")
        
        # 獲取PC Ratio數據
        pc_ratio_data = get_pc_ratio()
        logger.info(f"獲取PC Ratio數據: {pc_ratio_data}")
        
        # 獲取VIX指標數據
        vix_data = get_vix_data()
        logger.info(f"獲取VIX指標數據: {vix_data}")
        
        # 獲取十大交易人和特定法人持倉數據
        top_traders_data = get_top_traders_data()
        logger.info(f"獲取十大交易人數據: {top_traders_data}")
        
        # 獲取選擇權持倉數據
        option_positions_data = get_option_positions_data()
        logger.info(f"獲取選擇權持倉數據: {option_positions_data}")
        
        # 新增：獲取三大法人期貨持倉數據
        institutional_futures_data = get_institutional_futures_data()
        logger.info(f"獲取三大法人期貨持倉數據: {institutional_futures_data}")
        
        # 計算散戶指標
        # 修改為使用新的三大法人期貨持倉數據
        # 由於現在沒有完整的期貨數據，先使用固定值
        mtx_institutional_net = 0  # 暫時使用0
        mtx_oi = 1  # 避免除以零
        mtx_retail_indicator = 0.0
        
        xmtx_institutional_net = 0  # 暫時使用0
        xmtx_oi = 1  # 避免除以零
        xmtx_retail_indicator = 0.0
        
        # 獲取前一天的散戶指標
        yesterday_mtx_retail_indicator = 0.0  # 需要從資料庫獲取
        yesterday_xmtx_retail_indicator = 0.0  # 需要從資料庫獲取
        yesterday_pc_ratio = 0.0  # 需要從資料庫獲取
        yesterday_vix = 0.0  # 需要從資料庫獲取
        
        # 整合所有數據
        # 使用新的三大法人期貨持倉數據
        current_date = datetime.now(TW_TIMEZONE).strftime('%Y%m%d')
        market_data = {
            'date': institutional_data.get('date', current_date),
            'taiex': {
                'close': taiex_data.get('close', 0),
                'change': taiex_data.get('change', 0),
                'change_percent': taiex_data.get('change_percent', 0),
                'volume': taiex_data.get('volume', 0)
            },
            'futures': {
                'close': 0,  # 暫時使用0，後續會補充
                'change': 0,
                'change_percent': 0,
                'bias': 0
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
                'foreign_tx_net': institutional_futures_data.get('foreign_tx_net', 0),
                'foreign_tx_net_change': 0,  # 需要從資料庫計算變化
                'foreign_mtx_net': institutional_futures_data.get('foreign_mtx_net', 0),
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

# 以下函數保持不變
def push_market_report(line_bot_api, report_id):
    """
    推送市場報告到已設定的 LINE 群組
    
    Args:
        line_bot_api: LINE Bot API 實例
        report_id: 報告ID
    """
    try:
        # 獲取需要推送的群組
        groups = get_groups_for_push()
        if not groups:
            logger.info("沒有需要推送的群組")
            return
        
        # 生成市場報告
        report_text = generate_market_report(report_id)
        if not report_text:
            logger.error("生成市場報告失敗")
            return
        
        # 將報告推送到每個群組
        for group in groups:
            try:
                line_group_id = group.get('line_group_id')
                if line_group_id:
                    logger.info(f"推送市場報告到群組: {line_group_id}")
                    line_bot_api.push_message(
                        line_group_id,
                        TextSendMessage(text=report_text)
                    )
                    # 記錄推送成功
                    save_push_log(
                        target_type='group',
                        target_id=line_group_id,
                        report_date=datetime.now(TW_TIMEZONE).date(),
                        status='success',
                        message_type='full_report'
                    )
            except Exception as e:
                logger.error(f"推送到群組 {line_group_id} 時發生錯誤: {str(e)}")
                # 記錄推送失敗
                save_push_log(
                    target_type='group',
                    target_id=line_group_id,
                    report_date=datetime.now(TW_TIMEZONE).date(),
                    status='failure',
                    message_type='full_report',
                    error_message=str(e)
                )
        
        # 標記報告已推送
        mark_report_as_pushed(report_id)
        logger.info("市場報告推送完成")
        
    except Exception as e:
        logger.error(f"推送市場報告時發生錯誤: {str(e)}")

def schedule_market_data_job(line_bot_api):
    """
    排程市場數據任務
    
    Args:
        line_bot_api: LINE Bot API 實例
    """
    # 從環境變數獲取基礎時間和隨機延遲範圍
    base_time = os.environ.get('FETCH_BASE_TIME', '14:50')
    min_delay = int(os.environ.get('MIN_RANDOM_DELAY', '1'))
    max_delay = int(os.environ.get('MAX_RANDOM_DELAY', '3'))
    
    # 生成隨機延遲（min_delay-max_delay分鐘）
    random_minutes = random.randint(min_delay, max_delay)
    random_seconds = random.randint(0, 59)
    
    # In 記錄設定
    logger.info(f"排程設定：基礎時間 {base_time}，隨機延遲 {random_minutes}分{random_seconds}秒")
    
    # 設定爬取時間（基礎時間 + 隨機延遲）
    schedule.every().day.at(base_time).do(
        lambda: delayed_fetch_and_push(line_bot_api, minutes=random_minutes, seconds=random_seconds)
    )
    
    # 晚上清除過期的快取數據
    schedule.every().day.at("23:30").do(clean_cache)
    
    logger.info(f"已排程市場數據任務，爬取時間：{base_time} + {random_minutes}分{random_seconds}秒")

def delayed_fetch_and_push(line_bot_api, minutes=0, seconds=0):
    """
    延遲後爬取並推送市場數據
    
    Args:
        line_bot_api: LINE Bot API 實例
        minutes: 延遲分鐘數
        seconds: 延遲秒數
    """
    def _task():
        logger.info(f"等待 {minutes}分{seconds}秒 後爬取市場數據...")
        time.sleep(minutes * 60 + seconds)
        
        # 檢查今天是否是交易日
        now = datetime.now(TW_TIMEZONE)
        if now.weekday() >= 5:  # 週末不爬取
            logger.info("今天是週末，不爬取市場數據")
            return
        
        # 爬取市場數據
        report_id = fetch_market_data()
        if report_id:
            # 推送市場報告
            push_market_report(line_bot_api, report_id)
    
    # 在新執行緒中執行任務
    thread = threading.Thread(target=_task)
    thread.daemon = True
    thread.start()

def clean_cache():
    """清除過期的快取數據"""
    logger.info("清除過期的快取數據")
    # 在這裡實現清除快取的邏輯

def run_scheduler(line_bot_api):
    """
    運行排程器
    
    Args:
        line_bot_api: LINE Bot API 實例
    """
    # 設定排程任務
    schedule_market_data_job(line_bot_api)
    
    # 運行排程器
    while True:
        schedule.run_pending()
        time.sleep(1)

def start_scheduler_thread(line_bot_api):
    """
    在獨立執行緒中啟動排程器
    
    Args:
        line_bot_api: LINE Bot API 實例
    """
    scheduler_thread = threading.Thread(target=run_scheduler, args=(line_bot_api,))
    scheduler_thread.daemon = True
    scheduler_thread.start()
    logger.info("已在背景執行緒啟動排程器")
