"""
main.py - Real Exness Trading via FIX Protocol
"""

import logging
import time
import os
from collections import deque
import psycopg2
from psycopg2.extras import RealDictCursor

from exness_fix import ExnessFIX
from config import Config

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

def main():
    logger.info("="*60)
    logger.info("🚀 Forex Bot - REAL Exness Trading")
    logger.info("="*60)
    
    # اتصل بـ Exness FIX مباشرة
    fix = ExnessFIX(
        os.getenv('EXNESS_LOGIN'),
        os.getenv('EXNESS_PASSWORD'),
        os.getenv('EXNESS_FIX_HOST', 'tradeapi.exness.com'),
        os.getenv('EXNESS_FIX_PORT', 3128)
    )
    
    if not fix.connected:
        logger.error("❌ Failed to connect to Exness")
        return
    
    ph = {s: PriceHistory(100) for s in ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD']}
    
    logger.info("[System] Ready ✅")
    iteration = 0
    
    while True:
        iteration += 1
        try:
            prices = fix.get_all_prices(['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD'])
            
            conn = get_db()
            if conn:
                for symbol in ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD']:
                    if symbol in prices:
                        bid, ask = prices[symbol]['bid'], prices[symbol]['ask']
                        if bid > 0 and ask > 0:
                            mid = (bid + ask) / 2
                            ph[symbol].add(mid)
                conn.close()
        except Exception as e:
            logger.error(f"[Error] {e}")
        
        if iteration % 60 == 0:
            logger.info(f"[System] Running... {iteration} iterations")
        
        time.sleep(30)

if __name__ == '__main__':
    main()
