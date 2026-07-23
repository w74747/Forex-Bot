"""
main.py - Forex Trading Bot with Exness
"""

import logging
import time
import os
from collections import deque
import psycopg2
from psycopg2.extras import RealDictCursor

from config import Config
from exness_connector import ExnessConnector
from telegram_notifier import TelegramNotifierV3

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger("forex_bot")

cfg = Config()

class PriceHistory:
    def __init__(self, max_size=100):
        self.prices = deque(maxlen=max_size)
    
    def add(self, price):
        self.prices.append(price)
    
    def get_rsi(self, period=14):
        if len(self.prices) < period:
            return None
        prices = list(self.prices)[-period:]
        gains = sum(prices[i] - prices[i-1] for i in range(1, len(prices)) if prices[i] > prices[i-1])
        losses = sum(prices[i-1] - prices[i] for i in range(1, len(prices)) if prices[i] < prices[i-1])
        avg_gain = gains / period if gains > 0 else 0
        avg_loss = losses / period if losses > 0 else 0
        if avg_loss == 0:
            return 100 if avg_gain > 0 else 0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

def get_db():
    try:
        return psycopg2.connect(cfg.database_url, connect_timeout=5)
    except Exception as e:
        logger.error(f"[DB Error] {e}")
        return None

def close_trade(trade_id, exit_price, exit_reason, conn):
    if not conn:
        return
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM live_paper_trades WHERE id = %s", (trade_id,))
            trade = cur.fetchone()
            if not trade:
                return
            
            entry = float(trade['entry_price'])
            is_buy = trade['direction'] == 'BUY'
            diff = (exit_price - entry) if is_buy else (entry - exit_price)
            net_pnl = diff * 0.01 * 100000 - abs(diff * 0.01 * 100000) * 0.0001
            
            cur.execute("""UPDATE live_paper_trades SET status='CLOSED', exit_price=%s, exit_reason=%s, net_pnl=%s, closed_at=NOW() WHERE id=%s""", 
                       (exit_price, exit_reason, net_pnl, trade_id))
            conn.commit()
            
            pnl_str = f"+${net_pnl:.2f}" if net_pnl > 0 else f"-${abs(net_pnl):.2f}"
            logger.info(f"[CLOSE] #{trade_id} {trade['symbol']} {exit_reason} @ {exit_price:.5f} | {pnl_str}")
    except Exception as e:
        try:
            conn.rollback()
        except:
            pass
        logger.error(f"[Close Error] {e}")

def check_positions(prices, conn):
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM live_paper_trades WHERE status='OPEN'")
            for trade in cur.fetchall():
                if trade['symbol'] not in prices:
                    continue
                bid, ask = prices[trade['symbol']]['bid'], prices[trade['symbol']]['ask']
                if bid <= 0 or ask <= 0:
                    continue
                mid = (bid + ask) / 2
                sl, tp = float(trade['sl_price']), float(trade['tp_price'])
                is_buy = trade['direction'] == 'BUY'
                
                if (is_buy and mid >= tp) or (not is_buy and mid <= tp):
                    close_trade(trade['id'], tp, "TAKE_PROFIT", conn)
                elif (is_buy and mid <= sl) or (not is_buy and mid >= sl):
                    close_trade(trade['id'], sl, "STOP_LOSS", conn)
    except:
        pass

def open_trade(symbol, direction, entry_price, strategy, conn):
    if not conn or entry_price <= 0:
        return
    sl = entry_price - 0.0005 if direction == "BUY" else entry_price + 0.0005
    tp = entry_price + 0.001 if direction == "BUY" else entry_price - 0.001
    
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO live_paper_trades (symbol, direction, entry_price, sl_price, tp_price, status, strategy, opened_at) VALUES (%s, %s, %s, %s, %s, 'OPEN', %s, NOW()) RETURNING id",
                       (symbol, direction, entry_price, sl, tp, strategy))
            trade_id = cur.fetchone()[0]
            conn.commit()
            logger.info(f"[OPEN] #{trade_id} {symbol} {direction} @ {entry_price:.5f}")
    except Exception as e:
        try:
            conn.rollback()
        except:
            pass
        logger.error(f"[Open Error] {e}")

def main():
    logger.info("="*60)
    logger.info("🚀 Forex Bot - Exness Trading")
    logger.info("="*60)
    
    if not cfg.exness.enabled:
        logger.error("❌ Exness credentials not found!")
        return
    
    exness = ExnessConnector(cfg.exness.server, cfg.exness.login, cfg.exness.password)
    tg = TelegramNotifierV3(cfg.telegram)
    ph = {s: PriceHistory(100) for s in ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD']}
    
    try:
        tg.notify_system_event("🚀 Bot Started - Exness Trading")
    except:
        pass
    
    logger.info("[System] Ready ✅")
    iteration = 0
    
    while True:
        iteration += 1
        try:
            prices = exness.get_all_prices(['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD'])
            
            conn = get_db()
            if conn:
                check_positions(prices, conn)
                for symbol in ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD']:
                    if symbol in prices:
                        bid, ask = prices[symbol]['bid'], prices[symbol]['ask']
                        if bid > 0 and ask > 0:
                            mid = (bid + ask) / 2
                            ph[symbol].add(mid)
                            rsi = ph[symbol].get_rsi(14)
                            if rsi and rsi < 30:
                                open_trade(symbol, "BUY", mid, "RSI", conn)
                            elif rsi and rsi > 70:
                                open_trade(symbol, "SELL", mid, "RSI", conn)
                conn.close()
        except Exception as e:
            logger.error(f"[Error] {e}")
        
        if iteration % 60 == 0:
            logger.info(f"[System] Running... {iteration} iterations")
        
        time.sleep(30)

if __name__ == '__main__':
    main()
