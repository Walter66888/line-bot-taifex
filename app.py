"""
LINE BOT主應用程式
"""
import os
import logging
from datetime import datetime
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

from crawler.taiex import get_taiex_data
from crawler.futures import get_futures_data
from crawler.institutional import get_institutional_investors_data
from crawler.pc_ratio import get_pc_ratio
from crawler.vix import get_vix_data

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
        line_bot_api = DummyLineBotApi()
        handler = None
    else:
        raise

# 用戶認證
authorized_users = [user.strip() for user in os.environ.get('AUTHORIZED_USERS', '').split(',') if user.strip()]
authorized_groups = [group.strip() for group in os.environ.get('AUTHORIZED_GROUPS', '').split(',') if group.strip()]

# 快取市場報告
cached_report = None
cached_report_date = None

def format_market_report(taiex_data, futures_data, institutional_data, pc_ratio_data, vix_data, retail_indicators):
    """
    格式化市場報告
    
    Args:
        taiex_data: 加權指數數據
        futures_data: 期貨數據
        institutional_data: 三大法人數據
        pc_ratio_data: PC Ratio數據
        vix_data: VIX指標數據
        retail_indicators: 散戶指標數據
        
    Returns:
        str: 格式化後的市場報告
    """
    date_str = datetime.now().strftime('%Y/%m/%d')
    
    # 處理None值
    if not taiex_data:
        taiex_data = {'close': 0.0, 'change': 0.0, 'change_percent': 0.0, 'volume': 0.0}
    if not futures_data:
        futures_data = {'close': 0.0, 'change': 0.0, 'change_percent': 0.0, 'bias': 0.0}
    if not institutional_data:
        institutional_data = {'total': 0.0, 'foreign': 0.0, 'investment_trust': 0.0, 'dealer': 0.0, 'dealer_self': 0.0, 'dealer_hedge': 0.0}
    if not pc_ratio_data:
        pc_ratio_data = {'vol_ratio': 0.0, 'oi_ratio': 0.0}
    if not retail_indicators:
        retail_indicators = {'mtx': 0.0, 'xmtx': 0.0}
    
    report = f"[盤後籌碼快報] {date_str}\n\n"
    
    # 加權指數
    report += f"加權指數\n"
    report += f"{taiex_data['close']:.2f} {'▲' if taiex_data['change'] > 0 else '▼'}{abs(taiex_data['change']):.2f} ({abs(taiex_data['change_percent']):.2f}%) {taiex_data['volume']:.2f}億元\n\n"
    
    # 台指期(近)
    report += f"台指期(近)\n"
    report += f"{futures_data['close']:.2f} {'▲' if futures_data['change'] > 0 else '▼'}{abs(futures_data['change']):.2f} ({abs(futures_data['change_percent']):.2f}%) {futures_data['bias']:.2f} (偏差)\n\n"
    
    # 三大法人現貨買賣超(億元)
    report += f"三大法人現貨買賣超(億元)\n"
    report += f"合計: {'+' if institutional_data['total'] > 0 else ''}{institutional_data['total']:.2f}\n"
    report += f"外資: {'+' if institutional_data['foreign'] > 0 else ''}{institutional_data['foreign']:.2f}\n"
    report += f"投信: {'+' if institutional_data['investment_trust'] > 0 else ''}{institutional_data['investment_trust']:.2f}\n"
    report += f"自營商: {'+' if institutional_data['dealer'] > 0 else ''}{institutional_data['dealer']:.2f}\n"
    report += f"  自營商: {'+' if institutional_data['dealer_self'] > 0 else ''}{institutional_data['dealer_self']:.2f}\n"
    report += f"  避險: {'+' if institutional_data['dealer_hedge'] > 0 else ''}{institutional_data['dealer_hedge']:.2f}\n\n"
    
    # 外資及大額交易人期貨(口)
    report += f"外資及大額交易人期貨(口)\n"
    report += f"外資台指期: {'+' if futures_data.get('foreign_tx', 0) > 0 else ''}{futures_data.get('foreign_tx', 0)}\n"
    report += f"外資小台指: {'+' if futures_data.get('foreign_mtx', 0) > 0 else ''}{futures_data.get('foreign_mtx', 0)}\n"
    
    # 其他指標
    report += f"其他指標\n"
    report += f"小台散戶指標: {retail_indicators['mtx']:.2f}%\n"
    report += f"微台散戶指標: {retail_indicators['xmtx']:.2f}%\n"
    report += f"PC ratio 未平倉比: {pc_ratio_data['oi_ratio']:.2f}\n"
    report += f"VIX指標: {vix_data:.2f}\n"
    
    return report

def get_market_report():
    """
    獲取最新市場報告，使用快取提高效率
    
    Returns:
        str: 市場報告
    """
    global cached_report, cached_report_date
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 如果今天已經生成過報告，則直接使用快取
    if cached_report and cached_report_date == today:
        return cached_report
    
    # 否則生成新的報告
    try:
        logger.info("開始獲取市場數據...")
        
        taiex_data = get_taiex_data()
        logger.info(f"獲取加權指數數據: {taiex_data}")
        
        futures_data = get_futures_data()
        logger.info(f"獲取期貨數據: {futures_data}")
        
        institutional_data = get_institutional_investors_data()
        logger.info(f"獲取三大法人數據: {institutional_data}")
        
        pc_ratio_data = get_pc_ratio()
        logger.info(f"獲取PC Ratio數據: {pc_ratio_data}")
        
        vix_data = get_vix_data()
        logger.info(f"獲取VIX指標數據: {vix_data}")
        
        # 計算散戶指標
        mtx_institutional_net = futures_data.get('mtx_dealer_net', 0) + futures_data.get('mtx_it_net', 0) + futures_data.get('mtx_foreign_net', 0)
        mtx_oi = futures_data.get('mtx_oi', 1)  # 避免除以零
        mtx_retail_indicator = -mtx_institutional_net / mtx_oi * 100 if mtx_oi > 0 else 0.0
        
        xmtx_institutional_net = futures_data.get('xmtx_dealer_net', 0) + futures_data.get('xmtx_it_net', 0) + futures_data.get('xmtx_foreign_net', 0)
        xmtx_oi = futures_data.get('xmtx_oi', 1)  # 避免除以零
        xmtx_retail_indicator = -xmtx_institutional_net / xmtx_oi * 100 if xmtx_oi > 0 else 0.0
        
        retail_indicators = {
            'mtx': mtx_retail_indicator,
            'xmtx': xmtx_retail_indicator
        }
        logger.info(f"計算散戶指標: {retail_indicators}")
        
        # 格式化報告
        report = format_market_report(
            taiex_data, 
            futures_data, 
            institutional_data, 
            pc_ratio_data, 
            vix_data, 
            retail_indicators
        )
        
        # 更新快取
        cached_report = report
        cached_report_date = today
        
        logger.info("市場報告生成完成")
        return report
    except Exception as e:
        logger.error(f"獲取市場報告時發生錯誤: {str(e)}")
        return f"獲取市場報告時發生錯誤: {str(e)}"

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
    user_id = event.source.user_id
    
    # 來源類型檢查
    if event.source.type == 'user':
        source_id = user_id
        allowed_ids = authorized_users
    elif event.source.type == 'group':
        source_id = event.source.group_id
        allowed_ids = authorized_groups
    elif event.source.type == 'room':
        source_id = event.source.room_id
        allowed_ids = authorized_groups
    else:
        source_id = None
        allowed_ids = []
    
    # 權限檢查
    if allowed_ids and source_id not in allowed_ids:
        logger.warning(f"未授權的用戶/群組: {source_id}")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="抱歉，您沒有使用權限。")
        )
        return
    
    # 命令處理
    if text in ['最新籌碼快報', '籌碼快報']:
        logger.info(f"用戶 {source_id} 請求籌碼快報")
        report = get_market_report()
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=report)
        )
    elif '籌碼' in text and ('幫助' in text or '說明' in text):
        help_text = (
            "籌碼快報使用指南:\n\n"
            "- 輸入「最新籌碼快報」或「籌碼快報」獲取完整報告\n"
            "- 其他功能正在開發中...\n"
        )
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=help_text)
        )
    # 其他命令...

@app.route("/", methods=['GET'])
def index():
    """首頁"""
    return "LINE BOT Taiwan Futures Market Report is running!"

@app.route("/test", methods=['GET'])
def test():
    """測試頁面，用於開發環境測試"""
    if os.environ.get('FLASK_ENV') != 'development':
        return "Test endpoint is disabled in production", 403
    
    report = get_market_report()
    return f"<pre>{report}</pre>"

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
