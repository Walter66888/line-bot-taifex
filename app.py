"""
LINE BOT主應用程式 - 改進版
"""
import os
import logging
from datetime import datetime
import pytz
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, 
    SourceUser, SourceGroup, SourceRoom
)

from database.mongodb import (
    get_db, save_user_info, save_group_info, 
    is_user_authorized, is_group_authorized,
    get_latest_market_report, get_market_report_by_date,
    save_push_log
)
from utils import generate_market_report, generate_taiex_report, generate_institutional_report, generate_futures_report, generate_retail_report
from scheduler.market_data import start_scheduler_thread

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 設定台灣時區
TW_TIMEZONE = pytz.timezone('Asia/Taipei')

app = Flask(__name__)

# LINE BOT設定
try:
    line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
    handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))
except Exception as e:
    logger.error(f"LINE BOT初始化錯誤: {str(e)}")
    # 在開發環境中，使用假的LINE BOT API
    if os.environ.get('FLASK_ENV') == 'development':
        class DummyLineBotApi:
            def reply_message(self, *args, **kwargs):
                logger.info(f"DUMMY: reply_message({args}, {kwargs})")
            
            def push_message(self, *args, **kwargs):
                logger.info(f"DUMMY: push_message({args}, {kwargs})")
        
        class DummyWebhookHandler:
            def add(self, *args, **kwargs):
                pass
            
            def handle(self, *args, **kwargs):
                pass
        
        line_bot_api = DummyLineBotApi()
        handler = DummyWebhookHandler()
    else:
        raise

# 初始化資料庫連接
db = get_db()
if not db:
    logger.warning("無法連接到資料庫，某些功能可能不可用")

# 啟動排程器
if os.environ.get('ENABLE_SCHEDULER', 'true').lower() == 'true':
    start_scheduler_thread(line_bot_api)
    logger.info("已啟動市場數據排程器")

@app.route("/callback", methods=['POST'])
def callback():
    """LINE BOT Webhook回調函數"""
    if not handler:
        return 'LINE BOT not configured', 500
    
    # 獲取X-Line-Signature標頭
    signature = request.headers['X-Line-Signature']

    # 獲取請求體
    body = request.get_data(as_text=True)
    logger.info("Request body: " + body)

    # 處理webhook
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error("Invalid signature")
        abort(400)

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    """處理用戶發送的文字訊息"""
    text = event.message.text.strip()
    source_type = event.source.type
    reply_token = event.reply_token
    
    # 取得發送者ID
    if source_type == 'user':
        source_id = event.source.user_id
        # 儲存或更新用戶資訊
        try:
            profile = line_bot_api.get_profile(source_id)
            save_user_info(source_id, profile.display_name)
        except Exception as e:
            logger.error(f"獲取用戶資訊時出錯: {str(e)}")
    elif source_type == 'group':
        source_id = event.source.group_id
        # 儲存或更新群組資訊
        try:
            # 目前LINE API無法獲取群組名稱，所以只存ID
            save_group_info(source_id)
        except Exception as e:
            logger.error(f"儲存群組資訊時出錯: {str(e)}")
    elif source_type == 'room':
        source_id = event.source.room_id
        # 聊天室也視為群組處理
        try:
            save_group_info(source_id)
        except Exception as e:
            logger.error(f"儲存聊天室資訊時出錯: {str(e)}")
    else:
        source_id = None
    
    # 記錄請求
    logger.info(f"收到訊息: {text}，來源: {source_type}, ID: {source_id}")
    
    # 權限檢查 (如果啟用了資料庫)
    if db:
        authorized = False
        if source_type == 'user':
            authorized = is_user_authorized(source_id)
        elif source_type in ['group', 'room']:
            authorized = is_group_authorized(source_id)
        
        if not authorized:
            # 未授權的用戶或群組，建立資料並授予默認權限
            if source_type == 'user':
                try:
                    profile = line_bot_api.get_profile(source_id)
                    save_user_info(source_id, profile.display_name)
                    authorized = True
                except Exception as e:
                    logger.error(f"授權新用戶時出錯: {str(e)}")
            elif source_type in ['group', 'room']:
                try:
                    save_group_info(source_id)
                    authorized = True
                except Exception as e:
                    logger.error(f"授權新群組時出錯: {str(e)}")
    else:
        # 資料庫未連接時不做權限檢查
        authorized = True
    
    # 處理被加入好友或群組的情況
    if text == "":
        welcome_message = (
            "您好！我是台股籌碼快報機器人。\n\n"
            "您可以透過以下指令來使用我：\n"
            "- 輸入「籌碼快報」獲取今日完整籌碼報告\n"
            "- 輸入「加權指數」獲取今日加權指數資訊\n"
            "- 輸入「三大法人」獲取今日三大法人買賣超資訊\n"
            "- 輸入「期貨籌碼」獲取今日期貨籌碼資訊\n"
            "- 輸入「散戶籌碼」獲取今日散戶籌碼資訊\n"
            "- 輸入「籌碼說明」查看使用說明\n\n"
            "每天盤後約 14:45-14:50 會自動更新當日資料。"
        )
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text=welcome_message)
        )
        return
    
    # 處理命令
    if '籌碼快報' in text:
        logger.info(f"用戶 {source_id} 請求籌碼快報")
        
        # 生成市場報告
        report_text = generate_market_report()
        if report_text:
            line_bot_api.reply_message(
                reply_token,
                TextSendMessage(text=report_text)
            )
            
            # 記錄推送日誌
            if db:
                target_type = 'user' if source_type == 'user' else 'group'
                save_push_log(
                    target_type=target_type,
                    target_id=source_id,
                    report_date=datetime.now(TW_TIMEZONE).date(),
                    status='success',
                    message_type='full_report'
                )
        else:
            error_message = "抱歉，目前無法獲取籌碼快報，請稍後再試。"
            line_bot_api.reply_message(
                reply_token,
                TextSendMessage(text=error_message)
            )
    
    elif '加權指數' in text:
        logger.info(f"用戶 {source_id} 請求加權指數資訊")
        
        # 生成加權指數報告
        report_text = generate_taiex_report(get_latest_market_report())
        if report_text:
            line_bot_api.reply_message(
                reply_token,
                TextSendMessage(text=report_text)
            )
            
            # 記錄推送日誌
            if db:
                target_type = 'user' if source_type == 'user' else 'group'
                save_push_log(
                    target_type=target_type,
                    target_id=source_id,
                    report_date=datetime.now(TW_TIMEZONE).date(),
                    status='success',
                    message_type='taiex_report'
                )
        else:
            error_message = "抱歉，目前無法獲取加權指數資訊，請稍後再試。"
            line_bot_api.reply_message(
                reply_token,
                TextSendMessage(text=error_message)
            )
    
    elif '三大法人' in text:
        logger.info(f"用戶 {source_id} 請求三大法人資訊")
        
        # 生成三大法人報告
        report_text = generate_institutional_report(get_latest_market_report())
        if report_text:
            line_bot_api.reply_message(
                reply_token,
                TextSendMessage(text=report_text)
            )
            
            # 記錄推送日誌
            if db:
                target_type = 'user' if source_type == 'user' else 'group'
                save_push_log(
                    target_type=target_type,
                    target_id=source_id,
                    report_date=datetime.now(TW_TIMEZONE).date(),
                    status='success',
                    message_type='institutional_report'
                )
        else:
            error_message = "抱歉，目前無法獲取三大法人資訊，請稍後再試。"
            line_bot_api.reply_message(
                reply_token,
                TextSendMessage(text=error_message)
            )
    
    elif '期貨籌碼' in text:
        logger.info(f"用戶 {source_id} 請求期貨籌碼資訊")
        
        # 生成期貨籌碼報告
        report_text = generate_futures_report(get_latest_market_report())
        if report_text:
            line_bot_api.reply_message(
                reply_token,
                TextSendMessage(text=report_text)
            )
            
            # 記錄推送日誌
            if db:
                target_type = 'user' if source_type == 'user' else 'group'
                save_push_log(
                    target_type=target_type,
                    target_id=source_id,
                    report_date=datetime.now(TW_TIMEZONE).date(),
                    status='success',
                    message_type='futures_report'
                )
        else:
            error_message = "抱歉，目前無法獲取期貨籌碼資訊，請稍後再試。"
            line_bot_api.reply_message(
                reply_token,
                TextSendMessage(text=error_message)
            )
    
    elif '散戶籌碼' in text:
        logger.info(f"用戶 {source_id} 請求散戶籌碼資訊")
        
        # 生成散戶籌碼報告
        report_text = generate_retail_report(get_latest_market_report())
        if report_text:
            line_bot_api.reply_message(
                reply_token,
                TextSendMessage(text=report_text)
            )
            
            # 記錄推送日誌
            if db:
                target_type = 'user' if source_type == 'user' else 'group'
                save_push_log(
                    target_type=target_type,
                    target_id=source_id,
                    report_date=datetime.now(TW_TIMEZONE).date(),
                    status='success',
                    message_type='retail_report'
                )
        else:
            error_message = "抱歉，目前無法獲取散戶籌碼資訊，請稍後再試。"
            line_bot_api.reply_message(
                reply_token,
                TextSendMessage(text=error_message)
            )
    
    elif ('籌碼' in text and ('幫助' in text or '說明' in text)):
        help_text = (
            "📊 籌碼快報使用說明 📊\n\n"
            "主要功能：\n"
            "- 輸入「籌碼快報」獲取今日完整籌碼報告\n"
            "- 輸入「加權指數」獲取今日加權指數資訊\n"
            "- 輸入「三大法人」獲取今日三大法人買賣超資訊\n"
            "- 輸入「期貨籌碼」獲取今日期貨籌碼資訊\n"
            "- 輸入「散戶籌碼」獲取今日散戶籌碼資訊\n\n"
            "時間說明：\n"
            "- 每天盤後約 14:45-14:50 自動更新當日資料\n"
            "- 已設定自動推送的群組會在更新後自動收到通知\n\n"
            "🔹 籌碼數據來源：台灣期貨交易所、台灣證券交易所\n"
            "🔹 更多功能陸續開發中，敬請期待！"
        )
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text=help_text)
        )
    
    # 其他命令...
    else:
        # 如果沒有匹配的命令，提供幫助訊息
        help_text = (
            "您好！我是台股籌碼快報機器人。\n\n"
            "您可以透過以下指令來使用我：\n"
            "- 輸入「籌碼快報」獲取今日完整籌碼報告\n"
            "- 輸入「加權指數」獲取今日加權指數資訊\n"
            "- 輸入「三大法人」獲取今日三大法人買賣超資訊\n"
            "- 輸入「期貨籌碼」獲取今日期貨籌碼資訊\n"
            "- 輸入「散戶籌碼」獲取今日散戶籌碼資訊\n"
            "- 輸入「籌碼說明」查看使用說明\n\n"
            "每天盤後約 14:45-14:50 會自動更新當日資料。"
        )
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text=help_text)
        )

@app.route("/", methods=['GET'])
def index():
    """首頁"""
    return "LINE BOT Taiwan Futures Market Report is running!"

@app.route("/test", methods=['GET'])
def test():
    """測試頁面，用於開發環境測試"""
    if os.environ.get('FLASK_ENV') != 'development':
        return "Test endpoint is disabled in production", 403
    
    report = generate_market_report()
    return f"<pre>{report}</pre>"

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
