"""
main.py - Forex Trading Bot with Exness
"""

import logging
import time
import os
from collections import deque
import psycopg2
from psycopg2.extras import RealDictCursor

from exness_connector import ExnessConnector
from telegram_notifier import TelegramNotifierV3

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger("forex_bot")

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
        return psycopg2.connect(os.getenv('DATABASE_URL'), connect_timeout=5)
    except Exception as e:
        logger.error(f"[DB Error] {e}")
        return None

def main():
    logger.info("="*60)
    logger.info("🚀 Forex Bot - Exness Trading")
    logger.info("="*60)
    
    # Exness Connection
    exness = ExnessConnector(
        os.getenv('EXNESS_SERVER'),
        os.getenv('EXNESS_LOGIN'),
        os.getenv('EXNESS_PASSWORD')
    )
    
    tg = TelegramNotifierV3({})
    ph = {s: PriceHistory(100) for s in ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD']}
    
    logger.info("[System] Ready ✅")
    iteration = 0
    
    while True:
        iteration += 1
        try:
            prices = exness.get_all_prices(['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD'])
            
            conn = get_db()
            if conn:
                # Process trades here
                conn.close()
        except Exception as e:
            logger.error(f"[Error] {e}")
        
        if iteration % 60 == 0:
            logger.info(f"[System] Running... {iteration} iterations")
        
        time.sleep(30)

if __name__ == '__main__':
    main()
