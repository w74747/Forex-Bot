"""
main.py - Forex Trading Bot with Real cTrader Prices
"""

import logging
import time
import os
from collections import deque
import psycopg2
from psycopg2.extras import RealDictCursor

from config import Config
from capital_manager import CapitalManager
from telegram_notifier import TelegramNotifierV3
from monthly_tracker import MonthlyTracker
from ctrader_openapi import CTraderOpenAPI

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

def close_trade(trade_id, exit_price, exit_reason, conn, lot_size, tg):
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
            gross_pnl = diff * lot_size * 100000
            net_pnl = gross_pnl - abs(gross_pnl) * 0.0001
            
            cur.execute("""UPDATE live_paper_trades SET status='CLOSED', exit_price=%s, exit_reason=%s, net_pnl=%s, closed_at=NOW() WHERE id=%s""", 
                       (exit_price, exit_reason, net_pnl, trade_id))
            conn.commit()
            
            pnl_str = f"+${net_pnl:.2f}" if net_pnl > 0 else f"-${abs(net_pnl):.2f}"
            logger.info(f"[CLOSE] #{trade_id} {trade['symbol']} {exit_reason} @ {exit_price:.5f} | {pnl_str}")
            
            try:
                tg.notify_trade(trade_id, trade['symbol'], net_pnl, exit_reason, "CLOSE")
            except:
                pass
    except Exception as e:
        try:
            conn.rollback()
        except:
            pass
        logger.error(f"[Close Error] {e}")

def check_positions(prices, conn, tg):
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
                
                should_close = False
                reason = None
                exit_p = None
                
                if is_buy:
                    if mid >= tp:
                        should_close, reason, exit_p = True, "TAKE_PROFIT", tp
                    elif mid <= sl:
                        should_close, reason, exit_p = True, "STOP_LOSS", sl
                else:
                    if mid <= tp:
                        should_close, reason, exit_p = True, "TAKE_PROFIT", tp
                    elif mid >= sl:
                        should_close, reason, exit_p = True, "STOP_LOSS", sl
                
                if should_close:
                    close_trade(trade['id'], exit_p, reason, conn, 0.001, tg)
    except:
        pass

def strategy_rsi(symbol, bid, ask, ph):
    if bid <= 0 or ask <= 0:
        return None
    mid = (bid + ask) / 2
    ph[symbol].add(mid)
    rsi = ph[symbol].get_rsi(14)
    if rsi is None:
        return None
    return "BUY" if rsi < 30 else ("SELL" if rsi > 70 else None)

def open_trade(symbol, direction, entry_price, strategy, conn, tg):
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
            logger.info(f"[OPEN] #{trade_id} {symbol} {direction} @ {entry_price:.5f} (REAL PRICE)")
            
            try:
                tg.notify_trade(trade_id, symbol, entry_price, direction, "OPEN")
            except:
                pass
    except Exception as e:
        try:
            conn.rollback()
        except:
            pass
        logger.error(f"[Open Error] {e}")

def main():
    logger.info("="*60)
    logger.info("🚀 Forex Bot - REAL cTrader Prices")
    logger.info("="*60)
    
    # إنشاء موصل cTrader الحقيقي
    if not cfg.ctrader.access_token:
        logger.error("❌ No cTrader access token found!")
        return
    
    ctrader = CTraderOpenAPI(
        cfg.ctrader.client_id,
        cfg.ctrader.access_token,
        cfg.ctrader.account_id
    )
    
    logger.info("✅ Connected to cTrader OpenAPI")
    
    tg = TelegramNotifierV3(cfg.telegram)
    ph = {s: PriceHistory(100) for s in cfg.risk.target_symbols}
    
    try:
        tg.notify_system_event("🚀 Bot Started - REAL cTrader Prices")
    except:
        pass
    
    logger.info("[System] Ready ✅")
    iteration = 0
    
    while True:
        iteration += 1
        try:
            # احصل على أسعار حقيقية من cTrader
            prices = ctrader.get_all_prices(cfg.risk.target_symbols)
            
            conn = get_db()
            if conn:
                check_positions(prices, conn, tg)
                for symbol in cfg.risk.target_symbols:
                    if symbol in prices:
                        bid, ask = prices[symbol]['bid'], prices[symbol]['ask']
                        if bid > 0 and ask > 0:
                            if signal := strategy_rsi(symbol, bid, ask, ph):
                                open_trade(symbol, signal, (bid + ask) / 2, "RSI", conn, tg)
                conn.close()
        except Exception as e:
            logger.error(f"[Error] {e}")
        
        if iteration % 60 == 0:
            logger.info(f"[System] Running... {iteration} iterations")
        
        time.sleep(30)

if __name__ == '__main__':
    main()
