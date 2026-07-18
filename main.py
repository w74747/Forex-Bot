"""
main.py - 3 Scalping Strategies (Fixed)
"""

import logging
import time
import random
from risk_manager import RiskManager
from telegram_notifier import TelegramNotifier
from config import Config
import psycopg2
from psycopg2.extras import RealDictCursor
from collections import deque

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
    def __init__(self, max_size=50):
        self.prices = deque(maxlen=max_size)
    
    def add(self, price):
        self.prices.append(price)
    
    def get_rsi(self, period=14):
        if len(self.prices) < period:
            return None
        prices = list(self.prices)[-period:]
        gains = sum(prices[i] - prices[i-1] for i in range(1, len(prices)) if prices[i] > prices[i-1])
        losses = sum(prices[i-1] - prices[i] for i in range(1, len(prices)) if prices[i] < prices[i-1])
        if period == 0:
            return 50
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
    
    def get_stochastic(self, period=5):
        if len(self.prices) < period:
            return None
        prices = list(self.prices)[-period:]
        lowest = min(prices)
        highest = max(prices)
        if highest == lowest:
            return 50
        return 100 * (prices[-1] - lowest) / (highest - lowest)

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

def close_trade(trade_id, exit_price, exit_reason, conn):
    """إغلاق صفقة"""
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM live_paper_trades WHERE id = %s", (trade_id,))
            trade = cur.fetchone()
            
            if not trade:
                return False
            
            entry_price = float(trade['entry_price'])
            is_buy = trade['direction'] == 'BUY'
            
            if is_buy:
                gross_pnl = (exit_price - entry_price) * 100000
            else:
                gross_pnl = (entry_price - exit_price) * 100000
            
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
            
            return True
    except Exception as e:
        logger.error(f"[Close Error] {e}")
        return False

def check_open_positions(prices, conn):
    """التحقق من الصفقات المفتوحة"""
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
                close_trade(trade_id, exit_price, exit_reason, conn)
    
    except Exception as e:
        logger.error(f"[Check Positions Error] {e}")

def strategy_rsi_ema(symbol, bid, ask, price_history):
    """استراتيجية RSI + EMA"""
    mid = (bid + ask) / 2
    price_history[symbol].add(mid)
    
    rsi = price_history[symbol].get_rsi(14)
    ema5 = price_history[symbol].get_ema(5)
    ema10 = price_history[symbol].get_ema(10)
    
    if rsi is None or ema5 is None or ema10 is None:
        return None
    
    if rsi < 30 and ema5 > ema10:
        return "BUY"
    elif rsi > 70 and ema5 < ema10:
        return "SELL"
    
    return None

def strategy_bb_stoch(symbol, bid, ask, price_history):
    """استراتيجية Bollinger Bands + Stochastic"""
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

def strategy_ema_cross(symbol, bid, ask, price_history):
    """استراتيجية EMA Crossover"""
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

def open_trade(symbol, direction, entry_price, strategy, telegram_notifier, conn):
    """فتح صفقة جديدة"""
    if direction == "BUY":
        sl_price = entry_price - 0.0004
        tp_price = entry_price + 0.0006
    else:
        sl_price = entry_price + 0.0004
        tp_price = entry_price - 0.0006
    
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
                f"@ {entry_price:.5f} TP:{tp_price:.5f} SL:{sl_price:.5f}"
            )
            
            strategy_name = {
                "RSI_EMA": "RSI + EMA",
                "BB_STOCH": "Bollinger + Stochastic",
                "EMA_CROSS": "EMA Crossover"
            }.get(strategy, strategy)
            
            try:
                telegram_notifier.notify_system_event(
                    f"✅ Trade #{trade_id}\n"
                    f"📌 {strategy_name}\n"
                    f"💱 {symbol} {direction}\n"
                    f"💹 @ {entry_price:.5f}"
                )
            except:
                pass
    
    except Exception as e:
        logger.error(f"[Open Trade Error] {e}")

def on_emergency_close_all(reason):
    logger.critical(f"[EMERGENCY] {reason}")

def main():
    logger.info("="*60)
    logger.info("🚀 Multi-Strategy Scalping Bot")
    logger.info("📊 3 Strategies Running in Parallel")
    logger.info("💰 Capital per Strategy: $333.33")
    logger.info("="*60)
    
    risk_manager = RiskManager(cfg.risk, on_emergency_close_all=on_emergency_close_all)
    telegram_notifier = TelegramNotifier(cfg.telegram)
    
    price_history = {symbol: PriceHistory() for symbol in cfg.risk.target_symbols}
    
    try:
        telegram_notifier.notify_system_event(
            "🚀 Multi-Strategy Bot Started\n"
            "📌 RSI + EMA\n"
            "📌 Bollinger + Stochastic\n"
            "📌 EMA Crossover"
        )
    except:
        pass
    
    logger.info("[System] Ready ✅")
    
    try:
        iteration = 0
        while True:
            iteration += 1
            prices = generate_prices()
            
            conn = get_db()
            if conn:
                check_open_positions(prices, conn)
            
            for symbol in cfg.risk.target_symbols:
                if symbol not in prices:
                    continue
                
                bid = prices[symbol]['bid']
                ask = prices[symbol]['ask']
                mid = (bid + ask) / 2
                
                if bid > 0 and ask > 0:
                    if risk_manager.can_open_new_position():
                        signal1 = strategy_rsi_ema(symbol, bid, ask, price_history)
                        if signal1:
                            open_trade(symbol, signal1, mid, "RSI_EMA", telegram_notifier, conn)
                        
                        signal2 = strategy_bb_stoch(symbol, bid, ask, price_history)
                        if signal2:
                            open_trade(symbol, signal2, mid, "BB_STOCH", telegram_notifier, conn)
                        
                        signal3 = strategy_ema_cross(symbol, bid, ask, price_history)
                        if signal3:
                            open_trade(symbol, signal3, mid, "EMA_CROSS", telegram_notifier, conn)
            
            if conn:
                conn.close()
            
            if iteration % 120 == 0:
                logger.info(f"[System] Running... Iteration {iteration}")
            
            time.sleep(30)
    
    except KeyboardInterrupt:
        logger.info("⏹️ Stopping...")
        try:
            telegram_notifier.notify_system_event("⏹️ Bot Stopped")
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
