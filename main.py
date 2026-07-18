"""
main.py - Hybrid System (OpenAPI Real Prices + Paper Trading)
"""

import logging
import time
from twisted.internet import asyncioreactor
asyncioreactor.install()

from twisted.internet import reactor
from config import Config
from openapi_streamer import OpenApiStreamer
from market_scanner import MarketScanner, ScannerConfig
from risk_manager import RiskManager
from telegram_notifier import TelegramNotifier
import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger("forex_bot")

cfg = Config()
trading_halted = False

def get_db():
    try:
        return psycopg2.connect(cfg.database_url, connect_timeout=5)
    except Exception as e:
        logger.error(f"[DB] {e}")
        return None

def on_price_update(symbol_name, bid, ask):
    """أسعار حقيقية من OpenAPI"""
    global trading_halted
    if trading_halted:
        return
    
    signal = market_scanner.on_price(symbol_name, bid, ask)
    if signal.value == 0:
        return
    
    if not risk_manager.can_open_new_position():
        logger.warning(f"[Risk] حد أقصى من الصفقات المفتوحة")
        return
    
    is_buy = signal.name == "BUY_REVERSION"
    lot_size = risk_manager.calculate_position_size_lots(4.0)
    
    if lot_size <= 0:
        return
    
    entry_price = (bid + ask) / 2
    
    if is_buy:
        sl_price = entry_price - 0.0004
        tp_price = entry_price + 0.0006
    else:
        sl_price = entry_price + 0.0004
        tp_price = entry_price - 0.0006
    
    logger.info(
        f"[TRADE_OPEN] {symbol_name} {'BUY' if is_buy else 'SELL'} "
        f"{lot_size} لوت @ {entry_price:.5f} SL:{sl_price:.5f} TP:{tp_price:.5f}"
    )
    
    conn = get_db()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO live_paper_trades 
                    (symbol, direction, entry_price, sl_price, tp_price, status, opened_at)
                    VALUES (%s, %s, %s, %s, %s, 'OPEN', NOW())
                    RETURNING id
                """, (symbol_name, 'BUY' if is_buy else 'SELL', entry_price, sl_price, tp_price))
                trade_id = cur.fetchone()[0]
                conn.commit()
            
            telegram_notifier.notify_system_event(
                f"📊 صفقة جديدة #{trade_id}\n"
                f"الزوج: {symbol_name}\n"
                f"اتجاه: {'شراء' if is_buy else 'بيع'}\n"
                f"الحجم: {lot_size} لوت\n"
                f"السعر: {entry_price:.5f}"
            )
        except Exception as e:
            logger.error(f"[DB] {e}")
        finally:
            conn.close()

def on_account_info(balance, equity):
    """تحديث حالة الحساب"""
    risk_manager.update_account_info(balance, equity)
    logger.info(f"[Account] الرصيد: ${balance:.2f} | الإنصاف: ${equity:.2f}")

def on_emergency_close_all(reason):
    """إغلاق طارئ"""
    global trading_halted
    trading_halted = True
    logger.critical(f"[Emergency] {reason}")
    telegram_notifier.notify_emergency_halt(reason)

def on_reconcile(positions):
    """مصالحة الصفقات عند البدء"""
    logger.info(f"[Reconcile] {len(positions)} صفقة مفتوحة على الخادم")
    for pos in positions:
        risk_manager.register_open_position(pos)

def start_system():
    global trading_halted
    trading_halted = False
    
    logger.info("="*60)
    logger.info("🚀 بدء النظام الهجين - OpenAPI + Paper Trading")
    logger.info(f"📊 الأزواج: {', '.join(cfg.risk.target_symbols)}")
    logger.info("🔒 الأسعار: حقيقية من cTrader")
    logger.info("📝 الصفقات: محاكاة (Paper Trading)")
    logger.info("="*60)
    
    openapi_streamer.start()
    
    telegram_notifier.notify_system_event(
        f"🚀 النظام بدأ\n"
        f"📊 الأزواج: {', '.join(cfg.risk.target_symbols)}\n"
        f"🔒 Prices: Real cTrader\n"
        f"📝 Trades: Paper Trading"
    )

if __name__ == '__main__':
    try:
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
        
        openapi_streamer = OpenApiStreamer(
            cfg,
            on_price_update=on_price_update,
            on_account_info=on_account_info,
            on_reconcile=on_reconcile
        )
        
        reactor.callWhenRunning(start_system)
        reactor.run()
        
    except KeyboardInterrupt:
        logger.info("⏹️ إيقاف البوت...")
        reactor.stop()
    except Exception as e:
        logger.critical(f"[Fatal Error] {e}")
        telegram_notifier.notify_system_event(f"💥 خطأ حرج: {e}")
