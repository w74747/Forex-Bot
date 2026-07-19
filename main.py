"""
main.py - Enhanced 3 Strategies Scalping Bot
"""

import logging
import time
import random
from collections import deque
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

from config import Config
from capital_manager import CapitalManager
from telegram_notifier import TelegramNotifierV3
from monthly_tracker import MonthlyTracker

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger("forex_bot")

cfg = Config()

PRICES = {
    "EURUSD": 1.0850,
    "GBPUSD": 1.2750,
    "USDJPY": 149.50,
    "AUDUSD": 0.6580
}

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
        avg_gain = gains / period
        avg_loss = losses / period
        if avg_loss == 0:
            return 100 if avg_gain > 0 else 0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    def get_ema(self, period):
        if len(self.prices) < period:
            return None
        prices = list(self.prices)[-period:]
        return sum(prices) / len(prices)
    
    def get_macd(self):
        ema12 = self.get_ema(12)
        ema26 = self.get_ema(26)
        if ema12 is None or ema26 is None:
            return None, None
        return ema12 - ema26, ema12 - ema26
    
    def get_stochastic(self, period=5):
        if len(self.prices) < period:
            return None
        prices = list(self.prices)[-period:]
        lowest = min(prices)
        highest = max(prices)
        if highest == lowest:
            return 50
        return 100 * (prices[-1] - lowest) / (highest - lowest)
    
    def get_atr(self, period=14):
        if len(self.prices) < period + 1:
            return None
        prices = list(self.prices)[-(period+1):]
        tr_values = [abs(prices[i] - prices[i-1]) for i in range(1, len(prices))]
        return sum(tr_values) / len(tr_values) if tr_values else None

def get_db():
    try:
        return psycopg2.connect(cfg.database_url, connect_timeout=5)
    except Exception as e:
        logger.error(f"[DB Error] {e}")
        return None

def generate_prices():
    prices = {}
    for symbol, base_price in PRICES.items():
        change = random.uniform(-0.0015, 0.0015)
        bid = base_price + change
        ask = bid + 0.0005
        prices[symbol] = {"bid": bid, "ask": ask}
    return prices

def close_trade(trade_id, exit_price, exit_reason, conn, lot_size, telegram_notifier, capital_manager, monthly_tracker):
    if not conn:
        logger.error(f"[Close Trade] No database connection")
        return False
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM live_paper_trades WHERE id = %s", (trade_id,))
            trade = cur.fetchone()
            
            if not trade:
                return False
            
            entry_price = float(trade['entry_price'])
            is_buy = trade['direction'] == 'BUY'
            
            if is_buy:
                price_diff = exit_price - entry_price
            else:
                price_diff = entry_price - exit_price
            
            gross_pnl = price_diff * lot_size * 100000
            commission = abs(gross_pnl) * 0.0001
            net_pnl = gross_pnl - commission
            
            cur.execute("""
                UPDATE live_paper_trades 
                SET status = 'CLOSED', 
                    exit_price = %s, 
                    exit_reason = %s, 
                    gross_pnl = %s,
                    commission = %s,
                    net_pnl = %s,
                    closed_at = NOW()
                WHERE id = %s
            """, (exit_price, exit_reason, gross_pnl, commission, net_pnl, trade_id))
            
            conn.commit()
            
            pnl_str = f"+${net_pnl:.2f}" if net_pnl > 0 else f"-${abs(net_pnl):.2f}"
            strategy = trade['strategy'] if trade['strategy'] else 'UNKNOWN'
            logger.info(
                f"[{strategy}] CLOSE #{trade_id} {trade['symbol']} "
                f"{exit_reason} @ {exit_price:.5f} | {pnl_str}"
            )
            
            try:
                monthly_tracker.record_trade(gross_pnl, commission)
            except:
                pass
            
            return True
    except Exception as e:
        try:
            conn.rollback()
        except:
            pass
        logger.error(f"[Close Error] {e}")
        return False

def check_open_positions(prices, conn, capital_manager, telegram_notifier, monthly_tracker):
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM live_paper_trades WHERE status = 'OPEN'")
            open_trades = cur.fetchall()
        
        for trade in open_trades:
            symbol = trade['symbol']
            trade_id = trade['id']
            
            if symbol not in prices:
                continue
            
            bid = prices[symbol]['bid']
            ask = prices[symbol]['ask']
            mid = (bid + ask) / 2
            
            sl_price = float(trade['sl_price'])
            tp_price = float(trade['tp_price'])
            is_buy = trade['direction'] == 'BUY'
            entry_price = float(trade['entry_price'])
            
            lot_size = capital_manager.get_optimal_lot_size(entry_price, trade['strategy'])
            
            should_close = False
            exit_reason = None
            exit_price = None
            
            if is_buy:
                if mid >= tp_price:
                    should_close = True
                    exit_reason = "TAKE_PROFIT"
                    exit_price = tp_price
                elif mid <= sl_price:
                    should_close = True
                    exit_reason = "STOP_LOSS"
                    exit_price = sl_price
            else:
                if mid <= tp_price:
                    should_close = True
                    exit_reason = "TAKE_PROFIT"
                    exit_price = tp_price
                elif mid >= sl_price:
                    should_close = True
                    exit_reason = "STOP_LOSS"
                    exit_price = sl_price
            
            if should_close:
                close_trade(trade_id, exit_price, exit_reason, conn, lot_size, telegram_notifier, capital_manager, monthly_tracker)
    
    except Exception as e:
        logger.error(f"[Check Positions Error] {e}")

def strategy_rsi_ema_macd(symbol, bid, ask, price_history):
    mid = (bid + ask) / 2
    price_history[symbol].add(mid)
    
    rsi = price_history[symbol].get_rsi(14)
    ema5 = price_history[symbol].get_ema(5)
    ema10 = price_history[symbol].get_ema(10)
    macd, _ = price_history[symbol].get_macd()
    
    if rsi is None or ema5 is None or ema10 is None or macd is None:
        return None
    
    if rsi < 30 and ema5 > ema10 and macd > 0:
        return "BUY"
    elif rsi > 70 and ema5 < ema10 and macd < 0:
        return "SELL"
    
    return None

def strategy_bb_stoch_volume(symbol, bid, ask, price_history):
    mid = (bid + ask) / 2
    price_history[symbol].add(mid)
    
    stoch = price_history[symbol].get_stochastic(5)
    
    if stoch is None:
        return None
    
    if stoch < 20:
        return "BUY"
    elif stoch > 80:
        return "SELL"
    
    return None

def strategy_ema_cross_atr(symbol, bid, ask, price_history):
    mid = (bid + ask) / 2
    price_history[symbol].add(mid)
    
    ema5 = price_history[symbol].get_ema(5)
    ema10 = price_history[symbol].get_ema(10)
    ema20 = price_history[symbol].get_ema(20)
    
    if ema5 is None or ema10 is None or ema20 is None:
        return None
    
    if ema5 > ema10 > ema20:
        return "BUY"
    elif ema5 < ema10 < ema20:
        return "SELL"
    
    return None

def calculate_dynamic_tp_sl(mid_price, is_buy, atr_value):
    if atr_value is None:
        atr_value = 0.0005
    
    sl_distance = atr_value * 1.5
    tp_distance = atr_value * 2.5
    
    if is_buy:
        sl_price = mid_price - sl_distance
        tp_price = mid_price + tp_distance
    else:
        sl_price = mid_price + sl_distance
        tp_price = mid_price - tp_distance
    
    return sl_price, tp_price

def open_trade(symbol, direction, entry_price, strategy, telegram_notifier, conn, capital_manager, atr_value=None):
    is_buy = direction == "BUY"
    sl_price, tp_price = calculate_dynamic_tp_sl(entry_price, is_buy, atr_value)
    lot_size = capital_manager.get_optimal_lot_size(entry_price, strategy)
    
    if not conn:
        logger.error(f"[Open Trade] No database connection")
        return
    
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO live_paper_trades 
                (symbol, direction, entry_price, sl_price, tp_price, status, strategy, opened_at)
                VALUES (%s, %s, %s, %s, %s, 'OPEN', %s, NOW())
                RETURNING id
            """, (symbol, direction, entry_price, sl_price, tp_price, strategy))
            
            trade_id = cur.fetchone()[0]
            conn.commit()
            
            logger.info(
                f"[{strategy}] OPEN #{trade_id} {symbol} {direction} "
                f"{lot_size} lots @ {entry_price:.5f} TP:{tp_price:.5f} SL:{sl_price:.5f}"
            )
    
    except Exception as e:
        try:
            conn.rollback()
        except:
            pass
        logger.error(f"[Open Trade Error] {e}")

def main():
    logger.info("="*60)
    logger.info("🚀 Enhanced Multi-Strategy Scalping Bot")
    logger.info(f"📊 Mode: {'LIVE 🔴' if not cfg.dry_run else 'PAPER TRADING 📝'}")
    logger.info(f"💰 Starting Balance: ${cfg.capital.starting_balance}")
    logger.info(f"⚡ Risk Per Trade: {cfg.capital.risk_per_trade_pct}%")
    logger.info("="*60)
    
    capital_manager = CapitalManager(
        database_url=cfg.database_url,
        starting_balance=cfg.capital.starting_balance,
        risk_per_trade=cfg.capital.risk_per_trade_pct
    )
    
    telegram_notifier = TelegramNotifierV3(cfg.telegram)
    monthly_tracker = MonthlyTracker()
    price_history = {symbol: PriceHistory(100) for symbol in cfg.risk.target_symbols}
    
    try:
        mode = "LIVE 🔴" if not cfg.dry_run else "PAPER TRADING 📝"
        telegram_notifier.notify_system_event(
            f"🚀 Bot Started\n"
            f"📌 3 Improved Strategies\n"
            f"💰 Balance: ${cfg.capital.starting_balance}\n"
            f"🔒 Mode: {mode}"
        )
    except Exception as e:
        logger.warning(f"[Telegram] {e}")
    
    logger.info("[System] Ready ✅")
    
    iteration = 0
    try:
        while True:
            iteration += 1
            prices = generate_prices()
            
            conn = None
            try:
                conn = get_db()
                if conn:
                    check_open_positions(prices, conn, capital_manager, telegram_notifier, monthly_tracker)
                    
                    for symbol in cfg.risk.target_symbols:
                        if symbol not in prices:
                            continue
                        
                        bid = prices[symbol]['bid']
                        ask = prices[symbol]['ask']
                        mid = (bid + ask) / 2
                        
                        if bid > 0 and ask > 0:
                            signal1 = strategy_rsi_ema_macd(symbol, bid, ask, price_history)
                            if signal1:
                                atr1 = price_history[symbol].get_atr(14)
                                open_trade(symbol, signal1, mid, "RSI_EMA_MACD", telegram_notifier, conn, capital_manager, atr1)
                            
                            signal2 = strategy_bb_stoch_volume(symbol, bid, ask, price_history)
                            if signal2:
                                atr2 = price_history[symbol].get_atr(14)
                                open_trade(symbol, signal2, mid, "BB_STOCH", telegram_notifier, conn, capital_manager, atr2)
                            
                            signal3 = strategy_ema_cross_atr(symbol, bid, ask, price_history)
                            if signal3:
                                atr3 = price_history[symbol].get_atr(14)
                                open_trade(symbol, signal3, mid, "EMA_ATR", telegram_notifier, conn, capital_manager, atr3)
            except Exception as e:
                logger.error(f"[Iteration Error] {e}")
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass
            
            if iteration % 120 == 0:
                logger.info(f"[System] Running... Iteration {iteration}")
            
            time.sleep(30)
    
    except KeyboardInterrupt:
        logger.info("⏹️ Stopping...")
        try:
            telegram_notifier.notify_system_event("⏹️ Bot Stopped")
        except Exception as e:
            logger.warning(f"[Telegram] {e}")
    except Exception as e:
        logger.critical(f"[Fatal Error] {e}")
        try:
            telegram_notifier.notify_system_event(f"💥 Error: {e}")
        except Exception as ex:
            logger.warning(f"[Telegram] {ex}")

if __name__ == '__main__':
    main()
