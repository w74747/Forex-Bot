import logging
import time
import os
from collections import deque
import psycopg2
from psycopg2.extras import RealDictCursor

from config import Config
from capital_manager import CapitalManager
from telegram_notifier import TelegramNotifierV3
from ctrader_openapi import CTraderOpenAPI

logging.basicConfig(level=logging.DEBUG, format='[%(levelname)s] %(message)s')
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
    logger.info("🚀 Forex Bot - REAL cTrader Prices")
    logger.info("="*60)
    
    # تحقق من البيانات
    logger.info(f"Client ID: {cfg.ctrader.client_id[:20]}...")
    logger.info(f"Access Token: {cfg.ctrader.access_token[:20]}...")
    logger.info(f"Account ID: {cfg.ctrader.account_id}")
    
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
    
    logger.info("[System] Ready ✅")
    iteration = 0
    
    while True:
        iteration += 1
        try:
            # احصل على أسعار حقيقية
            logger.debug(f"[Iteration {iteration}] Fetching prices...")
            prices = ctrader.get_all_prices(cfg.risk.target_symbols)
            
            logger.debug(f"[Prices] {prices}")
            
            # تحقق من الأسعار
            has_prices = False
            for symbol, price_data in prices.items():
                if price_data and price_data.get('bid', 0) > 0:
                    has_prices = True
                    logger.info(f"[Price OK] {symbol} BID:{price_data['bid']:.5f}")
            
            if not has_prices:
                logger.warning("⚠️ No valid prices received!")
            
            conn = get_db()
            if conn:
                for symbol in cfg.risk.target_symbols:
                    if symbol in prices:
                        bid, ask = prices[symbol].get('bid', 0), prices[symbol].get('ask', 0)
                        logger.debug(f"[Check] {symbol} BID:{bid} ASK:{ask}")
                        
                        if bid > 0 and ask > 0:
                            mid = (bid + ask) / 2
                            ph[symbol].add(mid)
                            rsi = ph[symbol].get_rsi(14)
                            logger.debug(f"[RSI] {symbol} = {rsi}")
                conn.close()
        except Exception as e:
            logger.error(f"[Error] {e}", exc_info=True)
        
        if iteration % 60 == 0:
            logger.info(f"[System] Running... {iteration} iterations")
        
        time.sleep(30)

if __name__ == '__main__':
    main()
