"""
main.py - Paper Trading Mode
"""

import logging
import time
from market_scanner import MarketScanner, ScannerConfig
from risk_manager import RiskManager
from telegram_notifier import TelegramNotifier
from config import Config
import requests

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger("forex_bot")

cfg = Config()

def fetch_prices():
    try:
        response = requests.get("https://www.freeforexapi.com/api/latest?pairs=EURUSD,GBPUSD,USDJPY,AUDUSD", timeout=5)
        if response.status_code == 200:
            return response.json().get("rates", {})
        return None
    except Exception as e:
        logger.error(f"[Price Fetch Error] {e}")
        return None

def on_emergency_close_all(reason):
    logger.critical(f"[Emergency] {reason}")

def main():
    logger.info("="*60)
    logger.info("🚀 بدء نظام التداول - Paper Trading")
    logger.info(f"📊 الأزواج: EURUSD, GBPUSD, USDJPY, AUDUSD")
    logger.info(f"🔒 Mode: Paper Trading (محاكاة)")
    logger.info("="*60)
    
    market_scanner = MarketScanner(
        ScannerConfig(
            std_period=20,
            entry_std_multiplier=2.5,
            max_allowed_spread_pips=0.3
        ),
        symbols=cfg.risk.target_symbols
    )
    
    risk_manager = RiskManager(
        cfg.risk,
        on_emergency_close_all=on_emergency_close_all
    )
    
    telegram_notifier = TelegramNotifier(cfg.telegram)
    
    telegram_notifier.notify_system_event(
        "🚀 نظام التداول بدأ\n📊 الأزواج: EURUSD, GBPUSD, USDJPY, AUDUSD\n🔒 Mode: Paper Trading"
    )
    
    try:
        while True:
            prices = fetch_prices()
            if not prices:
                logger.warning("[Price Fetch] فشل جلب الأسعار، سيحاول مجدداً...")
                time.sleep(5)
                continue
            
            for symbol in cfg.risk.target_symbols:
                if symbol not in prices:
                    continue
                
                rate = prices[symbol]
                bid = rate.get("bid", 0)
                ask = rate.get("ask", 0)
                
                if bid > 0 and ask > 0:
                    signal = market_scanner.on_price(symbol, bid, ask)
                    
                    if signal.value > 0:
                        if risk_manager.can_open_new_position():
                            lot_size = risk_manager.calculate_position_size_lots(4.0)
                            is_buy = signal.name == "BUY_REVERSION"
                            
                            logger.info(
                                f"[TRADE] {symbol} {'BUY' if is_buy else 'SELL'} "
                                f"{lot_size} لوت @ {(bid+ask)/2:.5f}"
                            )
                            
                            telegram_notifier.notify_system_event(
                                f"📊 صفقة جديدة\n"
                                f"الزوج: {symbol}\n"
                                f"اتجاه: {'شراء' if is_buy else 'بيع'}\n"
                                f"الحجم: {lot_size} لوت\n"
                                f"السعر: {(bid+ask)/2:.5f}"
                            )
            
            time.sleep(30)
    
    except KeyboardInterrupt:
        logger.info("⏹️ إيقاف البوت...")
        telegram_notifier.notify_system_event("⏹️ تم إيقاف النظام")
    except Exception as e:
        logger.critical(f"[Fatal Error] {e}")
        telegram_notifier.notify_system_event(f"💥 خطأ حرج: {e}")

if __name__ == '__main__':
    main()
