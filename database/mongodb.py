"""
MongoDB 資料庫連接和操作模組
"""
import os
import logging
from datetime import datetime
import pytz
import pymongo
from pymongo import MongoClient
from bson.objectid import ObjectId

# 設定日誌
logger = logging.getLogger(__name__)

# 設定台灣時區
TW_TIMEZONE = pytz.timezone('Asia/Taipei')

# 從環境變數獲取 MongoDB 連接字串
MONGODB_URI = os.environ.get('MONGODB_URI')

# MongoDB 資料庫和集合名稱
DB_NAME = os.environ.get('MONGODB_DB_NAME', 'taifex_market_data')
MARKET_REPORTS_COLLECTION = 'market_reports'
USERS_COLLECTION = 'users'
GROUPS_COLLECTION = 'groups'
PUSH_LOGS_COLLECTION = 'push_logs'

# 全局 MongoDB 客戶端和資料庫實例
client = None
db = None

def get_db():
    """
    取得資料庫連接，如果尚未連接則建立連接
    
    Returns:
        MongoDB 資料庫實例
    """
    global client, db
    
    if db is None:
        try:
            # 連接 MongoDB
            if not MONGODB_URI:
                logger.error("未設定 MONGODB_URI 環境變數")
                return None
            
            client = MongoClient(MONGODB_URI)
            db = client[DB_NAME]
            
            # 建立必要的索引
            _setup_indexes()
            
            logger.info(f"已成功連接到 MongoDB 資料庫: {DB_NAME}")
        except Exception as e:
            logger.error(f"連接 MongoDB 時發生錯誤: {str(e)}")
            db = None
    
    return db

def _setup_indexes():
    """設定資料庫索引"""
    try:
        # market_reports 集合索引
        db[MARKET_REPORTS_COLLECTION].create_index([("date", pymongo.ASCENDING)], unique=True)
        db[MARKET_REPORTS_COLLECTION].create_index([("created_at", pymongo.DESCENDING)])
        
        # users 集合索引
        db[USERS_COLLECTION].create_index([("line_user_id", pymongo.ASCENDING)], unique=True)
        db[USERS_COLLECTION].create_index([("status", pymongo.ASCENDING)])
        db[USERS_COLLECTION].create_index([("subscription_type", pymongo.ASCENDING)])
        
        # groups 集合索引
        db[GROUPS_COLLECTION].create_index([("line_group_id", pymongo.ASCENDING)], unique=True)
        db[GROUPS_COLLECTION].create_index([("status", pymongo.ASCENDING)])
        db[GROUPS_COLLECTION].create_index([("auto_push", pymongo.ASCENDING)])
        
        # push_logs 集合索引
        db[PUSH_LOGS_COLLECTION].create_index([
            ("target_id", pymongo.ASCENDING), 
            ("report_date", pymongo.ASCENDING)
        ])
        db[PUSH_LOGS_COLLECTION].create_index([("push_time", pymongo.DESCENDING)])
        db[PUSH_LOGS_COLLECTION].create_index([("status", pymongo.ASCENDING)])
        
        logger.info("已成功設定 MongoDB 索引")
    except Exception as e:
        logger.error(f"設定 MongoDB 索引時發生錯誤: {str(e)}")

def save_market_report(report_data):
    """
    儲存市場報告到資料庫
    
    Args:
        report_data: 市場報告資料字典
        
    Returns:
        ObjectId: 儲存的文檔ID
    """
    try:
        db = get_db()
        if not db:
            return None
        
        # 轉換日期格式
        date_obj = datetime.strptime(report_data['date'], '%Y%m%d')
        date_tw = date_obj.replace(tzinfo=TW_TIMEZONE)
        
        # 格式化日期字串 (例如 2025/04/11)
        date_string = date_obj.strftime('%Y/%m/%d')
        
        # 獲取星期幾 (中文)
        weekday_mapping = {
            0: '一',
            1: '二',
            2: '三',
            3: '四',
            4: '五',
            5: '六',
            6: '日'
        }
        weekday = weekday_mapping[date_obj.weekday()]
        
        # 準備資料庫文檔
        now = datetime.now(TW_TIMEZONE)
        document = {
            "date": date_obj,
            "date_string": date_string,
            "weekday": weekday,
            "taiex": {
                "close": report_data.get('taiex', {}).get('close', 0),
                "change": report_data.get('taiex', {}).get('change', 0),
                "change_percent": report_data.get('taiex', {}).get('change_percent', 0),
                "volume": report_data.get('taiex', {}).get('volume', 0)
            },
            "futures": {
                "close": report_data.get('futures', {}).get('close', 0),
                "change": report_data.get('futures', {}).get('change', 0),
                "change_percent": report_data.get('futures', {}).get('change_percent', 0),
                "bias": report_data.get('futures', {}).get('bias', 0)
            },
            "institutional": {
                "total": report_data.get('institutional', {}).get('total', 0),
                "foreign": report_data.get('institutional', {}).get('foreign', 0),
                "investment_trust": report_data.get('institutional', {}).get('investment_trust', 0),
                "dealer": report_data.get('institutional', {}).get('dealer', 0),
                "dealer_self": report_data.get('institutional', {}).get('dealer_self', 0),
                "dealer_hedge": report_data.get('institutional', {}).get('dealer_hedge', 0),
                # 連續買賣超天數需另外計算
                "foreign_consecutive_days": report_data.get('institutional', {}).get('foreign_consecutive_days', 0),
                "investment_trust_consecutive_days": report_data.get('institutional', {}).get('investment_trust_consecutive_days', 0),
                "dealer_consecutive_days": report_data.get('institutional', {}).get('dealer_consecutive_days', 0)
            },
            "futures_positions": {
                "foreign_tx_net": report_data.get('futures_positions', {}).get('foreign_tx_net', 0),
                "foreign_tx_net_change": report_data.get('futures_positions', {}).get('foreign_tx_net_change', 0),
                "foreign_mtx_net": report_data.get('futures_positions', {}).get('foreign_mtx_net', 0),
                "foreign_mtx_net_change": report_data.get('futures_positions', {}).get('foreign_mtx_net_change', 0),
                "foreign_call_net": report_data.get('futures_positions', {}).get('foreign_call_net', 0),
                "foreign_call_net_change": report_data.get('futures_positions', {}).get('foreign_call_net_change', 0),
                "foreign_put_net": report_data.get('futures_positions', {}).get('foreign_put_net', 0),
                "foreign_put_net_change": report_data.get('futures_positions', {}).get('foreign_put_net_change', 0),
                "top10_traders_net": report_data.get('futures_positions', {}).get('top10_traders_net', 0),
                "top10_traders_net_change": report_data.get('futures_positions', {}).get('top10_traders_net_change', 0),
                "top10_specific_net": report_data.get('futures_positions', {}).get('top10_specific_net', 0),
                "top10_specific_net_change": report_data.get('futures_positions', {}).get('top10_specific_net_change', 0)
            },
            "retail_positions": {
                "mtx_net": report_data.get('retail_positions', {}).get('mtx_net', 0),
                "mtx_net_change": report_data.get('retail_positions', {}).get('mtx_net_change', 0),
                "xmtx_net": report_data.get('retail_positions', {}).get('xmtx_net', 0),
                "xmtx_net_change": report_data.get('retail_positions', {}).get('xmtx_net_change', 0)
            },
            "market_indicators": {
                "mtx_retail_ratio": report_data.get('market_indicators', {}).get('mtx_retail_ratio', 0),
                "mtx_retail_ratio_prev": report_data.get('market_indicators', {}).get('mtx_retail_ratio_prev', 0),
                "xmtx_retail_ratio": report_data.get('market_indicators', {}).get('xmtx_retail_ratio', 0),
                "xmtx_retail_ratio_prev": report_data.get('market_indicators', {}).get('xmtx_retail_ratio_prev', 0),
                "put_call_ratio": report_data.get('market_indicators', {}).get('put_call_ratio', 0),
                "put_call_ratio_prev": report_data.get('market_indicators', {}).get('put_call_ratio_prev', 0),
                "vix": report_data.get('market_indicators', {}).get('vix', 0),
                "vix_prev": report_data.get('market_indicators', {}).get('vix_prev', 0)
            },
            "created_at": now,
            "updated_at": now,
            "is_pushed": False,
            "push_time": None
        }
        
        # 使用 upsert 操作，如果今日資料已存在則更新，否則新增
        result = db[MARKET_REPORTS_COLLECTION].update_one(
            {"date": date_obj},
            {"$set": document},
            upsert=True
        )
        
        if result.upserted_id:
            logger.info(f"已新增市場報告: {date_string}")
            return result.upserted_id
        else:
            logger.info(f"已更新市場報告: {date_string}")
            # 查詢並返回文檔 ID
            doc = db[MARKET_REPORTS_COLLECTION].find_one({"date": date_obj})
            return doc.get('_id') if doc else None
    
    except Exception as e:
        logger.error(f"儲存市場報告時發生錯誤: {str(e)}")
        return None

def get_latest_market_report():
    """
    獲取最新的市場報告
    
    Returns:
        dict: 市場報告資料字典，如果沒有找到則返回 None
    """
    try:
        db = get_db()
        if not db:
            return None
        
        # 按建立時間降序排序，獲取第一筆資料
        report = db[MARKET_REPORTS_COLLECTION].find_one(
            sort=[("created_at", pymongo.DESCENDING)]
        )
        
        return report
    
    except Exception as e:
        logger.error(f"獲取最新市場報告時發生錯誤: {str(e)}")
        return None

def get_market_report_by_date(date_str):
    """
    按日期獲取市場報告
    
    Args:
        date_str: 日期字串，格式為 'YYYYMMDD'
        
    Returns:
        dict: 市場報告資料字典，如果沒有找到則返回 None
    """
    try:
        db = get_db()
        if not db:
            return None
        
        # 轉換日期格式
        date_obj = datetime.strptime(date_str, '%Y%m%d')
        
        # 查詢報告
        report = db[MARKET_REPORTS_COLLECTION].find_one({"date": date_obj})
        
        return report
    
    except Exception as e:
        logger.error(f"按日期獲取市場報告時發生錯誤: {str(e)}")
        return None

def update_consecutive_days():
    """
    更新三大法人連續買賣超天數
    """
    try:
        db = get_db()
        if not db:
            return
        
        # 獲取最新報告
        latest_report = get_latest_market_report()
        if not latest_report:
            logger.warning("找不到最新報告，無法更新連續買賣超天數")
            return
        
        # 獲取昨日報告
        yesterday = (latest_report['date'] - timedelta(days=1))
        yesterday_report = db[MARKET_REPORTS_COLLECTION].find_one({"date": yesterday})
        
        # 計算各法人連續買賣超天數
        if yesterday_report:
            # 外資
            if (latest_report['institutional']['foreign'] > 0 and 
                yesterday_report['institutional']['foreign_consecutive_days'] > 0):
                foreign_days = yesterday_report['institutional']['foreign_consecutive_days'] + 1
            elif (latest_report['institutional']['foreign'] < 0 and 
                  yesterday_report['institutional']['foreign_consecutive_days'] < 0):
                foreign_days = yesterday_report['institutional']['foreign_consecutive_days'] - 1
            else:
                foreign_days = 1 if latest_report['institutional']['foreign'] > 0 else -1
                
            # 投信
            if (latest_report['institutional']['investment_trust'] > 0 and 
                yesterday_report['institutional']['investment_trust_consecutive_days'] > 0):
                it_days = yesterday_report['institutional']['investment_trust_consecutive_days'] + 1
            elif (latest_report['institutional']['investment_trust'] < 0 and 
                  yesterday_report['institutional']['investment_trust_consecutive_days'] < 0):
                it_days = yesterday_report['institutional']['investment_trust_consecutive_days'] - 1
            else:
                it_days = 1 if latest_report['institutional']['investment_trust'] > 0 else -1
                
            # 自營商
            if (latest_report['institutional']['dealer'] > 0 and 
                yesterday_report['institutional']['dealer_consecutive_days'] > 0):
                dealer_days = yesterday_report['institutional']['dealer_consecutive_days'] + 1
            elif (latest_report['institutional']['dealer'] < 0 and 
                  yesterday_report['institutional']['dealer_consecutive_days'] < 0):
                dealer_days = yesterday_report['institutional']['dealer_consecutive_days'] - 1
            else:
                dealer_days = 1 if latest_report['institutional']['dealer'] > 0 else -1
        else:
            # 如果沒有昨日資料，則只設定今日方向
            foreign_days = 1 if latest_report['institutional']['foreign'] > 0 else -1
            it_days = 1 if latest_report['institutional']['investment_trust'] > 0 else -1
            dealer_days = 1 if latest_report['institutional']['dealer'] > 0 else -1
        
        # 更新最新報告
        db[MARKET_REPORTS_COLLECTION].update_one(
            {"_id": latest_report['_id']},
            {"$set": {
                "institutional.foreign_consecutive_days": foreign_days,
                "institutional.investment_trust_consecutive_days": it_days,
                "institutional.dealer_consecutive_days": dealer_days,
                "updated_at": datetime.now(TW_TIMEZONE)
            }}
        )
        
        logger.info(f"已更新連續買賣超天數: 外資={foreign_days}, 投信={it_days}, 自營商={dealer_days}")
    
    except Exception as e:
        logger.error(f"更新連續買賣超天數時發生錯誤: {str(e)}")

def mark_report_as_pushed(report_id):
    """
    標記報告已推送
    
    Args:
        report_id: 報告ID
    """
    try:
        db = get_db()
        if not db:
            return
        
        now = datetime.now(TW_TIMEZONE)
        
        db[MARKET_REPORTS_COLLECTION].update_one(
            {"_id": ObjectId(report_id)},
            {"$set": {
                "is_pushed": True,
                "push_time": now,
                "updated_at": now
            }}
        )
        
        logger.info(f"已標記報告 {report_id} 為已推送")
    
    except Exception as e:
        logger.error(f"標記報告已推送時發生錯誤: {str(e)}")

def save_push_log(target_type, target_id, report_date, status, message_type, error_message=None):
    """
    儲存推送日誌
    
    Args:
        target_type: 目標類型 ('group' 或 'user')
        target_id: 目標ID
        report_date: 報告日期
        status: 狀態 ('success' 或 'failure')
        message_type: 訊息類型
        error_message: 錯誤訊息 (僅在失敗時適用)
    """
    try:
        db = get_db()
        if not db:
            return
        
        now = datetime.now(TW_TIMEZONE)
        
        document = {
            "target_type": target_type,
            "target_id": target_id,
            "report_date": report_date,
            "push_time": now,
            "status": status,
            "message_type": message_type,
            "error_message": error_message
        }
        
        db[PUSH_LOGS_COLLECTION].insert_one(document)
        
        logger.info(f"已儲存推送日誌: {target_type} {target_id}, 狀態={status}")
    
    except Exception as e:
        logger.error(f"儲存推送日誌時發生錯誤: {str(e)}")

def get_groups_for_push():
    """
    獲取需要自動推送的群組列表
    
    Returns:
        list: 群組列表
    """
    try:
        db = get_db()
        if not db:
            return []
        
        groups = list(db[GROUPS_COLLECTION].find({
            "status": "active",
            "auto_push": True
        }))
        
        return groups
    
    except Exception as e:
        logger.error(f"獲取需要推送的群組時發生錯誤: {str(e)}")
        return []

def save_user_info(line_user_id, display_name):
    """
    儲存或更新用戶信息
    
    Args:
        line_user_id: LINE 用戶ID
        display_name: 顯示名稱
    """
    try:
        db = get_db()
        if not db:
            return
        
        now = datetime.now(TW_TIMEZONE)
        
        db[USERS_COLLECTION].update_one(
            {"line_user_id": line_user_id},
            {"$set": {
                "display_name": display_name,
                "last_active": now
            }, "$setOnInsert": {
                "status": "active",
                "subscription_type": "free",
                "created_at": now,
                "preferences": {
                    "notification_time": "14:50",
                    "notification_enabled": False,
                    "report_format": "full"
                }
            }},
            upsert=True
        )
        
        logger.info(f"已更新用戶信息: {line_user_id}")
    
    except Exception as e:
        logger.error(f"儲存用戶信息時發生錯誤: {str(e)}")

def save_group_info(line_group_id, group_name=None):
    """
    儲存或更新群組信息
    
    Args:
        line_group_id: LINE 群組ID
        group_name: 群組名稱
    """
    try:
        db = get_db()
        if not db:
            return
        
        now = datetime.now(TW_TIMEZONE)
        
        update = {
            "$set": {
                "last_active": now
            }, 
            "$setOnInsert": {
                "status": "active",
                "subscription_type": "free",
                "created_at": now,
                "auto_push": False,
                "push_time": "14:50"
            }
        }
        
        if group_name:
            update["$set"]["group_name"] = group_name
        
        db[GROUPS_COLLECTION].update_one(
            {"line_group_id": line_group_id},
            update,
            upsert=True
        )
        
        logger.info(f"已更新群組信息: {line_group_id}")
    
    except Exception as e:
        logger.error(f"儲存群組信息時發生錯誤: {str(e)}")

def is_user_authorized(line_user_id):
    """
    檢查用戶是否已授權
    
    Args:
        line_user_id: LINE 用戶ID
        
    Returns:
        bool: 是否已授權
    """
    try:
        db = get_db()
        if not db:
            return False
        
        user = db[USERS_COLLECTION].find_one({
            "line_user_id": line_user_id,
            "status": "active"
        })
        
        return user is not None
    
    except Exception as e:
        logger.error(f"檢查用戶授權時發生錯誤: {str(e)}")
        return False

def is_group_authorized(line_group_id):
    """
    檢查群組是否已授權
    
    Args:
        line_group_id: LINE 群組ID
        
    Returns:
        bool: 是否已授權
    """
    try:
        db = get_db()
        if not db:
            return False
        
        group = db[GROUPS_COLLECTION].find_one({
            "line_group_id": line_group_id,
            "status": "active"
        })
        
        return group is not None
    
    except Exception as e:
        logger.error(f"檢查群組授權時發生錯誤: {str(e)}")
        return False
