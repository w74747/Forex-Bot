"""
main.py - Enhanced 3 Strategies with Dynamic Capital Management & Live Trading
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
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger("forex_bot")

cfg = Config()

PRICES = {
    "EURUSD": 1.0850,
    "GBPUSD": 1.2750,
    "USDJPY": 149.50,
    "AUDUSD": 0.6580
}

class CapitalManager:
    def __init__(self, initial_balance=1000):
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.strategy_balances = {
            "RSI_EMA_MACD": initial_balance * 0.333,
            "BB_STOCH": initial_balance * 0.333,
            "EMA_ATR": initial_balance * 0.334
        }
        self.last_rebalance = datetime.now()
        self.rebalance_interval = 3600  # 1 hour
    
    def update_balance(self, new_balance):
        """تحديث الرصيد"""
        change = new_balance - self.current_balance
        self.current_balance = new_balance
        
        # توزيع الأرباح/الخسائر حسب النسبة
        for strategy in self.strategy_balances:
            ratio = 0.333 if strategy != "EMA_ATR" else 0.334
            self.strategy_balances[strategy] += change * ratio
        
        logger.info(
            f"[Capital] Balance updated: ${self.current_balance:.2f} | "
            f"RSI: ${self.strategy_balances['RSI_EMA_MACD']:.2f} | "
            f"BB: ${self.strategy_balances['BB_STOCH']:.2f} | "
            f"EMA: ${self.strategy_balances['EMA_ATR']:.2f}"
        )
    
    def get_position_size(self, strategy, entry_price, risk_pct=1.0):
        """حساب حجم الصفقة الديناميكي"""
        strategy_balance = self.strategy_balances.get(strategy, 1000)
        risk_amount = strategy_balance * (risk_pct / 100)
        
        # حساب حجم الصفقة بناءً على السعر
        if entry_price <= 0:
            return 0.01
        
        lot_size = risk_amount / (entry_price * 100000)
        
        # حد أدنى وحد أقصى
        lot_size = max(0.01, min(lot_size, 10.0))
        
        return round(lot_size, 2)
    
    def should_rebalance(self):
        """التحقق من الحاجة لإعادة التوازن"""
        elapsed = (datetime.now() - self.last_rebalance).total_seconds()
        return elapsed >= self.rebalance_interval
    
    def rebalance(self):
        """إعادة توازن الأموال"""
        total = sum(self.strategy_balances.values())
        self.strategy_balances["RSI_EMA_MACD"] = total * 0.333
        self.strategy_balances["BB_STOCH"] = total * 0.333
        self.strategy_balances["EMA_ATR"] = total * 0.334
        
        self.last_rebalance = datetime.now()
        
        logger.info(
            f"[Rebalance] Capital rebalanced | "
            f"RSI: ${self.strategy_balances['RSI_EMA_MACD']:.2f} | "
            f"BB: ${self.strategy_balances['BB_STOCH']:.2f} | "
            f"EMA: ${self.strategy_balances['EMA_ATR']:.2f}"
        )

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
    
    def get_macd(self):
        ema12 = self.get_ema(12)
        ema26 = self.get_ema(26)
        if ema12 is None or ema26 is None:
            return None, None
        macd_line = ema12 - ema26
        return macd_line, macd_line
    
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
        tr_values = []
        for i in range(1, len(prices)):
            tr = prices[i] - prices[i-1]
            tr_values.append(abs(tr))
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

def calculate_dynamic_tp_sl(mid_price, is_buy, atr_value, symbol):
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
    """فتح صفقة مع حجم ديناميكي"""
    is_buy = direction == "BUY"
    sl_price, tp_price = calculate_dynamic_tp_sl(entry_price, is_buy, atr_value, symbol)
    
    # احصل على حجم الصفقة الديناميكي
    lot_size = capital_manager.get_position_size(strategy, entry_price, risk_pct=1.0)
    
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
            
            strategy_name = {
                "RSI_EMA_MACD": "RSI + EMA + MACD",
                "BB_STOCH": "Bollinger + Stochastic",
                "EMA_ATR": "EMA + ATR"
            }.get(strategy, strategy)
            
            try:
                telegram_notifier.notify_system_event(
                    f"✅ Trade #{trade_id}\n"
                    f"📌 {strategy_name}\n"
                    f"💱 {symbol} {direction}\n"
                    f"📊 Size: {lot_size} lots\n"
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
    logger.info("🚀 Enhanced Multi-Strategy Bot with Dynamic Capital")
    logger.info(f"📊 Mode: {'LIVE' if not cfg.dry_run else 'PAPER TRADING'}")
    logger.info(f"💰 DRY_RUN: {cfg.dry_run}")
    logger.info("="*60)
    
    risk_manager = RiskManager(cfg.risk, on_emergency_close_all=on_emergency_close_all)
    telegram_notifier = TelegramNotifier(cfg.telegram)
    capital_manager = CapitalManager(initial_balance=1000)
    
    price_history = {symbol: PriceHistory(100) for symbol in cfg.risk.target_symbols}
    
    try:
        mode = "LIVE 🔴" if not cfg.dry_run else "PAPER TRADING 📝"
        telegram_notifier.notify_system_event(
            f"🚀 Enhanced Bot Started\n"
            f"📌 3 Improved Strategies\n"
            f"💰 Dynamic Capital Management\n"
            f"🔒 Mode: {mode}"
        )
    except:
        pass
    
    logger.info("[System] Ready ✅")
    
    try:
        iteration = 0
        while True:
            iteration += 1
            prices = generate_prices()
            
            # تحديث الرصيد كل 10 تكرارات (كل ~5 دقائق)
            if iteration % 10 == 0:
                current_balance = 1000 + random.uniform(-50, 100)  # محاكاة تغيير الرصيد
                capital_manager.update_balance(current_balance)
            
            # إعادة توازن كل ساعة
            if capital_manager.should_rebalance():
                capital_manager.rebalance()
            
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
                        # Strategy 1
                        signal1 = strategy_rsi_ema_macd(symbol, bid, ask, price_history)
                        if signal1:
                            atr1 = price_history[symbol].get_atr(14)
                            open_trade(symbol, signal1, mid, "RSI_EMA_MACD", telegram_notifier, conn, capital_manager, atr1)
                        
                        # Strategy 2
                        signal2 = strategy_bb_stoch_volume(symbol, bid, ask, price_history)
                        if signal2:
                            atr2 = price_history[symbol].get_atr(14)
                            open_trade(symbol, signal2, mid, "BB_STOCH", telegram_notifier, conn, capital_manager, atr2)
                        
                        # Strategy 3
                        signal3 = strategy_ema_cross_atr(symbol, bid, ask, price_history)
                        if signal3:
                            atr3 = price_history[symbol].get_atr(14)
                            open_trade(symbol, signal3, mid, "EMA_ATR", telegram_notifier, conn, capital_manager, atr3)
            
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
