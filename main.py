"""
main.py - Exness Forex Trading Bot
"""

import logging
import time
from collections import deque

from config import ExnessConfig, TradingConfig
from mt5_connector import MT5Connector
from database import Database
from telegram_notify import TelegramNotifier
from strategies import TradingStrategies

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger("bot")

class ForexBot:
    def __init__(self):
        logger.info("="*60)
        logger.info("🚀 Exness Forex Trading Bot")
        logger.info("="*60)
        
        self.mt5 = MT5Connector()
        self.db = Database()
        self.telegram = TelegramNotifier()
        self.price_history = {s: deque(maxlen=50) for s in TradingConfig.SYMBOLS}
        
        if not self.mt5.connected:
            logger.error("❌ Failed to connect to Exness")
            raise Exception("MT5 Connection failed")
        
        logger.info("✅ Bot Initialized")
    
    def get_current_prices(self):
        """احصل على الأسعار الحالية"""
        return self.mt5.get_all_prices(TradingConfig.SYMBOLS)
    
    def analyze_symbol(self, symbol):
        """حلل الرمز"""
        prices = self.price_history[symbol]
        if len(prices) < 20:
            return None
        
        # جرب استراتيجيات متعددة
        rsi_signal = TradingStrategies.rsi_strategy(list(prices))
        ma_signal = TradingStrategies.moving_average_strategy(list(prices))
        
        # تحتاج إشارتين لفتح صفقة
        if rsi_signal == ma_signal and rsi_signal:
            return rsi_signal
        return None
    
    def run(self):
        """شغّل البوت"""
        logger.info("[System] Ready ✅")
        iteration = 0
        
        try:
            while True:
                iteration += 1
                
                # احصل على الأسعار الحالية
                prices = self.get_current_prices()
                
                # أضف للسجل التاريخي
                for symbol, price_data in prices.items():
                    if price_data['bid'] > 0:
                        mid_price = (price_data['bid'] + price_data['ask']) / 2
                        self.price_history[symbol].append(mid_price)
                        logger.info(f"[{symbol}] BID:{price_data['bid']:.5f} ASK:{price_data['ask']:.5f}")
                
                # تحليل كل رمز
                for symbol in TradingConfig.SYMBOLS:
                    signal = self.analyze_symbol(symbol)
                    if signal:
                        self.open_trade(symbol, signal)
                
                # تحقق من الصفقات المفتوحة
                self.check_open_positions(prices)
                
                if iteration % 60 == 0:
                    logger.info(f"[System] Running... {iteration} iterations")
                
                time.sleep(30)
        
        except KeyboardInterrupt:
            logger.info("⏹️ Bot stopped")
        except Exception as e:
            logger.error(f"[Fatal] {e}")
            self.telegram.notify_error(str(e))
        finally:
            self.mt5.shutdown()
    
    def open_trade(self, symbol, direction):
        """فتح صفقة"""
        try:
            # احصل على السعر الحالي
            price = self.mt5.get_price(symbol)
            if price['bid'] <= 0:
                return
            
            # احسب SL و TP
            entry = (price['bid'] + price['ask']) / 2
            if direction == "BUY":
                sl = entry - 0.0050
                tp = entry + 0.0100
            else:
                sl = entry + 0.0050
                tp = entry - 0.0100
            
            # فتح الصفقة على MT5
            result = self.mt5.open_trade(symbol, direction, TradingConfig.LOT_SIZE, sl, tp)
            if result:
                self.telegram.notify_trade_open(symbol, direction, entry)
                logger.info(f"✅ OPEN: {symbol} {direction} @ {entry:.5f}")
        except Exception as e:
            logger.error(f"Error opening trade: {e}")
    
    def check_open_positions(self, prices):
        """تحقق من الصفقات المفتوحة"""
        try:
            positions = self.mt5.get_positions()
            for pos in positions:
                symbol = pos.symbol
                if symbol in prices:
                    current_price = prices[symbol]
                    mid = (current_price['bid'] + current_price['ask']) / 2
                    
                    pnl = pos.profit
                    
                    logger.info(f"[Position] {symbol} P&L: ${pnl:.2f}")
        except Exception as e:
            logger.error(f"Error checking positions: {e}")

if __name__ == '__main__':
    bot = ForexBot()
    bot.run()
