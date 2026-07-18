"""
main.py - Pure Paper Trading Mode
"""

import logging
import time
import random
from market_scanner import MarketScanner, ScannerConfig
from risk_manager import RiskManager
from telegram_notifier import TelegramNotifier
from config import Config
import psycopg2

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger("forex_bot")

cfg = Config()

PRICES = {
    "EURUSD": 1.0850,
    "GBPUSD": 1.2750,
    "USDJPY": 149.50,
    "AUDUSD": 0.6580
}

def get_db():
    try:
        return psycopg2.connect(cfg.database_url, connect_timeout=5)
    except Exception as e:
        logger.error(f"[DB Error] {e}")
        return None

def generate_prices():
    prices = {}
    for symbol, base_price in PRICES.items():
        change = random.uniform(-0.0008, 0.0008)
        bid = base_price + change
        ask = bid + 0.0005
        prices[symbol] = {"bid": bid, "ask": ask}
    return prices

def on_emergency_close_all(reason):
    logger.critical(f"[EMERGENCY] {reason}")

def main():
    logger.info("="*60)
    logger.info("🚀 Paper Trading - No OpenAPI Required")
    logger.info(f"📊 Pairs: {', '.join(cfg.risk.target_symbols)}")
    logger.info("💹 Prices: Simulated Real-like Movement")
    logger.info("📝 Trades: Virtual Paper Trading")
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
    
    try:
        telegram_notifier.notify_system_event(
            "🚀 System Started\n"
            "📊 Paper Trading Active\n"
            "💹 Simulated Prices"
        )
    except:
        logger.warning("[Telegram] Optional service unavailable")
    
    logger.info("[System] Ready ✅")
    
    try:
        iteration = 0
        while True:
            iteration += 1
            prices = generate_prices()
            
            for symbol in cfg.risk.target_symbols:
                if symbol not in prices:
                    continue
                
                rate = prices[symbol]
                bid = rate.get("bid", 0)
                ask = rate.get("ask", 0)
                mid = (bid + ask) / 2
                
                if bid > 0 and ask > 0:
                    signal = market_scanner.on_price(symbol, bid, ask)
                    
                    if signal.value > 0:
                        if risk_manager.can_open_new_position():
                            lot_size = risk_manager.calculate_position_size_lots(4.0)
                            is_buy = signal.name == "BUY_REVERSION"
                            
                            entry_price = mid
                            if is_buy:
                                sl_price = entry_price - 0.0004
                                tp_price = entry_price + 0.0006
                            else:
                                sl_price = entry_price + 0.0004
                                tp_price = entry_price - 0.0006
                            
                            direction = "BUY" if is_buy else "SELL"
                            logger.info(
                                f"[TRADE] {symbol} {direction} "
                                f"{lot_size} lots @ {entry_price:.5f}"
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
                                        """, (symbol, direction, entry_price, sl_price, tp_price))
                                        trade_id = cur.fetchone()[0]
                                        conn.commit()
                                        
                                        try:
                                            telegram_notifier.notify_system_event(
                                                f"✅ Trade #{trade_id}\n"
                                                f"Pair: {symbol}\n"
                                                f"Direction: {direction}\n"
                                                f"Price: {entry_price:.5f}"
                                            )
                                        except:
                                            pass
                                except Exception as e:
                                    logger.error(f"[DB Error] {e}")
                                finally:
                                    conn.close()
            
            if iteration % 60 == 0:
                logger.info(f"[System] Running... Iteration {iteration}")
            
            time.sleep(30)
    
    except KeyboardInterrupt:
        logger.info("⏹️ Stopping...")
        try:
            telegram_notifier.notify_system_event("⏹️ System Stopped")
        except:
            pass
    except Exception as e:
        logger.critical(f"[Fatal Error] {e}")
        try:
            telegram_notifier.notify_system_event(f"💥 Error: {e}")
        except:
            pass

if __name__ == '__main__':
    main()
