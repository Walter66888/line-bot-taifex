"""
本地測試運行腳本
"""
import os
import sys
import logging
from datetime import datetime
import pytz
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# 設定開發環境變數
os.environ['FLASK_ENV'] = 'development'
os.environ['ENABLE_SCHEDULER'] = 'false'  # 關閉排程器，避免自動任務干擾測試

def test_fetch_market_data():
    """測試爬取市場數據"""
    from scheduler.market_data import fetch_market_data
    
    logger.info("開始測試爬取市場數據")
    report_id = fetch_market_data()
    
    if report_id:
        logger.info(f"市場數據爬取成功，報告ID: {report_id}")
        return True
    else:
        logger.error("市場數據爬取失敗")
        return False

def test_generate_market_report():
    """測試生成市場報告"""
    from utils import generate_market_report
    
    logger.info("開始測試生成市場報告")
    report = generate_market_report()
    
    if report:
        logger.info("市場報告生成成功")
        print("\n" + "-" * 80 + "\n")
        print(report)
        print("\n" + "-" * 80 + "\n")
        return True
    else:
        logger.error("市場報告生成失敗")
        return False

def test_database_connection():
    """測試資料庫連接"""
    from database.mongodb import get_db
    
    logger.info("開始測試資料庫連接")
    db = get_db()
    
    if db:
        logger.info("資料庫連接成功")
        return True
    else:
        logger.error("資料庫連接失敗")
        return False

def run_test():
    """運行所有測試"""
    tests = [
        ("資料庫連接", test_database_connection),
        ("爬取市場數據", test_fetch_market_data),
        ("生成市場報告", test_generate_market_report)
    ]
    
    results = []
    
    for name, test_func in tests:
        logger.info(f"執行測試: {name}")
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            logger.error(f"測試 {name} 出錯: {str(e)}")
            results.append((name, False))
    
    # 顯示測試結果
    print("\n" + "=" * 50)
    print("測試結果摘要:")
    print("=" * 50)
    
    for name, result in results:
        status = "✅ 通過" if result else "❌ 失敗"
        print(f"{name}: {status}")
    
    print("=" * 50 + "\n")

def run_app():
    """運行 Flask 應用程式"""
    from app import app
    
    logger.info("啟動 Flask 應用程式")
    app.run(host='0.0.0.0', port=5000, debug=True)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='本地測試運行腳本')
    parser.add_argument('--test', action='store_true', help='運行測試')
    parser.add_argument('--app', action='store_true', help='運行 Flask 應用程式')
    
    args = parser.parse_args()
    
    if args.test:
        run_test()
    elif args.app:
        run_app()
    else:
        # 默認運行所有測試
        run_test()
        
        # 詢問是否運行 Flask 應用程式
        response = input("是否要啟動 Flask 應用程式？(y/n): ")
        if response.lower() in ['y', 'yes']:
            run_app()
